from __future__ import annotations

from typing import Any

from utils.message_utils import get_msg_role_and_content


def build_model_messages(
    state: dict,
    user_message: str,
    *,
    max_messages: int = 25,
) -> list[dict]:
    messages: list[dict[str, Any]] = []

    for m in state.get("messages") or []:
        role, content = get_msg_role_and_content(m)
        if not role:
            continue
        messages.append({"role": role, "content": content or ""})

    if user_message and user_message.strip():
        messages.append({"role": "user", "content": user_message})

    if max_messages > 0 and len(messages) > max_messages:
        messages = messages[-max_messages:]

    return list(messages)


def build_subagent_input(
    state: dict,
    *,
    max_messages: int = 25,
) -> dict:
    layer2 = state.get("layer2_memory") or {}
    layer3 = state.get("layer3_memory") or {}
    user_message = state.get("user_message") or ""

    return {
        "layer2": dict(layer2),
        "layer3": dict(layer3),
        "messages": build_model_messages(state, user_message, max_messages=max_messages),
    }

