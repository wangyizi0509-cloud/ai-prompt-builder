from fastapi import APIRouter, HTTPException

from .sdk_client import (
    session_to_thread_id,
    get_thread_state,
)

router = APIRouter()


@router.get("/context/{session_id}")
async def get_debug_context(session_id: str):
    """
    获取当前会话的上下文调试信息 - 使用 SDK 版本
    
    返回分层的上下文状态，用于前端调试面板显示
    """
    from utils.message_utils import count_user_turns
    from graph.archive_manager import (
        LAYER2_ARCHIVE_CONFIG,
        LAYER3_ARCHIVE_CONFIG,
        check_layer3_compression_needed,
    )
    
    thread_id = session_to_thread_id(session_id)
    state = get_thread_state(thread_id)
    
    if not state:
        return {
            "error": "Session not found",
            "session_id": session_id,
            "layer1_static": None,
            "layer2_working": None,
            "layer3_conversation": None,
            "layer4_archive": None,
            "crush_chat": None,
        }
    
    layer1_memory = state.get("layer1_memory") or {}
    layer2_memory = state.get("layer2_memory") or {}
    layer3_memory = state.get("layer3_memory") or {}
    maintenance_queue = state.get("maintenance_queue") or []
    maintenance_flags = state.get("maintenance_flags") or {}

    user_context = state.get("user_context", {}) or layer1_memory.get("full_data", {})
    history_archive = state.get("history_archive", {})
    
    crush_chat_storage = state.get("crush_chat_storage", {})
    
    _current_turns = count_user_turns(layer3_memory.get("all_messages", state.get("messages", [])))
    
    def calculate_turns_to_compression():
        threshold = LAYER3_ARCHIVE_CONFIG.get("compression_threshold", 45)
        batch_size = LAYER3_ARCHIVE_CONFIG.get("compression_batch_size", 5)
        turns = _current_turns if isinstance(_current_turns, int) else 0
        if turns <= threshold:
            return threshold - turns + 1
        else:
            return batch_size - ((turns - threshold) % batch_size) if ((turns - threshold) % batch_size) != 0 else 0

    return {
        "session_id": session_id,
        "onboarding_status": {
            "completed": bool(state.get("onboarding_completed", False)),
            "turn_count": state.get("onboarding_turn_count", 0),
            "max_turns": state.get("onboarding_max_turns", 3),
            "has_handoff": bool(state.get("onboarding_handoff")),
        },
        "maintenance": {
            "queue_size": len(maintenance_queue) if isinstance(maintenance_queue, list) else 0,
            "queue": maintenance_queue if isinstance(maintenance_queue, list) else [],
            "flags": maintenance_flags if isinstance(maintenance_flags, dict) else {},
            "last_finalized_at": state.get("maintenance_last_finalized_at"),
        },
        "archive_config": {
            "layer2": LAYER2_ARCHIVE_CONFIG or {},
            "layer3": LAYER3_ARCHIVE_CONFIG or {},
        },
        "organized_outputs": {
            "layer3_conversation_summaries": (
                (layer3_memory.get("conversation_summaries", [])[-5:] if isinstance(layer3_memory, dict) else [])
            ),
            "layer2_status_reports_history": (
                [
                    {
                        "id": r.get("id"),
                        "created_at": r.get("created_at"),
                        "stage": r.get("report", {}).get("stage") if isinstance(r.get("report"), dict) else r.get("stage"),
                        "summary": (r.get("summary") or "").strip(),
                        "one_liner": (r.get("one_liner") or "").strip(),
                    }
                    for r in (layer2_memory.get("status_report_history", []) if isinstance(layer2_memory, dict) else [])
                    if isinstance(r, dict)
                ][-5:]
            ),
            "layer2_action_plans_history": (
                [
                    {
                        "id": p.get("id"),
                        "created_at": p.get("created_at"),
                        "summary": (p.get("summary") or "").strip(),
                        "one_liner": (p.get("one_liner") or "").strip(),
                    }
                    for p in (layer2_memory.get("action_plan_history", []) if isinstance(layer2_memory, dict) else [])
                    if isinstance(p, dict)
                ][-5:]
            ),
            "layer2_terminal_guides": (
                [
                    {
                        "id": g.get("id"),
                        "status": g.get("status"),
                        "created_at": g.get("created_at"),
                        "completed_at": g.get("completed_at"),
                        "current_task": (
                            (g.get("guide") or {}).get("current_task")
                            if isinstance(g.get("guide"), dict)
                            else None
                        ),
                        "one_liner": (g.get("one_liner") or "").strip(),
                        "summary": (g.get("summary") or "").strip(),
                    }
                    for g in (layer2_memory.get("action_guides", []) if isinstance(layer2_memory, dict) else [])
                    if isinstance(g, dict) and (g.get("status") in ("completed", "cancelled", "expired"))
                ][-5:]
            ),
            "layer2_dynamic_intels": (
                (layer2_memory.get("dynamic_intels", [])[-10:] if isinstance(layer2_memory, dict) else [])
            ),
        },
        "layered_memory": {
            "layer1": {
                "version": layer1_memory.get("version") if isinstance(layer1_memory, dict) else None,
                "last_updated": layer1_memory.get("last_updated") if isinstance(layer1_memory, dict) else None,
            },
            "layer2": {
                "version": layer2_memory.get("version") if isinstance(layer2_memory, dict) else None,
                "last_updated": layer2_memory.get("last_updated") if isinstance(layer2_memory, dict) else None,
                "status_reports_total": (1 if layer2_memory.get("current_status_report") else 0) + len(layer2_memory.get("status_report_history", [])) if isinstance(layer2_memory, dict) else 0,
                "action_plans_total": (1 if layer2_memory.get("current_action_plan") else 0) + len(layer2_memory.get("action_plan_history", [])) if isinstance(layer2_memory, dict) else 0,
                "action_guides_total": len(layer2_memory.get("action_guides", [])) if isinstance(layer2_memory, dict) else 0,
                "dynamic_intels_total": len(layer2_memory.get("dynamic_intels", [])) if isinstance(layer2_memory, dict) else 0,
            },
            "layer3": {
                "version": layer3_memory.get("version") if isinstance(layer3_memory, dict) else None,
                "last_updated": layer3_memory.get("last_updated") if isinstance(layer3_memory, dict) else None,
                "all_messages_count": len(layer3_memory.get("all_messages", [])) if isinstance(layer3_memory, dict) else 0,
                "conversation_summaries_count": len(layer3_memory.get("conversation_summaries", [])) if isinstance(layer3_memory, dict) else 0,
            },
        },
        "layer1_static": {
            "user_info": user_context.get("user_info", {}),
            "crush_info": user_context.get("crush_info", {}),
            "both_info": user_context.get("both_info", {}),
        },
        "layer2_working": {
            "status_report": state.get("status_report"),
            "action_plan": state.get("action_plan"),
            "action_guides": state.get("action_guides", []),
            "recent_messages": state.get("messages", [])[-10:] if state.get("messages") else [],
        },
        "layer3_conversation": {
            "message_count": len(state.get("messages", [])),
            "messages_count_workspace": len(state.get("messages", [])),
            "all_messages_count_fullstore": len(layer3_memory.get("all_messages", [])) if isinstance(layer3_memory, dict) else len(state.get("messages", [])),
            "conversation_summaries_count": len(layer3_memory.get("conversation_summaries", [])) if isinstance(layer3_memory, dict) else 0,
            "compression_threshold": LAYER3_ARCHIVE_CONFIG.get("compression_threshold"),
            "compression_batch_size": LAYER3_ARCHIVE_CONFIG.get("compression_batch_size"),
            "max_recent_turns": LAYER3_ARCHIVE_CONFIG.get("max_recent_turns"),
            "current_user_turns": _current_turns,
            "turns_to_next_compression": calculate_turns_to_compression(),
            "needs_compression": bool(check_layer3_compression_needed(state)) if callable(check_layer3_compression_needed) else None,
            "messages_preview": (layer3_memory.get("all_messages", [])[-5:] if isinstance(layer3_memory, dict) else []) or (state.get("messages", [])[-5:] if state.get("messages") else []),
        },
        "layer4_archive": {
            "status_history_count": len(history_archive.get("status_history", [])),
            "guide_history_count": len(history_archive.get("guide_history", [])),
            "plan_history_count": len(history_archive.get("plan_history", [])),
            "conversation_archive_count": len(history_archive.get("conversation_archive", [])),
            "status_history": history_archive.get("status_history", []),
            "guide_history": history_archive.get("guide_history", []),
        },
        "crush_chat": {
            "metadata": crush_chat_storage.get("metadata", {}) if crush_chat_storage else {},
            "summary": crush_chat_storage.get("summary", {}) if crush_chat_storage else {},
        },
    }


@router.get("/detail/status_report/{session_id}/{report_id}")
async def get_status_report_detail(session_id: str, report_id: str):
    """
    获取现状报告全文（用于调试面板展开查看）- 使用 SDK 版本
    """
    thread_id = session_to_thread_id(session_id)
    state = get_thread_state(thread_id)
    
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    layer2_memory = state.get("layer2_memory") or {}
    
    current_report = layer2_memory.get("current_status_report") if isinstance(layer2_memory, dict) else None
    if isinstance(current_report, dict) and str(current_report.get("id")) == str(report_id):
        return {
            "id": current_report.get("id"),
            "created_at": current_report.get("created_at"),
            "is_current": True,
            "stage": current_report.get("stage") or (current_report.get("report", {}).get("stage") if isinstance(current_report.get("report"), dict) else None),
            "summary": current_report.get("summary"),
            "one_liner": current_report.get("one_liner"),
            "report_content": current_report.get("report_content") or (current_report.get("report", {}).get("report_content") if isinstance(current_report.get("report"), dict) else None),
            "full_report": current_report.get("report") if isinstance(current_report.get("report"), dict) else current_report,
        }
    
    history_reports = layer2_memory.get("status_report_history", []) if isinstance(layer2_memory, dict) else []
    for r in history_reports:
        if isinstance(r, dict) and str(r.get("id")) == str(report_id):
            return {
                "id": r.get("id"),
                "created_at": r.get("created_at"),
                "is_current": False,
                "stage": r.get("stage") or (r.get("report", {}).get("stage") if isinstance(r.get("report"), dict) else None),
                "summary": r.get("summary"),
                "one_liner": r.get("one_liner"),
                "report_content": r.get("report_content") or (r.get("report", {}).get("report_content") if isinstance(r.get("report"), dict) else None),
                "full_report": r.get("report") if isinstance(r.get("report"), dict) else r,
            }
    
    raise HTTPException(status_code=404, detail=f"Report with id {report_id} not found")


@router.get("/detail/action_guide/{session_id}/{guide_id}")
async def get_action_guide_detail(session_id: str, guide_id: str):
    """
    获取行动指南全文（用于调试面板展开查看）- 使用 SDK 版本
    """
    thread_id = session_to_thread_id(session_id)
    state = get_thread_state(thread_id)
    
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    layer2_memory = state.get("layer2_memory") or {}
    all_guides = layer2_memory.get("action_guides", []) if isinstance(layer2_memory, dict) else []
    
    if not all_guides:
        all_guides = state.get("action_guides", []) or []
    
    for g in all_guides:
        if isinstance(g, dict) and str(g.get("id")) == str(guide_id):
            guide_content = g.get("guide", {}) if isinstance(g.get("guide"), dict) else {}
            return {
                "id": g.get("id"),
                "status": g.get("status"),
                "created_at": g.get("created_at"),
                "completed_at": g.get("completed_at"),
                "current_task": guide_content.get("current_task"),
                "summary": g.get("summary"),
                "one_liner": g.get("one_liner"),
                "user_feedback": g.get("user_feedback"),
                "execution_status": g.get("execution_status"),
                "guide_content": guide_content.get("guide_content"),
                "full_guide": g,
            }
    
    raise HTTPException(status_code=404, detail=f"Guide with id {guide_id} not found")


@router.get("/detail/compressed_messages/{session_id}/{summary_index}")
async def get_compressed_messages_detail(session_id: str, summary_index: int):
    """
    获取压缩前的原始对话片段（用于调试面板展开查看）- 使用 SDK 版本
    
    注意：目前压缩时只保留摘要，原始消息被删除。
    如果需要保留原始消息，需要在 compress_layer3 里额外存储。
    这里返回 summary 的详细信息 + 相关元数据。
    """
    thread_id = session_to_thread_id(session_id)
    state = get_thread_state(thread_id)
    
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    layer3_memory = state.get("layer3_memory") or {}
    summaries = layer3_memory.get("conversation_summaries", []) if isinstance(layer3_memory, dict) else []
    
    if summary_index < 0 or summary_index >= len(summaries):
        raise HTTPException(status_code=404, detail=f"Summary at index {summary_index} not found")
    
    summary = summaries[summary_index]
    return {
        "index": summary_index,
        "summary": summary.get("summary") if isinstance(summary, dict) else str(summary),
        "turn_count": summary.get("turn_count") if isinstance(summary, dict) else None,
        "key_topics": summary.get("key_topics") if isinstance(summary, dict) else None,
        "created_at": summary.get("created_at") if isinstance(summary, dict) else None,
        "extracted_info": summary.get("extracted_info") if isinstance(summary, dict) else None,
        "original_messages": None,
        "note": "原始消息在压缩后被删除，仅保留摘要。如需保留原始消息，需修改 compress_layer3 逻辑。",
    }
