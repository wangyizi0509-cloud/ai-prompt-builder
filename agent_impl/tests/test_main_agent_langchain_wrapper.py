import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from agents.tooling.tool_result import ok
from graph.nodes import main_agent as main_agent_module
from tests.conftest import create_test_state


class DummyModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.seen_messages = []

    def bind(self, **kwargs):
        return self

    def bind_tools(self, tools, **kwargs):
        self.tools = list(tools or [])
        return self

    def invoke(self, messages):
        self.seen_messages.append(list(messages))
        return self._responses.pop(0)


def test_main_agent_merges_state_patches_from_tools(monkeypatch):
    def _patch_tool() -> dict:
        return ok(output="patched", state_patch={"layer2_memory": {"foo": "bar"}})

    patch_tool = StructuredTool.from_function(func=_patch_tool, name="patch_tool", description="test tool")

    dummy = DummyModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "patch_tool", "args": {}, "id": "tc1", "type": "tool_call"}],
            ),
            AIMessage(content="done"),
        ]
    )

    monkeypatch.setattr(main_agent_module, "get_llm", lambda *a, **k: dummy)
    monkeypatch.setattr(main_agent_module, "_build_all_tools", lambda state_getter: [patch_tool])

    state = create_test_state("hi")
    out = main_agent_module.main_agent_node(state)

    assert out["layer2_memory"]["foo"] == "bar"
    assert out["pending_responses"][-1]["content"] == "done"


def test_main_agent_calls_subagent_tools_and_merges(monkeypatch):
    dummy = DummyModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "call_status_agent",
                        "args": {"instruction": "x"},
                        "id": "tc_status",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="final"),
        ]
    )

    monkeypatch.setattr(main_agent_module, "get_llm", lambda *a, **k: dummy)
    monkeypatch.setattr(
        main_agent_module,
        "_call_subagent",
        lambda **kwargs: ok(output="subagent", state_patch={"layer2_memory": {"from_subagent": True}}),
    )

    state = create_test_state("hi")
    out = main_agent_module.main_agent_node(state)

    assert out["layer2_memory"]["from_subagent"] is True
    assert out["pending_responses"][-1]["content"] == "final"


def test_main_agent_truncates_messages_to_25_for_model(monkeypatch):
    dummy = DummyModel(responses=[AIMessage(content="ok")])
    monkeypatch.setattr(main_agent_module, "get_llm", lambda *a, **k: dummy)
    monkeypatch.setattr(main_agent_module, "_build_all_tools", lambda state_getter: [])

    state = create_test_state("hi")
    state["messages"] = [{"role": "user", "content": f"m{i}"} for i in range(60)]

    out = main_agent_module.main_agent_node(state)
    assert out["pending_responses"][-1]["content"] == "ok"
    assert len(dummy.seen_messages[0]) <= 25
