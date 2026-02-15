from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from agents.tooling.interrupts import build_inquiry_interrupt_payload
from agents.tooling.tool_result import ok


class AskHumanInput(BaseModel):
    inquiry_card: dict[str, Any] = Field(description="inquiry_card payload，包含 questions/intro/reasoning")


def _ask_human(inquiry_card: dict[str, Any]) -> dict:
    # 统一使用标准化后的 inquiry payload，确保 questions.id 可用于前端稳定映射与 resume。
    payload = build_inquiry_interrupt_payload(inquiry_card=inquiry_card)
    answers = interrupt(payload)
    return ok(
        output=json.dumps({"answers": answers}, ensure_ascii=False),
        state_patch={
            "inquiry_card": payload,
            "inquiry_answers": answers,
        },
    )


ask_human = StructuredTool.from_function(
    func=_ask_human,
    name="ask_human",
    description="向用户提问并等待回答（使用 interrupt）。输入为 inquiry_card。",
    args_schema=AskHumanInput,
)
