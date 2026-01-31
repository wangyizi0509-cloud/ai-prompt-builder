"""
主 Agent 节点 (Main Agent)
决策中枢，负责回应用户和决策下一步行动

支持的功能：
1. 回应用户（简短、共情、承上启下）
2. 决策下一步行动（调用子 Agent 或结束本轮）
3. 子 Agent 返回后再决策（灵活判断，无固定流程）
4. 根据意图类型使用咨询 Skills 直接回复（解答疑惑、情感陪伴）

上下文架构更新 (v2.0)：
- 使用分层上下文架构（Layer 0-4）
- 通过 context_builder 统一组装上下文

任务管理更新 (v2.1)：
- 任务边界：由模型判断（继续/新建/完成）
- 思考过程：同一任务内保留，任务切换时归档（不删除）
- 任务 ID：语义化命名（如"判断crush是否喜欢用户"）
"""

import json
import re
import uuid
from typing import Any

from graph.state import AgentState
from graph.message_builder import build_messages_for_model
from graph.tools.task_tools import create_task_tools
from graph.tools.context_loader import create_context_loader
from graph.tools.delegate_tools import (
    delegate_to_status,
    delegate_to_plan,
    delegate_to_guide,
    delegate_for_feedback,
    end_turn,
)
from graph.tools.ask_tool import get_ask_tool
from graph.tools.consult_answer_tool import get_consult_tool, consult_complete
from graph.tools.emotion_support_tool import get_emotion_tool, emotion_complete
from skills.registry import get_skill_registry
from utils.message_utils import get_msg_role_and_content
from config import get_llm, get_thinking_llm, is_thinking_with_tools_enabled
from langchain_core.messages import AIMessage


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


def _extract_reasoning_content(response) -> str | None:
    if response is None:
        return None
    additional_kwargs = getattr(response, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict) and additional_kwargs.get("reasoning_content"):
        return additional_kwargs.get("reasoning_content")
    return getattr(response, "reasoning_content", None)



def main_agent_node(state: AgentState) -> dict[str, Any]:
    """
    主 Agent 节点
    
    职责：
    1. 回应用户（简短、共情、承上启下）
    2. 决策下一步行动（调用子 Agent 或结束本轮）
    3. 子 Agent 返回后再决策（灵活判断，无固定流程）
    4. 使用咨询 Skills 直接回复（解答疑惑、情感陪伴）
    
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

    # 准备 LLM（工具绑定在决策后进行）
    # 如果启用了思考模式+工具调用，使用 get_thinking_llm
    if is_thinking_with_tools_enabled():
        base_llm = get_thinking_llm(temperature=0.7)
    else:
        base_llm = get_llm(temperature=0.7, use_tools=True)
    
    # 创建任务管理工具（需要 state_getter 来获取当前状态）
    task_tools = create_task_tools(lambda: state, agent_name="main_agent")
    
    # 获取当前 ask_mode 状态，决定使用哪个版本的 ask 工具
    ask_mode = state.get("ask_mode", False)
    ask_tool = get_ask_tool(ask_mode)
    
    # 获取当前 consult_mode 状态，决定使用哪个版本的 consult_answer 工具
    consult_mode = state.get("consult_mode", False)
    consult_tool = get_consult_tool(consult_mode)
    
    # 获取当前 emotion_mode 状态，决定使用哪个版本的 emotion_support 工具
    emotion_mode = state.get("emotion_mode", False)
    emotion_tool = get_emotion_tool(emotion_mode)
    
    tool_list = [
        # 子 Agent 委派工具
        delegate_to_status,
        delegate_to_plan,
        delegate_to_guide,
        delegate_for_feedback,
        # 结束本轮工具（不输出内容直接结束）
        end_turn,
        # 提问工具（状态驱动，根据 ask_mode 返回不同版本）
        ask_tool,
        # 解答工具（状态驱动，根据 consult_mode 返回不同版本）
        consult_tool,
        # 陪伴工具（状态驱动，根据 emotion_mode 返回不同版本）
        emotion_tool,
        # 通用上下文拉取工具
        create_context_loader(lambda: state, "main_agent"),
        # 任务管理工具
        *task_tools,
    ]
    if from_tool_call:
        print(f"[DEBUG] MainAgent: Detected return from tool call (from_tool_call)")
    
    if is_resuming:
        print(f"[DEBUG] MainAgent: Resuming from ask_user, question_count={state.get('question_count', 0)}")
    elif from_sub_agent:
        print(f"[DEBUG] MainAgent: Re-decision after sub-agent, status={state.get('completion_status')}, summary={state.get('result_summary')}")
    elif from_tool_call:
        print(f"[DEBUG] MainAgent: Continuing after tool call (last_role={last_msg_role})")
    
    # [FIX] 当从工具调用返回时，不应该再次添加用户的上一条输入
    # 否则模型会看到错误的消息栈，误以为用户已确认，跳过提问
    current_input = "" if from_tool_call else state.get("user_message", "")
    
    # 使用 message_builder 构建标准消息列表
    messages = build_messages_for_model(
        state=state,
        agent_name="main_agent",
        current_input=current_input,
    )
    prompt_source = "message_builder"
    prompt_fallback = False
    
    # === 调用 LLM（两段式：先决策，后工具）===
    print(f"[DEBUG] MainAgent: Invoking LLM (from_tool_call={from_tool_call}, ask_mode={ask_mode})")
    response = None
    result = None
    pending_action = state.get("_pending_action") or ""
    
    # Phase 2: ask_mode=True 后强制调用 ask 工具生成 inquiry_card
    if from_tool_call and pending_action == "ask":
        # 此时 ask_mode=True，ask_tool 是完整 schema 版本
        ask_full_tool = get_ask_tool(True)  # 确保使用完整版
        llm_with_tools = base_llm.bind_tools(
            [ask_full_tool],
            tool_choice={"type": "function", "function": {"name": "ask"}},
        )
        response = llm_with_tools.invoke(messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print("[DEBUG] MainAgent: Forced ask tool call (Phase 2: generate inquiry_card)")
            if hasattr(response, "name"):
                response.name = "main_agent"
            reasoning_content = _extract_reasoning_content(response)
            return {
                "messages": [response],
                "current_agent": "main_agent",
                "_tool_caller": "main_agent",
                "_reasoning_content_cache": reasoning_content,
                "debug_log": [{
                    "node": "main_agent",
                    "step": "Tool Call Requested (ask forced, Phase 2)",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }]
            }
    
    elif from_tool_call and (consult_mode or emotion_mode or pending_action in {"consult_answer", "emotion_support"}):
        # Phase 2: consult/emotion 两阶段技能
        # 绑定对应的 complete 工具，让模型可以正常输出 content + tool_call(complete)
        # 注意：不能不绑定工具，否则 DeepSeek 会在 content 里硬写 DSML 格式的工具调用
        if consult_mode:
            llm_with_complete = base_llm.bind_tools([consult_complete])
        elif emotion_mode:
            llm_with_complete = base_llm.bind_tools([emotion_complete])
        else:
            # fallback: 绑定完整工具列表（理论上不会走到这里）
            llm_with_complete = base_llm.bind_tools(tool_list)
        response = llm_with_complete.invoke(messages)
        # 如果模型返回了 tool_calls（complete），立即返回处理
        if hasattr(response, "tool_calls") and response.tool_calls:
            mode_name = "consult" if consult_mode else "emotion"
            print(f"[DEBUG] MainAgent: Model returned tool call in {mode_name}_mode Phase 2: {[tc['name'] for tc in response.tool_calls]}")
            if hasattr(response, "name"):
                response.name = "main_agent"
            reasoning_content = _extract_reasoning_content(response)
            existing_responses = state.get("pending_responses", [])
            response_content = response.content or ""
            if response_content:
                pending_responses = existing_responses + [{
                    "from": "main_agent",
                    "content": response_content,
                    "phase": "immediate",
                }]
            else:
                pending_responses = existing_responses
            return {
                "messages": [response],
                "pending_responses": pending_responses,
                "last_response_for_continuity": response_content or None,
                "current_agent": "main_agent",
                "_tool_caller": "main_agent",
                "_reasoning_content_cache": reasoning_content,
                "debug_log": [{
                    "node": "main_agent",
                    "step": f"Tool Call Requested ({mode_name}_mode Phase 2)",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }]
            }
        # 如果模型没有返回 tool_calls，继续往下走到兜底逻辑
    elif from_tool_call:
        # 非两阶段：允许链式工具调用（比如 task_manager -> delegate_to_status）
        llm_with_tools = base_llm.bind_tools(tool_list)
        response = llm_with_tools.invoke(messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"[DEBUG] MainAgent: Model requested tool call (chain): {[tc['name'] for tc in response.tool_calls]}")
            if hasattr(response, "name"):
                response.name = "main_agent"
            reasoning_content = _extract_reasoning_content(response)
            return {
                "messages": [response],
                "current_agent": "main_agent",
                "_tool_caller": "main_agent",
                "_reasoning_content_cache": reasoning_content,
                "debug_log": [{
                    "node": "main_agent",
                    "step": "Tool Call Requested (chain)",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }]
            }
    else:
        # 系统验收：用户明确要求调用 task_manager 时，直接生成 tool_call
        user_msg = state.get("user_message") if isinstance(state.get("user_message"), str) else ""
        if "task_manager" in user_msg and "action" in user_msg:
            def _extract_arg(pattern: str) -> str:
                match = re.search(pattern, user_msg, flags=re.IGNORECASE)
                return match.group(1).strip() if match else ""
            action = _extract_arg(r'action\s*=\s*"([^"]+)"') or _extract_arg(r"action\s*=\s*'([^']+)'")
            if action:
                task_id = _extract_arg(r'task_id\s*=\s*"([^"]+)"') or _extract_arg(r"task_id\s*=\s*'([^']+)'")
                title = _extract_arg(r'title\s*=\s*"([^"]+)"') or _extract_arg(r"title\s*=\s*'([^']+)'")
                summary = _extract_arg(r'summary\s*=\s*"([^"]+)"') or _extract_arg(r"summary\s*=\s*'([^']+)'")
                note = _extract_arg(r'note\s*=\s*"([^"]+)"') or _extract_arg(r"note\s*=\s*'([^']+)'")
                tool_args = {
                    "action": action,
                    "task_id": task_id,
                    "title": title,
                    "summary": summary,
                    "note": note,
                }
                tool_call = {"id": f"call_{uuid.uuid4().hex[:8]}", "name": "task_manager", "args": tool_args}
                response = AIMessage(content="", tool_calls=[tool_call], name="main_agent")
                return {
                    "messages": [response],
                    "current_agent": "main_agent",
                    "_tool_caller": "main_agent",
                    "_reasoning_content_cache": None,
                    "debug_log": [{
                        "node": "main_agent",
                        "step": "Tool Call Requested (forced)",
                        "tool_calls": ["task_manager"],
                        "tool_args": tool_args,
                    }]
                }
        force_tool_name = None
        if isinstance(state.get("user_message"), str):
            msg = state.get("user_message", "")
            if "task_manager" in msg and "action" in msg:
                force_tool_name = "task_manager"
        if force_tool_name:
            try:
                llm_with_tools = base_llm.bind_tools(
                    tool_list,
                    tool_choice={"type": "function", "function": {"name": force_tool_name}},
                )
            except Exception:
                llm_with_tools = base_llm.bind_tools(tool_list)
        else:
            llm_with_tools = base_llm.bind_tools(tool_list)
        response = llm_with_tools.invoke(messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            # 模型决定调用工具，返回消息让 workflow 路由到 skill_tools
            print(f"[DEBUG] MainAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
            if hasattr(response, "name"):
                response.name = "main_agent"
            reasoning_content = _extract_reasoning_content(response)
            return {
                "messages": [response],
                "current_agent": "main_agent",  # 标记调用来源
                "_tool_caller": "main_agent",   # 显式标记工具调用来源
                "_reasoning_content_cache": reasoning_content,
                "debug_log": [{
                    "node": "main_agent",
                    "step": "Tool Call Requested",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }]
            }
    
    # === 兜底重试：consult_mode/emotion_mode 下模型忘记调用 complete ===
    # 检查是否有 complete 调用
    def _has_complete_call(resp, tool_name: str) -> bool:
        if not hasattr(resp, "tool_calls") or not resp.tool_calls:
            return False
        for tc in resp.tool_calls:
            if tc.get("name") == tool_name and tc.get("args", {}).get("action") == "complete":
                return True
        return False
    
    # consult_mode 兜底：有 content 但没有 complete 调用
    if consult_mode and response and response.content and not _has_complete_call(response, "consult_answer"):
        print(f"[DEBUG] MainAgent: consult_mode retry - model forgot to call complete, forcing...")
        original_content = response.content
        
        # 重试：强制调用 complete
        retry_llm = base_llm.bind_tools(
            [consult_complete],
            tool_choice={"type": "function", "function": {"name": "consult_answer"}},
        )
        retry_response = retry_llm.invoke(messages + [response])
        
        # 合并：原始 content + 重试的 tool_calls
        if hasattr(retry_response, "tool_calls") and retry_response.tool_calls:
            reasoning_content = _extract_reasoning_content(retry_response)
            additional_kwargs = {"reasoning_content": reasoning_content} if reasoning_content else None
            merged_response = AIMessage(
                content=original_content,
                tool_calls=retry_response.tool_calls,
                name="main_agent",
                additional_kwargs=additional_kwargs,
            )
            print(f"[DEBUG] MainAgent: consult_mode retry successful, merged response")
            return {
                "messages": [merged_response],
                "current_agent": "main_agent",
                "_tool_caller": "main_agent",
                "_reasoning_content_cache": reasoning_content,
                "debug_log": [{
                    "node": "main_agent",
                    "step": "Tool Call Requested (consult_answer complete forced, retry)",
                    "tool_calls": [tc["name"] for tc in retry_response.tool_calls],
                }]
            }
    
    # emotion_mode 兜底：有 content 但没有 complete 调用
    if emotion_mode and response and response.content and not _has_complete_call(response, "emotion_support"):
        print(f"[DEBUG] MainAgent: emotion_mode retry - model forgot to call complete, forcing...")
        original_content = response.content
        
        # 重试：强制调用 complete
        retry_llm = base_llm.bind_tools(
            [emotion_complete],
            tool_choice={"type": "function", "function": {"name": "emotion_support"}},
        )
        retry_response = retry_llm.invoke(messages + [response])
        
        # 合并：原始 content + 重试的 tool_calls
        if hasattr(retry_response, "tool_calls") and retry_response.tool_calls:
            reasoning_content = _extract_reasoning_content(retry_response)
            additional_kwargs = {"reasoning_content": reasoning_content} if reasoning_content else None
            merged_response = AIMessage(
                content=original_content,
                tool_calls=retry_response.tool_calls,
                name="main_agent",
                additional_kwargs=additional_kwargs,
            )
            print(f"[DEBUG] MainAgent: emotion_mode retry successful, merged response")
            return {
                "messages": [merged_response],
                "current_agent": "main_agent",
                "_tool_caller": "main_agent",
                "_reasoning_content_cache": reasoning_content,
                "debug_log": [{
                    "node": "main_agent",
                    "step": "Tool Call Requested (emotion_support complete forced, retry)",
                    "tool_calls": [tc["name"] for tc in retry_response.tool_calls],
                }]
            }
    
    # 解析响应（若决策已解析则复用）
    if result is None:
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
    
    # === 提问逻辑由 ask_user 工具负责 ===
    response_content = result.get("response_content", "")
    # === 处理 pending_responses ===
    # 获取当前已有的 pending_responses（可能由之前的子 Agent 添加）
    existing_responses = state.get("pending_responses", [])
    
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
        reasoning_content = _extract_reasoning_content(response)
        additional_kwargs = {"reasoning_content": reasoning_content} if reasoning_content else None
        # [FIX] 使用 response.content (原始 JSON) 而不是 response_content (解析后的文本)
        # 这样 context_builder 才能从历史记录中提取 inquiry_card 等元数据
        message_payload = {
            "role": "assistant",
            "name": "main_agent",
            "content": response.content,
            "metadata": {
                "task_id": result.get("task_id", ""),
                "thought": result.get("thought", ""),
            }
        }
        if additional_kwargs:
            message_payload["additional_kwargs"] = additional_kwargs
        result["messages"] = [message_payload]
        result["_reasoning_content_cache"] = reasoning_content
        
        # 记录本轮回复用于连贯性
        result["last_response_for_continuity"] = response_content
    else:
        # 主 Agent 不说话，保留现有的 pending_responses
        result["pending_responses"] = existing_responses
        
        # [FIX] 即使 content 为空，也保留原始 response 以便记录思考过程或 tool calls
        # 但通常如果 content 为空且无 tool calls，可能是异常情况
        if response.content:
             reasoning_content = _extract_reasoning_content(response)
             message_payload = {"role": "assistant", "name": "main_agent", "content": response.content}
             if reasoning_content:
                 message_payload["additional_kwargs"] = {"reasoning_content": reasoning_content}
             result["messages"] = [message_payload]
             result["_reasoning_content_cache"] = reasoning_content
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
    
    return result


def _get_skills_metadata_prompt() -> str:
    """
    获取所有 Skills 的元数据（第一层：Metadata Level）
    """
    registry = get_skill_registry()
    skills_metadata = registry.generate_metadata_prompt()
    
    return f"""
---

## 📚 可用 Skills

{skills_metadata}

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
        
        # response 可以为 null（可选回复）
        response_raw = data.get("response", data.get("assistant_response"))
        response_content = response_raw if response_raw else ""

        # 解析 decision_rationale (v3.0) - 仅记录日志，不存入 State
        decision_rationale = data.get("decision_rationale")
        if decision_rationale:
            print(f"[DEBUG] MainAgent OODA Rationale: {decision_rationale}")

        # 解析思考与任务 ID
        task_id = data.get("task_id")
        thought = data.get("thought")
        
        return {
            "response_content": response_content,
            "intent_type": data.get("intent_type", "action_trigger"),
            "task_id": task_id or "",
            "thought": thought or "",
        }
    
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        # 解析失败，返回默认值
        return {
            "response_content": content.strip() if content else "我理解你的情况了，让我想想怎么帮你。",
            "intent_type": "action_trigger",
            "user_profile": state.get("user_profile", {}),
            "task_id": "",
            "thought": "",
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
    
    采用 Tool-based 两阶段工具模式：
    - ask / consult_answer / emotion_support 通过工具驱动
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
默认情况下你**不需要**给用户再解释报告/指南内容。
你需要做的是：**判断本轮是否真的需要你说话或采取新动作**。

### 默认策略（减压）
- **如果你没有新增决策/提问/行动要补充**（子 Agent 已经把产出写入系统、并且也可能已对用户做了说明）→ 直接 `next_action="end_turn"`，并将 `response` 留空字符串 `""`。
- **只有在确实需要时才说一句话**：例如需要用户下一步反馈、需要澄清一个关键点、或需要再次路由到另一个 Agent。

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
  "inquiry_card": null
}}
```

### 🔴 重要：inquiry_card 字段规则

**只有在需要提问时才填充 `inquiry_card`**：
- 当 `next_action="ask_user"` 时，才需要填充 `inquiry_card`
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

