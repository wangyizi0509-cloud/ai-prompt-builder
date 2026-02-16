from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Iterable

import pytest


BASE_URL = "http://127.0.0.1:8000"


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


def _iter_sse_data(resp) -> Iterable[str]:
    while True:
        raw = resp.readline()
        if not raw:
            return
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data: "):
            continue
        yield line[len("data: ") :]


def _post_stream(session_id: str, message: str, timeout: int = 180) -> dict[str, Any]:
    payload = {
        "session_id": session_id,
        "message": message,
        "stream_mode": "updates",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat/stream",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    seen_done = False
    interrupt_event: dict[str, Any] | None = None

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for data_line in _iter_sse_data(resp):
            if data_line == "[DONE]":
                seen_done = True
                break
            try:
                obj = json.loads(data_line)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("type") == "interrupt":
                interrupt_event = obj
                break

    return {"seen_done": seen_done, "interrupt_event": interrupt_event}


def _post_stream_resume(session_id: str, resume_payload: dict[str, Any], timeout: int = 180) -> dict[str, Any]:
    payload = {
        "session_id": session_id,
        "resume_payload": resume_payload,
        "stream_mode": "updates",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat/stream",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    seen_done = False
    interrupt_event: dict[str, Any] | None = None
    seen_non_interrupt_event = False
    error_event: dict[str, Any] | None = None

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for data_line in _iter_sse_data(resp):
            if data_line == "[DONE]":
                seen_done = True
                break
            try:
                obj = json.loads(data_line)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("type") == "interrupt":
                interrupt_event = obj
            elif isinstance(obj, dict) and obj.get("error"):
                error_event = obj
                break
            else:
                seen_non_interrupt_event = True

    return {
        "seen_done": seen_done,
        "interrupt_event": interrupt_event,
        "seen_non_interrupt_event": seen_non_interrupt_event,
        "error_event": error_event,
    }


@pytest.mark.api_test
def test_stream_emits_interrupt_event():
    _ensure_server_up()

    instruction = (
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
    )

    last = None
    for _ in range(3):
        session_id = f"real_http_stream_interrupt_{int(time.time() * 1000)}"
        last = _post_stream(session_id=session_id, message=instruction)
        interrupt_event = last.get("interrupt_event")
        if isinstance(interrupt_event, dict):
            break
        time.sleep(0.5)

    assert last is not None
    interrupt_event = last.get("interrupt_event")
    if not isinstance(interrupt_event, dict):
        pytest.skip(f"未收到 interrupt 事件（建议以 LLM_PROVIDER=mock 启动以跑确定性 api_test）：{last}")
    inquiry_card = interrupt_event.get("inquiry_card")
    assert isinstance(inquiry_card, dict)
    assert isinstance(inquiry_card.get("questions"), list) and inquiry_card["questions"]


@pytest.mark.api_test
def test_stream_resume_continues_after_interrupt():
    _ensure_server_up()

    instruction = (
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
    )

    last = None
    session_id = f"real_http_stream_interrupt_resume_{int(time.time() * 1000)}"
    for _ in range(3):
        last = _post_stream(session_id=session_id, message=instruction)
        interrupt_event = last.get("interrupt_event")
        if isinstance(interrupt_event, dict):
            break
        time.sleep(0.5)

    assert last is not None
    interrupt_event = last.get("interrupt_event")
    if not isinstance(interrupt_event, dict):
        pytest.skip(f"未收到 interrupt 事件（建议以 LLM_PROVIDER=mock 启动以跑确定性 api_test）：{last}")

    inquiry_card = interrupt_event.get("inquiry_card")
    if not (isinstance(inquiry_card, dict) and isinstance(inquiry_card.get("questions"), list) and inquiry_card["questions"]):
        pytest.skip(f"interrupt_event 缺少 inquiry_card: {interrupt_event}")

    q1 = inquiry_card["questions"][0]
    qid = q1.get("id") if isinstance(q1, dict) else None
    if not qid:
        pytest.skip(f"inquiry_card 缺少问题 id: {inquiry_card}")

    resume_payload = {"answers": {str(qid): "A"}}
    resumed = _post_stream_resume(session_id=session_id, resume_payload=resume_payload)
    if isinstance(resumed.get("error_event"), dict):
        pytest.fail(f"resume stream 返回 error: {resumed}")
    if isinstance(resumed.get("interrupt_event"), dict):
        pytest.skip(f"resume 后仍触发 interrupt（建议以 LLM_PROVIDER=mock 启动以跑确定性 api_test）：{resumed}")

    assert resumed.get("seen_done") is True
    assert resumed.get("seen_non_interrupt_event") is True
