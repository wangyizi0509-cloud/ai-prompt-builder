"""
LangGraph 工作流编排

当前主图节点收敛为：
- router
- onboarding（子图）
- main_agent
- post_turn_finalize

核心约束：
- 不再存在 skill_tools 节点与旧两阶段 ask/consult/emotion 状态机
- 工具执行由 main_agent 内部 tool-loop 完成（工具返回 state_patch 并合并写回）
- 人机交互通过 interrupt/resume（ask_human + Command(resume=...)）实现
"""

from __future__ import annotations

from typing import Literal, Optional

from langgraph.graph import END, StateGraph

from graph.nodes.finalizer import post_turn_finalize_node
from graph.nodes.main_agent import main_agent_node
from graph.nodes.router import router_node
from graph.state import AgentState, ensure_message_id
from onboarding.workflow import compile_onboarding_workflow


MAX_NODE_STEPS_PER_TURN = 18


def _wrap_step_counter(node_name: str, fn):
    def _wrapped(state: AgentState, config: dict | None = None) -> dict:
        try:
            out = fn(state, config) or {}
        except TypeError:
            out = fn(state) or {}
        if not isinstance(out, dict):
            out = {}

        msgs = out.get("messages")
        if isinstance(msgs, list) and msgs:
            out["messages"] = [ensure_message_id(m)[1] for m in msgs]

        curr = int(out.get("_iteration_count", state.get("_iteration_count", 0)) or 0) + 1
        out["_iteration_count"] = curr

        dbg = out.get("debug_log")
        if isinstance(dbg, list):
            dbg.append({"node": "workflow", "step": "StepCounter", "at": node_name, "iteration": curr})
        return out

    return _wrapped


def route_after_router(state: AgentState) -> Literal["onboarding", "main_agent", "end"]:
    iteration = int(state.get("_iteration_count", 0) or 0)
    if iteration >= MAX_NODE_STEPS_PER_TURN:
        return "end"

    route_to = state.get("route_to", "main_agent")
    if route_to == "end":
        return "end"
    if route_to == "onboarding":
        return "onboarding"
    return "main_agent"


def route_after_onboarding(state: AgentState) -> Literal["router", "end"]:
    if state.get("onboarding_completed", False):
        return "router"
    return "end"


def route_after_main_agent(state: AgentState) -> Literal["end"]:
    iteration = int(state.get("_iteration_count", 0) or 0)
    if iteration >= MAX_NODE_STEPS_PER_TURN:
        return "end"
    return "end"


def create_workflow():
    workflow = StateGraph(AgentState)

    workflow.add_node("router", _wrap_step_counter("router", router_node))
    workflow.add_node("onboarding", compile_onboarding_workflow())
    workflow.add_node("main_agent", _wrap_step_counter("main_agent", main_agent_node))
    workflow.add_node("post_turn_finalize", _wrap_step_counter("post_turn_finalize", post_turn_finalize_node))

    workflow.set_entry_point("router")

    workflow.add_conditional_edges(
        "onboarding",
        route_after_onboarding,
        {"router": "router", "end": "post_turn_finalize"},
    )

    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {"onboarding": "onboarding", "main_agent": "main_agent", "end": "post_turn_finalize"},
    )

    workflow.add_conditional_edges("main_agent", route_after_main_agent, {"end": "post_turn_finalize"})
    workflow.add_edge("post_turn_finalize", END)
    return workflow


def compile_workflow(*, checkpointer: Optional[object] = None):
    workflow = create_workflow()
    if checkpointer is not None:
        return workflow.compile(checkpointer=checkpointer)
    return workflow.compile()


_compiled_workflow = None


def get_workflow():
    global _compiled_workflow
    if _compiled_workflow is None:
        _compiled_workflow = compile_workflow()
    return _compiled_workflow


def reset_workflow():
    global _compiled_workflow
    _compiled_workflow = None
