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
import os

from graph.state import sync_new_messages_to_fullstore
from graph.archive_manager import (
    check_layer3_compression_needed,
    check_task_reasoning_compression_needed,
    refine_on_onboarding_complete,
    compress_layer3,
    compress_task_reasoning,
    archive_guide_to_layer2,
    archive_status_to_layer2,
    archive_plan_to_layer2,
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


def _consume_maintenance_queue_inline(state: dict, queue: list[dict]) -> dict:
    """
    在 Studio 模式下同步消费维护队列（允许触发 LLM 归档）。
    注意：仅在 STUDIO_SYNC_MAINTENANCE=1 时启用。
    """
    flags = state.get("maintenance_flags") if isinstance(state.get("maintenance_flags"), dict) else {}
    updated_queue = []
    updates: Dict[str, Any] = {}
    working_state = dict(state)

    for item in queue:
        if not isinstance(item, dict):
            continue

        task_type = item.get("type")
        status = item.get("status", "queued")
        if status in ("done", "skipped"):
            updated_queue.append(item)
            continue

        running_item = dict(item)
        running_item["status"] = "running"
        running_item["attempts"] = int(running_item.get("attempts", 0) or 0) + 1
        running_item["last_error"] = None
        updated_queue.append(running_item)

        try:
            task_updates: Dict[str, Any] = {}

            if task_type == "onboarding_refine":
                task_updates = refine_on_onboarding_complete(working_state)
                flags = dict(flags)
                flags["onboarding_refine_done"] = True
                flags["onboarding_refine_queued"] = False
                task_updates["maintenance_flags"] = flags

            elif task_type == "layer3_compress":
                # [DEBUG] 检查压缩输入状态
                workspace_msgs = working_state.get("messages", []) or []
                print(f"[Finalizer] layer3_compress: workspace_messages={len(workspace_msgs)}")
                task_updates = compress_layer3(working_state)
                print(f"[Finalizer] layer3_compress returned: {list(task_updates.keys()) if task_updates else 'empty'}")

            elif task_type == "task_reasoning_compress":
                task_updates = compress_task_reasoning(working_state)

            elif task_type == "archive_guide":
                payload = item.get("payload") or {}
                guide_id = payload.get("guide_id")
                if guide_id:
                    guide_obj = None
                    for g in working_state.get("action_guides", []) or []:
                        if isinstance(g, dict) and g.get("id") == guide_id:
                            guide_obj = g
                            break
                    if not guide_obj:
                        layer2_memory = working_state.get("layer2_memory") or {}
                        guides2 = layer2_memory.get("action_guides", []) if isinstance(layer2_memory, dict) else []
                        for g in guides2 or []:
                            if isinstance(g, dict) and g.get("id") == guide_id:
                                guide_obj = g
                                break
                    if guide_obj:
                        task_updates = archive_guide_to_layer2(guide_obj, working_state)
                        flags = dict(flags)
                        archived = flags.get("archived_guide_ids") or []
                        if not isinstance(archived, list):
                            archived = []
                        if guide_id not in archived:
                            archived.append(guide_id)
                        flags["archived_guide_ids"] = archived
                        task_updates["maintenance_flags"] = flags

            elif task_type == "archive_status":
                payload = item.get("payload") or {}
                report_uid = payload.get("report_uid")
                if report_uid:
                    old_report = None
                    layer2_memory = working_state.get("layer2_memory") or {}
                    # 在历史报告中查找
                    reports = layer2_memory.get("status_report_history", []) if isinstance(layer2_memory, dict) else []
                    for r in reports or []:
                        if isinstance(r, dict) and r.get("id") == report_uid:
                            old_report = r
                            break
                    if old_report:
                        task_updates = archive_status_to_layer2(old_report, working_state)
                        flags = dict(flags)
                        archived = flags.get("archived_status_ids") or []
                        if not isinstance(archived, list):
                            archived = []
                        if report_uid not in archived:
                            archived.append(report_uid)
                        flags["archived_status_ids"] = archived
                        task_updates["maintenance_flags"] = flags

            elif task_type == "archive_plan":
                payload = item.get("payload") or {}
                plan_uid = payload.get("plan_uid")
                if plan_uid:
                    old_plan = None
                    layer2_memory = working_state.get("layer2_memory") or {}
                    # 在历史规划中查找
                    plans = layer2_memory.get("action_plan_history", []) if isinstance(layer2_memory, dict) else []
                    for p in plans or []:
                        if isinstance(p, dict) and p.get("id") == plan_uid:
                            old_plan = p
                            break
                    if old_plan:
                        task_updates = archive_plan_to_layer2(old_plan, working_state)
                        flags = dict(flags)
                        archived = flags.get("archived_plan_ids") or []
                        if not isinstance(archived, list):
                            archived = []
                        if plan_uid not in archived:
                            archived.append(plan_uid)
                        flags["archived_plan_ids"] = archived
                        task_updates["maintenance_flags"] = flags
            else:
                done_item = dict(running_item)
                done_item["status"] = "skipped"
                done_item["last_error"] = f"unknown_task_type:{task_type}"
                updated_queue[-1] = done_item
                continue

            if task_updates:
                working_state.update(task_updates)
                updates.update(task_updates)

            done_item = dict(updated_queue[-1])
            done_item["status"] = "done"
            done_item["finished_at"] = _now()
            updated_queue[-1] = done_item

        except Exception as e:
            fail_item = dict(updated_queue[-1])
            fail_item["status"] = "failed"
            fail_item["last_error"] = str(e)
            updated_queue[-1] = fail_item

    updates["maintenance_queue"] = updated_queue
    if flags:
        updates["maintenance_flags"] = flags
    return updates


def post_turn_finalize_node(state: dict) -> dict:
    """
    每轮结束的 Finalizer：
    1) 同步 messages → layer3_memory.all_messages（全量存储）
    2) 评估是否需要触发维护任务（入队）
    """
    from utils.message_utils import count_user_turns
    from graph.archive_manager import LAYER3_ARCHIVE_CONFIG
    
    # [DEBUG] 验证 finalizer 是否被调用
    queue_before = len(_get_queue(state))
    print(f"[Finalizer] post_turn_finalize called, queue_before={queue_before}, onboarding_completed={state.get('onboarding_completed')}")
    
    updates: Dict[str, Any] = {}

    # 1) 全量存储（去重追加）
    sync_updates = sync_new_messages_to_fullstore(state)
    if sync_updates:
        updates.update(sync_updates)

    # [FIX] 创建 working_state，合并 sync_updates 后再进行后续检查
    # 这确保压缩检查使用的是包含最新消息的 layer3_memory
    working_state = dict(state)
    if sync_updates:
        working_state.update(sync_updates)

    # 2) 维护任务入队（默认只打标；Studio 可选择同步执行）
    queue = _get_queue(working_state)
    flags = _get_flags(working_state)
    before_len = len(queue)

    # 2.1 Onboarding 完成后提纯（只要没做过，就保持 queued）
    if working_state.get("onboarding_completed") and working_state.get("onboarding_handoff"):
        if not flags.get("onboarding_refine_done") and not _queue_has(queue, "onboarding_refine", "onboarding_refine"):
            _enqueue(queue, task_type="onboarding_refine", task_key="onboarding_refine")
            _set_flag(updates, working_state, "onboarding_refine_queued", True)

    # 2.2 对话压缩（Layer3）—— 基于工作区消息 (messages) 判断，而非全量存储
    # [DEBUG] 输出压缩检查的详细信息
    workspace_msgs = working_state.get("messages", []) or []
    user_turns = count_user_turns(workspace_msgs)
    threshold = LAYER3_ARCHIVE_CONFIG.get("compression_threshold", 25)
    batch_size = LAYER3_ARCHIVE_CONFIG.get("compression_batch_size", 1)
    excess = user_turns - threshold if user_turns > threshold else 0
    should_compress = excess > 0 and excess % batch_size == 0
    print(f"[Finalizer] Compression check: workspace_messages={len(workspace_msgs)}, user_turns={user_turns}, threshold={threshold}, batch_size={batch_size}, excess={excess}, should_compress={should_compress}")
    
    if check_layer3_compression_needed(working_state):
        if not _queue_has(queue, "layer3_compress", "layer3_compress"):
            _enqueue(queue, task_type="layer3_compress", task_key="layer3_compress")
            print(f"[Finalizer] Enqueued layer3_compress task")

    # 2.3 任务思考过程压缩（Layer3 task_registry）
    tasks_to_compress = check_task_reasoning_compression_needed(working_state)
    if tasks_to_compress:
        # 任务级压缩可合并为单个任务（内部再扫描）
        if not _queue_has(queue, "task_reasoning_compress", "task_reasoning_compress"):
            _enqueue(queue, task_type="task_reasoning_compress", task_key="task_reasoning_compress", payload={"tasks": tasks_to_compress})

    # 2.4 指南终态归档（逐条入队，避免漏）——优先使用 Layer2 真源
    archived_guide_ids = flags.get("archived_guide_ids") or []
    if not isinstance(archived_guide_ids, list):
        archived_guide_ids = []

    layer2_memory = working_state.get("layer2_memory") or {}
    guides_source = layer2_memory.get("action_guides") if isinstance(layer2_memory, dict) else None
    guides = guides_source if isinstance(guides_source, list) and guides_source else (working_state.get("action_guides", []) or [])

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

    # 2.5 历史现状报告归档（缺 summary 的历史报告）
    archived_status_ids = flags.get("archived_status_ids") or []
    if not isinstance(archived_status_ids, list):
        archived_status_ids = []

    history_reports = layer2_memory.get("status_report_history", []) if isinstance(layer2_memory, dict) else []
    if isinstance(history_reports, list):
        for r in history_reports:
            if not isinstance(r, dict):
                continue
            rid = r.get("id")
            if not rid:
                continue
            if (r.get("summary") or "").strip():
                continue
            if rid in archived_status_ids:
                continue
            task_key = f"archive_status:{rid}"
            if not _queue_has(queue, "archive_status", task_key):
                _enqueue(queue, task_type="archive_status", task_key=task_key, payload={"report_uid": rid})

    # 2.6 历史行动规划归档（缺 summary 的历史规划）
    archived_plan_ids = flags.get("archived_plan_ids") or []
    if not isinstance(archived_plan_ids, list):
        archived_plan_ids = []

    history_plans = layer2_memory.get("action_plan_history", []) if isinstance(layer2_memory, dict) else []
    if isinstance(history_plans, list):
        for p in history_plans:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            if not pid:
                continue
            if (p.get("summary") or "").strip():
                continue
            if pid in archived_plan_ids:
                continue
            task_key = f"archive_plan:{pid}"
            if not _queue_has(queue, "archive_plan", task_key):
                _enqueue(queue, task_type="archive_plan", task_key=task_key, payload={"plan_uid": pid})

    # queue 写回（仅当有变化时写）
    if queue != working_state.get("maintenance_queue"):
        updates["maintenance_queue"] = queue

    # 2.7 Studio 同步消费维护队列（可触发 LLM 归档）
    # [FIX] 检测 LangGraph Studio 环境：检查多个特征
    is_studio = False
    try:
        import sys
        # Studio dev 模式会加载这些模块
        is_studio = (
            "langgraph_runtime_inmem" in sys.modules or 
            "langgraph_api" in sys.modules or
            os.environ.get("STUDIO_SYNC_MAINTENANCE") == "1"
        )
    except:
        pass
    
    # [DEBUG] 记录 Studio 模式检测结果到 debug_log
    if "debug_log" not in updates:
        updates["debug_log"] = []
    updates["debug_log"].append({
        "node": "post_turn_finalize",
        "step": "Studio mode check",
        "is_studio": is_studio,
        "queue_len": len(queue),
    })
    
    if is_studio and queue:
        print(f"[Finalizer] Studio mode detected, consuming {len(queue)} maintenance tasks inline")
        inline_updates = _consume_maintenance_queue_inline(working_state, queue)
        if inline_updates:
            updates.update(inline_updates)
            # 记录消费结果
            updates["debug_log"].append({
                "node": "post_turn_finalize", 
                "step": "Inline consume done",
                "queue_after": len(inline_updates.get("maintenance_queue", [])),
            })

    # 最后更新时间
    updates["maintenance_last_finalized_at"] = _now()

    # 3) 可观测性：写一条 debug_log（本轮可见）
    enqueued = len(queue) - before_len
    if enqueued > 0:
        preview = []
        for t in queue[-min(enqueued, 5):]:
            if isinstance(t, dict):
                preview.append({"type": t.get("type"), "task_key": t.get("task_key")})
        # [FIX] 使用 append 而不是赋值，避免覆盖之前的日志
        if "debug_log" not in updates:
            updates["debug_log"] = []
        updates["debug_log"].append({
            "node": "post_turn_finalize",
            "step": "Enqueue maintenance tasks",
            "enqueued": enqueued,
            "queue_size": len(queue),
            "preview": preview,
        })

    return updates


