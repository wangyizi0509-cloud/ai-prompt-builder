"""
AgentState 状态定义
定义 LangGraph 工作流中传递的状态结构

更新记录：
- v2.0: 重构为分层上下文架构，引入 3×3 静态情报矩阵
- v2.1: 使用 LangGraph 官方的 add_messages reducer，添加循环计数器
- v3.0: 分层长期记忆架构，删除统一 Layer 4，改为各层独立长期记忆
- v3.1: 将模型推理 (Rolling Scratchpad) 移入 Layer 3，增加滚动摘要
"""

from typing import Literal, Optional, Annotated, Any
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
    ReportCounter,
    TaskState,
    # 工厂函数
    create_empty_layer1_memory,
    create_empty_layer2_memory,
    create_empty_layer3_memory,
    create_empty_report_counter,
)


class Message(TypedDict):
    """单条消息"""
    role: Literal["user", "assistant", "system"]
    content: str
    id: Optional[str]


class FeedbackMode(TypedDict, total=False):
    """行动反馈模式（用于 guide_agent 接管反馈流程）"""
    guide_id: str
    phase: Literal["initial", "followup"]
    prefilled_status: Optional[str]
    prefilled_detail: Optional[str]
    start_message_id: Optional[str]


class FeedbackCompression(TypedDict, total=False):
    """反馈消息压缩策略（历史注入时隐藏反馈对话，仅保留总结）"""
    guide_id: str
    start_message_id: str
    keep_tag: str  # 识别“反馈完成总结”消息的标记


# ============================================================
# 保留原有类型（向后兼容）
# ============================================================

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
    
    # === Layer 2: 工作上下文（分层长期记忆）===
    layer2_memory: Layer2Memory  # Layer 2 长期记忆（全量 + 提取配置）
    
    # === Layer 3: 对话历史与推理（分层长期记忆）===
    layer3_memory: Layer3Memory  # Layer 3 长期记忆（全量 + 提取配置）
    # messages 字段仍然保留，用于 LangGraph 的消息流
    # 但实际的长期存储和提取逻辑由 layer3_memory 管理
    messages: Annotated[list, add_messages]
    
    # === Crush 聊天记录存储 ===
    crush_chat_storage: Optional[CrushChatStorage]
    
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
    inquiry_card: Optional[dict]
    inquiry_answers: Optional[Any]
    # Onboarding: 局势初判卡（前端可直接渲染）
    preliminary_assessment: Optional[dict]
    
    # === 子 Agent 完成信号 ===
    completion_status: Optional[str]
    result_summary: Optional[str]
    
    # === 对话连贯性 ===
    last_response_for_continuity: Optional[str]

    # === 行动反馈模式 ===
    feedback_mode: Optional[FeedbackMode]
    feedback_mode_input: Optional[dict]  # 前端请求携带的反馈标记（临时）
    feedback_prefill: Optional[dict]     # 触发反馈弹窗的预填信息（临时）
    feedback_status: Optional[Literal["asking", "completed"]]
    feedback_question: Optional[str]
    feedback_compressions: list[FeedbackCompression]
    
    # === 路由控制 ===
    should_continue: bool
    route_to: str
    
    runtime: dict
    tool_patch_log: list[dict]
    collected_info: dict
    # Onboarding 状态
    onboarding_completed: bool
    pending_crushe_guide: bool
    onboarding_turn_count: int
    onboarding_last_answer_fingerprint: Optional[str]
    onboarding_max_turns: int
    onboarding_handoff: Optional[dict]
    last_onboarding_question: Optional[str]
    _onboarding_interrupted: bool
    _onboarding_interrupt_payload: dict
    # === 循环控制 ===
    _iteration_count: int

    # === 调试日志 ===
    debug_log: Annotated[list[dict], add]

    # === 维护任务队列（异步提纯/归档）===
    # 这些字段必须在 TypedDict 中声明，否则 LangGraph 不会持久化！
    maintenance_queue: list[dict]           # 维护任务队列
    maintenance_flags: dict                 # 维护状态标记（如 onboarding_refine_done）
    maintenance_last_finalized_at: Optional[str]  # 最后一次 finalize 的时间戳


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
        
        # Layer 2: 工作上下文
        layer2_memory=layer2,
        preliminary_assessment=None,
        
        # Layer 3: 对话历史与推理
        layer3_memory=layer3,
        
        # Crush 聊天记录
        crush_chat_storage=None,
        
        report_counter=create_empty_report_counter(),
        
        # 流程控制
        intent_type="action_trigger",
        next_action="end_turn",
        pending_responses=[],
        runtime={},
        tool_patch_log=[],
        collected_info={},
        should_continue=True,
        route_to="main_agent",
        onboarding_completed=False,  # 默认未完成，正常进入 Onboarding
        pending_crushe_guide=False,
        onboarding_turn_count=0,
        onboarding_last_answer_fingerprint=None,
        onboarding_max_turns=3,
        onboarding_handoff=None,
        last_onboarding_question=None,
        
        # 循环控制
        _iteration_count=0,
        
        # 子 Agent 完成信号
        completion_status=None,
        result_summary=None,
        
        # 对话连贯性
        last_response_for_continuity=None,
        
        # 行动反馈模式
        feedback_mode=None,
        feedback_mode_input=None,
        feedback_prefill=None,
        feedback_status=None,
        feedback_question=None,
        feedback_compressions=[],
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
    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    response_metadata = getattr(message, "response_metadata", {}) or {}
    reasoning_content = getattr(message, "reasoning_content", None)
    if reasoning_content is None:
        reasoning_content = additional_kwargs.get("reasoning_content")
    if reasoning_content is None:
        reasoning_content = response_metadata.get("reasoning_content")
    return {
        "id": getattr(message, "id", None),
        "role": getattr(message, "type", None) or getattr(message, "role", None),
        "content": getattr(message, "content", None),
        "additional_kwargs": additional_kwargs,
        "response_metadata": response_metadata,
        "reasoning_content": reasoning_content,
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
