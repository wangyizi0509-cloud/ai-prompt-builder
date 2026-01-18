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
    """确保 thread 存在，如果不存在则创建
    
    Args:
        session_id: 会话 ID
        user_id: 用户 ID (可选)，如果提供则优先从数据库获取已绑定的 thread
    
    Returns:
        thread_id: 线程 ID
    """
    client = get_client()
    
    # 1. 如果有 user_id，优先从数据库获取已绑定的 thread_id
    if user_id:
        from supabase_service.client import get_thread_by_user
        user_thread_data = await get_thread_by_user(user_id)
        if user_thread_data:
            thread_id = user_thread_data['thread_id']
            # 确保这个 thread 在 LangGraph 中也存在
            try:
                client.threads.get(thread_id)
                return thread_id
            except Exception:
                # 数据库有记录但 LangGraph 没记录，可能是环境迁移，继续执行默认逻辑
                print(f"Warning: Thread {thread_id} found in DB but not in LangGraph. Creating new.")
    
    # 2. 如果没有绑定或绑定失效，根据 session_id 生成（确定性映射）
    thread_id = session_to_thread_id(session_id)
    
    try:
        client.threads.get(thread_id)
    except Exception:
        client.threads.create(thread_id=thread_id)
    
    # 3. 如果有 user_id，建立或更新绑定关系
    if user_id:
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
