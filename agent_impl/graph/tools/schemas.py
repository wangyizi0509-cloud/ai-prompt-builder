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


def tool_response(success: bool, message: str, data: Optional[Any] = None) -> str:
    payload = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return json.dumps(payload, ensure_ascii=False)


def tool_error_response(message: str, data: Optional[Any] = None) -> str:
    return tool_response(False, message, data)
