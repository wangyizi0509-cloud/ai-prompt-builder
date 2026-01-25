from typing import Any

def get_msg_role_and_content(msg: Any) -> tuple[str, str]:
    """
    从消息对象或字典中提取角色和内容
    兼容 LangChain 消息对象和 TypedDict
    """
    if isinstance(msg, dict):
        # 优先使用 role，如果 role 为空/None，回退到 type 字段
        role = msg.get("role") or msg.get("type") or ""
        content = msg.get("content") or ""
        if role == "human":
            role = "user"
        elif role == "ai":
            role = "assistant"
        # 处理 tool 角色可能在 content 中为空，但在其他字段中有信息的情况
        if role == "tool" and not content:
            content = msg.get("tool_output", "")
        return role, content
    
    # 假设是 LangChain 消息对象 (BaseMessage)
    role = getattr(msg, "type", "")
    if role == "human":
        role = "user"
    elif role == "ai":
        role = "assistant"
    elif role == "system":
        role = "system"
    elif role == "tool":
        role = "tool"
    
    content = getattr(msg, "content", "")
    
    return role, content


def count_user_turns(messages: list) -> int:
    """
    统计消息列表中用户消息的数量（轮次）
    
    一"轮"以用户发送的消息为基准，不论这条消息后面有多少个 Agent 回复。
    这样可以确保轮次计算与用户的实际交互次数一致。
    
    Args:
        messages: 消息列表
    
    Returns:
        用户消息数量
    """
    count = 0
    for msg in messages:
        role, _ = get_msg_role_and_content(msg)
        if role == "user":
            count += 1
    return count

