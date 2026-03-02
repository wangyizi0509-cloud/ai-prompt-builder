from graph.subgraphs import guide, status


def test_status_merge_preserves_tool_calls_with_empty_content():
    existing = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "name": "ask_human", "args": {"inquiry_card": {"questions": []}}}],
        },
        {"role": "tool", "content": "{\"answers\": {\"q1\": \"A\"}}", "tool_call_id": "call_1"},
    ]
    incoming = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "name": "ask_human", "args": {"inquiry_card": {"questions": []}}}],
        },
        {"role": "tool", "content": "{\"answers\": {\"q1\": \"A\"}}", "tool_call_id": "call_1"},
        {"role": "assistant", "content": "next"},
    ]
    merged = status._merge_private_messages(existing, incoming)
    assert len([m for m in merged if isinstance(m, dict) and m.get("tool_calls")]) == 1
    assert len([m for m in merged if isinstance(m, dict) and m.get("role") == "tool"]) == 1
    assert merged[-1]["content"] == "next"


def test_guide_merge_preserves_tool_calls_with_empty_content():
    existing = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "name": "ask_human", "args": {"inquiry_card": {"questions": []}}}],
        },
        {"role": "tool", "content": "{\"answers\": {\"q1\": \"A\"}}", "tool_call_id": "call_1"},
    ]
    incoming = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call_1", "name": "ask_human", "args": {"inquiry_card": {"questions": []}}}],
        },
        {"role": "tool", "content": "{\"answers\": {\"q1\": \"A\"}}", "tool_call_id": "call_1"},
        {"role": "assistant", "content": "next"},
    ]
    merged = guide._merge_private_messages(existing, incoming)
    assert len([m for m in merged if isinstance(m, dict) and m.get("tool_calls")]) == 1
    assert len([m for m in merged if isinstance(m, dict) and m.get("role") == "tool"]) == 1
    assert merged[-1]["content"] == "next"


def test_status_merge_dedupes_tool_messages_by_tool_call_id():
    merged = status._merge_private_messages(
        [{"role": "tool", "content": "x", "tool_call_id": "call_1"}],
        [{"role": "tool", "content": "x", "tool_call_id": "call_1"}],
    )
    assert merged == [{"role": "tool", "content": "x", "tool_call_id": "call_1"}]


def test_guide_merge_dedupes_tool_messages_by_tool_call_id():
    merged = guide._merge_private_messages(
        [{"role": "tool", "content": "x", "tool_call_id": "call_1"}],
        [{"role": "tool", "content": "x", "tool_call_id": "call_1"}],
    )
    assert merged == [{"role": "tool", "content": "x", "tool_call_id": "call_1"}]
