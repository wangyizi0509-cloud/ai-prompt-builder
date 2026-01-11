"""
Onboarding 子图：用于首次信息收集。

采用 LangGraph 官方推荐的 Subgraph + interrupt 模式：
- 独立 StateGraph，作为主图的一个节点
- 单节点循环，通过 Command(goto="onboarding_agent") 自己回到自己
"""

from langgraph.graph import StateGraph, START, END

from graph.state import AgentState
from onboarding.onboarding_agent import onboarding_agent_node


def create_onboarding_workflow() -> StateGraph:
    """创建并返回 Onboarding 子图（未编译）。"""
    builder = StateGraph(AgentState)
    builder.add_node("onboarding_agent", onboarding_agent_node)
    builder.add_edge(START, "onboarding_agent")
    builder.add_edge("onboarding_agent", END)
    return builder


def compile_onboarding_workflow():
    """编译后的 Onboarding 子图，供主图引用。"""
    return create_onboarding_workflow().compile()

