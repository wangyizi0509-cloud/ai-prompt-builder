"""
维护队列（maintenance_queue）回归测试

目标：不依赖真实 LLM，只验证“回合结束 Finalizer 的必达触发”与“全量存储同步”。
"""

from graph.nodes.finalizer import post_turn_finalize_node
from graph.context_types import (
    create_empty_layer2_memory,
    create_empty_layer3_memory,
    create_status_report_item,
    create_action_plan_item,
    create_action_guide_item,
)
from graph.archive_manager import LAYER3_ARCHIVE_CONFIG


def _has_task(queue: list[dict], task_type: str, task_key_prefix: str) -> bool:
    for t in queue or []:
        if not isinstance(t, dict):
            continue
        if t.get("type") != task_type:
            continue
        if str(t.get("task_key", "")).startswith(task_key_prefix):
            return True
    return False


def test_fullstore_sync_appends_new_messages():
    layer3 = create_empty_layer3_memory()
    layer3["all_messages"] = [{"role": "user", "content": "t1", "id": "m1"}]

    state = {
        "messages": [
            {"role": "user", "content": "t1", "id": "m1"},
            {"role": "assistant", "content": "a1", "id": "m2"},
        ],
        "layer3_memory": layer3,
        "maintenance_queue": [],
        "maintenance_flags": {},
    }

    updates = post_turn_finalize_node(state)
    updated_layer3 = updates.get("layer3_memory", {})
    assert len(updated_layer3.get("all_messages", [])) == 2


def test_enqueues_layer3_compress_at_threshold_batch_point():
    layer3 = create_empty_layer3_memory()
    threshold = int(LAYER3_ARCHIVE_CONFIG.get("compression_threshold", 25))
    batch_size = int(LAYER3_ARCHIVE_CONFIG.get("compression_batch_size", 1))
    target_turns = threshold + batch_size
    layer3["all_messages"] = []

    messages = []
    for i in range(target_turns):
        messages.append({"role": "user", "content": f"u{i}", "id": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}", "id": f"a{i}"})

    state = {
        "layer3_memory": layer3,
        "messages": messages,
        "maintenance_queue": [],
        "maintenance_flags": {},
    }

    updates = post_turn_finalize_node(state)
    queue = updates.get("maintenance_queue", [])
    assert _has_task(queue, "layer3_compress", "layer3_compress")


def test_enqueues_archive_status_for_old_report_missing_summary():
    layer2 = create_empty_layer2_memory()
    current = create_status_report_item(report_content="new", report_id=2)
    old = create_status_report_item(report_content="old", report_id=1)
    old["summary"] = None
    layer2["current_status_report"] = current
    layer2["status_report_history"] = [old]

    state = {
        "layer2_memory": layer2,
        "layer3_memory": create_empty_layer3_memory(),
        "messages": [],
        "maintenance_queue": [],
        "maintenance_flags": {},
    }

    updates = post_turn_finalize_node(state)
    queue = updates.get("maintenance_queue", [])
    assert _has_task(queue, "archive_status", f"archive_status:{old['id']}")


def test_enqueues_archive_plan_for_old_plan_missing_summary():
    layer2 = create_empty_layer2_memory()
    current = create_action_plan_item(plan_content="new", plan_id=2)
    old = create_action_plan_item(plan_content="old", plan_id=1)
    old["summary"] = ""
    layer2["current_action_plan"] = current
    layer2["action_plan_history"] = [old]

    state = {
        "layer2_memory": layer2,
        "layer3_memory": create_empty_layer3_memory(),
        "messages": [],
        "maintenance_queue": [],
        "maintenance_flags": {},
    }

    updates = post_turn_finalize_node(state)
    queue = updates.get("maintenance_queue", [])
    assert _has_task(queue, "archive_plan", f"archive_plan:{old['id']}")


def test_enqueues_archive_guide_for_completed_guide():
    layer2 = create_empty_layer2_memory()
    guide = create_action_guide_item(guide={"guide_content": "x"}, guide_id=1, status="completed")
    layer2["action_guides"] = [guide]

    state = {
        "layer2_memory": layer2,
        "layer3_memory": create_empty_layer3_memory(),
        "messages": [],
        "maintenance_queue": [],
        "maintenance_flags": {},
    }

    updates = post_turn_finalize_node(state)
    queue = updates.get("maintenance_queue", [])
    assert _has_task(queue, "archive_guide", f"archive_guide:{guide['id']}")


def test_enqueues_archive_guide_for_cancelled_or_expired_guide():
    layer2 = create_empty_layer2_memory()
    g1 = create_action_guide_item(guide={"guide_content": "x"}, guide_id=1, status="cancelled")
    g2 = create_action_guide_item(guide={"guide_content": "y"}, guide_id=2, status="expired")
    layer2["action_guides"] = [g1, g2]

    state = {
        "layer2_memory": layer2,
        "layer3_memory": create_empty_layer3_memory(),
        "messages": [],
        "maintenance_queue": [],
        "maintenance_flags": {},
    }

    updates = post_turn_finalize_node(state)
    queue = updates.get("maintenance_queue", [])
    assert _has_task(queue, "archive_guide", f"archive_guide:{g1['id']}")
    assert _has_task(queue, "archive_guide", f"archive_guide:{g2['id']}")


def test_does_not_enqueue_archive_guide_for_paused_guide():
    layer2 = create_empty_layer2_memory()
    guide = create_action_guide_item(guide={"guide_content": "x"}, guide_id=1, status="paused")
    layer2["action_guides"] = [guide]

    state = {
        "layer2_memory": layer2,
        "layer3_memory": create_empty_layer3_memory(),
        "messages": [],
        "maintenance_queue": [],
        "maintenance_flags": {},
    }

    updates = post_turn_finalize_node(state)
    queue = updates.get("maintenance_queue", [])
    assert not _has_task(queue, "archive_guide", f"archive_guide:{guide['id']}")


def test_finalizer_is_idempotent_no_duplicate_queue_items():
    layer2 = create_empty_layer2_memory()
    old = create_action_plan_item(plan_content="old", plan_id=1)
    old["summary"] = ""
    layer2["action_plan_history"] = [old]

    state = {
        "layer2_memory": layer2,
        "layer3_memory": create_empty_layer3_memory(),
        "messages": [],
        "maintenance_queue": [],
        "maintenance_flags": {},
    }

    u1 = post_turn_finalize_node(state)
    q1 = u1.get("maintenance_queue", [])
    assert _has_task(q1, "archive_plan", f"archive_plan:{old['id']}")

    # 第二次运行：把第一次的 queue 写回 state，再跑一遍，不应新增重复条目
    state2 = dict(state)
    state2["maintenance_queue"] = q1
    u2 = post_turn_finalize_node(state2)
    q2 = u2.get("maintenance_queue", q1)

    plan_tasks = [t for t in q2 if isinstance(t, dict) and t.get("type") == "archive_plan" and t.get("task_key") == f"archive_plan:{old['id']}"]
    assert len(plan_tasks) == 1

