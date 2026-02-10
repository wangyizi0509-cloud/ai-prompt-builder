from typing import Any


def build_inquiry_interrupt_payload(*, inquiry_card: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = dict(inquiry_card or {})
    payload.setdefault("type", "inquiry_card")
    payload.setdefault("questions", [])
    payload.setdefault("intro", "")
    payload.setdefault("reasoning", "")
    return payload
