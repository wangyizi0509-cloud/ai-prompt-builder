"""
提问工具 (Ask User Tool)
用于强制模型输出结构化的提问卡片。
"""

import json
from typing import Any

from pydantic import BaseModel, Field
from langchain_core.tools import tool


class AskUserInput(BaseModel):
    questions: list[dict[str, Any]] = Field(
        description="问题列表，每个元素包含 id/type/question/options/is_required/purpose 等字段"
    )
    intro: str = Field(default="", description="引导语（可选）")
    reasoning: str = Field(default="", description="内部原因说明（可选）")


@tool(args_schema=AskUserInput)
def ask_user(
    questions: list[dict[str, Any]],
    intro: str = "",
    reasoning: str = "",
) -> str:
    """向用户提问，收集关键信息后继续。"""
    return json.dumps(
        {
            "action": "ask_user",
            "inquiry_card": {
                "questions": questions,
                "intro": intro,
                "reasoning": reasoning,
            },
        },
        ensure_ascii=False,
    )
