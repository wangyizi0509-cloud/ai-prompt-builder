from typing import Any

def get_msg_role_and_content(msg: Any) -> tuple[str, str]:
    """
    从消息对象或字典中提取角色和内容
    兼容 LangChain 消息对象和 TypedDict
    """
    if isinstance(msg, dict):
        role = msg.get("role", "")
        content = msg.get("content", "")
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
    
    # 特殊处理：如果是 AI 消息且包含工具调用
    if (role == "assistant" or role == "ai"):
        tool_calls = getattr(msg, "tool_calls", [])
        if tool_calls and not content:
            # 格式化工具调用信息，让模型在历史中能看到自己刚才的动作
            calls = []
            for tc in tool_calls:
                name = tc.get("name", "unknown")
                calls.append(f"{name}")
            content = f"[已发起工具调用: {', '.join(calls)}]"
        elif tool_calls:
            # 如果既有内容又有调用，也补充一下
            calls = [tc.get("name", "unknown") for tc in tool_calls]
            content = f"{content}\n[附带工具调用: {', '.join(calls)}]"
            
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

