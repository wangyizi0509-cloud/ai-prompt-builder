"""
主 Agent 节点 (Main Agent)
决策中枢，负责回应用户和决策下一步行动

采用 Anthropic 渐进式加载模式（Tool-based）：
- 系统提示只包含 Skills 的元数据（name + description）
- 模型通过 load_skill_instructions 工具按需加载完整技能指令
- 工作流自动处理工具调用循环

支持的功能：
1. 回应用户（简短、共情、承上启下）
2. 决策下一步行动（调用子 Agent 或结束本轮）
3. 如需提问，调用 load_skill_instructions 工具获取提问指令
4. 子 Agent 返回后再决策（灵活判断，无固定流程）
5. 根据意图类型使用咨询 Skills 直接回复（解答疑惑、情感陪伴）

上下文架构更新 (v2.0)：
- 使用分层上下文架构（Layer 0-4）
- 通过 context_builder 统一组装上下文

任务管理更新 (v2.1)：
- 任务边界：由模型判断（继续/新建/完成）
- 思考过程：同一任务内保留，任务切换时归档（不删除）
- 任务 ID：语义化命名（如"判断crush是否喜欢用户"）
"""

import json
from typing import Any
from datetime import datetime

from graph.state import AgentState
from graph.context_builder import build_context_dict
from graph.context_types import create_new_task, get_active_task
from graph.tools.task_tools import (
    create_task_tools,
    apply_task_tool_state_update,
    is_task_tool,
    TASK_TOOL_NAMES,
)
from graph.tools.guide_bind_tools import create_guide_bind_tool
from skills import (
    get_inquiry_skill, 
    get_consult_answer_skill, 
    get_emotion_support_skill, 
    load_inquiry_skill_instructions,
    load_consult_answer_skill_instructions,
    load_emotion_support_skill_instructions
)
from skills.guide_loader import create_guide_loader_tool
from utils.prompt_loader import load_prompt, get_prompt_path
from utils.message_utils import get_msg_role_and_content
from config import get_llm
from langchain_core.messages import ToolMessage


# ============================================================
# 任务管理辅助函数
# ============================================================

def _format_onboarding_handoff_summary(onboarding_handoff: dict) -> str:
    """
    将 onboarding_handoff 格式化为一行摘要文本，用于注入对话历史。
    这是纯函数：不触发 LLM、不依赖外部状态，便于单测。
    """
    if not onboarding_handoff or not isinstance(onboarding_handoff, dict):
        return ""
    parts: list[str] = []
    rec = onboarding_handoff.get("recommendation")
    action = onboarding_handoff.get("suggested_action")
    reason = onboarding_handoff.get("reason")
    if rec:
        parts.append(f"建议: {rec}")
    if action:
        parts.append(f"动作: {action}")
    if reason:
        parts.append(f"理由: {reason}")
    return " | ".join(parts) if parts else "Onboarding 已完成"


def _handle_task_update(state: AgentState, task_update: dict) -> dict:
    """
    处理任务更新（由模型判断）
    
    Args:
        state: 当前状态
        task_update: 模型输出的任务更新信息
            - action: "continue" | "new" | "complete"
            - task_id: 新任务的语义化 ID（仅 action=new 时）
            - reasoning_note: 本轮的关键思考
    
    Returns:
        包含 task_registry 更新的字典
    """
    if not task_update:
        return {}
    
    action = task_update.get("action", "continue")
    task_registry = state.get("layer3_memory", {}).get("task_registry", {})
    task_list = list(task_registry.get("main_agent", []))
    
    if action == "new":
        # 开启新任务：将旧任务标记为非活跃，并确保不会残留 status='active'
        for task in task_list:
            was_active = bool(task.get("is_active", False) or task.get("status") == "active")
            task["is_active"] = False
            if was_active and task.get("status") == "active":
                task["status"] = "pending"
        
        new_task_id = task_update.get("task_id", f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        new_task = create_new_task(new_task_id)
        
        # 如果有思考记录，添加到新任务
        reasoning_note = task_update.get("reasoning_note", "")
        if reasoning_note:
            new_task["reasoning"] = [reasoning_note]
        
        task_list.append(new_task)
        print(f"[DEBUG] MainAgent: Started new task '{new_task_id}'")
        
    elif action == "continue":
        # 继续当前任务：添加思考记录
        reasoning_note = task_update.get("reasoning_note", "")
        if reasoning_note:
            for task in task_list:
                # 兼容：老数据可能只有 status='active' 没有 is_active
                if task.get("is_active", False) or task.get("status") == "active":
                    reasoning = list(task.get("reasoning", []))
                    reasoning.append(reasoning_note)
                    task["reasoning"] = reasoning
                    print(f"[DEBUG] MainAgent: Added reasoning to task '{task.get('task_id')}'")
                    break
        
    elif action == "complete":
        # 完成当前任务：标记为非活跃（不删除，保留思考过程）
        for task in task_list:
            if task.get("is_active", False) or task.get("status") == "active":
                task["is_active"] = False
                task["status"] = "completed"
                task["completed_at"] = datetime.now().isoformat()
                print(f"[DEBUG] MainAgent: Completed task '{task.get('task_id')}'")
                break
    
    return {
        "layer3_memory": {
            **state.get("layer3_memory", {}),
            "task_registry": {
                **task_registry,
                "main_agent": task_list,
            }
        }
    }

def main_agent_node(state: AgentState) -> dict[str, Any]:
    """
    主 Agent 节点
    
    职责：
    1. 回应用户（简短、共情、承上启下）
    2. 决策下一步行动（调用子 Agent 或结束本轮）
    3. 如需技能指令，通过 load_skill_instructions 工具获取
    4. 子 Agent 返回后再决策（灵活判断，无固定流程）
    5. 使用咨询 Skills 直接回复（解答疑惑、情感陪伴）
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    # === 检测执行模式 ===
    # 模式1：从提问中恢复（主 Agent 之前提问，用户回答了）
    is_resuming = (state.get("current_agent") == "main_agent" and 
                   state.get("agent_resume_point") == "continue_decision")
    
    # 模式2：子 Agent 返回后的再决策
    from_sub_agent = state.get("completion_status") is not None
    
    # 模式3：工具调用返回（增强版检测）
    messages = state.get("messages", [])
    last_msg_role = ""
    last_tool_content = None
    if messages:
        last_msg_role, last_tool_content = get_msg_role_and_content(messages[-1])
        
    # Check if returning from tool call (either by state flag or by checking last message role)
    from_tool_call = (state.get("_tool_caller") == "main_agent" or last_msg_role == "tool")

    # 绑定 Skill 加载工具和任务管理工具
    llm = get_llm(temperature=0.7)
    
    # 创建任务管理工具（需要 state_getter 来获取当前状态）
    task_tools = create_task_tools(lambda: state, agent_name="main_agent")
    
    # [FIX] 防止死循环：只有在第一阶段（非工具返回）才允许调用工具
    if not from_tool_call:
        llm = llm.bind_tools([
            # Skill 加载工具
            load_inquiry_skill_instructions,
            load_consult_answer_skill_instructions,
            load_emotion_support_skill_instructions,
            create_guide_loader_tool(lambda: state),
            # 行动指南详情绑定工具（跨轮次持久注入）
            create_guide_bind_tool(lambda: state, "main_agent"),
            # 任务管理工具
            *task_tools,
        ])
    else:
        print(f"[DEBUG] MainAgent: Second stage (from_tool_call), tools disabled to prevent loop")
    
    if is_resuming:
        print(f"[DEBUG] MainAgent: Resuming from ask_user, question_count={state.get('question_count', 0)}")
    elif from_sub_agent:
        print(f"[DEBUG] MainAgent: Re-decision after sub-agent, status={state.get('completion_status')}, summary={state.get('result_summary')}")
    elif from_tool_call:
        print(f"[DEBUG] MainAgent: Continuing after tool call (last_role={last_msg_role})")
    
    # === 获取提问状态（用于恢复执行）===
    # vNext：同一 agent 连续提问 <= max_question_streak；中间发生非提问动作则清零
    streak_agent = state.get("question_streak_agent")
    streak_count = int(state.get("question_streak_count", 0) or 0)
    max_streak = int(state.get("max_question_streak", 3) or 3)

    # 向后兼容：旧字段（仍可能被日志/测试/旧逻辑依赖）
    question_count = int(state.get("question_count", 0) or 0)
    max_questions = int(state.get("max_questions", 10) or 10)
    
    # 加载 Prompt
    try:
        prompt_name = "main_agent"
        prompt_path = get_prompt_path(prompt_name)
        prompt_template = load_prompt(prompt_name)
        prompt_source = str(prompt_path)
        prompt_fallback = False
    except FileNotFoundError:
        prompt_template = _get_default_prompt(from_sub_agent, is_resuming)
        prompt_source = "fallback:_get_default_prompt(FileNotFoundError)"
        prompt_fallback = True
    
    # 构建上下文（使用新的分层上下文架构，包含任务思考过程）
    context_dict = build_context_dict(state, target_agent="main_agent")
    
    # Onboarding handoff：转换为一行对话历史，避免占用额外模板空间
    onboarding_handoff = state.get("onboarding_handoff") or {}
    conversation_history = context_dict.get("conversation_history", "无历史对话")
    if onboarding_handoff:
        summary_line = _format_onboarding_handoff_summary(onboarding_handoff)
        if summary_line:
            conversation_history = f"{conversation_history}\n\n【Onboarding总结】{summary_line}"

    # Skills 元数据 + 工具使用说明
    skills_prompt_content = _get_skills_metadata_prompt()

    # [FIX] 如果是从工具调用返回：tool 输出不会进入对话历史，需要注入 Prompt 才能在二阶段使用
    if from_tool_call:
        print(f"[DEBUG] MainAgent: Handling return from tool call.")

        # 尝试拿到上一轮的 tool_calls 名称，用于区分“技能指令” vs “行动指南详情”
        tool_call_names: list[str] = []
        for msg in reversed(messages):
            tc = getattr(msg, "tool_calls", None)
            if tc:
                try:
                    tool_call_names = [str(x.get("name") or "") for x in tc if isinstance(x, dict)]
                except Exception:
                    tool_call_names = []
                break
            if isinstance(msg, dict) and msg.get("tool_calls"):
                try:
                    tool_call_names = [str(x.get("name") or "") for x in msg["tool_calls"] if isinstance(x, dict)]
                except Exception:
                    tool_call_names = []
                break
        tool_call_names = [n for n in tool_call_names if n]
        
        tool_output = last_tool_content
        
        # 如果 last_tool_content 为空，尝试回溯查找 (兼容性处理)
        if not tool_output:
            for msg in reversed(messages):
                role, content = get_msg_role_and_content(msg)
                if role == "tool":
                    tool_output = content
                    break
                
        if tool_output:
            skill_tool_names = {
                "load_inquiry_skill_instructions",
                "load_consult_answer_skill_instructions",
                "load_emotion_support_skill_instructions",
            }

            # 检查是否为任务管理工具调用
            task_tool_called = any(is_task_tool(n) for n in tool_call_names)

            if task_tool_called:
                # 任务管理工具：返回了任务上下文，模型继续决策
                print(f"[DEBUG] MainAgent: Task tool called: {tool_call_names}")
                skills_prompt_content += f"\n\n## 📋 任务系统更新\n\n{tool_output}"
                skills_prompt_content += """

## 🟢 第二阶段执行指令 (CRITICAL)
任务切换/创建已完成。上面是最新的任务列表和当前活跃任务信息。
请**立即**基于新的任务上下文继续决策：
1. 根据 `active_task` 中的 `reasoning_notes` 理解任务进展
2. 结合用户输入和当前上下文，输出最终 JSON
3. 禁止再次调用任务管理工具（已切换完成）
"""
            elif "load_action_guide_detail" in tool_call_names:
                print("[DEBUG] MainAgent: Injecting action guide detail from tool output")
                skills_prompt_content += f"\n\n## 📌 已加载的行动指南详情\n\n{tool_output}"
                skills_prompt_content += """

## 🟢 第二阶段执行指令 (CRITICAL)
你已经成功加载了行动指南的详细内容。现在是**第二阶段**。
请**立即**基于这份指南详情 + 当前上下文，输出包含完整字段的最终 JSON。
禁止再次调用任何工具。
"""
            elif any(n in skill_tool_names for n in tool_call_names) or not tool_call_names:
                # 默认：当作 Skill 指令（向后兼容旧逻辑）
                print(f"[DEBUG] MainAgent: Injecting skill instructions from tool output")
                skills_prompt_content += f"\n\n## 🌟 已加载的 Skill 指令\n\n{tool_output}"
                skills_prompt_content += """

## 🟢 第二阶段执行指令 (CRITICAL)
你已经成功加载了 Skill 指令。现在是**第二阶段**。
请**立即**根据上面的 Skill 指令生成最终回复。

**必填项检查**：
- 如果加载了【提问 Skill】：必须生成完整的 `inquiry_card` JSON 对象，**严禁**设为 null。
- 如果加载了【咨询/陪伴 Skill】：请根据指令生成 `response`。

请忽略下方"第一阶段"的输出限制，直接输出包含完整数据的最终 JSON。
"""
            else:
                # 兜底：未知工具
                print("[DEBUG] MainAgent: Injecting generic tool output")
                skills_prompt_content += f"\n\n## 📦 已加载的工具输出\n\n{tool_output}"
                skills_prompt_content += """

## 🟢 第二阶段执行指令 (CRITICAL)
你已经成功获取到工具输出。现在是**第二阶段**。
请基于工具输出与上下文继续完成任务，输出最终 JSON，并禁止再次调用任何工具。
"""
        else:
            # 如果找不到工具输出，说明流程有问题，添加警告
            print(f"[ERROR] MainAgent: from_tool_call=True but no tool output found! This is a bug.")
            skills_prompt_content += """

## ⚠️ 系统警告
工具调用已执行，但未能获取到 tool 输出。这是一个系统错误。
请根据当前上下文自主判断并继续完成本轮输出。
"""

    # 填充 Prompt
    format_kwargs = {
        # 新版：使用分层上下文
        "user_context": context_dict.get("user_context", "暂无用户信息"),
        "status_report": context_dict.get("status_report", "暂无"),
        "action_plan": context_dict.get("action_plan", "暂无"),
        "action_guide": context_dict.get("action_guides", "暂无"),  # 向后兼容旧变量名
        "action_guides": context_dict.get("action_guides", "暂无"),  # 新变量名
        "bound_action_guides": context_dict.get("bound_action_guides", ""),
        "conversation_history": conversation_history,
        # 任务系统（Prompt 中使用）
        "task_index": context_dict.get("task_index", "暂无任务记录"),
        "active_task_payload": context_dict.get("active_task_payload", "{}"),
        # v2.1: 任务思考过程
        "task_reasoning": context_dict.get("task_reasoning", ""),
        # 向后兼容：保留旧版变量
        "user_profile": context_dict.get("user_profile", "{}"),
        # Skills 元数据 + 工具使用说明
        "skills_prompt": skills_prompt_content,
        # 子 Agent 完成信号默认值
        "completion_status": "无",
        "result_summary": "无",
    }
    
    # 如果是再决策，添加子 Agent 完成信号信息
    if from_sub_agent:
        format_kwargs["completion_status"] = state.get("completion_status", "")
        format_kwargs["result_summary"] = state.get("result_summary", "")
    
    # 如果是恢复执行，添加恢复上下文
    if is_resuming:
        format_kwargs["is_resuming"] = True
        format_kwargs["question_count"] = question_count
    
    from collections import defaultdict
    try:
        prompt = prompt_template.format(**format_kwargs)
    except Exception as e:
        # 兼容：KeyError（缺变量）、ValueError（未转义花括号）、其他格式异常
        print(f"[ERROR] MainAgent: Prompt format error: {type(e).__name__}: {e}. Trying safe format_map.")
        try:
            prompt = prompt_template.format_map(defaultdict(str, format_kwargs))
        except Exception as e2:
            print(f"[ERROR] MainAgent: Prompt safe format_map failed: {type(e2).__name__}: {e2}. Falling back to _get_default_prompt.")
            prompt_source = "fallback:_get_default_prompt(format_error)"
            prompt_fallback = True
            fallback_template = _get_default_prompt(from_sub_agent, is_resuming)
            try:
                prompt = fallback_template.format_map(defaultdict(str, format_kwargs))
            except Exception:
                # 最后兜底：至少保证能继续跑，不阻塞调试
                prompt = fallback_template
    
    # === 调用 LLM（模型自主决定是否需要工具）===
    print(f"[DEBUG] MainAgent: Invoking LLM with tool binding")
    response = llm.invoke(prompt)
    
    # 检查是否有工具调用
    if hasattr(response, "tool_calls") and response.tool_calls:
        # 模型决定调用工具，返回消息让 workflow 路由到 skill_tools
        print(f"[DEBUG] MainAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
        return {
            "messages": [response],
            "current_agent": "main_agent",  # 标记调用来源
            "_tool_caller": "main_agent",   # 显式标记工具调用来源
            "debug_log": [{
                "node": "main_agent",
                "step": "Tool Call Requested",
                "tool_calls": [tc["name"] for tc in response.tool_calls],
            }]
        }
    
    # 没有工具调用，解析响应
    result = _parse_response(response.content, state)
    
    # 记录调试日志
    result["debug_log"] = [{
        "node": "main_agent",
        "step": "Response Generated",
        "prompt_source": prompt_source,
        "prompt_fallback": prompt_fallback,
        # "prompt": prompt,  # [FIX] 移除完整 prompt 存储，防止 state 爆炸
        "response": response.content[:500] + "..." if len(response.content) > 500 else response.content,
        "parsed_result": {k: v for k, v in result.items() if k != "debug_log"}
    }]
    
    # === 处理提问逻辑 ===
    response_content = result.get("response_content", "")
    next_action = result.get("next_action", "end_turn")
    inquiry_card = result.get("inquiry_card")
    need_questions = result.get("need_questions", False)
    
    # 检查是否需要提问 (兼容 next_action="ask_user" 或 need_questions=true)
    need_to_ask = (next_action == "ask_user" or need_questions)
    
    next_streak = (streak_count + 1) if (streak_agent == "main_agent") else 1
    allow_ask = next_streak <= max_streak

    if need_to_ask and allow_ask:
        print(f"[DEBUG] MainAgent: ask_user triggered (count={question_count}/{max_questions})")
        
        # 检查是否有完整的 inquiry_card
        if inquiry_card and inquiry_card.get("questions"):
            # 提取问题列表
            questions = inquiry_card.get("questions", [])
            result["pending_questions"] = [q.get("question", "") if isinstance(q, dict) else str(q) for q in questions]
            print(f"[DEBUG] MainAgent: Generated {len(questions)} questions")
            
            # 引导语处理
            intro = inquiry_card.get("intro", "")
            if intro and not response_content.strip():
                response_content = intro
                result["response_content"] = response_content
            
            # === 设置暂停-恢复状态 ===
            result["next_action"] = "ask_user"
            result["current_agent"] = "main_agent"
            result["agent_resume_point"] = "continue_decision"
            # 连续提问计数：同一 agent 连续 +1；否则重置为 1
            result["question_streak_agent"] = "main_agent"
            result["question_streak_count"] = next_streak
            # 旧字段：保持与 streak 对齐
            result["question_count"] = next_streak
            
            print(f"[DEBUG] MainAgent: Setting pause state, will resume after user answers")

        else:
            # 没有生成完整的 inquiry_card，降级处理
            print(f"[WARNING] MainAgent: inquiry_card missing or incomplete, falling back to end_turn")
            result["next_action"] = "end_turn"
            result["inquiry_card"] = None
            result["pending_questions"] = []
            # 非提问动作：清零“连续提问计数”
            result["question_streak_agent"] = None
            result["question_streak_count"] = 0
            # 旧字段清零
            result["question_count"] = 0
    
    elif need_to_ask and not allow_ask:
        # 已达到“同一 agent 连续提问”上限：强制继续（不再 ask_user），并清零 streak
        print(f"[DEBUG] MainAgent: Reached max question streak ({max_streak}), proceeding without more questions")
        result["inquiry_card"] = None
        result["pending_questions"] = []
        result["next_action"] = "end_turn"
        result["question_streak_agent"] = None
        result["question_streak_count"] = 0
        result["question_count"] = 0
        
    else:
        # 不需要提问
        if not inquiry_card:
            result["inquiry_card"] = None
        result["pending_questions"] = []

        # 非提问动作：清零“连续提问计数”
        result["question_streak_agent"] = None
        result["question_streak_count"] = 0
        result["question_count"] = 0
        
        # 清除暂停状态（如果是从恢复执行来的）
        if is_resuming:
            result["current_agent"] = None
            result["agent_resume_point"] = None
            # 旧字段已经在上面清零；这里保留但不再重复赋值
    
    # === 处理 pending_responses ===
    # 获取当前已有的 pending_responses（可能由之前的子 Agent 添加）
    existing_responses = state.get("pending_responses", [])
    next_action = result.get("next_action", "end_turn")
    
    # 如果主 Agent 有回复内容，添加到 pending_responses
    if response_content:
        # 根据是否是再决策和下一步动作，决定 phase
        if from_sub_agent:
            # 再决策模式：根据刚完成的任务决定 phase
            result_summary = state.get("result_summary", "")
            if "现状分析" in result_summary:
                phase = "after_status"
            elif "行动规划" in result_summary:
                phase = "after_plan"
            elif "行动指南" in result_summary:
                phase = "after_guide"
            else:
                phase = "immediate"
        else:
            # 首次回复，立即展示
            phase = "immediate"
        
        result["pending_responses"] = existing_responses + [{
            "from": "main_agent", 
            "content": response_content,
            "phase": phase
        }]
        # [FIX] 使用 response.content (原始 JSON) 而不是 response_content (解析后的文本)
        # 这样 context_builder 才能从历史记录中提取 inquiry_card 等元数据
        result["messages"] = [{
            "role": "assistant",
            "content": response.content,
            "metadata": {
                "task_id": result.get("task_id", ""),
                "thought": result.get("thought", ""),
            }
        }]
        
        # 如果要调用子 Agent，记录这次回复以保持对话连贯
        if next_action in ["call_status", "call_plan", "call_guide"]:
            result["last_response_for_continuity"] = response_content
        else:
            result["last_response_for_continuity"] = None
    else:
        # 主 Agent 不说话，保留现有的 pending_responses
        result["pending_responses"] = existing_responses
        
        # [FIX] 即使 content 为空，也保留原始 response 以便记录思考过程或 tool calls
        # 但通常如果 content 为空且无 tool calls，可能是异常情况
        if response.content:
             result["messages"] = [{"role": "assistant", "content": response.content}]
        else:
             result["messages"] = []
        
        result["last_response_for_continuity"] = None
    
    # === 清除子 Agent 完成信号（再决策完成） ===
    result["completion_status"] = None
    result["result_summary"] = None
    
    # === 行动指南状态更新说明 ===
    # 根据「行动指南状态机制重构」：主 Agent 不再直接改指南状态。
    # 状态变更只能由：
    # - guide_agent 在输出 guide_status_updates 时触发；或
    # - 前端按钮调用 /api/update_guide_status 触发。
    
    # === 清除工具调用来源（防止无限循环） ===
    result["_tool_caller"] = None
    
    # === 处理任务更新（v2.1）===
    task_update = result.get("task_update", {})
    if task_update:
        task_registry_updates = _handle_task_update(state, task_update)
        if task_registry_updates:
            # 兼容：如果 layer3_memory 更新了，需要从返回结果中提取
            layer3_update = task_registry_updates.get("layer3_memory", {})
            if layer3_update:
                current_layer3 = state.get("layer3_memory", {}).copy()
                current_layer3["task_registry"] = layer3_update.get("task_registry", {})
                result["layer3_memory"] = current_layer3

    return result


def _get_skills_metadata_prompt() -> str:
    """
    获取所有 Skills 的元数据（第一层：Metadata Level）+ 工具使用说明
    
    只加载元数据，模型通过 load_skill_instructions 工具按需加载完整指令
    """
    inquiry_skill = get_inquiry_skill()
    consult_skill = get_consult_answer_skill()
    emotion_skill = get_emotion_support_skill()
    
    return f"""
---

## 📚 可用 Skills（通过工具按需加载）

{inquiry_skill.get_metadata_prompt()}
{consult_skill.get_metadata_prompt()}
{emotion_skill.get_metadata_prompt()}

### 🛠 Skill 调用规则（重要）

**当你判断需要使用某个 Skill（如你自己需要提问、需要咨询解答）时，必须优先调用对应的加载工具！**

1. **关于【提问 Skill (load_inquiry_skill_instructions)】的严格限制**：
   - ❌ **严禁**为了帮 Status/Plan/Guide Agent 收集信息而调用此 Skill。
     - *Bad Case*: "为了帮你分析现状，我先问问你们认识多久了" -> **错误！** 此时应直接 `call_status`，让 Status Agent 自己去问。
   - ✅ **仅当**你需要澄清**用户意图**（即你不知道用户想干嘛，或者需要确认是否开启新任务）或遇到只能你自己处理的问题且缺少信息时，才由你自己调用此 Skill。
     - *Good Case*: "你是想让我帮你分析一下聊天记录，还是想让我直接教你怎么回？"

2. **Skill 调用流程**：
   - 🚫 **严禁**直接输出 JSON 结果（如 `next_action="ask_user"`）。
   - ✅ **必须**先调用工具：
     - 意图不明、需要澄清 -> 调用 `load_inquiry_skill_instructions()`
     - 纯咨询、情感困惑 -> 调用 `load_consult_answer_skill_instructions()`
     - 情绪发泄、求安慰 -> 调用 `load_emotion_support_skill_instructions()`

3. **第 2 步（工具返回后）**：系统会提供完整的 Skill 指令（包含 JSON 格式规范）。
   - ✅ 此时再根据指令生成包含 `inquiry_card` 或专业回复的最终 JSON。

---
"""


def _format_history(messages: list) -> str:
    """格式化对话历史"""
    if not messages:
        return "无历史对话"
    
    # 只保留最近 10 条消息
    recent = messages[-10:]
    formatted = []
    for msg in recent:
        role = "用户" if msg["role"] == "user" else "小话"
        formatted.append(f"{role}: {msg['content']}")
    
    return "\n".join(formatted)


def _parse_response(content: str, state: AgentState) -> dict[str, Any]:
    """解析 LLM 输出"""
    try:
        # 尝试解析 JSON
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            # 尝试找到 JSON 对象
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                json_str = content[start:end]
            else:
                json_str = content
        
        data = json.loads(json_str)
        
        # 映射 next_action
        next_action_map = {
            "ask_user": "ask_user",
            "call_status": "call_status",
            "call_plan": "call_plan",
            "call_guide": "call_guide",
            "end_turn": "end_turn",
        }
        
        next_action = data.get("next_action", "end_turn")
        if next_action not in next_action_map:
            next_action = "end_turn"
        
        # response 可以为 null（可选回复）
        response_raw = data.get("response", data.get("assistant_response"))
        response_content = response_raw if response_raw else ""
        
        # 解析 inquiry_card（如果有）
        inquiry_card = data.get("inquiry_card")
        
        # 检测行动完成标记
        mark_guide_completed = data.get("mark_guide_completed", False)
        
        # 解析任务更新（v2.1）
        task_update = data.get("task_update", {})
        completed_guide_id = data.get("completed_guide_id")

        # 解析 instruction (v2.2)
        instruction = data.get("instruction")
        
        # 解析 decision_rationale (v3.0) - 仅记录日志，不存入 State
        decision_rationale = data.get("decision_rationale")
        if decision_rationale:
            print(f"[DEBUG] MainAgent OODA Rationale: {decision_rationale}")

        # 解析思考与任务 ID（用于交错式历史与按任务过滤）
        task_id = data.get("task_id")
        thought = data.get("thought")
        if not thought and isinstance(task_update, dict):
            thought = task_update.get("reasoning_note", "")
        # 向后兼容：如果没有显式 task_id，且是 new 任务，使用 task_update.task_id
        if not task_id and isinstance(task_update, dict) and task_update.get("action") == "new":
            task_id = task_update.get("task_id")
        
        return {
            "response_content": response_content,
            "next_action": next_action,
            "intent_type": data.get("intent_type", "action_trigger"),
            "need_questions": data.get("need_questions", False),
            "inquiry_card": inquiry_card,  # 渐进式加载：直接从输出获取
            "pending_questions": [],
            "mark_guide_completed": mark_guide_completed,
            "completed_guide_id": completed_guide_id,
            "task_update": task_update,  # v2.1: 任务更新
            "task_id": task_id or "",
            "thought": thought or "",
            "instruction": instruction or "",  # v2.2: 专家指令
        }
    
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        # 解析失败，返回默认值
        return {
            "response_content": content.strip() if content else "我理解你的情况了，让我想想怎么帮你。",
            "next_action": "end_turn",
            "intent_type": "action_trigger",
            "inquiry_card": None,
            "pending_questions": [],
            "user_profile": state.get("user_profile", {}),
            "task_update": {},  # v2.1: 默认空任务更新
            "task_id": "",
            "thought": "",
            "instruction": "",
        }


def _update_profile(current_profile: dict, new_info: dict) -> dict:
    """
    更新用户画像（旧版，向后兼容）
    
    @deprecated: 建议使用 _update_user_context 更新 3×3 矩阵
    """
    if not new_info:
        return current_profile
    
    updated = current_profile.copy()
    
    # 合并已知事实
    if "known_facts" in new_info:
        existing_facts = updated.get("known_facts", [])
        new_facts = new_info["known_facts"]
        updated["known_facts"] = list(set(existing_facts + new_facts))
        del new_info["known_facts"]
    
    # 更新其他字段
    updated.update(new_info)
    
    return updated


def _get_default_prompt(from_sub_agent: bool = False, is_resuming: bool = False) -> str:
    """
    获取默认 Prompt
    
    采用 Tool-based 渐进式加载模式：
    - 系统提示只包含 Skills 的元数据
    - 模型通过 load_skill_instructions 工具按需加载完整指令
    """
    base_prompt = """你是小话，一个专业的 AI 恋爱军师。你的任务是帮助用户解决与 Crush 相处过程中的情感推进问题。

## 当前用户消息
{user_message}

## 用户画像
{user_profile}

## 现状分析报告
{status_report}

## 行动规划
{action_plan}

## 行动指南
{action_guide}

## 对话历史
{conversation_history}

{skills_prompt}
"""
    
    if from_sub_agent:
        # 再决策模式：子 Agent 完成后回到主 Agent
        base_prompt += """
## 子 Agent 完成信号
- 完成状态: {completion_status}
- 结果摘要: {result_summary}

## 你的任务（再决策模式）
子 Agent 已完成任务并返回，分析结果已经更新到看板中（前端会自动展示）。
你需要：
1. 给用户一个简短的过渡或引导
2. **根据当前情况灵活决定下一步**（不要固定流程！）

## 决策原则（灵活判断，非固定流程）
- **用户之前是否表达过明确诉求**
- **当前看板状态**：哪些已有，哪些缺失
- **对话上下文**：用户的期望和情绪状态

**重要**：不要假设用户一定想要完整流程，每一步都要根据实际情况判断。

## 输出格式
```json
{{
  "task_id": "当前任务ID（沿用或新建）",
  "thought": "本轮内部思考（给系统看的，不给用户看）。要求：简短、决策导向。",
  "response": "给用户的回复",
  "intent_type": "action_trigger",
  "next_action": "ask_user|call_status|call_plan|call_guide|end_turn",
  "inquiry_card": null,
  "extracted_info": {{}}
}}
```
"""
    elif is_resuming:
        # 恢复执行模式：用户回答了之前的提问
        base_prompt += """
## 恢复执行模式
你之前向用户提问，用户已经回答了。当前是第 {question_count} 轮提问。

## 你的任务
1. 分析用户的回答，提取有用信息
2. 判断信息是否足够继续
3. 决定下一步行动

## 决策逻辑
- 如果信息仍然不足，可以继续提问（ask_user + inquiry_card）
- 如果信息足够，决定是调用子 Agent 还是直接回复
- 如果是简单咨询或情感陪伴，根据上面的 Skills 指导原则直接回复

## 输出格式
```json
{{
  "task_id": "当前任务ID（沿用或新建）",
  "thought": "本轮内部思考（给系统看的，不给用户看）。要求：简短、决策导向。",
  "response": "给用户的回复",
  "intent_type": "consult_only|emotion_vent|action_trigger|info_update",
  "next_action": "ask_user|call_status|call_plan|call_guide|end_turn",
  "inquiry_card": null,
  "extracted_info": {{}}
}}
```
"""
    else:
        # 正常模式：处理用户输入
        base_prompt += """
## 你的任务
1. **理解用户意图**：判断用户是纯咨询、情绪发泄、还是需要触发行动
2. **回应用户**：根据意图类型，使用上面对应的 Skill 指导原则生成回复
3. **决策下一步**：判断是否需要调用子 Agent 或向用户提问

## 意图分类与 Skill 使用
- `consult_only`: 纯咨询问题 → 按「解答情感疑惑 Skill」的原则回复
- `emotion_vent`: 情绪发泄/倾诉 → 按「情感陪伴 Skill」的原则回复
- `action_trigger`: 需要触发行动流程
- `info_update`: 用户提供了新信息

## 决策逻辑
- 如果是咨询/陪伴 → 直接用对应 Skill 原则生成回复，`next_action="end_turn"`
- 如果意图不明（需要澄清用户想做什么） → `next_action="ask_user"`，并填充 `inquiry_card`
- 如果信息不足以进行 Status/Plan/Guide 分析 → **不要提问**，直接路由给对应的 Agent（`call_status/plan/guide`）
- 如果需要更新看板 → 设置对应的 `next_action`

## 输出格式
```json
{{
  "task_id": "当前任务ID（沿用或新建）",
  "thought": "本轮内部思考（给系统看的，不给用户看）。要求：简短、决策导向。",
  "response": "给用户的回复（根据意图类型使用对应 Skill 原则）",
  "intent_type": "consult_only|emotion_vent|action_trigger|info_update",
  "next_action": "ask_user|call_status|call_plan|call_guide|end_turn",
  "need_questions": false,
  "inquiry_card": null
}}
```

### 🔴 重要：inquiry_card 字段规则

**只有在需要提问时才填充 `inquiry_card`**：
- 当 `next_action="ask_user"` 或 `need_questions=true` 时，才需要填充 `inquiry_card`
- 其他情况下，`inquiry_card` 必须为 `null`

**当需要提问时，`inquiry_card` 格式如下**（参考上面的「提问 Skill」完整规范）：
```json
{{
  "inquiry_card": {{
    "questions": [
      {{
        "id": "q1",
        "type": "free_input_question|single_choice|multiple_choice|private_chat_screenshot|group_chat_screenshot|moments_screenshot|other_social_media_screenshot",
        "question": "问题内容（简练、直接）",
        "info_type": 1,
        "options": ["选项1", "选项2"],
        "is_required": true,
        "purpose": "问这个问题的目的"
      }}
    ],
    "intro": "引导语（简短、有角色感）",
    "reasoning": "为什么问这些问题（内部分析）"
  }}
}}
```

**注意**：
- `response` 是给用户的回复，如果要提问，这里可以是简短的过渡语
"""
    
    return base_prompt

