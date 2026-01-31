"""
LLM 配置模块
支持 DeepSeek、OpenAI、Claude 切换
"""

import json
import os
from typing import Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import AIMessage

# 加载环境变量
load_dotenv()


def get_llm(temperature: float = 0.7, model: Optional[str] = None, use_tools: bool = False):
    """
    根据环境变量配置获取 LLM 实例
    
    Args:
        temperature: 生成温度，默认 0.7
    
    Returns:
        LangChain ChatModel 实例
    """
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
    
    if provider == "mock":
        return MockLLM()
    if provider == "doubao":
        return ChatOpenAI(
            model=os.getenv("DOUBAO_ENDPOINT_ID"),
            openai_api_key=os.getenv("DOUBAO_API_KEY"),
            openai_api_base=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            temperature=temperature,
        )
    
    elif provider == "deepseek":
        # 使用官方 ChatDeepSeek 集成；临时切换为 deepseek-chat 模式
        resolved_model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        thinking_with_tools = os.getenv("DEEPSEEK_THINKING_WITH_TOOLS", "false").lower() == "true"
        if use_tools and resolved_model == "deepseek-reasoner" and not thinking_with_tools:
            resolved_model = os.getenv("DEEPSEEK_TOOL_MODEL", "deepseek-chat")
        return ChatDeepSeek(
            model=resolved_model,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL"),
            temperature=temperature,
        )
    
    elif provider == "openai":
        return ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            temperature=temperature,
        )
    
    elif provider == "claude":
        # Claude 使用 langchain-anthropic
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
                anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
                temperature=temperature,
            )
        except ImportError:
            raise ImportError("请安装 langchain-anthropic: pip install langchain-anthropic")
    
    else:
        raise ValueError(f"不支持的 LLM Provider: {provider}")


class MockLLM:
    """轻量 Mock LLM，用于纯逻辑测试。"""

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages):
        payload = {
            "task_id": "mock_task",
            "thought": "mock_thought",
            "response": "mock_response",
            "intent_type": "consult_only",
            "report_content": "mock_status_report",
            "goal": "mock_goal",
            "strategy": "mock_strategy",
            "phases": [],
            "key_principles": [],
            "summary": "mock_summary",
            "title": "mock_guide_title",
            "one_liner": "mock_one_liner",
            "guide_content": "mock_guide_content",
            "guide_status_updates": [],
        }
        return AIMessage(content=json.dumps(payload, ensure_ascii=False))


# 导出默认 LLM 实例
def get_default_llm():
    """获取默认 LLM 实例"""
    return get_llm(temperature=0.7)


def get_thinking_llm(temperature: float = 0.7):
    """
    获取支持思考模式 + 工具调用的 LLM 实例
    
    DeepSeek V3.2 支持 thinking mode 下的 tool calling，但需要：
    1. 使用 deepseek-chat 模型（不是 deepseek-reasoner）
    2. 通过 extra_body 启用 thinking mode
    3. 在多轮工具调用中回传 reasoning_content
    
    注意：使用 ChatOpenAI 而非 ChatDeepSeek，因为需要传 extra_body 参数
    
    Returns:
        LangChain ChatModel 实例，已启用思考模式
    """
    return ChatOpenAI(
        model="deepseek-chat",  # 必须用 deepseek-chat，不是 deepseek-reasoner
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=temperature,
        extra_body={"thinking": {"type": "enabled"}},
    )


def is_thinking_with_tools_enabled() -> bool:
    """检查是否启用思考模式 + 工具调用"""
    return os.getenv("DEEPSEEK_THINKING_WITH_TOOLS", "false").lower() == "true"


def get_thinking_max_rounds() -> int:
    """获取思考模式下工具调用的最大轮次"""
    return int(os.getenv("DEEPSEEK_THINKING_MAX_ROUNDS", "15"))

