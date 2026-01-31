from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional

router = APIRouter()


class UpdateGuideStatusRequest(BaseModel):
    guide_id: str
    new_status: Literal["in_progress", "completed", "paused", "cancelled", "expired"]
    feedback: Optional[str] = None
    execution_status: Optional[Literal["perfect", "good", "normal", "failed", "skipped"]] = None
    completion_status: Optional[Literal["success", "partial", "failed", "abandoned", "other"]] = None
    completion_detail: Optional[str] = None
    feedback_summary: Optional[str] = None
    session_id: str


class CompleteGuideRequest(BaseModel):
    guide_id: str
    execution_status: Literal["perfect", "good", "normal", "failed", "skipped"]
    feedback: Optional[str] = ""
    session_id: str


@router.post("/update_guide_status")
async def update_guide_status(request: UpdateGuideStatusRequest):
    """
    更新行动指南状态（支持 6 状态机中的可变更状态）- 使用 SDK 版本
    - 写入 v3.1 真源：layer2_memory.action_guides
    - 向后兼容：同步写回 state.action_guides
    """
    print(
        f"✅ [SDK] 收到指南状态更新请求: guide_id={request.guide_id}, new_status={request.new_status}, session={request.session_id}"
    )

    from graph.context_types import (
        create_empty_layer2_memory,
        is_valid_action_guide_status_transition,
    )
    from graph.archive_manager import archive_guide_to_layer2
    
    from api.sdk_client import session_to_thread_id, get_thread_state, update_thread_state
    thread_id = session_to_thread_id(request.session_id)
    state = get_thread_state(thread_id)
    
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
    all_guides = list(layer2_memory.get("action_guides", []))
    if not all_guides:
        legacy = state.get("action_guides", []) or []
        if isinstance(legacy, list) and legacy:
            all_guides = list(legacy)

    guide_index = None
    guide = None
    for idx, g in enumerate(all_guides):
        if isinstance(g, dict) and g.get("id") == request.guide_id:
            guide_index = idx
            guide = g
            break
    if guide_index is None or not guide:
        raise HTTPException(status_code=404, detail=f"Guide with id {request.guide_id} not found")

    current_status = str(guide.get("status") or "pending")
    if not is_valid_action_guide_status_transition(current_status, request.new_status):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition: {current_status} -> {request.new_status}",
        )

    updated_guide = dict(guide)
    updated_guide["status"] = request.new_status

    if request.new_status in ("completed", "cancelled", "expired"):
        updated_guide["completed_at"] = datetime.now().isoformat()
    else:
        updated_guide["completed_at"] = None

    completion_status = request.completion_status
    if not completion_status and request.execution_status:
        status_map = {
            "perfect": "success",
            "good": "success",
            "normal": "partial",
            "failed": "failed",
            "skipped": "abandoned",
        }
        completion_status = status_map.get(request.execution_status)

    if request.feedback:
        if not updated_guide.get("one_liner"):
            updated_guide["one_liner"] = request.feedback
        if request.new_status in ("cancelled", "expired") and not updated_guide.get("summary"):
            updated_guide["summary"] = request.feedback
        updated_guide["user_feedback"] = request.feedback

    if completion_status or request.completion_detail or request.feedback_summary:
        feedback_data = dict(updated_guide.get("feedback_data") or {})
        if completion_status:
            feedback_data["completion_status"] = completion_status
        if request.completion_detail:
            feedback_data["completion_detail"] = request.completion_detail
        if request.feedback_summary:
            feedback_data["feedback_summary"] = request.feedback_summary
        updated_guide["feedback_data"] = feedback_data

    updated_guides = list(all_guides)
    updated_guides[guide_index] = updated_guide

    updated_layer2 = dict(layer2_memory)
    updated_layer2["action_guides"] = updated_guides
    updated_layer2["last_updated"] = datetime.now().isoformat()
    updated_layer2["version"] = layer2_memory.get("version", 1) + 1
    state["layer2_memory"] = updated_layer2

    state["action_guides"] = updated_guides

    if request.new_status in ("completed", "cancelled", "expired"):
        try:
            archive_updates = archive_guide_to_layer2(updated_guide, state)
            for k in ("history_archive", "user_context", "layer1_memory", "layer2_memory", "layer3_memory"):
                if k in archive_updates:
                    state[k] = archive_updates[k]
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"⚠️ 归档失败: {str(e)}")
    
    update_thread_state(thread_id, state)

    return {"success": True, "state": state}


@router.post("/complete_guide")
async def complete_guide(request: CompleteGuideRequest):
    """
    [兼容] 旧接口：标记行动指南为已完成。
    建议迁移到 /api/update_guide_status。
    """
    status_map = {
        "perfect": "success",
        "good": "success",
        "normal": "partial",
        "failed": "failed",
        "skipped": "abandoned",
    }
    wrapper = UpdateGuideStatusRequest(
        guide_id=request.guide_id,
        new_status="completed",
        feedback=request.feedback,
        execution_status=request.execution_status,
        completion_status=status_map.get(request.execution_status),
        completion_detail=request.feedback,
        session_id=request.session_id,
    )
    return await update_guide_status(wrapper)
