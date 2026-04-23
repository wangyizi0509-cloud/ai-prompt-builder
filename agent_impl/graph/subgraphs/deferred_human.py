from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from agents.tooling.interrupts import build_inquiry_interrupt_payload


DEFERRED_HUMAN_PLACEHOLDER = "__deferred_human_input__"


class DeferredAskHumanInput(BaseModel):
    inquiry_card: dict[str, Any] = Field(description="inquiry_card payload，包含 questions/intro/reasoning")


def create_deferred_ask_human_tool() -> BaseTool:
    def _ask_human(inquiry_card: dict[str, Any]) -> dict[str, Any]:
        payload = build_inquiry_interrupt_payload(inquiry_card=inquiry_card)
        return {
            "ok": True,
            "output": DEFERRED_HUMAN_PLACEHOLDER,
            "state_patch": {
                "inquiry_card": payload,
            },
            "deferred_interrupt": payload,
        }

    return StructuredTool.from_function(
        func=_ask_human,
        name="ask_human",
        description="向用户提问并等待回答（由子图节点统一 relay interrupt）。输入为 inquiry_card。",
        args_schema=DeferredAskHumanInput,
        return_direct=True,
    )


def replace_ask_human_tool(tools: list[BaseTool]) -> list[BaseTool]:
    replaced: list[BaseTool] = []
    inserted = False
    for tool in tools or []:
        if getattr(tool, "name", "") == "ask_human":
            if not inserted:
                replaced.append(create_deferred_ask_human_tool())
                inserted = True
            continue
        replaced.append(tool)
    if not inserted:
        replaced.append(create_deferred_ask_human_tool())
    return replaced


def extract_deferred_interrupt(result: Any) -> dict[str, Any]:
    payload = result.get("deferred_interrupt") if isinstance(result, dict) else None
    return dict(payload) if isinstance(payload, dict) else {}


def build_human_answer_tool_content(answer: Any) -> str:
    return json.dumps({"answers": answer}, ensure_ascii=False)


def build_human_answer_patch(payload: dict[str, Any], answer: Any) -> dict[str, Any]:
    return {
        "inquiry_card": dict(payload or {}),
        "inquiry_answers": answer,
    }


def inject_human_answer_into_messages(messages: list[dict], answer: Any) -> list[dict]:
    out: list[dict] = []
    for msg in messages or []:
        out.append(dict(msg) if isinstance(msg, dict) else msg)

    answer_content = build_human_answer_tool_content(answer)
    tool_call_id = _find_last_ask_human_tool_call_id(out)
    if not tool_call_id:
        return out

    for idx in range(len(out) - 1, -1, -1):
        msg = out[idx]
        if not isinstance(msg, dict):
            continue
        if str(msg.get("role") or "") != "tool":
            continue
        if str(msg.get("tool_call_id") or "") != tool_call_id:
            continue
        updated = dict(msg)
        updated["content"] = answer_content
        out[idx] = updated
        return out

    out.append(
        {
            "role": "tool",
            "content": answer_content,
            "tool_call_id": tool_call_id,
        }
    )
    return out


def _find_last_ask_human_tool_call_id(messages: list[dict]) -> str:
    for msg in reversed(messages or []):
        if not isinstance(msg, dict):
            continue
        tool_calls = msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tool_call in reversed(tool_calls):
            if not isinstance(tool_call, dict):
                continue
            if str(tool_call.get("name") or "") != "ask_human":
                continue
            tool_call_id = tool_call.get("id")
            if tool_call_id:
                return str(tool_call_id)
    return ""
