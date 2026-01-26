"""
子 Agent 委派工具 (Delegate Tools)
用于通过工具调用触发状态机切换（handoff）。

[FIX] 2026-01-26: 简化 handoff 消息，只包含最小路由信息
- instruction 通过 state.instruction 传递，不在 tool message 中重复
- 避免消息历史中 instruction 出现两次（tool message + dossier XML）
"""

import json
from langchain_core.tools import tool


@tool
def delegate_to_status(instruction: str) -> str:
    """委派给 Status Agent 进行现状分析。"""
    # instruction 通过 state 传递，这里只返回路由信息
    return json.dumps(
        {
            "action": "handoff",
            "target": "status_agent",
        },
        ensure_ascii=False,
    )


@tool
def delegate_to_plan(instruction: str) -> str:
    """委派给 Plan Agent 制定行动规划。"""
    # instruction 通过 state 传递，这里只返回路由信息
    return json.dumps(
        {
            "action": "handoff",
            "target": "plan_agent",
        },
        ensure_ascii=False,
    )


@tool
def delegate_to_guide(instruction: str) -> str:
    """委派给 Guide Agent 生成行动指南。"""
    # instruction 通过 state 传递，这里只返回路由信息
    return json.dumps(
        {
            "action": "handoff",
            "target": "guide_agent",
        },
        ensure_ascii=False,
    )
