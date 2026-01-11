"""
Dispatcher 节点

职责：
- 入口分发：新用户/未完成 Onboarding -> Onboarding 子图；否则 -> Router
- 为未来的特殊流程预留扩展点
"""

from typing import Any

from graph.state import AgentState


def _should_run_onboarding(state: AgentState) -> bool:
    """
    判定是否需要进入 Onboarding：
    - 未标记完成 onboarding_completed
    - 默认认为首次对话（messages 为空或仅 1 条用户消息）需要 Onboarding
    """
    if state.get("onboarding_completed"):
        return False
    messages = state.get("messages", [])
    # 初次进入通常只有一条用户消息；中途追问时也需要继续 Onboarding
    return True if messages else True


def dispatcher_node(state: AgentState) -> dict[str, Any]:
    """
    调度节点：
    - 判断是否走 Onboarding 子图
    - 否则进入现有 router 节点
    """
    go_onboarding = _should_run_onboarding(state)
    route_target = "onboarding" if go_onboarding else "router"

    return {
        "route_to": route_target,
        "debug_log": [{
            "node": "dispatcher",
            "decision": route_target,
            "onboarding_completed": state.get("onboarding_completed", False),
        }],
    }

