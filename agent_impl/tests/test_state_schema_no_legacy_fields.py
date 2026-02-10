from graph.nodes.router import router_node
from graph.nodes.main_agent import main_agent_node
from graph.state import create_initial_state


LEGACY_KEYS = {
    "current_agent",
    "agent_resume_point",
    "_tool_caller",
    "_pending_action",
    "_reply_skill_complete",
    "_handoff_target",
    "_handoff_instruction",
    "_submit_result",
    "_last_tool_outputs",
    "_last_tool_content",
    "ask_mode",
    "ask_mode_tool_message_id",
    "consult_mode",
    "consult_mode_tool_message_id",
    "emotion_mode",
    "emotion_mode_tool_message_id",
    "status_report",
    "action_plan",
    "action_guides",
    "action_guide",
    "history_archive",
    "task_registry",
    "user_context",
    "user_profile",
}


def test_create_initial_state_has_no_legacy_keys():
    state = create_initial_state("hi")
    assert LEGACY_KEYS.isdisjoint(state.keys())


def test_router_and_main_agent_outputs_have_no_legacy_keys():
    state = create_initial_state("hi")
    routed = router_node(state)
    assert LEGACY_KEYS.isdisjoint(routed.keys())

    state.update(routed)
    out = main_agent_node(state)
    assert LEGACY_KEYS.isdisjoint(out.keys())

