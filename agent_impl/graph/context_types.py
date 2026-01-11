"""
上下文类型定义
定义分层长期记忆架构和相关数据结构

基于 context_strategy.md v3.0 策略文档

架构说明：
- 每层都有独立的长期记忆（Memory）和提取策略（ExtractionConfig）
- Layer 1: 静态情报（3×3 矩阵）
- Layer 2: 工作上下文（报告/规划/指南）
- Layer 3: 对话历史

并发处理：
- 每层有 processing_status 字段标记是否正在处理中
- 处理中时使用降级策略（原始数据）
- 处理完成后合并结果
"""

from typing import TypedDict, Literal, Optional
import os
from datetime import datetime


# ============================================================
# 处理状态（并发控制）
# ============================================================

class ProcessingStatus(TypedDict, total=False):
    """
    长期记忆处理状态
    
    用于处理并发场景：当 LLM 正在处理（如生成摘要）时，
    如果用户发来新消息，需要知道当前状态以决定降级策略
    """
    is_processing: bool           # 是否正在处理中
    processing_type: Literal[     # 处理类型
        "compression",            # 压缩/生成摘要
        "extraction",             # 提取高价值信息
        "archiving",              # 归档
    ]
    started_at: str               # 处理开始时间
    snapshot_version: int         # 处理前的数据版本号
    # 处理前的数据快照（用于降级）
    fallback_data: Optional[dict]


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


class Layer1ExtractionConfig(TypedDict, total=False):
    """
    Layer 1 提取策略配置
    
    mode:
    - "full": 完整保留，不做任何压缩（默认）
    - "compressed": 压缩模式，对冗长内容做轻量摘要
    """
    mode: Literal["full", "compressed"]  # 提取模式
    max_tokens: int                       # 压缩模式下的 token 上限


class Layer1Memory(TypedDict, total=False):
    """
    Layer 1 长期记忆：静态情报全量存储
    
    包含：
    - full_data: 3×3 情报矩阵全量数据
    - extraction_config: 提取策略配置
    - processing_status: 处理状态（并发控制）
    - 元数据
    """
    # 全量数据
    full_data: UserContext  # 3×3 情报矩阵
    
    # 提取配置
    extraction_config: Layer1ExtractionConfig
    
    # 处理状态（并发控制）
    processing_status: Optional[ProcessingStatus]
    
    # 元数据
    last_updated: str       # 最后更新时间 ISO 格式
    update_count: int       # 累计更新次数
    version: int            # 数据版本号（每次更新递增）


# ============================================================
# Layer 2: 工作上下文 - 报告/规划/指南
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
    
    状态机（6 种状态）：
    - pending: 待开始（已生成但尚未执行）
    - in_progress: 进行中（用户正在执行）
    - completed: 已完成（终态）
    - cancelled: 已取消（终态）
    - paused: 暂停（可恢复）
    - expired: 过期（终态）
    """
    id: str                         # 唯一标识
    guide_id: int                   # 指南编号（用于显示【指南N】）
    # 说明：为向后兼容，这里仍然允许缺省；新生成的指南应当始终写入 title/one_liner/status
    title: Optional[str]            # 标题（用于元数据列表展示）
    one_liner: Optional[str]        # 一句话摘要（20-30字，用于元数据列表）
    status: Literal[
        "pending",
        "in_progress",
        "completed",
        "cancelled",
        "paused",
        "expired",
    ]
    guide: ActionGuideContent       # 指南内容
    created_at: str                 # 创建时间 ISO 格式
    completed_at: Optional[str]     # 完成时间（completed/cancelled/expired 状态时填充）
    # 摘要字段（终态 completed/cancelled/expired 时建议填充；其中 one_liner 用于元数据列表）
    summary: Optional[str]          # 中等摘要（100-200字）


class StatusReportItem(TypedDict, total=False):
    """
    现状分析报告项
    
    支持历史版本存储和摘要分级
    """
    id: str                         # 唯一标识
    report_id: int                  # 报告编号（用于显示【报告N】）
    is_current: bool                # 是否为当前版本
    # 报告内容
    stage: str                      # L1-L4 或 T1-T3
    stage_description: str          # 阶段描述
    acr_analysis: dict              # A/C/R 三维分析
    key_issues: list[str]           # 核心问题
    risk_points: list[str]          # 风险点
    report_content: str             # Markdown 格式的完整报告
    # 元数据
    created_at: str                 # 创建时间
    # 摘要字段（非当前版本时填充）
    summary: Optional[str]          # 中等摘要（100-200字）
    one_liner: Optional[str]        # 一句话摘要（20-30字）


class ActionPlanItem(TypedDict, total=False):
    """
    行动规划项
    
    支持历史版本存储和摘要分级
    """
    id: str                         # 唯一标识
    plan_id: int                    # 规划编号（用于显示【规划N】）
    is_current: bool                # 是否为当前版本
    # 规划内容
    goal: str                       # 阶段性目标
    strategy: str                   # 核心策略方向
    phases: list[dict]              # 分阶段计划
    key_principles: list[str]       # 关键原则
    plan_content: str               # Markdown 格式的完整规划
    # 元数据
    created_at: str                 # 创建时间
    # 摘要字段（非当前版本时填充）
    summary: Optional[str]          # 中等摘要（100-200字）
    one_liner: Optional[str]        # 一句话摘要（20-30字）


class DynamicIntelItem(TypedDict, total=False):
    """
    动态情报项（短期时效信息）

    分类：
    - schedule: 日程/时间点
    - mood: 心情/情绪
    - status: 状态/生理/工作负荷
    - intent: 意图/需求
    """
    id: str                                        # 唯一标识
    content: str                                   # 情报内容
    category: Literal["schedule", "mood", "status", "intent"]
    subject: Literal["user", "crush"]              # 情报主体
    valid_from: str                                # 生效时间 (ISO 8601)
    expire_at: Optional[str]                       # 过期时间 (ISO 8601)
    source_msg_id: Optional[str]                   # 来源消息 ID（用于溯源）
    confidence: float                              # 置信度 (0.0-1.0)


class Layer2ExtractionConfig(TypedDict, total=False):
    """
    Layer 2 提取策略配置
    
    控制如何从长期记忆中提取工作上下文
    """
    recent_summary_count: int      # 最近 N 份保留中等摘要（默认 2）
    max_one_liner_count: int       # 最多保留 N 条一句话摘要（默认 10）
    include_active_guides: bool    # 是否包含所有未执行指南（默认 True）


class Layer2Memory(TypedDict, total=False):
    """
    Layer 2 长期记忆：工作上下文全量存储
    
    包含：
    - all_status_reports: 所有现状分析报告（含历史）
    - all_action_plans: 所有行动规划（含历史）
    - all_action_guides: 所有行动指南（含历史）
    - dynamic_intels: 动态情报板（时效信息）
    - extraction_config: 提取策略配置
    - processing_status: 处理状态（并发控制）
    """
    # 全量数据
    all_status_reports: list[StatusReportItem]   # 所有现状分析报告
    all_action_plans: list[ActionPlanItem]       # 所有行动规划
    all_action_guides: list[ActionGuideItem]     # 所有行动指南
    dynamic_intels: list[DynamicIntelItem]       # 动态情报板（时效信息）
    
    # 提取配置
    extraction_config: Layer2ExtractionConfig
    
    # 处理状态（并发控制）
    processing_status: Optional[ProcessingStatus]
    
    # 元数据
    last_updated: str               # 最后更新时间
    version: int                    # 数据版本号


# ============================================================
# 任务级思考过程管理 (Rolling Scratchpad)
# ============================================================

# 每个任务最多绑定的行动指南数量
# - 默认 K=3（产品验收标准）
# - 测试/调试可通过环境变量临时覆盖，例如：BOUND_GUIDES_PER_TASK_K=1
MAX_BOUND_GUIDES_PER_TASK = int(os.getenv("BOUND_GUIDES_PER_TASK_K", "3"))


class BoundActionGuide(TypedDict, total=False):
    """
    绑定到任务的行动指南详情快照
    
    用于跨轮次持久注入行动指南完整内容
    """
    guide_id: str           # ActionGuideItem.id（短 uuid）
    title: str              # 标题（便于阅读）
    status: str             # pending/in_progress/... 绑定时的状态
    content_md: str         # 完整 Markdown 内容快照
    bound_at: str           # 绑定时间 ISO 格式
    source: str             # 固定 "bind_action_guide_detail"


class TaskState(TypedDict, total=False):
    """
    单个 Agent 的任务状态
    
    用于实现 Rolling Scratchpad 模式：
    - 同一任务内：思考过程全量保留
    - 任务切换时：旧任务的思考过程归档（不删除），新任务开始新的思考
    - 回到旧任务时：可以恢复该任务的思考过程
    
    任务状态机：
    - pending: 创建但尚未激活
    - active: 当前活跃任务
    - completed: 已完成
    """
    task_id: str           # 任务标识（子Agent: task_001, 主Agent: 语义化如"判断crush是否喜欢用户"）
    summary: str           # 任务摘要（20-30字，用于任务列表展示）
    status: Literal["pending", "active", "completed"]  # 任务状态
    reasoning: list[str]   # 思考过程记录（当前任务的内心戏，Active Task Payload）
    started_at: str        # 任务开始时间 ISO 格式
    completed_at: Optional[str]  # 完成时间（completed 状态时填充）
    is_active: bool        # 是否为当前活跃任务（保留向后兼容）
    bound_action_guides: list[BoundActionGuide]  # 绑定的行动指南详情快照


class AgentTaskRegistry(TypedDict, total=False):
    """
    各 Agent 的任务注册表
    
    结构说明：
    - 每个 Agent 可以有多个历史任务（归档的）
    - 但只有一个当前活跃任务（is_active=True）
    - 子 Agent 任务 ID 格式：task_001, task_002, ...
    - 主 Agent 任务 ID 格式：语义化命名如"判断crush是否喜欢用户"
    """
    main_agent: list[TaskState]      # 主 Agent 的任务列表
    status_agent: list[TaskState]    # 现状分析 Agent 的任务列表
    plan_agent: list[TaskState]      # 行动规划 Agent 的任务列表
    guide_agent: list[TaskState]     # 行动指南 Agent 的任务列表


# ============================================================
# Layer 3: 对话历史
# ============================================================

class ConversationSummary(TypedDict, total=False):
    """
    对话摘要
    
    当对话超出保留轮次时，压缩为摘要存储
    """
    id: str                 # 唯一标识
    summary: str            # 压缩摘要
    start_time: str         # 对话开始时间
    end_time: str           # 对话结束时间
    turn_count: int         # 对话轮次
    key_topics: list[str]   # 关键话题
    extracted_info: dict    # 提取的高价值信息（写入 Layer 1）


class Layer3ExtractionConfig(TypedDict, total=False):
    """
    Layer 3 提取策略配置
    
    控制如何从长期记忆中提取对话历史
    """
    max_recent_turns: int          # 完整保留的最近轮次（默认 25）
    include_summaries: bool        # 是否包含历史摘要（默认 True）
    max_summary_count: int         # 最多包含的摘要条数（默认 5）
    reasoning_limit: int           # 任务思考过程记录保留条数（默认 10）


class Layer3Memory(TypedDict, total=False):
    """
    Layer 3 长期记忆：对话历史全量存储
    
    包含：
    - all_messages: 完整对话记录
    - conversation_summaries: 压缩后的对话摘要
    - task_registry: 任务级思考过程（Rolling Scratchpad）
    - extraction_config: 提取策略配置
    - processing_status: 处理状态（并发控制）
    """
    # 全量数据
    all_messages: list[dict]                          # 完整对话记录
    conversation_summaries: list[ConversationSummary] # 对话摘要
    task_registry: AgentTaskRegistry                  # 任务级思考过程
    
    # 提取配置
    extraction_config: Layer3ExtractionConfig
    
    # 处理状态（并发控制）
    processing_status: Optional[ProcessingStatus]
    
    # 元数据
    last_updated: str               # 最后更新时间
    total_turns: int                # 累计对话轮次
    version: int                    # 数据版本号


class ReportCounter(TypedDict, total=False):
    """
    报告编号计数器
    
    用于追踪各类报告的产出编号，在 Layer 3 中记录"报告N已生成"
    """
    status_report: int    # 现状分析报告编号
    action_plan: int      # 行动规划编号
    action_guide: int     # 行动指南编号


# ============================================================
# Crush 聊天记录分层存储
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
# 向后兼容：保留旧的 HistoryArchive 类型（已废弃）
# ============================================================

class HistorySummary(TypedDict, total=False):
    """
    历史摘要项
    
    @deprecated: 请使用各层独立的摘要字段替代
    """
    id: str                 # 唯一标识
    summary: str            # 中等长度摘要（100-200字）
    one_liner: str          # 一句话摘要（20-30字）
    created_at: str         # 创建时间
    full_content: str       # 完整内容（抽屉式存储，按需调用）


class ConversationArchive(TypedDict, total=False):
    """
    对话归档项
    
    @deprecated: 请使用 ConversationSummary 替代
    """
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
    
    @deprecated: 请使用 Layer1Memory, Layer2Memory, Layer3Memory 替代
    保留此类型仅为向后兼容
    """
    status_history: list[HistorySummary]        # 历史现状分析
    plan_history: list[HistorySummary]          # 历史行动规划
    guide_history: list[HistorySummary]         # 历史行动指南（已完成的）
    conversation_archive: list[ConversationArchive]  # 对话归档


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


def create_empty_layer1_memory() -> Layer1Memory:
    """创建空的 Layer 1 长期记忆"""
    return Layer1Memory(
        full_data=create_empty_user_context(),
        extraction_config=Layer1ExtractionConfig(
            mode="full",
            max_tokens=15000,
        ),
        processing_status=None,
        last_updated=datetime.now().isoformat(),
        update_count=0,
        version=1,
    )


def create_empty_layer2_memory() -> Layer2Memory:
    """创建空的 Layer 2 长期记忆"""
    return Layer2Memory(
        all_status_reports=[],
        all_action_plans=[],
        all_action_guides=[],
        dynamic_intels=[],
        extraction_config=Layer2ExtractionConfig(
            recent_summary_count=2,
            max_one_liner_count=10,
            include_active_guides=True,
        ),
        processing_status=None,
        last_updated=datetime.now().isoformat(),
        version=1,
    )


def create_empty_task_registry() -> AgentTaskRegistry:
    """创建空的任务注册表"""
    return AgentTaskRegistry(
        main_agent=[],
        status_agent=[],
        plan_agent=[],
        guide_agent=[],
    )


def create_empty_layer3_memory() -> Layer3Memory:
    """创建空的 Layer 3 长期记忆"""
    return Layer3Memory(
        all_messages=[],
        conversation_summaries=[],
        task_registry=create_empty_task_registry(),
        extraction_config=Layer3ExtractionConfig(
            max_recent_turns=25,
            include_summaries=True,
            max_summary_count=5,
            reasoning_limit=10,
        ),
        processing_status=None,
        last_updated=datetime.now().isoformat(),
        total_turns=0,
        version=1,
    )


def create_empty_history_archive() -> HistoryArchive:
    """
    创建空的历史存档
    
    @deprecated: 请使用 create_empty_layer2_memory() 和 create_empty_layer3_memory() 替代
    """
    return HistoryArchive(
        status_history=[],
        plan_history=[],
        guide_history=[],
        conversation_archive=[],
    )


def create_action_guide_item(
    guide: ActionGuideContent,
    guide_id: int = 0,
    status: Literal[
        "pending",
        "in_progress",
        "completed",
        "cancelled",
        "paused",
        "expired",
    ] = "pending",
    title: str = "",
    one_liner: Optional[str] = None,
) -> ActionGuideItem:
    """创建行动指南项"""
    import uuid
    safe_title = title or guide.get("current_task") or (f"指南{guide_id}" if guide_id else "未命名指南")
    return ActionGuideItem(
        id=str(uuid.uuid4())[:8],
        guide_id=guide_id,
        status=status,
        title=safe_title,
        guide=guide,
        created_at=datetime.now().isoformat(),
        completed_at=None,
        summary=None,
        one_liner=one_liner,
    )


def create_status_report_item(
    report_content: str,
    report_id: int = 0,
    stage: str = "",
    stage_description: str = "",
    acr_analysis: dict = None,
    key_issues: list[str] = None,
    risk_points: list[str] = None,
    is_current: bool = True,
) -> StatusReportItem:
    """创建现状分析报告项"""
    import uuid
    return StatusReportItem(
        id=str(uuid.uuid4())[:8],
        report_id=report_id,
        is_current=is_current,
        stage=stage,
        stage_description=stage_description,
        acr_analysis=acr_analysis or {},
        key_issues=key_issues or [],
        risk_points=risk_points or [],
        report_content=report_content,
        created_at=datetime.now().isoformat(),
        summary=None,
        one_liner=None,
    )


def create_action_plan_item(
    plan_content: str,
    plan_id: int = 0,
    goal: str = "",
    strategy: str = "",
    phases: list[dict] = None,
    key_principles: list[str] = None,
    is_current: bool = True,
) -> ActionPlanItem:
    """创建行动规划项"""
    import uuid
    return ActionPlanItem(
        id=str(uuid.uuid4())[:8],
        plan_id=plan_id,
        is_current=is_current,
        goal=goal,
        strategy=strategy,
        phases=phases or [],
        key_principles=key_principles or [],
        plan_content=plan_content,
        created_at=datetime.now().isoformat(),
        summary=None,
        one_liner=None,
    )


def create_conversation_summary(
    summary: str,
    turn_count: int,
    key_topics: list[str] = None,
    extracted_info: dict = None,
) -> ConversationSummary:
    """创建对话摘要"""
    import uuid
    return ConversationSummary(
        id=str(uuid.uuid4())[:8],
        summary=summary,
        start_time=datetime.now().isoformat(),
        end_time=datetime.now().isoformat(),
        turn_count=turn_count,
        key_topics=key_topics or [],
        extracted_info=extracted_info or {},
    )


def create_empty_report_counter() -> ReportCounter:
    """创建空的报告计数器"""
    return ReportCounter(
        status_report=0,
        action_plan=0,
        action_guide=0,
    )


def create_dynamic_intel_item(
    content: str,
    category: Literal["schedule", "mood", "status", "intent"],
    *,
    subject: Literal["user", "crush"] = "user",
    valid_from: Optional[str] = None,
    expire_at: Optional[str] = None,
    source_msg_id: Optional[str] = None,
    confidence: float = 0.8,
) -> DynamicIntelItem:
    """创建动态情报项"""
    import uuid
    return DynamicIntelItem(
        id=str(uuid.uuid4())[:8],
        content=content,
        category=category,
        subject=subject,
        valid_from=valid_from or datetime.now().isoformat(),
        expire_at=expire_at,
        source_msg_id=source_msg_id,
        confidence=confidence,
    )


def _parse_iso(dt_str: Optional[str]):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def get_valid_dynamic_intels(
    layer2_memory: Layer2Memory,
    *,
    now: Optional[datetime] = None,
) -> list[DynamicIntelItem]:
    """获取未过期的动态情报"""
    now = now or datetime.now()
    intels = layer2_memory.get("dynamic_intels", [])
    valid_intels = []
    for intel in intels:
        expire_at = _parse_iso(intel.get("expire_at"))
        if expire_at and expire_at < now:
            continue
        valid_intels.append(intel)
    return valid_intels


def filter_expired_intels(
    intels: list[DynamicIntelItem],
    *,
    now: Optional[datetime] = None,
) -> list[DynamicIntelItem]:
    """过滤已过期的动态情报"""
    now = now or datetime.now()
    filtered = []
    for intel in intels:
        expire_at = _parse_iso(intel.get("expire_at"))
        if expire_at and expire_at < now:
            continue
        filtered.append(intel)
    return filtered


def create_new_task(task_id: str, summary: str = "") -> TaskState:
    """
    创建新任务
    
    Args:
        task_id: 任务唯一标识（语义化命名）
        summary: 任务摘要（20-30字，用于任务列表展示）
    
    Returns:
        新创建的 TaskState，状态为 active
    """
    return TaskState(
        task_id=task_id,
        summary=summary or f"任务: {task_id[:20]}",  # 默认摘要
        status="active",
        reasoning=[],
        started_at=datetime.now().isoformat(),
        completed_at=None,
        is_active=True,
        bound_action_guides=[],  # 初始化绑定的行动指南为空列表
    )


def get_active_task(task_list: list[TaskState]) -> Optional[TaskState]:
    """获取当前活跃任务"""
    for task in task_list:
        if task.get("is_active", False):
            return task
    return None


def get_task_by_id(task_list: list[TaskState], task_id: str) -> Optional[TaskState]:
    """根据 ID 获取任务"""
    for task in task_list:
        if task.get("task_id") == task_id:
            return task
    return None


# ============================================================
# Layer 2 辅助函数
# ============================================================

def get_current_status_report(memory: Layer2Memory) -> Optional[StatusReportItem]:
    """获取当前版本的现状分析报告"""
    for report in memory.get("all_status_reports", []):
        if report.get("is_current"):
            return report
    return None


def get_current_action_plan(memory: Layer2Memory) -> Optional[ActionPlanItem]:
    """获取当前版本的行动规划"""
    for plan in memory.get("all_action_plans", []):
        if plan.get("is_current"):
            return plan
    return None


def get_active_action_guides(memory: Layer2Memory) -> list[ActionGuideItem]:
    """获取所有“非终态”的行动指南（待开始/进行中/暂停）"""
    return [
        guide for guide in memory.get("all_action_guides", [])
        if guide.get("status") in ("pending", "in_progress", "paused")
    ]


def get_completed_action_guides(memory: Layer2Memory) -> list[ActionGuideItem]:
    """获取所有终态（已归档）的行动指南：completed/cancelled/expired"""
    return [
        guide for guide in memory.get("all_action_guides", [])
        if guide.get("status") in ("completed", "cancelled", "expired")
    ]


def is_valid_action_guide_status_transition(current: str | None, target: str) -> bool:
    """
    校验行动指南状态流转是否合法。

    规则来自「行动指南状态机制重构」方案：
    - pending -> in_progress/cancelled/expired
    - in_progress -> completed/paused/cancelled
    - paused -> in_progress/cancelled
    - completed/cancelled/expired 为终态，不可再变
    """
    cur = (current or "pending").strip()
    tgt = (target or "").strip()
    if not tgt:
        return False
    if cur == tgt:
        return True

    valid_transitions: dict[str, set[str]] = {
        "pending": {"in_progress", "cancelled", "expired"},
        "in_progress": {"completed", "paused", "cancelled"},
        "paused": {"in_progress", "cancelled"},
        "completed": set(),
        "cancelled": set(),
        "expired": set(),
    }
    return tgt in valid_transitions.get(cur, set())


def get_history_status_reports(memory: Layer2Memory) -> list[StatusReportItem]:
    """获取历史版本的现状分析报告（非当前版本）"""
    return [
        report for report in memory.get("all_status_reports", [])
        if not report.get("is_current")
    ]


def get_history_action_plans(memory: Layer2Memory) -> list[ActionPlanItem]:
    """获取历史版本的行动规划（非当前版本）"""
    return [
        plan for plan in memory.get("all_action_plans", [])
        if not plan.get("is_current")
    ]


# ============================================================
# 处理状态管理函数（并发控制）
# ============================================================

def create_processing_status(
    processing_type: Literal["compression", "extraction", "archiving"],
    current_version: int,
    fallback_data: Optional[dict] = None,
) -> ProcessingStatus:
    """
    创建处理状态
    
    Args:
        processing_type: 处理类型
        current_version: 当前数据版本号
        fallback_data: 降级时使用的数据快照
    """
    return ProcessingStatus(
        is_processing=True,
        processing_type=processing_type,
        started_at=datetime.now().isoformat(),
        snapshot_version=current_version,
        fallback_data=fallback_data,
    )


def is_layer_processing(memory: dict) -> bool:
    """
    检查某层是否正在处理中
    
    Args:
        memory: Layer1Memory / Layer2Memory / Layer3Memory
    
    Returns:
        是否正在处理中
    """
    status = memory.get("processing_status")
    if not status:
        return False
    return status.get("is_processing", False)


def get_layer_fallback_data(memory: dict) -> Optional[dict]:
    """
    获取某层的降级数据
    
    当该层正在处理中时，返回处理前的数据快照
    
    Args:
        memory: Layer1Memory / Layer2Memory / Layer3Memory
    
    Returns:
        降级数据，如果不在处理中则返回 None
    """
    status = memory.get("processing_status")
    if not status or not status.get("is_processing"):
        return None
    return status.get("fallback_data")


def start_layer_processing(
    memory: dict,
    processing_type: Literal["compression", "extraction", "archiving"],
    fallback_data: Optional[dict] = None,
) -> dict:
    """
    开始某层的处理，设置处理状态
    
    Args:
        memory: Layer1Memory / Layer2Memory / Layer3Memory
        processing_type: 处理类型
        fallback_data: 降级时使用的数据快照
    
    Returns:
        更新后的 memory
    """
    current_version = memory.get("version", 1)
    memory["processing_status"] = create_processing_status(
        processing_type=processing_type,
        current_version=current_version,
        fallback_data=fallback_data,
    )
    return memory


def finish_layer_processing(memory: dict, increment_version: bool = True) -> dict:
    """
    完成某层的处理，清除处理状态
    
    Args:
        memory: Layer1Memory / Layer2Memory / Layer3Memory
        increment_version: 是否递增版本号
    
    Returns:
        更新后的 memory
    """
    memory["processing_status"] = None
    if increment_version:
        memory["version"] = memory.get("version", 1) + 1
    memory["last_updated"] = datetime.now().isoformat()
    return memory


def check_processing_timeout(memory: dict, timeout_seconds: int = 60) -> bool:
    """
    检查处理是否超时
    
    如果处理时间超过阈值，认为处理失败，应该清除状态
    
    Args:
        memory: Layer1Memory / Layer2Memory / Layer3Memory
        timeout_seconds: 超时时间（秒）
    
    Returns:
        是否超时
    """
    status = memory.get("processing_status")
    if not status or not status.get("is_processing"):
        return False
    
    started_at = status.get("started_at")
    if not started_at:
        return True  # 没有开始时间，认为异常
    
    try:
        start_time = datetime.fromisoformat(started_at)
        elapsed = (datetime.now() - start_time).total_seconds()
        return elapsed > timeout_seconds
    except (ValueError, TypeError):
        return True  # 解析失败，认为异常


def clear_stale_processing(memory: dict, timeout_seconds: int = 60) -> dict:
    """
    清除过期的处理状态
    
    如果处理超时，自动清除状态，恢复到可用状态
    
    Args:
        memory: Layer1Memory / Layer2Memory / Layer3Memory
        timeout_seconds: 超时时间（秒）
    
    Returns:
        更新后的 memory
    """
    if check_processing_timeout(memory, timeout_seconds):
        print(f"[Warning] Processing timeout detected, clearing stale status")
        memory["processing_status"] = None
    return memory