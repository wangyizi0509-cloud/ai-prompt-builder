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
- Agent 可以通过专用工具（如 load_inquiry_skill_instructions）按需加载技能指令
- skill_tools 节点负责执行工具调用
- 工具执行完成后自动返回调用它的 Agent

v2.1 更新：
- 添加 Checkpointer 支持（使用 MemorySaver）
"""

from typing import Literal, Optional
import os
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from graph.state import AgentState
from graph.state import convert_message_to_dict
from graph.nodes.router import router_node
from graph.nodes.main_agent import main_agent_node
from graph.nodes.status_agent import status_agent_node
from graph.nodes.plan_agent import plan_agent_node
from graph.nodes.guide_agent import guide_agent_node
from graph.nodes.finalizer import post_turn_finalize_node
from onboarding.workflow import compile_onboarding_workflow
from skills import (
    load_inquiry_skill_instructions,
    load_consult_answer_skill_instructions,
    load_emotion_support_skill_instructions
)
from skills.guide_loader import create_guide_loader_tool
from graph.tools.task_tools import (
    create_task_tools,
    apply_task_tool_state_update,
    is_task_tool,
)
from graph.tools.guide_bind_tools import (
    create_guide_bind_tool,
    apply_guide_bind_state_update,
    is_guide_bind_tool,
)

MAX_NODE_STEPS_PER_TURN = 18  # 单次 /api/chat invoke 内允许的最大节点步数（防止死循环）


def _wrap_step_counter(node_name: str, fn):
    """
    给节点函数加一个“单轮步数计数器”，用于防止 LangGraph 在单次 invoke 内转圈。
    - 计数器在 server.py 每次 /api/chat 开始时归零
    - 每执行一个节点就 +1
    """

    def _wrapped(state: AgentState) -> dict:
        out = fn(state) or {}
        if not isinstance(out, dict):
            out = {}
        # [FIX] 优先使用节点返回的 _iteration_count（支持 Router 重置），否则从 state 读取
        if "_iteration_count" in out:
            # 节点显式设置了值（如 Router 重置为 0），从该值 +1 开始计数
            curr = int(out.get("_iteration_count", 0) or 0) + 1
        else:
            # 节点未设置，从 state 读取并 +1
            curr = int(state.get("_iteration_count", 0) or 0) + 1
        out["_iteration_count"] = curr
        # 轻量 debug 记录，方便定位循环链路（不会爆炸）
        dbg = out.get("debug_log")
        if isinstance(dbg, list):
            dbg.append({"node": "workflow", "step": "StepCounter", "at": node_name, "iteration": curr})
        return out

    return _wrapped


def route_after_router(state: AgentState) -> Literal["onboarding", "main_agent", "status_agent", "plan_agent", "guide_agent", "end"]:
    """
    路由节点后的条件路由
    
    如果有 current_agent 说明需要恢复之前的 Agent 执行
    支持主 Agent 和所有子 Agent 的恢复
    """
    # 防止无限循环
    iteration = int(state.get("_iteration_count", 0) or 0)
    if iteration >= MAX_NODE_STEPS_PER_TURN:
        print("[WARN] Max node steps reached, forcing end")
        return "end"

    route_to = state.get("route_to", "main_agent")
    if route_to == "end":
        return "end"
    if route_to == "onboarding":
        return "onboarding"
    
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


def route_after_onboarding(state: AgentState) -> Literal["router", "end"]:
    """
    Onboarding 子图完成后：
    - 如果 onboarding_completed=False（需要用户回答），本轮结束
    - 如果 onboarding_completed=True，进入 router，再由 router 分发到主 Agent
    """
    if state.get("onboarding_completed", False):
        return "router"
    return "end"


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


def route_after_main_agent(state: AgentState) -> Literal["skill_tools", "status_agent", "plan_agent", "guide_agent", "end"]:
    """
    主 Agent 后的条件路由
    根据 next_action 决定下一步
    
    优先级：
    1. 如果有 tool_calls，先执行工具
    2. 根据 next_action 路由
    """
    iteration = int(state.get("_iteration_count", 0) or 0)
    if iteration >= MAX_NODE_STEPS_PER_TURN:
        print("[WARN] Max node steps reached after main_agent, forcing end")
        return "end"

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
        # 主 Agent 需要提问，但使用了 interrupt 机制，
        # 如果代码走到这里，说明 interrupt 已经完成或被绕过，
        # 且 Agent 显式返回了 ask_user（可能是为了结束这一轮 invoke）
        return "end"
    else:
        # end_turn 结束本轮
        return "end"


def route_after_sub_agent(state: AgentState) -> Literal["skill_tools", "main_agent", "end"]:
    """
    子 Agent（status/plan/guide）后的统一路由
    
    优先级：
    1. 如果有 tool_calls，先执行工具
    2. 如果子 Agent 设置了 current_agent（需要提问），则等待用户输入
    3. 如果子 Agent 完成了任务，则返回主 Agent 再决策
    """
    iteration = int(state.get("_iteration_count", 0) or 0)
    if iteration >= MAX_NODE_STEPS_PER_TURN:
        print("[WARN] Max node steps reached after sub_agent, forcing end")
        return "end"

    # 优先检查是否有工具调用
    if _has_tool_calls(state):
        return "skill_tools"
    
    # 如果有待回答的问题，使用 interrupt 机制，这里直接结束
    if state.get("current_agent") and state.get("agent_resume_point"):
        return "end"
    
    # 任务完成，返回主 Agent 进行再决策
    return "main_agent"


def route_after_guide_agent(state: AgentState) -> Literal["skill_tools", "main_agent", "end"]:
    """
    Guide Agent 后的路由（与其他子 Agent 对齐）：

    优先级：
    1. 如果有 tool_calls，先执行工具
    2. 如果 guide_agent 设置了 current_agent（需要提问/等待用户输入），本轮结束（下轮从 Router 恢复）
    3. 否则视为任务完成，回到 main_agent 统一再决策（是否继续下一步 / 是否结束本轮）
    """
    return route_after_sub_agent(state)


def route_after_skill_tools(state: AgentState) -> Literal["main_agent", "status_agent", "plan_agent", "guide_agent"]:
    """
    skill_tools 节点执行完成后的路由
    
    返回到调用工具的 Agent，让它继续处理
    """
    iteration = int(state.get("_iteration_count", 0) or 0)
    if iteration >= MAX_NODE_STEPS_PER_TURN:
        # 兜底：工具已执行但本轮步数过多，直接回主 Agent 收口（由 main_agent end_turn）
        print("[WARN] Max node steps reached after skill_tools, returning to main_agent")
        return "main_agent"

    current_agent = state.get("current_agent", "main_agent")
    
    if current_agent == "status_agent":
        return "status_agent"
    elif current_agent == "plan_agent":
        return "plan_agent"
    elif current_agent == "guide_agent":
        return "guide_agent"
    else:
        return "main_agent"


def skill_tools_node(state: AgentState) -> dict:
    """
    Skill 工具执行节点
    执行工具，并处理任务工具的状态更新
    """
    # 说明：tool 输出不会写入对话历史（见 context_builder），因此需要保证工具执行后能在"二阶段"被对应 Agent 注入。
    # 其中 load_action_guide_detail 需要访问当前 state，故在此处用闭包动态创建。
    
    # 获取当前 Agent 名称（用于任务工具）
    current_agent = state.get("current_agent", "main_agent")
    
    # 创建任务工具
    task_tools = create_task_tools(lambda: state, agent_name=current_agent)
    
    tool_node = ToolNode([
        load_inquiry_skill_instructions,
        load_consult_answer_skill_instructions,
        load_emotion_support_skill_instructions,
        create_guide_loader_tool(lambda: state),
        # 行动指南绑定工具
        create_guide_bind_tool(lambda: state, current_agent),
        # 任务管理工具
        *task_tools,
    ])
    out = tool_node.invoke(state)
    
    # 检查是否调用了任务工具或行动指南绑定工具，如果是则应用状态更新
    messages = state.get("messages", [])
    for msg in reversed(messages):
        tool_calls = getattr(msg, "tool_calls", None) or (msg.get("tool_calls") if isinstance(msg, dict) else None)
        if tool_calls:
            for tc in tool_calls:
                tool_name = tc.get("name", "") if isinstance(tc, dict) else ""
                tool_args = tc.get("args", {}) if isinstance(tc, dict) else {}
                
                if is_task_tool(tool_name):
                    # 应用任务工具的状态更新
                    task_state_update = apply_task_tool_state_update(state, tool_name, tool_args, current_agent)
                    if task_state_update:
                        # 合并状态更新
                        for key, value in task_state_update.items():
                            out[key] = value
                        print(f"[DEBUG] skill_tools_node: Applied task tool state update for {tool_name}")
                
                elif is_guide_bind_tool(tool_name):
                    # 应用行动指南绑定工具的状态更新
                    bind_state_update = apply_guide_bind_state_update(state, tool_name, tool_args, current_agent)
                    if bind_state_update:
                        # 合并状态更新
                        for key, value in bind_state_update.items():
                            out[key] = value
                        print(f"[DEBUG] skill_tools_node: Applied guide bind state update for {tool_name}")
            break

    # 兼容：确保 tool 消息具备 tool_call_id（LangChain ToolMessage 必填，且不能为 None/空）
    # 在某些模式下，ToolNode 可能返回 dict 形式的消息；若缺 tool_call_id，会导致 add_messages 合并报错。
    msgs = out.get("messages", [])
    if not msgs:
        return out

    # 尝试从上一条 AIMessage 的 tool_calls 中取回 tool_call_id（若需要兜底）
    fallback_tool_call_id = ""
    for m in reversed(state.get("messages", []) or []):
        # LangChain AIMessage
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            try:
                fallback_tool_call_id = str(tool_calls[0].get("id") or "")
            except Exception:
                fallback_tool_call_id = ""
            break
        # dict 形式
        if isinstance(m, dict) and m.get("tool_calls"):
            try:
                fallback_tool_call_id = str(m["tool_calls"][0].get("id") or "")
            except Exception:
                fallback_tool_call_id = ""
            break

    normalized = []
    for m in msgs:
        md = convert_message_to_dict(m)
        # role 统一
        role = md.get("role")
        if role == "ai":
            md["role"] = "assistant"
        elif role == "human":
            md["role"] = "user"

        # ToolNode 有时会返回 dict/ToolMessage，tool_call_id 可能存在但为 None；
        # 此时也必须补齐，否则 add_messages 合并可能失败或导致 tool 输出无法被下游 Agent 读取。
        if md.get("role") == "tool" and not md.get("tool_call_id"):
            md["tool_call_id"] = fallback_tool_call_id or "tool_call_unknown"
        normalized.append(md)

    out["messages"] = normalized
    # 将最新的工具输出缓存到状态，方便子 Agent 在“第二阶段”注入到 Prompt
    tool_outputs = []
    for md in normalized:
        if md.get("role") != "tool":
            continue
        content = md.get("content") or md.get("tool_output") or ""
        if not content:
            continue
        tool_outputs.append({
            "tool": md.get("name") or "",
            "tool_call_id": md.get("tool_call_id") or "",
            "content": content,
        })
    if tool_outputs:
        out["_last_tool_outputs"] = tool_outputs
        out["_last_tool_content"] = tool_outputs[-1]["content"]

    return out


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
    workflow.add_node("router", _wrap_step_counter("router", router_node))
    workflow.add_node("onboarding", compile_onboarding_workflow())
    workflow.add_node("main_agent", _wrap_step_counter("main_agent", main_agent_node))
    workflow.add_node("status_agent", _wrap_step_counter("status_agent", status_agent_node))
    workflow.add_node("plan_agent", _wrap_step_counter("plan_agent", plan_agent_node))
    workflow.add_node("guide_agent", _wrap_step_counter("guide_agent", guide_agent_node))
    workflow.add_node("post_turn_finalize", _wrap_step_counter("post_turn_finalize", post_turn_finalize_node))
    # workflow.add_node("wait_user_input", wait_user_input_node) # Removed in Phase 3
    workflow.add_node("skill_tools", _wrap_step_counter("skill_tools", skill_tools_node))  # 新增：Skill 工具节点
    
    # 设置入口点
    workflow.set_entry_point("router")

    # Onboarding 完成后进入 Router
    workflow.add_conditional_edges(
        "onboarding",
        route_after_onboarding,
        {
            "router": "router",
            "end": "post_turn_finalize",
        }
    )

    # Router 后的路由：可能先到 Onboarding，也可能直接到主 Agent，或恢复 Agent
    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {
            "onboarding": "onboarding",
            "main_agent": "main_agent",
            "status_agent": "status_agent",
            "plan_agent": "plan_agent",
            "guide_agent": "guide_agent",
            "end": "post_turn_finalize",
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
            # "wait_user_input": "wait_user_input", # Removed in Phase 3
            "end": "post_turn_finalize",
        }
    )
    
    # 子 Agent 后的统一路由：工具调用 / 等待用户输入 / 回主 Agent
    workflow.add_conditional_edges(
        "status_agent",
        route_after_sub_agent,
        {
            "skill_tools": "skill_tools",  # 新增：工具调用
            "main_agent": "main_agent",
            "end": "post_turn_finalize",
            # "wait_user_input": "wait_user_input", # Removed in Phase 3
        }
    )
    
    workflow.add_conditional_edges(
        "plan_agent",
        route_after_sub_agent,
        {
            "skill_tools": "skill_tools",  # 新增：工具调用
            "main_agent": "main_agent",
            "end": "post_turn_finalize",
            # "wait_user_input": "wait_user_input", # Removed in Phase 3
        }
    )
    
    workflow.add_conditional_edges(
        "guide_agent",
        route_after_guide_agent,
        {
            "skill_tools": "skill_tools",
            "main_agent": "main_agent",
            "end": "post_turn_finalize",
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

    # Finalizer 只做“落库 + 入队”，之后结束本轮
    workflow.add_edge("post_turn_finalize", END)
    
    # wait_user_input 直接结束本轮 (Removed in Phase 3)
    # workflow.add_edge("wait_user_input", END)
    
    return workflow


def compile_workflow():
    """
    编译工作流
    
    Returns:
        可执行的工作流实例
    """
    workflow = create_workflow()
    return workflow.compile()


# 创建全局工作流实例（单例模式）
_compiled_workflow = None


def get_workflow():
    """
    获取编译后的工作流（单例模式）
    
    Returns:
        编译后的工作流实例
    """
    global _compiled_workflow
    
    if _compiled_workflow is None:
        _compiled_workflow = compile_workflow()
    
    return _compiled_workflow


def reset_workflow():
    """
    重置工作流实例
    """
    global _compiled_workflow
    _compiled_workflow = None

