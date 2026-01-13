"""
归档管理器 (Archive Manager)
管理历史摘要的分级存储和对话压缩

职责：
1. 历史摘要分级：最近 2 份中等摘要，更早的一句话摘要
2. 对话压缩触发：每超出 5 轮集中压缩一次
3. 管理归档写入：将整理 Agent 的输出写入正确的位置

基于 context_strategy.md 策略文档
"""

from typing import TYPE_CHECKING, Optional
from datetime import datetime

if TYPE_CHECKING:
    from graph.state import AgentState

from graph.context_types import (
    UserContext,
    HistoryArchive,
    HistorySummary,
    ConversationArchive,
    ActionGuideItem,
    create_empty_history_archive,
)
from graph.nodes.organize_agent import (
    archive_completed_guide,
    archive_replaced_status_report,
    archive_conversation_batch,
)


# ============================================================
# 配置常量
# ============================================================

ARCHIVE_CONFIG = {
    # 历史摘要分级
    "recent_summary_count": 2,      # 最近 N 份保留中等摘要
    "max_one_liner_count": 10,      # 最多保留 N 条一句话摘要
    "max_total_history": 20,        # 每类历史最多保留条数
    
    # 对话压缩
    "max_recent_turns": 40,         # 保留最近 N 轮完整对话
    "compression_batch_size": 5,    # 每超出 5 轮集中压缩一次
    "compression_threshold": 45,    # 超过此轮次开始检查是否需要压缩
}


# ============================================================
# 对话压缩管理
# ============================================================

def check_conversation_compression_needed(state: "AgentState") -> bool:
    """
    检查是否需要触发对话压缩
    
    触发条件：
    - 对话轮次超过 compression_threshold
    - 且超出部分达到 compression_batch_size 的倍数
    
    例如：阈值 45，批量大小 5
    - 44 轮：不压缩
    - 45 轮：不压缩（刚到阈值）
    - 50 轮：触发压缩（超出 5 轮）
    - 51-54 轮：不压缩
    - 55 轮：触发压缩（超出 10 轮）
    """
    messages = state.get("messages", [])
    current_turns = len(messages)
    
    threshold = ARCHIVE_CONFIG["compression_threshold"]
    batch_size = ARCHIVE_CONFIG["compression_batch_size"]
    
    if current_turns <= threshold:
        return False
    
    # 计算超出的轮次
    excess_turns = current_turns - threshold
    
    # 检查是否达到批量压缩的触发点
    return excess_turns > 0 and excess_turns % batch_size == 0


def get_messages_to_compress(state: "AgentState") -> tuple[list[dict], list[dict]]:
    """
    获取需要压缩的消息和保留的消息
    
    Returns:
        (to_compress, to_keep): 需要压缩的消息列表, 需要保留的消息列表
    """
    messages = state.get("messages", [])
    max_recent = ARCHIVE_CONFIG["max_recent_turns"]
    
    if len(messages) <= max_recent:
        return [], messages
    
    # 保留最近 N 轮，压缩更早的
    to_compress = messages[:-max_recent]
    to_keep = messages[-max_recent:]
    
    return to_compress, to_keep


def compress_conversation(state: "AgentState") -> dict:
    """
    执行对话压缩
    
    流程：
    1. 获取需要压缩的消息
    2. 调用整理 Agent 处理
    3. 更新历史归档
    4. 更新用户上下文（如有提取的信息）
    
    Returns:
        状态更新字典，包含：
        - messages: 压缩后保留的消息
        - history_archive: 更新后的历史归档
        - user_context: 更新后的用户上下文（如有新信息）
    """
    to_compress, to_keep = get_messages_to_compress(state)
    
    if not to_compress:
        return {}
    
    # 获取现有上下文和归档
    existing_context = state.get("user_context", {})
    existing_archive = state.get("history_archive") or create_empty_history_archive()
    
    # 调用整理 Agent 处理对话归档
    result = archive_conversation_batch(to_compress, existing_context)
    
    # 更新归档
    conversation_archives = list(existing_archive.get("conversation_archive", []))
    conversation_archives.insert(0, result["conversation_archive"])
    
    # 限制归档数量
    max_archives = ARCHIVE_CONFIG["max_total_history"]
    if len(conversation_archives) > max_archives:
        conversation_archives = conversation_archives[:max_archives]
    
    updated_archive = HistoryArchive(
        status_history=existing_archive.get("status_history", []),
        plan_history=existing_archive.get("plan_history", []),
        guide_history=existing_archive.get("guide_history", []),
        conversation_archive=conversation_archives,
    )
    
    return {
        "messages": to_keep,
        "history_archive": updated_archive,
        "user_context": result["updated_context"],
    }


# ============================================================
# 历史摘要分级管理
# ============================================================

def downgrade_old_summaries(history_list: list[HistorySummary]) -> list[HistorySummary]:
    """
    降级旧的历史摘要
    
    策略：
    - 最近 2 份：保留中等摘要（summary 字段）
    - 更早的：只保留一句话摘要（one_liner 字段），清空 summary
    - 超过最大数量的：丢弃
    
    Args:
        history_list: 历史摘要列表（按时间倒序，最新在前）
    
    Returns:
        处理后的历史摘要列表
    """
    recent_count = ARCHIVE_CONFIG["recent_summary_count"]
    max_one_liner = ARCHIVE_CONFIG["max_one_liner_count"]
    max_total = recent_count + max_one_liner
    
    processed = []
    for i, item in enumerate(history_list[:max_total]):
        if i < recent_count:
            # 最近的保留完整摘要
            processed.append(item)
        else:
            # 更早的降级为一句话
            downgraded = HistorySummary(
                id=item.get("id", ""),
                summary="",  # 清空中等摘要
                one_liner=item.get("one_liner", item.get("summary", "")[:30]),
                created_at=item.get("created_at", ""),
                full_content=item.get("full_content", ""),  # 完整内容保留，供抽屉式调用
            )
            processed.append(downgraded)
    
    return processed


def add_to_history(
    existing_archive: HistoryArchive,
    new_summary: HistorySummary,
    history_type: str,
) -> HistoryArchive:
    """
    添加新摘要到历史归档
    
    Args:
        existing_archive: 现有归档
        new_summary: 新的摘要
        history_type: 归档类型 (status_history / plan_history / guide_history)
    
    Returns:
        更新后的归档
    """
    archive_dict = {
        "status_history": list(existing_archive.get("status_history", [])),
        "plan_history": list(existing_archive.get("plan_history", [])),
        "guide_history": list(existing_archive.get("guide_history", [])),
        "conversation_archive": list(existing_archive.get("conversation_archive", [])),
    }
    
    # 插入新摘要到开头
    if history_type in archive_dict:
        archive_dict[history_type].insert(0, new_summary)
        # 降级旧摘要
        archive_dict[history_type] = downgrade_old_summaries(archive_dict[history_type])
    
    return HistoryArchive(**archive_dict)


# ============================================================
# 行动指南归档
# ============================================================

def archive_guide_on_completion(
    guide: ActionGuideItem,
    state: "AgentState",
) -> dict:
    """
    当行动指南完成时触发归档
    
    Args:
        guide: 已完成的行动指南
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    existing_context = state.get("user_context", {})
    existing_archive = state.get("history_archive") or create_empty_history_archive()
    
    # 调用整理 Agent
    result = archive_completed_guide(guide, existing_context)
    
    # 添加到历史归档
    updated_archive = add_to_history(
        existing_archive,
        result["guide_summary"],
        "guide_history",
    )
    
    return {
        "history_archive": updated_archive,
        "user_context": result["updated_context"],
    }


# ============================================================
# 现状分析归档
# ============================================================

def archive_status_on_replacement(
    old_report: dict,
    state: "AgentState",
) -> dict:
    """
    当现状分析被新版替换时触发归档
    
    Args:
        old_report: 被替换的旧报告
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    existing_context = state.get("user_context", {})
    existing_archive = state.get("history_archive") or create_empty_history_archive()
    
    # 调用整理 Agent
    result = archive_replaced_status_report(old_report, existing_context)
    
    # 添加到历史归档
    updated_archive = add_to_history(
        existing_archive,
        result["status_summary"],
        "status_history",
    )
    
    return {
        "history_archive": updated_archive,
        "user_context": result["updated_context"],
    }


# ============================================================
# 统一归档入口
# ============================================================

def process_archiving_if_needed(state: "AgentState") -> dict:
    """
    统一归档入口：检查并处理所有需要归档的内容
    
    在每轮结束时调用，检查：
    1. 是否需要对话压缩
    2. 是否有已完成的行动指南需要归档
    
    Returns:
        状态更新字典（如果没有需要归档的内容，返回空字典）
    """
    updates = {}
    
    # 1. 检查对话压缩
    if check_conversation_compression_needed(state):
        compression_result = compress_conversation(state)
        updates.update(compression_result)
        print(f"[Archive] Compressed conversation, kept {len(compression_result.get('messages', []))} messages")
    
    # 2. 检查已完成的行动指南
    # 注意：这部分通常在 guide 状态变更时触发，而不是这里统一处理
    # 但这里提供一个检查点，以防遗漏
    
    return updates


# ============================================================
# 调试/查询函数
# ============================================================

def get_archive_stats(state: "AgentState") -> dict:
    """
    获取归档统计信息（用于调试）
    """
    archive = state.get("history_archive") or {}
    messages = state.get("messages", [])
    
    return {
        "conversation_turns": len(messages),
        "status_history_count": len(archive.get("status_history", [])),
        "plan_history_count": len(archive.get("plan_history", [])),
        "guide_history_count": len(archive.get("guide_history", [])),
        "conversation_archive_count": len(archive.get("conversation_archive", [])),
        "compression_needed": check_conversation_compression_needed(state),
    }


def get_full_history_content(
    state: "AgentState",
    history_type: str,
    index: int,
) -> Optional[str]:
    """
    获取历史记录的完整内容（抽屉式调用）
    
    Args:
        state: 当前状态
        history_type: status_history / plan_history / guide_history
        index: 历史记录索引
    
    Returns:
        完整内容，如果不存在返回 None
    """
    archive = state.get("history_archive") or {}
    history_list = archive.get(history_type, [])
    
    if 0 <= index < len(history_list):
        return history_list[index].get("full_content")
    
    return None
