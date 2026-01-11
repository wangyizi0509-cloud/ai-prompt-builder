"""
前置路由节点 (Router)
负责对用户输入进行快速分类和过滤
"""

import re
from typing import Any

from graph.state import AgentState


# 风控关键词列表
BLOCKED_KEYWORDS = [
    "自杀", "自残", "伤害自己",
    # 可以根据需要扩展
]

# 纯闲聊模式的触发词
SMALL_TALK_PATTERNS = [
    r"^(你好|hi|hello|嗨|在吗)[\?？!！。]*$",
    r"^(谢谢|thanks|thx|感谢).*$",
    r"^(再见|拜拜|bye|晚安|早安).*$",
]


def router_node(state: AgentState) -> dict[str, Any]:
    """
    前置路由节点
    
    职责：
    1. 风控过滤：识别敏感内容
    2. 闲聊分流：识别纯闲聊内容
    3. 业务识别：将业务相关内容转发给主 Agent
    4. 状态清理：清理上一轮残留的调试信息和临时状态
    5. [FIX] 确保用户消息被添加到对话历史
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    user_message = state.get("user_message", "").strip()

    # 统一现有 messages 为 dict，防止混入 LangChain Message 对象
    existing_messages = state.get("messages", [])
    from graph.state import convert_message_to_dict
    normalized_messages = []
    for m in existing_messages:
        try:
            msg = convert_message_to_dict(m)
            role = msg.get("role")
            if role == "human":
                msg["role"] = "user"
            elif role == "ai":
                msg["role"] = "assistant"
            normalized_messages.append(msg)
        except Exception:
            # 最小容错
            if isinstance(m, dict):
                role = m.get("role")
                if role == "human":
                    m["role"] = "user"
                elif role == "ai":
                    m["role"] = "assistant"
                normalized_messages.append(m)
            elif hasattr(m, "content"):
                role = getattr(m, "type", getattr(m, "role", "assistant"))
                if role == "human":
                    role = "user"
                elif role == "ai":
                    role = "assistant"
                normalized_messages.append({"role": role, "content": m.content})
    state["messages"] = normalized_messages
    
    # [FIX] 状态清理：每轮开始时，确保清理上一轮的临时状态，防止上下文爆炸
    base_update = {
        "debug_log": [],  # 重置调试日志
        "pending_responses": [],  # 重置本轮回复
        "inquiry_card": None,  # 重置提问卡片
        "pending_questions": [],  # 重置待提问
        "completion_status": None,  # 重置子 Agent 信号
        "result_summary": None,
        "_tool_caller": None,  # [FIX] 重置工具调用标记，防止 Skill 指令一直挂着
    }

    # [v3.0] instruction 属于“主 Agent -> 专家”的临时 Brief：
    # - 非 resume 场景：每轮开头清空，避免跨轮次残留导致下游误用旧指令
    # - resume 场景：保留，用于子 Agent 提问后继续执行时保持任务连贯
    is_resuming = bool(state.get("current_agent") and state.get("agent_resume_point"))
    if not is_resuming:
        base_update["instruction"] = None

    # 如果 Onboarding 已完成，携带 handoff 给主 Agent，并保留 Onboarding 的即时回复
    onboarding_handoff = state.get("onboarding_handoff")
    if state.get("onboarding_completed") and onboarding_handoff:
        base_update["onboarding_handoff"] = onboarding_handoff

        pending_from_onboarding = state.get("pending_responses") or []
        if pending_from_onboarding:
            base_update["pending_responses"] = pending_from_onboarding

        base_update["debug_log"].append({
            "node": "router",
            "step": "Onboarding Handoff",
            "suggested_action": onboarding_handoff.get("suggested_action"),
            "reason": onboarding_handoff.get("reason"),
        })
    
    # [FIX] 确保用户消息被添加到 messages 中
    # 这是关键修复：LangGraph Studio 直接传入 input 时，只有 user_message，没有 messages
    # 我们需要在这里把用户消息添加到对话历史
    existing_messages = state.get("messages", [])

    # 修剪过长的消息列表，保留最近 N 条，直接覆盖 state 内存以避免继续膨胀
    existing_messages, trimmed = _trim_messages_if_needed(existing_messages, max_messages=50)
    state["messages"] = existing_messages
    
    # 检查最后一条消息是否已经是这条用户消息（避免重复添加）
    need_add_user_msg = True
    if existing_messages:
        last_msg = existing_messages[-1]
        # 兼容多种消息格式
        if hasattr(last_msg, "content"):
            last_content = last_msg.content
            last_role = getattr(last_msg, "type", "unknown")
        elif isinstance(last_msg, dict):
            last_content = last_msg.get("content", "")
            last_role = last_msg.get("role", "unknown")
        else:
            last_content = ""
            last_role = "unknown"
        
        # 如果最后一条消息就是当前用户消息，不重复添加
        if last_role in ("user", "human") and last_content.strip() == user_message:
            need_add_user_msg = False
    
    if need_add_user_msg and user_message:
        # 使用 LangGraph 的 add_messages reducer 兼容的格式
        base_update["messages"] = [{"role": "user", "content": user_message}]

    # 同步全量存储：默认情况下使用已有 messages + 本轮待添加的用户消息
    merged_messages = list(existing_messages)
    if base_update.get("messages"):
        merged_messages = merged_messages + base_update["messages"]
    
    # 1. 风控过滤
    if _check_blocked(user_message):
        response_content = "我注意到你可能正在经历一些困难的时刻。如果你需要专业帮助，请联系专业的心理咨询师或拨打心理援助热线。我在这里支持你。"
        # [FIX] 构建消息列表：先添加用户消息，再添加助手回复
        messages_to_add = []
        if need_add_user_msg and user_message:
            messages_to_add.append({"role": "user", "content": user_message})
        messages_to_add.append({"role": "assistant", "content": response_content})
        
        return {
            **base_update,
            "pending_responses": [{"from": "router", "content": response_content, "phase": "immediate"}],
            "next_action": "end_turn",
            "route_to": "end",
            "messages": messages_to_add,
            "debug_log": [{
                "node": "router",
                "step": "Risk Control",
                "response": "触发风控关键词",
            }],
        }
    
    # 2. 闲聊识别
    if _is_small_talk(user_message):
        response_content = _handle_small_talk(user_message)
        # [FIX] 构建消息列表：先添加用户消息，再添加助手回复
        messages_to_add = []
        if need_add_user_msg and user_message:
            messages_to_add.append({"role": "user", "content": user_message})
        messages_to_add.append({"role": "assistant", "content": response_content})
        
        return {
            **base_update,
            "pending_responses": [{"from": "router", "content": response_content, "phase": "immediate"}],
            "next_action": "end_turn",
            "route_to": "end",
            "messages": messages_to_add,
            "debug_log": [{
                "node": "router",
                "step": "Small Talk",
                "response": response_content,
            }],
        }
    
    # 3. 业务相关，先决定是否需要 Onboarding，再转发
    go_onboarding = not state.get("onboarding_completed", False)

    # 确保 messages 为列表（避免上一轮未携带）
    if "messages" not in base_update and not state.get("messages"):
        base_update["messages"] = []

    return {
        **base_update,
        "route_to": "onboarding" if go_onboarding else "main_agent",
        "debug_log": [{
            "node": "router",
            "step": "Route Decision",
            "response": "触发 Onboarding" if go_onboarding else "业务相关，转发给 main_agent",
        }],
    }


def _trim_messages_if_needed(messages: list, max_messages: int = 50) -> tuple[list, bool]:
    """
    如果消息超过阈值，保留最近 max_messages 条。
    返回 (trimmed_messages, 是否发生修剪)
    """
    if not messages or len(messages) <= max_messages:
        return messages, False
    return messages[-max_messages:], True


def _check_blocked(message: str) -> bool:
    """检查是否包含风控关键词"""
    message_lower = message.lower()
    for keyword in BLOCKED_KEYWORDS:
        if keyword in message_lower:
            return True
    return False


def _is_small_talk(message: str) -> bool:
    """检查是否是纯闲聊"""
    message_lower = message.lower().strip()
    
    # 如果消息太长，不太可能是纯闲聊
    if len(message) > 20:
        return False
    
    for pattern in SMALL_TALK_PATTERNS:
        if re.match(pattern, message_lower, re.IGNORECASE):
            return True
    
    return False


def _handle_small_talk(message: str) -> str:
    """处理闲聊消息"""
    message_lower = message.lower().strip()
    
    # 问候
    if re.match(r"^(你好|hi|hello|嗨|在吗)", message_lower):
        return "你好呀！我是小话，你的 AI 恋爱军师 💕 有什么想聊的吗？"
    
    # 感谢
    if re.match(r"^(谢谢|thanks|thx|感谢)", message_lower):
        return "不客气！能帮到你我很开心 😊 还有什么我能帮你的吗？"
    
    # 告别
    if re.match(r"^(再见|拜拜|bye)", message_lower):
        return "好的，有任何问题随时来找我！祝你好运 ✨"
    
    # 早晚安
    if "晚安" in message_lower:
        return "晚安！做个好梦 🌙 明天继续加油！"
    if "早安" in message_lower:
        return "早安！新的一天，新的机会 ☀️ 今天有什么计划吗？"
    
    return "你好！有什么我能帮你的吗？"

