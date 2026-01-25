import json

from tests.conftest import create_test_state


def test_delegate_to_status_returns_handoff_json():
    from graph.tools.delegate_tools import delegate_to_status

    result = delegate_to_status.invoke({"instruction": "分析当前关系阶段"})
    data = json.loads(result)

    assert data["action"] == "handoff"
    assert data["target"] == "status_agent"
    assert data["instruction"] == "分析当前关系阶段"


def test_skill_tools_node_sets_handoff_target(monkeypatch):
    state = create_test_state("我想知道我们是什么阶段")
    state["messages"].append({
        "role": "assistant",
        "tool_calls": [{
            "id": "tc_1",
            "name": "delegate_to_status",
            "args": {"instruction": "分析阶段"},
        }],
    })

    from graph.workflow import skill_tools_node
    from langgraph.prebuilt import ToolNode

    def _noop_invoke(self, state, config=None):
        return {}

    monkeypatch.setattr(ToolNode, "invoke", _noop_invoke)

    out = skill_tools_node(state)

    assert out.get("_handoff_target") == "status_agent"
    assert out.get("instruction") == "分析阶段"


def test_route_after_skill_tools_routes_to_sub_agent():
    from graph.workflow import route_after_skill_tools

    state = {"_handoff_target": "plan_agent", "_iteration_count": 1}

    assert route_after_skill_tools(state) == "plan_agent"
