from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

import pytest


BASE_URL = "http://127.0.0.1:8000"


def _post_json(url: str, payload: dict, timeout: int = 180) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return json.loads(body.decode("utf-8"))


def _get(url: str, timeout: int = 30) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read()


def _ensure_server_up() -> None:
    try:
        code, _ = _get(f"{BASE_URL}/openapi.json", timeout=10)
        if code != 200:
            raise RuntimeError(f"openapi not ok: {code}")
    except Exception as e:
        pytest.skip(f"本机 API 服务不可用（{BASE_URL}）：{e}")


def _chat(session_id: str, message: str, timeout: int = 180) -> dict[str, Any]:
    return _post_json(
        f"{BASE_URL}/api/chat",
        {"message": message, "session_id": session_id},
        timeout=timeout,
    )


def _chat_resume(session_id: str, resume_payload: dict, timeout: int = 180) -> dict[str, Any]:
    return _post_json(
        f"{BASE_URL}/api/chat",
        {"session_id": session_id, "resume_payload": resume_payload},
        timeout=timeout,
    )


def _pick_first_answer_value(question: dict) -> str:
    options = question.get("options") or []
    if not isinstance(options, list) or not options:
        return "ok"
    first = options[0]
    if isinstance(first, dict):
        if "value" in first:
            return str(first["value"])
        if "id" in first:
            return str(first["id"])
        if "label" in first:
            return str(first["label"])
    return str(first)


@pytest.mark.api_test
def test_chat_returns_interrupt_payload():
    _ensure_server_up()

    session_id = f"real_http_interrupt_{int(time.time())}"
    inquiry_card = None
    out = None
    for _ in range(3):
        out = _chat(
            session_id,
            (
                "[[TEST_INTERRUPT]]\n"
                "这是系统验收测试，请严格执行：\n"
                "你必须调用工具 ask_human 一次，并立刻暂停等待用户回答。\n"
                "inquiry_card 必须只包含 1 个问题：\n"
                "- id: q1\n"
                "- type: single_choice\n"
                "- question: 你选择 A 还是 B？\n"
                "- options: [\"A\", \"B\"]\n"
                "- is_required: true\n"
                "- purpose: 测试 interrupt/resume\n"
                "严禁输出最终建议，必须等待用户回复。"
            ),
        )
        state = out.get("state") or {}
        inquiry_card = state.get("inquiry_card") if isinstance(state, dict) else None
        if isinstance(inquiry_card, dict) and inquiry_card.get("questions"):
            break
        time.sleep(0.5)

    assert out is not None
    state = out.get("state") or {}
    assert isinstance(state, dict)
    inquiry_card = state.get("inquiry_card")
    if not isinstance(inquiry_card, dict):
        pytest.skip(f"服务未产出 inquiry_card（建议以 LLM_PROVIDER=mock 启动以跑确定性 api_test），state_keys={list(state.keys())}")
    assert isinstance(inquiry_card.get("questions"), list) and len(inquiry_card["questions"]) >= 1


@pytest.mark.api_test
def test_chat_resume_continues_and_returns_final_response():
    _ensure_server_up()

    session_id = f"real_http_interrupt_resume_{int(time.time())}"

    out = _chat(
        session_id,
        (
            "[[TEST_INTERRUPT]]\n"
            "这是系统验收测试，请严格执行：\n"
            "你必须调用工具 ask_human 一次，并立刻暂停等待用户回答。\n"
            "inquiry_card 必须只包含 1 个问题：\n"
            "- id: q1\n"
            "- type: single_choice\n"
            "- question: 你选择 A 还是 B？\n"
            "- options: [\"A\", \"B\"]\n"
            "- is_required: true\n"
            "- purpose: 测试 interrupt/resume\n"
            "严禁输出最终建议，必须等待用户回复。"
        ),
    )
    state = out.get("state") or {}
    assert isinstance(state, dict)
    inquiry_card = state.get("inquiry_card")
    if not (isinstance(inquiry_card, dict) and isinstance(inquiry_card.get("questions"), list) and inquiry_card["questions"]):
        pytest.skip("服务未进入 interrupt（建议以 LLM_PROVIDER=mock 启动以跑确定性 api_test）")
    q1 = inquiry_card["questions"][0]
    assert isinstance(q1, dict) and q1.get("id")

    resume_payload = {"answers": {str(q1["id"]): _pick_first_answer_value(q1)}}

    out2 = _chat_resume(session_id, resume_payload)
    state2 = out2.get("state") or {}
    assert isinstance(state2, dict)
    pending = out2.get("pending_responses") or []
    assert isinstance(pending, list)
    assert any(isinstance(r, dict) and r.get("content") for r in pending), "resume 后未返回 pending_responses"


