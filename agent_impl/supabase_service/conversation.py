"""
Supabase 会话与消息持久化 CRUD

提供会话(conversations)、轮次(conversation_turns)、消息(conversation_messages)
的增删查改能力，支持幂等写入、分页读取、物理删除与过期清理。

所有写入走 service_role_key，不受 RLS 限制。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from supabase_service.client import execute_supabase, supabase, is_supabase_configured

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_hash(content: Optional[str], metadata: Optional[dict] = None) -> str:
    """生成消息内容的 sha256 去重哈希。"""
    if content:
        raw = content
    elif metadata:
        raw = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    else:
        raw = ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _compute_seq(turn_seq: int, part_index: int) -> int:
    """根据 turn_seq 和 part_index 计算全局严格排序键 seq。"""
    return turn_seq * 1000 + part_index


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------

async def upsert_conversation(user_id: str, thread_id: str) -> Optional[Dict[str, Any]]:
    """
    创建或获取会话。
    - 如果 (user_id, thread_id) 已存在，直接返回
    - 否则创建新记录并标记为 is_default=true
    返回 conversation row dict，失败返回 None。
    """
    if not is_supabase_configured():
        logger.warning("upsert_conversation: Supabase not configured")
        return None

    try:
        # 先查是否存在
        resp = (
            execute_supabase(
                lambda: supabase.table("conversations")
                .select("*")
                .eq("user_id", user_id)
                .eq("thread_id", thread_id)
                .execute(),
                op_name="upsert_conversation.select_existing",
            )
        )
        if resp.data:
            return resp.data[0]

        # 先清除该用户其他 default 标记（保证 partial unique 约束）
        try:
            execute_supabase(
                lambda: supabase.table("conversations").update({"is_default": False}).eq("user_id", user_id).eq("is_default", True).execute(),
                op_name="upsert_conversation.clear_default",
            )
        except Exception:
            pass

        # 插入新会话
        now = datetime.now(timezone.utc).isoformat()
        insert_resp = (
            execute_supabase(
                lambda: supabase.table("conversations")
                .insert({
                    "user_id": user_id,
                    "thread_id": thread_id,
                    "is_default": True,
                    "created_at": now,
                    "updated_at": now,
                })
                .execute(),
                op_name="upsert_conversation.insert",
            )
        )
        if insert_resp.data:
            return insert_resp.data[0]
        return None
    except Exception as e:
        # 可能因并发导致 duplicate，再查一次
        logger.warning("upsert_conversation error: %s, retrying select", e)
        try:
            resp = (
                execute_supabase(
                    lambda: supabase.table("conversations")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("thread_id", thread_id)
                    .execute(),
                    op_name="upsert_conversation.retry_select",
                )
            )
            if resp.data:
                return resp.data[0]
        except Exception:
            pass
        return None


async def get_default_conversation(user_id: str) -> Optional[Dict[str, Any]]:
    """获取用户的默认会话。"""
    if not is_supabase_configured():
        return None
    try:
        resp = (
            execute_supabase(
                lambda: supabase.table("conversations")
                .select("*")
                .eq("user_id", user_id)
                .eq("is_default", True)
                .execute(),
                op_name="get_default_conversation.default",
            )
        )
        if resp.data:
            return resp.data[0]
        # 如果没有 default，返回最新的会话
        resp = (
            execute_supabase(
                lambda: supabase.table("conversations")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute(),
                op_name="get_default_conversation.latest",
            )
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error("get_default_conversation error: %s", e, exc_info=True)
        return None


async def get_conversation_by_id(conversation_id: str) -> Optional[Dict[str, Any]]:
    """通过 ID 获取会话。"""
    if not is_supabase_configured():
        return None
    try:
        resp = (
            execute_supabase(
                lambda: supabase.table("conversations")
                .select("*")
                .eq("id", conversation_id)
                .execute(),
                op_name="get_conversation_by_id",
            )
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error("get_conversation_by_id error: %s", e, exc_info=True)
        return None


async def get_conversation_by_thread(thread_id: str) -> Optional[Dict[str, Any]]:
    """通过 thread_id 获取会话。"""
    if not is_supabase_configured():
        return None
    try:
        resp = (
            execute_supabase(
                lambda: supabase.table("conversations")
                .select("*")
                .eq("thread_id", thread_id)
                .execute(),
                op_name="get_conversation_by_thread",
            )
        )
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error("get_conversation_by_thread error: %s", e, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Turn CRUD
# ---------------------------------------------------------------------------

async def get_or_create_turn(conversation_id: str, turn_id: str) -> Optional[Dict[str, Any]]:
    """
    幂等获取或创建轮次。
    返回 turn row dict（含 turn_seq）。
    """
    if not is_supabase_configured():
        return None

    try:
        resp = (
            execute_supabase(
                lambda: supabase.table("conversation_turns")
                .select("*")
                .eq("conversation_id", conversation_id)
                .eq("turn_id", turn_id)
                .execute(),
                op_name="get_or_create_turn.select_existing",
            )
        )
        if resp.data:
            return resp.data[0]

        insert_resp = (
            execute_supabase(
                lambda: supabase.table("conversation_turns")
                .insert({
                    "conversation_id": conversation_id,
                    "turn_id": turn_id,
                })
                .execute(),
                op_name="get_or_create_turn.insert",
            )
        )
        if insert_resp.data:
            return insert_resp.data[0]
        return None
    except Exception as e:
        # duplicate -> retry select
        logger.warning("get_or_create_turn error: %s, retrying select", e)
        try:
            resp = (
                execute_supabase(
                    lambda: supabase.table("conversation_turns")
                    .select("*")
                    .eq("conversation_id", conversation_id)
                    .eq("turn_id", turn_id)
                    .execute(),
                    op_name="get_or_create_turn.retry_select",
                )
            )
            if resp.data:
                return resp.data[0]
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Message Write
# ---------------------------------------------------------------------------

async def append_messages(
    conversation_id: str,
    thread_id: str,
    turn_id: str,
    turn_seq: int,
    messages: List[Dict[str, Any]],
) -> int:
    """
    幂等追加消息到 conversation_messages。

    每条 message dict 至少包含:
      role: str  — user / assistant / system
      kind: str  — chat_text / interrupt_inquiry / inquiry_receipt / system_task
      content: Optional[str]
      metadata: Optional[dict]
      part_index: int  — 同一轮次内的分段序号

    返回实际新写入的行数。
    """
    if not is_supabase_configured() or not messages:
        return 0

    written = 0
    for msg in messages:
        part_index = int(msg.get("part_index", 0))
        seq = _compute_seq(turn_seq, part_index)
        content = msg.get("content")
        metadata = msg.get("metadata")
        ch = _content_hash(content, metadata)
        role = msg.get("role", "assistant")
        kind = msg.get("kind", "chat_text")

        row = {
            "conversation_id": conversation_id,
            "thread_id": thread_id,
            "turn_id": turn_id,
            "turn_seq": turn_seq,
            "part_index": part_index,
            "seq": seq,
            "role": role,
            "kind": kind,
            "content": content,
            "content_hash": ch,
            "metadata": json.dumps(metadata, ensure_ascii=False, default=str) if metadata else None,
        }

        try:
            execute_supabase(
                lambda: supabase.table("conversation_messages").upsert(
                    row,
                    on_conflict="conversation_id,turn_id,kind,role,part_index",
                ).execute(),
                op_name="append_messages.upsert",
            )
            written += 1
        except Exception as e:
            logger.error("append_messages upsert error: %s (turn_id=%s, part=%s)", e, turn_id, part_index)

    # 更新 conversations.last_message_at
    try:
        now = datetime.now(timezone.utc).isoformat()
        execute_supabase(
            lambda: supabase.table("conversations").update({"last_message_at": now, "updated_at": now}).eq("id", conversation_id).execute(),
            op_name="append_messages.update_last_message_at",
        )
    except Exception as e:
        logger.warning("Failed to update last_message_at: %s", e)

    return written


# ---------------------------------------------------------------------------
# Message Read (paginated)
# ---------------------------------------------------------------------------

async def get_messages(
    conversation_id: str,
    limit: int = 50,
    before_seq: Optional[int] = None,
) -> Dict[str, Any]:
    """
    分页读取消息（按 seq ASC）。

    返回:
    {
      "messages": [...],
      "page": {
        "next_before_seq": int | None,
        "has_more": bool,
      }
    }
    """
    if not is_supabase_configured():
        return {"messages": [], "page": {"next_before_seq": None, "has_more": False}}

    try:
        query = (
            supabase.table("conversation_messages")
            .select("*")
            .eq("conversation_id", conversation_id)
        )
        if before_seq is not None:
            query = query.lt("seq", before_seq)

        # 取 limit+1 判断 has_more
        query = query.order("seq", desc=True).limit(limit + 1)
        resp = execute_supabase(
            lambda: query.execute(),
            op_name="get_messages",
        )
        rows = resp.data or []

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # 反转为 ASC
        rows.reverse()

        # 解析 metadata JSON 字符串
        for row in rows:
            if isinstance(row.get("metadata"), str):
                try:
                    row["metadata"] = json.loads(row["metadata"])
                except Exception:
                    pass

        next_before_seq = rows[0]["seq"] if rows else None

        return {
            "messages": rows,
            "page": {
                "next_before_seq": next_before_seq,
                "has_more": has_more,
            },
        }
    except Exception as e:
        logger.error("get_messages error: %s", e, exc_info=True)
        return {"messages": [], "page": {"next_before_seq": None, "has_more": False}}


async def get_messages_count(conversation_id: str) -> int:
    """获取会话消息总数。"""
    if not is_supabase_configured():
        return 0
    try:
        resp = execute_supabase(
            lambda: supabase.table("conversation_messages")
            .select("id", count="exact")
            .eq("conversation_id", conversation_id)
            .execute(),
            op_name="get_messages_count",
        )
        return resp.count or 0
    except Exception as e:
        logger.error("get_messages_count error: %s", e, exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

async def delete_conversation(conversation_id: str) -> bool:
    """物理删除会话及其所有关联数据（messages + turns 由 CASCADE 删除）。"""
    if not is_supabase_configured():
        return False
    try:
        execute_supabase(
            lambda: supabase.table("conversations").delete().eq("id", conversation_id).execute(),
            op_name="delete_conversation",
        )
        return True
    except Exception as e:
        logger.error("delete_conversation error: %s", e, exc_info=True)
        return False


async def delete_all_user_conversations(user_id: str) -> bool:
    """物理删除用户的所有会话（用于注销场景）。"""
    if not is_supabase_configured():
        return False
    try:
        execute_supabase(
            lambda: supabase.table("conversations").delete().eq("user_id", user_id).execute(),
            op_name="delete_all_user_conversations",
        )
        return True
    except Exception as e:
        logger.error("delete_all_user_conversations error: %s", e, exc_info=True)
        return False


async def purge_old_data(days: int = 30) -> int:
    """清理超过 days 天的消息，再清理空会话。返回删除的消息数。"""
    if not is_supabase_configured():
        return 0

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    deleted = 0

    try:
        # 1. 删除过期消息
        resp = (
            supabase.table("conversation_messages")
            .delete()
            .lt("created_at", cutoff)
            .execute()
        )
        deleted = len(resp.data) if resp.data else 0

        # 2. 删除过期轮次
        supabase.table("conversation_turns").delete().lt("created_at", cutoff).execute()

        # 3. 删除没有消息的空会话
        # (使用 created_at < cutoff 作为安全约束，只清理旧会话)
        supabase.table("conversations").delete().lt("created_at", cutoff).execute()

        logger.info("purge_old_data: deleted %d messages older than %d days", deleted, days)
    except Exception as e:
        logger.error("purge_old_data error: %s", e, exc_info=True)

    return deleted


# ---------------------------------------------------------------------------
# Backfill helper: 从 LangGraph state 回填消息到 Supabase
# ---------------------------------------------------------------------------

async def backfill_from_langgraph_state(
    conversation_id: str,
    thread_id: str,
    state: Dict[str, Any],
) -> int:
    """
    从 LangGraph thread state 回填消息到 Supabase。
    仅在 Supabase 无数据时使用。
    返回写入的消息数。
    """
    messages = _extract_messages_from_state(state)
    if not messages:
        return 0

    written = 0
    for idx, msg in enumerate(messages):
        turn_id = f"backfill-{idx}"
        # 为每条消息创建一个 turn
        turn = await get_or_create_turn(conversation_id, turn_id)
        if not turn:
            continue
        turn_seq = turn["turn_seq"]

        count = await append_messages(
            conversation_id=conversation_id,
            thread_id=thread_id,
            turn_id=turn_id,
            turn_seq=turn_seq,
            messages=[{
                "role": msg["role"],
                "kind": "chat_text",
                "content": msg["content"],
                "part_index": 0,
            }],
        )
        written += count

    return written


def _extract_messages_from_state(state: Dict[str, Any]) -> List[Dict[str, str]]:
    """从 LangGraph state 提取 user/assistant 消息列表。"""
    messages = state.get("messages") if isinstance(state.get("messages"), list) else []
    if not messages and isinstance(state.get("layer3_memory"), dict):
        alt = state["layer3_memory"].get("all_messages")
        messages = alt if isinstance(alt, list) else []

    result = []
    for msg in messages:
        role = ""
        content = ""
        if isinstance(msg, dict):
            role = msg.get("role") or (msg.get("type") if msg.get("type") in ["human", "ai"] else "")
            content = msg.get("content", "")
        else:
            role = "user" if getattr(msg, "type", "") == "human" else ("assistant" if getattr(msg, "type", "") == "ai" else "")
            content = getattr(msg, "content", "")

        if content and role in ("user", "assistant", "human", "ai"):
            normalized_role = "user" if role in ("user", "human") else "assistant"
            result.append({"role": normalized_role, "content": str(content)})

    return result
