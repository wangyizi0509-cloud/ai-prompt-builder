import json
import uuid
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, Literal

router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = PROJECT_ROOT / ".cursor" / "debug.log"


from utils.logger import get_logger

logger = get_logger("chat")
import time

class FeedbackModeInput(BaseModel):
    guide_id: str
    completion_status: Optional[Literal["success", "partial", "failed", "abandoned", "other"]] = None
    completion_detail: Optional[str] = ""


class ChatRequest(BaseModel):
    message: str
    session_id: str
    feedback_mode: Optional[FeedbackModeInput] = None


async def get_optional_user_dep(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    if credentials is None:
        return None
    from auth_utils import get_optional_user
    return await get_optional_user(credentials)


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
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
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
    from api.sdk_client import get_thread_state, update_thread_state
    from graph.archive_manager import (
        refine_on_onboarding_complete,
        compress_layer3,
        compress_task_reasoning,
        archive_guide_to_layer2,
        archive_status_to_layer2,
        archive_plan_to_layer2,
    )
    
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
                location="api/chat.py:_run_maintenance_tasks_sdk:start",
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
                location="api/chat.py:_run_maintenance_tasks_sdk:done",
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
                location="api/chat.py:_run_maintenance_tasks_sdk:failed",
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


@router.post("/chat")
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_optional_user_dep),
):
    logger.info(f"Received message from session {request.session_id}: {request.message[:50]}...")

    from api.sdk_client import (
        ensure_thread_exists,
        get_thread_state,
        run_assistant,
        update_thread_state,
    )
    from graph.state import create_initial_state
    
    user_id = current_user['user_id'] if current_user else None
    thread_id = await ensure_thread_exists(request.session_id, user_id)
    
    base_state = get_thread_state(thread_id)
    
    if base_state is None:
        logger.info(f"Creating new session for thread {thread_id} (checkpointer empty)")
        current_message_id = str(uuid.uuid4())
        state = create_initial_state(request.message, current_message_id=current_message_id)
        state["feedback_mode_input"] = request.feedback_mode.dict() if request.feedback_mode else None
    else:
        state = dict(base_state)
        current_message_id = str(uuid.uuid4())
        state["user_message"] = request.message
        state["current_message_id"] = current_message_id
        state["_iteration_count"] = 0
        state["debug_log"] = []
        state["inquiry_card"] = None
        state["pending_questions"] = []
        state["pending_responses"] = []
        state["last_response_for_continuity"] = None
        state["feedback_mode_input"] = request.feedback_mode.dict() if request.feedback_mode else None

    try:
        logger.debug(f"Invoking workflow via SDK for thread {thread_id}...")
        _append_debug_log(
            run_id="sdk-version",
            hypothesis_id="H3",
            location="api/chat.py:chat:entry",
            message="Enter chat endpoint via SDK",
            data={
                "session_id": request.session_id,
                "thread_id": thread_id,
                "message_preview": request.message[:100],
                "use_stream": False,
                "user_id": user_id,
            },
        )
        
        chunks = []
        for chunk in run_assistant(thread_id, state, stream_mode="values"):
            chunks.append(chunk)
        
        final_state = chunks[-1].data if chunks else {}
        
        background_tasks.add_task(_run_maintenance_tasks_sdk, request.session_id, thread_id)
        
        pending_responses = final_state.get("pending_responses", [])
        feedback_prefill = final_state.get("feedback_prefill")
        feedback_status = final_state.get("feedback_status")
        feedback_question = final_state.get("feedback_question")
        
        # 兼容旧逻辑：如果 pending_responses 为空，但有 response 字段（虽然这种情况在 SDK 模式下较少见）
        # 或者为了前端兼容性，我们仍然构建一个 response 字符串
        if pending_responses:
            combined_response = "\n\n".join([r["content"] for r in pending_responses if r.get("content")])
        else:
            combined_response = ""
        
        _append_debug_log(
            run_id="sdk-version",
            hypothesis_id="H1",
            location="api/chat.py:chat:final_state",
            message="Final state before response via SDK",
            data={
                "has_pending_responses": bool(pending_responses),
                "pending_resp_count": len(pending_responses),
                "pending_first_has_card": bool(pending_responses[0].get("inquiry_card")) if pending_responses else False,
                "state_has_inquiry_card": bool(final_state.get("inquiry_card")),
                "onboarding_completed": final_state.get("onboarding_completed"),
                "next_action": final_state.get("next_action"),
            },
        )
        # 注意：不要在这里手动把 messages 写回线程状态。
        # LangGraph 的 AgentState.messages 使用 add_messages reducer，会“追加合并”。
        # 如果我们每轮把“全量 messages”再写回一次，会导致消息数量近似翻倍增长，
        # 进而引发 response 体积膨胀、性能劣化，甚至 /threads/{id}/state 400。
        # 对话历史的持久化由 LangGraph + post_turn_finalize_node 负责（layer3_memory.all_messages）。
        
        if feedback_prefill:
            try:
                update_thread_state(thread_id, {"feedback_prefill": None})
            except Exception:
                pass

        # 构造标准响应
        # 优先使用 pending_responses (结构化消息)
        # 同时也填充 response 字段作为 fallback
        return {
            "response": combined_response,  # Fallback for legacy clients
            "pending_responses": pending_responses, # Structured messages
            "state": final_state,
            "feedback_prefill": feedback_prefill,
            "feedback_status": feedback_status,
            "feedback_question": feedback_question,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/history/{thread_id}")
async def get_chat_history(thread_id: str, current_user=Depends(get_optional_user_dep)):
    logger.info(f"get_chat_history request: thread_id={thread_id}, user={current_user['user_id'] if current_user else 'anonymous'}")
    
    if current_user:
        from supabase_service.client import get_thread_by_user
        user_thread = await get_thread_by_user(current_user['user_id'])
        if not user_thread or user_thread['thread_id'] != thread_id:
            logger.warning(f"Security: User {current_user['user_id']} accessing thread {thread_id} not bound to them.")
    
    try:
        from api.sdk_client import get_thread_state
        t0 = time.perf_counter()
        state = get_thread_state(thread_id)
        t1 = time.perf_counter()
        logger.info(f"State fetched for thread {thread_id} in {int((t1 - t0)*1000)}ms")
        if not state:
            logger.info(f"No state found for thread {thread_id}")
            return {"success": True, "messages": [], "state": None}
            
        if "messages" not in state and not (isinstance(state.get("layer3_memory"), dict) and isinstance(state["layer3_memory"].get("all_messages"), list)):
            logger.info(f"State found but no messages for thread {thread_id}")
            return {"success": True, "messages": [], "state": state}
        
        messages = state["messages"] if isinstance(state.get("messages"), list) else []
        if not messages and isinstance(state.get("layer3_memory"), dict):
            alt = state["layer3_memory"].get("all_messages")
            messages = alt if isinstance(alt, list) else []
        clean_messages = []
        for msg in messages:
            role = ""
            content = ""
            if isinstance(msg, dict):
                role = msg.get("role") or (msg.get("type") if msg.get("type") in ["human", "ai"] else "")
                content = msg.get("content")
            else:
                role = "user" if msg.type == "human" else ("assistant" if msg.type == "ai" else "")
                content = getattr(msg, "content", "")

            if content and role in ["user", "assistant", "human", "ai"]:
                normalized_role = "user" if role in ["user", "human"] else "assistant"
                cleaned_content = content
                if isinstance(content, str):
                    s = content.strip()
                    if s.startswith("```"):
                        try:
                            first_nl = s.find("\n")
                            body = s[first_nl + 1 :] if first_nl != -1 else s
                            end_idx = body.rfind("```")
                            if end_idx != -1:
                                body = body[:end_idx]
                            s = body.strip()
                        except Exception:
                            pass
                    try:
                        obj = json.loads(s)
                        if isinstance(obj, dict) and isinstance(obj.get("response"), str):
                            cleaned_content = obj.get("response")
                    except Exception:
                        cleaned_content = content
                clean_messages.append({"role": normalized_role, "content": cleaned_content})
        
        logger.info(f"Returning {len(clean_messages)} messages for thread {thread_id}")
        return {
            "success": True, 
            "messages": clean_messages, 
            "state": state
        }
    except Exception as e:
        logger.error(f"get_chat_history failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
