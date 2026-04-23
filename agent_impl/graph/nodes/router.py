"""
前置路由节点 (Router)
负责对用户输入进行快速分类和过滤
"""

import re
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from graph.state import AgentState
from utils.reasoning_content import clear_reasoning_content


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


def router_node(state: AgentState, config: RunnableConfig | None = None) -> dict[str, Any]:
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
    from graph.state import convert_message_to_dict, get_message_id
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
    
    # 清理上一轮的 reasoning_content（根据 DeepSeek 文档，新对话开始时需要清理）
    normalized_messages = clear_reasoning_content(normalized_messages)
    state["messages"] = normalized_messages

    # 根因修复：若 user_message 为空，但 messages 已包含用户输入，则回填
    fallback_user_message = ""
    fallback_message_id = ""
    if not user_message:
        for msg in reversed(normalized_messages):
            if msg.get("role") == "user":
                content = (msg.get("content") or "").strip()
                if content:
                    fallback_user_message = content
                    fallback_message_id = get_message_id(msg)
                    break
        if fallback_user_message:
            user_message = fallback_user_message
    
    # [FIX] 状态清理：每轮开始时，确保清理上一轮的临时状态，防止上下文爆炸
    base_update = {
        "debug_log": [],
        "pending_responses": [],
        "inquiry_card": None,
        "completion_status": None,
        "result_summary": None,
        "runtime": {},
        "_iteration_count": 0,
    }
    if fallback_user_message:
        base_update["user_message"] = fallback_user_message
        if fallback_message_id and not state.get("current_message_id"):
            base_update["current_message_id"] = fallback_message_id

    # [FIX] 确保用户消息被添加到 messages 中
    # 这是关键修复：LangGraph Studio 直接传入 input 时，只有 user_message，没有 messages
    # 我们需要在这里把用户消息添加到对话历史
    existing_messages = state.get("messages", [])

    # 修剪过长的消息列表，保留最近 N 条，直接覆盖 state 内存以避免继续膨胀
    existing_messages, trimmed = _trim_messages_if_needed(existing_messages, max_messages=50)
    state["messages"] = existing_messages
    
    # [FIX-2026-01-19] 使用消息 ID 去重，避免误删“用户重复发同一句话”
    current_message_id = (
        state.get("current_message_id")
        or base_update.get("current_message_id")
        or str(uuid.uuid4())
    )
    if not state.get("current_message_id") and not base_update.get("current_message_id"):
        base_update["current_message_id"] = current_message_id
    existing_ids = {get_message_id(m) for m in existing_messages if get_message_id(m)}

    # 如果当前 message_id 已存在但内容不一致，说明是“旧 id”，需要换新 id
    if current_message_id in existing_ids and user_message:
        matched_content = ""
        for msg in existing_messages:
            if get_message_id(msg) == current_message_id:
                matched_content = (msg.get("content") or "").strip() if isinstance(msg, dict) else ""
                break
        if matched_content and matched_content != user_message.strip():
            current_message_id = str(uuid.uuid4())
            base_update["current_message_id"] = current_message_id

    need_add_user_msg = bool(user_message) and current_message_id not in existing_ids
    
    if need_add_user_msg and user_message:
        # 使用 LangGraph 的 add_messages reducer 兼容的格式
        base_update["messages"] = [{"role": "user", "content": user_message, "id": current_message_id}]

    # 同步全量存储：默认情况下使用已有 messages + 本轮待添加的用户消息
    merged_messages = list(existing_messages)
    if base_update.get("messages"):
        merged_messages = merged_messages + base_update["messages"]

    # === 行动反馈入口处理 ===
    feedback_mode_input = state.get("feedback_mode_input")
    if isinstance(feedback_mode_input, dict):
        guide_id = str(feedback_mode_input.get("guide_id") or "").strip()
        if guide_id:
            feedback_mode = dict(state.get("feedback_mode") or {})
            feedback_mode["guide_id"] = guide_id
            if feedback_mode_input.get("completion_status"):
                feedback_mode["prefilled_status"] = feedback_mode_input.get("completion_status")
            if feedback_mode_input.get("completion_detail"):
                feedback_mode["prefilled_detail"] = feedback_mode_input.get("completion_detail")
            if not feedback_mode.get("phase"):
                feedback_mode["phase"] = "initial"
            if not feedback_mode.get("start_message_id"):
                feedback_mode["start_message_id"] = current_message_id
            base_update["feedback_mode"] = feedback_mode
            base_update["feedback_mode_input"] = None
            base_update["feedback_status"] = None
            base_update["feedback_question"] = None
    else:
        base_update["feedback_mode_input"] = None

    # 若用户未从反馈入口进入，检查是否处于追问阶段
    if not isinstance(feedback_mode_input, dict) and state.get("feedback_mode"):
        existing_feedback_mode = state.get("feedback_mode") or {}
        existing_feedback_status = state.get("feedback_status")
        
        # 如果处于追问阶段，保留 feedback_mode，不清除
        if existing_feedback_status == "asking" or existing_feedback_mode.get("phase") == "followup":
            # 保留现有 feedback_mode，不做任何清除
            pass
        else:
            # 不在追问阶段，正常清除
            base_update["feedback_mode"] = None
            base_update["feedback_status"] = None
            base_update["feedback_question"] = None
    
    # 1. 风控过滤
    if _check_blocked(user_message):
        response_content = "我注意到你可能正在经历一些困难的时刻。如果你需要专业帮助，请联系专业的心理咨询师或拨打心理援助热线。我在这里支持你。"
        # [FIX] 构建消息列表：先添加用户消息，再添加助手回复
        messages_to_add = []
        if need_add_user_msg and user_message:
            messages_to_add.append({"role": "user", "content": user_message, "id": current_message_id})
        messages_to_add.append({"role": "assistant", "name": "router", "content": response_content})
        
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
            messages_to_add.append({"role": "user", "content": user_message, "id": current_message_id})
        messages_to_add.append({"role": "assistant", "name": "router", "content": response_content})
        
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

    # 反馈模式：强制路由给 guide_agent
    feedback_mode = base_update.get("feedback_mode") or state.get("feedback_mode")
    if feedback_mode:
        return {
            **base_update,
            "route_to": "guide_agent",
            "debug_log": [{
                "node": "router",
                "step": "Feedback Mode",
                "response": f"guide_id={feedback_mode.get('guide_id', '')}",
            }],
        }
    
    # 3. 业务相关，先决定是否需要 Onboarding，再转发
    # 注意：Onboarding v2 上线后，create_initial_state 默认 onboarding_completed=True，
    # 理论上 go_onboarding 永远为 False。若仍被触发为 True，说明某条上游链路
    # 绕过了默认值，应当告警以便排查老子图被误触发的情况。
    go_onboarding = not state.get("onboarding_completed", False)
    if go_onboarding:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "router_node: unexpected go_onboarding=True after onboarding_v2 migration. "
            "onboarding_completed=%s, route_to=onboarding (legacy subgraph). "
            "Check caller/create_initial_state for missing defaults.",
            state.get("onboarding_completed"),
        )

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
