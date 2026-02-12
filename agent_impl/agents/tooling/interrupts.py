from typing import Any


def _normalize_inquiry_questions(raw_questions: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_questions, list):
        return []

    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for idx, raw_question in enumerate(raw_questions, start=1):
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
