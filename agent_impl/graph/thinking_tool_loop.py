"""
DeepSeek 思考模式 + 工具调用循环控制器

DeepSeek V3.2 支持在 thinking mode 下进行工具调用，但有特殊要求：
1. 使用 deepseek-chat + extra_body={"thinking": {"type": "enabled"}}
2. 在同一轮的多次子请求中，必须把 reasoning_content 回传给 API
3. 新一轮对话开始时，需要清除历史 reasoning_content

本模块实现了符合 DeepSeek 官方规范的工具调用循环。
"""

import json
import logging
import os
from typing import Any, Callable, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from openai import OpenAI

from config import get_thinking_max_rounds

logger = logging.getLogger(__name__)


class ThinkingToolLoopResult:
    """思考+工具循环的结果"""
    
    def __init__(
        self,
        final_response: AIMessage,
        tool_call_count: int,
        round_count: int,
        reasoning_contents: list[str],
        tool_results: list[dict],
    ):
        self.final_response = final_response
        self.tool_call_count = tool_call_count
        self.round_count = round_count
        self.reasoning_contents = reasoning_contents
        self.tool_results = tool_results
    
    @property
    def content(self) -> str:
        """最终回复内容"""
        return self.final_response.content or ""
    
    @property
    def last_reasoning_content(self) -> Optional[str]:
        """最后一轮的推理内容"""
        return self.reasoning_contents[-1] if self.reasoning_contents else None


def extract_reasoning_content(response: AIMessage) -> Optional[str]:
    """
    从 AIMessage 中提取 reasoning_content
    
    DeepSeek 返回的 reasoning_content 会放在 additional_kwargs 里
    """
    additional_kwargs = getattr(response, "additional_kwargs", {}) or {}
    return additional_kwargs.get("reasoning_content")


def execute_tool(tool: BaseTool, tool_call: dict) -> str:
    """
    执行单个工具调用
    
    Args:
        tool: LangChain 工具实例
        tool_call: 工具调用信息，包含 name, args, id
    
    Returns:
        工具执行结果（字符串）
    """
    try:
        args = tool_call.get("args", {})
        result = tool.invoke(args)
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        return str(result)
    except Exception as e:
        logger.error(f"Tool execution failed: {tool.name}, error: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def find_tool_by_name(tools: list[BaseTool], name: str) -> Optional[BaseTool]:
    """根据名称查找工具"""
    for tool in tools:
        if tool.name == name:
            return tool
    return None


def _convert_langchain_to_openai_messages(messages: list) -> list[dict]:
    """
    将 LangChain 消息转换为 OpenAI API 格式的消息列表
    
    关键：确保 reasoning_content 被正确传递
    """
    openai_messages = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            openai_messages.append({
                "role": "system",
                "content": msg.content,
            })
        elif isinstance(msg, HumanMessage):
            openai_messages.append({
                "role": "user",
                "content": msg.content,
            })
        elif isinstance(msg, AIMessage):
            # 关键：提取 reasoning_content
            reasoning_content = extract_reasoning_content(msg)
            msg_dict = {
                "role": "assistant",
                "content": msg.content or "",
            }
            # 如果有 reasoning_content，必须包含（DeepSeek 要求）
            if reasoning_content is not None:
                msg_dict["reasoning_content"] = reasoning_content
            # 如果有 tool_calls，转换为 OpenAI 格式
            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.get("id", ""),
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                        }
                    }
                    for tc in tool_calls
                ]
            openai_messages.append(msg_dict)
        elif isinstance(msg, ToolMessage):
            openai_messages.append({
                "role": "tool",
                "content": msg.content,
                "tool_call_id": msg.tool_call_id,
            })
    return openai_messages


def _convert_openai_to_langchain_message(openai_response) -> AIMessage:
    """将 OpenAI API 响应转换为 LangChain AIMessage"""
    msg = openai_response.choices[0].message
    
    # 提取 reasoning_content
    reasoning_content = getattr(msg, "reasoning_content", None)
    
    # 转换 tool_calls
    tool_calls = []
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}
            tool_calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "args": args,
            })
    
    # 构建 AIMessage
    ai_msg = AIMessage(
        content=msg.content or "",
        tool_calls=tool_calls,  # 空列表也是有效的
    )
    
    # 设置 reasoning_content 到 additional_kwargs
    if reasoning_content:
        ai_msg.additional_kwargs["reasoning_content"] = reasoning_content
    
    return ai_msg


def _convert_tools_to_openai_format(tools: list[BaseTool]) -> list[dict]:
    """将 LangChain 工具转换为 OpenAI API 格式"""
    from langchain_core.utils.function_calling import convert_to_openai_tool
    
    openai_tools = []
    for tool in tools:
        openai_tool = convert_to_openai_tool(tool)
        openai_tools.append(openai_tool)
    return openai_tools


def run_thinking_tool_loop(
    messages: list,
    tools: list[BaseTool],
    temperature: float = 0.7,
    max_rounds: Optional[int] = None,
    on_tool_call: Optional[Callable[[dict], None]] = None,
    on_tool_result: Optional[Callable[[str, str], None]] = None,
) -> ThinkingToolLoopResult:
    """
    运行思考模式 + 工具调用循环
    
    实现 DeepSeek 官方的多轮工具调用逻辑：
    1. 调用 LLM，检查是否有 tool_calls
    2. 有工具调用时：执行工具 -> 构建下一轮消息（含 reasoning_content）-> 继续调用
    3. 无工具调用或达到最大轮次时：返回最终结果
    
    注意：使用 OpenAI SDK 直接调用以确保 reasoning_content 被正确传递
    
    Args:
        messages: 初始消息列表
        tools: 可用工具列表
        temperature: 生成温度
        max_rounds: 最大轮次，默认从环境变量获取
        on_tool_call: 工具调用回调（用于日志/监控）
        on_tool_result: 工具结果回调（用于日志/监控）
    
    Returns:
        ThinkingToolLoopResult 包含最终响应和执行统计
    """
    if max_rounds is None:
        max_rounds = get_thinking_max_rounds()
    
    # 使用 OpenAI SDK 直接调用（确保 reasoning_content 被正确传递）
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    
    # 转换工具格式
    openai_tools = _convert_tools_to_openai_format(tools)
    
    # 转换消息格式（LangChain -> OpenAI API 格式）
    working_messages = _convert_langchain_to_openai_messages(_normalize_messages(messages))
    
    # 统计信息
    total_tool_calls = 0
    round_count = 0
    reasoning_contents: list[str] = []
    tool_results: list[dict] = []
    final_response: Optional[AIMessage] = None
    
    while round_count < max_rounds:
        round_count += 1
        logger.info(f"Thinking tool loop: round {round_count}/{max_rounds}")
        
        # 调用 OpenAI API
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=working_messages,
            tools=openai_tools if openai_tools else None,
            temperature=temperature,
            extra_body={"thinking": {"type": "enabled"}},
        )
        
        # 转换为 LangChain AIMessage
        ai_response = _convert_openai_to_langchain_message(response)
        final_response = ai_response
        
        # 提取 reasoning_content
        reasoning_content = extract_reasoning_content(ai_response)
        if reasoning_content:
            reasoning_contents.append(reasoning_content)
            logger.debug(f"Round {round_count} reasoning: {reasoning_content[:100]}...")
        
        # 检查是否有工具调用
        tool_calls = getattr(ai_response, "tool_calls", None) or []
        
        if not tool_calls:
            # 没有工具调用，返回最终结果
            logger.info(f"Thinking tool loop completed: {round_count} rounds, {total_tool_calls} tool calls")
            return ThinkingToolLoopResult(
                final_response=ai_response,
                tool_call_count=total_tool_calls,
                round_count=round_count,
                reasoning_contents=reasoning_contents,
                tool_results=tool_results,
            )
        
        # 有工具调用，执行工具
        # 先把 assistant 消息（含 reasoning_content 和 tool_calls）加入消息列表
        # 注意：DeepSeek 要求在工具调用时，assistant 消息必须包含 reasoning_content
        assistant_msg = {
            "role": "assistant",
            "content": ai_response.content or "",
        }
        # 关键：必须包含 reasoning_content（即使为空字符串）
        if reasoning_content is not None:
            assistant_msg["reasoning_content"] = reasoning_content
        else:
            # 第一轮可能没有，传递空字符串（DeepSeek 允许）
            assistant_msg["reasoning_content"] = ""
        
        # 添加 tool_calls
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                    }
                }
                for tc in tool_calls
            ]
        
        working_messages.append(assistant_msg)
        
        for tc in tool_calls:
            total_tool_calls += 1
            tool_name = tc.get("name", "")
            tool_id = tc.get("id", "")
            
            if on_tool_call:
                on_tool_call(tc)
            
            # 查找并执行工具
            tool = find_tool_by_name(tools, tool_name)
            if tool:
                result = execute_tool(tool, tc)
            else:
                result = json.dumps({"error": f"Tool not found: {tool_name}"}, ensure_ascii=False)
                logger.warning(f"Tool not found: {tool_name}")
            
            if on_tool_result:
                on_tool_result(tool_name, result)
            
            tool_results.append({
                "tool_name": tool_name,
                "tool_id": tool_id,
                "args": tc.get("args", {}),
                "result": result,
            })
            
            # 把工具结果加入消息列表
            working_messages.append({
                "role": "tool",
                "content": result,
                "tool_call_id": tool_id,
            })
    
    # 达到最大轮次，返回最后一次响应
    logger.warning(f"Thinking tool loop reached max rounds ({max_rounds})")
    return ThinkingToolLoopResult(
        final_response=final_response or ai_response,
        tool_call_count=total_tool_calls,
        round_count=round_count,
        reasoning_contents=reasoning_contents,
        tool_results=tool_results,
    )


def _normalize_messages(messages: list) -> list:
    """
    标准化消息列表，确保都是 LangChain 消息对象
    """
    normalized = []
    for msg in messages:
        if isinstance(msg, (AIMessage, HumanMessage, SystemMessage, ToolMessage)):
            normalized.append(msg)
        elif isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                normalized.append(SystemMessage(content=content))
            elif role == "user":
                normalized.append(HumanMessage(content=content))
            elif role == "assistant":
                # 处理 assistant 消息，保留 reasoning_content 和 tool_calls
                ai_msg = AIMessage(content=content)
                if msg.get("reasoning_content"):
                    ai_msg.additional_kwargs["reasoning_content"] = msg["reasoning_content"]
                if msg.get("tool_calls"):
                    ai_msg.tool_calls = msg["tool_calls"]
                normalized.append(ai_msg)
            elif role == "tool":
                normalized.append(ToolMessage(
                    content=content,
                    tool_call_id=msg.get("tool_call_id", ""),
                ))
        elif isinstance(msg, tuple) and len(msg) == 2:
            # LangChain 的 (role, content) 元组格式
            role, content = msg
            if role == "system":
                normalized.append(SystemMessage(content=content))
            elif role in ("user", "human"):
                normalized.append(HumanMessage(content=content))
            elif role == "assistant":
                normalized.append(AIMessage(content=content))
    return normalized


def _build_assistant_message(response: AIMessage, reasoning_content: Optional[str]) -> AIMessage:
    """
    构建 assistant 消息，保留 reasoning_content 和 tool_calls
    
    DeepSeek 要求在同一轮的多次子请求中回传 reasoning_content
    注意：LangChain 的 ChatOpenAI 在序列化时，需要确保 reasoning_content 被正确传递
    我们通过设置 additional_kwargs 来传递，但 LangChain 可能不会自动序列化
    因此我们需要确保 reasoning_content 被正确设置
    """
    # 构建消息，确保 reasoning_content 被包含
    additional_kwargs = {}
    if reasoning_content is not None:
        # 即使为空字符串也要传递（DeepSeek 要求）
        additional_kwargs["reasoning_content"] = reasoning_content
    
    msg = AIMessage(
        content=response.content or "",
        tool_calls=getattr(response, "tool_calls", None) or [],
        additional_kwargs=additional_kwargs if additional_kwargs else {},
    )
    
    # 同时设置到 response 的 additional_kwargs（确保被序列化）
    if reasoning_content is not None:
        msg.additional_kwargs["reasoning_content"] = reasoning_content
    
    return msg


def clear_reasoning_content_from_messages(messages: list) -> list:
    """
    清除消息列表中的 reasoning_content
    
    DeepSeek 官方建议：新一轮对话开始时，清除历史 reasoning_content 以节省带宽
    """
    cleaned = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            new_msg = AIMessage(
                content=msg.content,
                tool_calls=getattr(msg, "tool_calls", None) or [],
            )
            # 不复制 reasoning_content
            cleaned.append(new_msg)
        else:
            cleaned.append(msg)
    return cleaned
