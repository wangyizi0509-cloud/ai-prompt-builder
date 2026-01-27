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
- Agent 可以通过 load_skill(skill_id) 工具按需加载技能指令
- skill_tools 节点负责执行工具调用
- 工具执行完成后自动返回调用它的 Agent

v2.1 更新：
- 添加 Checkpointer 支持（使用 MemorySaver）
"""

from typing import Literal, Optional
import json
import os
import uuid
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from graph.state import AgentState
from graph.state import convert_message_to_dict, ensure_message_id
from graph.nodes.router import router_node
from graph.nodes.main_agent import main_agent_node
from graph.nodes.status_agent import status_agent_node
from graph.nodes.plan_agent import plan_agent_node
from graph.nodes.guide_agent import guide_agent_node
from graph.nodes.finalizer import post_turn_finalize_node
from onboarding.workflow import compile_onboarding_workflow
from skills import create_all_skills_loader
from graph.tools.delegate_tools import (
    delegate_to_status,
    delegate_to_plan,
    delegate_to_guide,
    end_turn,
)
from graph.tools.ask_tool import (
    get_ask_tool,
    ASK_MODE_STRATEGY,
    ASK_MODE_SIMPLE,
)
from graph.tools.consult_answer_tool import (
    get_consult_tool,
    CONSULT_MODE_STRATEGY,
    CONSULT_MODE_SIMPLE,
)
from graph.tools.emotion_support_tool import (
    get_emotion_tool,
    EMOTION_MODE_STRATEGY,
    EMOTION_MODE_SIMPLE,
)
from graph.tools.task_tools import (
    create_task_tools,
    apply_task_tool_state_update,
    is_task_tool,
)
from graph.tools.context_loader import (
    create_context_loader,
    apply_context_loader_state_update,
    is_context_loader_tool,
)
from graph.tools.submit_tools import (
    submit_status_report,
    submit_action_plan,
    submit_action_guide,
    update_guide_status,
    update_guide_content,
    return_to_main,
    apply_submit_tool_state_update,
    is_submit_tool,
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
        # 统一补齐消息 ID（已有 ID 不覆盖）
        msgs = out.get("messages")
        if isinstance(msgs, list) and msgs:
            out["messages"] = [ensure_message_id(m)[1] for m in msgs]
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


def route_after_main_agent(state: AgentState) -> Literal["skill_tools", "end"]:
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
    
    # 无工具调用则结束本轮
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


def route_after_skill_tools(state: AgentState) -> Literal["main_agent", "status_agent", "plan_agent", "guide_agent", "end"]:
    """
    skill_tools 节点执行完成后的路由
    
    返回到调用工具的 Agent，让它继续处理
    
    [FIX] 2026-01-26: 添加 submit tool 完成检查
    - 当子 Agent 调用 submit tool 完成任务后，应该路由回 main_agent
    - 而不是继续路由回原来的子 Agent
    
    [FIX] 2026-01-26: 修复 ask 两阶段流程
    - Phase 1: ask(action="enable") → 设置 ask_mode=True, _pending_action="ask"
      此时应该返回调用者 Agent 继续执行 Phase 2
    - Phase 2: ask(questions=[...]) → 生成 inquiry_card
      此时应该返回 "end" 等待用户输入
    
    [ADD] 2026-01-27: 添加 end_turn 支持
    - main_agent 调用 end_turn 后，直接返回 "end" 结束本轮
    - 不输出任何用户可见内容，但 post_turn_finalize 照常执行
    """
    iteration = int(state.get("_iteration_count", 0) or 0)
    if iteration >= MAX_NODE_STEPS_PER_TURN:
        # 兜底：工具已执行但本轮步数过多，直接回主 Agent 收口（由 main_agent end_turn）
        print("[WARN] Max node steps reached after skill_tools, returning to main_agent")
        return "main_agent"

    # [ADD] 优先检测 end_turn：main_agent 请求直接结束本轮
    if state.get("_end_turn"):
        print("[DEBUG] route_after_skill_tools: end_turn detected, ending turn")
        return "end"

    # [FIX] Phase 1 完成后：_pending_action="ask" 表示需要继续执行 Phase 2
    # 此时不应该结束，而应该返回调用者 Agent
    pending_action = state.get("_pending_action")
    if pending_action == "ask":
        # Phase 1 刚完成，需要返回调用者 Agent 执行 Phase 2
        current_agent = state.get("current_agent", "main_agent")
        print(f"[DEBUG] route_after_skill_tools: Phase 1 completed, returning to {current_agent} for Phase 2")
        if current_agent == "status_agent":
            return "status_agent"
        elif current_agent == "plan_agent":
            return "plan_agent"
        elif current_agent == "guide_agent":
            return "guide_agent"
        else:
            return "main_agent"

    # Phase 2 完成后：已生成 inquiry_card 或 pending_questions，等待用户输入
    if state.get("inquiry_card") or state.get("pending_questions"):
        return "end"
    
    # 如果有 current_agent 和 agent_resume_point，且没有 pending_action
    # 说明是需要等待用户输入的状态（但不是 ask Phase 1）
    if state.get("current_agent") and state.get("agent_resume_point"):
        return "end"
    
    # [FIX] consult_answer/emotion_support complete 后，本轮直接结束，不再回到 main_agent
    if state.get("_reply_skill_complete"):
        print("[DEBUG] route_after_skill_tools: Reply skill completed (consult/emotion), ending turn")
        return "end"

    # 子 Agent 主动请求转接回 main_agent
    if state.get("_return_to_main"):
        print("[DEBUG] route_after_skill_tools: return_to_main requested, routing to main_agent")
        return "main_agent"

    handoff_target = state.get("_handoff_target") or ""
    if handoff_target in ("status_agent", "plan_agent", "guide_agent"):
        return handoff_target

    # 兜底：检查工具输出 action
    last_tool_content = state.get("_last_tool_content") or ""
    if last_tool_content:
        try:
            payload = json.loads(last_tool_content)
            if payload.get("action") == "ask_user":
                return "end"
        except Exception:
            pass

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
    
    Ask 工具两阶段处理：
    - Phase 1: ask(action="enable") -> 设置 ask_mode=True，返回详细策略
    - Phase 2: ask(questions=[...]) -> 设置 ask_mode=False，生成 inquiry_card
    """
    # 说明：tool 输出不会写入对话历史（见 context_builder），因此需要保证工具执行后能在"二阶段"被对应 Agent 注入。
    
    # 获取当前 Agent 名称（用于任务工具）
    current_agent = state.get("current_agent", "main_agent")
    
    # 获取当前 ask_mode 状态，决定使用哪个版本的 ask 工具
    ask_mode = state.get("ask_mode", False)
    ask_tool = get_ask_tool(ask_mode)
    
    # 获取当前 consult_mode 状态，决定使用哪个版本的 consult_answer 工具
    consult_mode = state.get("consult_mode", False)
    consult_tool = get_consult_tool(consult_mode)
    
    # 获取当前 emotion_mode 状态，决定使用哪个版本的 emotion_support 工具
    emotion_mode = state.get("emotion_mode", False)
    emotion_tool = get_emotion_tool(emotion_mode)
    
    # 创建任务工具
    task_tools = create_task_tools(lambda: state, agent_name=current_agent)
    
    tool_node = ToolNode([
        # Skill 加载工具（工具名统一为 load_skill）
        create_all_skills_loader(),
        # 子 Agent 委派工具
        delegate_to_status,
        delegate_to_plan,
        delegate_to_guide,
        # 结束本轮工具（仅 main_agent 使用）
        end_turn,
        # 提问工具（状态驱动，根据 ask_mode 返回不同版本）
        ask_tool,
        # 解答工具（状态驱动，根据 consult_mode 返回不同版本）
        consult_tool,
        # 陪伴工具（状态驱动，根据 emotion_mode 返回不同版本）
        emotion_tool,
        # 通用上下文拉取工具（仅 main_agent 会调用，但 ToolNode 统一执行）
        create_context_loader(lambda: state, current_agent),
        # 任务管理工具
        *task_tools,
        # 提交类工具（子 Agent 产出）
        submit_status_report,
        submit_action_plan,
        submit_action_guide,
        update_guide_status,
        update_guide_content,
        return_to_main,
    ])
    out = tool_node.invoke(state)
    
    # 检查是否调用了任务工具或行动指南绑定工具，如果是则应用状态更新
    messages = state.get("messages", [])
    ask_user_payload = None
    ask_enable_payload = None  # Phase 1: 进入提问模式
    consult_enable_payload = None  # Phase 1: 进入解答模式
    consult_complete_payload = None  # Phase 2: 完成解答
    emotion_enable_payload = None  # Phase 1: 进入陪伴模式
    emotion_complete_payload = None  # Phase 2: 完成陪伴
    
    for msg in reversed(messages):
        tool_calls = getattr(msg, "tool_calls", None) or (msg.get("tool_calls") if isinstance(msg, dict) else None)
        if tool_calls:
            for tc in tool_calls:
                tool_name = tc.get("name", "") if isinstance(tc, dict) else ""
                tool_args = tc.get("args", {}) if isinstance(tc, dict) else {}
                
                if tool_name in {"delegate_to_status", "delegate_to_plan", "delegate_to_guide"}:
                    out["_handoff_target"] = {
                        "delegate_to_status": "status_agent",
                        "delegate_to_plan": "plan_agent",
                        "delegate_to_guide": "guide_agent",
                    }.get(tool_name, "")
                    out["_handoff_instruction"] = tool_args.get("instruction", "")
                    out["instruction"] = tool_args.get("instruction", "")
                    # [FIX] 2026-01-26: 清除所有可能干扰 route_after_skill_tools 路由判断的状态
                    # 这些状态在 route_after_skill_tools 中的检查顺序在 _handoff_target 之前
                    # 如果不清除，会导致路由函数提前返回错误的目标
                    # 
                    # 污染场景示例：
                    # 1. status_agent 完成 -> _submit_result 残留 -> main_agent 调用 delegate_to_plan -> 错误路由到 main_agent
                    # 2. Agent A 进入 ask Phase 1 -> _pending_action="ask" 残留 -> handoff 到 B -> 错误路由回 A
                    # 3. Agent A 生成 inquiry_card -> 残留 -> handoff 到 B -> 错误 return "end"
                    # 4. main_agent 用 consult 回复 -> _reply_skill_complete 残留 -> handoff 到 B -> 错误 return "end"
                    out["_submit_result"] = None
                    out["_pending_action"] = None
                    out["_reply_skill_complete"] = None
                    out["_return_to_main"] = None
                    out["_return_to_main_reason"] = None
                    out["inquiry_card"] = None
                    out["pending_questions"] = []
                    out["agent_resume_point"] = None
                    # 注意：current_agent 在 handoff 后会被目标 Agent 节点重新设置，这里不清除
                # === Ask 工具两阶段处理 ===
                elif tool_name == "ask":
                    if tool_args.get("action") == "enable":
                        # Phase 1: 进入提问模式
                        ask_enable_payload = {
                            "agent": current_agent,
                            "tool_call_id": tc.get("id", ""),
                        }
                    elif "questions" in tool_args:
                        # Phase 2: 执行提问（与原 ask_user 逻辑相同）
                        ask_user_payload = {
                            "questions": tool_args.get("questions") or [],
                            "intro": tool_args.get("intro") or "",
                            "reasoning": tool_args.get("reasoning") or "",
                            "agent": current_agent,
                        }
                        out["_pending_action"] = None
                
                # === consult_answer 工具两阶段处理 ===
                elif tool_name == "consult_answer":
                    if tool_args.get("action") == "enable":
                        # Phase 1: 进入解答模式
                        consult_enable_payload = {
                            "agent": current_agent,
                            "tool_call_id": tc.get("id", ""),
                        }
                    elif tool_args.get("action") == "complete":
                        # Phase 2: 完成解答
                        consult_complete_payload = {
                            "agent": current_agent,
                            "tool_call_id": tc.get("id", ""),
                        }
                
                # === emotion_support 工具两阶段处理 ===
                elif tool_name == "emotion_support":
                    if tool_args.get("action") == "enable":
                        # Phase 1: 进入陪伴模式
                        emotion_enable_payload = {
                            "agent": current_agent,
                            "tool_call_id": tc.get("id", ""),
                        }
                    elif tool_args.get("action") == "complete":
                        # Phase 2: 完成陪伴
                        emotion_complete_payload = {
                            "agent": current_agent,
                            "tool_call_id": tc.get("id", ""),
                        }
                    
                elif is_task_tool(tool_name):
                    # 应用任务工具的状态更新
                    task_state_update = apply_task_tool_state_update(state, tool_name, tool_args, current_agent)
                    if task_state_update:
                        # 合并状态更新
                        for key, value in task_state_update.items():
                            out[key] = value
                        print(f"[DEBUG] skill_tools_node: Applied task tool state update for {tool_name}")

                elif is_context_loader_tool(tool_name):
                    context_state_update = apply_context_loader_state_update(state, tool_name, tool_args, current_agent)
                    if context_state_update:
                        for key, value in context_state_update.items():
                            out[key] = value
                        print(f"[DEBUG] skill_tools_node: Applied context loader state update for {tool_name}")
                elif is_submit_tool(tool_name):
                    submit_state_update = apply_submit_tool_state_update(state, tool_name, tool_args)
                    if submit_state_update:
                        for key, value in submit_state_update.items():
                            out[key] = value
                        print(f"[DEBUG] skill_tools_node: Applied submit tool state update for {tool_name}")
                elif tool_name == "return_to_main":
                    out["_return_to_main"] = True
                    out["_return_to_main_reason"] = tool_args.get("reason", "") or ""
                elif tool_name == "end_turn":
                    # main_agent 调用 end_turn：设置标记，路由时直接结束
                    out["_end_turn"] = True
                    reason = tool_args.get("reason", "") or ""
                    if reason:
                        print(f"[DEBUG] skill_tools_node: end_turn called with reason: {reason}")
                    else:
                        print(f"[DEBUG] skill_tools_node: end_turn called (no reason)")
            break
    
    # === Phase 1 处理：进入提问模式 ===
    if ask_enable_payload:
        tool_message_id = str(uuid.uuid4())
        out["ask_mode"] = True
        out["ask_mode_tool_message_id"] = tool_message_id
        out["_pending_action"] = "ask"  # 强制下一步调用 ask
        
        # [FIX] 2026-01-26: 清理旧的 agent_resume_point，避免影响路由判断
        # Phase 1 时不应该有 resume_point，它只在 Phase 2 完成后才设置
        out["agent_resume_point"] = None
        
        # 生成带策略的 ToolMessage（替换 ToolNode 返回的简单消息）
        strategy_content = f"已进入提问模式，请使用 ask 工具向用户提问。\n\n{ASK_MODE_STRATEGY}"
        
        # 找到原来的 tool message 并替换其内容
        msgs = out.get("messages", [])
        for i, m in enumerate(msgs):
            md = convert_message_to_dict(m) if not isinstance(m, dict) else m
            if md.get("role") == "tool" and md.get("name") == "ask":
                msgs[i] = {
                    "role": "tool",
                    "id": tool_message_id,
                    "name": "ask",
                    "content": strategy_content,
                    "tool_call_id": ask_enable_payload.get("tool_call_id", ""),
                }
                break
        out["messages"] = msgs
        print(f"[DEBUG] skill_tools_node: Phase 1 - entered ask_mode, tool_message_id={tool_message_id}")

    # === Phase 1 处理：进入解答模式 ===
    if consult_enable_payload:
        tool_message_id = str(uuid.uuid4())
        out["consult_mode"] = True
        out["consult_mode_tool_message_id"] = tool_message_id
        # 注意：不设置 _pending_action，模型自由输出 content + tool_call(complete)
        
        # [FIX] 2026-01-26: 清理旧的 agent_resume_point，避免影响路由判断
        out["agent_resume_point"] = None
        
        # 生成带策略的 ToolMessage
        strategy_content = f"已进入解答模式，请根据以下策略回复用户。回复完成后，调用 consult_answer(action=\"complete\") 关闭解答模式。\n\n{CONSULT_MODE_STRATEGY}"
        
        msgs = out.get("messages", [])
        for i, m in enumerate(msgs):
            md = convert_message_to_dict(m) if not isinstance(m, dict) else m
            if md.get("role") == "tool" and md.get("name") == "consult_answer":
                msgs[i] = {
                    "role": "tool",
                    "id": tool_message_id,
                    "name": "consult_answer",
                    "content": strategy_content,
                    "tool_call_id": consult_enable_payload.get("tool_call_id", ""),
                }
                break
        out["messages"] = msgs
        print(f"[DEBUG] skill_tools_node: Phase 1 - entered consult_mode, tool_message_id={tool_message_id}")
    
    # === Phase 2 处理：完成解答 ===
    if consult_complete_payload:
        out["consult_mode"] = False
        out["_reply_skill_complete"] = True  # 标记回复技能已完成，用于路由直接结束
        # 生成关闭确认的 ToolMessage
        msgs = out.get("messages", [])
        for i, m in enumerate(msgs):
            md = convert_message_to_dict(m) if not isinstance(m, dict) else m
            if md.get("role") == "tool" and md.get("name") == "consult_answer":
                msgs[i] = {
                    "role": "tool",
                    "id": md.get("id") or str(uuid.uuid4()),
                    "name": "consult_answer",
                    "content": "解答模式已关闭。",
                    "tool_call_id": consult_complete_payload.get("tool_call_id", ""),
                }
                break
        out["messages"] = msgs
        print(f"[DEBUG] skill_tools_node: Phase 2 - consult_mode closed, marking _reply_skill_complete")

    # === Phase 1 处理：进入陪伴模式 ===
    if emotion_enable_payload:
        tool_message_id = str(uuid.uuid4())
        out["emotion_mode"] = True
        out["emotion_mode_tool_message_id"] = tool_message_id
        # 注意：不设置 _pending_action，模型自由输出 content + tool_call(complete)
        
        # [FIX] 2026-01-26: 清理旧的 agent_resume_point，避免影响路由判断
        out["agent_resume_point"] = None
        
        # 生成带策略的 ToolMessage
        strategy_content = f"已进入陪伴模式，请根据以下策略回复用户。回复完成后，调用 emotion_support(action=\"complete\") 关闭陪伴模式。\n\n{EMOTION_MODE_STRATEGY}"
        
        msgs = out.get("messages", [])
        for i, m in enumerate(msgs):
            md = convert_message_to_dict(m) if not isinstance(m, dict) else m
            if md.get("role") == "tool" and md.get("name") == "emotion_support":
                msgs[i] = {
                    "role": "tool",
                    "id": tool_message_id,
                    "name": "emotion_support",
                    "content": strategy_content,
                    "tool_call_id": emotion_enable_payload.get("tool_call_id", ""),
                }
                break
        out["messages"] = msgs
        print(f"[DEBUG] skill_tools_node: Phase 1 - entered emotion_mode, tool_message_id={tool_message_id}")
    
    # === Phase 2 处理：完成陪伴 ===
    if emotion_complete_payload:
        out["emotion_mode"] = False
        out["_reply_skill_complete"] = True  # 标记回复技能已完成，用于路由直接结束
        # 生成关闭确认的 ToolMessage
        msgs = out.get("messages", [])
        for i, m in enumerate(msgs):
            md = convert_message_to_dict(m) if not isinstance(m, dict) else m
            if md.get("role") == "tool" and md.get("name") == "emotion_support":
                msgs[i] = {
                    "role": "tool",
                    "id": md.get("id") or str(uuid.uuid4()),
                    "name": "emotion_support",
                    "content": "陪伴模式已关闭。",
                    "tool_call_id": emotion_complete_payload.get("tool_call_id", ""),
                }
                break
        out["messages"] = msgs
        print(f"[DEBUG] skill_tools_node: Phase 2 - emotion_mode closed, marking _reply_skill_complete")

    # 兜底：确保任务/上下文相关的状态更新从 tool 执行结果写回
    if "layer3_memory" in state and "layer3_memory" not in out:
        out["layer3_memory"] = state.get("layer3_memory")
    if "task_registry" in state and "task_registry" not in out:
        out["task_registry"] = state.get("task_registry")

    # 兼容：确保 tool 消息具备 tool_call_id（LangChain ToolMessage 必填，且不能为 None/空）
    # 在某些模式下，ToolNode 可能返回 dict 形式的消息；若缺 tool_call_id，会导致 add_messages 合并报错。
    msgs = out.get("messages", [])
    if not msgs:
        return out

    # 尝试从上一条 AIMessage 的 tool_calls 中取回 tool_call_id（若需要兜底）
    tool_call_map: dict[str, str] = {}
    fallback_tool_call_id = ""
    for m in reversed(state.get("messages", []) or []):
        # LangChain AIMessage
        tool_calls = getattr(m, "tool_calls", None)
        if tool_calls:
            try:
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc_id = str(tc.get("id") or "")
                        tc_name = str(tc.get("name") or "")
                        if tc_id:
                            tool_call_map[tc_id] = tc_name
                fallback_tool_call_id = str(tool_calls[0].get("id") or "")
            except Exception:
                fallback_tool_call_id = ""
            break
        # dict 形式
        if isinstance(m, dict) and m.get("tool_calls"):
            try:
                for tc in m["tool_calls"]:
                    if isinstance(tc, dict):
                        tc_id = str(tc.get("id") or "")
                        tc_name = str(tc.get("name") or "")
                        if tc_id:
                            tool_call_map[tc_id] = tc_name
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
            md["tool_call_id"] = fallback_tool_call_id or ""
        if md.get("role") == "tool" and not md.get("name"):
            tc_id = md.get("tool_call_id") or ""
            if tc_id and tc_id in tool_call_map:
                md["name"] = tool_call_map[tc_id]
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

    # === 任务完成转接 ===
    if out.get("_return_to_main"):
        submit_result = out.get("_submit_result") or state.get("_submit_result") or {}
        submit_type = submit_result.get("type", "")
        reason = out.get("_return_to_main_reason") or ""
        if reason:
            result_summary = reason
        elif submit_type == "status_report":
            result_summary = f"现状分析完成：报告{submit_result.get('report_id', '')}"
        elif submit_type == "action_plan":
            result_summary = f"行动规划完成：规划{submit_result.get('plan_id', '')}"
        elif submit_type == "action_guide":
            result_summary = f"行动指南完成：指南{submit_result.get('guide_id', '')}"
        elif submit_type == "guide_status_update":
            result_summary = f"行动指南状态更新：{submit_result.get('new_status', '')}"
        elif submit_type == "guide_content_update":
            result_summary = f"行动指南内容更新：指南{submit_result.get('guide_id', '')}"
        else:
            result_summary = "任务已完成"
        out["completion_status"] = "COMPLETED"
        out["result_summary"] = result_summary
        out["current_agent"] = None
        out["agent_resume_point"] = None
        out["_handoff_target"] = None

    # === Phase 2 处理：执行提问 ===
    if ask_user_payload:
        questions = ask_user_payload.get("questions") or []
        intro = ask_user_payload.get("intro") or ""
        agent_name = ask_user_payload.get("agent") or current_agent
        resume_map = {
            "main_agent": "continue_decision",
            "status_agent": "continue_analysis",
            "plan_agent": "continue_planning",
            "guide_agent": "continue_guide",
        }
        
        # Phase 2 完成：恢复 ask_mode 为 False
        out["ask_mode"] = False
        
        out["inquiry_card"] = {
            "questions": questions,
            "intro": intro,
            "reasoning": ask_user_payload.get("reasoning") or "",
        }
        out["pending_questions"] = [
            q.get("question", "") if isinstance(q, dict) else str(q) for q in questions
        ]
        out["current_agent"] = agent_name
        out["agent_resume_point"] = resume_map.get(agent_name)

        # 连续提问计数
        streak_agent = state.get("question_streak_agent")
        streak_count = int(state.get("question_streak_count", 0) or 0)
        next_streak = (streak_count + 1) if (streak_agent == agent_name) else 1
        out["question_streak_agent"] = agent_name
        out["question_streak_count"] = next_streak
        out["question_count"] = next_streak

        response_content = intro.strip() or "为了更好地继续，我需要再了解一些细节～"
        phase_map = {
            "status_agent": "after_status",
            "plan_agent": "after_plan",
            "guide_agent": "after_guide",
        }
        existing_responses = state.get("pending_responses", [])
        out["pending_responses"] = existing_responses + [{
            "from": agent_name,
            "content": response_content,
            "phase": phase_map.get(agent_name, "immediate"),
        }]
        
        # 生成提问结束的 ToolMessage 摘要
        questions_summary = "\n".join([f"- {q.get('question', '')}" for q in questions if isinstance(q, dict)])
        ask_end_content = f"提问模式结束。已生成以下问题：\n{questions_summary}"
        
        # 更新 normalized 中的 ask tool message 内容
        for i, md in enumerate(normalized):
            if md.get("role") == "tool" and md.get("name") == "ask":
                normalized[i] = dict(md)
                normalized[i]["content"] = ask_end_content
                break
        
        out["messages"] = normalized + [{
            "role": "assistant",
            "name": agent_name,
            "content": response_content,
        }]
        
        print(f"[DEBUG] skill_tools_node: Phase 2 - ask_mode reset to False, {len(questions)} questions generated")

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
            "end": "post_turn_finalize",
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

