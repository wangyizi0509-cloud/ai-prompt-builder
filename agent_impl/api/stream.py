import json
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Literal, Optional

from auth_utils import get_optional_user
from .sdk_client import (
    get_client,
    session_to_thread_id,
    ensure_thread_exists,
    get_thread_state,
    update_thread_state,
    run_assistant,
)

router = APIRouter()

LOG_PATH = Path("/Users/ant/Desktop/Crushe/模型策略/.cursor/debug.log")


class StreamChatRequest(BaseModel):
    message: str
    session_id: str
    stream_mode: Optional[Literal["values", "updates", "messages", "debug"]] = "updates"


def _append_debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict):
    import time
    payload = {
        "sessionId": "debug-session",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _run_maintenance_tasks_sdk(session_id: str, thread_id: str) -> None:
    """
    后台消费 maintenance_queue - 使用 SDK 版本
    - 读取最新 state（避免拿到过期的 final_state）
    - best-effort 执行：失败记录在 queue item 里，下一轮可重试
    """
    from graph.archive_manager import (
        refine_on_onboarding_complete,
        compress_layer3,
        compress_task_reasoning,
        archive_guide_to_layer2,
        archive_status_to_layer2,
        archive_plan_to_layer2,
    )
    from datetime import datetime

    state = get_thread_state(thread_id)
    if not state:
        return

    queue = state.get("maintenance_queue") or []
    if not isinstance(queue, list) or not queue:
        return

    flags = state.get("maintenance_flags") if isinstance(state.get("maintenance_flags"), dict) else {}

    updated_queue = []
    any_changes = False

    for item in queue:
        if not isinstance(item, dict):
            continue

        task_type = item.get("type")
        task_key = item.get("task_key")
        status = item.get("status", "queued")

        if status in ("done", "skipped"):
            updated_queue.append(item)
            continue

        running_item = dict(item)
        running_item["status"] = "running"
        running_item["attempts"] = int(running_item.get("attempts", 0) or 0) + 1
        running_item["last_error"] = None
        updated_queue.append(running_item)
        any_changes = True
        update_thread_state(thread_id, {"maintenance_queue": updated_queue})

        try:
            _append_debug_log(
                run_id="maintenance-sdk",
                hypothesis_id="M1",
                location="api/stream.py:_run_maintenance_tasks_sdk:start",
                message="Maintenance task started via SDK",
                data={
                    "session_id": session_id,
                    "type": task_type,
                    "task_key": task_key,
                    "attempts": running_item.get("attempts"),
                },
            )

            updates = {}

            if task_type == "onboarding_refine":
                updates = refine_on_onboarding_complete(state)
                flags = dict(flags)
                flags["onboarding_refine_done"] = True
                flags["onboarding_refine_queued"] = False
                updates["maintenance_flags"] = flags

            elif task_type == "layer3_compress":
                updates = compress_layer3(state)

            elif task_type == "task_reasoning_compress":
                updates = compress_task_reasoning(state)

            elif task_type == "archive_guide":
                payload = item.get("payload") or {}
                guide_id = payload.get("guide_id")
                if guide_id:
                    guide_obj = None
                    for g in state.get("action_guides", []) or []:
                        if isinstance(g, dict) and g.get("id") == guide_id:
                            guide_obj = g
                            break
                    if not guide_obj:
                        layer2_memory = state.get("layer2_memory") or {}
                        guides2 = layer2_memory.get("action_guides", []) if isinstance(layer2_memory, dict) else []
                        for g in guides2 or []:
                            if isinstance(g, dict) and g.get("id") == guide_id:
                                guide_obj = g
                                break
                    if guide_obj:
                        updates = archive_guide_to_layer2(guide_obj, state)
                        flags = dict(flags)
                        archived = flags.get("archived_guide_ids") or []
                        if not isinstance(archived, list):
                            archived = []
                        if guide_id not in archived:
                            archived.append(guide_id)
                        flags["archived_guide_ids"] = archived
                        updates["maintenance_flags"] = flags
                    else:
                        updates = {}

            elif task_type == "archive_status":
                payload = item.get("payload") or {}
                report_uid = payload.get("report_uid")
                if report_uid:
                    old_report = None
                    layer2_memory = state.get("layer2_memory") or {}
                    reports = layer2_memory.get("status_report_history", []) if isinstance(layer2_memory, dict) else []
                    for r in reports or []:
                        if isinstance(r, dict) and r.get("id") == report_uid:
                            old_report = r
                            break
                    if old_report:
                        updates = archive_status_to_layer2(old_report, state)
                        flags = dict(flags)
                        archived = flags.get("archived_status_ids") or []
                        if not isinstance(archived, list):
                            archived = []
                        if report_uid not in archived:
                            archived.append(report_uid)
                        flags["archived_status_ids"] = archived
                        updates["maintenance_flags"] = flags

            elif task_type == "archive_plan":
                payload = item.get("payload") or {}
                plan_uid = payload.get("plan_uid")
                if plan_uid:
                    old_plan = None
                    layer2_memory = state.get("layer2_memory") or {}
                    plans = layer2_memory.get("action_plan_history", []) if isinstance(layer2_memory, dict) else []
                    for p in plans or []:
                        if isinstance(p, dict) and p.get("id") == plan_uid:
                            old_plan = p
                            break
                    if old_plan:
                        updates = archive_plan_to_layer2(old_plan, state)
                        flags = dict(flags)
                        archived = flags.get("archived_plan_ids") or []
                        if not isinstance(archived, list):
                            archived = []
                        if plan_uid not in archived:
                            archived.append(plan_uid)
                        flags["archived_plan_ids"] = archived
                        updates["maintenance_flags"] = flags

            else:
                done_item = dict(running_item)
                done_item["status"] = "skipped"
                done_item["last_error"] = f"unknown_task_type:{task_type}"
                updated_queue[-1] = done_item
                update_thread_state(thread_id, {"maintenance_queue": updated_queue})
                continue

            if updates:
                state.update(updates)
                update_thread_state(thread_id, updates)

            done_item = dict(updated_queue[-1])
            done_item["status"] = "done"
            done_item["finished_at"] = datetime.now().isoformat()
            updated_queue[-1] = done_item
            update_thread_state(thread_id, {"maintenance_queue": updated_queue})

            _append_debug_log(
                run_id="maintenance-sdk",
                hypothesis_id="M2",
                location="api/stream.py:_run_maintenance_tasks_sdk:done",
                message="Maintenance task done via SDK",
                data={
                    "session_id": session_id,
                    "type": task_type,
                    "task_key": task_key,
                    "updated_keys": list(updates.keys()) if isinstance(updates, dict) else [],
                },
            )

        except Exception as e:
            fail_item = dict(updated_queue[-1])
            fail_item["status"] = "failed"
            fail_item["last_error"] = str(e)
            updated_queue[-1] = fail_item
            update_thread_state(thread_id, {"maintenance_queue": updated_queue})

            _append_debug_log(
                run_id="maintenance-sdk",
                hypothesis_id="M3",
                location="api/stream.py:_run_maintenance_tasks_sdk:failed",
                message="Maintenance task failed via SDK",
                data={
                    "session_id": session_id,
                    "type": task_type,
                    "task_key": task_key,
                    "error": str(e),
                },
            )

    if any_changes:
        update_thread_state(thread_id, {"maintenance_queue": updated_queue})


@router.post("/chat/stream")
async def chat_stream(request: StreamChatRequest, background_tasks: BackgroundTasks, current_user = Depends(get_optional_user)):
    """
    流式聊天接口 - 实时查看 Agent 执行过程（通过 SDK）
    
    支持多种流模式：
    - values: 每个步骤后的完整状态
    - updates: 每个步骤的状态更新（推荐）
    - messages: LLM tokens 和元数据
    - debug: 最详细的调试信息
    
    使用 Server-Sent Events (SSE) 格式返回数据
    """
    print(f"[Stream SDK] Received message from session {request.session_id}: {request.message}")
    print(f"[Stream SDK] Stream mode: {request.stream_mode}")
    
    from graph.state import create_initial_state
    
    user_id = current_user['user_id'] if current_user else None
    thread_id = await ensure_thread_exists(request.session_id, user_id)
    base_state = get_thread_state(thread_id)
    
    if base_state is None:
        print("[Stream SDK] Creating new session (checkpointer empty)")
        state = create_initial_state(request.message)
    else:
        print("[Stream SDK] Restoring existing session (checkpointer)")
        state = dict(base_state)
        state["user_message"] = request.message
        state["debug_log"] = []
        state["inquiry_card"] = None
        state["pending_questions"] = []
        state["pending_responses"] = []
        state["last_response_for_continuity"] = None
    
    async def generate_stream():
        """生成流式响应"""
        final_state = None
        try:
            for chunk in run_assistant(thread_id, state, stream_mode=request.stream_mode):
                event_name = request.stream_mode or "values"
                chunk_data = {
                    "event": event_name,
                    "data": chunk.data if hasattr(chunk, 'data') else chunk,
                    "stream_mode": request.stream_mode
                }
                
                _append_debug_log(
                    run_id="sdk-version",
                    hypothesis_id="H3",
                    location="api/stream.py:chat_stream:chunk",
                    message="Stream chunk via SDK",
                    data={
                        "event": event_name,
                        "has_inquiry_card": bool(chunk.data.get("inquiry_card")) if hasattr(chunk, 'data') and isinstance(chunk.data, dict) else False,
                        "has_pending_responses": bool(chunk.data.get("pending_responses")) if hasattr(chunk, 'data') and isinstance(chunk.data, dict) else False,
                        "pending_resp_count": len(chunk.data.get("pending_responses", []) or []) if hasattr(chunk, 'data') and isinstance(chunk.data, dict) else None,
                        "nodes": list(chunk.data.keys()) if hasattr(chunk, 'data') and isinstance(chunk.data, dict) else None,
                    },
                )

                yield f"data: {json.dumps(chunk_data, ensure_ascii=False, default=str)}\n\n"
                
                if request.stream_mode == "values":
                    final_state = chunk.data if hasattr(chunk, 'data') else chunk
                elif request.stream_mode == "updates":
                    if isinstance(chunk.data, dict):
                        for node_name, node_update in chunk.data.items():
                            if isinstance(node_update, dict):
                                state.update(node_update)
                                _append_debug_log(
                                    run_id="sdk-version",
                                    hypothesis_id="H2",
                                    location="api/stream.py:chat_stream:updates_merge",
                                    message="Merging stream update via SDK",
                                    data={
                                        "node": node_name,
                                        "has_inquiry_card": bool(node_update.get("inquiry_card")),
                                        "pending_resp_count": len(node_update.get("pending_responses", []) or []),
                                        "onboarding_completed": node_update.get("onboarding_completed"),
                                        "next_action": node_update.get("next_action"),
                                    },
                                )
                    final_state = state
                    
                    if isinstance(chunk.data, dict):
                        for node_name, node_update in chunk.data.items():
                            if isinstance(node_update, dict) and "messages" in node_update:
                                messages = node_update["messages"]
                                if messages:
                                    last_msg = messages[-1]
                                    if hasattr(last_msg, "content") and last_msg.content:
                                        info = {
                                            "type": "info",
                                            "node": node_name,
                                            "message": f"Agent 回复: {last_msg.content[:100]}..."
                                        }
                                        yield f"data: {json.dumps(info, ensure_ascii=False)}\n\n"
                                    elif hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                                        tool_names = [tc.get("name", "unknown") for tc in last_msg.tool_calls]
                                        info = {
                                            "type": "info",
                                            "node": node_name,
                                            "message": f"调用工具: {', '.join(tool_names)}"
                                        }
                                        yield f"data: {json.dumps(info, ensure_ascii=False)}\n\n"
            
            if final_state is None:
                final_state = state
            
            background_tasks.add_task(_run_maintenance_tasks_sdk, request.session_id, thread_id)
            
            _append_debug_log(
                run_id="sdk-version",
                hypothesis_id="H2",
                location="api/stream.py:chat_stream:final_state",
                message="Final state before stream completion via SDK",
                data={
                    "has_pending_responses": bool(final_state.get("pending_responses")),
                    "pending_resp_count": len(final_state.get("pending_responses", []) or []),
                    "pending_first_has_card": bool(final_state.get("pending_responses", [{}])[0].get("inquiry_card")) if final_state.get("pending_responses") else False,
                    "state_has_inquiry_card": bool(final_state.get("inquiry_card")),
                    "onboarding_completed": final_state.get("onboarding_completed"),
                    "next_action": final_state.get("next_action"),
                },
            )
            
            completion = {
                "type": "done",
                "message": "流式执行完成",
                "final_state": {
                    "message_count": len(final_state.get("messages", [])),
                    "has_response": bool(final_state.get("pending_responses")),
                }
            }
            yield f"data: {json.dumps(completion, ensure_ascii=False, default=str)}\n\n"
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"[Stream SDK] Error: {error_trace}")
            
            error_data = {
                "type": "error",
                "error": str(e),
                "traceback": error_trace
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        background=background_tasks,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
