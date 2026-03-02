from graph.subgraphs import plan


def test_plan_private_message_merge_preserves_tool_calls_with_empty_content():
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
        {"role": "assistant", "content": "next step"},
    ]

    merged = plan._merge_private_messages(existing, incoming)

    tool_call_msgs = [m for m in merged if isinstance(m, dict) and m.get("tool_calls")]
    tool_result_msgs = [m for m in merged if isinstance(m, dict) and m.get("role") == "tool"]
    assert len(tool_call_msgs) == 1
    assert len(tool_result_msgs) == 1
    assert merged[-1]["content"] == "next step"


def test_plan_private_message_merge_dedupes_by_tool_call_id_for_tool_messages():
    existing = [{"role": "tool", "content": "x", "tool_call_id": "call_1"}]
    incoming = [{"role": "tool", "content": "x", "tool_call_id": "call_1"}]
    merged = plan._merge_private_messages(existing, incoming)
    assert merged == [{"role": "tool", "content": "x", "tool_call_id": "call_1"}]
