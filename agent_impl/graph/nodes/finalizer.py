"""
Post-turn Finalizer Node

目标：让“存储/归档/提纯触发”不再依赖某个业务节点是否记得调用。

原则：
- 不调用 LLM（绝不阻塞用户回复）
- 每轮必经：同步全量对话到 layer3_memory.all_messages
- 只做“入队/打标”，LLM-heavy 的维护任务交给 server 异步消费
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from graph.state import sync_new_messages_to_fullstore
from graph.archive_manager import (
    check_layer3_compression_needed,
    check_task_reasoning_compression_needed,
)


def _now() -> str:
    return datetime.now().isoformat()


def _get_flags(state: dict) -> dict:
    flags = state.get("maintenance_flags")
    if isinstance(flags, dict):
        return flags
    return {}


def _set_flag(updates: dict, state: dict, key: str, value: Any) -> None:
    flags = dict(_get_flags(state))
    flags[key] = value
    updates["maintenance_flags"] = flags


def _get_queue(state: dict) -> list[dict]:
    q = state.get("maintenance_queue")
    if isinstance(q, list):
        # shallow copy to avoid in-place mutation
        return list(q)
    return []


def _queue_has(queue: list[dict], task_type: str, task_key: Optional[str] = None) -> bool:
    for t in queue:
        if not isinstance(t, dict):
            continue
        if t.get("type") != task_type:
            continue
        if task_key is None or t.get("task_key") == task_key:
            return True
    return False


def _enqueue(queue: list[dict], *, task_type: str, task_key: str, payload: dict | None = None) -> None:
    queue.append(
        {
            "type": task_type,
            "task_key": task_key,
            "payload": payload or {},
            "created_at": _now(),
            "attempts": 0,
            "last_error": None,
            "status": "queued",
        }
    )


def post_turn_finalize_node(state: dict) -> dict:
    """
    每轮结束的 Finalizer：
    1) 同步 messages → layer3_memory.all_messages（全量存储）
    2) 评估是否需要触发维护任务（入队）
    """
    updates: Dict[str, Any] = {}

    # 1) 全量存储（去重追加）
    sync_updates = sync_new_messages_to_fullstore(state)
    if sync_updates:
        updates.update(sync_updates)

    # 2) 维护任务入队（只打标，不执行）
    queue = _get_queue(state)
    flags = _get_flags(state)
    before_len = len(queue)

    # 2.1 Onboarding 完成后提纯（只要没做过，就保持 queued）
    if state.get("onboarding_completed") and state.get("onboarding_handoff"):
        if not flags.get("onboarding_refine_done") and not _queue_has(queue, "onboarding_refine", "onboarding_refine"):
            _enqueue(queue, task_type="onboarding_refine", task_key="onboarding_refine")
            _set_flag(updates, state, "onboarding_refine_queued", True)

    # 2.2 对话压缩（Layer3）
    if check_layer3_compression_needed(state):
        if not _queue_has(queue, "layer3_compress", "layer3_compress"):
            _enqueue(queue, task_type="layer3_compress", task_key="layer3_compress")

    # 2.3 任务思考过程压缩（Layer3 task_registry）
    tasks_to_compress = check_task_reasoning_compression_needed(state)
    if tasks_to_compress:
        # 任务级压缩可合并为单个任务（内部再扫描）
        if not _queue_has(queue, "task_reasoning_compress", "task_reasoning_compress"):
            _enqueue(queue, task_type="task_reasoning_compress", task_key="task_reasoning_compress", payload={"tasks": tasks_to_compress})

    # 2.4 指南终态归档（逐条入队，避免漏）——优先使用 Layer2 真源
    archived_guide_ids = flags.get("archived_guide_ids") or []
    if not isinstance(archived_guide_ids, list):
        archived_guide_ids = []

    layer2_memory = state.get("layer2_memory") or {}
    guides_source = layer2_memory.get("all_action_guides") if isinstance(layer2_memory, dict) else None
    guides = guides_source if isinstance(guides_source, list) and guides_source else (state.get("action_guides", []) or [])

    for g in guides:
        if not isinstance(g, dict):
            continue
        gid = g.get("id")
        if not gid:
            continue
        if g.get("status") not in ("completed", "cancelled", "expired"):
            continue
        if gid in archived_guide_ids:
            continue
        task_key = f"archive_guide:{gid}"
        if not _queue_has(queue, "archive_guide", task_key):
            _enqueue(queue, task_type="archive_guide", task_key=task_key, payload={"guide_id": gid})

    # 2.5 旧现状报告归档（is_current=False 且缺 summary）
    archived_status_ids = flags.get("archived_status_ids") or []
    if not isinstance(archived_status_ids, list):
        archived_status_ids = []

    reports = layer2_memory.get("all_status_reports", []) if isinstance(layer2_memory, dict) else []
    if isinstance(reports, list):
        for r in reports:
            if not isinstance(r, dict):
                continue
            rid = r.get("id")
            if not rid:
                continue
            if r.get("is_current"):
                continue
            if (r.get("summary") or "").strip():
                continue
            if rid in archived_status_ids:
                continue
            task_key = f"archive_status:{rid}"
            if not _queue_has(queue, "archive_status", task_key):
                _enqueue(queue, task_type="archive_status", task_key=task_key, payload={"report_uid": rid})

    # 2.6 旧行动规划归档（is_current=False 且缺 summary）
    archived_plan_ids = flags.get("archived_plan_ids") or []
    if not isinstance(archived_plan_ids, list):
        archived_plan_ids = []

    plans = layer2_memory.get("all_action_plans", []) if isinstance(layer2_memory, dict) else []
    if isinstance(plans, list):
        for p in plans:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            if not pid:
                continue
            if p.get("is_current"):
                continue
            if (p.get("summary") or "").strip():
                continue
            if pid in archived_plan_ids:
                continue
            task_key = f"archive_plan:{pid}"
            if not _queue_has(queue, "archive_plan", task_key):
                _enqueue(queue, task_type="archive_plan", task_key=task_key, payload={"plan_uid": pid})

    # queue 写回（仅当有变化时写）
    if queue != state.get("maintenance_queue"):
        updates["maintenance_queue"] = queue

    # 最后更新时间
    updates["maintenance_last_finalized_at"] = _now()

    # 3) 可观测性：写一条 debug_log（本轮可见）
    enqueued = len(queue) - before_len
    if enqueued > 0:
        preview = []
        for t in queue[-min(enqueued, 5):]:
            if isinstance(t, dict):
                preview.append({"type": t.get("type"), "task_key": t.get("task_key")})
        updates["debug_log"] = [{
            "node": "post_turn_finalize",
            "step": "Enqueue maintenance tasks",
            "enqueued": enqueued,
            "queue_size": len(queue),
            "preview": preview,
        }]

    return updates


