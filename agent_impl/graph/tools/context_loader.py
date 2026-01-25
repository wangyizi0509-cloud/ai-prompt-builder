"""
通用上下文拉取工具 (context_loader)
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, Optional, TYPE_CHECKING

from langchain_core.tools import tool

if TYPE_CHECKING:
    from graph.state import AgentState

from graph.context_types import (
    BOUND_CONTEXT_LIMITS,
    create_bound_context,
)
from graph.tools.schemas import ContextLoaderInput, tool_error_response
from graph.tools.task_tools import get_task_list_for_agent, get_active_task


CONTEXT_LOADER_TOOL_NAMES = {"context_loader"}


def is_context_loader_tool(tool_name: str) -> bool:
    return tool_name in CONTEXT_LOADER_TOOL_NAMES


def _build_guide_detail_md(guide_item: dict) -> str:
    guide = guide_item.get("guide") if isinstance(guide_item.get("guide"), dict) else {}
    guide_id = guide_item.get("id", "")
    title = guide_item.get("title") or guide.get("current_task") or "未命名指南"
    status = guide_item.get("status") or "pending"
    created_at = guide_item.get("created_at") or ""

    guide_content = ""
    if isinstance(guide_item.get("guide_content"), str) and guide_item.get("guide_content"):
        guide_content = guide_item["guide_content"]
    elif isinstance(guide.get("guide_content"), str) and guide.get("guide_content"):
        guide_content = guide["guide_content"]

    meta_lines = [
        f"## 指南详情：{title}",
        "",
        f"- **ID**: {guide_id}",
        f"- **状态**: {status}",
    ]
    if created_at:
        meta_lines.append(f"- **创建时间**: {created_at}")

    if guide_content:
        return "\n".join(meta_lines) + "\n\n" + guide_content

    parts = list(meta_lines)
    steps = guide.get("steps") or []
    if isinstance(steps, list) and steps:
        parts.append("\n### 步骤")
        parts.extend([f"{i}. {s}" for i, s in enumerate([str(x) for x in steps], 1)])
    talking_points = guide.get("talking_points") or []
    if isinstance(talking_points, list) and talking_points:
        parts.append("\n### 话术要点")
        parts.extend([f"- {tp}" for tp in [str(x) for x in talking_points]])
    if len(parts) == len(meta_lines):
        parts.append("\n该指南没有可用的详细内容（guide_content/steps 均为空）。")
    return "\n".join(parts)


def _find_action_guide(state: "AgentState", context_id: str) -> Optional[dict]:
    layer2 = state.get("layer2_memory") or {}
    guides = layer2.get("action_guides") or state.get("action_guides") or []
    target_id = str(context_id or "").strip()
    if not target_id:
        return None
    for g in guides:
        if not isinstance(g, dict):
            continue
        if str(g.get("id") or "") == target_id:
            return g
        if str(g.get("guide_id") or "") == target_id:
            return g
    return None


def _find_status_report(state: "AgentState", context_id: str) -> Optional[dict]:
    layer2 = state.get("layer2_memory") or {}
    current = layer2.get("current_status_report")
    history = layer2.get("status_report_history") or []
    target_id = str(context_id or "").strip()
    if not target_id or target_id == "current":
        return current
    for item in [current] + list(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == target_id:
            return item
        if str(item.get("report_id") or "") == target_id:
            return item
    return None


def _find_action_plan(state: "AgentState", context_id: str) -> Optional[dict]:
    layer2 = state.get("layer2_memory") or {}
    current = layer2.get("current_action_plan")
    history = layer2.get("action_plan_history") or []
    target_id = str(context_id or "").strip()
    if not target_id or target_id == "current":
        return current
    for item in [current] + list(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == target_id:
            return item
        if str(item.get("plan_id") or "") == target_id:
            return item
    return None


def _find_history_snippet(state: "AgentState", context_id: str) -> Optional[dict]:
    layer3 = state.get("layer3_memory") or {}
    summaries = layer3.get("conversation_summaries") or []
    target_id = str(context_id or "").strip()
    if not target_id:
        return None
    if target_id.isdigit():
        idx = int(target_id)
        if 0 <= idx < len(summaries):
            return summaries[idx]
    for item in summaries:
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") == target_id:
            return item
    return None


def _build_bound_context_index(bound_contexts: list[dict]) -> list[dict]:
    payload = []
    for ctx in bound_contexts:
        if not isinstance(ctx, dict):
            continue
        payload.append({
            "id": ctx.get("id", ""),
            "title": ctx.get("title", ""),
            "type": ctx.get("type", ""),
            "expire_at": ctx.get("expire_at", ""),
        })
    return payload


def _sort_by_bound_at(contexts: list[dict]) -> list[dict]:
    def _key(ctx: dict) -> str:
        return str(ctx.get("bound_at") or "")
    return sorted(contexts, key=_key)


def _bind_context(
    state: "AgentState",
    context_type: str,
    title: str,
    content_md: str,
    ref_id: Optional[str],
    expire_at: Optional[str],
    agent_name: str,
) -> tuple[dict, dict]:
    task_list = get_task_list_for_agent(state, agent_name)
    active_task = get_active_task(task_list)
    if not active_task:
        return {}, json.loads(tool_error_response("当前没有活跃任务"))

    bound_contexts = list(active_task.get("bound_contexts", []) or [])
    updated = False
    existing_idx = None
    if ref_id:
        for i, ctx in enumerate(bound_contexts):
            if ctx.get("ref_id") == ref_id and ctx.get("type") == context_type:
                existing_idx = i
                updated = True
                break

    type_limit = BOUND_CONTEXT_LIMITS.get(context_type, BOUND_CONTEXT_LIMITS.get("default", 3))
    type_count = sum(1 for ctx in bound_contexts if ctx.get("type") == context_type)
    evicted = None

    new_context = create_bound_context(
        context_type=context_type,
        title=title,
        content_md=content_md,
        ref_id=ref_id,
        expire_at=expire_at,
        source="tool:context_loader",
    )
    if existing_idx is not None:
        bound_contexts[existing_idx] = new_context
    else:
        bound_contexts.append(new_context)
        if type_count >= type_limit:
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

    result = {
        "success": True,
        "action": "bind",
        "message": f"已绑定上下文 '{title}'",
        "context": {
            "id": new_context.get("id", ""),
            "title": title,
            "type": context_type,
        },
        "bound_to_task": active_task.get("task_id", ""),
        "updated": updated,
        "bound_contexts_index": _build_bound_context_index(bound_contexts),
    }
    if evicted:
        result["evicted"] = {
            "context_id": evicted.get("id", ""),
            "title": evicted.get("title", ""),
            "reason": f"超过 type={context_type} 上限 {type_limit}，已淘汰最早绑定的上下文",
        }
    return {"layer3_memory": layer3_memory}, result


def _unbind_context(
    state: "AgentState",
    context_id: str,
    agent_name: str,
) -> tuple[dict, dict]:
    task_list = get_task_list_for_agent(state, agent_name)
    active_task = get_active_task(task_list)
    if not active_task:
        return {}, json.loads(tool_error_response("当前没有活跃任务"))

    bound_contexts = list(active_task.get("bound_contexts", []) or [])
    new_contexts = [c for c in bound_contexts if c.get("id") != context_id]
    if len(new_contexts) == len(bound_contexts):
        return {}, json.loads(tool_error_response(
            f"未找到 context_id={context_id}",
            {"available_ids": [c.get("id") for c in bound_contexts]},
        ))

    active_task["bound_contexts"] = new_contexts
    for i, task in enumerate(task_list):
        if task.get("task_id") == active_task.get("task_id"):
            task_list[i] = active_task
            break

    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()

    return {"layer3_memory": layer3_memory}, {
        "success": True,
        "action": "unbind",
        "message": f"已解绑 context_id={context_id}",
        "bound_to_task": active_task.get("task_id", ""),
        "bound_contexts_index": _build_bound_context_index(new_contexts),
    }


def _refresh_context(
    state: "AgentState",
    context_id: str,
    expire_at: Optional[str],
    agent_name: str,
) -> tuple[dict, dict]:
    task_list = get_task_list_for_agent(state, agent_name)
    active_task = get_active_task(task_list)
    if not active_task:
        return {}, json.loads(tool_error_response("当前没有活跃任务"))

    bound_contexts = list(active_task.get("bound_contexts", []) or [])
    updated = False
    for ctx in bound_contexts:
        if ctx.get("id") == context_id:
            ctx["bound_at"] = datetime.now().isoformat()
            if expire_at is not None:
                ctx["expire_at"] = expire_at
            updated = True
            break

    if not updated:
        return {}, json.loads(tool_error_response(
            f"未找到 context_id={context_id}",
            {"available_ids": [c.get("id") for c in bound_contexts]},
        ))

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

    return {"layer3_memory": layer3_memory}, {
        "success": True,
        "action": "refresh",
        "message": f"已刷新 context_id={context_id}",
        "bound_to_task": active_task.get("task_id", ""),
        "bound_contexts_index": _build_bound_context_index(bound_contexts),
    }


def _load_context(
    state: "AgentState",
    context_type: str,
    context_id: str,
) -> tuple[Optional[dict], Optional[str]]:
    if context_type == "action_guide":
        guide = _find_action_guide(state, context_id)
        if not guide:
            return None, None
        guide_id = str(guide.get("id") or "")
        title = guide.get("title") or (guide.get("guide") or {}).get("current_task") or "未命名指南"
        return {
            "id": guide_id,
            "title": title,
            "type": context_type,
            "ref_id": guide_id,
        }, _build_guide_detail_md(guide)

    if context_type == "status_report":
        report = _find_status_report(state, context_id)
        if not report:
            return None, None
        title = f"现状分析报告{report.get('report_id', '')}".strip() or "现状分析报告"
        content = report.get("report_content") or ""
        return {
            "id": report.get("id", ""),
            "title": title,
            "type": context_type,
            "ref_id": str(report.get("report_id") or report.get("id") or ""),
        }, content

    if context_type == "action_plan":
        plan = _find_action_plan(state, context_id)
        if not plan:
            return None, None
        title = f"行动规划{plan.get('plan_id', '')}".strip() or "行动规划"
        content = plan.get("plan_content") or ""
        return {
            "id": plan.get("id", ""),
            "title": title,
            "type": context_type,
            "ref_id": str(plan.get("plan_id") or plan.get("id") or ""),
        }, content

    if context_type == "history_snippet":
        snippet = _find_history_snippet(state, context_id)
        if not snippet:
            return None, None
        title = snippet.get("topics") or "历史摘要"
        content = snippet.get("summary") or ""
        return {
            "id": snippet.get("id", ""),
            "title": title,
            "type": context_type,
            "ref_id": snippet.get("id", ""),
        }, content

    if context_type == "crush_chat":
        storage = state.get("crush_chat_storage") or {}
        content = storage.get("summary") or storage.get("metadata") or ""
        content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content)
        if not content_str:
            return None, None
        return {
            "id": context_id or "crush_chat",
            "title": "Crush 聊天记录",
            "type": context_type,
            "ref_id": context_id or "crush_chat",
        }, content_str

    if context_type == "custom":
        return None, None

    return None, None


def create_context_loader(state_getter: Callable[[], "AgentState"], agent_name: str = "main_agent"):
    @tool(args_schema=ContextLoaderInput)
    def context_loader(
        action: str,
        context_type: str,
        context_id: str,
        expire_at: str = "",
    ) -> str:
        """
        上下文加载/绑定工具。
        - load: 仅查看内容，不绑定到任务（一次性使用）
        - bind: 绑定到当前任务，后续轮次自动注入（跨轮次使用）
        - unbind: 解除绑定
        - refresh: 刷新过期时间

        强规则：只看一眼用 load，跨轮次复用才 bind。
        """
        state = state_getter() or {}
        if action == "unbind":
            _, result = _unbind_context(state, context_id, agent_name)
            return json.dumps(result, ensure_ascii=False)

        if action == "refresh":
            _, result = _refresh_context(state, context_id, expire_at or None, agent_name)
            return json.dumps(result, ensure_ascii=False)

        context_meta, content_md = _load_context(state, context_type, context_id)
        if not context_meta or not content_md:
            return tool_error_response("未找到对应上下文")

        if action == "load":
            result = {
                "success": True,
                "action": "load",
                "message": "已加载上下文",
                "context": context_meta,
                "content_md": content_md,
            }
            return json.dumps(result, ensure_ascii=False)

        if action == "bind":
            state_update, result = _bind_context(
                state,
                context_type,
                context_meta.get("title", ""),
                content_md,
                context_meta.get("ref_id"),
                expire_at or None,
                agent_name,
            )
            if state_update:
                for key, value in state_update.items():
                    state[key] = value
            result["content_md"] = content_md
            return json.dumps(result, ensure_ascii=False)

        return tool_error_response(f"不支持的 action: {action}")

    return context_loader


def apply_context_loader_state_update(
    state: "AgentState",
    tool_name: str,
    tool_args: dict,
    agent_name: str = "main_agent",
) -> dict:
    if tool_name != "context_loader":
        return {}

    action = tool_args.get("action", "")
    if action == "bind":
        context_type = tool_args.get("context_type", "")
        context_id = tool_args.get("context_id", "")
        expire_at = tool_args.get("expire_at") or None
        context_meta, content_md = _load_context(state, context_type, context_id)
        if not context_meta or not content_md:
            return {}
        state_update, _ = _bind_context(
            state,
            context_type,
            context_meta.get("title", ""),
            content_md,
            context_meta.get("ref_id"),
            expire_at,
            agent_name,
        )
        return state_update

    if action == "unbind":
        state_update, _ = _unbind_context(state, tool_args.get("context_id", ""), agent_name)
        return state_update

    if action == "refresh":
        state_update, _ = _refresh_context(
            state,
            tool_args.get("context_id", ""),
            tool_args.get("expire_at") or None,
            agent_name,
        )
        return state_update

    return {}
