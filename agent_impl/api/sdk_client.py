"""
LangGraph SDK 客户端工具
提供统一的客户端获取、状态管理和辅助函数
"""
import os
import hashlib
import uuid
from langgraph_sdk import get_sync_client

from utils.langgraph_config import (
    LANGGRAPH_URL,
    LANGGRAPH_API_KEY,
    ASSISTANT_ID,
)


from utils.logger import get_logger

logger = get_logger("sdk_client")

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
            except Exception:
                logger.warning(f"Thread {thread_id} NOT found in LangGraph. Will create new.")
    
    # 2. 如果没有绑定或绑定失效，根据 session_id 生成
    thread_id = session_to_thread_id(session_id)
    logger.debug(f"Using session-mapped thread_id: {thread_id}")
    
    try:
        client.threads.get(thread_id)
        logger.debug(f"Thread {thread_id} already exists in LangGraph.")
    except Exception:
        logger.info(f"Creating new thread {thread_id} in LangGraph.")
        client.threads.create(thread_id=thread_id)
    
    # 3. 如果有 user_id，建立或更新绑定关系
    if user_id:
        logger.info(f"Binding user {user_id} to thread {thread_id} in DB.")
        from supabase_service.client import get_or_create_user_thread
        await get_or_create_user_thread(user_id, thread_id)
    
    return thread_id


def get_thread_state(thread_id: str):
    """获取 thread 的当前状态"""
    client = get_client()
    try:
        state_snapshot = client.threads.get_state(thread_id)
        if state_snapshot.values:
            return dict(state_snapshot.values)
        return None
    except Exception:
        return None


def update_thread_state(thread_id: str, updates: dict):
    """更新 thread 状态"""
    client = get_client()
    client.threads.update_state(thread_id, updates)


def run_assistant(thread_id: str, input_state: dict, stream_mode: str = "values"):
    """运行 assistant 并返回流式结果"""
    client = get_client()
    return client.runs.stream(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID,
        input=input_state,
        stream_mode=stream_mode,
    )
