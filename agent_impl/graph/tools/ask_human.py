from __future__ import annotations

import hashlib
import json
from typing import Any

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
    qids: list[str] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        qid = q.get("id")
        if qid is None:
            continue
        qids.append(str(qid))
    return qids


class AskHumanInput(BaseModel):
    inquiry_card: dict[str, Any] = Field(description="inquiry_card payload，包含 questions/intro/reasoning")


def _ask_human(inquiry_card: dict[str, Any]) -> dict:
    # 统一使用标准化后的 inquiry payload，确保 questions.id 可用于前端稳定映射与 resume。
    payload = build_inquiry_interrupt_payload(inquiry_card=inquiry_card)
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
