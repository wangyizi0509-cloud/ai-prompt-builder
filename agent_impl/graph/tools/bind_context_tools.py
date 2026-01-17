"""
通用上下文绑定工具 (BoundContext)
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Optional, TYPE_CHECKING
import uuid

from langchain.tools import tool

if TYPE_CHECKING:
    from graph.state import AgentState

from graph.context_types import BoundContext, BOUND_CONTEXT_LIMITS
from graph.tools.task_tools import get_task_list_for_agent, get_active_task


def _get_limit(context_type: str) -> int:
    return int(BOUND_CONTEXT_LIMITS.get(context_type, BOUND_CONTEXT_LIMITS["default"]))


def _sort_by_bound_at(contexts: list[BoundContext]) -> list[BoundContext]:
    def _key(ctx: BoundContext) -> str:
        return str(ctx.get("bound_at") or "")
    return sorted(contexts, key=_key)


def bind_context_impl(
    state: "AgentState",
    *,
    context_type: str,
    title: str,
    content_md: str,
    ref_id: Optional[str] = None,
    expire_at: Optional[str] = None,
    source: str = "tool:bind_context",
    agent_name: str = "main_agent",
) -> tuple[dict, str]:
    """
    绑定上下文到当前活跃任务
    """
    task_list = get_task_list_for_agent(state, agent_name)
    active_task = get_active_task(task_list)
    if not active_task:
        return {}, json.dumps({
            "success": False,
            "error": "当前没有活跃任务",
            "hint": "请先创建或切换任务",
        }, ensure_ascii=False)

    bound_contexts = list(active_task.get("bound_contexts", []) or [])
    updated = False
    existing_idx = None

    if ref_id:
        for i, ctx in enumerate(bound_contexts):
            if ctx.get("type") == context_type and ctx.get("ref_id") == ref_id:
                existing_idx = i
                updated = True
                break

    new_ctx: BoundContext = {
        "id": str(uuid.uuid4())[:8],
        "type": context_type,
        "ref_id": ref_id,
        "title": title,
        "content_md": content_md,
        "source": source,
        "bound_at": datetime.now().isoformat(),
        "expire_at": expire_at,
    }

    evicted = None
    if existing_idx is not None:
        bound_contexts[existing_idx] = new_ctx
    else:
        bound_contexts.append(new_ctx)
        limit = _get_limit(context_type)
        if len([c for c in bound_contexts if c.get("type") == context_type]) > limit:
            # 优先淘汰有 expire_at 的最早绑定
            same_type = [c for c in bound_contexts if c.get("type") == context_type]
            with_expire = [c for c in same_type if c.get("expire_at")]
            candidates = with_expire or same_type
            candidates = _sort_by_bound_at(candidates)
            evicted = candidates[0] if candidates else None
            if evicted:
                bound_contexts = [c for c in bound_contexts if c.get("id") != evicted.get("id")]

    active_task["bound_contexts"] = bound_contexts

    for i, task in enumerate(task_list):
        if task.get("task_id") == active_task.get("task_id"):
            task_list[i] = active_task
            break

    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()

    state_update = {"layer3_memory": layer3_memory}

    result = {
        "success": True,
        "bound_to_task_id": active_task.get("task_id", ""),
        "updated": updated,
        "context_id": new_ctx["id"],
    }
    if evicted:
        result["evicted"] = {
            "context_id": evicted.get("id", ""),
            "title": evicted.get("title", ""),
            "reason": f"超过 type={context_type} 上限 {limit}，已淘汰最早绑定的上下文",
        }

    return state_update, json.dumps(result, ensure_ascii=False)


def unbind_context_impl(
    state: "AgentState",
    context_id: str,
    agent_name: str = "main_agent",
) -> tuple[dict, str]:
    task_list = get_task_list_for_agent(state, agent_name)
    active_task = get_active_task(task_list)
    if not active_task:
        return {}, json.dumps({
            "success": False,
            "error": "当前没有活跃任务",
        }, ensure_ascii=False)

    bound_contexts = list(active_task.get("bound_contexts", []) or [])
    new_list = [c for c in bound_contexts if c.get("id") != context_id]
    if len(new_list) == len(bound_contexts):
        return {}, json.dumps({
            "success": False,
            "error": f"未找到 context_id={context_id}",
        }, ensure_ascii=False)

    active_task["bound_contexts"] = new_list
    for i, task in enumerate(task_list):
        if task.get("task_id") == active_task.get("task_id"):
            task_list[i] = active_task
            break

    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()

    return {"layer3_memory": layer3_memory}, json.dumps({
        "success": True,
        "message": f"已解绑 context_id={context_id}",
    }, ensure_ascii=False)


def refresh_context_impl(
    state: "AgentState",
    context_id: str,
    content_md: Optional[str] = None,
    expire_at: Optional[str] = None,
    agent_name: str = "main_agent",
) -> tuple[dict, str]:
    task_list = get_task_list_for_agent(state, agent_name)
    active_task = get_active_task(task_list)
    if not active_task:
        return {}, json.dumps({
            "success": False,
            "error": "当前没有活跃任务",
        }, ensure_ascii=False)

    bound_contexts = list(active_task.get("bound_contexts", []) or [])
    updated = False
    for ctx in bound_contexts:
        if ctx.get("id") == context_id:
            if content_md:
                ctx["content_md"] = content_md
            if expire_at is not None:
                ctx["expire_at"] = expire_at
            ctx["bound_at"] = datetime.now().isoformat()
            updated = True
            break

    if not updated:
        return {}, json.dumps({
            "success": False,
            "error": f"未找到 context_id={context_id}",
        }, ensure_ascii=False)

    active_task["bound_contexts"] = bound_contexts
    for i, task in enumerate(task_list):
        if task.get("task_id") == active_task.get("task_id"):
            task_list[i] = active_task
            break

    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()

    return {"layer3_memory": layer3_memory}, json.dumps({
        "success": True,
        "message": f"已刷新 context_id={context_id}",
    }, ensure_ascii=False)


def create_bind_context_tools(state_getter: Callable[[], "AgentState"], agent_name: str = "main_agent") -> list:
    """
    创建通用上下文绑定工具
    """
    @tool
    def bind_context(
        type: str,
        title: str,
        content_md: str,
        ref_id: str = "",
        expire_at: str = "",
        source: str = "tool:bind_context",
    ) -> str:
        state = state_getter() or {}
        _, result = bind_context_impl(
            state,
            context_type=type,
            title=title,
            content_md=content_md,
            ref_id=ref_id or None,
            expire_at=expire_at or None,
            source=source,
            agent_name=agent_name,
        )
        return result

    @tool
    def unbind_context(context_id: str) -> str:
        state = state_getter() or {}
        _, result = unbind_context_impl(state, context_id, agent_name)
        return result

    @tool
    def refresh_context(context_id: str, content_md: str = "", expire_at: str = "") -> str:
        state = state_getter() or {}
        _, result = refresh_context_impl(
            state,
            context_id,
            content_md=content_md or None,
            expire_at=expire_at or None,
            agent_name=agent_name,
        )
        return result

    return [bind_context, unbind_context, refresh_context]
