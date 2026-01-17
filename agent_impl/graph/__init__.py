"""
Graph 模块 - LangGraph 工作流定义

v3.1 更新：
- 统一上下文系统规范
- 删除旧版类型（HistoryArchive, ConversationArchive, HistorySummary）
- 使用 AtomicMemory 原子记忆结构
- 使用 current_xxx + xxx_history 替代 is_current 字段
- 任务系统使用 status 替代 is_active
"""

from .state import (
    AgentState,
    create_initial_state,
    migrate_user_profile_to_context,
    migrate_to_layered_memory,
    get_active_action_guides,
    get_completed_action_guides,
    sync_layer1_to_user_context,
    sync_messages_to_layer3,
)
from .context_types import (
    # Layer 1 - 静态情报（原子记忆结构）
    AtomicMemory,
    UserContext,
    InfoSource,
    CrushInfo,
    Layer1Memory,
    Layer1ExtractionConfig,
    # Layer 2 - 工作上下文
    ActionGuideItem,
    ActionGuideContent,
    StatusReportItem,
    ActionPlanItem,
    DynamicIntelItem,
    Layer2Memory,
    Layer2ExtractionConfig,
    # Layer 3 - 对话历史
    Layer3Memory,
    Layer3ExtractionConfig,
    ConversationSummary,
    # 任务系统
    AgentTaskRegistry,
    TaskState,
    BoundContext,
    ReasoningNote,
    BOUND_CONTEXT_LIMITS,
    # 处理状态（并发控制）
    ProcessingStatus,
    create_processing_status,
    is_layer_processing,
    get_layer_fallback_data,
    start_layer_processing,
    finish_layer_processing,
    check_processing_timeout,
    clear_stale_processing,
    # Crush 聊天记录
    CrushChatMetadata,
    CrushChatSummary,
    CrushChatStorage,
    # 计数器
    ReportCounter,
    # 工厂函数
    create_empty_user_context,
    create_empty_layer1_memory,
    create_empty_layer2_memory,
    create_empty_layer3_memory,
    create_empty_task_registry,
    create_action_guide_item,
    create_status_report_item,
    create_action_plan_item,
    create_conversation_summary,
    create_empty_report_counter,
    create_dynamic_intel_item,
    create_atomic_memory,
    create_bound_context,
    create_reasoning_note,
    create_new_task,
    # Layer 2 辅助函数
    get_active_action_guides as get_layer2_active_guides,
    get_completed_action_guides as get_layer2_completed_guides,
    get_valid_dynamic_intels,
    is_valid_action_guide_status_transition,
    # 任务辅助函数
    get_active_task,
    get_task_by_id,
)
from .context_builder import (
    build_context,
    build_context_dict,
    extract_layer1,
    extract_layer2,
    extract_layer3,
    estimate_tokens,
    estimate_state_tokens,
    should_compress_layer3,
    check_and_compress_if_needed,
    get_context_stats,
    TOKEN_BUDGET,
    LAYER1_DEFAULT_CONFIG,
    LAYER2_DEFAULT_CONFIG,
    LAYER3_DEFAULT_CONFIG,
)
from .archive_manager import (
    # 新版 API
    check_layer3_compression_needed,
    compress_layer3,
    archive_guide_to_layer2,
    archive_status_to_layer2,
    # 向后兼容
    check_conversation_compression_needed,
    compress_conversation,
    archive_guide_on_completion,
    archive_status_on_replacement,
    process_archiving_if_needed,
    get_archive_stats,
    get_full_history_content,
    LAYER2_ARCHIVE_CONFIG,
    LAYER3_ARCHIVE_CONFIG,
)
from .state_storage import (
    save_state,
    load_state,
    delete_state,
    list_users,
    get_user_info,
    get_or_create_state,
    AutoSaveState,
    get_layer_memory,
    update_layer_memory,
    get_extraction_config,
    update_extraction_config,
    save_image,
    list_user_images,
    DATA_DIR,
)
from .crush_chat_storage import (
    CrushChatManager,
    CrushMessage,
    create_crush_chat_manager,
    CRUSH_CHAT_CONFIG,
)
from .workflow import create_workflow

__all__ = [
    # State
    "AgentState",
    "create_initial_state",
    "migrate_user_profile_to_context",
    "migrate_to_layered_memory",
    "get_active_action_guides",
    "get_completed_action_guides",
    "sync_layer1_to_user_context",
    "sync_messages_to_layer3",
    # Context Types - Layer 1
    "AtomicMemory",
    "UserContext",
    "InfoSource",
    "CrushInfo",
    "Layer1Memory",
    "Layer1ExtractionConfig",
    # Context Types - Layer 2
    "ActionGuideItem",
    "ActionGuideContent",
    "StatusReportItem",
    "ActionPlanItem",
    "DynamicIntelItem",
    "Layer2Memory",
    "Layer2ExtractionConfig",
    # Context Types - Layer 3
    "Layer3Memory",
    "Layer3ExtractionConfig",
    "ConversationSummary",
    # Context Types - 任务系统
    "AgentTaskRegistry",
    "TaskState",
    "BoundContext",
    "ReasoningNote",
    "BOUND_CONTEXT_LIMITS",
    # Context Types - 处理状态（并发控制）
    "ProcessingStatus",
    "create_processing_status",
    "is_layer_processing",
    "get_layer_fallback_data",
    "start_layer_processing",
    "finish_layer_processing",
    "check_processing_timeout",
    "clear_stale_processing",
    # Context Types - Crush 聊天记录
    "CrushChatMetadata",
    "CrushChatSummary",
    "CrushChatStorage",
    # Context Types - 计数器
    "ReportCounter",
    # Context Types - 工厂函数
    "create_empty_user_context",
    "create_empty_layer1_memory",
    "create_empty_layer2_memory",
    "create_empty_layer3_memory",
    "create_empty_task_registry",
    "create_action_guide_item",
    "create_status_report_item",
    "create_action_plan_item",
    "create_conversation_summary",
    "create_empty_report_counter",
    "create_dynamic_intel_item",
    "create_atomic_memory",
    "create_bound_context",
    "create_reasoning_note",
    "create_new_task",
    # Context Types - Layer 2 辅助函数
    "get_layer2_active_guides",
    "get_layer2_completed_guides",
    "get_valid_dynamic_intels",
    "is_valid_action_guide_status_transition",
    # Context Types - 任务辅助函数
    "get_active_task",
    "get_task_by_id",
    # Context Builder
    "build_context",
    "build_context_dict",
    "extract_layer1",
    "extract_layer2",
    "extract_layer3",
    "estimate_tokens",
    "estimate_state_tokens",
    "should_compress_layer3",
    "check_and_compress_if_needed",
    "get_context_stats",
    "TOKEN_BUDGET",
    "LAYER1_DEFAULT_CONFIG",
    "LAYER2_DEFAULT_CONFIG",
    "LAYER3_DEFAULT_CONFIG",
    # Archive Manager - 新版 API
    "check_layer3_compression_needed",
    "compress_layer3",
    "archive_guide_to_layer2",
    "archive_status_to_layer2",
    # Archive Manager - 向后兼容
    "check_conversation_compression_needed",
    "compress_conversation",
    "archive_guide_on_completion",
    "archive_status_on_replacement",
    "process_archiving_if_needed",
    "get_archive_stats",
    "get_full_history_content",
    "LAYER2_ARCHIVE_CONFIG",
    "LAYER3_ARCHIVE_CONFIG",
    # State Storage
    "save_state",
    "load_state",
    "delete_state",
    "list_users",
    "get_user_info",
    "get_or_create_state",
    "AutoSaveState",
    "get_layer_memory",
    "update_layer_memory",
    "get_extraction_config",
    "update_extraction_config",
    "save_image",
    "list_user_images",
    "DATA_DIR",
    # Crush Chat Storage
    "CrushChatManager",
    "CrushMessage",
    "create_crush_chat_manager",
    "CRUSH_CHAT_CONFIG",
    # Workflow
    "create_workflow",
]
