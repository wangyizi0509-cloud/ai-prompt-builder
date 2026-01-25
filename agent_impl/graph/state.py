"""
AgentState 状态定义
定义 LangGraph 工作流中传递的状态结构

更新记录：
- v2.0: 重构为分层上下文架构，引入 3×3 静态情报矩阵
- v2.1: 使用 LangGraph 官方的 add_messages reducer，添加循环计数器
- v3.0: 分层长期记忆架构，删除统一 Layer 4，改为各层独立长期记忆
- v3.1: 将模型推理 (Rolling Scratchpad) 移入 Layer 3，增加滚动摘要
"""

from typing import Literal, Optional, Annotated
from typing_extensions import TypedDict
from datetime import datetime
import uuid
from operator import add

# 使用 LangGraph 官方的消息合并逻辑
from langgraph.graph import add_messages

# 导入新的上下文类型
from graph.context_types import (
    # Layer 1
    UserContext,
    Layer1Memory,
    Layer1ExtractionConfig,
    # Layer 2
    ActionGuideItem,
    ActionGuideContent,
    StatusReportItem,
    ActionPlanItem,
    Layer2Memory,
    Layer2ExtractionConfig,
    # Layer 3
    Layer3Memory,
    Layer3ExtractionConfig,
    ConversationSummary,
    # 其他
    CrushChatStorage,
    AgentTaskRegistry,
    ReportCounter,
    TaskState,
    # 向后兼容
    HistoryArchive,
    # 工厂函数
    create_empty_user_context,
    create_empty_layer1_memory,
    create_empty_layer2_memory,
    create_empty_layer3_memory,
    create_empty_history_archive,
    create_empty_task_registry,
    create_empty_report_counter,
)


class Message(TypedDict):
    """单条消息"""
    role: Literal["user", "assistant", "system"]
    content: str
    id: Optional[str]


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
    """
    现状分析报告（旧版）
    
    @deprecated: 请使用 StatusReportItem 替代
    """
    stage: str  # L1-L4 或 T1-T3
    stage_description: str  # 阶段描述
    acr_analysis: dict  # A/C/R 三维分析
    key_issues: list[str]  # 核心问题
    risk_points: list[str]  # 风险点
    summary: str  # 总结
    report_content: str  # Markdown 格式的完整报告


class ActionPlan(TypedDict, total=False):
    """
    行动规划（战略层）- 旧版
    
    @deprecated: 请使用 ActionPlanItem 替代
    """
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
    
    分层长期记忆架构（基于 context_strategy.md v3.0）：
    - Layer 0: 系统指令区（只读常驻）- 在 Prompt 中定义
    - Layer 1: 静态情报 -> layer1_memory（长期记忆）-> 提取后输出
    - Layer 2: 工作上下文 -> layer2_memory（长期记忆）-> 提取后输出
    - Layer 3: 对话历史 -> layer3_memory（长期记忆）-> 提取后输出
    """
    
    # === 用户输入 ===
    user_message: str  # 用户当前消息
    current_message_id: Optional[str]  # 用户当前消息的唯一 ID（用于去重）
    
    # === Layer 1: 静态情报（分层长期记忆）===
    layer1_memory: Layer1Memory  # Layer 1 长期记忆（全量 + 提取配置）
    # 向后兼容字段
    user_context: UserContext    # @deprecated: 直接访问，请使用 layer1_memory.full_data
    user_profile: UserProfile    # @deprecated: 旧版，保留向后兼容
    
    # === Layer 2: 工作上下文（分层长期记忆）===
    layer2_memory: Layer2Memory  # Layer 2 长期记忆（全量 + 提取配置）
    # 向后兼容字段
    status_report: Optional[StatusReport]         # @deprecated: 请使用 layer2_memory
    action_plan: Optional[ActionPlan]             # @deprecated: 请使用 layer2_memory
    action_guides: list[ActionGuideItem]          # @deprecated: 请使用 layer2_memory
    action_guide: Optional[ActionGuide]           # @deprecated: 旧版单个指南
    
    # === Layer 3: 对话历史与推理（分层长期记忆）===
    layer3_memory: Layer3Memory  # Layer 3 长期记忆（全量 + 提取配置）
    # messages 字段仍然保留，用于 LangGraph 的消息流
    # 但实际的长期存储和提取逻辑由 layer3_memory 管理
    messages: Annotated[list, add_messages]
    
    # === 向后兼容：旧的 Layer 4 历史存档 ===
    history_archive: HistoryArchive  # @deprecated: 请使用各层的 memory
    
    # === Crush 聊天记录存储 ===
    crush_chat_storage: Optional[CrushChatStorage]
    
    # === 任务级思考过程管理 (Rolling Scratchpad) ===
    task_registry: AgentTaskRegistry  # @deprecated: 移入 layer3_memory.task_registry，保留此字段仅为向后兼容
    
    # === 报告编号追踪 ===
    report_counter: ReportCounter
    
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
    pending_responses: list[dict]
    pending_questions: list[str]
    inquiry_card: Optional[dict]
    # Onboarding: 局势初判卡（前端可直接渲染）
    preliminary_assessment: Optional[dict]
    
    # === 子 Agent 完成信号 ===
    completion_status: Optional[str]
    result_summary: Optional[str]
    
    # === 对话连贯性 ===
    last_response_for_continuity: Optional[str]
    
    # === 路由控制 ===
    should_continue: bool
    route_to: str

    # === Agent 执行状态 ===
    current_agent: Optional[str]
    agent_resume_point: Optional[str]
    _tool_caller: Optional[str]
    # 最新一次工具输出（用于二阶段 Prompt 注入）
    _last_tool_outputs: list
    _last_tool_content: Optional[str]
    # 工具触发的状态机切换信息
    _handoff_target: Optional[str]
    _handoff_instruction: Optional[str]
    # 两阶段工具强制执行标记
    _pending_action: Optional[str]
    collected_info: dict
    # 指令（Main Agent 给专家的 Brief）
    instruction: Optional[str]
    # Onboarding 状态
    onboarding_completed: bool
    onboarding_turn_count: int
    onboarding_max_turns: int
    onboarding_handoff: Optional[dict]
    last_onboarding_question: Optional[str]
    question_count: int
    max_questions: int

    # === 提问节流（vNext）：同一 Agent 连续提问轮次控制 ===
    # 规则：同一 agent 连续 ask_user 不超过 max_question_streak；一旦中间发生非提问动作（如出报告/路由到其它 agent/结束本轮但不在提问暂停态），立即清零。
    question_streak_agent: Optional[str]        # 当前连续提问的 agent（main_agent/status_agent/plan_agent/guide_agent）
    question_streak_count: int                 # 当前连续提问轮次（仅对 question_streak_agent 生效）
    max_question_streak: int                   # 同一 agent 连续提问的最大轮次（默认 3）
    
    # === 提问模式（渐进式披露）===
    # ask_mode=False 时：ask 工具只能设置为 enable（进入提问模式）
    # ask_mode=True 时：ask 工具变为完整的提问 schema，强制模型调用
    ask_mode: bool                              # 提问模式状态，默认 False
    ask_mode_tool_message_id: Optional[str]     # Phase 1 的 ToolMessage ID，用于后续简化
    
    # === 解答模式（渐进式披露）===
    # consult_mode=False 时：consult_answer 工具只能设置为 enable（进入解答模式）
    # consult_mode=True 时：consult_answer 工具变为 complete 版本，模型输出 content + tool_call(complete)
    consult_mode: bool                              # 解答模式状态，默认 False
    consult_mode_tool_message_id: Optional[str]     # Phase 1 的 ToolMessage ID，用于后续简化
    
    # === 情感陪伴模式（渐进式披露）===
    # emotion_mode=False 时：emotion_support 工具只能设置为 enable（进入陪伴模式）
    # emotion_mode=True 时：emotion_support 工具变为 complete 版本，模型输出 content + tool_call(complete)
    emotion_mode: bool                              # 情感陪伴模式状态，默认 False
    emotion_mode_tool_message_id: Optional[str]     # Phase 1 的 ToolMessage ID，用于后续简化
    
    # === 循环控制 ===
    _iteration_count: int

    # === 调试日志 ===
    debug_log: Annotated[list[dict], add]


# ============================================================
# 状态创建和迁移函数
# ============================================================

def create_initial_state(user_message: str, **overrides) -> AgentState:
    """
    创建初始状态
    
    Args:
        user_message: 用户的第一条消息
    
    Returns:
        初始化的 AgentState
    """
    # 创建各层长期记忆
    layer1 = create_empty_layer1_memory()
    layer2 = create_empty_layer2_memory()
    layer3 = create_empty_layer3_memory()
    
    # 初始化 Layer 3 的消息，确保带有唯一 ID
    first_msg_id = str(overrides.get("current_message_id") or uuid.uuid4())
    layer3["all_messages"] = [{"role": "user", "content": user_message, "id": first_msg_id}]
    
    state = AgentState(
        user_message=user_message,
        current_message_id=first_msg_id,
        messages=[{"role": "user", "content": user_message, "id": first_msg_id}],
        
        # Layer 1: 静态情报
        layer1_memory=layer1,
        user_context=layer1["full_data"],  # 向后兼容
        user_profile={},
        
        # Layer 2: 工作上下文
        layer2_memory=layer2,
        status_report=None,
        action_plan=None,
        action_guides=[],
        action_guide=None,
        preliminary_assessment=None,
        
        # Layer 3: 对话历史与推理
        layer3_memory=layer3,
        
        # 向后兼容
        history_archive=create_empty_history_archive(),
        
        # Crush 聊天记录
        crush_chat_storage=None,
        
        # 任务管理 - 保持空以便兼容，实际存储在 layer3_memory 中
        task_registry=create_empty_task_registry(),
        report_counter=create_empty_report_counter(),
        
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
        _handoff_target=None,
        _handoff_instruction=None,
        _pending_action=None,
        collected_info={},
        instruction=None,  # Main Agent 给专家的 Brief（v3.0）
        onboarding_completed=False,  # 默认未完成，正常进入 Onboarding
        onboarding_turn_count=0,
        onboarding_max_turns=3,
        onboarding_handoff=None,
        last_onboarding_question=None,
        question_count=0,
        max_questions=3,

        # 提问节流（默认：同一 agent 连续提问最多 3 轮）
        question_streak_agent=None,
        question_streak_count=0,
        max_question_streak=3,
        
        # 提问模式（渐进式披露）
        ask_mode=False,
        ask_mode_tool_message_id=None,
        
        # 解答模式（渐进式披露）
        consult_mode=False,
        consult_mode_tool_message_id=None,
        
        # 情感陪伴模式（渐进式披露）
        emotion_mode=False,
        emotion_mode_tool_message_id=None,
        
        # 循环控制
        _iteration_count=0,
        
        # 子 Agent 完成信号
        completion_status=None,
        result_summary=None,
        
        # 对话连贯性
        last_response_for_continuity=None,
        debug_log=[],

        # === 维护任务（异步提纯/归档队列）===
        maintenance_queue=[],
        maintenance_flags={},
        maintenance_last_finalized_at=None,
    )

    # 允许测试或调用方注入额外字段（如 status_report 等）
    for key, value in overrides.items():
        state[key] = value

    return state


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
            "crush_name": "",
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


def migrate_to_layered_memory(state: AgentState) -> AgentState:
    """
    将旧版状态迁移到新的分层长期记忆架构
    
    Args:
        state: 旧版状态
    
    Returns:
        迁移后的新版状态
    """
    # 如果已经有新版字段，直接返回
    if state.get("layer1_memory") and state.get("layer2_memory") and state.get("layer3_memory"):
        return state
    
    # 迁移 Layer 1
    layer1 = create_empty_layer1_memory()
    if state.get("user_context"):
        layer1["full_data"] = state["user_context"]
    
    # 迁移 Layer 2
    layer2 = create_empty_layer2_memory()
    if state.get("status_report"):
        from graph.context_types import create_status_report_item
        report_item = create_status_report_item(
            report_content=state["status_report"].get("report_content", ""),
            report_id=state.get("report_counter", {}).get("status_report", 1),
            stage=state["status_report"].get("stage", ""),
            stage_description=state["status_report"].get("stage_description", ""),
            acr_analysis=state["status_report"].get("acr_analysis", {}),
            key_issues=state["status_report"].get("key_issues", []),
            risk_points=state["status_report"].get("risk_points", []),
        )
        layer2["current_status_report"] = report_item
    
    if state.get("action_guides"):
        layer2["action_guides"] = state["action_guides"]
    
    # 迁移 Layer 3
    layer3 = create_empty_layer3_memory()
    if state.get("messages"):
        layer3["all_messages"] = list(state["messages"])
        
    # 迁移 TaskRegistry 到 Layer 3
    if state.get("task_registry"):
        layer3["task_registry"] = state.get("task_registry")
    
    # 迁移旧的 history_archive 到各层
    if state.get("history_archive"):
        archive = state["history_archive"]
        
        # 迁移对话归档到 Layer 3
        if archive.get("conversation_archive"):
            for conv in archive["conversation_archive"]:
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
    
    # 更新状态
    state["layer1_memory"] = layer1
    state["layer2_memory"] = layer2
    state["layer3_memory"] = layer3
    
    return state


# ============================================================
# 辅助函数
# ============================================================

def get_active_action_guides(action_guides: list[ActionGuideItem]) -> list[ActionGuideItem]:
    """
    获取所有活跃的（未完成的）行动指南
    
    @deprecated: 请使用 context_types.get_active_action_guides(layer2_memory) 替代
    """
    return [
        guide for guide in action_guides
        if guide.get("status") in ("pending", "in_progress", "paused")
    ]


def get_completed_action_guides(action_guides: list[ActionGuideItem]) -> list[ActionGuideItem]:
    """
    获取所有已完成的行动指南
    
    @deprecated: 请使用 context_types.get_completed_action_guides(layer2_memory) 替代
    """
    return [
        guide for guide in action_guides
        if guide.get("status") in ("completed", "cancelled", "expired")
    ]


def sync_layer1_to_user_context(state: AgentState) -> AgentState:
    """
    同步 Layer 1 长期记忆到 user_context 字段（向后兼容）
    
    在更新 layer1_memory 后调用此函数，确保旧代码仍能正常工作
    """
    if state.get("layer1_memory"):
        state["user_context"] = state["layer1_memory"].get("full_data", create_empty_user_context())
    return state


def sync_messages_to_layer3(state: AgentState) -> AgentState:
    """
    同步 messages 到 Layer 3 长期记忆
    
    在消息更新后调用此函数，保持 layer3_memory 与 messages 同步
    """
    if state.get("layer3_memory") and state.get("messages"):
        state["layer3_memory"]["all_messages"] = list(state["messages"])
    return state


# ============================================================
# 消息同步与序列化辅助
# ============================================================

def get_message_id(message) -> str:
    """获取消息 ID（兼容 LangChain Message 和 dict），缺失则返回空字符串"""
    if hasattr(message, "id") and getattr(message, "id"):
        return str(getattr(message, "id"))
    if isinstance(message, dict):
        return str(message.get("id", "") or "")
    return ""


def ensure_message_id(message) -> tuple[str, dict]:
    """
    确保消息有 ID，返回 (id, dict格式)
    - 如果没有 ID，则生成 UUID
    - 转换为可序列化的 dict
    """
    msg_dict = convert_message_to_dict(message)
    msg_id = msg_dict.get("id")
    if not msg_id:
        msg_id = str(uuid.uuid4())
        msg_dict["id"] = msg_id
    return msg_id, msg_dict


def message_key(message) -> str:
    """
    用于去重的消息键：
    - 优先使用 id
    - 没有 id 时使用 role+content 组合
    """
    msg_dict = convert_message_to_dict(message)
    if msg_dict.get("id"):
        return str(msg_dict["id"])
    role = msg_dict.get("role", "")
    content = msg_dict.get("content", "")
    return f"{role}:{content}"


def convert_message_to_dict(message) -> dict:
    """将消息转换为 dict，兼容 LangChain Message / dict"""
    if isinstance(message, dict):
        return dict(message)
    return {
        "id": getattr(message, "id", None),
        "role": getattr(message, "type", None) or getattr(message, "role", None),
        "content": getattr(message, "content", None),
        "additional_kwargs": getattr(message, "additional_kwargs", {}),
        "tool_call_id": getattr(message, "tool_call_id", None),
        "name": getattr(message, "name", None),
        "tool_calls": getattr(message, "tool_calls", None),
    }


def sync_new_messages_to_fullstore(state: AgentState, merged_messages: Optional[list] = None) -> dict:
    """
    将工作区 messages 中新增的消息同步到 layer3_memory.all_messages（全量存储）
    - 只追加，不删除
    - 通过 message_key 去重，保证不会重复写入
    """
    messages = merged_messages if merged_messages is not None else state.get("messages", [])
    if not messages:
        return {}

    layer3_memory = state.get("layer3_memory") or create_empty_layer3_memory()
    all_messages = layer3_memory.get("all_messages", [])

    existing_keys = {message_key(m) for m in all_messages}

    new_serialized = []
    for m in messages:
        key = message_key(m)
        if key in existing_keys:
            continue
        _, msg_dict = ensure_message_id(m)
        existing_keys.add(key)
        new_serialized.append(msg_dict)

    if not new_serialized:
        return {}

    layer3_memory["all_messages"] = all_messages + new_serialized
    layer3_memory["last_updated"] = datetime.now().isoformat()

    return {"layer3_memory": layer3_memory}
