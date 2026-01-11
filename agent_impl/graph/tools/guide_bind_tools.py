"""
行动指南绑定工具 (Action Guide Bind Tools)

提供 bind_action_guide_detail 工具，用于：
1. 查询指定行动指南的完整内容
2. 将详情绑定到当前活跃任务的 bound_action_guides 字段
3. 后续轮次自动注入绑定的详情到上下文

设计原则：
- 与现有 load_action_guide_detail 工具兼容（使用相同的 guide_id 格式）
- 绑定后跨轮次持久可见
- 每任务最多绑定 K 篇（FIFO 淘汰）
"""

from __future__ import annotations

import json
from typing import Callable, Any, TYPE_CHECKING, Optional
from datetime import datetime

from langchain.tools import tool

if TYPE_CHECKING:
    from graph.state import AgentState

from graph.context_types import (
    MAX_BOUND_GUIDES_PER_TASK,
    BoundActionGuide,
)
from graph.tools.task_tools import get_task_list_for_agent, get_active_task


# ============================================================
# 工具名称常量
# ============================================================

GUIDE_BIND_TOOL_NAMES = {"bind_action_guide_detail"}


def is_guide_bind_tool(tool_name: str) -> bool:
    """检查是否为行动指南绑定工具"""
    return tool_name in GUIDE_BIND_TOOL_NAMES


# ============================================================
# 核心实现函数
# ============================================================

def _build_guide_detail_md(guide_item: dict) -> str:
    """
    组装指南的完整 Markdown 内容
    
    与 load_action_guide_detail 保持一致的输出格式
    """
    guide = guide_item.get("guide") if isinstance(guide_item.get("guide"), dict) else {}
    guide_id = guide_item.get("id", "")
    title = guide_item.get("title") or guide.get("current_task") or "未命名指南"
    status = guide_item.get("status") or "pending"
    created_at = guide_item.get("created_at") or ""

    # 兼容旧结构：guide_content 可能直接在顶层或在 guide 内
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

    # 降级：结构化字段拼一个简版
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


def bind_action_guide_detail_impl(
    state: "AgentState",
    guide_id: str,
    agent_name: str = "main_agent"
) -> tuple[dict, str]:
    """
    查询指南详情并绑定到当前活跃任务
    
    Args:
        state: 当前状态
        guide_id: 指南唯一 ID（ActionGuideItem.id）
        agent_name: Agent 名称
    
    Returns:
        (状态更新字典, 工具返回消息)
    """
    target_id = str(guide_id or "").strip()
    if not target_id:
        return {}, json.dumps({
            "success": False,
            "error": "guide_id 不能为空",
            "hint": "请传入行动指南的唯一 ID（从上下文表格中复制）",
        }, ensure_ascii=False)

    # 1. 检查是否有活跃任务
    task_list = get_task_list_for_agent(state, agent_name)
    active_task = get_active_task(task_list)
    
    if not active_task:
        return {}, json.dumps({
            "success": False,
            "error": "当前没有活跃任务",
            "hint": "请先调用 create_task 创建任务，或调用 switch_task 切换到已有任务",
        }, ensure_ascii=False)

    # 2. 从 layer2_memory 查找目标指南
    layer2 = state.get("layer2_memory") or {}
    guides = layer2.get("all_action_guides") or state.get("action_guides") or []
    
    target_guide = None
    for g in guides:
        if not isinstance(g, dict):
            continue
        if str(g.get("id") or "") == target_id:
            target_guide = g
            break
    
    if not target_guide:
        return {}, json.dumps({
            "success": False,
            "error": f"未找到 ID 为 '{target_id}' 的指南",
            "hint": "请检查上下文表格中的 ID 是否正确",
        }, ensure_ascii=False)

    # 3. 组装 Markdown 内容
    content_md = _build_guide_detail_md(target_guide)
    guide = target_guide.get("guide") if isinstance(target_guide.get("guide"), dict) else {}
    title = target_guide.get("title") or guide.get("current_task") or "未命名指南"
    status = target_guide.get("status") or "pending"

    # 4. 检查是否已绑定（覆盖策略）
    bound_guides = list(active_task.get("bound_action_guides", []) or [])
    updated = False
    existing_idx = None
    
    for i, bg in enumerate(bound_guides):
        if bg.get("guide_id") == target_id:
            existing_idx = i
            updated = True
            break

    # 5. 创建绑定记录
    new_bound_guide = BoundActionGuide(
        guide_id=target_id,
        title=title,
        status=status,
        content_md=content_md,
        bound_at=datetime.now().isoformat(),
        source="bind_action_guide_detail",
    )

    # 6. 更新绑定列表
    evicted = None
    if existing_idx is not None:
        # 覆盖已存在的绑定
        bound_guides[existing_idx] = new_bound_guide
    else:
        # 新增绑定
        if len(bound_guides) >= MAX_BOUND_GUIDES_PER_TASK:
            # FIFO 淘汰最早绑定的
            evicted = bound_guides.pop(0)
        bound_guides.append(new_bound_guide)

    # 7. 更新任务状态
    active_task["bound_action_guides"] = bound_guides
    
    # 更新任务列表中的任务
    for i, task in enumerate(task_list):
        if task.get("task_id") == active_task.get("task_id"):
            task_list[i] = active_task
            break

    # 8. 构建状态更新
    layer3_memory = dict(state.get("layer3_memory", {}) or {})
    task_registry = dict(layer3_memory.get("task_registry", {}) or {})
    task_registry[agent_name] = task_list
    layer3_memory["task_registry"] = task_registry
    layer3_memory["last_updated"] = datetime.now().isoformat()
    
    state_update = {"layer3_memory": layer3_memory}

    # 9. 构建返回结果
    bound_index = [
        {"guide_id": bg.get("guide_id", ""), "title": bg.get("title", ""), "status": bg.get("status", "")}
        for bg in bound_guides
    ]
    
    result = {
        "success": True,
        "guide_detail_md": content_md,
        "bound_to_task_id": active_task.get("task_id", ""),
        "updated": updated,
        "bound_action_guides_index": bound_index,
    }
    
    if evicted:
        result["evicted"] = {
            "guide_id": evicted.get("guide_id", ""),
            "title": evicted.get("title", ""),
            "reason": f"超过上限 {MAX_BOUND_GUIDES_PER_TASK} 篇，已淘汰最早绑定的指南",
        }

    return state_update, json.dumps(result, ensure_ascii=False)


# ============================================================
# LangChain Tool 定义
# ============================================================

def create_guide_bind_tool(state_getter: Callable[[], "AgentState"], agent_name: str = "main_agent"):
    """
    创建带状态访问能力的 bind_action_guide_detail 工具
    
    Args:
        state_getter: 一个函数，调用时返回当前 state（dict）
        agent_name: Agent 名称
    """

    @tool
    def bind_action_guide_detail(guide_id: str) -> str:
        """
        查询指定行动指南的完整内容，并绑定到当前活跃任务。
        
        绑定后，该指南的完整内容将在后续轮次自动注入上下文，
        直到切换任务或手动解绑。
        
        使用场景：
        - 当上下文中只看到某条指南的摘要/元数据（表格里有 ID）
        - 需要查看并持续参考该指南的完整步骤和内容
        
        注意：每个任务最多绑定 3 篇指南，超出时会淘汰最早绑定的。
        
        Args:
            guide_id: 指南唯一 ID（从上下文表格中的 ID 列复制，如 'a1b2c3d4'）
        
        Returns:
            JSON 格式结果，包含：
            - success: 是否成功
            - guide_detail_md: 完整的 Markdown 格式指南内容
            - bound_to_task_id: 绑定到的任务 ID
            - updated: 是否为覆盖更新
            - bound_action_guides_index: 当前任务已绑定的指南列表
            - evicted: (可选) 被淘汰的指南信息
        """
        state = state_getter() or {}
        _, result = bind_action_guide_detail_impl(state, guide_id, agent_name)
        return result

    return bind_action_guide_detail


# ============================================================
# 状态更新辅助函数（供 workflow 使用）
# ============================================================

def apply_guide_bind_state_update(
    state: "AgentState",
    tool_name: str,
    tool_args: dict,
    agent_name: str = "main_agent"
) -> dict:
    """
    应用行动指南绑定工具的状态更新
    
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
    if tool_name == "bind_action_guide_detail":
        state_update, _ = bind_action_guide_detail_impl(
            state,
            tool_args.get("guide_id", ""),
            agent_name
        )
        return state_update
    
    return {}
