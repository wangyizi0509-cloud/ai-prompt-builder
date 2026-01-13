"""
State 本地持久化存储
使用 JSON 文件存储每个用户的 AgentState

特点：
- 简单易用，无需数据库
- 按用户 ID 区分，每人一个文件
- 团队成员各自电脑上存各自的数据
- 支持自动保存和加载

存储位置：agent_impl/data/users/{user_id}.json
"""

import os
import json
from typing import Optional, Any
from datetime import datetime
from pathlib import Path

# 获取存储目录（相对于本文件）
_CURRENT_DIR = Path(__file__).parent.parent  # agent_impl/
DATA_DIR = _CURRENT_DIR / "data" / "users"


def _ensure_data_dir():
    """确保数据目录存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_user_file(user_id: str) -> Path:
    """获取用户数据文件路径"""
    _ensure_data_dir()
    # 清理用户 ID，避免路径注入
    safe_user_id = "".join(c for c in user_id if c.isalnum() or c in "-_")
    return DATA_DIR / f"{safe_user_id}.json"


def _serialize_state(state: dict) -> dict:
    """
    序列化 state 为可 JSON 存储的格式
    处理特殊类型（如 datetime）
    """
    def convert(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(item) for item in obj]
        else:
            return obj
    
    return convert(state)


def _deserialize_state(data: dict) -> dict:
    """反序列化 state"""
    # 目前不需要特殊处理，直接返回
    return data


# ============================================================
# 核心 API
# ============================================================

def save_state(user_id: str, state: dict) -> None:
    """
    保存用户的 state 到本地文件
    
    Args:
        user_id: 用户 ID（可以是用户名、手机号等唯一标识）
        state: AgentState 字典
    
    Example:
        save_state("user_001", state)
    """
    file_path = _get_user_file(user_id)
    
    # 添加元数据
    data_to_save = {
        "user_id": user_id,
        "updated_at": datetime.now().isoformat(),
        "state": _serialize_state(state),
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    
    print(f"[Storage] Saved state for user '{user_id}' to {file_path}")


def load_state(user_id: str) -> Optional[dict]:
    """
    加载用户的 state
    
    Args:
        user_id: 用户 ID
    
    Returns:
        AgentState 字典，如果用户不存在返回 None
    
    Example:
        state = load_state("user_001")
        if state is None:
            state = create_initial_state("你好")
    """
    file_path = _get_user_file(user_id)
    
    if not file_path.exists():
        print(f"[Storage] No saved state for user '{user_id}'")
        return None
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"[Storage] Loaded state for user '{user_id}' (updated: {data.get('updated_at')})")
    return _deserialize_state(data.get("state", {}))


def delete_state(user_id: str) -> bool:
    """
    删除用户的 state
    
    Args:
        user_id: 用户 ID
    
    Returns:
        是否删除成功
    """
    file_path = _get_user_file(user_id)
    
    if file_path.exists():
        file_path.unlink()
        print(f"[Storage] Deleted state for user '{user_id}'")
        return True
    
    return False


def list_users() -> list[str]:
    """
    列出所有有保存数据的用户
    
    Returns:
        用户 ID 列表
    """
    _ensure_data_dir()
    users = []
    for file in DATA_DIR.glob("*.json"):
        users.append(file.stem)
    return users


def get_user_info(user_id: str) -> Optional[dict]:
    """
    获取用户信息摘要（不加载完整 state）
    
    Returns:
        {
            "user_id": "user_001",
            "updated_at": "2024-12-19T10:30:00",
            "message_count": 25,
            "has_status_report": True,
            ...
        }
    """
    file_path = _get_user_file(user_id)
    
    if not file_path.exists():
        return None
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    state = data.get("state", {})
    
    return {
        "user_id": user_id,
        "updated_at": data.get("updated_at"),
        "message_count": len(state.get("messages", [])),
        "has_status_report": state.get("status_report") is not None,
        "has_action_plan": state.get("action_plan") is not None,
        "action_guides_count": len(state.get("action_guides", [])),
        "crush_name": state.get("user_context", {}).get("crush_info", {}).get("crush_name", ""),
    }


# ============================================================
# 便捷函数：自动保存/加载
# ============================================================

def get_or_create_state(user_id: str, initial_message: str = "") -> dict:
    """
    获取用户的 state，如果不存在则创建新的
    
    Args:
        user_id: 用户 ID
        initial_message: 如果是新用户，使用的初始消息
    
    Returns:
        AgentState 字典
    """
    from graph.state import create_initial_state
    
    state = load_state(user_id)
    if state is None:
        state = create_initial_state(initial_message or "开始对话")
        print(f"[Storage] Created new state for user '{user_id}'")
    
    return state


class AutoSaveState:
    """
    自动保存的 State 包装器
    
    使用 with 语句自动在退出时保存
    
    Example:
        with AutoSaveState("user_001") as state:
            state["messages"].append({"role": "user", "content": "你好"})
            # 修改 state...
        # 退出 with 时自动保存
    """
    
    def __init__(self, user_id: str, initial_message: str = ""):
        self.user_id = user_id
        self.initial_message = initial_message
        self.state = None
    
    def __enter__(self) -> dict:
        self.state = get_or_create_state(self.user_id, self.initial_message)
        return self.state
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.state is not None:
            save_state(self.user_id, self.state)
        return False  # 不抑制异常


# ============================================================
# 图片文件存储（Crush 聊天截图）
# ============================================================

IMAGES_DIR = _CURRENT_DIR / "data" / "images"


def save_image(user_id: str, image_data: bytes, filename: str) -> str:
    """
    保存用户上传的图片
    
    Args:
        user_id: 用户 ID
        image_data: 图片二进制数据
        filename: 原始文件名
    
    Returns:
        保存后的文件路径
    """
    user_images_dir = IMAGES_DIR / user_id
    user_images_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成唯一文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = Path(filename).suffix or ".png"
    new_filename = f"{timestamp}_{filename}" if filename else f"{timestamp}{ext}"
    
    file_path = user_images_dir / new_filename
    with open(file_path, "wb") as f:
        f.write(image_data)
    
    print(f"[Storage] Saved image for user '{user_id}': {file_path}")
    return str(file_path)


def list_user_images(user_id: str) -> list[str]:
    """
    列出用户的所有图片
    
    Returns:
        图片文件路径列表
    """
    user_images_dir = IMAGES_DIR / user_id
    if not user_images_dir.exists():
        return []
    
    images = []
    for ext in ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp"]:
        images.extend(str(p) for p in user_images_dir.glob(ext))
    
    return sorted(images)

