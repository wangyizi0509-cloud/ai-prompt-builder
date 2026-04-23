import sys
from pathlib import Path

from langchain_core.messages import ToolMessage


AGENT_IMPL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(AGENT_IMPL_DIR))


def test_build_system_task_pending_responses_emits_status_plan_and_guide_cards():
    from graph.context_types import (
        create_action_guide_item,
        create_action_plan_item,
        create_status_report_item,
    )
    from graph.nodes.main_agent import _build_system_task_pending_responses

    previous_state = {"layer2_memory": {}}
    next_state = {
        "layer2_memory": {
            "current_status_report": create_status_report_item("# status", report_id=1),
            "current_action_plan": create_action_plan_item("## 阶段目标\n推进关系", plan_id=1, goal="推进关系", strategy="稳步推进"),
            "action_guides": [
                create_action_guide_item(
                    guide={"current_task": "破冰", "guide_content": "step 1"},
                    guide_id=1,
                    title="第一步",
                    one_liner="先轻松破冰",
                )
            ],
        }
    }

    pending = _build_system_task_pending_responses(previous_state, next_state, [])

    assert any(item.get("phase") == "status_preface" for item in pending)
    assert any(item.get("taskType") == "status" for item in pending)
    assert any(item.get("phase") == "plan_preface" for item in pending)
    assert any(item.get("taskType") == "strategy" for item in pending)
    assert any(item.get("taskType") == "plan" for item in pending)


def test_build_system_task_pending_responses_respects_existing_thinking_messages():
    from graph.context_types import (
        create_action_plan_item,
        create_status_report_item,
    )
    from graph.nodes.main_agent import _build_system_task_pending_responses

    previous_state = {"layer2_memory": {}}
    next_state = {
        "layer2_memory": {
            "current_status_report": create_status_report_item("# status", report_id=1),
            "current_action_plan": create_action_plan_item("## 阶段目标\n推进关系", plan_id=1, goal="推进关系", strategy="稳步推进"),
        }
    }
    existing_pending = [
        {"from": "status_agent", "phase": "subgraph_thinking", "content": "状态思考中"},
        {"from": "plan_agent", "phase": "subgraph_thinking", "content": "规划思考中"},
    ]

    pending = _build_system_task_pending_responses(previous_state, next_state, existing_pending)

    assert not any(item.get("phase") == "status_preface" for item in pending)
    assert not any(item.get("phase") == "plan_preface" for item in pending)
    assert any(item.get("taskType") == "status" for item in pending)
    assert any(item.get("taskType") == "strategy" for item in pending)


def test_build_system_task_pending_responses_supports_business_ids_without_uuid_id():
    from graph.nodes.main_agent import _build_system_task_pending_responses

    previous_state = {"layer2_memory": {}}
    next_state = {
        "layer2_memory": {
            "current_status_report": {
                "report_id": 7,
                "report_content": "# status\n关系正在推进",
            },
            "current_action_plan": {
                "plan_id": 9,
                "plan_content": "## 阶段目标\n稳住节奏",
            },
            "action_guides": [
                {
                    "guide_id": 11,
                    "title": "第一步",
                    "one_liner": "先稳住关系节奏",
                    "guide": {"guide_content": "step 1"},
                }
            ],
        }
    }

    pending = _build_system_task_pending_responses(previous_state, next_state, [])

    assert any(item.get("messageKey") == "status_preface_7" for item in pending)
    assert any(item.get("taskKey") == "status_7" for item in pending)
    assert any(item.get("messageKey") == "plan_preface_9" for item in pending)
    assert any(item.get("taskKey") == "plan_9" for item in pending)
    assert any(item.get("taskKey") == "guide_11" for item in pending)


def test_emit_tool_done_from_message_uses_business_ids_for_report_ready_events():
    from graph.nodes.main_agent import _emit_tool_done_from_message

    events = []

    _emit_tool_done_from_message(
        events.append,
        ToolMessage(content="ok", tool_call_id="tool_status_1"),
        {
            "layer2_memory": {
                "current_status_report": {
                    "report_id": 12,
                    "report_content": "# 状态报告",
                },
                "current_action_plan": {
                    "plan_id": 34,
                    "plan_content": "## 行动计划",
                },
                "action_guides": [
                    {
                        "guide_id": 56,
                        "title": "第一步",
                        "one_liner": "先自然破冰",
                        "guide": {
                            "guide_content": "### 行动指南\n第一步先自然破冰",
                        },
                    }
                ],
            }
        },
        {"layer2_memory": {}},
    )

    report_ready_events = [event for event in events if event.get("event_type") == "report_ready"]
    assert len(report_ready_events) == 3
    assert any(event.get("task_key") == "status_12" and event.get("report_id") == "12" for event in report_ready_events)
    assert any(event.get("task_key") == "plan_34" and event.get("report_id") == "34" for event in report_ready_events)
    assert any(event.get("task_key") == "guide_56" and event.get("report_id") == "56" for event in report_ready_events)


def test_emit_tool_done_from_message_only_emits_new_report_ready_events():
    from graph.nodes.main_agent import _emit_tool_done_from_message

    events = []
    previous_state = {
        "layer2_memory": {
            "current_status_report": {
                "report_id": 12,
                "report_content": "# 旧状态报告",
            },
            "current_action_plan": {
                "plan_id": 34,
                "plan_content": "## 旧行动计划",
            },
            "action_guides": [
                {
                    "guide_id": 56,
                    "title": "旧指南",
                    "guide": {"guide_content": "旧指南内容"},
                }
            ],
        }
    }

    _emit_tool_done_from_message(
        events.append,
        ToolMessage(content="ok", tool_call_id="tool_plan_1"),
        {
            "layer2_memory": {
                "current_status_report": {
                    "report_id": 12,
                    "report_content": "# 旧状态报告",
                },
                "current_action_plan": {
                    "plan_id": 35,
                    "plan_content": "## 新行动计划",
                },
                "action_guides": [
                    {
                        "guide_id": 56,
                        "title": "旧指南",
                        "guide": {"guide_content": "旧指南内容"},
                    }
                ],
            }
        },
        previous_state,
    )

    report_ready_events = [event for event in events if event.get("event_type") == "report_ready"]
    assert len(report_ready_events) == 1
    assert report_ready_events[0]["report_kind"] == "action_plan"
    assert report_ready_events[0]["task_key"] == "plan_35"
