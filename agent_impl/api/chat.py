import json
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, Literal, Any, Union, List

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


class ImageInfo(BaseModel):
    image_url: Optional[str] = None
    ocr_result: Optional[str] = None
    screenshot_type: Optional[str] = None



class ChatRequest(BaseModel):
    message: str = ""
    session_id: str
    images: Optional[List[ImageInfo]] = None
    feedback_mode: Optional[FeedbackModeInput] = None
    resume_payload: Optional[Union[dict[str, Any], str]] = None
    resume: Optional[bool] = None

def _get_screenshot_label(screenshot_type: Optional[str]) -> str:
    labels = {
        "private_chat_screenshot": "私聊截图",
        "group_chat_screenshot": "群聊截图",
        "moments_screenshot": "朋友圈截图",
        "other_social_media_screenshot": "其他社媒截图",
        "universal_screenshot_analysis": "通用截图",
    }
    return labels.get(screenshot_type or "", "截图")


def _build_user_message_with_images(request: ChatRequest) -> str:
    final_message = request.message or ""
    if request.images:
        image_parts = []
        for img in request.images:
            if img.ocr_result:
                type_label = _get_screenshot_label(img.screenshot_type)
                image_parts.append(f"【{type_label}分析结果】\n{img.ocr_result}")

        if image_parts:
            final_message = "\n\n---\n\n".join(image_parts)
            if request.message:
                final_message += f"\n\n---\n\n用户补充说明：{request.message}"
    return final_message


def _extract_answers_from_resume_payload(resume_payload: Optional[Union[dict[str, Any], str]]) -> dict[str, Any]:
    if not isinstance(resume_payload, dict):
        return {}
    answers = resume_payload.get("answers")
    if isinstance(answers, dict):
        return answers
    return {k: v for k, v in resume_payload.items() if k != "answers"}


def _stringify_answer_value(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _build_resume_message_from_card(inquiry_card: dict[str, Any], answers: dict[str, Any]) -> str:
    questions = inquiry_card.get("questions") if isinstance(inquiry_card, dict) else None
    lines: list[str] = []

    if isinstance(questions, list):
        for q in questions:
            if not isinstance(q, dict):
                continue
            qid = str(q.get("id") or "").strip()
            if not qid or qid not in answers:
                continue
            label = str(q.get("title") or q.get("question") or qid)
            lines.append(f"{label}：{_stringify_answer_value(answers.get(qid))}")

    if not lines:
        for k, v in (answers or {}).items():
            lines.append(f"{k}：{_stringify_answer_value(v)}")

    if not lines:
        return "用户已提交补充信息"
    return "\n\n".join(lines)


def _is_valid_inquiry_card(card: Any) -> bool:
    if not isinstance(card, dict):
        return False
    questions = card.get("questions")
    return isinstance(questions, list) and len(questions) > 0


def _answers_fingerprint(answers: dict[str, Any]) -> str:
    if not isinstance(answers, dict) or not answers:
        return ""
    canonical = json.dumps(answers, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()



async def get_optional_user_dep(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    if credentials is None:
        return None
    from auth_utils import get_optional_user
    return await get_optional_user(credentials)


security_required = HTTPBearer()


async def get_required_user_dep(
    credentials: HTTPAuthorizationCredentials = Depends(security_required),
):
    from auth_utils import get_current_user
    return await get_current_user(credentials)


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

def _extract_inquiry_card_from_interrupt(final_state: dict) -> dict | None:
    interrupts = final_state.get("__interrupt__")
    if not isinstance(interrupts, list) or not interrupts:
        return None
    first = interrupts[0]
    if isinstance(first, dict):
        value = first.get("value")
    else:
        value = getattr(first, "value", None)
    return value if isinstance(value, dict) else None


def _extract_inquiry_card_from_chunk_interrupts(chunks: list[Any]) -> dict | None:
    for chunk in chunks:
        data = getattr(chunk, "data", None)
        if isinstance(data, dict):
            card = _extract_inquiry_card_from_interrupt(data)
            if isinstance(card, dict):
                return card
        if isinstance(chunk, dict):
            card = _extract_inquiry_card_from_interrupt(chunk)
            if isinstance(card, dict):
                return card
    return None


def _extract_inquiry_card_from_any(value: Any) -> dict | None:
    if value is None:
        return None

    if isinstance(value, dict):
        direct_card = value.get("inquiry_card")
        if isinstance(direct_card, dict):
            questions = direct_card.get("questions")
            if isinstance(questions, list) and questions:
                return direct_card

        pending = value.get("pending_responses")
        if isinstance(pending, list):
            for item in pending:
                if not isinstance(item, dict):
                    continue
                card = item.get("inquiry_card")
                if isinstance(card, dict):
                    questions = card.get("questions")
                    if isinstance(questions, list) and questions:
                        return card

        card = _extract_inquiry_card_from_interrupt(value)
        if card is not None:
            return card
        for v in value.values():
            found = _extract_inquiry_card_from_any(v)
            if found is not None:
                return found
        return None

    if isinstance(value, (list, tuple)):
        for v in value:
            found = _extract_inquiry_card_from_any(v)
            if found is not None:
                return found
        return None

    data_attr = getattr(value, "data", None)
    if data_attr is not None:
        found = _extract_inquiry_card_from_any(data_attr)
        if found is not None:
            return found

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            found = _extract_inquiry_card_from_any(model_dump())
            if found is not None:
                return found
        except Exception:
            pass

    as_dict = getattr(value, "dict", None)
    if callable(as_dict):
        try:
            found = _extract_inquiry_card_from_any(as_dict())
            if found is not None:
                return found
        except Exception:
            pass

    try:
        return _extract_inquiry_card_from_any(vars(value))
    except Exception:
        return None


@router.post("/chat")
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_required_user_dep),
):
    is_resume = bool(request.resume_payload) or bool(request.resume)
    has_images = bool(request.images)
    if not is_resume and not (request.message or "").strip() and not has_images:
        raise HTTPException(status_code=400, detail="message is required")
    if is_resume and request.resume_payload is None:
        raise HTTPException(status_code=400, detail="resume_payload is required when resume is true")

    final_message = _build_user_message_with_images(request) if not is_resume else ""
    message_preview = (final_message or "").strip()[:50] if not is_resume else ""
    logger.info(
        f"Received message from session {request.session_id}: {message_preview if not is_resume else '[resume]'}..."
    )

    from api.sdk_client import (
        ensure_thread_exists,
        get_thread_state,
        run_assistant,
        thread_has_pending_interrupt,
        update_thread_state,
    )
    from graph.state import create_initial_state
    
    user_id = current_user['user_id']
    thread_id = await ensure_thread_exists(request.session_id, user_id)
    onboarding_turn_count_before: int | None = None

    input_payload: Any = None
    resume_command: dict | None = None
    synthetic_resume = False
    if is_resume:
        base_state = get_thread_state(thread_id)
        if isinstance(base_state, dict):
            onboarding_turn_count_before = int(base_state.get("onboarding_turn_count", 0) or 0)
        has_pending_interrupt = thread_has_pending_interrupt(thread_id)
        logger.info(
            "Resume precheck: thread=%s, has_pending_interrupt=%s, state_has___interrupt__=%s, state_has_inquiry_card=%s",
            thread_id,
            has_pending_interrupt,
            bool(base_state.get("__interrupt__")) if isinstance(base_state, dict) else None,
            bool(base_state.get("inquiry_card")) if isinstance(base_state, dict) else None,
        )
        if has_pending_interrupt:
            resume_command = {"resume": request.resume_payload}
        else:
            synthetic_resume = True
            answers = _extract_answers_from_resume_payload(request.resume_payload)
            inquiry_card = base_state.get("inquiry_card") if isinstance(base_state, dict) else None
            if _is_valid_inquiry_card(inquiry_card):
                final_message = _build_resume_message_from_card(inquiry_card, answers)
            else:
                lines = [f"{k}：{_stringify_answer_value(v)}" for k, v in (answers or {}).items()]
                final_message = "\n\n".join(lines) if lines else "用户已提交补充信息"
            logger.warning(
                "Resume precheck failed: thread has no pending interrupt; using synthetic_resume fallback. thread=%s",
                thread_id,
            )
            state = dict(base_state or {})
            current_message_id = str(uuid.uuid4())
            state["user_message"] = final_message
            state["current_message_id"] = current_message_id
            state["_iteration_count"] = 0
            state["debug_log"] = []
            state["inquiry_card"] = None
            state["inquiry_answers"] = None
            state["pending_questions"] = []
            state["pending_responses"] = []
            state["last_response_for_continuity"] = None
            state["feedback_mode_input"] = request.feedback_mode.dict() if request.feedback_mode else None
            input_payload = state
        logger.info(f"Resume mode: thread={thread_id}, resume_payload_keys={list(request.resume_payload.keys()) if isinstance(request.resume_payload, dict) else type(request.resume_payload).__name__}")
    else:
        base_state = get_thread_state(thread_id)
        if isinstance(base_state, dict):
            onboarding_turn_count_before = int(base_state.get("onboarding_turn_count", 0) or 0)

        if base_state is None:
            logger.info(f"Creating new session for thread {thread_id} (checkpointer empty)")
            current_message_id = str(uuid.uuid4())
            state = create_initial_state(final_message, current_message_id=current_message_id)
            state["feedback_mode_input"] = request.feedback_mode.dict() if request.feedback_mode else None
        else:
            state = dict(base_state)
            current_message_id = str(uuid.uuid4())
            state["user_message"] = final_message
            state["current_message_id"] = current_message_id
            state["_iteration_count"] = 0
            state["debug_log"] = []
            state["inquiry_card"] = None
            state["inquiry_answers"] = None
            state["pending_questions"] = []
            state["pending_responses"] = []
            state["last_response_for_continuity"] = None
            state["feedback_mode_input"] = request.feedback_mode.dict() if request.feedback_mode else None
        input_payload = state

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
                "message_preview": (final_message or request.message or "")[:100],
                "use_stream": False,
                "user_id": user_id,
                "is_resume": is_resume,
                "synthetic_resume": synthetic_resume,
            },
        )
        
        chunks = []
        for chunk in run_assistant(thread_id, input_payload, stream_mode="values", command=resume_command):
            chunks.append(chunk)
        
        final_state: Any = {}
        if chunks:
            last_chunk = chunks[-1]
            data_attr = getattr(last_chunk, "data", None)
            if isinstance(data_attr, dict):
                final_state = data_attr
            elif isinstance(last_chunk, dict):
                final_state = last_chunk.get("data") or {}
        if not isinstance(final_state, dict):
            final_state = {}
        final_state = dict(final_state)

        inquiry_card = _extract_inquiry_card_from_chunk_interrupts(chunks)
        if inquiry_card is None:
            inquiry_card = _extract_inquiry_card_from_interrupt(final_state)
        if inquiry_card is not None:
            final_state["inquiry_card"] = inquiry_card
        else:
            final_state["inquiry_card"] = {"questions": []}
        has_interrupt = inquiry_card is not None
        onboarding_turn_count_after = int(final_state.get("onboarding_turn_count", 0) or 0)

        merged_patch_keys: list[str] = []
        tool_patch_log = final_state.get("tool_patch_log")
        if isinstance(tool_patch_log, list) and tool_patch_log:
            latest_patch = tool_patch_log[-1]
            if isinstance(latest_patch, dict):
                merged_patch_keys = sorted(str(k) for k in latest_patch.keys())
        
        if not has_interrupt:
            background_tasks.add_task(_run_maintenance_tasks_sdk, request.session_id, thread_id)
        
        pending_responses = final_state.get("pending_responses", [])
        feedback_prefill = final_state.get("feedback_prefill")
        feedback_status = final_state.get("feedback_status")
        feedback_question = final_state.get("feedback_question")
        
        # 仅透传真实 pending_responses，避免用户侧兜底文案掩盖流程问题。
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
                "has_interrupt": has_interrupt,
                "is_resume": is_resume,
                "synthetic_resume": synthetic_resume,
                "merged_patch_keys": merged_patch_keys,
                "has_inquiry_answers": bool(final_state.get("inquiry_answers")),
                "onboarding_turn_count_before": onboarding_turn_count_before,
                "onboarding_turn_count_after": onboarding_turn_count_after,
                "onboarding_completed": final_state.get("onboarding_completed"),
                "next_action": final_state.get("next_action"),
            },
        )
        # 注意：不要在这里手动把 messages 写回线程状态。
        # LangGraph 的 AgentState.messages 使用 add_messages reducer，会“追加合并”。
        # 如果我们每轮把“全量 messages”再写回一次，会导致消息数量近似翻倍增长，
        # 进而引发 response 体积膨胀、性能劣化，甚至 /threads/{id}/state 400。
        # 对话历史的持久化由 LangGraph + post_turn_finalize_node 负责（layer3_memory.all_messages）。
        
        if feedback_prefill and inquiry_card is None:
            try:
                update_thread_state(thread_id, {"feedback_prefill": None})
            except Exception:
                pass

        # 后台持久化本轮消息到 Supabase
        if user_id:
            from api.conversation_persist import persist_turn_messages
            background_tasks.add_task(
                persist_turn_messages,
                user_id=user_id,
                thread_id=thread_id,
                turn_id=current_message_id if not is_resume else (str(uuid.uuid4())),
                user_message=final_message if not is_resume else None,
                pending_responses=pending_responses,
                final_state=final_state,
                is_resume=is_resume,
                inquiry_card=inquiry_card,
            )

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
async def get_chat_history(thread_id: str, current_user=Depends(get_required_user_dep)):
    """
    历史消息读取接口。
    - 登录态：强制 thread 归属校验，优先从 Supabase 读取。
    """
    user_id = current_user['user_id']
    logger.info(f"get_chat_history request: thread_id={thread_id}, user={user_id}")

    # 强制 thread 归属校验
    from supabase_service.client import get_thread_by_user
    user_thread = await get_thread_by_user(user_id)
    if not user_thread or user_thread['thread_id'] != thread_id:
        logger.warning(f"Security: User {user_id} accessing thread {thread_id} not bound to them.")
        raise HTTPException(status_code=403, detail="Thread does not belong to this user")

    try:
        # 优先尝试从 Supabase 读取（仅在表存在且有数据时使用）
        supabase_ok = False
        try:
            from supabase_service.conversation import (
                get_conversation_by_thread,
                get_messages,
                get_messages_count,
                upsert_conversation,
                backfill_from_langgraph_state,
            )
            from supabase_service.client import is_supabase_configured

            if is_supabase_configured():
                conv = await get_conversation_by_thread(thread_id)
                if not conv:
                    conv = await upsert_conversation(user_id, thread_id)

                if conv:
                    supabase_ok = True
                    msg_count = await get_messages_count(conv["id"])
                    if msg_count == 0:
                        from api.sdk_client import get_thread_state
                        state = get_thread_state(thread_id)
                        if state:
                            await backfill_from_langgraph_state(conv["id"], thread_id, state)

                    result = await get_messages(conv["id"], limit=200)
                    messages = result.get("messages", [])
                    clean_messages = []
                    for msg in messages:
                        role = msg.get("role", "")
                        content = msg.get("content", "")
                        kind = msg.get("kind", "chat_text")
                        metadata = msg.get("metadata")

                        if kind == "chat_text" and content and role in ("user", "assistant"):
                            clean_messages.append({"role": role, "content": content, "kind": kind})
                        elif kind in ("interrupt_inquiry", "inquiry_receipt", "system_task"):
                            clean_messages.append({
                                "role": role,
                                "content": content,
                                "kind": kind,
                                "metadata": metadata,
                            })

                    from api.sdk_client import get_thread_state
                    state = get_thread_state(thread_id)

                    logger.info(f"Returning {len(clean_messages)} messages from Supabase for thread {thread_id}")
                    return {
                        "success": True,
                        "messages": clean_messages,
                        "state": state,
                    }
        except Exception as e:
            logger.warning(f"Supabase conversation read failed (table may not exist): {e}")
            supabase_ok = False

        # Fallback: 从 LangGraph 读取
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
        
        logger.info(f"Returning {len(clean_messages)} messages (LangGraph fallback) for thread {thread_id}")
        return {
            "success": True, 
            "messages": clean_messages, 
            "state": state
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_chat_history failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
