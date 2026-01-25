import pytest

from tests.conftest import create_test_state


def test_skill_tools_sets_pending_action_for_inquiry(monkeypatch):
    state = create_test_state("我想追一个女生")
    state["messages"].append({
        "role": "assistant",
        "tool_calls": [{
            "id": "tc_1",
            "name": "load_skill",
            "args": {"skill_id": "inquiry"},
        }],
    })

    from graph.workflow import skill_tools_node
    from langgraph.prebuilt import ToolNode

    def _noop_invoke(self, state, config=None):
        return {
            "messages": [{
                "role": "tool",
                "content": "{}",
                "tool_call_id": "tc_1",
                "name": "ask_user",
            }],
        }

    monkeypatch.setattr(ToolNode, "invoke", _noop_invoke)

    out = skill_tools_node(state)

    assert out.get("_pending_action") == "inquiry"


@pytest.mark.skip(reason="需要真实 API 或更精细的 Mock 才能验证强制 tool_choice")
def test_main_agent_forces_ask_user_after_inquiry_skill():
    pass


def test_ask_user_tool_updates_state(monkeypatch):
    state = create_test_state("测试")
    state["current_agent"] = "main_agent"
    state["messages"].append({
        "role": "assistant",
        "tool_calls": [{
            "id": "tc_1",
            "name": "ask_user",
            "args": {
                "questions": [{
                    "id": "q1",
                    "type": "free_input_question",
                    "question": "你们认识多久了？",
                }],
                "intro": "为了更好地帮你，我想了解一下～",
                "reasoning": "需要确认关系时长",
            },
        }],
    })

    from graph.workflow import skill_tools_node
    from langgraph.prebuilt import ToolNode

    def _noop_invoke(self, state, config=None):
        return {
            "messages": [{
                "role": "tool",
                "content": "{}",
                "tool_call_id": "tc_1",
                "name": "ask_user",
            }],
        }

    monkeypatch.setattr(ToolNode, "invoke", _noop_invoke)

    out = skill_tools_node(state)

    assert out.get("inquiry_card") is not None
    assert out.get("pending_questions") == ["你们认识多久了？"]
    assert out.get("current_agent") == "main_agent"
    assert out.get("agent_resume_point") == "continue_decision"
