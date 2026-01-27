"""
Agent 工具模块

提供给 Agent 按需调用的工具集合
"""

from .drawer_tools import (
    # 历史记录抽屉工具
    get_full_status_history,
    get_full_guide_history,
    list_history_summaries,
    get_conversation_archive,
    # Crush 聊天抽屉工具
    get_recent_crush_messages,
    get_important_crush_messages,
    search_crush_messages,
    # 统一工具类
    DrawerTools,
    create_drawer_tools_for_langchain,
)

from .task_tools import (
    # 任务管理工具
    create_task_tools,
    apply_task_tool_state_update,
    is_task_tool,
    TASK_TOOL_NAMES,
    # 任务操作函数
    format_task_index,
    format_active_task_payload,
    get_task_list_for_agent,
    get_active_task,
    get_task_by_id,
)

from .context_loader import (
    create_context_loader,
    apply_context_loader_state_update,
    is_context_loader_tool,
)

from .submit_tools import (
    submit_status_report,
    submit_action_plan,
    submit_action_guide,
    update_guide_status,
    return_to_main,
    apply_submit_tool_state_update,
    is_submit_tool,
    SUBMIT_TOOL_NAMES,
)

from .ask_tool import (
    # 新版 ask 工具（状态驱动）
    get_ask_tool,
    ask_enable,
    ask_questions,
    ASK_MODE_STRATEGY,
    ASK_MODE_SIMPLE,
)

from .consult_answer_tool import (
    # 解答工具（状态驱动）
    get_consult_tool,
    consult_enable,
    consult_complete,
    CONSULT_MODE_STRATEGY,
    CONSULT_MODE_SIMPLE,
)

from .emotion_support_tool import (
    # 陪伴工具（状态驱动）
    get_emotion_tool,
    emotion_enable,
    emotion_complete,
    EMOTION_MODE_STRATEGY,
    EMOTION_MODE_SIMPLE,
)

__all__ = [
    # 历史记录
    "get_full_status_history",
    "get_full_guide_history",
    "list_history_summaries",
    "get_conversation_archive",
    # Crush 聊天
    "get_recent_crush_messages",
    "get_important_crush_messages",
    "search_crush_messages",
    # 抽屉工具类
    "DrawerTools",
    "create_drawer_tools_for_langchain",
    # 任务管理工具
    "create_task_tools",
    "apply_task_tool_state_update",
    "is_task_tool",
    "TASK_TOOL_NAMES",
    "format_task_index",
    "format_active_task_payload",
    "get_task_list_for_agent",
    "get_active_task",
    "get_task_by_id",
    # 上下文拉取工具
    "create_context_loader",
    "apply_context_loader_state_update",
    "is_context_loader_tool",
    # 提交类工具
    "submit_status_report",
    "submit_action_plan",
    "submit_action_guide",
    "update_guide_status",
    "return_to_main",
    "apply_submit_tool_state_update",
    "is_submit_tool",
    "SUBMIT_TOOL_NAMES",
    # Ask 工具（状态驱动）
    "get_ask_tool",
    "ask_enable",
    "ask_questions",
    "ASK_MODE_STRATEGY",
    "ASK_MODE_SIMPLE",
    # Consult Answer 工具（状态驱动）
    "get_consult_tool",
    "consult_enable",
    "consult_complete",
    "CONSULT_MODE_STRATEGY",
    "CONSULT_MODE_SIMPLE",
    # Emotion Support 工具（状态驱动）
    "get_emotion_tool",
    "emotion_enable",
    "emotion_complete",
    "EMOTION_MODE_STRATEGY",
    "EMOTION_MODE_SIMPLE",
]
