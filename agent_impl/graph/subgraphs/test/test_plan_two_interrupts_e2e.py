from __future__ import annotations

import os

os.environ["LLM_PROVIDER"] = "mock"

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from graph.state import create_initial_state
from graph.nodes.main_agent import _build_all_tools
from graph.subgraphs.plan import get_plan_subgraph


def test_plan_subgraph_two_interrupts_are_propagated():
    checkpointer = MemorySaver()
    app = get_plan_subgraph(checkpointer=checkpointer)

    cfg = {"configurable": {"thread_id": "test_plan_two_interrupts"}}
    sub_in = {
        "task_spec": {
            "instruction": "[[TEST_INTERRUPT_TWICE]]",
            "parent_state": {
                "messages": [],
                "layer2_memory": {},
                "layer3_memory": {},
                "pending_responses": [],
                "runtime": {},
                "tool_patch_log": [],
            },
        },
        "private_messages": [],
        "tool_patches": [],
    }

    out1 = app.invoke(sub_in, config=cfg)
    assert "__interrupt__" in out1
    payload1 = (out1.get("__interrupt__") or [None])[0].value
    qids1 = [q.get("id") for q in (payload1.get("questions") or []) if isinstance(q, dict)]
    assert qids1 == ["q1"]

    out2 = app.invoke(Command(resume={"q1": "A"}), config=cfg)
    assert "__interrupt__" in out2
    payload2 = (out2.get("__interrupt__") or [None])[0].value
    qids2 = [q.get("id") for q in (payload2.get("questions") or []) if isinstance(q, dict)]
    assert qids2 == ["q2"]

    out3 = app.invoke(Command(resume={"q2": "C"}), config=cfg)
    assert "__interrupt__" not in out3


def test_call_plan_agent_tool_two_interrupts_are_propagated():
    checkpointer = MemorySaver()
    thread_cfg = {"configurable": {"thread_id": "test_call_plan_two_interrupts"}, "checkpointer": checkpointer}

    state: dict = create_initial_state(
        "x",
        onboarding_completed=True,
        onboarding_handoff=None,
        onboarding_turn_count=999,
    )

    def _pick_tool(tools, name: str):
        for t in tools:
            if getattr(t, "name", None) == name:
                return t
        raise AssertionError(f"tool not found: {name}")

    tools = _build_all_tools(lambda: state)
    plan_tool = _pick_tool(tools, "call_plan_agent")

    def node(s: dict, config=None) -> dict:
        result = plan_tool.invoke({"instruction": "[[TEST_INTERRUPT_TWICE]]"}, config=dict(config or {}))
        return {"tool_result": result}

    graph = StateGraph(dict)
    graph.add_node("n", node)
    graph.set_entry_point("n")
    graph.add_edge("n", END)
    app = graph.compile(checkpointer=checkpointer)

    out1 = app.invoke({}, config=thread_cfg)
    assert "__interrupt__" in out1

    out2 = app.invoke(Command(resume={"q1": "A"}), config=thread_cfg)
    assert "__interrupt__" in out2

    out3 = app.invoke(Command(resume={"q2": "C"}), config=thread_cfg)
    assert "__interrupt__" not in out3


if __name__ == "__main__":
    test_plan_subgraph_two_interrupts_are_propagated()
    test_call_plan_agent_tool_two_interrupts_are_propagated()
    print("ok")
