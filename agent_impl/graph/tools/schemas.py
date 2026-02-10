"""
工具输入/输出 Schema 与统一错误结构
"""

from __future__ import annotations

import json
from typing import Literal, Optional, Any

from pydantic import BaseModel, Field


class LoadSkillInput(BaseModel):
    skill_id: str = Field(
        description="Skill ID（由当前 Agent 的权限决定可用范围）。工具仅返回指令，不会直接给出问题或回复内容。"
    )


class TaskManagerInput(BaseModel):
    action: Literal["create", "switch", "complete", "append_note"] = Field(
        description="操作类型（任务状态变更的主路径）"
    )
    task_id: str = Field(
        default="",
        description="任务 ID（create: 新 ID；其他操作：目标 ID；空则默认当前任务）",
    )
    title: str = Field(default="", description="任务标题（仅 create 时需要）")
    summary: str = Field(
        default="",
        description="任务摘要（create 时可选）或完成总结（complete 时必填）",
    )
    note: str = Field(default="", description="思考笔记（仅 append_note 时需要）")


class ContextLoaderInput(BaseModel):
    action: Literal["load", "bind", "unbind", "refresh"] = Field(
        description="操作：load=仅查看不绑定，bind=绑定到当前任务用于跨轮次注入，unbind=解绑，refresh=刷新过期时间"
    )
    context_type: Literal[
        "action_guide",
        "status_report",
        "action_plan",
        "crush_chat",
        "history_snippet",
        "custom",
    ] = Field(description="上下文类型")
    context_id: str = Field(description="上下文 ID")
    expire_at: str = Field(default="", description="过期时间 ISO 格式（bind/refresh 时可选）")


class SubmitStatusReportInput(BaseModel):
    report_markdown: str = Field(description="现状分析报告 Markdown 内容")
    stage: str = Field(default="", description="关系阶段（可选）")
    stage_description: str = Field(default="", description="阶段描述（可选）")
    acr_analysis: dict = Field(default_factory=dict, description="A/C/R 维度分析（可选）")
    key_issues: list[str] = Field(default_factory=list, description="核心问题列表（可选）")
    risk_points: list[str] = Field(default_factory=list, description="风险点列表（可选）")


class SubmitActionPlanInput(BaseModel):
    goal: str = Field(description="阶段性目标")
    strategy: str = Field(description="核心策略方向")
    phases: list[dict] = Field(default_factory=list, description="分阶段计划")
    key_principles: list[str] = Field(default_factory=list, description="关键原则列表")
    summary: str = Field(default="", description="规划总结（可选）")


class SubmitActionGuideInput(BaseModel):
    title: str = Field(description="指南标题")
    one_liner: str = Field(description="一句话摘要")
    guide_markdown: str = Field(description="完整行动指南 Markdown")
    current_task: str = Field(default="", description="当前任务（可选）")
    steps: list[str] = Field(default_factory=list, description="执行步骤（可选）")
    talking_points: list[str] = Field(default_factory=list, description="话术要点（可选）")
    dos: list[str] = Field(default_factory=list, description="该做的（可选）")
    donts: list[str] = Field(default_factory=list, description="不该做的（可选）")
    next_milestone: str = Field(default="", description="下一个里程碑（可选）")


class UpdateGuideStatusInput(BaseModel):
    guide_id: str = Field(description="指南唯一 ID（ActionGuideItem.id）")
    new_status: Literal[
        "pending",
        "in_progress",
        "completed",
        "cancelled",
        "paused",
        "expired",
    ] = Field(description="目标状态")
    reason: str = Field(default="", description="更新原因（可选）")
    feedback_completion_status: Optional[
        Literal["success", "partial", "failed", "abandoned", "other"]
    ] = Field(default=None, description="反馈完成状态（可选）")
    feedback_completion_detail: str = Field(default="", description="反馈完成详情（可选）")
    feedback_summary: str = Field(default="", description="反馈总结（可选）")


class UpdateGuideContentInput(BaseModel):
    """更新行动指南内容（原地更新，保留编号）"""
    guide_id: str = Field(description="指南唯一 ID（ActionGuideItem.id）")
    title: str = Field(default="", description="新标题（可选，不填则保留原标题）")
    one_liner: str = Field(default="", description="新一句话摘要（可选）")
    guide_markdown: str = Field(description="更新后的完整行动指南 Markdown")
    current_task: str = Field(default="", description="当前任务（可选）")
    steps: list[str] = Field(default_factory=list, description="执行步骤（可选）")
    talking_points: list[str] = Field(default_factory=list, description="话术要点（可选）")
    dos: list[str] = Field(default_factory=list, description="该做的（可选）")
    donts: list[str] = Field(default_factory=list, description="不该做的（可选）")
    next_milestone: str = Field(default="", description="下一个里程碑（可选）")
    update_reason: str = Field(default="", description="更新原因（用于历史追溯）")


class ReturnToMainInput(BaseModel):
    reason: str = Field(default="", description="转接回主 Agent 的原因（可选）")


class EndTurnInput(BaseModel):
    """结束本轮对话，不输出任何内容"""
    reason: str = Field(default="", description="结束本轮的原因（可选，仅用于日志/调试）")


# =========================
# 委派工具输入（Main -> 子 Agent）
# =========================

class DelegateInstructionInput(BaseModel):
    instruction: str = Field(
        description="默认只写\"目标\"，最多2行，不要罗列子agent应该分析和书写的内容，它们都有自己的prompt，它们知道该写啥"
    )


class DelegateToStatusInput(DelegateInstructionInput):
    """委派给 status_agent 的输入"""


class DelegateToPlanInput(DelegateInstructionInput):
    """委派给 plan_agent 的输入"""


class DelegateToGuideInput(DelegateInstructionInput):
    """委派给 guide_agent 的输入"""


class DelegateForFeedbackInput(BaseModel):
    """发起行动反馈模式（用于打开反馈弹窗）"""
    guide_id: str = Field(description="指南唯一 ID（ActionGuideItem.id）")
    prefilled_status: Literal["success", "partial", "failed", "abandoned", "other", "completed"] | None = Field(
        default=None,
        description="预填完成状态（可选）",
    )
    prefilled_detail: str = Field(default="", description="预填完成详情（可选）")


def tool_response(success: bool, message: str, data: Optional[Any] = None) -> str:
    payload = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return json.dumps(payload, ensure_ascii=False)


def tool_error_response(message: str, data: Optional[Any] = None) -> str:
    return tool_response(False, message, data)
