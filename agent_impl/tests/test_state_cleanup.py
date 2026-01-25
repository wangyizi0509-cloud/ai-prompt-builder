from tests.conftest import create_test_state


def test_router_clears_handoff_and_pending_action():
    from graph.nodes.router import router_node

    state = create_test_state("新一轮输入")
    state["_handoff_target"] = "status_agent"
    state["_pending_action"] = "inquiry"

    out = router_node(state)

    assert out.get("_handoff_target") is None
    assert out.get("_pending_action") is None
