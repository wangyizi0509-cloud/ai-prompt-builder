"""
LLM 配置模块
支持 DeepSeek、OpenAI、Claude 切换
"""

import json
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage

# 加载环境变量
load_dotenv()


def get_llm(temperature: float = 0.7):
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
        return ChatOpenAI(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            temperature=temperature,
        )
    
    elif provider == "openai":
        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
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

