import json

import pytest

from graph.state import create_initial_state
from graph.context_builder import build_context_dict
from graph.context_types import (
    create_empty_layer2_memory,
    create_empty_layer3_memory,
    create_new_task,
)
from graph.tools.guide_bind_tools import bind_action_guide_detail_impl
from graph.tools.task_tools import create_task_impl


def _mk_guide(guide_id: str, title: str, content_md: str, status: str = "pending") -> dict:
    return {
        "id": guide_id,
        "title": title,
        "status": status,
        "created_at": "2026-01-11T00:00:00",
        "guide_content": content_md,
        "guide": {
            "current_task": title,
            "guide_content": content_md,
            "steps": ["step1", "step2"],
            "talking_points": ["tp1", "tp2"],
        },
    }


@pytest.fixture
def state_with_task_and_guides():
    """
    一个最小可用的 state：
    - Layer2: 有 action_guides（用于 bind 工具读取详情）
    - Layer3: main_agent 有一个 active task（用于写入 bound_action_guides）
    """
    state = create_initial_state("测试 bind_action_guide_detail")

    # Layer2: guides
    layer2 = create_empty_layer2_memory()
    layer2["action_guides"] = [
        _mk_guide("g1", "指南1", "内容1"),
        _mk_guide("g2", "指南2", "内容2"),
        _mk_guide("g3", "指南3", "内容3"),
        _mk_guide("g4", "指南4", "内容4"),
    ]
    state["layer2_memory"] = layer2

    # Layer3: tasks
    task_a = create_new_task("taskA_case", "测试绑定注入")
    task_a["is_active"] = True
    task_a["status"] = "active"

    layer3 = create_empty_layer3_memory()
    layer3["task_registry"] = {
        "main_agent": [task_a],
        "status_agent": [],
        "plan_agent": [],
        "guide_agent": [],
    }
    state["layer3_memory"] = layer3

    return state


class TestTaskBoundActionGuideDetail:
    def test_bind_writes_into_active_task(self, state_with_task_and_guides):
        state = state_with_task_and_guides

        state_update, result_json = bind_action_guide_detail_impl(state, "g1", "main_agent")
        result = json.loads(result_json)

        assert result["success"] is True
        assert result["updated"] is False
        assert result["bound_to_task_id"] == "taskA_case"

        # 写入 task 容器字段
        task_list = state_update["layer3_memory"]["task_registry"]["main_agent"]
        active_task = next(t for t in task_list if t.get("is_active"))
        bound = active_task.get("bound_action_guides") or []

        assert len(bound) == 1
        assert bound[0]["guide_id"] == "g1"
        assert bound[0].get("content_md")
        assert bound[0].get("bound_at")
        assert bound[0].get("source") == "bind_action_guide_detail"

        # 跨轮次注入：build_context_dict 只注入当前 active task 的 bound_action_guides
        state["layer3_memory"] = state_update["layer3_memory"]
        ctx = build_context_dict(state, target_agent="main_agent")
        assert "任务绑定的行动指南详情" in (ctx.get("bound_action_guides") or "")
        assert "g1" in (ctx.get("bound_action_guides") or "")

    def test_rebind_same_guide_id_overwrites(self, state_with_task_and_guides):
        state = state_with_task_and_guides

        # 第一次绑定
        state_update, _ = bind_action_guide_detail_impl(state, "g1", "main_agent")
        state["layer3_memory"] = state_update["layer3_memory"]

        # 修改 Layer2 内容（模拟“刷新快照”）
        layer2 = state["layer2_memory"]
        layer2["action_guides"][0] = _mk_guide("g1", "指南1", "内容1-新版")
        state["layer2_memory"] = layer2

        # 第二次绑定同一 guide_id
        state_update2, result_json2 = bind_action_guide_detail_impl(state, "g1", "main_agent")
        result2 = json.loads(result_json2)

        assert result2["success"] is True
        assert result2["updated"] is True

        task_list2 = state_update2["layer3_memory"]["task_registry"]["main_agent"]
        active_task2 = next(t for t in task_list2 if t.get("is_active"))
        bound2 = active_task2.get("bound_action_guides") or []

        assert len(bound2) == 1  # 去重覆盖：数量仍为 1
        assert bound2[0]["guide_id"] == "g1"
        assert "内容1-新版" in (bound2[0].get("content_md") or "")

    def test_task_isolation_new_task_has_no_bound_guides(self, state_with_task_and_guides):
        state = state_with_task_and_guides

        # 先在 taskA 绑定一条
        state_update, _ = bind_action_guide_detail_impl(state, "g1", "main_agent")
        state["layer3_memory"] = state_update["layer3_memory"]

        # 创建 taskB 并设为活跃
        state_update2, _ = create_task_impl(state, "taskB_case", "测试任务隔离", "main_agent")
        task_list2 = state_update2["layer3_memory"]["task_registry"]["main_agent"]
        active_task2 = next(t for t in task_list2 if t.get("is_active"))

        assert active_task2["task_id"] == "taskB_case"
        assert active_task2.get("bound_action_guides") == []

        # 旧任务仍保留绑定，只是不再注入
        old_task = next(t for t in task_list2 if t.get("task_id") == "taskA_case")
        assert len(old_task.get("bound_action_guides") or []) == 1

    def test_k3_fifo_eviction(self, state_with_task_and_guides):
        state = state_with_task_and_guides

        # 连续绑定 4 个不同 guide_id
        state_update, _ = bind_action_guide_detail_impl(state, "g1", "main_agent")
        state["layer3_memory"] = state_update["layer3_memory"]
        state_update, _ = bind_action_guide_detail_impl(state, "g2", "main_agent")
        state["layer3_memory"] = state_update["layer3_memory"]
        state_update, _ = bind_action_guide_detail_impl(state, "g3", "main_agent")
        state["layer3_memory"] = state_update["layer3_memory"]

        # 第 4 个触发 FIFO 淘汰
        state_update4, result_json4 = bind_action_guide_detail_impl(state, "g4", "main_agent")
        result4 = json.loads(result_json4)

        assert result4["success"] is True
        assert "evicted" in result4
        assert result4["evicted"]["guide_id"] == "g1"

        task_list4 = state_update4["layer3_memory"]["task_registry"]["main_agent"]
        active_task4 = next(t for t in task_list4 if t.get("is_active"))
        bound4 = active_task4.get("bound_action_guides") or []

        assert [b.get("guide_id") for b in bound4] == ["g2", "g3", "g4"]

