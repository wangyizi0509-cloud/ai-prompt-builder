from __future__ import annotations

import json
from typing import Any, Optional

from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from agents.tooling.patch import merge_patches
from agents.tools.all_tools import build_all_tools_for_agent
from config import get_llm
from graph.message_builder import build_messages_for_model
from graph.state import convert_message_to_dict, ensure_message_id


def _truncate_messages(messages: list[Any], *, max_total: int = 25) -> list[Any]:
    if max_total <= 0:
        return list(messages)
    if len(messages) <= max_total:
        return list(messages)
    head = list(messages[:3])
    tail_budget = max_total - len(head)
    if tail_budget <= 0:
        return list(messages[-max_total:])
    return head + list(messages[-tail_budget:])


def _tool_output_to_content(result: Any) -> str:
    if isinstance(result, dict) and "output" in result:
        return str(result.get("output") or "")
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except Exception:
        return str(result)


def _extract_state_patch(result: Any) -> dict:
    if isinstance(result, dict) and isinstance(result.get("state_patch"), dict):
        return dict(result.get("state_patch") or {})
    return {}


def _wrap_tools_for_patch_collection(tools: list[BaseTool], patches: list[dict]) -> list[BaseTool]:
    wrapped: list[BaseTool] = []
    for tool in tools:
        if not isinstance(tool, BaseTool):
            wrapped.append(tool)
            continue

        def _make_wrapped(inner: BaseTool):
            def _wrapped(**kwargs):
                result = inner.invoke(kwargs)
                patch = _extract_state_patch(result)
                if patch:
                    patches.append(patch)
                return _tool_output_to_content(result)

            return _wrapped

        wrapped.append(
            StructuredTool.from_function(
                func=_make_wrapped(tool),
                name=getattr(tool, "name", None) or tool.__class__.__name__,
                description=getattr(tool, "description", None) or "",
                return_direct=bool(getattr(tool, "return_direct", False)),
                args_schema=getattr(tool, "args_schema", None),
            )
        )
    return wrapped


def _run_langchain_supervisor(
    *,
    llm: Any,
    tools: list[BaseTool],
    initial_messages: list[Any],
    max_rounds: int,
    config: dict | None = None,
) -> dict[str, Any]:
    patches: list[dict] = []
    wrapped_tools = _wrap_tools_for_patch_collection(list(tools or []), patches)

    agent_graph = create_agent(model=llm, tools=wrapped_tools, system_prompt=None, name="plan_tool_loop_agent")

    rounds = max(1, int(max_rounds or 1))
    recursion_limit = max(25, rounds * 4 + 10)
    cfg = dict(config or {})
    cfg["recursion_limit"] = recursion_limit

    result = agent_graph.invoke(
        {"messages": list(initial_messages)},
        config=cfg,
    )

    messages_out = list(result.get("messages") or [])
    final = messages_out[-1] if messages_out else AIMessage(content="")
    new_messages = messages_out[len(initial_messages) :] if len(messages_out) >= len(initial_messages) else messages_out

    return {"final": final, "new_messages": new_messages, "patches": patches}


class PlanSubState(TypedDict, total=False):
    task_spec: dict
    private_messages: list[dict]
    pending_tool_calls: list[dict]
    tool_patches: list[dict]
    final: dict
    state_patch: dict


_compiled_cache: dict[int, Any] = {}
_shared_llm = get_llm(temperature=0.7, use_tools=True)


def _normalize_role(msg_dict: dict) -> dict:
    role = msg_dict.get("role")
    if role == "human":
        msg_dict["role"] = "user"
    elif role == "ai":
        msg_dict["role"] = "assistant"
    return msg_dict



def _normalize_private_messages(messages: list[Any]) -> list[dict]:
    out: list[dict] = []
    for m in messages or []:
        try:
            msg_dict = convert_message_to_dict(m)
        except Exception:
            if isinstance(m, dict):
                msg_dict = dict(m)
            else:
                continue
        msg_dict = _normalize_role(msg_dict)
        _, msg_dict = ensure_message_id(msg_dict)
        out.append(msg_dict)
    return out


def _dict_messages_to_lc(messages: list[dict]) -> list[Any]:
    out: list[Any] = []
    for m in messages or []:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            out.append(SystemMessage(content=content))
        elif role == "user":
            out.append(HumanMessage(content=content))
        elif role == "tool":
            out.append(ToolMessage(content=str(content or ""), tool_call_id=str(m.get("tool_call_id") or "")))
        else:
            tool_calls = m.get("tool_calls")
            reasoning_content = m.get("reasoning_content") or (m.get("additional_kwargs") or {}).get("reasoning_content")
            if isinstance(tool_calls, list):
                msg = AIMessage(content=str(content or ""), tool_calls=tool_calls)
            else:
                msg = AIMessage(content=str(content or ""))
            if reasoning_content:
                msg.additional_kwargs = {"reasoning_content": reasoning_content}
            out.append(msg)
    return out


def _build_plan_tools(task_spec: dict) -> list[BaseTool]:
    parent_state = task_spec.get("parent_state") if isinstance(task_spec.get("parent_state"), dict) else {}

    def state_getter() -> dict:
        return parent_state

    return build_all_tools_for_agent("plan", state_getter=state_getter)


def _tool_output_to_content(result: Any) -> str:
    if isinstance(result, dict) and "output" in result:
        return str(result.get("output") or "")
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except Exception:
        return str(result)


def _extract_state_patch(result: Any) -> dict:
    if isinstance(result, dict) and isinstance(result.get("state_patch"), dict):
        return dict(result.get("state_patch") or {})
    return {}


def llm_step_node(state: PlanSubState, config: RunnableConfig | None = None) -> dict[str, Any]:
    task_spec = state.get("task_spec") if isinstance(state.get("task_spec"), dict) else {}
    instruction = str(task_spec.get("instruction") or "")
    private_messages = state.get("private_messages") if isinstance(state.get("private_messages"), list) else []

    if not private_messages:
        parent_state = task_spec.get("parent_state") if isinstance(task_spec.get("parent_state"), dict) else {}
        initial_messages = build_messages_for_model(
            state=parent_state,
            agent_name="plan_agent",
            current_input=instruction,
        )
        initial_messages = _truncate_messages(initial_messages, max_total=25)
        private_messages = _normalize_private_messages(initial_messages)

    tools = _build_plan_tools(task_spec)
    llm = _shared_llm.bind_tools(tools)
    messages_in = _dict_messages_to_lc(private_messages)
    ai = llm.invoke(messages_in)

    ai_dict = convert_message_to_dict(ai)
    ai_dict = _normalize_role(ai_dict)
    _, ai_dict = ensure_message_id(ai_dict)

    pending_tool_calls = list(getattr(ai, "tool_calls", None) or [])

    updates: dict[str, Any] = {
        "private_messages": list(private_messages) + [ai_dict],
        "pending_tool_calls": pending_tool_calls,
    }
    if not pending_tool_calls:
        updates["final"] = {"text": str(getattr(ai, "content", "") or "").strip()}
    return updates


def tool_step_node(state: PlanSubState, config: RunnableConfig | None = None) -> dict[str, Any]:
    task_spec = state.get("task_spec") if isinstance(state.get("task_spec"), dict) else {}
    tools = _build_plan_tools(task_spec)
    tool_map = {getattr(t, "name", ""): t for t in tools if getattr(t, "name", "")}

    private_messages = state.get("private_messages") if isinstance(state.get("private_messages"), list) else []
    pending_tool_calls = state.get("pending_tool_calls") if isinstance(state.get("pending_tool_calls"), list) else []
    tool_patches = state.get("tool_patches") if isinstance(state.get("tool_patches"), list) else []

    new_private = list(private_messages)
    new_patches = list(tool_patches)

    for call in pending_tool_calls:
        name = call.get("name")
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        call_id = str(call.get("id") or "")

        tool = tool_map.get(name)
        if tool is None:
            obs = {"role": "tool", "content": f"Tool not found: {name}", "tool_call_id": call_id}
            _, obs = ensure_message_id(obs)
            new_private.append(obs)
            continue

        result = tool.invoke(args)
        patch = _extract_state_patch(result)
        if patch:
            new_patches.append(patch)

        obs = {"role": "tool", "content": _tool_output_to_content(result), "tool_call_id": call_id}
        _, obs = ensure_message_id(obs)
        new_private.append(obs)

    return {
        "private_messages": new_private,
        "tool_patches": new_patches,
        "pending_tool_calls": [],
    }


def finalize_node(state: PlanSubState, config: RunnableConfig | None = None) -> dict[str, Any]:
    tool_patches = state.get("tool_patches") if isinstance(state.get("tool_patches"), list) else []
    merged_patch = merge_patches({}, tool_patches)
    return {"state_patch": merged_patch}


def cleanup_node(state: PlanSubState, config: RunnableConfig | None = None) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if state.get("private_messages"):
        updates["private_messages"] = []
    if state.get("pending_tool_calls"):
        updates["pending_tool_calls"] = []
    if state.get("tool_patches"):
        updates["tool_patches"] = []
    return updates


def create_plan_subgraph() -> StateGraph:
    builder = StateGraph(PlanSubState)
    builder.add_node("llm", llm_step_node)
    builder.add_node("tools", tool_step_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("cleanup", cleanup_node)

    def _route_after_llm(state: PlanSubState) -> str:
        calls = state.get("pending_tool_calls") if isinstance(state.get("pending_tool_calls"), list) else []
        if calls:
            return "tools"
        return "finalize"

    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", _route_after_llm, {"tools": "tools", "finalize": "finalize"})
    builder.add_edge("tools", "llm")
    builder.add_edge("finalize", "cleanup")
    builder.add_edge("cleanup", END)
    return builder


def get_plan_subgraph(checkpointer: Optional[BaseCheckpointSaver] = None):
    key = id(checkpointer) if checkpointer is not None else 0
    cached = _compiled_cache.get(key)
    if cached is not None:
        return cached
    builder = create_plan_subgraph()
    if checkpointer is not None:
        app = builder.compile(checkpointer=checkpointer)
    else:
        app = builder.compile()
    _compiled_cache[key] = app
    return app
