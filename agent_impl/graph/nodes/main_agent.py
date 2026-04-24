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
import hashlib
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import ensure_config
from langgraph.config import get_stream_writer
from langgraph.errors import GraphBubbleUp
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
from api.display_events import get_tool_label
from utils.logger import get_logger
from utils.reasoning_content import extract_reasoning_content


logger = get_logger("main_agent")


def _answers_fingerprint(answers: Any) -> str:
    if not isinstance(answers, dict) or not answers:
        return ""
    canonical = json.dumps(answers, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_question_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    questions = payload.get("questions")
    if not isinstance(questions, list):
        return []
    qids: list[str] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        qid = q.get("id")
        if qid is None:
            continue
        qids.append(str(qid))
    return qids


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


def _tool_failure_to_content(tool_name: str, exc: Exception) -> str:
    name = (tool_name or "unknown_tool").strip() or "unknown_tool"
    err = str(exc).strip() or exc.__class__.__name__
    return f"{name} 调用失败：{err}"


def _is_checkpoint_iter_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "error iterating checkpoint results" in text


def _invoke_subgraph_with_fallback_namespace(
    *,
    subgraph: Any,
    sub_in: dict[str, Any],
    invoke_cfg: dict[str, Any],
    fallback_invoke_cfg: dict[str, Any],
    tool_name: str,
) -> tuple[Any, dict[str, Any]]:
    try:
        return subgraph.invoke(sub_in, config=invoke_cfg), invoke_cfg
    except Exception as e:
        if not _is_checkpoint_iter_error(e):
            raise
        logger.exception("%s invoke failed with primary namespace", tool_name)
        logger.warning("%s retrying with fallback namespace", tool_name)
        return subgraph.invoke(sub_in, config=fallback_invoke_cfg), fallback_invoke_cfg


def _extract_state_patch(result: Any) -> dict:
    if isinstance(result, dict) and isinstance(result.get("state_patch"), dict):
        return dict(result.get("state_patch") or {})
    return {}


def _extract_pending_interrupt(subgraph: Any, invoke_cfg: dict[str, Any]) -> dict | None:
    """检查子图 thread 是否有上一轮留下的 pending interrupt（未被 relay 的问题）。

    用于修复跨 trace interrupt 静默消费问题：
    - Trace 1 的外层 interrupt() 在 _plan_tool / _guide_tool / _status_tool 的 while 循环里触发
    - Trace 2 时 main_agent_node 从零重新执行，子图全新调用，handle_interrupt_node
      里的 interrupt() 成为第一个调用，错误消费了 answer_to_A
    - 通过在 invoke 之前先检测 pending interrupt 并在外层 relay，确保消费顺序正确

    返回 dict（非空 payload）→ 有 pending interrupt，调用方应先 relay
    返回 None → 无 pending interrupt（首次调用、子图已完成、get_state 失败等）
    """
    try:
        snapshot = subgraph.get_state(invoke_cfg)
    except Exception:
        return None
    if snapshot is None:
        return None

    # 路径 1：读取子图 state values 中的语义字段（最可靠，跨 LangGraph 版本稳定）
    values = getattr(snapshot, "values", None) or {}
    if isinstance(values, dict) and values.get("_inner_interrupted"):
        payload = values.get("_interrupt_payload")
        if isinstance(payload, dict) and payload:
            return payload

    # 路径 2：兜底——读取 PregelTask.interrupts
    tasks = getattr(snapshot, "tasks", None) or []
    for task in tasks:
        task_interrupts = getattr(task, "interrupts", None) or []
        if task_interrupts:
            first = task_interrupts[0]
            val = getattr(first, "value", None)
            if isinstance(val, dict) and val:
                return val

    return None


def _extract_status_report_markdown(state_like: Any) -> str:
    if not isinstance(state_like, dict):
        return ""
    layer2 = state_like.get("layer2_memory")
    if not isinstance(layer2, dict):
        return ""
    report = layer2.get("current_status_report")
    if not isinstance(report, dict):
        return ""
    content = report.get("report_content")
    return str(content).strip() if isinstance(content, str) else ""


def _extract_current_status_report_item(state_like: Any) -> dict[str, Any]:
    if not isinstance(state_like, dict):
        return {}
    layer2 = state_like.get("layer2_memory")
    if not isinstance(layer2, dict):
        return {}
    report = layer2.get("current_status_report")
    return dict(report) if isinstance(report, dict) else {}


def _extract_current_action_plan_item(state_like: Any) -> dict[str, Any]:
    if not isinstance(state_like, dict):
        return {}
    layer2 = state_like.get("layer2_memory")
    if not isinstance(layer2, dict):
        return {}
    plan = layer2.get("current_action_plan")
    return dict(plan) if isinstance(plan, dict) else {}


def _extract_action_guides(state_like: Any) -> list[dict[str, Any]]:
    if not isinstance(state_like, dict):
        return []
    layer2 = state_like.get("layer2_memory")
    if not isinstance(layer2, dict):
        return []
    guides = layer2.get("action_guides")
    if not isinstance(guides, list):
        return []
    return [dict(g) for g in guides if isinstance(g, dict)]


def _extract_layer2_from_patch(patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        return {}
    layer2 = patch.get("layer2_memory")
    return layer2 if isinstance(layer2, dict) else {}


def _first_non_empty_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _get_item_identity(item: dict[str, Any], *keys: str) -> str:
    if not isinstance(item, dict):
        return ""
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _trim_for_observation(text: str, *, limit: int = 1600) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "\n...[已截断]"


def _build_status_tool_observation(final_text: str, patch: dict[str, Any]) -> str:
    layer2 = _extract_layer2_from_patch(patch)
    report = layer2.get("current_status_report") if isinstance(layer2.get("current_status_report"), dict) else {}
    report_id = report.get("report_id")
    report_md = _first_non_empty_text(report.get("report_content"))
    if not report_md:
        return final_text

    header = f"【Status 子Agent结果】已提交现状分析报告 #{report_id}" if report_id else "【Status 子Agent结果】已提交现状分析报告"
    payload = _trim_for_observation(report_md, limit=1800)
    if final_text:
        return f"{final_text}\n\n{header}\n{payload}"
    return f"{header}\n{payload}"


def _build_plan_tool_observation(final_text: str, patch: dict[str, Any]) -> str:
    layer2 = _extract_layer2_from_patch(patch)
    plan = layer2.get("current_action_plan") if isinstance(layer2.get("current_action_plan"), dict) else {}
    plan_id = plan.get("plan_id")
    plan_md = _first_non_empty_text(plan.get("plan_content"))
    if not plan_md:
        return final_text

    header = f"【Plan 子Agent结果】已提交行动规划 #{plan_id}" if plan_id else "【Plan 子Agent结果】已提交行动规划"
    payload = _trim_for_observation(plan_md, limit=1800)
    if final_text:
        return f"{final_text}\n\n{header}\n{payload}"
    return f"{header}\n{payload}"


def _build_guide_tool_observation(final_text: str, patch: dict[str, Any]) -> str:
    layer2 = _extract_layer2_from_patch(patch)
    guides = layer2.get("action_guides") if isinstance(layer2.get("action_guides"), list) else []
    latest = guides[-1] if guides and isinstance(guides[-1], dict) else {}
    if not latest:
        return final_text

    guide_id = latest.get("guide_id")
    title = _first_non_empty_text(latest.get("title"), latest.get("one_liner"))
    guide_obj = latest.get("guide") if isinstance(latest.get("guide"), dict) else {}
    guide_md = _first_non_empty_text(guide_obj.get("guide_content"))
    if not guide_md:
        return final_text

    if guide_id and title:
        header = f"【Guide 子Agent结果】已提交行动指南 #{guide_id}（{title}）"
    elif guide_id:
        header = f"【Guide 子Agent结果】已提交行动指南 #{guide_id}"
    elif title:
        header = f"【Guide 子Agent结果】已提交行动指南（{title}）"
    else:
        header = "【Guide 子Agent结果】已提交行动指南"
    payload = _trim_for_observation(guide_md, limit=1800)
    if final_text:
        return f"{final_text}\n\n{header}\n{payload}"
    return f"{header}\n{payload}"


def _build_status_brief(markdown: str) -> str:
    text = (markdown or "").strip()
    if not text:
        return ""

    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("```"):
            continue
        line = line.lstrip("#").strip()
        line = line.lstrip("-*+ ").strip()
        line = line.replace("**", "").replace("`", "")
        if line:
            lines.append(line)
        if len(lines) >= 4:
            break

    if not lines:
        return ""

    summary = "；".join(lines)
    if len(summary) > 220:
        summary = summary[:220].rstrip() + "..."

    return f"【现状分析摘要】{summary}\n\n完整内容见“当前现状”面板。"


def _build_system_task_pending_responses(
    previous_state: dict[str, Any],
    next_state: dict[str, Any],
    existing_pending_responses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pending_items: list[dict[str, Any]] = []

    has_status_thinking = any(
        isinstance(item, dict)
        and item.get("from") == "status_agent"
        and item.get("phase") == "subgraph_thinking"
        for item in existing_pending_responses
    )
    has_plan_thinking = any(
        isinstance(item, dict)
        and item.get("from") == "plan_agent"
        and item.get("phase") == "subgraph_thinking"
        for item in existing_pending_responses
    )

    old_status = _extract_current_status_report_item(previous_state)
    new_status = _extract_current_status_report_item(next_state)
    old_status_id = _get_item_identity(old_status, "report_id", "id")
    new_status_id = _get_item_identity(new_status, "report_id", "id")
    if new_status and new_status_id and new_status_id != old_status_id:
        report_markdown = _extract_status_report_markdown(next_state)
        if report_markdown and not has_status_thinking:
            pending_items.append(
                {
                    "from": "main_agent",
                    "content": "这是基于你提供的信息生成的现状分析报告：",
                    "phase": "status_preface",
                    "messageKey": f"status_preface_{new_status_id}",
                }
            )
        pending_items.append(
            {
                "type": "system_task",
                "from": "main_agent",
                "taskType": "status",
                "taskKey": f"status_{new_status_id}",
                "taskState": "done",
                "label": "STATUS REPORT",
                "title": "现状分析报告已生成",
                "desc": "点击查看最新的关系阶段与分析报告",
            }
        )

    old_plan = _extract_current_action_plan_item(previous_state)
    new_plan = _extract_current_action_plan_item(next_state)
    old_plan_id = _get_item_identity(old_plan, "plan_id", "id")
    new_plan_id = _get_item_identity(new_plan, "plan_id", "id")
    if new_plan and new_plan_id and new_plan_id != old_plan_id:
        plan_markdown = str(new_plan.get("plan_content") or "").strip()
        if plan_markdown and not has_plan_thinking:
            pending_items.append(
                {
                    "from": "main_agent",
                    "content": "我已为你制定了专属的行动计划：",
                    "phase": "plan_preface",
                    "messageKey": f"plan_preface_{new_plan_id}",
                }
            )
        pending_items.append(
            {
                "type": "system_task",
                "from": "main_agent",
                "taskType": "strategy",
                "taskKey": f"plan_{new_plan_id}",
                "taskState": "done",
                "label": "PLANNING",
                "title": "专属情感计划已生成",
                "desc": "点击查看最新的情感计划",
            }
        )

    old_guides = _extract_action_guides(previous_state)
    new_guides = _extract_action_guides(next_state)
    old_guide_ids = {
        _get_item_identity(guide, "guide_id", "id")
        for guide in old_guides
        if _get_item_identity(guide, "guide_id", "id")
    }
    for guide in new_guides:
        guide_id = _get_item_identity(guide, "guide_id", "id")
        if not guide_id or guide_id in old_guide_ids:
            continue
        guide_title = _first_non_empty_text(guide.get("title"), guide.get("one_liner"), "点击查看最新的行动指南")
        pending_items.append(
            {
                "type": "system_task",
                "from": "main_agent",
                "taskType": "plan",
                "taskKey": f"guide_{guide_id}",
                "taskState": "done",
                "label": "ACTION GUIDE",
                "title": "新的行动指南已生成",
                "desc": guide_title,
            }
        )

    return pending_items


def _wrap_tools_for_patch_collection(
    tools: list[BaseTool],
    patches: list[dict],
    live_state: dict | None = None,
    emission_records: list[dict[str, Any]] | None = None,
) -> list[BaseTool]:
    """Wrap tools to collect state_patch from each invocation.

    If *live_state* is provided, the dict is **mutated in-place** after every
    tool call so that subsequent tools (and their ``_submit_tools_state`` reads)
    see the accumulated patches.  This prevents a later tool from overwriting an
    earlier tool's ``layer2_memory`` changes with stale snapshot data.
    """
    wrapped: list[BaseTool] = []
    for tool in tools:
        if not isinstance(tool, BaseTool):
            wrapped.append(tool)
            continue

        def _make_wrapped(inner: BaseTool):
            def _wrapped(**kwargs):
                pre_patch_state = {}
                if isinstance(live_state, dict):
                    layer2 = live_state.get("layer2_memory")
                    if isinstance(layer2, dict):
                        pre_patch_state = {"layer2_memory": deepcopy(layer2)}
                try:
                    result = inner.invoke(kwargs, config=sanitize_runtime_config(ensure_config()))
                except GraphBubbleUp:
                    raise
                except Exception as e:
                    logger.exception("tool invoke failed: tool=%s", getattr(inner, "name", ""))
                    return _tool_failure_to_content(getattr(inner, "name", ""), e)
                patch = _extract_state_patch(result)
                if emission_records is not None:
                    emission_records.append({
                        "patch": patch if isinstance(patch, dict) else None,
                        "previous_state": pre_patch_state,
                    })
                if patch:
                    patches.append(patch)
                    if live_state is not None:
                        updated = merge_state_patch(dict(live_state), patch)
                        live_state.clear()
                        live_state.update(updated)
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
    live_state: dict | None = None,
    writer=None,
) -> dict[str, Any]:
    # 手写 tool-loop，避开 langgraph.prebuilt.create_react_agent 里 ToolNode
    # 访问 Runtime.execution_info 的新 API——LangGraph Platform 的 base image
    # 锁死 langgraph==1.0.5（Runtime 上没有该属性），新版 prebuilt 会崩。
    patches: list[dict] = []
    emission_records: list[dict[str, Any]] = []
    wrapped_tools = _wrap_tools_for_patch_collection(
        list(tools or []),
        patches,
        live_state=live_state,
        emission_records=emission_records,
    )

    tools_by_name: dict[str, BaseTool] = {}
    for t in wrapped_tools:
        tname = getattr(t, "name", None)
        if tname:
            tools_by_name[tname] = t

    cfg = build_inner_agent_config(config, namespace="main_tool_loop")

    try:
        llm_with_tools = llm.bind_tools(wrapped_tools) if wrapped_tools else llm
    except Exception:
        logger.exception("bind_tools failed; falling back to unbounded llm")
        llm_with_tools = llm

    rounds = max(1, int(max_rounds or 1))

    messages_out: list[BaseMessage] = list(initial_messages)
    convo: list[BaseMessage] = list(initial_messages)
    interrupt_value = None

    for _ in range(rounds + 1):
        try:
            ai_msg = llm_with_tools.invoke(convo, config=cfg)
        except GraphBubbleUp as bubble:
            raise
        if not isinstance(ai_msg, AIMessage):
            ai_msg = AIMessage(content=str(getattr(ai_msg, "content", ai_msg) or ""))
        convo.append(ai_msg)
        messages_out.append(ai_msg)
        _emit_ai_events(writer, ai_msg)

        tool_calls = list(getattr(ai_msg, "tool_calls", None) or [])
        if not tool_calls:
            break

        stop_loop = False
        for tc in tool_calls:
            tc_name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            tc_args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
            tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
            tool = tools_by_name.get(tc_name or "")
            if tool is None:
                tool_content = _tool_failure_to_content(tc_name or "", RuntimeError(f"tool {tc_name} not found"))
                record: dict[str, Any] = {}
            else:
                pre_patch_index = len(emission_records)
                try:
                    tool_content = tool.invoke(tc_args or {}, config=sanitize_runtime_config(cfg))
                except GraphBubbleUp as bubble:
                    # interrupt() bubbles out — capture payload and stop
                    interrupt_value = getattr(bubble, "args", None) or getattr(bubble, "value", None)
                    stop_loop = True
                    break
                except Exception as e:
                    logger.exception("manual tool loop: tool invoke failed: tool=%s", tc_name)
                    tool_content = _tool_failure_to_content(tc_name or "", e)
                record = emission_records[pre_patch_index] if pre_patch_index < len(emission_records) else {}

            if not isinstance(tool_content, str):
                tool_content = str(tool_content)

            tool_msg = ToolMessage(
                content=tool_content,
                tool_call_id=tc_id or "",
                name=tc_name or "",
            )
            convo.append(tool_msg)
            messages_out.append(tool_msg)
            _emit_tool_done_from_message(
                writer,
                tool_msg,
                record.get("patch") if isinstance(record, dict) else None,
                record.get("previous_state") if isinstance(record, dict) else None,
            )

        if stop_loop:
            break

    final = next(
        (m for m in reversed(messages_out) if isinstance(m, AIMessage)),
        AIMessage(content=""),
    )
    new_messages = messages_out[len(initial_messages):]
    out = {"final": final, "new_messages": new_messages, "patches": patches}
    if interrupt_value is not None:
        out["__interrupt__"] = interrupt_value
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
    try:
        _subagent_writer = get_stream_writer()
    except RuntimeError:
        _subagent_writer = None
    with submit_tools_state_context(current_state):
        supervisor = _run_langchain_supervisor(
            llm=llm,
            tools=tools,
            initial_messages=initial_messages,
            max_rounds=int(os.getenv("SUBAGENT_TOOL_MAX_ROUNDS", "8")),
            config=config,
            live_state=current_state,
            writer=_subagent_writer,
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
        # 获取 stream writer 用于发射实时展示事件
        try:
            _sw = get_stream_writer()
        except RuntimeError:
            _sw = None

        cfg = _current_config()
        checkpointer = resolve_runtime_checkpointer(cfg)
        subgraph = get_status_subgraph(checkpointer=checkpointer) if checkpointer is not None else get_status_subgraph()
        invoke_cfg = build_inner_agent_config(cfg, namespace="status_subgraph")
        invoke_cfg_fallback = build_inner_agent_config(cfg, namespace="status_subgraph_retry")
        parent_state = state_getter()
        sub_in = {
            "task_spec": {
                "instruction": instruction,
                "parent_state": dict(parent_state or {}),
            },
            "private_messages": [],
        }

        # 报告卡片 loading 事件
        if _sw:
            try:
                _sw({"event_type": "report_card", "status": "loading", "report_type": "status"})
            except Exception:
                pass

        pending_payload = _extract_pending_interrupt(subgraph, invoke_cfg)
        active_cfg = invoke_cfg
        if pending_payload is not None:
            logger.info("call_status_agent pre-invoke relay: relaying pending interrupt from previous trace")
            answer = interrupt(pending_payload)
            sub_out = subgraph.invoke(Command(resume=answer), config=active_cfg)
        else:
            sub_out, active_cfg = _invoke_subgraph_with_fallback_namespace(
                subgraph=subgraph,
                sub_in=sub_in,
                invoke_cfg=invoke_cfg,
                fallback_invoke_cfg=invoke_cfg_fallback,
                tool_name="call_status_agent",
            )
        while isinstance(sub_out, dict) and "__interrupt__" in sub_out:
            interrupts = sub_out.get("__interrupt__") or []
            payload = interrupts[0].value if interrupts else {}
            answer = interrupt(payload)
            sub_out = subgraph.invoke(Command(resume=answer), config=active_cfg)
        patch = dict(sub_out.get("state_patch") or {}) if isinstance(sub_out, dict) else {}
        final = sub_out.get("final") if isinstance(sub_out, dict) else None
        # DEBUG: 检查子图返回的 patch 内容
        _l2_in_patch = patch.get("layer2_memory", {}) if isinstance(patch, dict) else {}
        _csr_in_patch = _l2_in_patch.get("current_status_report") if isinstance(_l2_in_patch, dict) else None
        logger.info(
            "call_status_agent patch check: patch_keys=%s l2_keys=%s csr_exists=%s csr_preview=%s",
            list(patch.keys()) if patch else [],
            list(_l2_in_patch.keys()) if isinstance(_l2_in_patch, dict) else None,
            _csr_in_patch is not None,
            str(_csr_in_patch)[:200] if _csr_in_patch else None,
        )
        text = ""
        if isinstance(final, dict) and isinstance(final.get("text"), str):
            text = final["text"].strip()
        text = _build_status_tool_observation(text, patch)

        # 提取子图中间 AI 消息，累积到 working_state 的临时字段，并通过 stream_writer 实时发射
        intermediate = sub_out.get("intermediate_messages") or [] if isinstance(sub_out, dict) else []
        if intermediate:
            ws = state_getter()
            existing = ws.get("_subgraph_intermediates") or []
            for msg_item in intermediate:
                if isinstance(msg_item, dict) and msg_item.get("text"):
                    existing.append({"from": "status_agent", "content": msg_item["text"], "phase": "subgraph_thinking"})
                    if _sw:
                        try:
                            _sw({
                                "event_type": "subgraph_thinking",
                                "content": msg_item["text"],
                                "source": "status_agent",
                            })
                        except Exception:
                            pass
            ws["_subgraph_intermediates"] = existing

        # 报告卡片 done 事件
        report_id = ""
        l2_patch = _extract_layer2_from_patch(patch)
        status_report = l2_patch.get("current_status_report") if isinstance(l2_patch.get("current_status_report"), dict) else {}
        if isinstance(status_report, dict):
            report_id = _get_item_identity(status_report, "report_id", "id")
        if _sw:
            try:
                _sw({"event_type": "report_card", "status": "done", "report_type": "status", "report_id": report_id})
            except Exception:
                pass

        return ok(output=text, state_patch=patch)

    def _plan_tool(instruction: str) -> ToolResult:
        # 获取 stream writer 用于发射实时展示事件
        try:
            _sw = get_stream_writer()
        except RuntimeError:
            _sw = None

        cfg = _current_config()
        checkpointer = resolve_runtime_checkpointer(cfg)
        subgraph = get_plan_subgraph(checkpointer=checkpointer) if checkpointer is not None else get_plan_subgraph()
        invoke_cfg = build_inner_agent_config(cfg, namespace="plan_subgraph")
        invoke_cfg_fallback = build_inner_agent_config(cfg, namespace="plan_subgraph_retry")
        parent_state = state_getter()
        sub_in = {
            "task_spec": {
                "instruction": instruction,
                "parent_state": dict(parent_state or {}),
            },
            "private_messages": [],
        }

        # 报告卡片 loading 事件
        if _sw:
            try:
                _sw({"event_type": "report_card", "status": "loading", "report_type": "plan"})
            except Exception:
                pass

        pending_payload = _extract_pending_interrupt(subgraph, invoke_cfg)
        active_cfg = invoke_cfg
        if pending_payload is not None:
            qids = _extract_question_ids(pending_payload)
            logger.info(
                "call_plan_agent pre-invoke relay: relaying pending interrupt from previous trace, "
                "question_count=%s, qids=%s",
                len(qids),
                qids,
            )
            answer = interrupt(pending_payload)
            if isinstance(answer, dict):
                logger.info(
                    "call_plan_agent pre-invoke relay resumed: answer_keys=%s, fp=%s",
                    list(answer.keys()),
                    _answers_fingerprint(answer),
                )
            else:
                logger.info("call_plan_agent pre-invoke relay resumed: answer_type=%s", type(answer).__name__)
            sub_out = subgraph.invoke(Command(resume=answer), config=active_cfg)
        else:
            sub_out, active_cfg = _invoke_subgraph_with_fallback_namespace(
                subgraph=subgraph,
                sub_in=sub_in,
                invoke_cfg=invoke_cfg,
                fallback_invoke_cfg=invoke_cfg_fallback,
                tool_name="call_plan_agent",
            )
        while isinstance(sub_out, dict) and "__interrupt__" in sub_out:
            interrupts = sub_out.get("__interrupt__") or []
            payload = interrupts[0].value if interrupts else {}
            qids = _extract_question_ids(payload)
            logger.info(
                "call_plan_agent interrupt: question_count=%s, qids=%s",
                len(qids),
                qids,
            )
            answer = interrupt(payload)
            if isinstance(answer, dict):
                logger.info(
                    "call_plan_agent resumed: answer_keys=%s, fp=%s",
                    list(answer.keys()),
                    _answers_fingerprint(answer),
                )
            else:
                logger.info("call_plan_agent resumed: answer_type=%s", type(answer).__name__)
            sub_out = subgraph.invoke(Command(resume=answer), config=active_cfg)
        patch = dict(sub_out.get("state_patch") or {}) if isinstance(sub_out, dict) else {}
        final = sub_out.get("final") if isinstance(sub_out, dict) else None
        text = ""
        if isinstance(final, dict) and isinstance(final.get("text"), str):
            text = final["text"].strip()
        text = _build_plan_tool_observation(text, patch)

        # 提取子图中间 AI 消息，累积到 working_state 的临时字段，并通过 stream_writer 实时发射
        intermediate = sub_out.get("intermediate_messages") or [] if isinstance(sub_out, dict) else []
        if intermediate:
            ws = state_getter()
            existing = ws.get("_subgraph_intermediates") or []
            for msg_item in intermediate:
                if isinstance(msg_item, dict) and msg_item.get("text"):
                    existing.append({"from": "plan_agent", "content": msg_item["text"], "phase": "subgraph_thinking"})
                    if _sw:
                        try:
                            _sw({
                                "event_type": "subgraph_thinking",
                                "content": msg_item["text"],
                                "source": "plan_agent",
                            })
                        except Exception:
                            pass
            ws["_subgraph_intermediates"] = existing

        # 报告卡片 done 事件
        report_id = ""
        l2_patch = _extract_layer2_from_patch(patch)
        plan_item = l2_patch.get("current_action_plan") if isinstance(l2_patch.get("current_action_plan"), dict) else {}
        if isinstance(plan_item, dict):
            report_id = _get_item_identity(plan_item, "plan_id", "id")
        if _sw:
            try:
                _sw({"event_type": "report_card", "status": "done", "report_type": "plan", "report_id": report_id})
            except Exception:
                pass

        return ok(output=text, state_patch=patch)

    def _guide_tool(instruction: str) -> ToolResult:
        # 获取 stream writer 用于发射实时展示事件
        try:
            _sw = get_stream_writer()
        except RuntimeError:
            _sw = None

        cfg = _current_config()
        checkpointer = resolve_runtime_checkpointer(cfg)
        subgraph = get_guide_subgraph(checkpointer=checkpointer) if checkpointer is not None else get_guide_subgraph()
        invoke_cfg = build_inner_agent_config(cfg, namespace="guide_subgraph")
        invoke_cfg_fallback = build_inner_agent_config(cfg, namespace="guide_subgraph_retry")
        parent_state = state_getter()
        sub_in = {
            "task_spec": {
                "instruction": instruction,
                "parent_state": dict(parent_state or {}),
            },
            "private_messages": [],
        }

        # 报告卡片 loading 事件
        if _sw:
            try:
                _sw({"event_type": "report_card", "status": "loading", "report_type": "guide"})
            except Exception:
                pass

        pending_payload = _extract_pending_interrupt(subgraph, invoke_cfg)
        active_cfg = invoke_cfg
        if pending_payload is not None:
            logger.info("call_guide_agent pre-invoke relay: relaying pending interrupt from previous trace")
            answer = interrupt(pending_payload)
            sub_out = subgraph.invoke(Command(resume=answer), config=active_cfg)
        else:
            sub_out, active_cfg = _invoke_subgraph_with_fallback_namespace(
                subgraph=subgraph,
                sub_in=sub_in,
                invoke_cfg=invoke_cfg,
                fallback_invoke_cfg=invoke_cfg_fallback,
                tool_name="call_guide_agent",
            )
        while isinstance(sub_out, dict) and "__interrupt__" in sub_out:
            interrupts = sub_out.get("__interrupt__") or []
            payload = interrupts[0].value if interrupts else {}
            answer = interrupt(payload)
            sub_out = subgraph.invoke(Command(resume=answer), config=active_cfg)
        patch = dict(sub_out.get("state_patch") or {}) if isinstance(sub_out, dict) else {}
        final = sub_out.get("final") if isinstance(sub_out, dict) else None
        text = ""
        if isinstance(final, dict) and isinstance(final.get("text"), str):
            text = final["text"].strip()
        text = _build_guide_tool_observation(text, patch)

        # 提取子图中间 AI 消息，累积到 working_state 的临时字段，并通过 stream_writer 实时发射
        intermediate = sub_out.get("intermediate_messages") or [] if isinstance(sub_out, dict) else []
        if intermediate:
            ws = state_getter()
            existing = ws.get("_subgraph_intermediates") or []
            for msg_item in intermediate:
                if isinstance(msg_item, dict) and msg_item.get("text"):
                    existing.append({"from": "guide_agent", "content": msg_item["text"], "phase": "subgraph_thinking"})
                    if _sw:
                        try:
                            _sw({
                                "event_type": "subgraph_thinking",
                                "content": msg_item["text"],
                                "source": "guide_agent",
                            })
                        except Exception:
                            pass
            ws["_subgraph_intermediates"] = existing

        # 报告卡片 done 事件
        report_id = ""
        l2_patch = _extract_layer2_from_patch(patch)
        guides = l2_patch.get("action_guides") if isinstance(l2_patch.get("action_guides"), list) else []
        if guides:
            latest = guides[-1] if isinstance(guides[-1], dict) else {}
            report_id = _get_item_identity(latest, "guide_id", "id")
        if _sw:
            try:
                _sw({"event_type": "report_card", "status": "done", "report_type": "guide", "report_id": report_id})
            except Exception:
                pass

        return ok(output=text, state_patch=patch)

    status_tool = StructuredTool.from_function(
        func=_status_tool,
        name="call_status_agent",
        description="调用现状诊断专家，分析用户与 Crush 的当前关系阶段(L/T模型)、识别致命伤及信息缺口。是所有行动规划(Plan)的前提。",
        args_schema=_SubagentToolInput,
    )
    plan_tool = StructuredTool.from_function(
        func=_plan_tool,
        name="call_plan_agent",
        description="调用战略指挥官，基于现状诊断(Status Analysis)制定宏观行动蓝图、里程碑及交战规则(ROEs)。适用于确定“接下来该怎么做”的战略方向，严禁用于撰写具体话术。",
        args_schema=_SubagentToolInput,
    )
    guide_tool = StructuredTool.from_function(
        func=_guide_tool,
        name="call_guide_agent",
        description="调用战术教官，将战略规划落地为原子化、保姆级的具体执行指南(SOP)或任务卡片。适用于生成具体的聊天话术、朋友圈文案、约会预案及心理按摩。必须在已有 Action Plan 后调用。",
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
    try:
        _stream_writer = get_stream_writer()
    except RuntimeError:
        _stream_writer = None  # 单元测试无 stream 上下文时兜底
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
            live_state=working_state,
            writer=_stream_writer,
        )

    merged_tool_patch = merge_patches({}, supervisor["patches"])
    if merged_tool_patch:
        working_state = merge_state_patch(working_state, merged_tool_patch)

    existing_messages = list(state.get("messages") or [])
    messages_out = existing_messages + list(supervisor["new_messages"])

    pending_responses = list(state.get("pending_responses") or [])
    # 子图中间 AI 消息 → pending_responses（排在 status_brief 和 final 之前）
    subgraph_intermediates = working_state.pop("_subgraph_intermediates", [])
    for item in subgraph_intermediates or []:
        if isinstance(item, dict) and item.get("content"):
            pending_responses.append(item)
    pending_responses.extend(_build_system_task_pending_responses(state, working_state, pending_responses))
    old_status_markdown = _extract_status_report_markdown(state)
    new_status_markdown = _extract_status_report_markdown(working_state)
    if new_status_markdown and new_status_markdown != old_status_markdown:
        status_brief = _build_status_brief(new_status_markdown)
        if status_brief:
            pending_responses.append(
                {
                    "from": "status_agent",
                    "content": status_brief,
                    "phase": "status_brief",
                }
            )

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


def _emit_ai_events(writer, msg: AIMessage) -> None:
    """把 AIMessage 中的 reasoning、文字回复、tool_calls 都 emit 出去。"""
    if writer is None:
        return
    try:
        reasoning = extract_reasoning_content(msg)
        if reasoning:
            writer({"event_type": "reasoning", "content": reasoning})
        text = (msg.content or "").strip()
        if text and not msg.tool_calls:
            writer({"event_type": "ai_intermediate", "content": text, "phase": "intermediate"})
        for tc in (msg.tool_calls or []):
            tool_name = tc["name"]
            writer({
                "event_type": "tool_call",
                "status": "loading",
                "tool_name": tool_name,
                "tool_call_id": tc.get("id", ""),
                "tool_label": get_tool_label(tool_name),
                "args_preview": str(tc.get("args", ""))[:200],
            })
    except Exception:
        pass  # stream writer 失败不能影响主流程


def _emit_tool_done_from_message(
    writer,
    msg: ToolMessage,
    patch: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
) -> None:
    """把工具执行结果 emit 出去，如果当前工具 patch 真正产生新报告则额外 emit report_ready。"""
    if writer is None:
        return
    try:
        result_preview = str(msg.content or "")[:300]
        tool_name = getattr(msg, "name", "") or ""
        writer({
            "event_type": "tool_call",
            "status": "done",
            "tool_name": tool_name,
            "tool_call_id": getattr(msg, "tool_call_id", ""),
            "tool_label": get_tool_label(tool_name),
            "result_summary": result_preview,
        })
        # 只对当前工具真正新增/更新的报告 emit report_ready，避免 plan/guide patch 把旧 status 再次带出来。
        l2 = (patch.get("layer2_memory") or {}) if isinstance(patch, dict) else {}
        if not isinstance(l2, dict):
            return

        old_status = _extract_current_status_report_item(previous_state or {})
        new_status = l2.get("current_status_report") if isinstance(l2.get("current_status_report"), dict) else {}
        old_status_id = _get_item_identity(old_status, "report_id", "id")
        new_status_id = _get_item_identity(new_status, "report_id", "id")
        status_content = _first_non_empty_text(new_status.get("report_content"))
        if new_status and new_status_id and new_status_id != old_status_id and status_content:
            writer({
                "event_type": "report_ready",
                "report_type": "status",
                "report_kind": "status_report",
                "report_id": new_status_id,
                "task_key": f"status_{new_status_id}",
                "content": status_content,
                "preview": str(new_status)[:500],
            })

        old_plan = _extract_current_action_plan_item(previous_state or {})
        new_plan = l2.get("current_action_plan") if isinstance(l2.get("current_action_plan"), dict) else {}
        old_plan_id = _get_item_identity(old_plan, "plan_id", "id")
        new_plan_id = _get_item_identity(new_plan, "plan_id", "id")
        plan_content = _first_non_empty_text(new_plan.get("plan_content"))
        if new_plan and new_plan_id and new_plan_id != old_plan_id and plan_content:
            writer({
                "event_type": "report_ready",
                "report_type": "plan",
                "report_kind": "action_plan",
                "report_id": new_plan_id,
                "task_key": f"plan_{new_plan_id}",
                "content": plan_content,
                "preview": str(new_plan)[:500],
            })

        old_guide_ids = {
            _get_item_identity(guide, "guide_id", "id")
            for guide in _extract_action_guides(previous_state or {})
            if _get_item_identity(guide, "guide_id", "id")
        }
        guides = l2.get("action_guides")
        if isinstance(guides, list):
            for guide in guides:
                if not isinstance(guide, dict):
                    continue
                guide_id = _get_item_identity(guide, "guide_id", "id")
                if not guide_id or guide_id in old_guide_ids:
                    continue
                guide_payload = guide.get("guide") if isinstance(guide.get("guide"), dict) else {}
                guide_content = _first_non_empty_text(
                    guide_payload.get("guide_content"),
                    guide.get("guide_content"),
                )
                if not guide_content:
                    continue
                writer({
                    "event_type": "report_ready",
                    "report_type": "guide",
                    "report_kind": "action_guide",
                    "report_id": guide_id,
                    "task_key": f"guide_{guide_id}",
                    "content": guide_content,
                    "title": _first_non_empty_text(guide.get("title"), guide.get("one_liner")),
                    "preview": str(guide)[:500],
                })
    except Exception:
        pass  # stream writer 失败不能影响主流程
