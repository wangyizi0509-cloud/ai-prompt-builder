from graph.subgraphs.deferred_human import (
    DEFERRED_HUMAN_PLACEHOLDER,
    build_human_answer_patch,
    create_deferred_ask_human_tool,
    inject_human_answer_into_messages,
)


def test_deferred_ask_human_tool_returns_interrupt_request_without_throwing():
    tool = create_deferred_ask_human_tool()

    result = tool.invoke({"inquiry_card": {"questions": [{"question": "Q1"}]}})

    assert result["output"] == DEFERRED_HUMAN_PLACEHOLDER
    assert isinstance(result.get("deferred_interrupt"), dict)
    assert result["state_patch"]["inquiry_card"]["questions"][0]["id"] == "q1"


def test_inject_human_answer_replaces_placeholder_tool_message():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "name": "ask_human",
                    "id": "tc1",
                    "args": {"inquiry_card": {"questions": [{"id": "q1"}]}},
                    "type": "tool_call",
                }
            ],
        },
        {
            "role": "tool",
            "content": DEFERRED_HUMAN_PLACEHOLDER,
            "tool_call_id": "tc1",
        },
    ]

    updated = inject_human_answer_into_messages(messages, {"q1": "A"})

    assert updated[-1]["tool_call_id"] == "tc1"
    assert updated[-1]["content"] == '{"answers": {"q1": "A"}}'


def test_build_human_answer_patch_keeps_card_and_answers():
    payload = {"questions": [{"id": "q1"}], "type": "inquiry_card"}

    patch = build_human_answer_patch(payload, {"q1": "A"})

    assert patch["inquiry_card"] == payload
    assert patch["inquiry_answers"] == {"q1": "A"}
