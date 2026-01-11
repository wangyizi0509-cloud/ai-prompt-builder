"""
State 本地持久化存储
使用 JSON 文件存储每个用户的 AgentState

特点：
- 简单易用，无需数据库
- 按用户 ID 区分，每人一个文件
- 团队成员各自电脑上存各自的数据
- 支持自动保存和加载
- 支持分层长期记忆架构（v3.0）

存储位置：agent_impl/data/users/{user_id}.json

更新记录：
- v3.0: 适配分层长期记忆架构（Layer 1/2/3 Memory）
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


def _migrate_to_layered_memory(state: dict) -> dict:
    """
    将旧版状态迁移到新的分层长期记忆架构
    
    迁移逻辑：
    - 如果没有 layer1_memory，从 user_context 创建
    - 如果没有 layer2_memory，从 status_report/action_plan/action_guides 创建
    - 如果没有 layer3_memory，从 messages 创建
    - 将 history_archive 内容迁移到各层
    """
    from graph.context_types import (
        create_empty_layer1_memory,
        create_empty_layer2_memory,
        create_empty_layer3_memory,
        create_empty_user_context,
        ConversationSummary,
        StatusReportItem,
        ActionPlanItem,
    )
    
    # 如果已经有新版字段，直接返回
    if state.get("layer1_memory") and state.get("layer2_memory") and state.get("layer3_memory"):
        return state
    
    print("[Storage] Migrating state to layered memory architecture...")
    
    # 迁移 Layer 1
    if not state.get("layer1_memory"):
        layer1 = create_empty_layer1_memory()
        if state.get("user_context"):
            layer1["full_data"] = state["user_context"]
        state["layer1_memory"] = layer1
    
    # 迁移 Layer 2
    if not state.get("layer2_memory"):
        layer2 = create_empty_layer2_memory()
        
        # 迁移现状分析报告
        if state.get("status_report"):
            report = state["status_report"]
            report_item = StatusReportItem(
                id=report.get("id", "migrated_1"),
                report_id=state.get("report_counter", {}).get("status_report", 1),
                is_current=True,
                stage=report.get("stage", ""),
                stage_description=report.get("stage_description", ""),
                acr_analysis=report.get("acr_analysis", {}),
                key_issues=report.get("key_issues", []),
                risk_points=report.get("risk_points", []),
                report_content=report.get("report_content", ""),
                created_at=datetime.now().isoformat(),
            )
            layer2["all_status_reports"] = [report_item]
        
        # 迁移行动规划
        if state.get("action_plan"):
            plan = state["action_plan"]
            plan_item = ActionPlanItem(
                id=plan.get("id", "migrated_1"),
                plan_id=state.get("report_counter", {}).get("action_plan", 1),
                is_current=True,
                goal=plan.get("goal", ""),
                strategy=plan.get("strategy", ""),
                phases=plan.get("phases", []),
                key_principles=plan.get("key_principles", []),
                plan_content=plan.get("plan_content", ""),
                created_at=datetime.now().isoformat(),
            )
            layer2["all_action_plans"] = [plan_item]
        
        # 迁移行动指南
        if state.get("action_guides"):
            layer2["all_action_guides"] = state["action_guides"]
        
        # 迁移历史摘要
        if state.get("history_archive"):
            archive = state["history_archive"]
            
            # 迁移历史现状分析
            for i, item in enumerate(archive.get("status_history", [])):
                report_item = StatusReportItem(
                    id=item.get("id", f"history_{i}"),
                    report_id=0,
                    is_current=False,
                    report_content=item.get("full_content", ""),
                    summary=item.get("summary", ""),
                    one_liner=item.get("one_liner", ""),
                    created_at=item.get("created_at", ""),
                )
                layer2["all_status_reports"].append(report_item)
        
        state["layer2_memory"] = layer2
    
    # 迁移 Layer 3
    if not state.get("layer3_memory"):
        layer3 = create_empty_layer3_memory()
        
        if state.get("messages"):
            layer3["all_messages"] = list(state["messages"])
        
        # 迁移对话归档
        if state.get("history_archive"):
            archive = state["history_archive"]
            for conv in archive.get("conversation_archive", []):
                summary = ConversationSummary(
                    id=conv.get("id", ""),
                    summary=conv.get("summary", ""),
                    start_time=conv.get("start_time", ""),
                    end_time=conv.get("end_time", ""),
                    turn_count=conv.get("turn_count", 0),
                    key_topics=conv.get("key_topics", []),
                    extracted_info=conv.get("extracted_info", {}),
                )
                layer3["conversation_summaries"].append(summary)
        
        state["layer3_memory"] = layer3
    
    print("[Storage] Migration completed")
    return state


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
        "version": "3.0",  # 标记存储版本
        "state": _serialize_state(state),
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=2)
    
    print(f"[Storage] Saved state for user '{user_id}' to {file_path}")


def load_state(user_id: str, auto_migrate: bool = True) -> Optional[dict]:
    """
    加载用户的 state
    
    Args:
        user_id: 用户 ID
        auto_migrate: 是否自动迁移旧版数据到新架构
    
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
    
    state = _deserialize_state(data.get("state", {}))
    
    # 检查版本，自动迁移旧版数据
    version = data.get("version", "1.0")
    if auto_migrate and version < "3.0":
        print(f"[Storage] Detected old version ({version}), migrating...")
        state = _migrate_to_layered_memory(state)
        # 保存迁移后的数据
        save_state(user_id, state)
    
    print(f"[Storage] Loaded state for user '{user_id}' (updated: {data.get('updated_at')}, version: {version})")
    return state


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
            "version": "3.0",
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
    version = data.get("version", "1.0")
    
    # 根据版本获取不同字段
    if version >= "3.0":
        # 新版：从分层长期记忆获取
        layer1 = state.get("layer1_memory", {})
        layer2 = state.get("layer2_memory", {})
        layer3 = state.get("layer3_memory", {})
        
        message_count = len(layer3.get("all_messages", state.get("messages", [])))
        has_status_report = any(
            r.get("is_current") for r in layer2.get("all_status_reports", [])
        )
        has_action_plan = any(
            p.get("is_current") for p in layer2.get("all_action_plans", [])
        )
        action_guides_count = len([
            g for g in layer2.get("all_action_guides", [])
            if g.get("status") in ("pending", "in_progress", "paused")
        ])
        crush_name = layer1.get("full_data", {}).get("crush_info", {}).get("crush_name", "")
        conversation_summaries = len(layer3.get("conversation_summaries", []))
    else:
        # 旧版：从原始字段获取
        message_count = len(state.get("messages", []))
        has_status_report = state.get("status_report") is not None
        has_action_plan = state.get("action_plan") is not None
        action_guides_count = len(state.get("action_guides", []))
        crush_name = state.get("user_context", {}).get("crush_info", {}).get("crush_name", "")
        conversation_summaries = len(state.get("history_archive", {}).get("conversation_archive", []))
    
    return {
        "user_id": user_id,
        "updated_at": data.get("updated_at"),
        "version": version,
        "message_count": message_count,
        "has_status_report": has_status_report,
        "has_action_plan": has_action_plan,
        "action_guides_count": action_guides_count,
        "crush_name": crush_name,
        "conversation_summaries": conversation_summaries,
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
# 分层长期记忆专用函数
# ============================================================

def get_layer_memory(user_id: str, layer: int) -> Optional[dict]:
    """
    获取指定层的长期记忆
    
    Args:
        user_id: 用户 ID
        layer: 层级（1, 2, 或 3）
    
    Returns:
        对应层的 Memory 字典，如果不存在返回 None
    """
    state = load_state(user_id)
    if state is None:
        return None
    
    layer_key = f"layer{layer}_memory"
    return state.get(layer_key)


def update_layer_memory(user_id: str, layer: int, memory: dict) -> bool:
    """
    更新指定层的长期记忆
    
    Args:
        user_id: 用户 ID
        layer: 层级（1, 2, 或 3）
        memory: 新的 Memory 字典
    
    Returns:
        是否更新成功
    """
    state = load_state(user_id)
    if state is None:
        return False
    
    layer_key = f"layer{layer}_memory"
    state[layer_key] = memory
    save_state(user_id, state)
    return True


def get_extraction_config(user_id: str, layer: int) -> Optional[dict]:
    """
    获取指定层的提取策略配置
    
    Args:
        user_id: 用户 ID
        layer: 层级（1, 2, 或 3）
    
    Returns:
        提取策略配置字典
    """
    memory = get_layer_memory(user_id, layer)
    if memory is None:
        return None
    
    return memory.get("extraction_config", {})


def update_extraction_config(user_id: str, layer: int, config: dict) -> bool:
    """
    更新指定层的提取策略配置
    
    Args:
        user_id: 用户 ID
        layer: 层级（1, 2, 或 3）
        config: 新的提取策略配置
    
    Returns:
        是否更新成功
    """
    state = load_state(user_id)
    if state is None:
        return False
    
    layer_key = f"layer{layer}_memory"
    if layer_key not in state:
        return False
    
    state[layer_key]["extraction_config"] = config
    save_state(user_id, state)
    return True


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
