"""
Graph 模块 - LangGraph 工作流定义

v2.0 更新：
- 新增分层上下文架构（context_types, context_builder）
- AgentState 支持 3×3 静态情报矩阵

v2.1 更新：
- 新增整理 Agent（organize_agent）
- 新增归档管理器（archive_manager）
- 对话压缩和历史摘要分级存储

v2.2 更新：
- 新增本地持久化存储（state_storage）
- 新增 Crush 聊天记录分层存储（crush_chat_storage）
- 新增抽屉式完整信息调用工具（tools/drawer_tools）

v3.0 更新：
- 分层长期记忆架构：删除统一 Layer 4，改为各层独立长期记忆
- Layer 1/2/3 各自有独立的长期记忆存储和提取策略
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
    # Layer 1
    UserContext,
    InfoSource,
    CrushInfo,
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
    # 处理状态（并发控制）
    ProcessingStatus,
    create_processing_status,
    is_layer_processing,
    get_layer_fallback_data,
    start_layer_processing,
    finish_layer_processing,
    check_processing_timeout,
    clear_stale_processing,
    # 其他
    CrushChatMetadata,
    CrushChatSummary,
    CrushChatStorage,
    AgentTaskRegistry,
    TaskState,
    ReportCounter,
    # 向后兼容
    HistoryArchive,
    ConversationArchive,
    HistorySummary,
    # 工厂函数
    create_empty_user_context,
    create_empty_layer1_memory,
    create_empty_layer2_memory,
    create_empty_layer3_memory,
    create_empty_history_archive,
    create_action_guide_item,
    create_status_report_item,
    create_action_plan_item,
    create_conversation_summary,
    create_empty_task_registry,
    create_empty_report_counter,
    # Layer 2 辅助函数
    get_current_status_report,
    get_current_action_plan,
    get_active_action_guides as get_layer2_active_guides,
    get_completed_action_guides as get_layer2_completed_guides,
    get_history_status_reports,
    get_history_action_plans,
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
    "Layer2Memory",
    "Layer2ExtractionConfig",
    # Context Types - Layer 3
    "Layer3Memory",
    "Layer3ExtractionConfig",
    "ConversationSummary",
    # Context Types - 处理状态（并发控制）
    "ProcessingStatus",
    "create_processing_status",
    "is_layer_processing",
    "get_layer_fallback_data",
    "start_layer_processing",
    "finish_layer_processing",
    "check_processing_timeout",
    "clear_stale_processing",
    # Context Types - 其他
    "CrushChatMetadata",
    "CrushChatSummary",
    "CrushChatStorage",
    "AgentTaskRegistry",
    "TaskState",
    "ReportCounter",
    # Context Types - 向后兼容
    "HistoryArchive",
    "ConversationArchive",
    "HistorySummary",
    # Context Types - 工厂函数
    "create_empty_user_context",
    "create_empty_layer1_memory",
    "create_empty_layer2_memory",
    "create_empty_layer3_memory",
    "create_empty_history_archive",
    "create_action_guide_item",
    "create_status_report_item",
    "create_action_plan_item",
    "create_conversation_summary",
    "create_empty_task_registry",
    "create_empty_report_counter",
    # Context Types - Layer 2 辅助函数
    "get_current_status_report",
    "get_current_action_plan",
    "get_layer2_active_guides",
    "get_layer2_completed_guides",
    "get_history_status_reports",
    "get_history_action_plans",
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
