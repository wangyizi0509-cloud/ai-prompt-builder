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
    tool_response,
    tool_error_response,
)


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
) -> str:
    """提交或更新现状分析报告（写入真源由 workflow 统一处理）"""
    if not report_markdown.strip():
        return tool_error_response("report_markdown 不能为空")
    return tool_response(True, "已提交现状分析报告")


@tool(args_schema=SubmitActionPlanInput)
def submit_action_plan(
    goal: str,
    strategy: str,
    phases: list[dict[str, Any]],
    key_principles: list[str],
    summary: str = "",
) -> str:
    """提交或更新行动规划（写入真源由 workflow 统一处理）"""
    if not goal.strip() or not strategy.strip():
        return tool_error_response("goal 与 strategy 不能为空")
    return tool_response(True, "已提交行动规划")


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
) -> str:
    """提交或更新行动指南（写入真源由 workflow 统一处理）"""
    if not title.strip() or not guide_markdown.strip():
        return tool_error_response("title 与 guide_markdown 不能为空")
    return tool_response(True, "已提交行动指南")


@tool(args_schema=UpdateGuideStatusInput)
def update_guide_status(
    guide_id: str,
    new_status: str,
    reason: str = "",
) -> str:
    """更新行动指南状态（写入真源由 workflow 统一处理）"""
    if not guide_id.strip() or not new_status.strip():
        return tool_error_response("guide_id 与 new_status 不能为空")
    return tool_response(True, "已更新行动指南状态")


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
) -> str:
    """更新行动指南内容（原地更新，保留编号，写入真源由 workflow 统一处理）"""
    if not guide_id.strip():
        return tool_error_response("guide_id 不能为空")
    if not guide_markdown.strip():
        return tool_error_response("guide_markdown 不能为空")
    return tool_response(True, "已更新行动指南内容")


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
            "status_report": report_markdown,
            "status_report_id": new_report_id,
            "_submit_result": {
                "type": "status_report",
                "report_id": new_report_id,
            },
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
            "action_plan": plan_markdown,
            "action_plan_id": new_plan_id,
            "_submit_result": {
                "type": "action_plan",
                "plan_id": new_plan_id,
            },
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
            status="pending",
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
            "action_guides": updated_layer2["action_guides"],
            "action_guide": guide_markdown,
            "_submit_result": {
                "type": "action_guide",
                "guide_id": new_guide_id,
                "guide_uid": new_guide_item.get("id"),
            },
        }

    if tool_name == "update_guide_status":
        guide_id = (tool_args.get("guide_id") or "").strip()
        new_status = (tool_args.get("new_status") or "").strip()
        reason = (tool_args.get("reason") or "").strip()
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

            all_guides[i] = updated
            did_update = True
            break

        if not did_update:
            return {}

        updated_layer2 = dict(layer2_memory)
        updated_layer2["action_guides"] = all_guides
        updated_layer2["last_updated"] = datetime.now().isoformat()
        updated_layer2["version"] = updated_layer2.get("version", 1) + 1

        return {
            "layer2_memory": updated_layer2,
            "action_guides": updated_layer2["action_guides"],
            "_submit_result": {
                "type": "guide_status_update",
                "guide_uid": guide_id,
                "new_status": new_status,
            },
        }

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
            "action_guides": updated_layer2["action_guides"],
            "_submit_result": {
                "type": "guide_content_update",
                "guide_uid": guide_id,
                "guide_id": updated_guide_num,
            },
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
