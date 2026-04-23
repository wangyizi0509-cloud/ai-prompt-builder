from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.errors import GraphInterrupt, Interrupt

from graph.state import create_initial_state
from onboarding import onboarding_agent as onboarding_module


def test_onboarding_main_path_builds_message_stack(monkeypatch):
    captured: dict[str, object] = {}

    class DummyLLM:
        pass

    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: DummyLLM())

    def _fake_supervisor(*, llm, tools, initial_messages, config=None, max_rounds=6):
        captured["initial_messages"] = list(initial_messages)
        return {
            "final": AIMessage(content="ok"),
            "new_messages": [],
            "patches": [
                {
                    "pending_crushe_guide": True,
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
                    "pending_responses": [
                        {
                            "from": "onboarding",
                            "content": "我先给你做初判。",
                            "phase": "immediate",
                        }
                    ],
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

    state = create_initial_state("你好")
    state["messages"] = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，我是小话。"},
        {"role": "user", "content": "我想追一个女生"},
    ]
    state["user_message"] = "她最近回复很慢"

    out = onboarding_module.onboarding_agent_node(state)
    assert out.get("pending_crushe_guide") is True

    messages = captured.get("initial_messages")
    assert isinstance(messages, list) and messages

    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert "<dossier agent=\"onboarding_agent\">" in messages[1].content
    assert isinstance(messages[2], AIMessage)
    assert messages[2].content == "[SYS:DOSSIER_LOADED]"

    assert isinstance(messages[-2], HumanMessage)
    assert "<onboarding_runtime>" in messages[-2].content
    assert "<turn_count>" in messages[-2].content
    assert "<max_turns>" in messages[-2].content
    assert isinstance(messages[-1], HumanMessage)
    assert messages[-1].content == "她最近回复很慢"

    # 历史应该以独立 message 注入，而非单条模板化大 prompt。
    assert any(isinstance(m, HumanMessage) and m.content == "我想追一个女生" for m in messages[3:-2])
    assert not (len(messages) == 1 and isinstance(messages[0], HumanMessage))


def test_onboarding_supervisor_returns_incremental_new_messages(monkeypatch):
    class FakeGraph:
        def invoke(self, payload, config=None):
            initial = list(payload.get("messages") or [])
            return {"messages": initial + [AIMessage(content="done")]}

    monkeypatch.setattr(onboarding_module, "create_agent", lambda **kwargs: FakeGraph())

    out = onboarding_module._run_onboarding_supervisor(
        llm=object(),
        tools=[],
        initial_messages=[HumanMessage(content="a"), HumanMessage(content="b")],
        config={},
        max_rounds=1,
    )

    assert len(out["new_messages"]) == 1
    assert isinstance(out["new_messages"][0], AIMessage)
    assert out["new_messages"][0].content == "done"


def test_onboarding_supervisor_maps_graph_interrupt(monkeypatch):
    class FakeGraph:
        def invoke(self, payload, config=None):
            raise GraphInterrupt(
                (
                    Interrupt(
                        value={
                            "type": "inquiry_card",
                            "intro": "补充一下信息",
                            "questions": [{"id": "q1", "question": "你们认识多久了？"}],
                        },
                        id="it_1",
                    ),
                )
            )

    monkeypatch.setattr(onboarding_module, "create_agent", lambda **kwargs: FakeGraph())

    out = onboarding_module._run_onboarding_supervisor(
        llm=object(),
        tools=[],
        initial_messages=[HumanMessage(content="a")],
        config={},
        max_rounds=1,
    )

    assert "__interrupt__" in out
    interrupts = out["__interrupt__"]
    assert isinstance(interrupts, list) and interrupts
    assert getattr(interrupts[0], "value", {}).get("type") == "inquiry_card"


@pytest.mark.xfail(
    reason="superseded by onboarding_v2 (独立 REST 流程)；create_initial_state "
    "默认 onboarding_completed=True 后，onboarding_agent_node 会直接跳过 supervisor。",
    strict=False,
)
def test_onboarding_node_emits_runtime_interrupt_from_supervisor(monkeypatch):
    class DummyLLM:
        pass

    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: DummyLLM())

    payload = {
        "type": "inquiry_card",
        "intro": "补充一下信息",
        "questions": [{"id": "q1", "question": "你们认识多久了？"}],
    }

    def _fake_supervisor(**kwargs):
        return {
            "__interrupt__": [Interrupt(value=payload, id="it_1")],
            "patches": [{"inquiry_answers": {"answers": {"q0": "A"}}}],
        }

    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _fake_supervisor)

    def _fake_interrupt(value):
        raise AssertionError("onboarding node should return __interrupt__ instead of calling interrupt() directly")

    monkeypatch.setattr(onboarding_module, "interrupt", _fake_interrupt, raising=False)

    state = create_initial_state("你好")
    out = onboarding_module.onboarding_agent_node(state)

    assert "__interrupt__" in out
    assert out["__interrupt__"][0].value == payload
    assert out.get("inquiry_answers") == {"answers": {"q0": "A"}}
