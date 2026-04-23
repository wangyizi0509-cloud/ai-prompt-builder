"""
LangGraph SDK 客户端工具
提供统一的客户端获取、状态管理和辅助函数
"""
import os
import hashlib
import uuid
from typing import Any
from langgraph_sdk import get_sync_client

from utils.langgraph_config import (
    LANGGRAPH_URL,
    LANGGRAPH_API_KEY,
    ASSISTANT_ID,
)


from utils.logger import get_logger

logger = get_logger("sdk_client")
import time


def _looks_like_inquiry_card(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    questions = value.get("questions")
    return isinstance(questions, list) and len(questions) > 0


def _extract_inquiry_card_from_interrupt_value(value: Any) -> dict[str, Any] | None:
    if _looks_like_inquiry_card(value):
        return value
    if isinstance(value, dict):
        nested = value.get("inquiry_card")
        if _looks_like_inquiry_card(nested):
            return nested
    return None


def _restore_pending_inquiry_card(state_snapshot: Any, values: dict[str, Any]) -> dict[str, Any]:
    if values.get("inquiry_card"):
        return values

    tasks = state_snapshot.get("tasks") if isinstance(state_snapshot, dict) else getattr(state_snapshot, "tasks", None)
    if not isinstance(tasks, (list, tuple)):
        return values

    for task in tasks:
        interrupts = task.get("interrupts") if isinstance(task, dict) else getattr(task, "interrupts", None)
        if not isinstance(interrupts, (list, tuple)):
            continue
        for interrupt in interrupts:
            payload = interrupt.get("value") if isinstance(interrupt, dict) else getattr(interrupt, "value", None)
            inquiry_card = _extract_inquiry_card_from_interrupt_value(payload)
            if inquiry_card:
                restored = dict(values)
                restored["inquiry_card"] = inquiry_card
                logger.info("threads.get_state: restored inquiry_card from pending interrupt")
                return restored
    return values

def get_client():
    """获取 LangGraph SDK 客户端"""
    return get_sync_client(url=LANGGRAPH_URL, api_key=LANGGRAPH_API_KEY)


def session_to_thread_id(session_id: str) -> str:
    """将 session_id 转换为 UUID 格式"""
    try:
        uuid.UUID(session_id)
        return session_id
    except ValueError:
        hash_obj = hashlib.md5(session_id.encode())
        hex_digest = hash_obj.hexdigest()
        return str(uuid.UUID(hex=hex_digest[:32]))


async def ensure_thread_exists(session_id: str, user_id: str = None) -> str:
    """确保 thread 存在，如果不存在则创建"""
    client = get_client()
    logger.debug(f"ensure_thread_exists: session_id={session_id}, user_id={user_id}")
    
    # 1. 如果有 user_id，优先从数据库获取已绑定的 thread_id
    if user_id:
        from supabase_service.client import get_thread_by_user
        user_thread_data = await get_thread_by_user(user_id)
        if user_thread_data:
            thread_id = user_thread_data['thread_id']
            logger.info(f"Found bound thread in DB: {thread_id} for user: {user_id}")
            # 确保这个 thread 在 LangGraph 中也存在
            try:
                client.threads.get(thread_id)
                logger.debug(f"Thread {thread_id} exists in LangGraph. Returning.")
                return thread_id
            except Exception as exc:
                # 关键：无论是 checkpointer 被清掉还是瞬时错误，都沿用 DB 里
                # 已绑定的 thread_id 在 LangGraph 重建，避免把写入和 DB 绑定
                # 分叉到两个 thread_id（会导致用户刷新后看到空历史）。
                logger.warning(
                    f"Thread {thread_id} not accessible in LangGraph ({exc}); "
                    f"recreating under same id to keep DB binding canonical."
                )
                client.threads.create(thread_id=thread_id, if_exists="do_nothing")
                return thread_id

    # 2. 没有 user_id 或 DB 无绑定：首次为该 session 生成 thread_id
    thread_id = session_to_thread_id(session_id)
    logger.debug(f"Using session-mapped thread_id: {thread_id}")
    client.threads.create(thread_id=thread_id, if_exists="do_nothing")

    # 3. 如果有 user_id，首次建立绑定关系
    if user_id:
        logger.info(f"Binding user {user_id} to thread {thread_id} in DB.")
        from supabase_service.client import get_or_create_user_thread
        await get_or_create_user_thread(user_id, thread_id)

    return thread_id


def get_thread_state(thread_id: str):
    """获取 thread 的当前状态"""
    client = get_client()
    try:
        t0 = time.perf_counter()
        state_snapshot = client.threads.get_state(thread_id)
        t1 = time.perf_counter()
        logger.info(f"threads.get_state: thread={thread_id} took {int((t1 - t0)*1000)}ms")
        values = None
        if isinstance(state_snapshot, dict):
            values = state_snapshot.get("values")
        else:
            v_attr = getattr(state_snapshot, "values", None)
            values = v_attr if isinstance(v_attr, dict) else (v_attr() if callable(v_attr) else v_attr)
        if isinstance(values, dict):
            values = _restore_pending_inquiry_card(state_snapshot, values)
            msg_count = len(values.get("messages", [])) if isinstance(values.get("messages"), list) else 0
            keys = list(values.keys())
            logger.info(f"threads.get_state: thread={thread_id} state_keys={keys} messages={msg_count}")
            return values if keys else None
        return None
    except Exception as e:
        logger.error(f"threads.get_state failed for thread {thread_id}: {e}", exc_info=True)
        return None


def thread_has_pending_interrupt(thread_id: str) -> bool:
    """检查 thread 是否有 pending interrupt（图在等待 Command(resume=...)）"""
    client = get_client()
    try:
        state_snapshot = client.threads.get_state(thread_id)
        # SDK 返回的 state snapshot 中 tasks 里的 interrupts 非空则表示有 pending interrupt
        tasks = None
        if isinstance(state_snapshot, dict):
            tasks = state_snapshot.get("tasks")
        else:
            tasks = getattr(state_snapshot, "tasks", None)
        if isinstance(tasks, (list, tuple)):
            for task in tasks:
                interrupts = task.get("interrupts") if isinstance(task, dict) else getattr(task, "interrupts", None)
                if interrupts:
                    return True
        return False
    except Exception as e:
        logger.warning(f"thread_has_pending_interrupt check failed: {e}")
        return False


def update_thread_state(thread_id: str, updates: dict):
    """更新 thread 状态"""
    client = get_client()
    client.threads.update_state(thread_id, updates)


def run_assistant(
    thread_id: str,
    input_state: Any = None,
    stream_mode: str | list = "updates",
    *,
    command: dict | None = None,
):
    """运行 assistant 并返回流式结果。

    对于普通消息：传 input_state（新的 state）。
    对于 resume：传 command={"resume": payload}（从 interrupt 恢复）。
    """
    client = get_client()
    # 确保 custom 模式始终包含，以便接收 get_stream_writer() 的事件
    if isinstance(stream_mode, list):
        modes = list(stream_mode)
    else:
        modes = [stream_mode] if stream_mode else ["updates"]
    if "custom" not in modes:
        modes.append("custom")
    kwargs: dict[str, Any] = {
        "thread_id": thread_id,
        "assistant_id": ASSISTANT_ID,
        "stream_mode": modes,
    }
    if command is not None:
        kwargs["command"] = command
        logger.info(f"run_assistant: thread={thread_id} mode=RESUME command_keys={list(command.keys())}")
    else:
        kwargs["input"] = input_state
        logger.info(f"run_assistant: thread={thread_id} mode=NEW_RUN")
    return client.runs.stream(**kwargs)
