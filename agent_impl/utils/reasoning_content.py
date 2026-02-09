"""
Reasoning Content 管理工具

处理 DeepSeek Reasoner 模型的 reasoning_content：
1. 回传逻辑：工具调用场景下，需要将上一轮的 reasoning_content 传回 API
2. 清理逻辑：新对话开始时，需要清理之前的 reasoning_content

参考文档：
https://api-docs.deepseek.com/zh-cn/guides/thinking_mode
"""

from typing import Any
from langchain_core.messages import BaseMessage


def clear_reasoning_content(messages: list[Any]) -> list[dict]:
    """
    清理消息列表中的 reasoning_content
    
    根据官方文档：在下一个用户问题开始时，需删除之前的 reasoning_content。
    
    Args:
        messages: 消息列表（dict 或 LangChain Message 对象）
    
    Returns:
        清理后的消息列表（dict 格式）
    """
    cleaned = []
    for msg in messages:
        if isinstance(msg, dict):
            msg_dict = dict(msg)
            msg_dict.pop("reasoning_content", None)
            if "additional_kwargs" in msg_dict:
                kwargs = dict(msg_dict["additional_kwargs"])
                kwargs.pop("reasoning_content", None)
                if kwargs:
                    msg_dict["additional_kwargs"] = kwargs
                else:
                    msg_dict.pop("additional_kwargs", None)
            cleaned.append(msg_dict)
        elif hasattr(msg, "reasoning_content"):
            msg_dict = {"role": "assistant", "content": getattr(msg, "content", "")}
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                msg_dict["tool_calls"] = tool_calls
            name = getattr(msg, "name", None)
            if name:
                msg_dict["name"] = name
            cleaned.append(msg_dict)
        else:
            cleaned.append(msg)
    return cleaned


def preserve_reasoning_content(messages: list[dict]) -> list[dict]:
    """
    保留消息列表中的 reasoning_content（工具调用场景）
    
    根据官方文档：在工具调用过程中，需要回传 reasoning_content 给 API。
    
    Args:
        messages: 消息列表（dict 格式）
    
    Returns:
        保留 reasoning_content 的消息列表
    """
    return list(messages)


def extract_reasoning_content(msg: Any) -> str | None:
    """
    从消息中提取 reasoning_content
    
    Args:
        msg: 消息对象（dict 或 LangChain Message）
    
    Returns:
        reasoning_content 字符串，如果不存在则返回 None
    """
    if isinstance(msg, dict):
        reasoning_content = msg.get("reasoning_content")
        if reasoning_content is None:
            reasoning_content = (msg.get("additional_kwargs") or {}).get("reasoning_content")
        if reasoning_content is None:
            reasoning_content = (msg.get("response_metadata") or {}).get("reasoning_content")
        return reasoning_content if isinstance(reasoning_content, str) else None
    else:
        reasoning_content = getattr(msg, "reasoning_content", None)
        if reasoning_content is None:
            reasoning_content = (getattr(msg, "additional_kwargs", {}) or {}).get("reasoning_content")
        if reasoning_content is None:
            reasoning_content = (getattr(msg, "response_metadata", {}) or {}).get("reasoning_content")
        return reasoning_content if isinstance(reasoning_content, str) else None
