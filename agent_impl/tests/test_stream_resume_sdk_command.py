from __future__ import annotations

import json

import pytest
from fastapi import BackgroundTasks


@pytest.mark.asyncio
async def test_stream_resume_uses_sdk_command(monkeypatch):
    from api.stream import StreamChatRequest, chat_stream
    from api import sdk_client as sdk_client_module

    captured: dict = {}

    async def _fake_ensure_thread_exists(session_id: str, user_id: str = None) -> str:
        return "thread_test_stream_resume"

    def _fake_get_thread_state(thread_id: str):
        return {"onboarding_turn_count": 0}

    def _fake_run_assistant(thread_id: str, input_state=None, stream_mode: str = "values", *, command: dict | None = None):
        captured["thread_id"] = thread_id
        captured["input_state"] = input_state
        captured["stream_mode"] = stream_mode
        captured["command"] = command
        yield {"data": {"messages": [], "ok": True}}

    monkeypatch.setattr(sdk_client_module, "ensure_thread_exists", _fake_ensure_thread_exists)
    monkeypatch.setattr(sdk_client_module, "get_thread_state", _fake_get_thread_state)
    monkeypatch.setattr(sdk_client_module, "run_assistant", _fake_run_assistant)

    resume_payload = {"answers": {"q1": "A"}}
    request = StreamChatRequest(session_id="sess", resume_payload=resume_payload, stream_mode="updates")
    resp = await chat_stream(request, BackgroundTasks(), current_user={"user_id": "u1"})

    seen_done = False
    async for chunk in resp.body_iterator:
        text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
        if "data: [DONE]" in text:
            seen_done = True
            break
        if text.startswith("data: "):
            payload = text[len("data: ") :].strip()
            if payload and payload != "[DONE]":
                obj = json.loads(payload)
                assert not (isinstance(obj, dict) and obj.get("error"))

    assert seen_done is True
    assert captured.get("thread_id") == "thread_test_stream_resume"
    assert captured.get("input_state") is None
    assert captured.get("command") == {"resume": resume_payload}
