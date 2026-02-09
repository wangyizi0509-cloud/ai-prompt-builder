from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from graph.nodes.main_agent import _CURRENT_RUN_CONFIG, _build_all_tools


def _pick_tool(tools, name: str):
    for t in tools:
        if getattr(t, "name", None) == name:
            return t
    raise AssertionError(f"tool not found: {name}")


def test_call_status_agent_tool_interrupt_then_resume():
    checkpointer = MemorySaver()
    thread_cfg = {"configurable": {"thread_id": "test_call_status_agent_tool_interrupt"}, "checkpointer": checkpointer}

    state: dict = {
        "messages": [],
        "layer2_memory": {},
        "layer3_memory": {},
        "pending_responses": [],
        "runtime": {},
        "tool_patch_log": [],
    }
    tools = _build_all_tools(lambda: state)
    status_tool = _pick_tool(tools, "call_status_agent")

    def node(s: dict, config: dict | None = None) -> dict:
        cfg = dict(config or {})
        cfg["checkpointer"] = checkpointer
        token = _CURRENT_RUN_CONFIG.set(cfg)
        try:
            result = status_tool.invoke({"instruction": "[[TEST_INTERRUPT]] 请先问我一个问题再继续。"})
            return {"tool_result": result}
        finally:
            _CURRENT_RUN_CONFIG.reset(token)

    graph = StateGraph(dict)
    graph.add_node("n", node)
    graph.set_entry_point("n")
    graph.add_edge("n", END)
    app = graph.compile(checkpointer=checkpointer)

    out1 = app.invoke({}, config=thread_cfg)
    assert "__interrupt__" in out1
    interrupts = out1["__interrupt__"]
    assert interrupts and interrupts[0].value["questions"][0]["id"] == "q1"

    resume_payload = {"answers": {"q1": "A"}}
    out2 = app.invoke(Command(resume=resume_payload), config=thread_cfg)
    tool_result = out2["tool_result"]
    assert tool_result["ok"] is True
    assert tool_result["state_patch"]["inquiry_answers"] == resume_payload


def test_call_plan_agent_tool_interrupt_then_resume():
    checkpointer = MemorySaver()
    thread_cfg = {"configurable": {"thread_id": "test_call_plan_agent_tool_interrupt"}, "checkpointer": checkpointer}

    state: dict = {
        "messages": [],
        "layer2_memory": {},
        "layer3_memory": {},
        "pending_responses": [],
        "runtime": {},
        "tool_patch_log": [],
    }
    tools = _build_all_tools(lambda: state)
    plan_tool = _pick_tool(tools, "call_plan_agent")

    def node(s: dict, config: dict | None = None) -> dict:
        cfg = dict(config or {})
        cfg["checkpointer"] = checkpointer
        token = _CURRENT_RUN_CONFIG.set(cfg)
        try:
            result = plan_tool.invoke({"instruction": "[[TEST_INTERRUPT]] 请先问我一个问题再继续。"})
            return {"tool_result": result}
        finally:
            _CURRENT_RUN_CONFIG.reset(token)

    graph = StateGraph(dict)
    graph.add_node("n", node)
    graph.set_entry_point("n")
    graph.add_edge("n", END)
    app = graph.compile(checkpointer=checkpointer)

    out1 = app.invoke({}, config=thread_cfg)
    assert "__interrupt__" in out1

    resume_payload = {"answers": {"q1": "A"}}
    out2 = app.invoke(Command(resume=resume_payload), config=thread_cfg)
    tool_result = out2["tool_result"]
    assert tool_result["ok"] is True
    assert tool_result["state_patch"]["inquiry_answers"] == resume_payload


def test_call_guide_agent_tool_interrupt_then_resume():
    checkpointer = MemorySaver()
    thread_cfg = {"configurable": {"thread_id": "test_call_guide_agent_tool_interrupt"}, "checkpointer": checkpointer}

    state: dict = {
        "messages": [],
        "layer2_memory": {},
        "layer3_memory": {},
        "pending_responses": [],
        "runtime": {},
        "tool_patch_log": [],
    }
    tools = _build_all_tools(lambda: state)
    guide_tool = _pick_tool(tools, "call_guide_agent")

    def node(s: dict, config: dict | None = None) -> dict:
        cfg = dict(config or {})
        cfg["checkpointer"] = checkpointer
        token = _CURRENT_RUN_CONFIG.set(cfg)
        try:
            result = guide_tool.invoke({"instruction": "[[TEST_INTERRUPT]] 请先问我一个问题再继续。"})
            return {"tool_result": result}
        finally:
            _CURRENT_RUN_CONFIG.reset(token)

    graph = StateGraph(dict)
    graph.add_node("n", node)
    graph.set_entry_point("n")
    graph.add_edge("n", END)
    app = graph.compile(checkpointer=checkpointer)

    out1 = app.invoke({}, config=thread_cfg)
    assert "__interrupt__" in out1

    resume_payload = {"answers": {"q1": "A"}}
    out2 = app.invoke(Command(resume=resume_payload), config=thread_cfg)
    tool_result = out2["tool_result"]
    assert tool_result["ok"] is True
    assert tool_result["state_patch"]["inquiry_answers"] == resume_payload

