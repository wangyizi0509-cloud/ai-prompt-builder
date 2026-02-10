from __future__ import annotations

from typing import Callable, Literal

from langchain_core.tools import BaseTool

from graph.tools.ask_human import ask_human
from graph.tools.context_loader import create_context_loader
from graph.tools.submit_tools import (
    submit_action_guide,
    submit_action_plan,
    submit_status_report,
    update_guide_content,
    update_guide_status,
    return_to_main,
)
from graph.tools.task_tools import create_task_tools
from skills import create_all_skills_loader, create_inquiry_only_loader


def _role_to_agent_name(role: str) -> str:
    role = (role or "").strip().lower()
    if role in {"main", "main_agent"}:
        return "main_agent"
    if role in {"status", "status_agent"}:
        return "status_agent"
    if role in {"plan", "plan_agent"}:
        return "plan_agent"
    if role in {"guide", "guide_agent"}:
        return "guide_agent"
    return role or "main_agent"


def build_all_tools_for_agent(
    role: Literal["main", "status", "plan", "guide"],
    *,
    state_getter: Callable[[], dict] | None = None,
) -> list[BaseTool]:
    agent_name = _role_to_agent_name(role)
    getter = state_getter or (lambda: {})

    skill_loader = create_all_skills_loader() if role == "main" else create_inquiry_only_loader()
    task_tools = create_task_tools(getter, agent_name=agent_name) if role == "main" else []
    context_loader = create_context_loader(getter, agent_name)

    tools: list[BaseTool] = [
        skill_loader,
        ask_human,
        context_loader,
        *task_tools,
        submit_status_report,
        submit_action_plan,
        submit_action_guide,
        update_guide_status,
        update_guide_content,
        return_to_main,
    ]
    return tools
