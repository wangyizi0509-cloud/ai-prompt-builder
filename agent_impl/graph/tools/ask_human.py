from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from agents.tooling.interrupts import build_inquiry_interrupt_payload
from agents.tooling.tool_result import ok
from utils.logger import get_logger


logger = get_logger("ask_human")


def _answers_fingerprint(answers: Any) -> str:
    if not isinstance(answers, dict) or not answers:
        return ""
    canonical = json.dumps(answers, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_question_ids(payload: dict[str, Any]) -> list[str]:
    questions = payload.get("questions")
    if not isinstance(questions, list):
        return []
    return [str(q["id"]) for q in questions if isinstance(q, dict) and q.get("id") is not None]


# 前端支持的题型枚举，必须严格使用这些值，不得自造新 type
QuestionType = Literal[
    "free_input_question",  # 开放式/情感描述/复杂背景 → 文本输入框
    "single_choice",        # 单选（时间/地点/二选一等） → 单选按钮，必须附带 options
    "multiple_choice",      # 多选 → 多选框，必须附带 options
    "screenshot",           # 图片/截图上传（聊天记录、朋友圈、社媒等一律用此值）
]


class InquiryQuestion(BaseModel):
    id: str = Field(description="本卡片内唯一 ID，推荐 q1/q2/q3 或语义化名称如 relationship_duration")
    question: str = Field(description="问题文案，简练直接，不含选项内容")
    type: QuestionType = Field(
        description=(
            "题型，必须是以下之一（不得使用其他值）："
            " free_input_question（开放文字输入）"
            "| single_choice（单选，需附 options）"
            "| multiple_choice（多选，需附 options）"
            "| screenshot（图片/截图上传，适用于聊天记录、朋友圈、社媒等一切需要上传图片的场景）"
        )
    )
    options: list[str] | None = Field(
        default=None,
        description="选项列表，single_choice/multiple_choice 时必填，其他题型留 null",
    )
    is_required: bool = Field(default=False, description="是否必填")
    purpose: str | None = Field(default=None, description="该问题的意图（调试用，不展示给用户）")


class InquiryCard(BaseModel):
    questions: list[InquiryQuestion] = Field(description="问题列表，建议 1-3 个")
    intro: str | None = Field(default="", description="展示给用户的引导语，自然衔接上文")
    reasoning: str | None = Field(default="", description="内部推理自查，说明为何需要这些问题（不展示给用户）")


class AskHumanInput(BaseModel):
    inquiry_card: InquiryCard = Field(description="问题卡片，包含 questions/intro/reasoning")


def _ask_human(inquiry_card: InquiryCard) -> dict:
    # 统一使用标准化后的 inquiry payload，确保 questions.id 可用于前端稳定映射与 resume。
    payload = build_inquiry_interrupt_payload(inquiry_card=inquiry_card.model_dump(exclude_none=True))
    qids = _extract_question_ids(payload)
    logger.info(
        "ask_human interrupt: type=%s, question_count=%s, qids=%s",
        payload.get("type"),
        len(qids),
        qids,
    )
    answers = interrupt(payload)
    if isinstance(answers, dict):
        logger.info(
            "ask_human resumed: answer_keys=%s, fp=%s",
            list(answers.keys()),
            _answers_fingerprint(answers),
        )
    else:
        logger.info("ask_human resumed: answer_type=%s", type(answers).__name__)
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
