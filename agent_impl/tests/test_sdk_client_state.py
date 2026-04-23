from __future__ import annotations


def test_get_thread_state_restores_pending_inquiry_from_interrupt(monkeypatch):
    from api import sdk_client

    class _Threads:
        def get_state(self, thread_id: str):
            assert thread_id == "thread_with_interrupt"
            return {
                "values": {
                    "messages": [{"role": "user", "content": "hi"}],
                    "inquiry_card": None,
                },
                "tasks": [
                    {
                        "interrupts": [
                            {
                                "value": {
                                    "type": "inquiry_card",
                                    "intro": "need more info",
                                    "questions": [
                                        {"id": "q1", "question": "What happened?"}
                                    ],
                                }
                            }
                        ]
                    }
                ],
            }

    class _Client:
        threads = _Threads()

    monkeypatch.setattr(sdk_client, "get_client", lambda: _Client())

    state = sdk_client.get_thread_state("thread_with_interrupt")

    assert isinstance(state, dict)
    inquiry_card = state.get("inquiry_card")
    assert isinstance(inquiry_card, dict)
    assert inquiry_card.get("questions")[0]["id"] == "q1"


def test_get_thread_state_keeps_existing_inquiry_card(monkeypatch):
    from api import sdk_client

    existing_card = {
        "type": "inquiry_card",
        "questions": [{"id": "q_existing", "question": "Existing?"}],
    }

    class _Threads:
        def get_state(self, thread_id: str):
            assert thread_id == "thread_with_existing_card"
            return {
                "values": {
                    "messages": [],
                    "inquiry_card": existing_card,
                },
                "tasks": [
                    {
                        "interrupts": [
                            {
                                "value": {
                                    "type": "inquiry_card",
                                    "questions": [{"id": "q_other", "question": "Other?"}],
                                }
                            }
                        ]
                    }
                ],
            }

    class _Client:
        threads = _Threads()

    monkeypatch.setattr(sdk_client, "get_client", lambda: _Client())

    state = sdk_client.get_thread_state("thread_with_existing_card")

    assert isinstance(state, dict)
    assert state.get("inquiry_card") == existing_card
