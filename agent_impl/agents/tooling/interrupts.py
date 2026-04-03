from typing import Any
from langchain_core.runnables import RunnableConfig

# 前端能渲染的合法题型集合（与 ask_human.py 的 QuestionType Literal 保持同步）
# 旧的截图子类型保留在此集合中，确保历史数据不被错误降级
_VALID_QUESTION_TYPES = frozenset({
    "free_input_question",
    "single_choice",
    "multiple_choice",
    "screenshot",
    # 向后兼容：旧的截图子类型仍视为合法，不被重置为 free_input_question
    "private_chat_screenshot",
    "group_chat_screenshot",
    "moments_screenshot",
    "other_social_media_screenshot",
    "universal_screenshot_analysis",
})


def is_resuming(config: RunnableConfig | None) -> bool:
    """
    统一的 resume 检测函数，供主 agent 和 onboarding agent 使用。
    
    检查 config.configurable.__pregel_resuming 标志位，判断当前是否处于 resume 状态。
    """
    if not isinstance(config, dict):
        return False
    configurable = config.get("configurable")
    if not isinstance(configurable, dict):
        return False
    return bool(configurable.get("__pregel_resuming"))


def _normalize_inquiry_questions(raw_questions: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_questions, list):
        return []

    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for idx, raw_question in enumerate(raw_questions, start=1):
        # LLM 有时把问题传成纯字符串（如 "1. 你的特长是什么？"），兜底转为 dict
        if isinstance(raw_question, str) and raw_question.strip():
            raw_question = {"question": raw_question.strip()}
        if not isinstance(raw_question, dict):
            continue

        question = dict(raw_question)

        raw_id = question.get("id")
        base_id = str(raw_id).strip() if raw_id is not None else ""
        if not base_id:
            base_id = f"q{idx}"

        dedup_id = base_id
        suffix = 2
        while dedup_id in used_ids:
            dedup_id = f"{base_id}_{suffix}"
            suffix += 1
        used_ids.add(dedup_id)

        raw_question_text = question.get("question")
        if isinstance(raw_question_text, str) and raw_question_text.strip():
            question_text = raw_question_text.strip()
        else:
            question_text = f"问题{len(normalized) + 1}"

        question["id"] = dedup_id
        question["question"] = question_text

        # 兜底：type 不在合法集合内时，重置为 free_input_question，避免前端 fallback 渲染
        raw_type = question.get("type")
        if not isinstance(raw_type, str) or raw_type not in _VALID_QUESTION_TYPES:
            question["type"] = "free_input_question"

        normalized.append(question)

    return normalized


def build_inquiry_interrupt_payload(*, inquiry_card: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = dict(inquiry_card or {}) if isinstance(inquiry_card, dict) else {}

    raw_type = payload.get("type")
    payload["type"] = raw_type.strip() if isinstance(raw_type, str) and raw_type.strip() else "inquiry_card"
    payload["questions"] = _normalize_inquiry_questions(payload.get("questions"))
    payload["intro"] = payload.get("intro") if isinstance(payload.get("intro"), str) else ""
    payload["reasoning"] = payload.get("reasoning") if isinstance(payload.get("reasoning"), str) else ""
    return payload
