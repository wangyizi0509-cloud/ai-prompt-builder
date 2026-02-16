"""
主 Agent 节点 (Main Agent)
决策中枢，负责回应用户和决策下一步行动

支持的功能：
1. 回应用户（简短、共情、承上启下）
2. 决策下一步行动（调用子 Agent 或结束本轮）
3. 子 Agent 返回后再决策（灵活判断，无固定流程）
4. 根据意图类型使用咨询 Skills 直接回复（解答疑惑、情感陪伴）

上下文架构更新 (v2.0)：
- 使用分层上下文架构（Layer 0-4）
- 通过 context_builder 统一组装上下文

任务管理更新 (v2.1)：
- 任务边界：由模型判断（继续/新建/完成）
- 思考过程：同一任务内保留，任务切换时归档（不删除）
- 任务 ID：语义化命名（如"判断crush是否喜欢用户"）
"""

import json
import os
from typing import Any

from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import ensure_config
from langgraph.types import Command, interrupt

from agents.tooling.patch import ToolResult, merge_patches, merge_state_patch
from agents.tooling.tool_result import ok
from agents.tools.all_tools import build_all_tools_for_agent
from graph.state import AgentState
from graph.message_builder import build_messages_for_model
from config import get_llm
from graph.runtime_config import (
    build_inner_agent_config,
    resolve_runtime_checkpointer,
    sanitize_nested_runtime_config,
    sanitize_runtime_config,
)
from graph.subgraphs.plan import get_plan_subgraph
from graph.subgraphs.guide import get_guide_subgraph
from graph.subgraphs.status import get_status_subgraph
from graph.tools.submit_tools import submit_tools_state_context


class _SubagentToolInput(BaseModel):
    instruction: str = Field(description="对子 agent 的指令/请求")

def _ensure_tool_call_integrity(messages: list[BaseMessage]) -> list[BaseMessage]:
    if not messages:
        return []
    out: list[BaseMessage] = []
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
            block: list[BaseMessage] = [msg]
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


def _truncate_messages(messages: list[BaseMessage], *, max_total: int = 25) -> list[BaseMessage]:
    if max_total <= 0:
        return list(messages)
    if len(messages) <= max_total:
        return _ensure_tool_call_integrity(list(messages))
    head = list(messages[:3])
    tail_budget = max_total - len(head)
    if tail_budget <= 0:
        return _ensure_tool_call_integrity(list(messages[-max_total:]))
    return _ensure_tool_call_integrity(head + list(messages[-tail_budget:]))


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


def _format_onboarding_handoff_summary(handoff: Any) -> str:
    if not isinstance(handoff, dict):
        return ""
    recommendation = handoff.get("recommendation")
    suggested_action = handoff.get("suggested_action")
    reason = handoff.get("reason")

    rec_text = str(recommendation) if isinstance(recommendation, (str, int, float, bool)) else ""
    action_text = str(suggested_action) if isinstance(suggested_action, (str, int, float, bool)) else ""
    reason_text = str(reason) if isinstance(reason, (str, int, float, bool)) else ""

    parts: list[str] = []
    if rec_text:
        parts.append(f"建议: {rec_text}")
    if action_text:
        parts.append(f"动作: {action_text}")
    if reason_text:
        parts.append(f"理由: {reason_text}")
    return "\n".join(parts)


def _format_onboarding_handoff_summary(handoff: Any) -> str:
    if not isinstance(handoff, dict):
        return ""
    recommendation = handoff.get("recommendation")
    suggested_action = handoff.get("suggested_action")
    reason = handoff.get("reason")

    rec_text = str(recommendation) if isinstance(recommendation, (str, int, float, bool)) else ""
    action_text = str(suggested_action) if isinstance(suggested_action, (str, int, float, bool)) else ""
    reason_text = str(reason) if isinstance(reason, (str, int, float, bool)) else ""

    parts: list[str] = []
    if rec_text:
        parts.append(f"建议: {rec_text}")
    if action_text:
        parts.append(f"动作: {action_text}")
    if reason_text:
        parts.append(f"理由: {reason_text}")
    return "\n".join(parts)


def _wrap_tools_for_patch_collection(tools: list[BaseTool], patches: list[dict]) -> list[BaseTool]:
    wrapped: list[BaseTool] = []
    for tool in tools:
        if not isinstance(tool, BaseTool):
            wrapped.append(tool)
            continue

        def _make_wrapped(inner: BaseTool):
            def _wrapped(**kwargs):
                result = inner.invoke(kwargs, config=sanitize_nested_runtime_config(ensure_config()))
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


def _inquiry_card_from_interrupt(interrupts: Any) -> dict[str, Any] | None:
    """从 __interrupt__ 列表中取出 inquiry_card，供 state 与前端展示。支持 value 为 {inquiry_card: card} 或直接为 card。"""
    if not isinstance(interrupts, list) or not interrupts:
        return None
    first = interrupts[0]
    value = first.get("value") if isinstance(first, dict) else getattr(first, "value", None)
    if not isinstance(value, dict):
        return None
    inner = value.get("inquiry_card") if isinstance(value.get("inquiry_card"), dict) else None
    if inner is not None and isinstance(inner.get("questions"), list) and inner["questions"]:
        return inner
    if isinstance(value.get("questions"), list) and value["questions"]:
        return value
    return None


def _run_langchain_supervisor(
    *,
    llm: Any,
    tools: list[BaseTool],
    initial_messages: list[BaseMessage],
    max_rounds: int,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    patches: list[dict] = []
    wrapped_tools = _wrap_tools_for_patch_collection(list(tools or []), patches)

    checkpointer = resolve_runtime_checkpointer(config)

    # Build a clean config that strips ALL __pregel_* / checkpoint_* keys
    # to prevent the inner agent's tool-loop from being disrupted.
    cfg = build_inner_agent_config(config, namespace="main_tool_loop")

    agent_graph = create_agent(model=llm, tools=wrapped_tools, system_prompt=None, name="tool_loop_agent", checkpointer=checkpointer)

    rounds = max(1, int(max_rounds or 1))
    recursion_limit = max(25, rounds * 4 + 10)
    cfg["recursion_limit"] = recursion_limit
    result = agent_graph.invoke(
        {"messages": list(initial_messages)},
        config=cfg,
    )

    messages_out = list(result.get("messages") or [])
    final = messages_out[-1] if messages_out else AIMessage(content="")
    new_messages = messages_out[len(initial_messages) :] if len(messages_out) >= len(initial_messages) else messages_out

    out = {"final": final, "new_messages": new_messages, "patches": patches}
    if "__interrupt__" in result:
        out["__interrupt__"] = result["__interrupt__"]
    return out


def _call_subagent(
    *,
    role: str,
    instruction: str,
    state_getter,
    config: RunnableConfig | None = None,
) -> ToolResult:
    role = (role or "").strip().lower()
    tools = build_all_tools_for_agent(role, state_getter=state_getter)
    llm = get_llm(temperature=0.7, use_tools=True)

    agent_name = {"status": "status_agent", "plan": "plan_agent", "guide": "guide_agent"}.get(role, role)
    current_state = state_getter()
    initial_messages = build_messages_for_model(
        state=current_state,
        agent_name=agent_name,
        current_input=instruction,
    )
    initial_messages = _truncate_messages(initial_messages, max_total=25)
    with submit_tools_state_context(current_state):
        supervisor = _run_langchain_supervisor(
            llm=llm,
            tools=tools,
            initial_messages=initial_messages,
            max_rounds=int(os.getenv("SUBAGENT_TOOL_MAX_ROUNDS", "8")),
            config=config,
        )
    merged_patch = merge_patches({}, supervisor["patches"])
    output = (supervisor["final"].content or "").strip()
    return ok(output=output, state_patch=merged_patch)


def _build_all_tools(state_getter, runtime_config: dict[str, Any] | None = None) -> list[BaseTool]:
    def _current_config() -> dict:
        merged = sanitize_nested_runtime_config(runtime_config)
        incoming_raw = ensure_config()
        incoming = sanitize_nested_runtime_config(incoming_raw)

        base_cfg = merged.get("configurable")
        in_cfg = incoming.get("configurable")
        if isinstance(base_cfg, dict) and isinstance(in_cfg, dict):
            merged["configurable"] = {**base_cfg, **in_cfg}
        elif isinstance(in_cfg, dict):
            merged["configurable"] = dict(in_cfg)

        checkpointer = resolve_runtime_checkpointer(incoming_raw) or resolve_runtime_checkpointer(runtime_config)
        if checkpointer is not None:
            merged["checkpointer"] = checkpointer
        return merged

    def _status_tool(instruction: str) -> ToolResult:
        cfg = _current_config()
        checkpointer = resolve_runtime_checkpointer(cfg)
        subgraph = get_status_subgraph(checkpointer=checkpointer) if checkpointer is not None else get_status_subgraph()
        invoke_cfg = sanitize_nested_runtime_config(cfg)
        parent_state = state_getter()
        sub_in = {
            "task_spec": {
                "instruction": instruction,
                "parent_state": dict(parent_state or {}),
            },
            "private_messages": [],
        }
        sub_out = subgraph.invoke(sub_in, config=invoke_cfg)
        if isinstance(sub_out, dict) and "__interrupt__" in sub_out:
            interrupts = sub_out.get("__interrupt__") or []
            payload = interrupts[0].value if interrupts else {}
            answer = interrupt(payload)
            sub_out = subgraph.invoke(Command(resume=answer), config=invoke_cfg)
        patch = dict(sub_out.get("state_patch") or {}) if isinstance(sub_out, dict) else {}
        final = sub_out.get("final") if isinstance(sub_out, dict) else None
        text = ""
        if isinstance(final, dict) and isinstance(final.get("text"), str):
            text = final["text"].strip()
        return ok(output=text, state_patch=patch)

    def _plan_tool(instruction: str) -> ToolResult:
        cfg = _current_config()
        checkpointer = resolve_runtime_checkpointer(cfg)
        subgraph = get_plan_subgraph(checkpointer=checkpointer) if checkpointer is not None else get_plan_subgraph()
        invoke_cfg = sanitize_nested_runtime_config(cfg)
        parent_state = state_getter()
        sub_in = {
            "task_spec": {
                "instruction": instruction,
                "parent_state": dict(parent_state or {}),
            },
            "private_messages": [],
        }
        sub_out = subgraph.invoke(sub_in, config=invoke_cfg)
        if isinstance(sub_out, dict) and "__interrupt__" in sub_out:
            interrupts = sub_out.get("__interrupt__") or []
            payload = interrupts[0].value if interrupts else {}
            answer = interrupt(payload)
            sub_out = subgraph.invoke(Command(resume=answer), config=invoke_cfg)
        patch = dict(sub_out.get("state_patch") or {}) if isinstance(sub_out, dict) else {}
        final = sub_out.get("final") if isinstance(sub_out, dict) else None
        text = ""
        if isinstance(final, dict) and isinstance(final.get("text"), str):
            text = final["text"].strip()
        return ok(output=text, state_patch=patch)

    def _guide_tool(instruction: str) -> ToolResult:
        cfg = _current_config()
        checkpointer = resolve_runtime_checkpointer(cfg)
        subgraph = get_guide_subgraph(checkpointer=checkpointer) if checkpointer is not None else get_guide_subgraph()
        invoke_cfg = sanitize_nested_runtime_config(cfg)
        parent_state = state_getter()
        sub_in = {
            "task_spec": {
                "instruction": instruction,
                "parent_state": dict(parent_state or {}),
            },
            "private_messages": [],
        }
        sub_out = subgraph.invoke(sub_in, config=invoke_cfg)
        if isinstance(sub_out, dict) and "__interrupt__" in sub_out:
            interrupts = sub_out.get("__interrupt__") or []
            payload = interrupts[0].value if interrupts else {}
            answer = interrupt(payload)
            sub_out = subgraph.invoke(Command(resume=answer), config=invoke_cfg)
        patch = dict(sub_out.get("state_patch") or {}) if isinstance(sub_out, dict) else {}
        final = sub_out.get("final") if isinstance(sub_out, dict) else None
        text = ""
        if isinstance(final, dict) and isinstance(final.get("text"), str):
            text = final["text"].strip()
        return ok(output=text, state_patch=patch)

    status_tool = StructuredTool.from_function(
        func=_status_tool,
        name="call_status_agent",
        description="调用 status 子 agent 完成现状分析/补齐缺口",
        args_schema=_SubagentToolInput,
    )
    plan_tool = StructuredTool.from_function(
        func=_plan_tool,
        name="call_plan_agent",
        description="调用 plan 子 agent 产出行动规划",
        args_schema=_SubagentToolInput,
    )
    guide_tool = StructuredTool.from_function(
        func=_guide_tool,
        name="call_guide_agent",
        description="调用 guide 子 agent 产出行动指南或更新指南",
        args_schema=_SubagentToolInput,
    )

    base_tools = build_all_tools_for_agent("main", state_getter=state_getter)
    tools = [status_tool, plan_tool, guide_tool, *base_tools]

    seen: set[str] = set()
    unique: list[BaseTool] = []
    for t in tools:
        name = getattr(t, "name", None) or ""
        if not name or name in seen:
            continue
        seen.add(name)
        unique.append(t)
    return unique


def main_agent_node(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
    working_state: dict[str, Any] = dict(state or {})
    runtime_cfg: dict[str, Any] = sanitize_runtime_config(config)
    checkpointer = resolve_runtime_checkpointer(config)
    if checkpointer is not None:
        runtime_cfg["checkpointer"] = checkpointer

    def state_getter() -> dict:
        return working_state

    tools = _build_all_tools(state_getter, runtime_config=runtime_cfg)
    llm = get_llm(temperature=0.7, use_tools=True)

    initial_messages = build_messages_for_model(
        state=working_state,
        agent_name="main_agent",
        current_input=str(working_state.get("user_message") or ""),
    )
    initial_messages = _truncate_messages(initial_messages, max_total=25)
    with submit_tools_state_context(working_state):
        supervisor = _run_langchain_supervisor(
            llm=llm,
            tools=tools,
            initial_messages=initial_messages,
            max_rounds=int(os.getenv("MAIN_AGENT_TOOL_MAX_ROUNDS", "10")),
            config=config,
        )

    merged_tool_patch = merge_patches({}, supervisor["patches"])
    if merged_tool_patch:
        working_state = merge_state_patch(working_state, merged_tool_patch)

    existing_messages = list(state.get("messages") or [])
    messages_out = existing_messages + list(supervisor["new_messages"])

    pending_responses = list(state.get("pending_responses") or [])
    final_content = (supervisor["final"].content or "").strip()
    if final_content:
        pending_responses.append({"from": "main_agent", "content": final_content, "phase": "final"})

    # 当 tool loop 被 interrupt 中断且没有最终文本回复时，
    # 从 new_messages 中提取中断前已产出的 AI 文本回复，
    # 确保 submit_status_report 等工具完成后的总结不会因后续 interrupt 而丢失。
    has_interrupt = "__interrupt__" in supervisor
    if has_interrupt and not pending_responses:
        for msg in reversed(supervisor["new_messages"]):
            if isinstance(msg, AIMessage):
                pre_text = (msg.content or "").strip()
                if pre_text:
                    pending_responses.append({
                        "from": "main_agent",
                        "content": pre_text,
                        "phase": "pre_interrupt",
                    })
                    if not final_content:
                        final_content = pre_text
                    break

    out: dict[str, Any] = dict(merged_tool_patch)
    out.update(
        {
            "messages": messages_out,
            "pending_responses": pending_responses,
            "last_response_for_continuity": final_content or None,
            "completion_status": None,
            "result_summary": None,
        }
    )
    if has_interrupt:
        out["__interrupt__"] = supervisor["__interrupt__"]
        # 让前端/API 能从 state 直接读到 inquiry_card 并展示（子图 ask_human 触发的 interrupt 会透传到这里）
        _card = _inquiry_card_from_interrupt(supervisor["__interrupt__"])
        if _card is not None:
            out["inquiry_card"] = _card
    return out
