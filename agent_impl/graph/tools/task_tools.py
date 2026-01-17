"""
任务管理工具 (Task Tools)

提供给 Agent 的任务管理工具，支持：
1. create_task: 创建新任务并设为活跃
2. switch_task: 切换到已存在的任务
3. complete_task: 完成当前任务
4. append_task_note: 追加思考笔记
5. bind_context: 绑定通用上下文到当前任务
6. unbind_context: 解绑上下文
7. refresh_context: 刷新/续期上下文

基于 Task_System/task_system_spec.md 规范

设计原则：
- 使用 status 字段管理任务状态（pending/active/completed）
- 同一时刻只有一个活跃任务
- BoundContext 支持任意类型上下文绑定
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
    "max_non_completed": 5,  # 非 completed 任务最多展示条数（不含当前活跃）
    "max_completed": 3,      # completed 任务最多展示条数
}


# ============================================================
# 任务操作核心函数
# ============================================================

def get_task_list_for_agent(state: "AgentState", agent_name: str = "main_agent") -> list[dict]:
    """获取指定 Agent 的任务列表"""
    layer3_memory = state.get("layer3_memory", {}) or {}
    task_registry = layer3_memory.get("task_registry", {}) or {}
    return list(task_registry.get(agent_name, []) or [])


def get_active_task(task_list: list[dict]) -> Optional[dict]:
    """获取当前活跃任务（status == 'active'）"""
    for task in task_list:
        if task.get("status") == "active":
            return task
    return None


def get_task_by_id(task_list: list[dict], task_id: str) -> Optional[dict]:
    """根据 ID 获取任务"""
    for task in task_list:
        if task.get("task_id") == task_id:
            return task
    return None


def format_task_index(task_list: list[dict]) -> str:
    """格式化任务列表（Task Index）"""
    if not task_list:
        return "暂无任务记录"
    
    # 按时间排序（最新在前）
    sorted_tasks = sorted(
        task_list,
        key=lambda t: t.get("started_at", ""),
        reverse=True
    )

    active_task = get_active_task(sorted_tasks)
    non_completed = [t for t in sorted_tasks if t.get("status") != "completed" and t is not active_task]
    completed = [t for t in sorted_tasks if t.get("status") == "completed"]

    non_completed = non_completed[:TASK_INDEX_CONFIG["max_non_completed"]]
    completed = completed[:TASK_INDEX_CONFIG["max_completed"]]

    lines = ["## 任务列表"]

    if active_task:
        title = active_task.get("title") or active_task.get("task_id", "")
        summary = active_task.get("summary", "")
        lines.append("### 当前任务")
        lines.append(f"- **{title}** [active]")
        if summary:
            lines.append(f"  摘要：{summary}")

    if non_completed:
        lines.append("")
        lines.append("### 其他任务")
        lines.append("| title | status | summary |")
        lines.append("|-------|--------|---------|")
        for task in non_completed:
            title = (task.get("title") or task.get("task_id") or "")[:40]
            status = task.get("status", "pending")
            summary = (task.get("summary", "") or "")[:60]
            title = title.replace("|", "\\|")
            summary = summary.replace("|", "\\|")
            lines.append(f"| {title} | {status} | {summary} |")

    if completed:
        lines.append("")
        lines.append("### 已完成任务")
        lines.append("| title | completion_summary |")
        lines.append("|-------|---------------------|")
        for task in completed:
            title = (task.get("title") or task.get("task_id") or "")[:40]
            summary = (task.get("completion_summary", "") or "")[:80]
            title = title.replace("|", "\\|")
            summary = summary.replace("|", "\\|")
            lines.append(f"| {title} | {summary} |")

    return "\n".join(lines) if len(lines) > 1 else "暂无任务记录"


def format_active_task_payload(task: Optional[dict]) -> dict:
    """格式化当前活跃任务信息（Active Task Payload）"""
    if not task:
        return {
            "task_id": "",
            "title": "",
            "summary": "",
            "reasoning_notes": [],
            "bound_contexts": []
        }
    
    reasoning_notes = task.get("reasoning_notes")
    if not isinstance(reasoning_notes, list) or not reasoning_notes:
        reasoning_notes = []
    
    bound_contexts = task.get("bound_contexts")
    if not isinstance(bound_contexts, list) or not bound_contexts:
        bound_contexts = []
    
    return {
        "task_id": task.get("task_id", ""),
        "title": task.get("title", ""),
        "summary": task.get("summary", ""),
        "reasoning_notes": list(reasoning_notes),
        "bound_contexts": list(bound_contexts)
    }


# ============================================================
# 任务生命周期操作
# ============================================================

def create_task_impl(
    state: "AgentState",
    task_id: str,
    title: str = "",
    summary: str = "",
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """创建新任务并设为活跃"""
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
        if task.get("status") == "active":
            task["status"] = "pending"
    
    # 创建新任务
    from graph.context_types import create_new_task
    new_task = create_new_task(task_id, title or task_id, summary)
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


def switch_task_impl(
    state: "AgentState",
    task_id: str,
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """切换到已存在的任务"""
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
        if task.get("task_id") == task_id:
            task["status"] = "active"
        elif task.get("status") == "active":
            task["status"] = "pending"
    
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


def complete_task_impl(
    state: "AgentState",
    completion_summary: str,
    task_id: Optional[str] = None,
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """完成任务并生成结论摘要"""
    task_list = get_task_list_for_agent(state, agent_name)
    
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

    target_task["status"] = "completed"
    target_task["completed_at"] = datetime.now().isoformat()
    target_task["completion_summary"] = completion_summary

    for i, task in enumerate(task_list):
        if task.get("task_id") == target_task.get("task_id"):
            task_list[i] = target_task
            break

    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()

    state_update = {"layer3_memory": layer3_memory}

    return state_update, json.dumps({
        "success": True,
        "message": f"已完成任务 '{target_task.get('task_id')}'",
        "task_index": format_task_index(task_list),
    }, ensure_ascii=False)


def append_task_note_impl(
    state: "AgentState",
    note: str,
    task_id: Optional[str] = None,
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """追加思考笔记到指定任务"""
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
    from graph.context_types import create_reasoning_note
    reasoning_notes = list(target_task.get("reasoning_notes", []) or [])
    reasoning_notes.append(create_reasoning_note(note, target_task.get("task_id", "")))
    
    # 只保留最新 8 条
    if len(reasoning_notes) > 8:
        reasoning_notes = reasoning_notes[-8:]
    target_task["reasoning_notes"] = reasoning_notes
    
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
        "note_count": len(reasoning_notes),
    }, ensure_ascii=False)


# ============================================================
# 上下文绑定操作
# ============================================================

def bind_context_impl(
    state: "AgentState",
    context_type: str,
    title: str,
    content_md: str,
    ref_id: Optional[str] = None,
    expire_at: Optional[str] = None,
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """绑定通用上下文到当前任务"""
    from graph.context_types import create_bound_context, BOUND_CONTEXT_LIMITS
    
    task_list = get_task_list_for_agent(state, agent_name)
    active_task = get_active_task(task_list)
    
    if not active_task:
        return {}, json.dumps({
            "success": False,
            "error": "没有活跃任务，请先创建或切换任务",
        }, ensure_ascii=False)
    
    bound_contexts = list(active_task.get("bound_contexts", []) or [])
    
    # 如果有 ref_id，检查是否已绑定（去重）
    if ref_id:
        for ctx in bound_contexts:
            if ctx.get("ref_id") == ref_id and ctx.get("type") == context_type:
                return {}, json.dumps({
                    "success": False,
                    "error": f"上下文已绑定（ref_id={ref_id}）",
                    "hint": "如需更新请先 unbind_context 再重新绑定",
                }, ensure_ascii=False)
    
    # 检查该类型的绑定数量上限
    type_limit = BOUND_CONTEXT_LIMITS.get(context_type, BOUND_CONTEXT_LIMITS.get("default", 3))
    type_count = sum(1 for ctx in bound_contexts if ctx.get("type") == context_type)
    if type_count >= type_limit:
        return {}, json.dumps({
            "success": False,
            "error": f"类型 '{context_type}' 的绑定数量已达上限 ({type_limit})",
            "hint": "请先 unbind_context 移除旧的绑定",
        }, ensure_ascii=False)
    
    # 创建新的绑定上下文
    new_context = create_bound_context(
        context_type=context_type,
        title=title,
        content_md=content_md,
        ref_id=ref_id,
        expire_at=expire_at,
        source="tool:bind_context",
    )
    bound_contexts.append(new_context)
    active_task["bound_contexts"] = bound_contexts
    
    # 更新任务列表
    for i, task in enumerate(task_list):
        if task.get("task_id") == active_task.get("task_id"):
            task_list[i] = active_task
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
        "message": f"已绑定上下文 '{title}' (类型: {context_type})",
        "context_id": new_context.get("id"),
        "bound_count": len(bound_contexts),
    }, ensure_ascii=False)


def unbind_context_impl(
    state: "AgentState",
    context_id: str,
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """解绑上下文"""
    task_list = get_task_list_for_agent(state, agent_name)
    active_task = get_active_task(task_list)
    
    if not active_task:
        return {}, json.dumps({
            "success": False,
            "error": "没有活跃任务",
        }, ensure_ascii=False)
    
    bound_contexts = list(active_task.get("bound_contexts", []) or [])
    
    # 查找并移除
    found = False
    removed_title = ""
    new_contexts = []
    for ctx in bound_contexts:
        if ctx.get("id") == context_id:
            found = True
            removed_title = ctx.get("title", "")
        else:
            new_contexts.append(ctx)
    
    if not found:
        return {}, json.dumps({
            "success": False,
            "error": f"未找到上下文 ID: {context_id}",
            "available_ids": [ctx.get("id") for ctx in bound_contexts],
        }, ensure_ascii=False)
    
    active_task["bound_contexts"] = new_contexts
    
    # 更新任务列表
    for i, task in enumerate(task_list):
        if task.get("task_id") == active_task.get("task_id"):
            task_list[i] = active_task
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
        "message": f"已解绑上下文 '{removed_title}'",
        "remaining_count": len(new_contexts),
    }, ensure_ascii=False)


def refresh_context_impl(
    state: "AgentState",
    context_id: str,
    new_expire_at: Optional[str] = None,
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """刷新/续期上下文"""
    task_list = get_task_list_for_agent(state, agent_name)
    active_task = get_active_task(task_list)
    
    if not active_task:
        return {}, json.dumps({
            "success": False,
            "error": "没有活跃任务",
        }, ensure_ascii=False)
    
    bound_contexts = list(active_task.get("bound_contexts", []) or [])
    
    # 查找并更新
    found = False
    refreshed_title = ""
    for ctx in bound_contexts:
        if ctx.get("id") == context_id:
            found = True
            refreshed_title = ctx.get("title", "")
            # 更新绑定时间和过期时间
            ctx["bound_at"] = datetime.now().isoformat()
            if new_expire_at:
                ctx["expire_at"] = new_expire_at
            break
    
    if not found:
        return {}, json.dumps({
            "success": False,
            "error": f"未找到上下文 ID: {context_id}",
            "available_ids": [ctx.get("id") for ctx in bound_contexts],
        }, ensure_ascii=False)
    
    active_task["bound_contexts"] = bound_contexts
    
    # 更新任务列表
    for i, task in enumerate(task_list):
        if task.get("task_id") == active_task.get("task_id"):
            task_list[i] = active_task
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
        "message": f"已刷新上下文 '{refreshed_title}'",
    }, ensure_ascii=False)


# ============================================================
# LangChain Tool 定义
# ============================================================

def create_task_tools(state_getter: Callable[[], "AgentState"], agent_name: str = "main_agent") -> list:
    """创建任务管理工具列表"""
    
    @tool
    def create_task(task_id: str, title: str = "", summary: str = "") -> str:
        """
        创建新任务并设为活跃。
        
        当用户开启了一个全新的话题/问题，不属于任何已有任务时，调用此工具创建新任务。
        
        Args:
            task_id: 新任务的唯一标识（建议使用语义化命名）
            title: 任务标题（如"判断Crush是否喜欢用户"）
            summary: 任务摘要（20-30字，用于任务列表展示）
        
        Returns:
            JSON 格式的结果，包含任务列表和新任务信息
        """
        state = state_getter()
        _, result = create_task_impl(state, task_id, title, summary, agent_name)
        return result
    
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
    def complete_task(completion_summary: str, task_id: str = "") -> str:
        """
        完成当前任务并生成结论摘要。
        
        当任务目标已达成时，调用此工具完成任务。
        
        Args:
            completion_summary: 任务完成时的结论摘要（50-100字）
            task_id: 目标任务 ID（可选，默认为当前活跃任务）
        
        Returns:
            JSON 格式的确认信息
        """
        state = state_getter()
        _, result = complete_task_impl(state, completion_summary, task_id or None, agent_name)
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
    
    @tool
    def bind_context(context_type: str, title: str, content_md: str, ref_id: str = "", expire_at: str = "") -> str:
        """
        绑定通用上下文到当前任务。
        
        支持的 context_type:
        - action_guide: 行动指南详情（上限 3）
        - status_report: 现状报告片段（上限 1）
        - action_plan: 行动规划片段（上限 1）
        - crush_chat: Crush 聊天记录片段（上限 3）
        - history_snippet: 历史对话片段（上限 3）
        - dynamic_intel: 动态情报（上限 5）
        - custom: 自定义上下文（上限 3）
        
        Args:
            context_type: 上下文类型
            title: 标题（20-30字，用于列表展示）
            content_md: Markdown 格式内容（注入 Prompt 用）
            ref_id: 引用的资源 ID（用于去重，可选）
            expire_at: 过期时间 ISO 格式（可选）
        
        Returns:
            JSON 格式的确认信息
        """
        state = state_getter()
        _, result = bind_context_impl(
            state, context_type, title, content_md,
            ref_id or None, expire_at or None, agent_name
        )
        return result
    
    @tool
    def unbind_context(context_id: str) -> str:
        """
        解绑上下文。
        
        从当前任务中移除指定的绑定上下文。
        
        Args:
            context_id: 绑定上下文的 ID
        
        Returns:
            JSON 格式的确认信息
        """
        state = state_getter()
        _, result = unbind_context_impl(state, context_id, agent_name)
        return result
    
    @tool
    def refresh_context(context_id: str, new_expire_at: str = "") -> str:
        """
        刷新/续期上下文。
        
        更新绑定时间，可选更新过期时间。
        
        Args:
            context_id: 绑定上下文的 ID
            new_expire_at: 新的过期时间 ISO 格式（可选）
        
        Returns:
            JSON 格式的确认信息
        """
        state = state_getter()
        _, result = refresh_context_impl(state, context_id, new_expire_at or None, agent_name)
        return result
    
    return [create_task, switch_task, complete_task, append_task_note, bind_context, unbind_context, refresh_context]


# ============================================================
# 状态更新辅助函数（供 workflow 使用）
# ============================================================

def apply_task_tool_state_update(
    state: "AgentState",
    tool_name: str,
    tool_args: dict,
    agent_name: str = "main_agent"
) -> dict:
    """应用任务工具的状态更新"""
    if tool_name == "create_task":
        state_update, _ = create_task_impl(
            state,
            tool_args.get("task_id", ""),
            tool_args.get("title", ""),
            tool_args.get("summary", ""),
            agent_name
        )
        return state_update
    
    elif tool_name == "switch_task":
        state_update, _ = switch_task_impl(
            state,
            tool_args.get("task_id", ""),
            agent_name
        )
        return state_update
    
    elif tool_name == "complete_task":
        state_update, _ = complete_task_impl(
            state,
            tool_args.get("completion_summary", ""),
            tool_args.get("task_id") or None,
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
    
    elif tool_name == "bind_context":
        state_update, _ = bind_context_impl(
            state,
            tool_args.get("context_type", "custom"),
            tool_args.get("title", ""),
            tool_args.get("content_md", ""),
            tool_args.get("ref_id") or None,
            tool_args.get("expire_at") or None,
            agent_name
        )
        return state_update
    
    elif tool_name == "unbind_context":
        state_update, _ = unbind_context_impl(
            state,
            tool_args.get("context_id", ""),
            agent_name
        )
        return state_update
    
    elif tool_name == "refresh_context":
        state_update, _ = refresh_context_impl(
            state,
            tool_args.get("context_id", ""),
            tool_args.get("new_expire_at") or None,
            agent_name
        )
        return state_update
    
    return {}


# ============================================================
# 工具名称常量
# ============================================================

TASK_TOOL_NAMES = {
    "create_task",
    "switch_task",
    "complete_task",
    "append_task_note",
    "bind_context",
    "unbind_context",
    "refresh_context",
}


def is_task_tool(tool_name: str) -> bool:
    """检查是否为任务管理工具"""
    return tool_name in TASK_TOOL_NAMES
