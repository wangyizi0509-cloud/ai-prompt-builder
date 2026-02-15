from __future__ import annotations

from graph.state import create_initial_state
from onboarding import onboarding_agent as onboarding_module


def _base_collected_info() -> dict:
    return {
        "raw_inputs": [],
        "user_profile": {},
        "crush_profile": {},
        "pain_points": [],
    }


def _base_submit_patch() -> dict:
    return {
        "pending_crushe_guide": True,
        "onboarding_completed": False,
        "onboarding_handoff": {
            "collected_context": _base_collected_info(),
            "recommendation": "信息已收集完毕，进入主流程进一步分析。",
            "suggested_action": "建议进行现状分析",
            "reason": "Onboarding 收集完成。",
        },
        "collected_info": _base_collected_info(),
    }


def test_submit_sequence_emits_two_pending_responses_in_order(monkeypatch):
    class DummyLLM:
        def invoke(self, *_args, **_kwargs):
            raise AssertionError("tool-path should not call llm fallback invoke")

    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: DummyLLM())

    pre_submit = "截图看完了，情况比你想的复杂，让我先给你一张局势初判卡。"
    post_submit = "我的初步判断先到这里。真正的攻坚战现在才开始。"

    def _fake_supervisor(**kwargs):
        return {
            "new_messages": [
                {
                    "role": "assistant",
                    "content": pre_submit,
                    "tool_calls": [
                        {
                            "name": "submit_onboarding",
                            "args": {
                                "response": "兜底文案",
                                "recommendation": "信息已收集完毕，进入主流程进一步分析。",
                                "suggested_action": "建议进行现状分析",
                                "reason": "已满足 MAS",
                            },
                        }
                    ],
                },
                {"role": "tool", "name": "submit_onboarding", "content": "已提交"},
                {"role": "assistant", "content": post_submit},
            ],
            "patches": [_base_submit_patch()],
        }

    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _fake_supervisor)

    out = onboarding_module.onboarding_agent_node(create_initial_state("我想追一个女生"))

    assert out.get("pending_crushe_guide") is True
    assert out.get("onboarding_completed") is False
    pending = out.get("pending_responses") or []
    assert [item.get("phase") for item in pending] == ["pre_submit", "post_submit"]
    assert pending[0].get("content") == pre_submit
    assert pending[1].get("content") == post_submit


def test_submit_called_but_patch_missing_does_not_fallback_or_resubmit(monkeypatch):
    class DummyLLM:
        def invoke(self, *_args, **_kwargs):
            raise AssertionError("submit main path should not run legacy llm invoke")

    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: DummyLLM())

    submit_tool_calls = {"count": 0}

    class _FakeSubmitTool:
        name = "submit_onboarding"

        def invoke(self, _payload):
            submit_tool_calls["count"] += 1
            return {"state_patch": {}}

    monkeypatch.setattr(onboarding_module, "create_submit_onboarding_tool", lambda _getter: _FakeSubmitTool())

    recommendation = "信息足够，建议进入主流程做深度分析。"

    def _fake_supervisor(**kwargs):
        return {
            "new_messages": [
                {
                    "role": "assistant",
                    "content": "我先给你做初判。",
                    "tool_calls": [
                        {
                            "name": "submit_onboarding",
                            "args": {
                                "response": "兜底短句",
                                "recommendation": recommendation,
                                "suggested_action": "建议进行现状分析",
                                "reason": "已满足 MAS",
                            },
                        }
                    ],
                }
            ],
            "patches": [
                {
                    "inquiry_answers": {"answers": {"q1": "最近回复忽冷忽热"}},
                }
            ],
        }

    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _fake_supervisor)

    out = onboarding_module.onboarding_agent_node(create_initial_state("她最近回复很慢"))

    assert submit_tool_calls["count"] == 0
    assert out.get("pending_crushe_guide") is True
    assert out.get("onboarding_completed") is False
    handoff = out.get("onboarding_handoff") or {}
    assert handoff.get("recommendation") == recommendation

    pending = out.get("pending_responses") or []
    assert pending and pending[0].get("phase") == "pre_submit"
    assert any(item.get("phase") == "post_submit" for item in pending)


def test_tool_path_no_extra_llm_fallback_for_preliminary_assessment(monkeypatch):
    class DummyLLM:
        def __init__(self):
            self.invoke_count = 0

        def invoke(self, *_args, **_kwargs):
            self.invoke_count += 1
            return None

    llm = DummyLLM()
    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: llm)

    def _fake_supervisor(**kwargs):
        return {
            "new_messages": [
                {
                    "role": "assistant",
                    "content": "先给你一张初判卡。",
                    "tool_calls": [
                        {
                            "name": "submit_onboarding",
                            "args": {
                                "response": "兜底",
                                "recommendation": "信息已收集完毕，进入主流程进一步分析。",
                                "suggested_action": "建议进行现状分析",
                                "reason": "已满足 MAS",
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "下一步我会做深度复盘。"},
            ],
            "patches": [_base_submit_patch()],
        }

    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _fake_supervisor)

    out = onboarding_module.onboarding_agent_node(create_initial_state("你好"))

    assert out.get("pending_crushe_guide") is True
    assert llm.invoke_count == 0


def test_guide_done_token_completes_and_handoffs(monkeypatch):
    class DummyLLM:
        def invoke(self, *_args, **_kwargs):
            raise AssertionError("guide_done branch should not call llm")

    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: DummyLLM())

    supervisor_calls = {"count": 0}

    def _fake_supervisor(**kwargs):
        supervisor_calls["count"] += 1
        return {
            "new_messages": [
                {
                    "role": "assistant",
                    "content": "截图看完了，我先给你一张局势初判卡。",
                    "tool_calls": [
                        {
                            "name": "submit_onboarding",
                            "args": {
                                "response": "兜底",
                                "recommendation": "信息已收集完毕，进入主流程进一步分析。",
                                "suggested_action": "建议进行现状分析",
                                "reason": "已满足 MAS",
                            },
                        }
                    ],
                },
                {"role": "assistant", "content": "真正的攻坚战才刚开始。"},
            ],
            "patches": [_base_submit_patch()],
        }

    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _fake_supervisor)

    out1 = onboarding_module.onboarding_agent_node(create_initial_state("我想追一个女生"))
    assert out1.get("pending_crushe_guide") is True
    assert supervisor_calls["count"] == 1

    resume_state = dict(out1)
    resume_state["user_message"] = onboarding_module.GUIDE_DONE_TOKEN
    resume_state["messages"] = list(out1.get("messages") or []) + [
        {"role": "user", "content": onboarding_module.GUIDE_DONE_TOKEN}
    ]

    out2 = onboarding_module.onboarding_agent_node(resume_state)

    assert supervisor_calls["count"] == 1
    assert out2.get("onboarding_completed") is True
    assert out2.get("pending_crushe_guide") is False
    assert out2.get("onboarding_handoff") == out1.get("onboarding_handoff")
