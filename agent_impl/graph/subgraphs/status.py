from __future__ import annotations

import json
import os
from typing import Any, Optional

from typing_extensions import TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agents.tooling.patch import merge_patches
from agents.tools.all_tools import build_all_tools_for_agent
from config import get_llm
from graph.message_builder import build_messages_for_model
from graph.state import convert_message_to_dict, ensure_message_id


class StatusSubState(TypedDict, total=False):
    task_spec: dict
    private_messages: list[dict]
    tool_patches: list[dict]
    final: dict
    state_patch: dict


_compiled_cache: dict[int, Any] = {}


def _normalize_role(msg_dict: dict) -> dict:
    role = msg_dict.get("role")
    if role == "human":
        msg_dict["role"] = "user"
    elif role == "ai":
        msg_dict["role"] = "assistant"
    return msg_dict


def _ensure_tool_call_integrity(messages: list[Any]) -> list[Any]:
    if not messages:
        return []
    out: list[Any] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if isinstance(msg, ToolMessage):
            i += 1
            continue
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            tool_calls = getattr(msg, "tool_calls", None) or []
            expected_ids: list[str] = []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tc_id = tc.get("id")
                    if tc_id:
                        expected_ids.append(str(tc_id))
            if not expected_ids:
                out.append(msg)
                i += 1
                continue
            block: list[Any] = [msg]
            remaining = set(expected_ids)
            j = i + 1
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                tm = messages[j]
                tc_id = str(getattr(tm, "tool_call_id", "") or "")
                if tc_id in remaining:
                    remaining.remove(tc_id)
                    block.append(tm)
                    j += 1
                    if not remaining:
                        break
                    continue
                break
            if not remaining:
                out.extend(block)
                i = j
                continue
            i += 1
            continue
        out.append(msg)
        i += 1
    return out


def _truncate_messages(messages: list[Any], *, max_total: int = 25) -> list[Any]:
    if max_total <= 0:
        return list(messages)
    if len(messages) <= max_total:
        return _ensure_tool_call_integrity(list(messages))
    head = list(messages[:3])
    tail_budget = max_total - len(head)
    if tail_budget <= 0:
        return _ensure_tool_call_integrity(list(messages[-max_total:]))
    return _ensure_tool_call_integrity(head + list(messages[-tail_budget:]))


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


def _build_status_tools(task_spec: dict) -> list[BaseTool]:
    parent_state = task_spec.get("parent_state") if isinstance(task_spec.get("parent_state"), dict) else {}

    def state_getter() -> dict:
        return parent_state

    return build_all_tools_for_agent("status", state_getter=state_getter)


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


def run_node(state: StatusSubState, config: RunnableConfig | None = None) -> dict[str, Any]:
    task_spec = state.get("task_spec") if isinstance(state.get("task_spec"), dict) else {}
    instruction = str(task_spec.get("instruction") or "")
    private_messages = state.get("private_messages") if isinstance(state.get("private_messages"), list) else []

    tools = _build_status_tools(task_spec)
    patches: list[dict] = []
    wrapped_tools = _wrap_tools_for_patch_collection(list(tools or []), patches)

    cfg = dict(config or {})
    rounds = max(1, int(os.getenv("SUBAGENT_TOOL_MAX_ROUNDS", "8")))
    cfg["recursion_limit"] = max(25, rounds * 4 + 10)

    llm = get_llm(temperature=0.7, use_tools=True)
    agent_graph = create_agent(
        model=llm,
        tools=wrapped_tools,
        system_prompt=None,
        name="status_tool_loop_agent",
        checkpointer=cfg.get("checkpointer"),
    )

    if private_messages:
        messages_in: list[BaseMessage] = _dict_messages_to_lc(private_messages)
    else:
        parent_state = task_spec.get("parent_state") if isinstance(task_spec.get("parent_state"), dict) else {}
        initial_messages = build_messages_for_model(
            state=parent_state,
            agent_name="status_agent",
            current_input=instruction,
        )
        initial_messages = _truncate_messages(initial_messages, max_total=25)
        messages_in = list(initial_messages)

    result = agent_graph.invoke({"messages": messages_in}, config=cfg)
    if isinstance(result, dict) and "__interrupt__" in result:
        interrupts = result.get("__interrupt__") or []
        payload = interrupts[0].value if interrupts else {}
        answer = interrupt(payload)
        result = agent_graph.invoke(Command(resume=answer), config=cfg)

    messages_out = list(result.get("messages") or []) if isinstance(result, dict) else []
    final = messages_out[-1] if messages_out else AIMessage(content="")
    final_text = str(getattr(final, "content", "") or "").strip()
    normalized_private = _normalize_private_messages(messages_out)

    return {
        "private_messages": normalized_private,
        "tool_patches": patches,
        "final": {"text": final_text},
    }


def finalize_node(state: StatusSubState, config: RunnableConfig | None = None) -> dict[str, Any]:
    tool_patches = state.get("tool_patches") if isinstance(state.get("tool_patches"), list) else []
    merged_patch = merge_patches({}, tool_patches)
    return {"state_patch": merged_patch}


def cleanup_node(state: StatusSubState, config: RunnableConfig | None = None) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if state.get("private_messages"):
        updates["private_messages"] = []
    if state.get("tool_patches"):
        updates["tool_patches"] = []
    return updates


def create_status_subgraph() -> StateGraph:
    builder = StateGraph(StatusSubState)
    builder.add_node("run", run_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("cleanup", cleanup_node)

    builder.add_edge(START, "run")
    builder.add_edge("run", "finalize")
    builder.add_edge("finalize", "cleanup")
    builder.add_edge("cleanup", END)
    return builder


def get_status_subgraph(checkpointer: Optional[BaseCheckpointSaver] = None):
    key = id(checkpointer) if checkpointer is not None else 0
    cached = _compiled_cache.get(key)
    if cached is not None:
        return cached
    builder = create_status_subgraph()
    if checkpointer is not None:
        app = builder.compile(checkpointer=checkpointer)
    else:
        app = builder.compile()
    _compiled_cache[key] = app
    return app
