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
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    user_message = state.get("user_message", "").strip()
    
    # 1. 风控过滤
    if _check_blocked(user_message):
        response_content = "我注意到你可能正在经历一些困难的时刻。如果你需要专业帮助，请联系专业的心理咨询师或拨打心理援助热线。我在这里支持你。"
        return {
            "pending_responses": [{"from": "router", "content": response_content, "phase": "immediate"}],
            "next_action": "end_turn",
            "route_to": "end",
            "messages": [{"role": "assistant", "content": response_content}],
            "debug_log": [{
                "node": "router",
                "step": "Risk Control",
                "prompt": f"User message: {user_message}",
                "response": "触发风控关键词",
                "parsed_result": {"route_to": "end", "reason": "blocked_keywords"}
            }],
        }
    
    # 2. 闲聊识别
    if _is_small_talk(user_message):
        response_content = _handle_small_talk(user_message)
        return {
            "pending_responses": [{"from": "router", "content": response_content, "phase": "immediate"}],
            "next_action": "end_turn",
            "route_to": "end",
            "messages": [{"role": "assistant", "content": response_content}],
            "debug_log": [{
                "node": "router",
                "step": "Small Talk",
                "prompt": f"User message: {user_message}",
                "response": response_content,
                "parsed_result": {"route_to": "end", "reason": "small_talk"}
            }],
        }
    
    # 3. 业务相关，转发给主 Agent
    return {
        "route_to": "main_agent",
        "debug_log": [{
            "node": "router",
            "step": "Route Decision",
            "prompt": f"User message: {user_message}",
            "response": "业务相关，转发给 main_agent",
            "parsed_result": {"route_to": "main_agent"}
        }],
    }


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

