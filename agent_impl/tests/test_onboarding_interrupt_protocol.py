from __future__ import annotations

from unittest.mock import MagicMock

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from graph.state import create_initial_state
from graph.workflow import compile_workflow


def _make_mock_response(content: str):
    resp = MagicMock()
    resp.content = content
    return resp


def test_onboarding_uses_interrupt_and_resume(monkeypatch):
    from onboarding import onboarding_agent as onboarding_module

    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = [
        _make_mock_response(
            """```json
{
  "needs_more": true,
  "response": "还差一条关键信息，我先问你一个问题。",
  "inquiry_card": {
    "questions": [
      {
        "id": "onboard_q_0",
        "question": "你们目前认识多久？",
        "type": "free_input_question",
        "is_required": true
      }
    ],
    "intro": "补齐这一条我就能继续判断",
    "reasoning": "缺少关系时长"
  }
}
```"""
        ),
        _make_mock_response(
            """```json
{
  "needs_more": false,
  "response": "信息齐了，我先给你初判。",
  "recommendation": "信息已收集完毕，进入主流程进一步分析。",
  "suggested_action": "建议进行现状分析",
  "reason": "已满足 MAS"
}
```"""
        ),
    ]
    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: mock_llm)
    def _force_fallback(**kwargs):
        raise RuntimeError("force legacy fallback in test")
    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _force_fallback)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    config = {
        "configurable": {"thread_id": "test_onboarding_interrupt_protocol"},
        "checkpointer": checkpointer,
    }

    state = create_initial_state("我想追一个女生")
    out1 = app.invoke(state, config=config)

    assert "__interrupt__" in out1
    interrupts = out1.get("__interrupt__") or []
    first = interrupts[0]
    payload = first.get("value") if isinstance(first, dict) else getattr(first, "value", None)
    assert isinstance(payload, dict)
    assert payload.get("type") == "inquiry_card"
    assert isinstance(payload.get("questions"), list) and payload["questions"]
    assert payload["questions"][0].get("id") == "onboard_q_0"

    resume_payload = {"answers": {"onboard_q_0": "我们认识三个月了"}}
    out2 = app.invoke(Command(resume=resume_payload), config=config)

    assert "__interrupt__" not in out2
    assert out2.get("onboarding_completed") is False
    assert out2.get("pending_crushe_guide") is True
    assert out2.get("inquiry_answers") == resume_payload
    pending = out2.get("pending_responses") or []
    assert any(isinstance(item, dict) and item.get("content") for item in pending)

    raw_inputs = (((out2.get("collected_info") or {}).get("raw_inputs")) or [])
    assert any("我们认识三个月了" in str(item) for item in raw_inputs)


def test_onboarding_guide_done_token_keeps_route_contract(monkeypatch):
    from onboarding import onboarding_agent as onboarding_module

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = _make_mock_response(
        """```json
{
  "needs_more": false,
  "response": "信息齐了，我先给你初判。",
  "recommendation": "信息已收集完毕，进入主流程进一步分析。",
  "suggested_action": "建议进行现状分析",
  "reason": "已满足 MAS"
}
```"""
    )
    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: mock_llm)
    def _force_fallback(**kwargs):
        raise RuntimeError("force legacy fallback in test")
    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _force_fallback)

    state = create_initial_state("我是新用户")
    out1 = onboarding_module.onboarding_agent_node(state)
    assert out1.get("onboarding_completed") is False
    assert out1.get("pending_crushe_guide") is True

    resume_state = dict(out1)
    resume_state["user_message"] = onboarding_module.GUIDE_DONE_TOKEN
    resume_state["messages"] = list(out1.get("messages", [])) + [
        {"role": "user", "content": onboarding_module.GUIDE_DONE_TOKEN}
    ]

    out2 = onboarding_module.onboarding_agent_node(resume_state)
    assert out2.get("onboarding_completed") is True
    assert out2.get("pending_crushe_guide") is False


def test_onboarding_pending_guide_returns_soft_gate_pending_response():
    from onboarding import onboarding_agent as onboarding_module

    state = create_initial_state("我想继续问一个问题")
    state["pending_crushe_guide"] = True
    state["onboarding_completed"] = False
    state["collected_info"] = {
        "raw_inputs": ["我想继续问一个问题"],
        "user_profile": {},
        "crush_profile": {},
        "pain_points": [],
    }

    out = onboarding_module.onboarding_agent_node(state)
    assert out.get("pending_crushe_guide") is True
    assert out.get("onboarding_completed") is False
    pending = out.get("pending_responses") or []
    assert pending and isinstance(pending[0], dict)
    assert pending[0].get("phase") == "guide_gate"
    assert pending[0].get("content")


def test_onboarding_tool_interrupt_keeps_merged_patch(monkeypatch):
    from onboarding import onboarding_agent as onboarding_module

    class DummyLLM:
        pass

    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: DummyLLM())

    interrupt_payload = {
        "type": "inquiry_card",
        "intro": "请补充信息",
        "questions": [{"id": "q_next", "question": "补充一下最近联系频率"}],
    }

    def _fake_supervisor(**kwargs):
        return {
            "final": _make_mock_response(""),
            "new_messages": [],
            "patches": [
                {
                    "inquiry_answers": {"answers": {"q_prev": "最近联系比较少"}},
                    "collected_info": {
                        "raw_inputs": ["最近联系比较少"],
                        "user_profile": {},
                        "crush_profile": {},
                        "pain_points": [],
                    },
                }
            ],
            "__interrupt__": [{"value": interrupt_payload}],
        }

    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _fake_supervisor)

    state = create_initial_state("我想追一个女生")
    out = onboarding_module.onboarding_agent_node(state)

    assert isinstance(out.get("inquiry_card"), dict)
    assert out["inquiry_card"].get("questions")
    assert out.get("inquiry_answers") == {"answers": {"q_prev": "最近联系比较少"}}
    assert out.get("onboarding_turn_count") == 1
    assert isinstance(out.get("onboarding_last_answer_fingerprint"), str)
    assert out.get("onboarding_last_answer_fingerprint")


def test_onboarding_resume_twice_progresses_turn_count_and_raw_inputs(monkeypatch):
    from onboarding import onboarding_agent as onboarding_module

    class DummyLLM:
        pass

    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: DummyLLM())
    monkeypatch.setattr(onboarding_module, "_build_preliminary_assessment_fallback", lambda **kwargs: None)

    call_count = {"n": 0}

    def _fake_supervisor(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {
                "final": _make_mock_response(""),
                "new_messages": [],
                "patches": [],
                "__interrupt__": [
                    {
                        "value": {
                            "type": "inquiry_card",
                            "intro": "继续补充",
                            "questions": [{"id": "q1", "question": "第一个问题"}],
                        }
                    }
                ],
            }
        if call_count["n"] == 2:
            return {
                "final": _make_mock_response(""),
                "new_messages": [],
                "patches": [],
                "__interrupt__": [
                    {
                        "value": {
                            "type": "inquiry_card",
                            "intro": "继续补充",
                            "questions": [{"id": "q2", "question": "第二个问题"}],
                        }
                    }
                ],
            }
        return {
            "final": _make_mock_response("ok"),
            "new_messages": [],
            "patches": [
                {
                    "pending_crushe_guide": True,
                    "onboarding_handoff": {
                        "collected_context": {
                            "raw_inputs": ["第一次补充", "第二次补充"],
                            "user_profile": {},
                            "crush_profile": {},
                            "pain_points": [],
                        },
                        "recommendation": "信息已收集完毕，进入主流程进一步分析。",
                        "suggested_action": "建议进行现状分析",
                        "reason": "Onboarding 收集完成。",
                    },
                    "collected_info": {
                        "raw_inputs": ["第一次补充", "第二次补充"],
                        "user_profile": {},
                        "crush_profile": {},
                        "pain_points": [],
                    },
                    "pending_responses": [{"from": "onboarding", "content": "已完成", "phase": "immediate"}],
                }
            ],
        }

    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _fake_supervisor)

    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.types import Command
    from onboarding.workflow import compile_onboarding_workflow

    checkpointer = MemorySaver()
    app = compile_onboarding_workflow(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "test_onboarding_resume_twice"}, "checkpointer": checkpointer}

    state = create_initial_state("我想追一个女生")
    out1 = app.invoke(state, config=config)
    assert "__interrupt__" in out1

    out2 = app.invoke(Command(resume={"answers": {"q1": "第一次补充"}}), config=config)
    assert "__interrupt__" in out2

    out3 = app.invoke(Command(resume={"answers": {"q2": "第二次补充"}}), config=config)
    assert "__interrupt__" not in out3
    assert out3.get("pending_crushe_guide") is True
    assert out3.get("onboarding_turn_count") == 2
    raw_inputs3 = (((out3.get("collected_info") or {}).get("raw_inputs")) or [])
    assert any("第一次补充" in str(item) for item in raw_inputs3)
    assert any("第二次补充" in str(item) for item in raw_inputs3)


def test_onboarding_direct_submit_emits_two_phase_pending_and_waits_guide(monkeypatch):
    from onboarding import onboarding_agent as onboarding_module

    class DummyLLM:
        def invoke(self, *_args, **_kwargs):
            raise AssertionError("direct submit path should not call llm fallback")

    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: DummyLLM())

    call_count = {"n": 0}
    pre_submit = "截图看完了，先给你一张局势初判卡。"
    post_submit = "我的初步判断先到这里，下一步我会做深度复盘。"

    def _fake_supervisor(**kwargs):
        call_count["n"] += 1
        return {
            "new_messages": [
                {
                    "role": "assistant",
                    "content": pre_submit,
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
                {"role": "assistant", "content": post_submit},
            ],
            "patches": [
                {
                    "pending_crushe_guide": True,
                    "onboarding_completed": False,
                    "onboarding_handoff": {
                        "collected_context": {
                            "raw_inputs": [],
                            "user_profile": {},
                            "crush_profile": {},
                            "pain_points": [],
                        },
                        "recommendation": "信息已收集完毕，进入主流程进一步分析。",
                        "suggested_action": "建议进行现状分析",
                        "reason": "Onboarding 收集完成。",
                    },
                    "collected_info": {
                        "raw_inputs": [],
                        "user_profile": {},
                        "crush_profile": {},
                        "pain_points": [],
                    },
                }
            ],
        }

    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _fake_supervisor)

    out = onboarding_module.onboarding_agent_node(create_initial_state("我是新用户"))

    assert call_count["n"] == 1
    assert out.get("onboarding_completed") is False
    assert out.get("pending_crushe_guide") is True
    pending = out.get("pending_responses") or []
    assert [item.get("phase") for item in pending] == ["pre_submit", "post_submit"]
    assert pending[0].get("content") == pre_submit
    assert pending[1].get("content") == post_submit
