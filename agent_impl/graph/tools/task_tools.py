"""
任务管理工具 (Task Tools)

统一为 task_manager 工具，支持：
1. create: 创建新任务并设为活跃
2. switch: 切换到已存在的任务
3. complete: 完成当前任务
4. append_note: 追加思考笔记
"""

import copy
import json
from typing import Optional, Callable, TYPE_CHECKING
from datetime import datetime
from langchain_core.tools import tool
from graph.tools.schemas import TaskManagerInput, tool_error_response
from agents.tooling.tool_result import error, ok

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
    return copy.deepcopy(list(task_registry.get(agent_name, []) or []))


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


def build_task_index_payload(task_list: list[dict]) -> list[dict]:
    """构建任务索引（结构化）"""
    if not task_list:
        return []
    sorted_tasks = sorted(
        task_list,
        key=lambda t: t.get("started_at", ""),
        reverse=True,
    )
    payload = []
    for task in sorted_tasks:
        payload.append({
            "task_id": task.get("task_id", ""),
            "title": task.get("title", ""),
            "status": task.get("status", "pending"),
            "summary": task.get("summary", ""),
        })
    return payload


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
) -> tuple[dict, dict]:
    """创建新任务并设为活跃"""
    task_list = get_task_list_for_agent(state, agent_name)
    
    # 检查任务是否已存在
    existing_task = get_task_by_id(task_list, task_id)
    if existing_task:
        return {}, json.loads(tool_error_response(
            f"任务 '{task_id}' 已存在",
            {
                "hint": "如需切换请调用 task_manager(action='switch')",
                "task_index": build_task_index_payload(task_list),
            },
        ))
    
    # 将现有活跃任务变为 pending
    for task in task_list:
        if task.get("status") == "active" or task.get("is_active"):
            task["status"] = "pending"
            task["is_active"] = False
    
    # 创建新任务
    from graph.context_types import create_new_task
    new_task = create_new_task(task_id, title or task_id, summary)
    new_task["is_active"] = True
    task_list.append(new_task)
    
    # 构建状态更新
    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()
    
    state_update = {"layer3_memory": layer3_memory}
    
    return state_update, {
        "success": True,
        "action": "create",
        "message": f"已创建新任务 '{task_id}' 并设为活跃",
        "task_index": build_task_index_payload(task_list),
        "current_task": format_active_task_payload(new_task),
    }


def switch_task_impl(
    state: "AgentState",
    task_id: str,
    agent_name: str = "main_agent"
) -> tuple[dict, dict]:
    """切换到已存在的任务"""
    task_list = get_task_list_for_agent(state, agent_name)
    
    # 检查任务是否存在
    target_task = get_task_by_id(task_list, task_id)
    if not target_task:
        available_ids = [t.get("task_id", "") for t in task_list[:5]]
        return {}, json.loads(tool_error_response(
            f"任务 '{task_id}' 不存在",
            {
                "hint": f"可用任务: {available_ids}。如需新建请调用 task_manager(action='create')",
                "task_index": build_task_index_payload(task_list),
            },
        ))
    
    # 切换活跃状态
    for task in task_list:
        if task.get("task_id") == task_id:
            task["status"] = "active"
            task["is_active"] = True
        else:
            if task.get("status") == "active":
                task["status"] = "pending"
            task["is_active"] = False
    
    # 构建状态更新
    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()
    
    state_update = {"layer3_memory": layer3_memory}
    
    # 获取切换后的活跃任务
    active_task = get_task_by_id(task_list, task_id)
    
    return state_update, {
        "success": True,
        "action": "switch",
        "message": f"已切换到任务 '{task_id}'",
        "task_index": build_task_index_payload(task_list),
        "current_task": format_active_task_payload(active_task),
    }


def complete_task_impl(
    state: "AgentState",
    completion_summary: str,
    task_id: Optional[str] = None,
    agent_name: str = "main_agent"
) -> tuple[dict, dict]:
    """完成任务并生成结论摘要"""
    task_list = get_task_list_for_agent(state, agent_name)
    
    if task_id:
        target_task = get_task_by_id(task_list, task_id)
        if not target_task:
            return {}, json.loads(tool_error_response(f"任务 '{task_id}' 不存在"))
    else:
        target_task = get_active_task(task_list)
        if not target_task:
            return {}, json.loads(tool_error_response("没有活跃任务，请先创建或切换任务"))

    target_task["status"] = "completed"
    target_task["is_active"] = False
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

    return state_update, {
        "success": True,
        "action": "complete",
        "message": f"已完成任务 '{target_task.get('task_id')}'",
        "task_index": build_task_index_payload(task_list),
        "current_task": format_active_task_payload(get_active_task(task_list)),
    }


def append_task_note_impl(
    state: "AgentState",
    note: str,
    task_id: Optional[str] = None,
    agent_name: str = "main_agent"
) -> tuple[dict, dict]:
    """追加思考笔记到指定任务"""
    task_list = get_task_list_for_agent(state, agent_name)
    
    # 确定目标任务
    if task_id:
        target_task = get_task_by_id(task_list, task_id)
        if not target_task:
            return {}, json.loads(tool_error_response(f"任务 '{task_id}' 不存在"))
    else:
        target_task = get_active_task(task_list)
        if not target_task:
            return {}, json.loads(tool_error_response("没有活跃任务，请先创建或切换任务"))
    
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
    
    return state_update, {
        "success": True,
        "action": "append_note",
        "message": f"已追加笔记到任务 '{target_task.get('task_id')}'",
        "note_count": len(reasoning_notes),
        "task_index": build_task_index_payload(task_list),
        "current_task": format_active_task_payload(get_active_task(task_list)),
    }


# ============================================================
# LangChain Tool 定义
# ============================================================

def create_task_tools(state_getter: Callable[[], "AgentState"], agent_name: str = "main_agent") -> list:
    """创建 task_manager 工具"""

    @tool(args_schema=TaskManagerInput)
    def task_manager(
        action: str,
        task_id: str = "",
        title: str = "",
        summary: str = "",
        note: str = "",
    ) -> dict:
        """
        任务管理工具（统一入口，主路径）。
        用于任务状态变更的唯一主入口，支持 create / switch / complete / append_note。
        """
        state = state_getter()
        if action == "create":
            state_update, result = create_task_impl(state, task_id, title, summary, agent_name)
        elif action == "switch":
            state_update, result = switch_task_impl(state, task_id, agent_name)
        elif action == "complete":
            if not summary:
                return error(tool_error_response("complete 操作需要 summary"))
            state_update, result = complete_task_impl(state, summary, task_id or None, agent_name)
        elif action == "append_note":
            if not note:
                return error(tool_error_response("append_note 操作需要 note"))
            state_update, result = append_task_note_impl(state, note, task_id or None, agent_name)
        else:
            return error(tool_error_response(f"不支持的 action: {action}"))

        payload = json.dumps(result, ensure_ascii=False)
        if bool(result.get("success")):
            return ok(payload, state_patch=state_update)
        return error(payload, state_patch=state_update)

    return [task_manager]


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
    if tool_name != "task_manager":
        return {}

    action = tool_args.get("action", "")
    if action == "create":
        state_update, _ = create_task_impl(
            state,
            tool_args.get("task_id", ""),
            tool_args.get("title", ""),
            tool_args.get("summary", ""),
            agent_name,
        )
        return state_update

    if action == "switch":
        state_update, _ = switch_task_impl(
            state,
            tool_args.get("task_id", ""),
            agent_name,
        )
        return state_update

    if action == "complete":
        state_update, _ = complete_task_impl(
            state,
            tool_args.get("summary", ""),
            tool_args.get("task_id") or None,
            agent_name,
        )
        return state_update

    if action == "append_note":
        state_update, _ = append_task_note_impl(
            state,
            tool_args.get("note", ""),
            tool_args.get("task_id") or None,
            agent_name,
        )
        return state_update

    return {}


# ============================================================
# 工具名称常量
# ============================================================

TASK_TOOL_NAMES = {"task_manager"}


def is_task_tool(tool_name: str) -> bool:
    """检查是否为任务管理工具"""
    return tool_name in TASK_TOOL_NAMES
