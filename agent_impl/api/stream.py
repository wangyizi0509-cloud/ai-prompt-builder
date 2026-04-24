import json
import uuid
import hashlib
import logging
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Literal, Optional, Any, Union

from api.display_events import (
    SeqAllocator,
    DisplayNodeCollector,
    build_reasoning_node,
    build_tool_call_node,
    build_ai_intermediate_node,
    build_report_card_node,
    build_inquiry_node,
    build_subgraph_thinking_node,
    build_final_response_node,
    get_tool_label,
)
from api.onboarding_handoff_prompt import (
    OnboardingPayload,
    render_onboarding_first_turn_message,
)
from api.chat import _is_first_turn_for_thread

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
    inquiry_receipt_payload: Optional[dict[str, Any]] = None
    # Onboarding v2：付费后首轮前端自动触发时携带。后端会用固定模板渲染为
    # 完整 user_message（系统指令 + 诊断素材），main_agent 首轮立即调
    # call_status_agent。仅首轮生效，非首轮即使前端误传也被忽略。
    # 详见 onboarding_v2/API_CONTRACT.md §4。
    onboarding_payload: Optional[OnboardingPayload] = None
    device_id: Optional[str] = None


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
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    from auth_utils import get_optional_user
    return await get_optional_user(request, credentials)


security_required = HTTPBearer(auto_error=False)


async def get_required_user_dep(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_required),
):
    from auth_utils import get_current_user
    return await get_current_user(request, credentials)


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

            if task_type == "layer3_compress":
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

# ---------------------------------------------------------------------------
# report_kind → report_type 映射 (graph 事件用 status_report/action_plan/action_guide,
# DisplayNode 用 status/plan/guide)
# ---------------------------------------------------------------------------
_REPORT_KIND_TO_TYPE: dict[str, str] = {
    "status_report": "status",
    "action_plan": "plan",
    "action_guide": "guide",
}


def _derive_turn_seq(base_state: dict | None) -> int:
    """从 base_state 中推算一个简单的轮次序号。"""
    if not isinstance(base_state, dict):
        return 1
    l3 = base_state.get("layer3_memory")
    if isinstance(l3, dict):
        all_msgs = l3.get("all_messages")
        if isinstance(all_msgs, list):
            # 粗略用已有消息数 / 2 作轮次近似，保底为 1
            return max(len(all_msgs) // 2, 1)
    return max(int(base_state.get("onboarding_turn_count", 0) or 0), 1)


def _enrich_process_event(
    event_data: dict[str, Any],
    *,
    seq_alloc: SeqAllocator,
    turn_id: str,
    collector: DisplayNodeCollector,
    reasoning_counter: list[int],
    ai_msg_counter: list[int],
    tool_call_counter: list[int],
) -> dict[str, Any]:
    """
    为一个 process_event 注入 DisplayNode 统一展示字段，
    同时 upsert 到 collector。返回增强后的 event dict（原字段保留）。
    """
    event_type = event_data.get("event_type", "")
    enriched = dict(event_data)  # 浅拷贝，保留原始字段

    try:
        if event_type == "reasoning":
            idx = reasoning_counter[0]
            reasoning_counter[0] += 1
            node = build_reasoning_node(
                seq=seq_alloc.next_seq(),
                turn_id=turn_id,
                part_index=idx,
                content=event_data.get("content", ""),
            )
            collector.upsert(node)
            enriched.update({
                "seq": node["seq"],
                "turn_id": turn_id,
                "node_id": node["nodeId"],
                "node_type": node["nodeType"],
                "payload": node["payload"],
            })

        elif event_type == "tool_call":
            status = event_data.get("status", "loading")
            tool_name = event_data.get("tool_name", "")
            tool_call_id = event_data.get("tool_call_id", "")
            mapped_status = "loading" if status in ("calling", "loading") else ("error" if status == "error" else "done")
            node = build_tool_call_node(
                seq=seq_alloc.next_seq(),
                turn_id=turn_id,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                status=mapped_status,
                args_preview=event_data.get("args_preview", ""),
                result_summary=event_data.get("result_summary", ""),
                local_counter=tool_call_counter[0],
            )
            if mapped_status == "loading":
                tool_call_counter[0] += 1
            collector.upsert(node)
            enriched.update({
                "seq": node["seq"],
                "turn_id": turn_id,
                "node_id": node["nodeId"],
                "node_type": node["nodeType"],
                "status": node.get("status", "loading"),
                "payload": node["payload"],
            })

        elif event_type in ("ai_message", "ai_intermediate"):
            idx = ai_msg_counter[0]
            ai_msg_counter[0] += 1
            node = build_ai_intermediate_node(
                seq=seq_alloc.next_seq(),
                turn_id=turn_id,
                part_index=idx,
                content=event_data.get("content", ""),
            )
            collector.upsert(node)
            enriched.update({
                "seq": node["seq"],
                "turn_id": turn_id,
                "node_id": node["nodeId"],
                "node_type": node["nodeType"],
                "payload": node["payload"],
            })

        elif event_type == "subgraph_thinking":
            idx = ai_msg_counter[0]
            ai_msg_counter[0] += 1
            source = event_data.get("source", "unknown_agent")
            node = build_subgraph_thinking_node(
                seq=seq_alloc.next_seq(),
                turn_id=turn_id,
                part_index=idx,
                content=event_data.get("content", ""),
                source=source,
            )
            collector.upsert(node)
            enriched.update({
                "seq": node["seq"],
                "turn_id": turn_id,
                "node_id": node["nodeId"],
                "node_type": node["nodeType"],
                "source": source,
                "payload": node["payload"],
            })

        elif event_type == "report_card":
            report_type = event_data.get("report_type", "")
            status_val = event_data.get("status", "loading")
            report_id = event_data.get("report_id", "")
            node = build_report_card_node(
                seq=seq_alloc.next_seq(),
                turn_id=turn_id,
                report_type=report_type,
                report_id=report_id,
                status=status_val,
            )
            collector.upsert(node)
            enriched.update({
                "seq": node["seq"],
                "turn_id": turn_id,
                "node_id": node["nodeId"],
                "node_type": node["nodeType"],
                "status": status_val,
                "payload": node["payload"],
            })

        elif event_type == "report_ready":
            report_kind = event_data.get("report_kind", "")
            report_type = _REPORT_KIND_TO_TYPE.get(report_kind, report_kind)
            report_id = event_data.get("report_id", "")
            node = build_report_card_node(
                seq=seq_alloc.next_seq(),
                turn_id=turn_id,
                report_type=report_type,
                report_id=report_id,
                status="done",
                tool_call_id=event_data.get("task_key", ""),
            )
            collector.upsert(node)
            enriched.update({
                "seq": node["seq"],
                "turn_id": turn_id,
                "node_id": node["nodeId"],
                "node_type": node["nodeType"],
                "status": "done",
                "payload": node["payload"],
            })

    except Exception:
        # 展示字段注入失败不能影响主流程
        logger.debug("Failed to enrich process_event: %s", event_type, exc_info=True)

    return enriched


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
    # langgraph_sdk StreamPart is a NamedTuple with .event and .data fields
    event = getattr(chunk, "event", None)
    data = getattr(chunk, "data", None)
    if event is not None:
        return _jsonable({"event": event, "data": data})
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

    Onboarding v2 本期默认无登录,因此采用可选鉴权(与 /api/chat 对齐):
    - 有 token + 验证通过 → current_user 为 dict
    - 无 token / 无效 → current_user 为 None,user_id 回退到 session_id
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
        thread_has_pending_interrupt,
    )
    from graph.state import create_initial_state
    
    # Onboarding v2 本期支持匿名入口:current_user 可能为 None
    user_id = current_user['user_id'] if isinstance(current_user, dict) else None
    thread_id = await ensure_thread_exists(request.session_id, user_id)
    onboarding_turn_count_before: int | None = None

    is_resume = bool(request.resume_payload) or bool(request.resume)
    has_onboarding_payload = request.onboarding_payload is not None
    if (
        not is_resume
        and not (request.message or "").strip()
        and not has_onboarding_payload
    ):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="message is required")
    if is_resume and request.resume_payload is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="resume_payload is required when resume is true")

    # Resume 不属于"首轮",onboarding_payload 一律忽略
    if is_resume and request.onboarding_payload is not None:
        request.onboarding_payload = None

    input_payload: Any = None
    resume_command: dict | None = None
    synthetic_resume = False
    if is_resume:
        base_state = get_thread_state(thread_id)
        if isinstance(base_state, dict):
            onboarding_turn_count_before = int(base_state.get("onboarding_turn_count", 0) or 0)
        has_pending_interrupt = thread_has_pending_interrupt(thread_id)
        logger.info(
            "[Stream SDK] Resume precheck: thread=%s, has_pending_interrupt=%s, state_has___interrupt__=%s, state_has_inquiry_card=%s",
            thread_id,
            has_pending_interrupt,
            bool(base_state.get("__interrupt__")) if isinstance(base_state, dict) else None,
            bool(base_state.get("inquiry_card")) if isinstance(base_state, dict) else None,
        )
        if has_pending_interrupt:
            resume_value: Any = request.resume_payload
            resume_value_normalized: Any = resume_value
            if isinstance(resume_value, dict):
                resume_value_normalized = _extract_answers_from_resume_payload(resume_value)
                logger.info(
                    "[Stream SDK] Resume payload normalized: thread=%s, wrapper=%s, answer_key_count=%s, fp=%s",
                    thread_id,
                    "answers" in resume_value,
                    len(resume_value_normalized) if isinstance(resume_value_normalized, dict) else None,
                    _answers_fingerprint(resume_value_normalized) if isinstance(resume_value_normalized, dict) else "",
                )
            else:
                logger.info(
                    "[Stream SDK] Resume payload normalized: thread=%s, type=%s",
                    thread_id,
                    type(resume_value).__name__,
                )
            resume_command = {"resume": resume_value_normalized}
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
                "[Stream SDK] Resume precheck failed: thread has no pending interrupt; using synthetic_resume fallback. thread=%s",
                thread_id,
            )
            state = dict(base_state or {})
            current_message_id = str(uuid.uuid4())
            state["user_message"] = final_message
            state["current_message_id"] = current_message_id
            state["debug_log"] = []
            state["inquiry_card"] = None
            state["inquiry_answers"] = None
            state["pending_questions"] = []
            state["pending_responses"] = []
            state["last_response_for_continuity"] = None
            state["feedback_mode_input"] = request.feedback_mode.dict() if request.feedback_mode else None
            input_payload = state
    else:
        base_state = get_thread_state(thread_id)
        if isinstance(base_state, dict):
            onboarding_turn_count_before = int(base_state.get("onboarding_turn_count", 0) or 0)

        # Onboarding v2 衔接：仅首轮允许 onboarding_payload。非首轮忽略。
        is_first_turn = _is_first_turn_for_thread(base_state)
        use_onboarding_payload = is_first_turn and request.onboarding_payload is not None
        if not is_first_turn and request.onboarding_payload is not None:
            logger.info(
                "[Stream SDK] Ignoring onboarding_payload on non-first turn: thread=%s",
                thread_id,
            )
            request.onboarding_payload = None

        if use_onboarding_payload:
            final_message = render_onboarding_first_turn_message(request.onboarding_payload)
            logger.info(
                "[Stream SDK] First-turn onboarding_payload rendered: thread=%s, msg_len=%d",
                thread_id,
                len(final_message),
            )
        else:
            final_message = request.message

        if base_state is None:
            logger.info("[Stream SDK] Creating new session (checkpointer empty)")
            current_message_id = str(uuid.uuid4())
            state = create_initial_state(final_message, current_message_id=current_message_id)
            state["feedback_mode_input"] = request.feedback_mode.dict() if request.feedback_mode else None
        else:
            logger.info("[Stream SDK] Restoring existing session (checkpointer)")
            state = dict(base_state)
            current_message_id = str(uuid.uuid4())
            state["user_message"] = final_message
            state["current_message_id"] = current_message_id
            state["debug_log"] = []
            state["inquiry_card"] = None
            state["inquiry_answers"] = None
            state["pending_questions"] = []
            state["pending_responses"] = []
            state["last_response_for_continuity"] = None
            state["feedback_mode_input"] = request.feedback_mode.dict() if request.feedback_mode else None
        input_payload = state

    # 用于在流结束后做持久化
    _stream_turn_id = current_message_id if (not is_resume or synthetic_resume) else str(uuid.uuid4())
    # 持久化场景下的"用户原话":首轮 onboarding 自动触发没有用户原话,存空串
    _stream_user_message = (
        request.message if (not is_resume and not has_onboarding_payload) else None
    )

    async def generate_stream():
        """生成流式响应"""
        final_state = None
        last_dict_state = None
        accumulated_pending_responses: list = []  # 跨节点累积，updates 模式下各节点分别写
        # updates 模式下各节点分散写入，需跨节点累积关键状态字段供前端 processStateUpdate 使用
        _STATE_FIELDS_TO_ACCUMULATE = (
            "onboarding_completed", "pending_crushe_guide", "preliminary_assessment",
            "onboarding_turn_count", "onboarding_max_turns",
            "status_report", "action_plan", "action_guides",
            "layer2_memory",
        )
        accumulated_state_fields: dict = {}
        interrupt_sent = False
        merged_patch_keys: list[str] = []
        detected_inquiry_card = None
        process_events: list[dict] = []

        # --- DisplayNode 统一展示字段初始化 ---
        _display_turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        _display_turn_seq = _derive_turn_seq(base_state if isinstance(base_state, dict) else None)
        _seq_alloc = SeqAllocator(_display_turn_seq)
        _node_collector = DisplayNodeCollector()
        # 可变计数器（list 包装以便闭包内修改）
        _reasoning_counter = [0]
        _ai_msg_counter = [0]
        _tool_call_counter = [0]
        try:
            for chunk in run_assistant(
                thread_id,
                input_payload,
                stream_mode=request.stream_mode,
                command=resume_command,
                device_id=request.device_id,
            ):
                # 识别并转发 custom 事件（get_stream_writer 发出的中间过程事件）
                chunk_event = getattr(chunk, "event", None)
                chunk_data = getattr(chunk, "data", None)
                if chunk_event == "custom" and isinstance(chunk_data, dict):
                    enriched = _enrich_process_event(
                        chunk_data,
                        seq_alloc=_seq_alloc,
                        turn_id=_display_turn_id,
                        collector=_node_collector,
                        reasoning_counter=_reasoning_counter,
                        ai_msg_counter=_ai_msg_counter,
                        tool_call_counter=_tool_call_counter,
                    )
                    process_events.append(enriched)
                    yield f"data: {json.dumps({'type': 'process_event', 'payload': enriched}, ensure_ascii=False)}\n\n"
                    continue

                final_state = getattr(chunk, "data", None)
                if final_state is None and isinstance(chunk, dict):
                    final_state = chunk.get("data")
                if isinstance(final_state, dict):
                    last_dict_state = final_state
                    # updates 模式：data 是节点 patch dict，各节点可能分别携带 pending_responses 和关键状态字段
                    if chunk_event == "updates":
                        for _node_patch in final_state.values():
                            if isinstance(_node_patch, dict):
                                _pr = _node_patch.get("pending_responses")
                                if isinstance(_pr, list) and _pr:
                                    accumulated_pending_responses.extend(_pr)
                                # 累积需要透传给前端 processStateUpdate 的关键状态字段
                                for _sf in _STATE_FIELDS_TO_ACCUMULATE:
                                    if _sf in _node_patch:
                                        if _sf == "layer2_memory" and isinstance(_node_patch[_sf], dict):
                                            existing = accumulated_state_fields.get("layer2_memory")
                                            if isinstance(existing, dict):
                                                existing.update(_node_patch[_sf])
                                            else:
                                                accumulated_state_fields[_sf] = dict(_node_patch[_sf])
                                        else:
                                            accumulated_state_fields[_sf] = _node_patch[_sf]
                yield f"data: {json.dumps(_dump_stream_chunk(chunk), ensure_ascii=False)}\n\n"

                if not interrupt_sent and isinstance(final_state, dict):
                    inquiry_card = _extract_inquiry_card_from_any(final_state)
                    if inquiry_card is None:
                        inquiry_card = _extract_inquiry_card_from_any(chunk)
                    if inquiry_card is not None:
                        interrupt_sent = True
                        detected_inquiry_card = inquiry_card
                        # 构建 inquiry DisplayNode
                        _inquiry_task_key = inquiry_card.get("task_key", "")
                        _inquiry_node = build_inquiry_node(
                            seq=_seq_alloc.next_seq(),
                            turn_id=_display_turn_id,
                            task_key=_inquiry_task_key,
                            status="new",
                            payload=inquiry_card,
                        )
                        _node_collector.upsert(_inquiry_node)
                        _interrupt_payload = {
                            'type': 'interrupt',
                            'inquiry_card': inquiry_card,
                            'seq': _inquiry_node["seq"],
                            'turn_id': _display_turn_id,
                            'node_id': _inquiry_node["nodeId"],
                            'node_type': _inquiry_node["nodeType"],
                            'status': 'new',
                        }
                        yield f"data: {json.dumps(_interrupt_payload, ensure_ascii=False)}\n\n"

                    tool_patch_log = final_state.get("tool_patch_log")
                    if isinstance(tool_patch_log, list) and tool_patch_log:
                        latest_patch = tool_patch_log[-1]
                        if isinstance(latest_patch, dict):
                            merged_patch_keys = sorted(str(k) for k in latest_patch.keys())
            
            # 后台运行维护任务
            if not interrupt_sent:
                background_tasks.add_task(_run_maintenance_tasks_sdk, request.session_id, thread_id)

            # 后台持久化本轮消息到 Supabase
            if user_id and last_dict_state:
                from api.conversation_persist import persist_stream_turn_messages
                persisted_state = dict(last_dict_state)
                if accumulated_state_fields:
                    persisted_state.update(accumulated_state_fields)
                if accumulated_pending_responses:
                    persisted_state["pending_responses"] = accumulated_pending_responses
                background_tasks.add_task(
                    persist_stream_turn_messages,
                    user_id=user_id,
                    thread_id=thread_id,
                    turn_id=_stream_turn_id,
                    user_message=_stream_user_message,
                    collected_chunks=[],
                    final_state=persisted_state,
                    is_resume=is_resume,
                    inquiry_card=detected_inquiry_card,
                    inquiry_receipt_payload=request.inquiry_receipt_payload,
                    process_events=process_events,
                    display_nodes=_node_collector.get_ordered_nodes(),
                )

            _emit_state = last_dict_state or {}
            if _emit_state:
                _append_debug_log(
                    run_id="sdk-version-stream",
                    hypothesis_id="S1",
                    location="api/stream.py:chat_stream:final_state",
                    message="Final stream state before completion",
                    data={
                        "is_resume": is_resume,
                        "synthetic_resume": synthetic_resume,
                        "has_interrupt": interrupt_sent,
                        "merged_patch_keys": merged_patch_keys,
                        "has_inquiry_answers": bool(_emit_state.get("inquiry_answers")),
                        "onboarding_turn_count_before": onboarding_turn_count_before,
                        "onboarding_turn_count_after": int(_emit_state.get("onboarding_turn_count", 0) or 0),
                    },
                )

            # emit final 事件，透传 feedback 字段和 inquiry_card（始终发送，interrupt 场景也不跳过）
            # state 字段：跨节点累积的关键状态字段，供前端 processStateUpdate 使用
            _final_state_payload = accumulated_state_fields or None

            # 为 pending_responses 中的 final 回复创建 DisplayNode
            _final_pending = accumulated_pending_responses or _emit_state.get("pending_responses") or []
            for _pr in _final_pending:
                if not isinstance(_pr, dict):
                    continue
                _pr_phase = _pr.get("phase", "")
                _pr_content = _pr.get("content", "")
                if _pr_phase == "final" and _pr_content:
                    _final_node = build_final_response_node(
                        seq=_seq_alloc.next_seq(),
                        turn_id=_display_turn_id,
                        content=_pr_content,
                        source=_pr.get("source", "main_agent"),
                    )
                    _node_collector.upsert(_final_node)
                elif _pr_phase == "subgraph_thinking" and _pr_content:
                    _sg_node = build_subgraph_thinking_node(
                        seq=_seq_alloc.next_seq(),
                        turn_id=_display_turn_id,
                        part_index=_ai_msg_counter[0],
                        content=_pr_content,
                        source=_pr.get("source", "subgraph"),
                    )
                    _ai_msg_counter[0] += 1
                    _node_collector.upsert(_sg_node)

            final_payload = {
                "type": "final",
                "turn_id": _display_turn_id,
                "turn_seq": _display_turn_seq,
                "feedback_prefill": _emit_state.get("feedback_prefill"),
                "feedback_status": _emit_state.get("feedback_status"),
                "feedback_question": _emit_state.get("feedback_question"),
                "inquiry_card": detected_inquiry_card,
                "pending_responses": _final_pending,
                "display_nodes": _node_collector.get_ordered_nodes(),
                "state": _final_state_payload,
            }
            yield f"data: {json.dumps(final_payload, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception("Stream generation failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
