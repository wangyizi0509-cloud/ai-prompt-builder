from agents.tooling.context import build_model_messages, build_subagent_input


def test_build_model_messages_truncates_to_25():
    state = {"messages": [{"role": "user", "content": f"m{i}"} for i in range(30)]}
    messages = build_model_messages(state, "final", max_messages=25)
    assert len(messages) == 25
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "final"
    assert messages[0]["content"] == "m6"


def test_build_subagent_input_contains_layer2_layer3():
    state = {"messages": []}
    payload = build_subagent_input(state, max_messages=25)
    assert "layer2" in payload
    assert "layer3" in payload
    assert payload["layer2"] == {}
    assert payload["layer3"] == {}
    assert "messages" in payload
