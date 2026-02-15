"""
语义化对话接口

GET  /api/conversations/default                    — 获取默认会话
GET  /api/conversations/{conversation_id}/messages  — 分页获取消息
GET  /api/conversations/{conversation_id}/state     — 获取会话 state
DELETE /api/conversations/{conversation_id}         — 删除会话
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter()
security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth dependency (require login)
# ---------------------------------------------------------------------------

async def _require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """强制登录态。未登录返回 401。"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    from auth_utils import get_optional_user
    user = await get_optional_user(credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/default")
async def get_default_conversation(current_user=Depends(_require_user)):
    """
    获取当前用户的默认会话。
    如果不存在，从 user_threads 绑定中查找 thread_id 并创建。
    """
    user_id = current_user["user_id"]

    from supabase_service.conversation import (
        get_default_conversation as _get_default,
        upsert_conversation,
    )
    from supabase_service.client import get_thread_by_user

    conv = await _get_default(user_id)
    if conv:
        return {"success": True, "conversation": conv}

    # 从 user_threads 查找该用户绑定的 thread_id
    user_thread = await get_thread_by_user(user_id)
    if not user_thread:
        return {"success": True, "conversation": None}

    thread_id = user_thread["thread_id"]
    conv = await upsert_conversation(user_id, thread_id)
    if conv:
        return {"success": True, "conversation": conv}

    return {"success": True, "conversation": None}


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before_seq: Optional[int] = Query(default=None),
    current_user=Depends(_require_user),
):
    """
    分页获取会话消息（按 seq ASC 排序）。
    支持向上加载更多（before_seq 游标）。
    """
    user_id = current_user["user_id"]

    from supabase_service.conversation import (
        get_conversation_by_id,
        get_messages,
        get_messages_count,
        backfill_from_langgraph_state,
    )

    # 校验会话归属
    conv = await get_conversation_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv["user_id"] != user_id:
        logger.warning("Security: user %s tried to access conversation %s owned by %s", user_id, conversation_id, conv["user_id"])
        raise HTTPException(status_code=403, detail="Access denied")

    # 检查 Supabase 是否有数据
    msg_count = await get_messages_count(conversation_id)
    if msg_count == 0:
        # 尝试从 LangGraph 回填
        thread_id = conv["thread_id"]
        try:
            from api.sdk_client import get_thread_state
            state = get_thread_state(thread_id)
            if state:
                written = await backfill_from_langgraph_state(conversation_id, thread_id, state)
                logger.info("Backfilled %d messages from LangGraph for conv=%s", written, conversation_id)
        except Exception as e:
            logger.warning("Backfill from LangGraph failed: %s", e)

    # 读取消息
    result = await get_messages(conversation_id, limit=limit, before_seq=before_seq)
    return {"success": True, **result}


@router.get("/{conversation_id}/state")
async def get_conversation_state(
    conversation_id: str,
    current_user=Depends(_require_user),
):
    """
    获取会话的 LangGraph thread state。
    用于首屏或按需刷新状态面板。
    """
    user_id = current_user["user_id"]

    from supabase_service.conversation import get_conversation_by_id

    conv = await get_conversation_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    thread_id = conv["thread_id"]

    try:
        from api.sdk_client import get_thread_state
        state = get_thread_state(thread_id)
        return {"success": True, "state": state}
    except Exception as e:
        logger.error("get_conversation_state failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{conversation_id}")
async def delete_conversation_endpoint(
    conversation_id: str,
    current_user=Depends(_require_user),
):
    """
    物理删除会话及其所有关联数据。
    """
    user_id = current_user["user_id"]

    from supabase_service.conversation import (
        get_conversation_by_id,
        delete_conversation,
    )

    conv = await get_conversation_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    success = await delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete conversation")

    return {"success": True}
