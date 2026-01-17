"""
上下文类型定义
定义分层长期记忆架构和相关数据结构

基于最新规范文档：
- Layer_Specs/layer1_spec_v1.0.md
- Layer_Specs/layer2_spec_v1.0.md
- Layer_Specs/layer3_spec_v1.0.md
- Task_System/task_system_spec.md
- Context_Assembly/context_assembly_spec.md

架构说明：
- 每层都有独立的长期记忆（Memory）和提取策略（ExtractionConfig）
- Layer 1: 静态情报（3×3 矩阵，原子记忆结构）
- Layer 2: 工作上下文（报告/规划/指南/动态情报）
- Layer 3: 对话历史（摘要/任务笔记/最近对话）
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
    fallback_data: Optional[dict] # 处理前的数据快照（用于降级）


# ============================================================
# Layer 1: 静态情报 - 3×3 矩阵（原子记忆结构）
# ============================================================

class AtomicMemory(TypedDict, total=False):
    """
    原子记忆（最小语义单元）
    
    每条信息独立存储，不做字符串拼接。
    """
    id: str                       # 唯一标识 (uuid[:8])
    content: str                  # 内容（最小语义单元）
    created_at: str               # ISO 格式时间（精确到小时）: "2026-01-13T14"
    source_type: Literal[         # 来源类型
        "onboarding",             # Onboarding 阶段收集
        "conversation",           # 日常对话中提取
        "report",                 # 报告生成时提取
    ]
    confidence: float             # 置信度 (0.0-1.0)，AI分析必填
    confidence_reason: str        # 置信度原因，AI分析必填


class InfoSource(TypedDict, total=False):
    """
    信息来源三元组（原子记忆列表）
    
    信任优先级（冲突时的判断依据）：
    1. 最高可信 - fact: 客观事实（聊天记录、截图等直接证据）
    2. 中等可信 - ai_provide: AI分析（基于证据的推断）
    3. 最低可信 - user_provide: 用户口述（可能美化或误读）
    """
    user_provide: list[AtomicMemory]  # 用户提供的原子记忆列表
    fact: list[AtomicMemory]          # 客观事实列表
    ai_provide: list[AtomicMemory]    # AI分析列表


class CrushInfo(TypedDict, total=False):
    """
    Crush 信息（含名称，原子记忆列表）
    """
    crush_name: str                   # Crush 名称或昵称
    user_provide: list[AtomicMemory]  # 用户提供的原子记忆列表
    fact: list[AtomicMemory]          # 客观事实列表
    ai_provide: list[AtomicMemory]    # AI分析列表


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
    - "compressed": 压缩模式，按相关性筛选 Top-K
    """
    mode: Literal["full", "compressed"]  # 提取模式
    max_tokens: int                       # 压缩模式下的 token 上限


class Layer1Memory(TypedDict, total=False):
    """
    Layer 1 长期记忆：静态情报全量存储（原子记忆）
    
    包含：
    - full_data: 3×3 情报矩阵全量数据（原子记忆列表）
    - extraction_config: 提取策略配置
    - processing_status: 处理状态（并发控制）
    - 元数据
    """
    full_data: UserContext              # 3×3 情报矩阵
    extraction_config: Layer1ExtractionConfig
    processing_status: Optional[ProcessingStatus]
    last_updated: str                   # 最后更新时间 ISO 格式
    update_count: int                   # 累计更新次数
    version: int                        # 数据版本号（每次更新递增）


# ============================================================
# Layer 2: 工作上下文 - 报告/规划/指南/动态情报
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
    行动指南项
    
    状态机（6 种状态）：
    - in_progress: 进行中（默认状态）
    - pending: 搁置中，等待执行
    - paused: 用户主动暂停
    - completed: 已完成（终态）
    - cancelled: 已取消（终态）
    - expired: 已过期（终态）
    """
    id: str                              # 唯一标识 (uuid[:8])
    guide_id: int                        # 指南编号（用于显示【指南N】）
    title: str                           # 标题
    status: Literal[
        "pending",
        "in_progress",
        "paused",
        "completed",
        "cancelled",
        "expired",
    ]
    guide: ActionGuideContent            # 指南内容
    created_at: str                      # 创建时间 ISO 格式
    
    # 时间管理
    expected_start_at: Optional[str]     # 预计开始时间（Agent 生成）
    expire_at: Optional[str]             # 过期时间（Agent 生成）
    completed_at: Optional[str]          # 完成时间（用户操作时记录）
    
    # 用户反馈（completed 时记录）
    user_feedback: Optional[str]         # 用户的完成反馈
    
    # 摘要字段（Organize Agent 生成）
    summary: Optional[str]               # 中等摘要（100-200字）
    one_liner: Optional[str]             # 一句话摘要（20-30字）


class StatusReportItem(TypedDict, total=False):
    """
    现状分析报告项
    """
    id: str                              # 报告 ID (uuid[:8])
    report_id: int                       # 报告编号（用于显示【报告N】）
    report_content: str                  # 报告正文（Markdown）
    created_at: str                      # 创建时间 ISO 格式
    version: int                         # 版本号（修改时+1）
    
    # 报告内容（结构化字段，可选）
    stage: str                           # L1-L4 或 T1-T3
    stage_description: str               # 阶段描述
    acr_analysis: dict                   # A/C/R 三维分析
    key_issues: list[str]                # 核心问题
    risk_points: list[str]               # 风险点
    
    # 归档字段（由 Organize Agent 生成）
    summary: Optional[str]               # 中等摘要（~100-200 字）
    one_liner: Optional[str]             # 一句话摘要（~30 字）
    archived_at: Optional[str]           # 归档时间


class ActionPlanItem(TypedDict, total=False):
    """
    行动规划项
    """
    id: str                              # 规划 ID (uuid[:8])
    plan_id: int                         # 规划编号（用于显示【规划N】）
    plan_content: str                    # 规划正文（Markdown）
    created_at: str                      # 创建时间 ISO 格式
    version: int                         # 版本号（修改时+1）
    
    # 规划内容（结构化字段，可选）
    goal: str                            # 阶段性目标
    strategy: str                        # 核心策略方向
    phases: list[dict]                   # 分阶段计划
    key_principles: list[str]            # 关键原则
    
    # 归档字段（由 Organize Agent 生成）
    summary: Optional[str]               # 中等摘要
    one_liner: Optional[str]             # 一句话摘要
    archived_at: Optional[str]           # 归档时间


class DynamicIntelItem(TypedDict, total=False):
    """
    动态情报项（短期时效信息）
    
    category 为自由文本，LLM 自定义（如：日程、情绪、意向、状态等）
    """
    id: str                              # 唯一标识 (uuid[:8])
    content: str                         # 情报内容
    created_at: str                      # 创建时间 ISO 格式
    expire_at: str                       # 过期时间 ISO 格式
    subject: Literal["user", "crush"]    # 归属
    category: str                        # 类型（不限制，LLM 自定义）
    confidence: float                    # 置信度 (0.0-1.0)
    confidence_reason: str               # 置信度原因（必填）
    source_type: Literal["conversation"] # 来源类型


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
    - dynamic_intels: 动态情报板（时效信息）
    - current_status_report: 当前现状报告
    - status_report_history: 历史现状报告
    - current_action_plan: 当前行动规划
    - action_plan_history: 历史行动规划
    - action_guides: 所有行动指南（全量保留）
    """
    # 动态情报板
    dynamic_intels: list[DynamicIntelItem]
    
    # 现状报告
    current_status_report: Optional[StatusReportItem]
    status_report_history: list[StatusReportItem]
    
    # 行动规划
    current_action_plan: Optional[ActionPlanItem]
    action_plan_history: list[ActionPlanItem]
    
    # 行动指南（全量保留）
    action_guides: list[ActionGuideItem]
    
    # 提取配置
    extraction_config: Layer2ExtractionConfig
    
    # 处理状态（并发控制）
    processing_status: Optional[ProcessingStatus]
    
    # 元数据
    last_updated: str
    version: int


# ============================================================
# Layer 3: 对话历史
# ============================================================

class ConversationSummary(TypedDict, total=False):
    """
    对话摘要
    
    当对话轮次超过 25 轮触发压缩时，旧对话被压缩成摘要存储。
    """
    id: str                 # 唯一标识 (uuid[:8])
    summary: str            # 摘要内容
    topics: str             # 关键话题（逗号分隔，自由文本）
    created_at: str         # ISO 格式时间
    turn_range: str         # 覆盖的轮次范围: "1-25"


class HistorySummary(TypedDict, total=False):
    """
    历史摘要（用于行动指南/现状报告/规划归档）
    
    当行动指南完成、报告/规划被替换时，生成摘要用于归档。
    """
    id: str                 # 唯一标识 (uuid[:8])
    summary: str            # 中等摘要（100-200字）
    one_liner: str          # 一句话摘要（20-30字）
    created_at: str         # ISO 格式时间
    full_content: str       # 原始完整内容


class ConversationArchive(TypedDict, total=False):
    """
    对话归档摘要
    
    对话批量压缩时生成的归档记录。
    """
    id: str                 # 唯一标识 (uuid[:8])
    summary: str            # 对话摘要（50-100字）
    start_time: str         # 对话开始时间 ISO 格式
    end_time: str           # 对话结束时间 ISO 格式
    turn_count: int         # 对话轮次数
    key_topics: list[str]   # 关键话题列表
    extracted_info: dict    # 提取的高价值信息


class HistoryArchive(TypedDict, total=False):
    """
    历史归档容器（向后兼容）
    
    用于存储各类历史归档的集合。
    """
    guide_history: list[HistorySummary]           # 行动指南归档
    status_history: list[HistorySummary]          # 现状报告归档
    plan_history: list[HistorySummary]            # 行动规划归档
    conversation_archives: list[ConversationArchive]  # 对话归档


class Layer3ExtractionConfig(TypedDict, total=False):
    """
    Layer 3 提取策略配置
    
    控制如何从长期记忆中提取对话历史
    """
    max_recent_turns: int          # 完整保留的最近轮次（默认 25）
    include_summaries: bool        # 是否包含历史摘要（默认 True）
    max_summary_count: int         # 最多包含的摘要条数（默认 5）
    reasoning_limit: int           # 任务思考过程记录保留条数（默认 8）


# ============================================================
# 任务系统（Task System）
# ============================================================

# 通用 BoundContext 各类型上限
BOUND_CONTEXT_LIMITS = {
    "action_guide": 3,
    "status_report": 1,
    "action_plan": 1,
    "crush_chat": 3,
    "history_snippet": 3,
    "dynamic_intel": 5,
    "custom": 3,
    "default": 3,
}

# 每个任务最多绑定的行动指南数量
MAX_BOUND_GUIDES_PER_TASK = 3


class BoundActionGuide(TypedDict, total=False):
    """
    绑定的行动指南（专用类型）
    
    用于在任务中绑定行动指南的详细内容。
    """
    guide_id: str           # 引用的指南 ID
    title: str              # 指南标题
    status: str             # 指南状态
    content_md: str         # Markdown 格式内容
    bound_at: str           # 绑定时间 ISO 格式
    source: str             # 来源标识


class BoundContext(TypedDict, total=False):
    """
    通用绑定上下文
    
    支持任意类型的上下文绑定，通过 type 区分。
    """
    id: str                       # 绑定记录的唯一 ID (uuid[:8])
    type: str                     # 上下文类型（字符串，可扩展）
    ref_id: Optional[str]         # 引用的资源 ID（用于去重，可选）
    title: str                    # 标题（20-30字，用于列表展示）
    content_md: str               # Markdown 格式内容（注入 Prompt 用）
    source: str                   # 来源标识（格式：{方式}:{具体来源}）
    bound_at: str                 # 绑定时间 ISO 格式
    expire_at: Optional[str]      # 可选过期时间（到期不注入，但保留）


class ReasoningNote(TypedDict, total=False):
    """
    任务推理笔记（结构化）
    
    存储推理结论而非过程，最多保留 8 条。
    """
    id: str                       # 唯一标识 (uuid[:8])
    content: str                  # 笔记内容（结论导向）
    created_at: str               # ISO 格式时间
    task_id: str                  # 所属任务 ID


class TaskState(TypedDict, total=False):
    """
    单个任务状态
    
    任务是额外上下文的生命周期边界：
    - 任务进行中 → 检索的上下文持续注入
    - 任务切换 → 上下文卸载（不注入，但后台保留）
    - 任务回来 → 上下文恢复注入
    
    任务状态机：
    - pending: 创建但未激活（被其他任务切走时）
    - active: 当前活跃（同一时刻只有一个）
    - completed: 已完成
    """
    task_id: str                  # 任务唯一标识（短 UUID，如 "a1b2c3d4"）
    title: str                    # 语义化标题（如 "判断Crush是否喜欢用户"）
    summary: str                  # 摘要（20-30字，用于列表展示）
    status: Literal["pending", "active", "completed"]  # 任务状态
    
    # 内容
    reasoning_notes: list[ReasoningNote]  # 推理笔记（最多 8 条）
    bound_contexts: list[BoundContext]    # 绑定的上下文
    
    # 时间
    started_at: str               # 开始时间 ISO 格式
    completed_at: Optional[str]   # 完成时间（completed 状态时填充）
    
    # 归档
    completion_summary: Optional[str]  # 任务完成时的结论摘要（50-100字）


class AgentTaskRegistry(TypedDict, total=False):
    """
    各 Agent 的任务注册表
    
    各 Agent 独立维护任务列表，互不干扰。
    """
    main_agent: list[TaskState]      # 主 Agent 的任务列表
    status_agent: list[TaskState]    # 现状分析 Agent 的任务列表
    plan_agent: list[TaskState]      # 行动规划 Agent 的任务列表
    guide_agent: list[TaskState]     # 行动指南 Agent 的任务列表


class Layer3Memory(TypedDict, total=False):
    """
    Layer 3 长期记忆：对话历史全量存储
    
    包含：
    - all_messages: 完整对话记录
    - conversation_summaries: 压缩后的对话摘要（最多 5 条）
    - task_registry: 任务级思考过程
    """
    all_messages: list[dict]                          # 完整对话记录
    conversation_summaries: list[ConversationSummary] # 对话摘要
    task_registry: AgentTaskRegistry                  # 任务注册表
    
    extraction_config: Layer3ExtractionConfig
    processing_status: Optional[ProcessingStatus]
    
    last_updated: str
    total_turns: int
    version: int


class ReportCounter(TypedDict, total=False):
    """
    报告编号计数器
    """
    status_report: int    # 现状分析报告编号
    action_plan: int      # 行动规划编号
    action_guide: int     # 行动指南编号


# ============================================================
# Crush 聊天记录分层存储
# ============================================================

class CrushChatMetadata(TypedDict, total=False):
    """Crush 聊天记录元数据 (L1)"""
    total_messages: int         # 总消息数
    chat_frequency: str         # 聊天频率描述
    time_span: str              # 时间跨度
    last_chat_time: str         # 最后聊天时间


class CrushChatSummary(TypedDict, total=False):
    """Crush 聊天记录结构化摘要 (L2)"""
    key_events: list[str]       # 关键事件
    emotional_turns: list[str]  # 情感转折点
    main_topics: list[str]      # 主要话题


class CrushChatStorage(TypedDict, total=False):
    """Crush 聊天记录完整存储结构"""
    metadata: CrushChatMetadata  # L1: 元数据
    summary: CrushChatSummary    # L2: 结构化摘要


# ============================================================
# 工具函数
# ============================================================

def create_empty_user_context() -> UserContext:
    """创建空的用户上下文（原子记忆结构）"""
    return UserContext(
        user_info=InfoSource(
            user_provide=[],
            fact=[],
            ai_provide=[],
        ),
        crush_info=CrushInfo(
            crush_name="",
            user_provide=[],
            fact=[],
            ai_provide=[],
        ),
        both_info=InfoSource(
            user_provide=[],
            fact=[],
            ai_provide=[],
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
        dynamic_intels=[],
        current_status_report=None,
        status_report_history=[],
        current_action_plan=None,
        action_plan_history=[],
        action_guides=[],
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
            reasoning_limit=8,
        ),
        processing_status=None,
        last_updated=datetime.now().isoformat(),
        total_turns=0,
        version=1,
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
    ] = "in_progress",  # 默认状态改为 in_progress
    title: str = "",
    one_liner: Optional[str] = None,
) -> ActionGuideItem:
    """创建行动指南项"""
    import uuid
    safe_title = title or guide.get("current_task") or (f"指南{guide_id}" if guide_id else "未命名指南")
    return ActionGuideItem(
        id=str(uuid.uuid4())[:8],
        guide_id=guide_id,
        title=safe_title,
        status=status,
        guide=guide,
        created_at=datetime.now().isoformat(),
        expected_start_at=None,
        expire_at=None,
        completed_at=None,
        user_feedback=None,
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
) -> StatusReportItem:
    """创建现状分析报告项"""
    import uuid
    return StatusReportItem(
        id=str(uuid.uuid4())[:8],
        report_id=report_id,
        report_content=report_content,
        created_at=datetime.now().isoformat(),
        version=1,
        stage=stage,
        stage_description=stage_description,
        acr_analysis=acr_analysis or {},
        key_issues=key_issues or [],
        risk_points=risk_points or [],
        summary=None,
        one_liner=None,
        archived_at=None,
    )


def create_action_plan_item(
    plan_content: str,
    plan_id: int = 0,
    goal: str = "",
    strategy: str = "",
    phases: list[dict] = None,
    key_principles: list[str] = None,
) -> ActionPlanItem:
    """创建行动规划项"""
    import uuid
    return ActionPlanItem(
        id=str(uuid.uuid4())[:8],
        plan_id=plan_id,
        plan_content=plan_content,
        created_at=datetime.now().isoformat(),
        version=1,
        goal=goal,
        strategy=strategy,
        phases=phases or [],
        key_principles=key_principles or [],
        summary=None,
        one_liner=None,
        archived_at=None,
    )


def create_conversation_summary(
    summary: str,
    topics: str = "",
    turn_range: str = "",
) -> ConversationSummary:
    """创建对话摘要"""
    import uuid
    return ConversationSummary(
        id=str(uuid.uuid4())[:8],
        summary=summary,
        topics=topics,
        created_at=datetime.now().isoformat(),
        turn_range=turn_range,
    )


def create_empty_report_counter() -> ReportCounter:
    """创建空的报告计数器"""
    return ReportCounter(
        status_report=0,
        action_plan=0,
        action_guide=0,
    )


def create_empty_history_archive() -> HistoryArchive:
    """创建空的历史归档容器"""
    return HistoryArchive(
        guide_history=[],
        status_history=[],
        plan_history=[],
        conversation_archives=[],
    )


def create_dynamic_intel_item(
    content: str,
    category: str,
    *,
    subject: Literal["user", "crush"] = "user",
    valid_from: Optional[str] = None,
    expire_at: Optional[str] = None,
    confidence: float = 0.8,
    confidence_reason: str = "",
) -> DynamicIntelItem:
    """创建动态情报项"""
    import uuid
    return DynamicIntelItem(
        id=str(uuid.uuid4())[:8],
        content=content,
        created_at=valid_from or datetime.now().isoformat(),
        expire_at=expire_at or "",
        subject=subject,
        category=category,
        confidence=confidence,
        confidence_reason=confidence_reason or "默认置信度",
        source_type="conversation",
    )


def create_atomic_memory(
    content: str,
    source_type: Literal["onboarding", "conversation", "report"],
    *,
    created_at: Optional[str] = None,
    confidence: Optional[float] = None,
    confidence_reason: Optional[str] = None,
) -> AtomicMemory:
    """创建原子记忆"""
    import uuid
    created_at = created_at or datetime.now().strftime("%Y-%m-%dT%H")
    data: AtomicMemory = {
        "id": str(uuid.uuid4())[:8],
        "content": content,
        "created_at": created_at,
        "source_type": source_type,
    }
    if confidence is not None:
        data["confidence"] = confidence
    if confidence_reason:
        data["confidence_reason"] = confidence_reason
    return data


def create_bound_context(
    context_type: str,
    title: str,
    content_md: str,
    *,
    ref_id: Optional[str] = None,
    expire_at: Optional[str] = None,
    source: str = "tool:bind_context",
    bound_at: Optional[str] = None,
) -> BoundContext:
    """创建通用绑定上下文"""
    import uuid
    return BoundContext(
        id=str(uuid.uuid4())[:8],
        type=context_type,
        ref_id=ref_id,
        title=title,
        content_md=content_md,
        source=source,
        bound_at=bound_at or datetime.now().isoformat(),
        expire_at=expire_at,
    )


def create_reasoning_note(content: str, task_id: str) -> ReasoningNote:
    """创建结构化任务笔记"""
    import uuid
    return ReasoningNote(
        id=str(uuid.uuid4())[:8],
        content=content,
        created_at=datetime.now().isoformat(),
        task_id=task_id,
    )


def create_new_task(task_id: str, title: str = "", summary: str = "") -> TaskState:
    """
    创建新任务
    
    Args:
        task_id: 任务唯一标识
        title: 语义化标题
        summary: 任务摘要（20-30字）
    
    Returns:
        新创建的 TaskState，状态为 active
    """
    return TaskState(
        task_id=task_id,
        title=title or task_id,
        summary=summary or f"任务: {task_id[:20]}",
        status="active",
        reasoning_notes=[],
        bound_contexts=[],
        started_at=datetime.now().isoformat(),
        completed_at=None,
        completion_summary=None,
    )


# ============================================================
# 辅助查询函数
# ============================================================

def _parse_iso(dt_str: Optional[str]):
    """解析 ISO 格式时间"""
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
) -> tuple[list[DynamicIntelItem], list[DynamicIntelItem]]:
    """
    过滤过期的动态情报
    
    Returns:
        (valid_intels, expired_intels) - 未过期和已过期的情报列表
    """
    now = now or datetime.now()
    valid_intels = []
    expired_intels = []
    for intel in intels or []:
        expire_at = _parse_iso(intel.get("expire_at"))
        if expire_at and expire_at < now:
            expired_intels.append(intel)
        else:
            valid_intels.append(intel)
    return valid_intels, expired_intels


def get_active_task(task_list: list[TaskState]) -> Optional[TaskState]:
    """获取当前活跃任务（status == 'active'）"""
    for task in task_list:
        if task.get("status") == "active":
            return task
    return None


def get_task_by_id(task_list: list[TaskState], task_id: str) -> Optional[TaskState]:
    """根据 ID 获取任务"""
    for task in task_list:
        if task.get("task_id") == task_id:
            return task
    return None


def get_current_status_report(memory: Layer2Memory) -> Optional[StatusReportItem]:
    """获取当前现状报告"""
    return memory.get("current_status_report")


def get_current_action_plan(memory: Layer2Memory) -> Optional[ActionPlanItem]:
    """获取当前行动规划"""
    return memory.get("current_action_plan")


def get_active_action_guides(memory: Layer2Memory) -> list[ActionGuideItem]:
    """获取所有"非终态"的行动指南（in_progress/pending/paused）"""
    return [
        guide for guide in memory.get("action_guides", [])
        if guide.get("status") in ("pending", "in_progress", "paused")
    ]


def get_completed_action_guides(memory: Layer2Memory) -> list[ActionGuideItem]:
    """获取所有终态的行动指南（completed/cancelled/expired）"""
    return [
        guide for guide in memory.get("action_guides", [])
        if guide.get("status") in ("completed", "cancelled", "expired")
    ]


def is_valid_action_guide_status_transition(current: str | None, target: str) -> bool:
    """
    校验行动指南状态流转是否合法
    """
    cur = (current or "in_progress").strip()
    tgt = (target or "").strip()
    if not tgt:
        return False
    if cur == tgt:
        return True

    valid_transitions: dict[str, set[str]] = {
        "pending": {"in_progress", "cancelled", "expired"},
        "in_progress": {"completed", "paused", "cancelled", "pending"},
        "paused": {"in_progress", "cancelled"},
        "completed": set(),
        "cancelled": set(),
        "expired": set(),
    }
    return tgt in valid_transitions.get(cur, set())


# ============================================================
# 处理状态管理函数（并发控制）
# ============================================================

def create_processing_status(
    processing_type: Literal["compression", "extraction", "archiving"],
    current_version: int,
    fallback_data: Optional[dict] = None,
) -> ProcessingStatus:
    """创建处理状态"""
    return ProcessingStatus(
        is_processing=True,
        processing_type=processing_type,
        started_at=datetime.now().isoformat(),
        snapshot_version=current_version,
        fallback_data=fallback_data,
    )


def is_layer_processing(memory: dict) -> bool:
    """检查某层是否正在处理中"""
    status = memory.get("processing_status")
    if not status:
        return False
    return status.get("is_processing", False)


def get_layer_fallback_data(memory: dict) -> Optional[dict]:
    """获取某层的降级数据"""
    status = memory.get("processing_status")
    if not status or not status.get("is_processing"):
        return None
    return status.get("fallback_data")


def start_layer_processing(
    memory: dict,
    processing_type: Literal["compression", "extraction", "archiving"],
    fallback_data: Optional[dict] = None,
) -> dict:
    """开始某层的处理，设置处理状态"""
    current_version = memory.get("version", 1)
    memory["processing_status"] = create_processing_status(
        processing_type=processing_type,
        current_version=current_version,
        fallback_data=fallback_data,
    )
    return memory


def finish_layer_processing(memory: dict, increment_version: bool = True) -> dict:
    """完成某层的处理，清除处理状态"""
    memory["processing_status"] = None
    if increment_version:
        memory["version"] = memory.get("version", 1) + 1
    memory["last_updated"] = datetime.now().isoformat()
    return memory


def check_processing_timeout(memory: dict, timeout_seconds: int = 60) -> bool:
    """检查处理是否超时"""
    status = memory.get("processing_status")
    if not status or not status.get("is_processing"):
        return False
    
    started_at = status.get("started_at")
    if not started_at:
        return True
    
    try:
        start_time = datetime.fromisoformat(started_at)
        elapsed = (datetime.now() - start_time).total_seconds()
        return elapsed > timeout_seconds
    except (ValueError, TypeError):
        return True


def clear_stale_processing(memory: dict, timeout_seconds: int = 60) -> dict:
    """清除过期的处理状态"""
    if check_processing_timeout(memory, timeout_seconds):
        print(f"[Warning] Processing timeout detected, clearing stale status")
        memory["processing_status"] = None
    return memory
