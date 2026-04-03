"""Middleware that rescues invalid_tool_calls by repairing malformed JSON args."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langchain.agents.middleware.types import AgentMiddleware, ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


def _repair_ai_message(msg: AIMessage) -> AIMessage:
    """Try to move invalid_tool_calls → tool_calls by fixing their JSON args."""
    if not getattr(msg, "invalid_tool_calls", None):
        return msg
    try:
        from json_repair import repair_json
    except ImportError:
        return msg

    repaired: list[dict[str, Any]] = []
    still_invalid: list[dict[str, Any]] = []
    for tc in msg.invalid_tool_calls:
        try:
            fixed = repair_json(tc.get("args", ""))
            parsed = json.loads(fixed) if isinstance(fixed, str) else fixed
            repaired.append({"id": tc.get("id", ""), "name": tc.get("name", ""), "args": parsed, "type": "tool_call"})
            logger.info("tool_call_repair: rescued invalid tool call '%s'", tc.get("name"))
        except Exception:
            still_invalid.append(tc)

    if not repaired:
        return msg

    return msg.model_copy(
        update={
            "tool_calls": list(msg.tool_calls or []) + repaired,
            "invalid_tool_calls": still_invalid,
        }
    )


class ToolCallRepairMiddleware(AgentMiddleware):
    """Intercepts model output and repairs invalid_tool_calls before the tool node sees them."""

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        result = handler(request)
        if isinstance(result, AIMessage):
            return _repair_ai_message(result)
        if isinstance(result, ModelResponse) and result.result:
            result = ModelResponse(
                result=[_repair_ai_message(m) if isinstance(m, AIMessage) else m for m in result.result],
                structured_response=result.structured_response,
            )
        return result
