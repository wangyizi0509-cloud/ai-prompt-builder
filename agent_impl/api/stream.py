import json
import uuid
import hashlib
import logging
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Literal, Optional, Any, Union

router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


class FeedbackModeInput(BaseModel):
    guide_id: str
    completion_status: Optional[Literal["success", "partial", "failed", "abandoned", "other"]] = None
    completion_detail: Optional[str] = ""


class StreamChatRequest(BaseModel):
    message: str = ""
    session_id: str
    stream_mode: Literal["values", "updates", "messages", "debug"] = "updates"
    feedback_mode: Optional[FeedbackModeInput] = None
    resume_payload: Optional[Union[dict[str, Any], str]] = None
    resume: Optional[bool] = None


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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = PROJECT_ROOT / ".cursor" / "debug.log"


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
    from api.sdk_client import get_thread_state, update_thread_state
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


def _extract_inquiry_card_from_chunks(chunks: list[Any]) -> dict | None:
    for chunk in chunks:
        found = _extract_inquiry_card_from_any(chunk)
        if found is not None:
            return found
    return None


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return _jsonable(dumped)
    as_dict = getattr(value, "dict", None)
    if callable(as_dict):
        dumped = as_dict()
        return _jsonable(dumped)
    as_dict = getattr(value, "dict", None)
    if isinstance(as_dict, dict):
        return _jsonable(as_dict)
    try:
        return _jsonable(vars(value))
    except Exception:
        return str(value)


def _dump_stream_chunk(chunk: Any) -> dict[str, Any]:
    if isinstance(chunk, dict):
        return _jsonable(chunk)
    model_dump = getattr(chunk, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return _jsonable(dumped) if isinstance(dumped, dict) else {"value": _jsonable(dumped)}
    as_dict = getattr(chunk, "dict", None)
    if callable(as_dict):
        dumped = as_dict()
        return _jsonable(dumped) if isinstance(dumped, dict) else {"value": _jsonable(dumped)}
    try:
        dumped = vars(chunk)
        return _jsonable(dumped) if isinstance(dumped, dict) else {"value": _jsonable(dumped)}
    except Exception:
        return {"value": str(chunk)}


@router.post("/chat/stream")
async def chat_stream(
    request: StreamChatRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_optional_user_dep),
):
    """
    流式聊天接口 - 实时查看 Agent 执行过程（通过 SDK）
    """
    logger.info(
        "[Stream SDK] Received message: session=%s, message_len=%s",
        request.session_id,
        len(request.message or ""),
    )
    logger.info("[Stream SDK] Stream mode: %s", request.stream_mode)
    
    from api.sdk_client import (
        ensure_thread_exists,
        get_thread_state,
        run_assistant,
    )
    from graph.state import create_initial_state
    
    user_id = current_user['user_id'] if current_user else None
    thread_id = await ensure_thread_exists(request.session_id, user_id)
    onboarding_turn_count_before: int | None = None

    is_resume = bool(request.resume_payload) or bool(request.resume)
    if not is_resume and not (request.message or "").strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="message is required")
    if is_resume and request.resume_payload is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="resume_payload is required when resume is true")

    input_payload: Any
    if is_resume:
        from langgraph.types import Command
        base_state = get_thread_state(thread_id)
        synthetic_resume = False
        if isinstance(base_state, dict):
            onboarding_turn_count_before = int(base_state.get("onboarding_turn_count", 0) or 0)
        state_inquiry_card = base_state.get("inquiry_card") if isinstance(base_state, dict) else None
        if isinstance(base_state, dict) and _is_valid_inquiry_card(state_inquiry_card):
            synthetic_resume = True
            answers = _extract_answers_from_resume_payload(request.resume_payload)
            resume_message = _build_resume_message_from_card(state_inquiry_card, answers)
            current_message_id = str(uuid.uuid4())
            state = dict(base_state)
            state["user_message"] = resume_message
            state["current_message_id"] = current_message_id
            state["debug_log"] = []
            state["inquiry_answers"] = request.resume_payload
            state["inquiry_card"] = None
            state["pending_questions"] = []
            state["pending_responses"] = []
            state["last_response_for_continuity"] = None

            collected_info = state.get("collected_info") if isinstance(state.get("collected_info"), dict) else {}
            raw_inputs = list(collected_info.get("raw_inputs") or [])
            if resume_message and resume_message not in raw_inputs:
                raw_inputs.append(resume_message)
            merged_collected = {
                **collected_info,
                "raw_inputs": raw_inputs,
                "user_profile": collected_info.get("user_profile") if isinstance(collected_info.get("user_profile"), dict) else {},
                "crush_profile": collected_info.get("crush_profile") if isinstance(collected_info.get("crush_profile"), dict) else {},
                "pain_points": collected_info.get("pain_points") if isinstance(collected_info.get("pain_points"), list) else [],
            }
            state["collected_info"] = merged_collected

            if answers:
                state["onboarding_turn_count"] = int(state.get("onboarding_turn_count", 0) or 0) + 1
                state["onboarding_last_answer_fingerprint"] = _answers_fingerprint(answers)

            input_payload = state
        else:
            input_payload = Command(resume=request.resume_payload)
    else:
        base_state = get_thread_state(thread_id)
        if isinstance(base_state, dict):
            onboarding_turn_count_before = int(base_state.get("onboarding_turn_count", 0) or 0)

        if base_state is None:
            logger.info("[Stream SDK] Creating new session (checkpointer empty)")
            current_message_id = str(uuid.uuid4())
            state = create_initial_state(request.message, current_message_id=current_message_id)
            state["feedback_mode_input"] = request.feedback_mode.dict() if request.feedback_mode else None
        else:
            logger.info("[Stream SDK] Restoring existing session (checkpointer)")
            state = dict(base_state)
            current_message_id = str(uuid.uuid4())
            state["user_message"] = request.message
            state["current_message_id"] = current_message_id
            state["debug_log"] = []
            state["inquiry_card"] = None
            state["inquiry_answers"] = None
            state["pending_questions"] = []
            state["pending_responses"] = []
            state["last_response_for_continuity"] = None
            state["feedback_mode_input"] = request.feedback_mode.dict() if request.feedback_mode else None
        input_payload = state
    
    async def generate_stream():
        """生成流式响应"""
        final_state = None
        interrupt_sent = False
        merged_patch_keys: list[str] = []
        try:
            for chunk in run_assistant(thread_id, input_payload, stream_mode=request.stream_mode):
                final_state = getattr(chunk, "data", None)
                if final_state is None and isinstance(chunk, dict):
                    final_state = chunk.get("data")
                yield f"data: {json.dumps(_dump_stream_chunk(chunk), ensure_ascii=False)}\n\n"

                if not interrupt_sent and isinstance(final_state, dict):
                    inquiry_card = _extract_inquiry_card_from_any(final_state)
                    if inquiry_card is None:
                        inquiry_card = _extract_inquiry_card_from_any(chunk)
                    if inquiry_card is not None:
                        interrupt_sent = True
                        yield f"data: {json.dumps({'type': 'interrupt', 'inquiry_card': inquiry_card}, ensure_ascii=False)}\n\n"

                    tool_patch_log = final_state.get("tool_patch_log")
                    if isinstance(tool_patch_log, list) and tool_patch_log:
                        latest_patch = tool_patch_log[-1]
                        if isinstance(latest_patch, dict):
                            merged_patch_keys = sorted(str(k) for k in latest_patch.keys())
            
            # 后台运行维护任务
            if not interrupt_sent:
                background_tasks.add_task(_run_maintenance_tasks_sdk, request.session_id, thread_id)

            if isinstance(final_state, dict):
                _append_debug_log(
                    run_id="sdk-version-stream",
                    hypothesis_id="S1",
                    location="api/stream.py:chat_stream:final_state",
                    message="Final stream state before completion",
                    data={
                        "is_resume": is_resume,
                        "synthetic_resume": synthetic_resume if is_resume else False,
                        "has_interrupt": interrupt_sent,
                        "merged_patch_keys": merged_patch_keys,
                        "has_inquiry_answers": bool(final_state.get("inquiry_answers")),
                        "onboarding_turn_count_before": onboarding_turn_count_before,
                        "onboarding_turn_count_after": int(final_state.get("onboarding_turn_count", 0) or 0),
                    },
                )
                
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Stream generation failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
