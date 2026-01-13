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
"""

from .state import (
    AgentState,
    create_initial_state,
    migrate_user_profile_to_context,
    get_active_action_guides,
    get_completed_action_guides,
)
from .context_types import (
    UserContext,
    InfoSource,
    CrushInfo,
    ActionGuideItem,
    ActionGuideContent,
    HistoryArchive,
    ConversationArchive,
    HistorySummary,
    CrushChatMetadata,
    CrushChatSummary,
    CrushChatStorage,
    create_empty_user_context,
    create_empty_history_archive,
    create_action_guide_item,
)
from .context_builder import (
    build_context,
    build_context_dict,
    estimate_tokens,
    should_compress,
    check_and_compress_if_needed,
    get_context_stats,
    TOKEN_BUDGET,
)
from .archive_manager import (
    check_conversation_compression_needed,
    compress_conversation,
    archive_guide_on_completion,
    archive_status_on_replacement,
    process_archiving_if_needed,
    get_archive_stats,
    get_full_history_content,
    ARCHIVE_CONFIG,
)
from .state_storage import (
    save_state,
    load_state,
    delete_state,
    list_users,
    get_user_info,
    get_or_create_state,
    AutoSaveState,
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
    "get_active_action_guides",
    "get_completed_action_guides",
    # Context Types
    "UserContext",
    "InfoSource",
    "CrushInfo",
    "ActionGuideItem",
    "ActionGuideContent",
    "HistoryArchive",
    "ConversationArchive",
    "HistorySummary",
    "CrushChatMetadata",
    "CrushChatSummary",
    "CrushChatStorage",
    "create_empty_user_context",
    "create_empty_history_archive",
    "create_action_guide_item",
    # Context Builder
    "build_context",
    "build_context_dict",
    "estimate_tokens",
    "should_compress",
    "check_and_compress_if_needed",
    "get_context_stats",
    "TOKEN_BUDGET",
    # Archive Manager
    "check_conversation_compression_needed",
    "compress_conversation",
    "archive_guide_on_completion",
    "archive_status_on_replacement",
    "process_archiving_if_needed",
    "get_archive_stats",
    "get_full_history_content",
    "ARCHIVE_CONFIG",
    # State Storage (本地持久化)
    "save_state",
    "load_state",
    "delete_state",
    "list_users",
    "get_user_info",
    "get_or_create_state",
    "AutoSaveState",
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

