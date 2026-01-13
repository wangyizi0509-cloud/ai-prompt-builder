"""
上下文类型定义
定义 3×3 静态情报矩阵和相关数据结构

基于 context_strategy.md 策略文档
"""

from typing import TypedDict, Literal, Optional
from datetime import datetime


# ============================================================
# Layer 1: 静态情报 - 3×3 矩阵
# ============================================================

class InfoSource(TypedDict, total=False):
    """
    信息来源三元组
    
    信任优先级（冲突时的判断依据）：
    1. 最高可信 - fact: 客观事实（聊天记录、截图等直接证据）
    2. 中等可信 - ai_provide: AI分析（基于证据的推断）
    3. 最低可信 - user_provide: 用户口述（可能美化或误读）
    """
    user_provide: str  # 用户口述的信息
    fact: str          # 客观事实（截图、记录等直接证据）
    ai_provide: str    # AI军师分析得出的信息


class CrushInfo(TypedDict, total=False):
    """Crush 信息（含名称）"""
    crush_name: str     # Crush 名称或昵称
    user_provide: str   # 用户描述的 Crush
    fact: str           # 聊天记录/社媒截图提取的信息
    ai_provide: str     # AI 分析（如性格特征、依恋类型）


class UserContext(TypedDict, total=False):
    """
    3×3 静态情报矩阵
    
    行：信息归属（用户/Crush/双方）
    列：信息来源（用户提供/客观事实/AI分析）
    """
    user_info: InfoSource   # 用户自身信息
    crush_info: CrushInfo   # Crush 信息
    both_info: InfoSource   # 双方相处信息


# ============================================================
# Layer 2: 工作上下文 - 行动指南项
# ============================================================

class ActionGuideContent(TypedDict, total=False):
    """行动指南内容（战术层）"""
    current_task: str           # 当前任务
    steps: list[str]            # 具体步骤
    talking_points: list[str]   # 话术要点
    dos: list[str]              # 该做的
    donts: list[str]            # 不该做的
    next_milestone: str         # 下一个里程碑
    guide_content: str          # Markdown 格式的完整指南


class ActionGuideItem(TypedDict, total=False):
    """
    行动指南项（支持多个未执行指南）
    
    状态流转：pending -> in_progress -> completed
    未执行的指南（pending/in_progress）完整保留，不可压缩
    """
    id: str                         # 唯一标识
    status: Literal["pending", "in_progress", "completed"]
    guide: ActionGuideContent       # 指南内容
    created_at: str                 # 创建时间 ISO 格式
    completed_at: Optional[str]     # 完成时间（completed 状态时填充）


# ============================================================
# Layer 4: 历史存档
# ============================================================

class HistorySummary(TypedDict, total=False):
    """历史摘要项"""
    id: str                 # 唯一标识
    summary: str            # 中等长度摘要（100-200字）
    one_liner: str          # 一句话摘要（20-30字）
    created_at: str         # 创建时间
    full_content: str       # 完整内容（抽屉式存储，按需调用）


class ConversationArchive(TypedDict, total=False):
    """对话归档项"""
    id: str                 # 唯一标识
    summary: str            # 压缩摘要
    start_time: str         # 对话开始时间
    end_time: str           # 对话结束时间
    turn_count: int         # 对话轮次
    key_topics: list[str]   # 关键话题
    extracted_info: dict    # 提取的高价值信息


class HistoryArchive(TypedDict, total=False):
    """
    历史存档
    
    摘要分级：
    - 最近 1-2 份：中等摘要（常驻）
    - 更早的：一句话摘要（常驻）
    - 完整内容：按需调用（抽屉式）
    """
    status_history: list[HistorySummary]        # 历史现状分析
    plan_history: list[HistorySummary]          # 历史行动规划
    guide_history: list[HistorySummary]         # 历史行动指南（已完成的）
    conversation_archive: list[ConversationArchive]  # 对话归档


# ============================================================
# Crush 聊天记录分层存储（P2 预留）
# ============================================================

class CrushChatMetadata(TypedDict, total=False):
    """
    Crush 聊天记录元数据 (L1)
    常驻上下文
    """
    total_messages: int         # 总消息数
    chat_frequency: str         # 聊天频率描述
    time_span: str              # 时间跨度
    last_chat_time: str         # 最后聊天时间


class CrushChatSummary(TypedDict, total=False):
    """
    Crush 聊天记录结构化摘要 (L2)
    常驻上下文
    """
    key_events: list[str]       # 关键事件
    emotional_turns: list[str]  # 情感转折点
    main_topics: list[str]      # 主要话题


class CrushChatStorage(TypedDict, total=False):
    """
    Crush 聊天记录完整存储结构
    L1/L2 常驻，L3/L4 按需调用
    """
    metadata: CrushChatMetadata         # L1: 元数据
    summary: CrushChatSummary            # L2: 结构化摘要
    # L3/L4 存储在外部，通过工具调用


# ============================================================
# 工具函数
# ============================================================

def create_empty_user_context() -> UserContext:
    """创建空的用户上下文"""
    return UserContext(
        user_info=InfoSource(
            user_provide="",
            fact="",
            ai_provide="",
        ),
        crush_info=CrushInfo(
            crush_name="",
            user_provide="",
            fact="",
            ai_provide="",
        ),
        both_info=InfoSource(
            user_provide="",
            fact="",
            ai_provide="",
        ),
    )


def create_empty_history_archive() -> HistoryArchive:
    """创建空的历史存档"""
    return HistoryArchive(
        status_history=[],
        plan_history=[],
        guide_history=[],
        conversation_archive=[],
    )


def create_action_guide_item(
    guide: ActionGuideContent,
    status: Literal["pending", "in_progress", "completed"] = "pending"
) -> ActionGuideItem:
    """创建行动指南项"""
    import uuid
    return ActionGuideItem(
        id=str(uuid.uuid4())[:8],
        status=status,
        guide=guide,
        created_at=datetime.now().isoformat(),
        completed_at=None,
    )
