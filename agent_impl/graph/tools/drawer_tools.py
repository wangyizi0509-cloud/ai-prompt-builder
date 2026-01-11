"""
抽屉式完整信息调用工具 (Drawer Tools)

提供给 Agent 按需调用的工具，用于获取：
1. 历史报告/指南的完整内容
2. Crush 聊天记录的关键片段
3. 更多上下文细节

这些工具返回的信息不会常驻上下文，只在 Agent 需要时调用
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from graph.state import AgentState
    from graph.crush_chat_storage import CrushChatManager


# ============================================================
# 历史报告/指南 抽屉工具
# ============================================================

def get_full_status_history(
    state: "AgentState",
    index: int = 0,
) -> str:
    """
    获取历史现状分析的完整内容
    
    Args:
        state: 当前状态
        index: 历史索引（0=最近，1=次近...）
    
    Returns:
        完整的现状分析报告内容
    """
    archive = state.get("history_archive", {})
    status_history = archive.get("status_history", [])
    
    if not status_history:
        return "暂无历史现状分析记录"
    
    if index < 0 or index >= len(status_history):
        return f"索引超出范围，共有 {len(status_history)} 条历史记录（索引 0-{len(status_history)-1}）"
    
    item = status_history[index]
    full_content = item.get("full_content", "")
    
    if not full_content:
        # 如果没有完整内容，返回摘要
        return f"[仅有摘要] {item.get('summary', item.get('one_liner', '无内容'))}"
    
    created_at = item.get("created_at", "未知时间")[:10]
    return f"## 历史现状分析（{created_at}）\n\n{full_content}"


def get_full_guide_history(
    state: "AgentState",
    index: int = 0,
) -> str:
    """
    获取历史行动指南的完整内容
    
    Args:
        state: 当前状态
        index: 历史索引（0=最近，1=次近...）
    
    Returns:
        完整的行动指南内容
    """
    archive = state.get("history_archive", {})
    guide_history = archive.get("guide_history", [])
    
    if not guide_history:
        return "暂无历史行动指南记录"
    
    if index < 0 or index >= len(guide_history):
        return f"索引超出范围，共有 {len(guide_history)} 条历史记录（索引 0-{len(guide_history)-1}）"
    
    item = guide_history[index]
    full_content = item.get("full_content", "")
    
    if not full_content:
        return f"[仅有摘要] {item.get('summary', item.get('one_liner', '无内容'))}"
    
    created_at = item.get("created_at", "未知时间")[:10]
    return f"## 历史行动指南（{created_at}）\n\n{full_content}"


def list_history_summaries(
    state: "AgentState",
    history_type: str = "all",
) -> str:
    """
    列出所有历史摘要
    
    Args:
        state: 当前状态
        history_type: "status" / "guide" / "plan" / "all"
    
    Returns:
        历史摘要列表
    """
    archive = state.get("history_archive", {})
    parts = []
    
    if history_type in ("status", "all"):
        status_history = archive.get("status_history", [])
        if status_history:
            parts.append("### 历史现状分析")
            for i, item in enumerate(status_history):
                summary = item.get("summary") or item.get("one_liner", "")
                created_at = item.get("created_at", "")[:10]
                parts.append(f"[{i}] ({created_at}) {summary[:50]}...")
    
    if history_type in ("guide", "all"):
        guide_history = archive.get("guide_history", [])
        if guide_history:
            parts.append("### 历史行动指南")
            for i, item in enumerate(guide_history):
                summary = item.get("summary") or item.get("one_liner", "")
                created_at = item.get("created_at", "")[:10]
                parts.append(f"[{i}] ({created_at}) {summary[:50]}...")
    
    if history_type in ("plan", "all"):
        plan_history = archive.get("plan_history", [])
        if plan_history:
            parts.append("### 历史行动规划")
            for i, item in enumerate(plan_history):
                summary = item.get("summary") or item.get("one_liner", "")
                created_at = item.get("created_at", "")[:10]
                parts.append(f"[{i}] ({created_at}) {summary[:50]}...")
    
    if not parts:
        return "暂无历史记录"
    
    return "\n".join(parts)


# ============================================================
# Crush 聊天记录 抽屉工具
# ============================================================

def get_recent_crush_messages(
    crush_chat_manager: "CrushChatManager",
    count: int = 20,
) -> str:
    """
    获取最近的 Crush 聊天记录
    
    Args:
        crush_chat_manager: Crush 聊天管理器
        count: 获取条数
    
    Returns:
        格式化的聊天记录
    """
    if crush_chat_manager is None:
        return "暂无 Crush 聊天记录"
    
    messages = crush_chat_manager.get_recent_messages(count)
    if not messages:
        return "暂无 Crush 聊天记录"
    
    parts = [f"## 最近 {len(messages)} 条聊天记录"]
    for msg in messages:
        sender = "用户" if msg.sender == "user" else "Crush"
        time_str = msg.timestamp[:16] if msg.timestamp else ""
        parts.append(f"**{sender}** [{time_str}]: {msg.content}")
    
    return "\n\n".join(parts)


def get_important_crush_messages(
    crush_chat_manager: "CrushChatManager",
) -> str:
    """
    获取标记为重要的 Crush 聊天记录
    
    Args:
        crush_chat_manager: Crush 聊天管理器
    
    Returns:
        格式化的重要聊天记录
    """
    if crush_chat_manager is None:
        return "暂无 Crush 聊天记录"
    
    messages = crush_chat_manager.get_important_messages()
    if not messages:
        return "暂无标记为重要的聊天记录"
    
    parts = ["## 重要聊天记录"]
    for msg in messages:
        sender = "用户" if msg.sender == "user" else "Crush"
        reason = f"（重要原因：{msg.importance_reason}）" if msg.importance_reason else ""
        parts.append(f"**{sender}**: {msg.content} {reason}")
    
    return "\n\n".join(parts)


def search_crush_messages(
    crush_chat_manager: "CrushChatManager",
    keyword: str,
) -> str:
    """
    搜索 Crush 聊天记录
    
    Args:
        crush_chat_manager: Crush 聊天管理器
        keyword: 搜索关键词
    
    Returns:
        匹配的聊天记录
    """
    if crush_chat_manager is None:
        return "暂无 Crush 聊天记录"
    
    messages = crush_chat_manager.search_messages(keyword)
    if not messages:
        return f"未找到包含「{keyword}」的聊天记录"
    
    parts = [f"## 搜索结果：「{keyword}」（共 {len(messages)} 条）"]
    for msg in messages[:20]:  # 最多返回 20 条
        sender = "用户" if msg.sender == "user" else "Crush"
        time_str = msg.timestamp[:10] if msg.timestamp else ""
        parts.append(f"**{sender}** ({time_str}): {msg.content}")
    
    if len(messages) > 20:
        parts.append(f"\n... 还有 {len(messages) - 20} 条结果未显示")
    
    return "\n\n".join(parts)


# ============================================================
# 对话归档 抽屉工具
# ============================================================

def get_conversation_archive(
    state: "AgentState",
    index: int = 0,
) -> str:
    """
    获取历史对话归档详情
    
    Args:
        state: 当前状态
        index: 归档索引
    
    Returns:
        对话归档详情
    """
    archive = state.get("history_archive", {})
    conv_archive = archive.get("conversation_archive", [])
    
    if not conv_archive:
        return "暂无对话归档"
    
    if index < 0 or index >= len(conv_archive):
        return f"索引超出范围，共有 {len(conv_archive)} 条归档（索引 0-{len(conv_archive)-1}）"
    
    item = conv_archive[index]
    
    parts = [
        f"## 对话归档 #{index}",
        f"**时间**：{item.get('start_time', '')[:10]} 至 {item.get('end_time', '')[:10]}",
        f"**轮次**：{item.get('turn_count', 0)} 轮",
        f"**摘要**：{item.get('summary', '无')}",
    ]
    
    key_topics = item.get("key_topics", [])
    if key_topics:
        parts.append(f"**关键话题**：{', '.join(key_topics)}")
    
    extracted = item.get("extracted_info", {})
    if extracted:
        parts.append("**提取的信息**：")
        for key, value in extracted.items():
            if value:
                parts.append(f"  - {key}: {value}")
    
    return "\n".join(parts)


# ============================================================
# 统一工具接口（供 LangGraph Tools 使用）
# ============================================================

class DrawerTools:
    """
    抽屉工具集合
    
    封装所有抽屉工具，提供统一接口
    """
    
    def __init__(
        self,
        state: "AgentState",
        crush_chat_manager: Optional["CrushChatManager"] = None,
    ):
        self.state = state
        self.crush_chat_manager = crush_chat_manager
    
    def get_full_history(
        self,
        history_type: str,
        index: int = 0,
    ) -> str:
        """
        获取历史记录的完整内容
        
        Args:
            history_type: "status" / "guide" / "plan" / "conversation"
            index: 索引
        
        Returns:
            完整内容
        """
        if history_type == "status":
            return get_full_status_history(self.state, index)
        elif history_type == "guide":
            return get_full_guide_history(self.state, index)
        elif history_type == "conversation":
            return get_conversation_archive(self.state, index)
        else:
            return f"未知的历史类型：{history_type}"
    
    def list_history(self, history_type: str = "all") -> str:
        """列出历史摘要"""
        return list_history_summaries(self.state, history_type)
    
    def get_crush_chat(
        self,
        action: str = "recent",
        count: int = 20,
        keyword: str = "",
    ) -> str:
        """
        获取 Crush 聊天记录
        
        Args:
            action: "recent" / "important" / "search"
            count: 获取条数（仅 recent 有效）
            keyword: 搜索关键词（仅 search 有效）
        
        Returns:
            聊天记录
        """
        if action == "recent":
            return get_recent_crush_messages(self.crush_chat_manager, count)
        elif action == "important":
            return get_important_crush_messages(self.crush_chat_manager)
        elif action == "search":
            return search_crush_messages(self.crush_chat_manager, keyword)
        else:
            return f"未知的操作：{action}"


# ============================================================
# LangGraph 工具定义（供 Agent 使用）
# ============================================================

def create_drawer_tools_for_langchain(
    state: "AgentState",
    crush_chat_manager: Optional["CrushChatManager"] = None,
) -> list:
    """
    创建 LangChain/LangGraph 格式的工具列表
    
    注意：这需要 langchain 的 Tool 类，如果环境中没有则返回空列表
    """
    try:
        from langchain.tools import Tool
    except ImportError:
        print("[DrawerTools] langchain not installed, returning empty tools")
        return []
    
    drawer = DrawerTools(state, crush_chat_manager)
    
    tools = [
        Tool(
            name="get_full_history",
            description="""获取历史报告或指南的完整内容。
参数格式：history_type,index
- history_type: status（现状分析）/ guide（行动指南）/ conversation（对话归档）
- index: 索引，0=最近，1=次近
示例：status,0 表示获取最近的现状分析完整内容""",
            func=lambda x: drawer.get_full_history(
                *x.split(",") if "," in x else (x, 0)
            ),
        ),
        Tool(
            name="list_history",
            description="""列出所有历史记录摘要。
参数：history_type（可选）
- all: 全部（默认）
- status: 现状分析
- guide: 行动指南
示例：status""",
            func=lambda x: drawer.list_history(x or "all"),
        ),
        Tool(
            name="get_crush_chat",
            description="""获取 Crush 聊天记录。
参数格式：action,param
- recent,20: 获取最近 20 条
- important: 获取重要消息
- search,关键词: 搜索包含关键词的消息
示例：recent,10 或 search,约会""",
            func=lambda x: _parse_crush_chat_args(drawer, x),
        ),
    ]
    
    return tools


def _parse_crush_chat_args(drawer: DrawerTools, args_str: str) -> str:
    """解析 get_crush_chat 的参数"""
    parts = args_str.split(",", 1)
    action = parts[0].strip()
    
    if action == "recent":
        count = int(parts[1]) if len(parts) > 1 else 20
        return drawer.get_crush_chat("recent", count=count)
    elif action == "important":
        return drawer.get_crush_chat("important")
    elif action == "search":
        keyword = parts[1].strip() if len(parts) > 1 else ""
        return drawer.get_crush_chat("search", keyword=keyword)
    else:
        return drawer.get_crush_chat(action)
