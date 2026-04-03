import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.errors import NodeInterrupt

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
    monkeypatch.setattr(main_agent_module, "_build_all_tools", lambda state_getter, runtime_config=None: [patch_tool])

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
    def _status_tool(instruction: str) -> dict:
        return ok(output="subagent", state_patch={"layer2_memory": {"from_subagent": True}})

    status_tool = StructuredTool.from_function(
        func=_status_tool,
        name="call_status_agent",
        description="test status tool",
    )
    monkeypatch.setattr(main_agent_module, "_build_all_tools", lambda state_getter, runtime_config=None: [status_tool])

    state = create_test_state("hi")
    out = main_agent_module.main_agent_node(state)

    assert out["layer2_memory"]["from_subagent"] is True
    assert out["pending_responses"][-1]["content"] == "final"


def test_main_agent_truncates_messages_to_25_for_model(monkeypatch):
    dummy = DummyModel(responses=[AIMessage(content="ok")])
    monkeypatch.setattr(main_agent_module, "get_llm", lambda *a, **k: dummy)
    monkeypatch.setattr(main_agent_module, "_build_all_tools", lambda state_getter, runtime_config=None: [])

    state = create_test_state("hi")
    state["messages"] = [{"role": "user", "content": f"m{i}"} for i in range(60)]

    out = main_agent_module.main_agent_node(state)
    assert out["pending_responses"][-1]["content"] == "ok"
    assert len(dummy.seen_messages[0]) <= 25


def test_main_agent_injects_status_brief_before_final(monkeypatch):
    def _status_patch_tool() -> dict:
        return ok(
            output="status updated",
            state_patch={
                "layer2_memory": {
                    "current_status_report": {
                        "report_content": "## 关系阶段\nL2 暧昧期\n\n- 核心矛盾：沟通频率不稳定\n- 风险点：对方边界感较强",
                    }
                }
            },
        )

    status_tool = StructuredTool.from_function(
        func=_status_patch_tool,
        name="call_status_agent",
        description="test status patch tool",
    )
    dummy = DummyModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "call_status_agent", "args": {}, "id": "tc_status", "type": "tool_call"}],
            ),
            AIMessage(content="final reply"),
        ]
    )

    monkeypatch.setattr(main_agent_module, "get_llm", lambda *a, **k: dummy)
    monkeypatch.setattr(main_agent_module, "_build_all_tools", lambda state_getter, runtime_config=None: [status_tool])

    state = create_test_state("hi")
    out = main_agent_module.main_agent_node(state)

    pending = out.get("pending_responses") or []
    assert len(pending) >= 2
    assert pending[0]["from"] == "status_agent"
    assert pending[0]["phase"] == "status_brief"
    assert "现状分析摘要" in pending[0]["content"]
    assert pending[-1]["from"] == "main_agent"
    assert pending[-1]["phase"] == "final"
    assert pending[-1]["content"] == "final reply"


def test_main_agent_skips_status_brief_when_status_unchanged(monkeypatch):
    unchanged_report = "## 关系阶段\nL2 暧昧期"

    def _status_patch_tool() -> dict:
        return ok(
            output="status unchanged",
            state_patch={
                "layer2_memory": {
                    "current_status_report": {
                        "report_content": unchanged_report,
                    }
                }
            },
        )

    status_tool = StructuredTool.from_function(
        func=_status_patch_tool,
        name="call_status_agent",
        description="test status unchanged tool",
    )
    dummy = DummyModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "call_status_agent", "args": {}, "id": "tc_status", "type": "tool_call"}],
            ),
            AIMessage(content="final only"),
        ]
    )

    monkeypatch.setattr(main_agent_module, "get_llm", lambda *a, **k: dummy)
    monkeypatch.setattr(main_agent_module, "_build_all_tools", lambda state_getter, runtime_config=None: [status_tool])

    state = create_test_state("hi")
    state["layer2_memory"] = {
        "current_status_report": {"report_content": unchanged_report},
    }
    out = main_agent_module.main_agent_node(state)

    pending = out.get("pending_responses") or []
    assert len(pending) == 1
    assert pending[0]["from"] == "main_agent"
    assert pending[0]["phase"] == "final"
    assert pending[0]["content"] == "final only"


def test_main_agent_tool_failure_returns_tool_message_and_avoids_cascade(monkeypatch):
    def _broken_status_tool(instruction: str) -> dict:
        raise RuntimeError("checkpoint read failed")

    status_tool = StructuredTool.from_function(
        func=_broken_status_tool,
        name="call_status_agent",
        description="broken status tool",
    )
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
            AIMessage(content="fallback final"),
        ]
    )

    monkeypatch.setattr(main_agent_module, "get_llm", lambda *a, **k: dummy)
    monkeypatch.setattr(main_agent_module, "_build_all_tools", lambda state_getter, runtime_config=None: [status_tool])

    out = main_agent_module.main_agent_node(create_test_state("hi"))
    assert out["pending_responses"][-1]["content"] == "fallback final"

    second_round_messages = dummy.seen_messages[1]
    tool_msgs = [m for m in second_round_messages if isinstance(m, ToolMessage)]
    assert tool_msgs
    assert any(str(getattr(m, "tool_call_id", "")) == "tc_status" for m in tool_msgs)
    assert any("调用失败" in str(getattr(m, "content", "")) for m in tool_msgs)


def test_main_agent_tool_wrapper_reraises_graph_interrupt():
    def _interrupting_tool() -> dict:
        raise NodeInterrupt({"questions": [{"id": "q1"}], "type": "inquiry_card"})

    interrupt_tool = StructuredTool.from_function(
        func=_interrupting_tool,
        name="ask_human",
        description="interrupting tool",
    )

    wrapped = main_agent_module._wrap_tools_for_patch_collection([interrupt_tool], patches=[])

    with pytest.raises(NodeInterrupt):
        wrapped[0].invoke({})


def test_status_tool_retries_with_fallback_namespace_on_checkpoint_iter_error(monkeypatch):
    class _FakeSubgraph:
        def __init__(self):
            self.thread_ids = []

        def invoke(self, payload, config=None):
            tid = ((config or {}).get("configurable") or {}).get("thread_id", "")
            self.thread_ids.append(tid)
            if tid.endswith(":status_subgraph"):
                raise RuntimeError("error iterating checkpoint results")
            return {"state_patch": {}, "final": {"text": "status ok"}}

    fake_subgraph = _FakeSubgraph()
    monkeypatch.setattr(main_agent_module, "get_status_subgraph", lambda checkpointer=None: fake_subgraph)
    monkeypatch.setattr(main_agent_module, "build_all_tools_for_agent", lambda role, state_getter=None: [])

    tools = main_agent_module._build_all_tools(
        lambda: {},
        runtime_config={"configurable": {"thread_id": "thread-1"}, "checkpointer": object()},
    )
    status_tool = next(t for t in tools if getattr(t, "name", "") == "call_status_agent")
    result = status_tool.invoke({"instruction": "x"})

    assert result["ok"] is True
    assert "status ok" in result["output"]
    assert fake_subgraph.thread_ids[0].endswith(":status_subgraph")
    assert fake_subgraph.thread_ids[1].endswith(":status_subgraph_retry")
