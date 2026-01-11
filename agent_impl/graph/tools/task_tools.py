"""
任务管理工具 (Task Tools)

提供给 Agent 的任务管理工具，支持：
1. switch_task: 切换到已存在的任务
2. create_task: 创建新任务并设为活跃
3. append_task_note: 追加思考笔记

设计原则：
- 工具返回后，模型可在同一轮内获得新任务上下文继续决策
- 保证任务 ID 唯一性
- 同一时刻只有一个活跃任务
"""

import json
from typing import Optional, Callable, TYPE_CHECKING
from datetime import datetime
from langchain_core.tools import tool

if TYPE_CHECKING:
    from graph.state import AgentState


# ============================================================
# 任务列表配置
# ============================================================

TASK_INDEX_CONFIG = {
    "max_display_count": 5,  # 任务列表最多展示条数（不含当前活跃）
}


# ============================================================
# 任务操作核心函数
# ============================================================

def get_task_list_for_agent(state: "AgentState", agent_name: str = "main_agent") -> list[dict]:
    """
    获取指定 Agent 的任务列表
    
    Args:
        state: 当前状态
        agent_name: Agent 名称
    
    Returns:
        任务列表
    """
    layer3_memory = state.get("layer3_memory", {}) or {}
    task_registry = layer3_memory.get("task_registry", {}) or {}
    return list(task_registry.get(agent_name, []) or [])


def get_active_task(task_list: list[dict]) -> Optional[dict]:
    """获取当前活跃任务"""
    for task in task_list:
        if task.get("is_active", False) or task.get("status") == "active":
            return task
    return None


def get_task_by_id(task_list: list[dict], task_id: str) -> Optional[dict]:
    """根据 ID 获取任务"""
    for task in task_list:
        if task.get("task_id") == task_id:
            return task
    return None


def format_task_index(task_list: list[dict], max_count: int = 5) -> str:
    """
    格式化任务列表（Task Index）
    
    展示最近 N 个任务 + 当前活跃任务标记
    
    Args:
        task_list: 任务列表
        max_count: 最大展示条数
    
    Returns:
        Markdown 格式的任务列表
    """
    if not task_list:
        return "暂无任务记录"
    
    # 按时间排序（最新在前）
    sorted_tasks = sorted(
        task_list,
        key=lambda t: t.get("started_at", ""),
        reverse=True
    )[:max_count + 1]  # 多取一个以确保活跃任务在列表中
    
    lines = [
        "| task_id | summary | status | active |",
        "|---------|---------|--------|--------|"
    ]
    
    for task in sorted_tasks:
        task_id = task.get("task_id", "")[:30]  # 截断过长的 ID
        summary = (task.get("summary", "") or "")[:40]
        status = task.get("status", "pending")
        is_active = "✅" if task.get("is_active", False) or task.get("status") == "active" else ""
        
        # 转义 Markdown 表格中的特殊字符
        task_id = task_id.replace("|", "\\|")
        summary = summary.replace("|", "\\|")
        
        lines.append(f"| {task_id} | {summary} | {status} | {is_active} |")
    
    return "\n".join(lines)


def format_active_task_payload(task: Optional[dict]) -> dict:
    """
    格式化当前活跃任务信息（Active Task Payload）
    
    Args:
        task: 活跃任务
    
    Returns:
        包含任务 ID 和 reasoning notes 的字典
    """
    if not task:
        return {
            "task_id": "",
            "summary": "",
            "reasoning_notes": []
        }
    
    return {
        "task_id": task.get("task_id", ""),
        "summary": task.get("summary", ""),
        "reasoning_notes": list(task.get("reasoning", []) or [])
    }


def switch_task_impl(
    state: "AgentState",
    task_id: str,
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """
    切换到已存在的任务
    
    Args:
        state: 当前状态
        task_id: 目标任务 ID
        agent_name: Agent 名称
    
    Returns:
        (状态更新字典, 工具返回消息)
    """
    task_list = get_task_list_for_agent(state, agent_name)
    
    # 检查任务是否存在
    target_task = get_task_by_id(task_list, task_id)
    if not target_task:
        available_ids = [t.get("task_id", "") for t in task_list[:5]]
        return {}, json.dumps({
            "success": False,
            "error": f"任务 '{task_id}' 不存在",
            "hint": f"可用任务: {available_ids}。如需新建请调用 create_task。",
            "task_index": format_task_index(task_list),
        }, ensure_ascii=False)
    
    # 切换活跃状态
    for task in task_list:
        was_active = task.get("is_active", False) or task.get("status") == "active"
        if task.get("task_id") == task_id:
            task["is_active"] = True
            task["status"] = "active"
        else:
            task["is_active"] = False
            if was_active:
                task["status"] = "pending"  # 原活跃任务变为 pending
    
    # 构建状态更新
    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()
    
    state_update = {"layer3_memory": layer3_memory}
    
    # 获取切换后的活跃任务
    active_task = get_task_by_id(task_list, task_id)
    
    return state_update, json.dumps({
        "success": True,
        "message": f"已切换到任务 '{task_id}'",
        "task_index": format_task_index(task_list),
        "active_task": format_active_task_payload(active_task),
    }, ensure_ascii=False)


def create_task_impl(
    state: "AgentState",
    task_id: str,
    summary: str = "",
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """
    创建新任务并设为活跃
    
    Args:
        state: 当前状态
        task_id: 新任务 ID
        summary: 任务摘要
        agent_name: Agent 名称
    
    Returns:
        (状态更新字典, 工具返回消息)
    """
    task_list = get_task_list_for_agent(state, agent_name)
    
    # 检查任务是否已存在
    existing_task = get_task_by_id(task_list, task_id)
    if existing_task:
        return {}, json.dumps({
            "success": False,
            "error": f"任务 '{task_id}' 已存在",
            "hint": "如需切换请调用 switch_task，或使用不同的 task_id 创建新任务。",
            "task_index": format_task_index(task_list),
        }, ensure_ascii=False)
    
    # 将现有活跃任务变为 pending
    for task in task_list:
        if task.get("is_active", False) or task.get("status") == "active":
            task["is_active"] = False
            task["status"] = "pending"
    
    # 创建新任务
    from graph.context_types import create_new_task
    new_task = create_new_task(task_id, summary)
    task_list.append(new_task)
    
    # 构建状态更新
    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()
    
    state_update = {"layer3_memory": layer3_memory}
    
    return state_update, json.dumps({
        "success": True,
        "message": f"已创建新任务 '{task_id}' 并设为活跃",
        "task_index": format_task_index(task_list),
        "active_task": format_active_task_payload(new_task),
    }, ensure_ascii=False)


def append_task_note_impl(
    state: "AgentState",
    note: str,
    task_id: Optional[str] = None,
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """
    追加思考笔记到指定任务
    
    Args:
        state: 当前状态
        note: 思考笔记内容
        task_id: 目标任务 ID（可选，默认为当前活跃任务）
        agent_name: Agent 名称
    
    Returns:
        (状态更新字典, 工具返回消息)
    """
    task_list = get_task_list_for_agent(state, agent_name)
    
    # 确定目标任务
    if task_id:
        target_task = get_task_by_id(task_list, task_id)
        if not target_task:
            return {}, json.dumps({
                "success": False,
                "error": f"任务 '{task_id}' 不存在",
            }, ensure_ascii=False)
    else:
        target_task = get_active_task(task_list)
        if not target_task:
            return {}, json.dumps({
                "success": False,
                "error": "没有活跃任务，请先创建或切换任务",
            }, ensure_ascii=False)
    
    # 追加笔记
    reasoning = list(target_task.get("reasoning", []) or [])
    reasoning.append(note)
    target_task["reasoning"] = reasoning
    
    # 更新任务列表中的任务
    for i, task in enumerate(task_list):
        if task.get("task_id") == target_task.get("task_id"):
            task_list[i] = target_task
            break
    
    # 构建状态更新
    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()
    
    state_update = {"layer3_memory": layer3_memory}
    
    return state_update, json.dumps({
        "success": True,
        "message": f"已追加笔记到任务 '{target_task.get('task_id')}'",
        "note_count": len(reasoning),
    }, ensure_ascii=False)


# ============================================================
# LangChain Tool 定义
# ============================================================

def create_task_tools(state_getter: Callable[[], "AgentState"], agent_name: str = "main_agent") -> list:
    """
    创建任务管理工具列表
    
    Args:
        state_getter: 获取当前状态的函数
        agent_name: Agent 名称
    
    Returns:
        LangChain Tool 列表
    """
    
    @tool
    def switch_task(task_id: str) -> str:
        """
        切换到已存在的任务。
        
        当用户的消息属于某个已有任务时，调用此工具切换到该任务。
        切换后会返回该任务的上下文信息，你可以基于这些信息继续决策。
        
        Args:
            task_id: 目标任务的唯一标识
        
        Returns:
            JSON 格式的结果，包含任务列表和当前任务信息
        """
        state = state_getter()
        _, result = switch_task_impl(state, task_id, agent_name)
        return result
    
    @tool
    def create_task(task_id: str, summary: str = "") -> str:
        """
        创建新任务并设为活跃。
        
        当用户开启了一个全新的话题/问题，不属于任何已有任务时，调用此工具创建新任务。
        
        Args:
            task_id: 新任务的唯一标识（建议使用语义化命名，如"判断crush是否喜欢用户"）
            summary: 任务摘要（20-30字，用于任务列表展示）
        
        Returns:
            JSON 格式的结果，包含任务列表和新任务信息
        """
        state = state_getter()
        _, result = create_task_impl(state, task_id, summary, agent_name)
        return result
    
    @tool
    def append_task_note(note: str, task_id: str = "") -> str:
        """
        追加思考笔记到任务。
        
        用于记录关键推理过程、决策依据等，便于后续回溯。
        如果不指定 task_id，默认追加到当前活跃任务。
        
        Args:
            note: 思考笔记内容
            task_id: 目标任务 ID（可选，默认为当前活跃任务）
        
        Returns:
            JSON 格式的确认信息
        """
        state = state_getter()
        _, result = append_task_note_impl(state, note, task_id or None, agent_name)
        return result
    
    return [switch_task, create_task, append_task_note]


# ============================================================
# 状态更新辅助函数（供 workflow 使用）
# ============================================================

def apply_task_tool_state_update(
    state: "AgentState",
    tool_name: str,
    tool_args: dict,
    agent_name: str = "main_agent"
) -> dict:
    """
    应用任务工具的状态更新
    
    由于 LangChain Tool 的限制，工具函数本身无法直接更新状态。
    此函数用于在 workflow 中根据工具调用结果更新状态。
    
    Args:
        state: 当前状态
        tool_name: 工具名称
        tool_args: 工具参数
        agent_name: Agent 名称
    
    Returns:
        状态更新字典
    """
    if tool_name == "switch_task":
        state_update, _ = switch_task_impl(
            state,
            tool_args.get("task_id", ""),
            agent_name
        )
        return state_update
    
    elif tool_name == "create_task":
        state_update, _ = create_task_impl(
            state,
            tool_args.get("task_id", ""),
            tool_args.get("summary", ""),
            agent_name
        )
        return state_update
    
    elif tool_name == "append_task_note":
        state_update, _ = append_task_note_impl(
            state,
            tool_args.get("note", ""),
            tool_args.get("task_id") or None,
            agent_name
        )
        return state_update
    
    return {}


# ============================================================
# 工具名称常量
# ============================================================

TASK_TOOL_NAMES = {"switch_task", "create_task", "append_task_note"}


def is_task_tool(tool_name: str) -> bool:
    """检查是否为任务管理工具"""
    return tool_name in TASK_TOOL_NAMES
