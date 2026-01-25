"""
子 Agent 委派工具 (Delegate Tools)
用于通过工具调用触发状态机切换（handoff）。
"""

import json
from langchain_core.tools import tool


@tool
def delegate_to_status(instruction: str) -> str:
    """委派给 Status Agent 进行现状分析。"""
    return json.dumps(
        {
            "action": "handoff",
            "target": "status_agent",
            "instruction": instruction,
        },
        ensure_ascii=False,
    )


@tool
def delegate_to_plan(instruction: str) -> str:
    """委派给 Plan Agent 制定行动规划。"""
    return json.dumps(
        {
            "action": "handoff",
            "target": "plan_agent",
            "instruction": instruction,
        },
        ensure_ascii=False,
    )


@tool
def delegate_to_guide(instruction: str) -> str:
    """委派给 Guide Agent 生成行动指南。"""
    return json.dumps(
        {
            "action": "handoff",
            "target": "guide_agent",
            "instruction": instruction,
        },
        ensure_ascii=False,
    )
