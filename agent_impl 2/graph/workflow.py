"""
LangGraph 工作流编排
定义 Agent 之间的调用关系和状态流转

架构说明：
- 主 Agent 是决策中枢，负责协调子 Agent
- 主 Agent 和子 Agent 都可以通过「提问 Skill」向用户提问
- 所有 Agent 提问后会暂停，用户回答后从 resume_point 恢复执行
- wait_user_input 节点负责等待用户输入并路由到正确的 Agent
- 主 Agent 可以使用咨询 Skills 直接回复用户

渐进式加载机制（Tool-based）：
- Agent 可以通过 load_skill_instructions 工具按需加载技能指令
- skill_tools 节点负责执行工具调用
- 工具执行完成后自动返回调用它的 Agent
"""

from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from graph.state import AgentState
from graph.nodes.router import router_node
from graph.nodes.main_agent import main_agent_node
from graph.nodes.status_agent import status_agent_node
from graph.nodes.plan_agent import plan_agent_node
from graph.nodes.guide_agent import guide_agent_node
from skills import load_skill_instructions


def route_after_router(state: AgentState) -> Literal["main_agent", "status_agent", "plan_agent", "guide_agent", "end"]:
    """
    路由节点后的条件路由
    
    如果有 current_agent 说明需要恢复之前的 Agent 执行
    支持主 Agent 和所有子 Agent 的恢复
    """
    route_to = state.get("route_to", "main_agent")
    if route_to == "end":
        return "end"
    
    # 检查是否需要恢复之前的 Agent（包括主 Agent）
    current_agent = state.get("current_agent")
    if current_agent and state.get("agent_resume_point"):
        # 直接返回需要恢复的 Agent
        if current_agent == "main_agent":
            return "main_agent"  # 新增：支持主 Agent 恢复
        elif current_agent == "status_agent":
            return "status_agent"
        elif current_agent == "plan_agent":
            return "plan_agent"
        elif current_agent == "guide_agent":
            return "guide_agent"
    
    return "main_agent"


def _has_tool_calls(state: AgentState) -> bool:
    """
    检查最后一条消息是否包含 tool_calls
    
    用于判断 Agent 是否需要调用工具
    """
    messages = state.get("messages", [])
    if not messages:
        return False
    
    last_message = messages[-1]
    # LangChain 的 AIMessage 有 tool_calls 属性
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return True
    # 兼容字典格式
    if isinstance(last_message, dict) and last_message.get("tool_calls"):
        return True
    
    return False


def route_after_main_agent(state: AgentState) -> Literal["skill_tools", "status_agent", "plan_agent", "guide_agent", "wait_user_input", "end"]:
    """
    主 Agent 后的条件路由
    根据 next_action 决定下一步
    
    优先级：
    1. 如果有 tool_calls，先执行工具
    2. 根据 next_action 路由
    """
    # 优先检查是否有工具调用
    if _has_tool_calls(state):
        return "skill_tools"
    
    next_action = state.get("next_action", "end_turn")
    
    if next_action == "call_status":
        return "status_agent"
    elif next_action == "call_plan":
        return "plan_agent"
    elif next_action == "call_guide":
        return "guide_agent"
    elif next_action == "ask_user":
        # 主 Agent 需要提问，走 wait_user_input（跟子 Agent 一致）
        return "wait_user_input"
    else:
        # end_turn 结束本轮
        return "end"


def route_after_sub_agent(state: AgentState) -> Literal["skill_tools", "main_agent", "wait_user_input"]:
    """
    子 Agent（status/plan/guide）后的统一路由
    
    优先级：
    1. 如果有 tool_calls，先执行工具
    2. 如果子 Agent 设置了 current_agent（需要提问），则等待用户输入
    3. 如果子 Agent 完成了任务，则返回主 Agent 再决策
    """
    # 优先检查是否有工具调用
    if _has_tool_calls(state):
        return "skill_tools"
    
    # 如果有待回答的问题，等待用户输入
    if state.get("current_agent") and state.get("agent_resume_point"):
        return "wait_user_input"
    
    # 任务完成，返回主 Agent 进行再决策
    return "main_agent"


def route_after_skill_tools(state: AgentState) -> Literal["main_agent", "status_agent", "plan_agent", "guide_agent"]:
    """
    skill_tools 节点执行完成后的路由
    
    返回到调用工具的 Agent，让它继续处理
    通过 _tool_caller 状态字段跟踪是哪个 Agent 发起的调用
    """
    tool_caller = state.get("_tool_caller", "main_agent")
    
    if tool_caller == "status_agent":
        return "status_agent"
    elif tool_caller == "plan_agent":
        return "plan_agent"
    elif tool_caller == "guide_agent":
        return "guide_agent"
    else:
        return "main_agent"


def wait_user_input_node(state: AgentState) -> dict:
    """
    等待用户输入节点
    
    这是一个「暂停点」，工作流在这里结束本轮执行
    用户回答后，新的一轮会通过 router 的 resume_agent 路由到正确的 Agent
    """
    # 这个节点不做任何处理，只是标记工作流需要等待用户输入
    return {
        "debug_log": [{
            "node": "wait_user_input",
            "step": "Waiting for user input",
            "current_agent": state.get("current_agent"),
            "resume_point": state.get("agent_resume_point"),
        }]
    }


# 创建 Skill 工具节点（全局复用）
_skill_tools_node = ToolNode([load_skill_instructions])


def skill_tools_node(state: AgentState) -> dict:
    """
    Skill 工具执行节点
    
    执行 Agent 发起的工具调用，并记录调用来源以便返回
    """
    # 记录是哪个 Agent 发起的工具调用
    current_agent = state.get("current_agent")
    tool_caller = current_agent if current_agent else "main_agent"
    
    # 调用 ToolNode 执行工具
    result = _skill_tools_node.invoke(state)
    
    # 添加调用来源标记
    result["_tool_caller"] = tool_caller
    
    # 添加调试日志
    result["debug_log"] = [{
        "node": "skill_tools",
        "step": "Executed skill tool",
        "tool_caller": tool_caller,
        "messages_added": len(result.get("messages", [])),
    }]
    
    return result


def create_workflow() -> StateGraph:
    """
    创建 LangGraph 工作流
    
    工作流结构（Tool-based 渐进式加载版）：
    
    [用户输入] 
         │
         ▼
    [Router] ─── 风控/闲聊 ───→ [END]
         │
         ├── 有 current_agent ───→ [恢复对应 Agent]（包括主 Agent）
         │
         │ 无 current_agent
         ▼
    [Main Agent] ─── end_turn ───→ [END]
         │
         ├── tool_calls ──→ [Skill Tools] ──→ [Main Agent] (循环)
         │
         ├── ask_user ────→ [Wait User Input] → [END]
         │                  (下轮从 Router 恢复到 Main Agent)
         │
         ├── call_status ──→ [Status Agent] ──┐
         ├── call_plan ────→ [Plan Agent] ───┼──→ [tool_calls?]
         └── call_guide ───→ [Guide Agent] ──┘        │
                                                      ├── 是 → [Skill Tools] → [回到调用者]
                                                      ├── 需要提问 → [Wait User Input] → [END]
                                                      └── 完成 → [Main Agent] (再决策)
    
    Returns:
        编译后的 LangGraph 工作流
    """
    # 创建状态图
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("router", router_node)
    workflow.add_node("main_agent", main_agent_node)
    workflow.add_node("status_agent", status_agent_node)
    workflow.add_node("plan_agent", plan_agent_node)
    workflow.add_node("guide_agent", guide_agent_node)
    workflow.add_node("wait_user_input", wait_user_input_node)
    workflow.add_node("skill_tools", skill_tools_node)  # 新增：Skill 工具节点
    
    # 设置入口点
    workflow.set_entry_point("router")
    
    # Router 后的路由：可能直接到主 Agent，也可能恢复之前的 Agent
    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {
            "main_agent": "main_agent",
            "status_agent": "status_agent",
            "plan_agent": "plan_agent",
            "guide_agent": "guide_agent",
            "end": END,
        }
    )
    
    # 主 Agent 后的路由（新增 skill_tools 支持）
    workflow.add_conditional_edges(
        "main_agent",
        route_after_main_agent,
        {
            "skill_tools": "skill_tools",  # 新增：工具调用
            "status_agent": "status_agent",
            "plan_agent": "plan_agent",
            "guide_agent": "guide_agent",
            "wait_user_input": "wait_user_input",
            "end": END,
        }
    )
    
    # 子 Agent 后的统一路由：工具调用 / 等待用户输入 / 回主 Agent
    workflow.add_conditional_edges(
        "status_agent",
        route_after_sub_agent,
        {
            "skill_tools": "skill_tools",  # 新增：工具调用
            "main_agent": "main_agent",
            "wait_user_input": "wait_user_input",
        }
    )
    
    workflow.add_conditional_edges(
        "plan_agent",
        route_after_sub_agent,
        {
            "skill_tools": "skill_tools",  # 新增：工具调用
            "main_agent": "main_agent",
            "wait_user_input": "wait_user_input",
        }
    )
    
    workflow.add_conditional_edges(
        "guide_agent",
        route_after_sub_agent,
        {
            "skill_tools": "skill_tools",  # 新增：工具调用
            "main_agent": "main_agent",
            "wait_user_input": "wait_user_input",
        }
    )
    
    # skill_tools 执行完成后，返回到调用它的 Agent
    workflow.add_conditional_edges(
        "skill_tools",
        route_after_skill_tools,
        {
            "main_agent": "main_agent",
            "status_agent": "status_agent",
            "plan_agent": "plan_agent",
            "guide_agent": "guide_agent",
        }
    )
    
    # wait_user_input 直接结束本轮
    workflow.add_edge("wait_user_input", END)
    
    return workflow


def compile_workflow():
    """
    编译工作流
    
    Returns:
        可执行的工作流实例
    """
    workflow = create_workflow()
    return workflow.compile()


# 创建全局工作流实例
_compiled_workflow = None


def get_workflow():
    """获取编译后的工作流（单例模式）"""
    global _compiled_workflow
    if _compiled_workflow is None:
        _compiled_workflow = compile_workflow()
    return _compiled_workflow

