from __future__ import annotations

import asyncio

import pytest
from fastapi import BackgroundTasks


def test_chat_synthetic_resume_when_no_pending_interrupt(monkeypatch):
    from api.chat import ChatRequest, chat as chat_endpoint
    from api import sdk_client as sdk_client_module

    captured: dict = {}

    async def _fake_ensure_thread_exists(session_id: str, user_id: str = None) -> str:
        return "thread_test_chat_synth_resume"

    def _fake_get_thread_state(thread_id: str):
        return {
            "messages": [{"role": "user", "content": "hi"}],
            "inquiry_card": {"questions": [{"id": "q1", "question": "Q1", "options": ["A", "B"]}]},
        }

    def _fake_thread_has_pending_interrupt(thread_id: str) -> bool:
        return False

    def _fake_run_assistant(thread_id: str, input_state=None, stream_mode: str = "values", *, command: dict | None = None):
        captured["thread_id"] = thread_id
        captured["input_state"] = input_state
        captured["command"] = command
        yield {"data": {"pending_responses": [{"content": "ok"}]}}

    monkeypatch.setattr(sdk_client_module, "ensure_thread_exists", _fake_ensure_thread_exists)
    monkeypatch.setattr(sdk_client_module, "get_thread_state", _fake_get_thread_state)
    monkeypatch.setattr(sdk_client_module, "thread_has_pending_interrupt", _fake_thread_has_pending_interrupt)
    monkeypatch.setattr(sdk_client_module, "run_assistant", _fake_run_assistant)

    req = ChatRequest(session_id="sess", resume_payload={"answers": {"q1": "A"}})
    out = asyncio.run(chat_endpoint(req, BackgroundTasks(), current_user={"user_id": "u1"}))

    assert captured.get("thread_id") == "thread_test_chat_synth_resume"
    assert captured.get("command") is None
    assert isinstance(captured.get("input_state"), dict)
    assert (captured["input_state"].get("user_message") or "").strip()

    state = out.get("state") if isinstance(out, dict) else None
    assert isinstance(state, dict)
    inquiry_card = state.get("inquiry_card")
    assert isinstance(inquiry_card, dict)
    assert inquiry_card.get("questions") == []
