"""
提交类工具 (Submit Tools)

用于将子 Agent 的结构化产出写入 layer2_memory 真源。
仅通过 tool call 触发，content 不承载 JSON。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, Any

from langchain_core.tools import tool
from contextvars import ContextVar

from utils.message_utils import get_msg_role_and_content
from agents.tooling.tool_result import error, ok
from graph.context_types import (
    create_empty_layer2_memory,
    create_status_report_item,
    create_action_plan_item,
    create_action_guide_item,
    is_valid_action_guide_status_transition,
)
from graph.tools.schemas import (
    SubmitStatusReportInput,
    SubmitActionPlanInput,
    SubmitActionGuideInput,
    UpdateGuideStatusInput,
    UpdateGuideContentInput,
    ReturnToMainInput,
)

FEEDBACK_SUMMARY_TAG = "[反馈完成]"

_submit_tools_state: ContextVar[dict | None] = ContextVar("submit_tools_state", default=None)


def set_submit_tools_state(state: dict | None) -> None:
    _submit_tools_state.set(state)


class submit_tools_state_context:
    """Context manager that sets/restores _submit_tools_state using ContextVar tokens.

    Supports nesting: main_agent sets state → subgraph overrides with parent_state
    → on exit, the outer value is restored automatically.

    Usage::

        with submit_tools_state_context(current_state):
            agent_graph.invoke(...)
    """

    def __init__(self, state: dict | None) -> None:
        self._state = state
        self._token = None

    def __enter__(self):
        self._token = _submit_tools_state.set(self._state)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token is not None:
            _submit_tools_state.reset(self._token)
        return False


# ============================================================
# 工具实现（纯输出，不直接写 state）
# ============================================================

@tool(args_schema=SubmitStatusReportInput)
def submit_status_report(
    report_markdown: str,
    stage: str = "",
    stage_description: str = "",
    acr_analysis: dict | None = None,
    key_issues: list[str] | None = None,
    risk_points: list[str] | None = None,
) -> dict:
    """提交或更新现状分析报告"""
    if not report_markdown.strip():
        return error("report_markdown 不能为空")

    state = _submit_tools_state.get()
    if state:
        patch = apply_submit_tool_state_update(
            state,
            "submit_status_report",
            {
                "report_markdown": report_markdown,
                "stage": stage,
                "stage_description": stage_description,
                "acr_analysis": acr_analysis,
                "key_issues": key_issues,
                "risk_points": risk_points,
            },
        )
        return ok("已提交现状分析报告", state_patch=patch)

    layer2_memory = create_empty_layer2_memory()
    new_report_item = create_status_report_item(
        report_content=report_markdown.strip(),
        report_id=0,
        stage=stage or "",
        stage_description=stage_description or "",
        acr_analysis=acr_analysis or {},
        key_issues=key_issues or [],
        risk_points=risk_points or [],
    )
    updated_layer2 = dict(layer2_memory)
    updated_layer2["current_status_report"] = new_report_item
    updated_layer2["last_updated"] = datetime.now().isoformat()
    updated_layer2["version"] = updated_layer2.get("version", 1) + 1
    return ok(
        "已提交现状分析报告",
        state_patch={"layer2_memory": updated_layer2},
    )


@tool(args_schema=SubmitActionPlanInput)
def submit_action_plan(
    goal: str,
    strategy: str,
    phases: list[dict[str, Any]],
    key_principles: list[str],
    summary: str = "",
) -> dict:
    """提交或更新行动规划"""
    if not goal.strip() or not strategy.strip():
        return error("goal 与 strategy 不能为空")

    state = _submit_tools_state.get()
    if state:
        patch = apply_submit_tool_state_update(
            state,
            "submit_action_plan",
            {
                "goal": goal,
                "strategy": strategy,
                "phases": phases,
                "key_principles": key_principles,
                "summary": summary,
            },
        )
        return ok("已提交行动规划", state_patch=patch)

    layer2_memory = create_empty_layer2_memory()
    plan_md = _format_plan_as_markdown(
        {
            "goal": goal,
            "strategy": strategy,
            "phases": phases,
            "key_principles": key_principles,
            "summary": summary,
        }
    )
    new_plan_item = create_action_plan_item(
        plan_content=plan_md,
        plan_id=0,
        goal=goal,
        strategy=strategy,
        phases=phases,
        key_principles=key_principles,
    )
    updated_layer2 = dict(layer2_memory)
    updated_layer2["current_action_plan"] = new_plan_item
    updated_layer2["last_updated"] = datetime.now().isoformat()
    updated_layer2["version"] = updated_layer2.get("version", 1) + 1
    return ok(
        "已提交行动规划",
        state_patch={"layer2_memory": updated_layer2},
    )


@tool(args_schema=SubmitActionGuideInput)
def submit_action_guide(
    title: str,
    one_liner: str,
    guide_markdown: str,
    current_task: str = "",
    steps: list[str] | None = None,
    talking_points: list[str] | None = None,
    dos: list[str] | None = None,
    donts: list[str] | None = None,
    next_milestone: str = "",
) -> dict:
    """提交或更新行动指南"""
    if not title.strip() or not guide_markdown.strip():
        return error("title 与 guide_markdown 不能为空")

    state = _submit_tools_state.get()
    if state:
        patch = apply_submit_tool_state_update(
            state,
            "submit_action_guide",
            {
                "title": title,
                "one_liner": one_liner,
                "guide_markdown": guide_markdown,
                "current_task": current_task,
                "steps": steps,
                "talking_points": talking_points,
                "dos": dos,
                "donts": donts,
                "next_milestone": next_milestone,
            },
        )
        return ok("已提交行动指南", state_patch=patch)

    layer2_memory = create_empty_layer2_memory()
    guide_content = {
        "current_task": current_task or title,
        "steps": steps or [],
        "talking_points": talking_points or [],
        "dos": dos or [],
        "donts": donts or [],
        "next_milestone": next_milestone or "",
        "guide_content": guide_markdown.strip(),
    }
    new_guide_item = create_action_guide_item(
        guide=guide_content,
        guide_id=0,
        status="in_progress",
        title=title,
        one_liner=one_liner,
    )
    updated_layer2 = dict(layer2_memory)
    updated_layer2["action_guides"] = [new_guide_item]
    updated_layer2["last_updated"] = datetime.now().isoformat()
    updated_layer2["version"] = updated_layer2.get("version", 1) + 1
    return ok(
        "已提交行动指南",
        state_patch={"layer2_memory": updated_layer2},
    )


@tool(args_schema=UpdateGuideStatusInput)
def update_guide_status(
    guide_id: str,
    new_status: str,
    reason: str = "",
    feedback_completion_status: str | None = None,
    feedback_completion_detail: str = "",
    feedback_summary: str = "",
) -> dict:
    """更新行动指南状态"""
    if not guide_id.strip() or not new_status.strip():
        return error("guide_id 与 new_status 不能为空")

    state = _submit_tools_state.get()
    if state:
        patch = apply_submit_tool_state_update(
            state,
            "update_guide_status",
            {
                "guide_id": guide_id,
                "new_status": new_status,
                "reason": reason,
                "feedback_completion_status": feedback_completion_status,
                "feedback_completion_detail": feedback_completion_detail,
                "feedback_summary": feedback_summary,
            },
        )
        return ok("已更新行动指南状态", state_patch=patch)

    return ok("已更新行动指南状态", state_patch={})


@tool(args_schema=UpdateGuideContentInput)
def update_guide_content(
    guide_id: str,
    guide_markdown: str,
    title: str = "",
    one_liner: str = "",
    current_task: str = "",
    steps: list[str] | None = None,
    talking_points: list[str] | None = None,
    dos: list[str] | None = None,
    donts: list[str] | None = None,
    next_milestone: str = "",
    update_reason: str = "",
) -> dict:
    """更新行动指南内容（原地更新，保留编号）"""
    if not guide_id.strip():
        return error("guide_id 不能为空")
    if not guide_markdown.strip():
        return error("guide_markdown 不能为空")

    state = _submit_tools_state.get()
    if state:
        patch = apply_submit_tool_state_update(
            state,
            "update_guide_content",
            {
                "guide_id": guide_id,
                "guide_markdown": guide_markdown,
                "title": title,
                "one_liner": one_liner,
                "current_task": current_task,
                "steps": steps,
                "talking_points": talking_points,
                "dos": dos,
                "donts": donts,
                "next_milestone": next_milestone,
                "update_reason": update_reason,
            },
        )
        return ok("已更新行动指南内容", state_patch=patch)

    return ok("已更新行动指南内容", state_patch={})


@tool(args_schema=ReturnToMainInput)
def return_to_main(reason: str = "") -> dict:
    """完成当前任务，将控制权交还给主 Agent"""
    state = _submit_tools_state.get()
    if state:
        patch = apply_submit_tool_state_update(state, "return_to_main", {"reason": reason})
        return ok("已完成任务，转接回主 Agent", state_patch=patch)
    return ok("已完成任务，转接回主 Agent", state_patch={})


# ============================================================
# 反馈辅助函数
# ============================================================

def _find_message_index_by_id(messages: list, message_id: str) -> int:
    if not message_id:
        return -1
    for i, msg in enumerate(messages or []):
        # 支持 dict 类型
        if isinstance(msg, dict):
            if str(msg.get("id") or "") == message_id:
                return i
        else:
            # 支持 LangChain Message 对象
            msg_id = getattr(msg, "id", None)
            if msg_id and str(msg_id) == message_id:
                return i
    return -1


def _build_feedback_qa_history(messages: list, start_message_id: str, keep_tag: str) -> list[dict]:
    """从消息中提取反馈追问历史（保留 user/assistant，忽略工具与总结）"""
    if not messages or not start_message_id:
        return []
    start_idx = _find_message_index_by_id(messages, start_message_id)
    if start_idx < 0:
        return []
    qa_history: list[dict] = []
    for msg in messages[start_idx:]:
        role, content = get_msg_role_and_content(msg)
        if not content:
            continue
        if keep_tag and keep_tag in content:
            continue
        if role in ("assistant", "ai"):
            qa_history.append({"role": "ai", "content": content})
        elif role == "user":
            qa_history.append({"role": "user", "content": content})
    return qa_history


# ============================================================
# 状态更新辅助函数（供 workflow 使用）
# ============================================================

def _get_next_report_id(report_counter: dict, key: str) -> int:
    current = int(report_counter.get(key, 0) or 0)
    return current + 1


def _format_plan_as_markdown(data: dict) -> str:
    parts: list[str] = []
    if data.get("goal"):
        parts.append(f"## 阶段目标\n{data['goal']}\n")
    if data.get("strategy"):
        parts.append(f"## 核心策略\n{data['strategy']}\n")
    if data.get("phases"):
        parts.append("## 分阶段计划\n")
        for i, phase in enumerate(data.get("phases", []), 1):
            name = phase.get("name", f"阶段{i}")
            desc = phase.get("description", "")
            duration = phase.get("duration")
            milestone = phase.get("milestone")
            parts.append(f"### 阶段 {i}: {name}\n")
            if desc:
                parts.append(f"{desc}\n")
            if duration:
                parts.append(f"- 预计时长: {duration}\n")
            if milestone:
                parts.append(f"- 里程碑: {milestone}\n")
    if data.get("key_principles"):
        parts.append("## 关键原则\n")
        for p in data.get("key_principles", []):
            parts.append(f"- {p}\n")
    if data.get("summary"):
        parts.append(f"## 规划总结\n{data.get('summary')}\n")
    return "\n".join(parts)


def apply_submit_tool_state_update(state: dict, tool_name: str, tool_args: dict) -> dict:
    if tool_name == "submit_status_report":
        report_markdown = (tool_args.get("report_markdown") or "").strip()
        if not report_markdown:
            return {}

        layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
        report_counter = state.get("report_counter") or {"status_report": 0, "action_plan": 0, "action_guide": 0}
        new_report_id = _get_next_report_id(report_counter, "status_report")

        old_current = layer2_memory.get("current_status_report")
        history = list(layer2_memory.get("status_report_history", []) or [])
        if old_current:
            history.insert(0, old_current)

        new_report_item = create_status_report_item(
            report_content=report_markdown,
            report_id=new_report_id,
            stage=tool_args.get("stage", "") or "",
            stage_description=tool_args.get("stage_description", "") or "",
            acr_analysis=tool_args.get("acr_analysis") or {},
            key_issues=tool_args.get("key_issues") or [],
            risk_points=tool_args.get("risk_points") or [],
        )

        updated_layer2 = dict(layer2_memory)
        updated_layer2["current_status_report"] = new_report_item
        updated_layer2["status_report_history"] = history
        updated_layer2["last_updated"] = datetime.now().isoformat()
        updated_layer2["version"] = updated_layer2.get("version", 1) + 1

        updated_counter = dict(report_counter)
        updated_counter["status_report"] = new_report_id

        return {
            "layer2_memory": updated_layer2,
            "report_counter": updated_counter,
        }

    if tool_name == "submit_action_plan":
        plan_payload = {
            "goal": tool_args.get("goal", "") or "",
            "strategy": tool_args.get("strategy", "") or "",
            "phases": tool_args.get("phases") or [],
            "key_principles": tool_args.get("key_principles") or [],
            "summary": tool_args.get("summary", "") or "",
        }
        if not plan_payload["goal"] or not plan_payload["strategy"]:
            return {}

        layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
        report_counter = state.get("report_counter") or {"status_report": 0, "action_plan": 0, "action_guide": 0}
        new_plan_id = _get_next_report_id(report_counter, "action_plan")
        plan_markdown = _format_plan_as_markdown(plan_payload)

        old_current = layer2_memory.get("current_action_plan")
        history = list(layer2_memory.get("action_plan_history", []) or [])
        if old_current:
            history.insert(0, old_current)

        new_plan_item = create_action_plan_item(
            plan_content=plan_markdown,
            plan_id=new_plan_id,
            goal=plan_payload["goal"],
            strategy=plan_payload["strategy"],
            phases=plan_payload["phases"],
            key_principles=plan_payload["key_principles"],
        )

        updated_layer2 = dict(layer2_memory)
        updated_layer2["current_action_plan"] = new_plan_item
        updated_layer2["action_plan_history"] = history
        updated_layer2["last_updated"] = datetime.now().isoformat()
        updated_layer2["version"] = updated_layer2.get("version", 1) + 1

        updated_counter = dict(report_counter)
        updated_counter["action_plan"] = new_plan_id

        return {
            "layer2_memory": updated_layer2,
            "report_counter": updated_counter,
        }

    if tool_name == "submit_action_guide":
        title = (tool_args.get("title") or "").strip()
        guide_markdown = (tool_args.get("guide_markdown") or "").strip()
        if not title or not guide_markdown:
            return {}

        layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
        report_counter = state.get("report_counter") or {"status_report": 0, "action_plan": 0, "action_guide": 0}
        new_guide_id = _get_next_report_id(report_counter, "action_guide")

        guide_payload = {
            "current_task": tool_args.get("current_task") or title,
            "steps": tool_args.get("steps") or [],
            "talking_points": tool_args.get("talking_points") or [],
            "dos": tool_args.get("dos") or [],
            "donts": tool_args.get("donts") or [],
            "next_milestone": tool_args.get("next_milestone") or "",
            "guide_content": guide_markdown,
        }

        one_liner = (tool_args.get("one_liner") or "")[:30] or title[:30]
        new_guide_item = create_action_guide_item(
            guide=guide_payload,
            guide_id=new_guide_id,
            title=title,
            one_liner=one_liner,
        )

        all_guides = list(layer2_memory.get("action_guides", []) or [])
        updated_layer2 = dict(layer2_memory)
        updated_layer2["action_guides"] = all_guides + [new_guide_item]
        updated_layer2["last_updated"] = datetime.now().isoformat()
        updated_layer2["version"] = updated_layer2.get("version", 1) + 1

        updated_counter = dict(report_counter)
        updated_counter["action_guide"] = new_guide_id

        return {
            "layer2_memory": updated_layer2,
            "report_counter": updated_counter,
        }

    if tool_name == "update_guide_status":
        guide_id = (tool_args.get("guide_id") or "").strip()
        new_status = (tool_args.get("new_status") or "").strip()
        reason = (tool_args.get("reason") or "").strip()
        feedback_completion_status = tool_args.get("feedback_completion_status")
        feedback_completion_detail = (tool_args.get("feedback_completion_detail") or "").strip()
        feedback_summary = (tool_args.get("feedback_summary") or "").strip()
        if not guide_id or not new_status:
            return {}

        layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
        all_guides = list(layer2_memory.get("action_guides", []) or [])
        did_update = False

        for i, g in enumerate(all_guides):
            if not isinstance(g, dict):
                continue
            if str(g.get("id") or "") != guide_id:
                continue

            current_status = str(g.get("status") or "pending")
            if not is_valid_action_guide_status_transition(current_status, new_status):
                return {}

            updated = dict(g)
            updated["status"] = new_status
            if new_status in ("completed", "cancelled", "expired"):
                updated["completed_at"] = datetime.now().isoformat()
            if reason:
                if not updated.get("one_liner"):
                    updated["one_liner"] = reason
                if new_status in ("cancelled", "expired") and not updated.get("summary"):
                    updated["summary"] = reason

            if feedback_completion_status or feedback_completion_detail or feedback_summary:
                feedback_data = dict(updated.get("feedback_data") or {})
                if feedback_completion_status:
                    feedback_data["completion_status"] = feedback_completion_status
                if feedback_completion_detail:
                    feedback_data["completion_detail"] = feedback_completion_detail
                if feedback_summary:
                    feedback_data["feedback_summary"] = feedback_summary

                feedback_mode = state.get("feedback_mode") or {}
                start_message_id = feedback_mode.get("start_message_id")
                qa_history = _build_feedback_qa_history(
                    state.get("messages", []),
                    start_message_id,
                    FEEDBACK_SUMMARY_TAG,
                )
                if qa_history:
                    feedback_data["qa_history"] = qa_history

                updated["feedback_data"] = feedback_data
                if feedback_completion_detail and not updated.get("user_feedback"):
                    updated["user_feedback"] = feedback_completion_detail

            all_guides[i] = updated
            did_update = True
            break

        if not did_update:
            return {}

        updated_layer2 = dict(layer2_memory)
        updated_layer2["action_guides"] = all_guides
        updated_layer2["last_updated"] = datetime.now().isoformat()
        updated_layer2["version"] = updated_layer2.get("version", 1) + 1

        updates = {
            "layer2_memory": updated_layer2,
        }

        if feedback_summary or feedback_completion_status or feedback_completion_detail:
            compressions = list(state.get("feedback_compressions") or [])
            feedback_mode = state.get("feedback_mode") or {}
            start_message_id = feedback_mode.get("start_message_id")
            if start_message_id:
                compressions.append({
                    "guide_id": guide_id,
                    "start_message_id": start_message_id,
                    "keep_tag": FEEDBACK_SUMMARY_TAG,
                })
            updates["feedback_compressions"] = compressions
            updates["feedback_mode"] = None
            updates["feedback_status"] = "completed"
            updates["feedback_question"] = None

        return updates

    if tool_name == "update_guide_content":
        guide_id = (tool_args.get("guide_id") or "").strip()
        guide_markdown = (tool_args.get("guide_markdown") or "").strip()
        if not guide_id or not guide_markdown:
            return {}

        layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
        all_guides = list(layer2_memory.get("action_guides", []) or [])
        did_update = False
        updated_guide_num = 0

        for i, g in enumerate(all_guides):
            if not isinstance(g, dict):
                continue
            if str(g.get("id") or "") != guide_id:
                continue

            # 找到目标指南，进行原地更新
            updated = dict(g)
            old_version = int(updated.get("version", 1) or 1)
            
            # 保存旧版本到 content_history
            content_history = list(updated.get("content_history", []) or [])
            old_snapshot = {
                "version": old_version,
                "guide": updated.get("guide", {}),
                "title": updated.get("title", ""),
                "one_liner": updated.get("one_liner"),
                "updated_at": datetime.now().isoformat(),
                "update_reason": (tool_args.get("update_reason") or "").strip(),
            }
            content_history.append(old_snapshot)
            updated["content_history"] = content_history

            # 更新版本号
            updated["version"] = old_version + 1

            # 更新标题（如果提供了新标题）
            new_title = (tool_args.get("title") or "").strip()
            if new_title:
                updated["title"] = new_title

            # 更新一句话摘要（如果提供了）
            new_one_liner = (tool_args.get("one_liner") or "").strip()
            if new_one_liner:
                updated["one_liner"] = new_one_liner

            # 构建新的 guide 内容
            new_guide = {
                "current_task": (tool_args.get("current_task") or "").strip() or updated.get("guide", {}).get("current_task", ""),
                "steps": tool_args.get("steps") or [],
                "talking_points": tool_args.get("talking_points") or [],
                "dos": tool_args.get("dos") or [],
                "donts": tool_args.get("donts") or [],
                "next_milestone": (tool_args.get("next_milestone") or "").strip(),
                "guide_content": guide_markdown,
            }
            updated["guide"] = new_guide

            all_guides[i] = updated
            did_update = True
            updated_guide_num = int(updated.get("guide_id", 0) or 0)
            break

        if not did_update:
            return {}

        updated_layer2 = dict(layer2_memory)
        updated_layer2["action_guides"] = all_guides
        updated_layer2["last_updated"] = datetime.now().isoformat()
        updated_layer2["version"] = updated_layer2.get("version", 1) + 1

        return {
            "layer2_memory": updated_layer2,
        }

    return {}


# ============================================================
# 工具名称常量
# ============================================================

SUBMIT_TOOL_NAMES = {
    "submit_status_report",
    "submit_action_plan",
    "submit_action_guide",
    "update_guide_status",
    "update_guide_content",
}


def is_submit_tool(tool_name: str) -> bool:
    return tool_name in SUBMIT_TOOL_NAMES
