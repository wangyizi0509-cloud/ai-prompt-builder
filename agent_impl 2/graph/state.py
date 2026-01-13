"""
AgentState 状态定义
定义 LangGraph 工作流中传递的状态结构

更新记录：
- v2.0: 重构为分层上下文架构，引入 3×3 静态情报矩阵
"""

from typing import TypedDict, Literal, Optional, Annotated
from operator import add

# 导入新的上下文类型
from graph.context_types import (
    UserContext,
    ActionGuideItem,
    ActionGuideContent,
    HistoryArchive,
    CrushChatStorage,
    create_empty_user_context,
    create_empty_history_archive,
)


class Message(TypedDict):
    """单条消息"""
    role: Literal["user", "assistant", "system"]
    content: str


# ============================================================
# 保留原有类型（向后兼容）
# ============================================================

class UserProfile(TypedDict, total=False):
    """
    用户情报（旧版，保留向后兼容）
    
    @deprecated: 请使用 UserContext（3×3 矩阵）替代
    """
    name: str
    age: int
    gender: str
    occupation: str
    crush_info: str  # Crush 基本信息
    relationship_context: str  # 关系背景
    known_facts: list[str]  # 已知事实列表


class StatusReport(TypedDict, total=False):
    """现状分析报告"""
    stage: str  # L1-L4 或 T1-T3
    stage_description: str  # 阶段描述
    acr_analysis: dict  # A/C/R 三维分析
    key_issues: list[str]  # 核心问题
    risk_points: list[str]  # 风险点
    summary: str  # 总结
    report_content: str  # Markdown 格式的完整报告


class ActionPlan(TypedDict, total=False):
    """行动规划（战略层）"""
    goal: str  # 阶段性目标
    strategy: str  # 核心策略方向
    phases: list[dict]  # 分阶段计划
    key_principles: list[str]  # 关键原则
    summary: str  # 总结


class ActionGuide(TypedDict, total=False):
    """
    行动指南（战术层）- 旧版单个指南
    
    @deprecated: 请使用 ActionGuideItem 列表替代
    """
    current_task: str  # 当前任务
    steps: list[str]  # 具体步骤
    talking_points: list[str]  # 话术要点
    dos: list[str]  # 该做的
    donts: list[str]  # 不该做的
    next_milestone: str  # 下一个里程碑
    guide_content: str  # Markdown 格式的完整指南


# ============================================================
# AgentState - 核心状态对象
# ============================================================

class AgentState(TypedDict, total=False):
    """
    Agent 工作流状态
    
    这是 LangGraph 工作流中传递的核心状态对象
    
    上下文分层架构（基于 context_strategy.md）：
    - Layer 0: 系统指令区（只读常驻）- 在 Prompt 中定义
    - Layer 1: 静态情报区 -> user_context
    - Layer 2: 工作上下文 -> status_report, action_plan, action_guides
    - Layer 3: 滚动对话区 -> messages
    - Layer 4: 外部长期记忆 -> history_archive
    """
    
    # === 用户输入 ===
    user_message: str  # 用户当前消息
    
    # === Layer 3: 对话历史（滚动窗口）===
    messages: Annotated[list[Message], add]  # 对话历史（自动累加）
    
    # === Layer 1: 静态情报（3×3 矩阵）===
    user_context: UserContext  # 新版：3×3 静态情报矩阵
    user_profile: UserProfile  # 旧版：保留向后兼容，后续逐步迁移
    
    # === Layer 2: 工作上下文 ===
    status_report: Optional[StatusReport]  # 现状分析报告（最新版）
    action_plan: Optional[ActionPlan]  # 行动规划（最新版）
    action_guides: list[ActionGuideItem]  # 行动指南列表（支持多个未执行指南）
    action_guide: Optional[ActionGuide]  # 旧版：保留向后兼容
    
    # === Layer 4: 历史存档 ===
    history_archive: HistoryArchive  # 历史摘要和归档
    
    # === Crush 聊天记录存储（P2 预留）===
    crush_chat_storage: Optional[CrushChatStorage]
    
    # === 流程控制 ===
    intent_type: Literal[
        "consult_only",     # 纯咨询
        "emotion_vent",     # 情绪发泄
        "action_trigger",   # 触发行动
        "info_update",      # 信息更新
        "off_topic",        # 无关话题
    ]
    
    next_action: Literal[
        "ask_user",         # 向用户提问
        "call_status",      # 调用现状分析 Agent
        "call_plan",        # 调用行动规划 Agent
        "call_guide",       # 调用行动指南 Agent
        "end_turn",         # 结束本轮
    ]
    
    # === Agent 输出 ===
    # pending_responses 格式:
    # [{"from": "agent_id", "content": "消息", "phase": "immediate|after_status|after_plan|after_guide"}]
    # phase 说明：
    # - immediate: 立即展示（主 Agent 第一次回复）
    # - after_status: 现状分析完成后展示
    # - after_plan: 行动规划完成后展示
    # - after_guide: 行动指南完成后展示
    pending_responses: list[dict]
    pending_questions: list[str]  # 待回答的问题（由提问 Skill 生成）
    inquiry_card: Optional[dict]  # 提问卡片数据（前端渲染用）
    
    # === 子 Agent 完成信号 ===
    completion_status: Optional[str]  # COMPLETED / NEED_MORE_INFO / BLOCKED / None
    result_summary: Optional[str]  # 任务结果摘要（供主 Agent 决策用）
    
    # === 对话连贯性 ===
    last_response_for_continuity: Optional[str]  # 主 Agent 刚说的话，传给子 Agent 保持连贯
    
    # === 路由控制 ===
    should_continue: bool  # 是否继续执行
    route_to: str  # 下一个节点

    # === Agent 执行状态（用于恢复执行）===
    current_agent: Optional[str]  # 当前执行的 Agent (status_agent/plan_agent/guide_agent)
    agent_resume_point: Optional[str]  # Agent 恢复点标识
    collected_info: dict  # 本轮已收集的信息
    question_count: int  # 已提问次数
    max_questions: int  # 最大提问次数（默认3）

    # === 调试日志 ===
    debug_log: Annotated[list[dict], add]  # 调试日志（自动累加）


# ============================================================
# 状态创建和迁移函数
# ============================================================

def create_initial_state(user_message: str) -> AgentState:
    """
    创建初始状态
    
    Args:
        user_message: 用户的第一条消息
    
    Returns:
        初始化的 AgentState
    """
    return AgentState(
        user_message=user_message,
        messages=[{"role": "user", "content": user_message}],
        # Layer 1: 静态情报
        user_context=create_empty_user_context(),
        user_profile={},  # 向后兼容
        # Layer 2: 工作上下文
        status_report=None,
        action_plan=None,
        action_guides=[],  # 新版：列表
        action_guide=None,  # 向后兼容
        # Layer 4: 历史存档
        history_archive=create_empty_history_archive(),
        # Crush 聊天记录
        crush_chat_storage=None,
        # 流程控制
        intent_type="action_trigger",
        next_action="end_turn",
        pending_responses=[],
        pending_questions=[],
        should_continue=True,
        route_to="main_agent",
        # Agent 执行状态
        current_agent=None,
        agent_resume_point=None,
        collected_info={},
        question_count=0,
        max_questions=3,
        # 子 Agent 完成信号
        completion_status=None,
        result_summary=None,
        # 对话连贯性
        last_response_for_continuity=None,
        debug_log=[],
    )


def migrate_user_profile_to_context(old_profile: UserProfile) -> UserContext:
    """
    将旧的 UserProfile 迁移到新的 UserContext（3×3 矩阵）
    
    迁移规则：
    - name/age/gender/occupation -> user_info.user_provide
    - crush_info -> crush_info.user_provide
    - relationship_context -> both_info.user_provide
    - known_facts -> both_info.fact（客观事实）
    
    Args:
        old_profile: 旧版 UserProfile
    
    Returns:
        新版 UserContext
    """
    # 提取用户基本信息
    user_provide_parts = []
    if old_profile.get("name"):
        user_provide_parts.append(f"姓名：{old_profile['name']}")
    if old_profile.get("age"):
        user_provide_parts.append(f"年龄：{old_profile['age']}")
    if old_profile.get("gender"):
        user_provide_parts.append(f"性别：{old_profile['gender']}")
    if old_profile.get("occupation"):
        user_provide_parts.append(f"职业：{old_profile['occupation']}")
    
    return UserContext(
        user_info={
            "user_provide": "\n".join(user_provide_parts) if user_provide_parts else "",
            "fact": "",
            "ai_provide": "",
        },
        crush_info={
            "crush_name": "",  # 需要从其他地方提取
            "user_provide": old_profile.get("crush_info", ""),
            "fact": "",
            "ai_provide": "",
        },
        both_info={
            "user_provide": old_profile.get("relationship_context", ""),
            "fact": "\n".join(old_profile.get("known_facts", [])),
            "ai_provide": "",
        },
    )


def get_active_action_guides(action_guides: list[ActionGuideItem]) -> list[ActionGuideItem]:
    """
    获取所有活跃的（未完成的）行动指南
    
    Args:
        action_guides: 行动指南列表
    
    Returns:
        状态为 pending 或 in_progress 的指南列表
    """
    return [
        guide for guide in action_guides
        if guide.get("status") in ("pending", "in_progress")
    ]


def get_completed_action_guides(action_guides: list[ActionGuideItem]) -> list[ActionGuideItem]:
    """
    获取所有已完成的行动指南
    
    Args:
        action_guides: 行动指南列表
    
    Returns:
        状态为 completed 的指南列表
    """
    return [
        guide for guide in action_guides
        if guide.get("status") == "completed"
    ]
