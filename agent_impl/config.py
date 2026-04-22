"""
LLM 配置模块
支持 DeepSeek、OpenAI、Claude 切换
"""

import json
import os
import logging
from typing import Any, Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)


def _normalize_env_value(value: Optional[str]) -> str:
    return str(value or "").strip()


def _is_placeholder_key(value: Optional[str]) -> bool:
    normalized = _normalize_env_value(value).lower()
    if not normalized:
        return True
    if normalized in {"none", "null", "changeme", "todo"}:
        return True
    placeholder_prefixes = (
        "your_",
        "your-",
        "replace_",
        "replace-",
        "example_",
        "example-",
        "<your",
    )
    if any(normalized.startswith(prefix) for prefix in placeholder_prefixes):
        return True
    if "api_key_here" in normalized or "your_api_key" in normalized:
        return True
    return False


def _resolve_effective_provider(preferred_provider: str) -> str:
    provider = _normalize_env_value(preferred_provider).lower() or "deepseek"
    if provider == "mock":
        return provider

    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    doubao_key = os.getenv("DOUBAO_API_KEY")
    doubao_endpoint = _normalize_env_value(os.getenv("DOUBAO_ENDPOINT_ID"))

    has_deepseek = not _is_placeholder_key(deepseek_key)
    has_openai = not _is_placeholder_key(openai_key)
    has_doubao = (not _is_placeholder_key(doubao_key)) and bool(doubao_endpoint)

    if provider == "deepseek" and not has_deepseek:
        if has_doubao:
            logger.warning("LLM_PROVIDER=deepseek but DEEPSEEK_API_KEY is placeholder; fallback to doubao")
            return "doubao"
        if has_openai:
            logger.warning("LLM_PROVIDER=deepseek but DEEPSEEK_API_KEY is placeholder; fallback to openai")
            return "openai"
    if provider == "openai" and not has_openai:
        if has_doubao:
            logger.warning("LLM_PROVIDER=openai but OPENAI_API_KEY is placeholder; fallback to doubao")
            return "doubao"
        if has_deepseek:
            logger.warning("LLM_PROVIDER=openai but OPENAI_API_KEY is placeholder; fallback to deepseek")
            return "deepseek"
    if provider == "doubao" and not has_doubao:
        if has_deepseek:
            logger.warning("LLM_PROVIDER=doubao but DOUBAO config is incomplete; fallback to deepseek")
            return "deepseek"
        if has_openai:
            logger.warning("LLM_PROVIDER=doubao but DOUBAO config is incomplete; fallback to openai")
            return "openai"

    return provider


class ChatDeepSeekReasoning(ChatDeepSeek):
    """
    自定义 DeepSeek Reasoner 包装器，正确处理 reasoning_content 回传
    
    DeepSeek Reasoner 在工具调用场景下要求：
    - assistant 消息必须包含 reasoning_content 字段
    - 多轮工具调用时需要回传上一轮的 reasoning_content
    
    这个包装器会从 additional_kwargs 中提取 reasoning_content 并放入请求 payload
    """
    
    def _get_request_payload(
        self,
        input_,
        *,
        stop=None,
        **kwargs,
    ):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        
        # 提取原始 input 中的 reasoning_content
        reasoning_map = {}
        if isinstance(input_, list):
            for i, msg in enumerate(input_):
                if hasattr(msg, "additional_kwargs") and isinstance(msg.additional_kwargs, dict):
                    reasoning_content = msg.additional_kwargs.get("reasoning_content")
                    if reasoning_content:
                        reasoning_map[i] = reasoning_content
                        # 调试输出
                        if os.getenv("DEBUG_REASONING", "false").lower() == "true":
                            logger.debug(
                                "Found reasoning_content at index %s (len=%s)",
                                i,
                                len(reasoning_content),
                            )
        
        # 将 reasoning_content 注入到 payload 中
        injected_count = 0
        for i, message in enumerate(payload.get("messages", [])):
            if message.get("role") == "assistant":
                if i in reasoning_map:
                    message["reasoning_content"] = reasoning_map[i]
                    injected_count += 1
                    if os.getenv("DEBUG_REASONING", "false").lower() == "true":
                        logger.debug("Injected reasoning_content to message %s", i)
                if message.get("tool_calls") and "reasoning_content" not in message:
                    message["reasoning_content"] = ""
                    injected_count += 1
        
        if os.getenv("DEBUG_REASONING", "false").lower() == "true":
            logger.debug("Total reasoning_content injected: %s", injected_count)
            logger.debug("Total messages in payload: %s", len(payload.get("messages", [])))
            for i, msg in enumerate(payload.get('messages', [])):
                logger.debug(
                    "Message %s: role=%s, has_reasoning=%s",
                    i,
                    msg.get("role"),
                    "reasoning_content" in msg,
                )
        
        return payload


def get_llm(temperature: float = 0.7, model: Optional[str] = None, use_tools: bool = False):
    """
    根据环境变量配置获取 LLM 实例
    
    Args:
        temperature: 生成温度，默认 0.7
        model: 模型名称，默认从环境变量读取
        use_tools: 是否用于工具调用，启用后会使用 deepseek-reasoner
    
    Returns:
        LangChain ChatModel 实例
    """
    provider = _resolve_effective_provider(os.getenv("LLM_PROVIDER", "deepseek"))
    
    if provider == "mock":
        return MockLLM()
    if provider == "doubao":
        endpoint_id = _normalize_env_value(os.getenv("DOUBAO_ENDPOINT_ID"))
        if not endpoint_id:
            raise ValueError("DOUBAO_ENDPOINT_ID is required when provider is doubao")
        if _is_placeholder_key(os.getenv("DOUBAO_API_KEY")):
            raise ValueError("DOUBAO_API_KEY is missing or placeholder")
        return ChatOpenAI(
            model=endpoint_id,
            openai_api_key=os.getenv("DOUBAO_API_KEY"),
            openai_api_base=os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            temperature=temperature,
        )
    
    elif provider == "deepseek":
        if _is_placeholder_key(os.getenv("DEEPSEEK_API_KEY")):
            raise ValueError("DEEPSEEK_API_KEY is missing or placeholder")
        resolved_model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        
        # 工具调用场景：使用 deepseek-reasoner（ChatDeepSeekReasoning 正确处理 reasoning_content 回传）
        if use_tools:
            return ChatDeepSeekReasoning(
                model="deepseek-reasoner",
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=os.getenv("DEEPSEEK_BASE_URL"),
                temperature=temperature,
            )
        
        # 非工具调用场景：使用 ChatDeepSeek
        return ChatDeepSeek(
            model=resolved_model,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL"),
            temperature=temperature,
        )
    
    elif provider == "openai":
        if _is_placeholder_key(os.getenv("OPENAI_API_KEY")):
            raise ValueError("OPENAI_API_KEY is missing or placeholder")
        return ChatOpenAI(
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            temperature=temperature,
        )
    
    elif provider == "claude":
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


class MockLLM(BaseChatModel):
    """轻量 Mock LLM，用于纯逻辑测试。"""

    def __init__(self):
        super().__init__()
        self._tool_names: set[str] = set()
        self._interrupt_tool_call_id = "tc_mock_ask_human"
        self._interrupt_tool_call_id_2 = "tc_mock_ask_human_2"
        self._status_tool_call_id = "tc_mock_call_status"
        self._plan_tool_call_id = "tc_mock_call_plan"

    @property
    def _llm_type(self) -> str:
        return "mock_llm"

    def _has_tool_observation(self, messages, *, tool_call_id: str) -> bool:
        for m in messages or []:
            if isinstance(m, dict):
                if m.get("role") == "tool" and str(m.get("tool_call_id") or "") == tool_call_id:
                    return True
                continue
            msg_type = getattr(m, "type", None)
            if msg_type == "tool" and str(getattr(m, "tool_call_id", "") or "") == tool_call_id:
                return True
        return False

    def bind_tools(self, tools, **kwargs):
        names: set[str] = set()
        for t in tools or []:
            name = getattr(t, "name", None)
            if isinstance(name, str) and name:
                names.add(name)
        self._tool_names = names
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        last_user_text = ""
        for m in reversed(messages or []):
            content = getattr(m, "content", None)
            if not isinstance(content, str):
                continue
            msg_type = getattr(m, "type", None)
            role = getattr(m, "role", None)
            if msg_type == "human" or role == "user":
                last_user_text = content
                break

        already_has_status_result = self._has_tool_observation(messages, tool_call_id=self._status_tool_call_id)
        if (
            (not already_has_status_result)
            and ("[[TEST_CALL_STATUS_INTERRUPT]]" in last_user_text)
            and ("call_status_agent" in self._tool_names)
        ):
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "call_status_agent",
                        "args": {"instruction": "[[TEST_INTERRUPT]]"},
                        "id": self._status_tool_call_id,
                        "type": "tool_call",
                    }
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=msg)])

        already_has_plan_result = self._has_tool_observation(messages, tool_call_id=self._plan_tool_call_id)
        if (
            (not already_has_plan_result)
            and ("[[TEST_CALL_PLAN_INTERRUPT]]" in last_user_text)
            and ("call_plan_agent" in self._tool_names)
        ):
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "call_plan_agent",
                        "args": {"instruction": "[[TEST_INTERRUPT]]"},
                        "id": self._plan_tool_call_id,
                        "type": "tool_call",
                    }
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=msg)])

        already_has_plan_result_2 = self._has_tool_observation(messages, tool_call_id=self._plan_tool_call_id)
        if (
            (not already_has_plan_result_2)
            and ("[[TEST_CALL_PLAN_INTERRUPT_TWICE]]" in last_user_text)
            and ("call_plan_agent" in self._tool_names)
        ):
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "call_plan_agent",
                        "args": {"instruction": "[[TEST_INTERRUPT_TWICE]]"},
                        "id": self._plan_tool_call_id,
                        "type": "tool_call",
                    }
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=msg)])

        already_has_tool_result = self._has_tool_observation(messages, tool_call_id=self._interrupt_tool_call_id)
        already_has_tool_result_2 = self._has_tool_observation(messages, tool_call_id=self._interrupt_tool_call_id_2)
        if (
            (not already_has_tool_result)
            and ("[[TEST_INTERRUPT]]" in last_user_text)
            and ("ask_human" in self._tool_names)
        ):
            inquiry_card = {
                "intro": "测试用提问卡片",
                "reasoning": "触发 interrupt/resume 的确定性测试",
                "questions": [
                    {
                        "id": "q1",
                        "type": "single_choice",
                        "question": "你选择 A 还是 B？",
                        "options": ["A", "B"],
                        "is_required": True,
                        "purpose": "测试 interrupt/resume",
                    }
                ],
            }
            msg = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_human",
                        "args": {"inquiry_card": inquiry_card},
                        "id": self._interrupt_tool_call_id,
                        "type": "tool_call",
                    }
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=msg)])

        if ("[[TEST_INTERRUPT_TWICE]]" in last_user_text) and ("ask_human" in self._tool_names):
            if not already_has_tool_result:
                inquiry_card = {
                    "intro": "测试用提问卡片",
                    "reasoning": "触发 interrupt/resume 的确定性测试",
                    "questions": [
                        {
                            "id": "q1",
                            "type": "single_choice",
                            "question": "你选择 A 还是 B？",
                            "options": ["A", "B"],
                            "is_required": True,
                            "purpose": "测试 interrupt/resume",
                        }
                    ],
                }
                msg = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "ask_human",
                            "args": {"inquiry_card": inquiry_card},
                            "id": self._interrupt_tool_call_id,
                            "type": "tool_call",
                        }
                    ],
                )
                return ChatResult(generations=[ChatGeneration(message=msg)])
            if not already_has_tool_result_2:
                inquiry_card = {
                    "intro": "测试用提问卡片",
                    "reasoning": "触发 interrupt/resume 的确定性测试",
                    "questions": [
                        {
                            "id": "q2",
                            "type": "single_choice",
                            "question": "你选择 C 还是 D？",
                            "options": ["C", "D"],
                            "is_required": True,
                            "purpose": "测试 interrupt/resume",
                        }
                    ],
                }
                msg = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "ask_human",
                            "args": {"inquiry_card": inquiry_card},
                            "id": self._interrupt_tool_call_id_2,
                            "type": "tool_call",
                        }
                    ],
                )
                return ChatResult(generations=[ChatGeneration(message=msg)])

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
        msg = AIMessage(content=json.dumps(payload, ensure_ascii=False))
        return ChatResult(generations=[ChatGeneration(message=msg)])


# 导出默认 LLM 实例
def get_default_llm():
    """获取默认 LLM 实例"""
    return get_llm(temperature=0.7)


def get_onboarding_vision_llm(temperature: float = 0.3):
    """
    Onboarding v2 analyze 节点专用：智谱 BigModel GLM vision 旗舰。

    - 场景：一张聊天截图 + 400 字自由描述 → 结构化 JSON（5 条 skip_rules + FirstHook）
    - 模型：glm-4.6v（106B 原生 function call，结构化输出稳定）
    - 协议：OpenAI 兼容，base_url = https://open.bigmodel.cn/api/paas/v4/
    - 环境变量：
        - ONBOARDING_VISION_API_KEY（缺省回退到 IMAGE_TYPE_DETECT_API_KEY）
        - ONBOARDING_VISION_BASE_URL（默认 https://open.bigmodel.cn/api/paas/v4/）
        - ONBOARDING_VISION_MODEL（默认 glm-4.6v）
    """
    api_key = (
        _normalize_env_value(os.getenv("ONBOARDING_VISION_API_KEY"))
        or _normalize_env_value(os.getenv("IMAGE_TYPE_DETECT_API_KEY"))
    )
    if _is_placeholder_key(api_key):
        raise ValueError(
            "ONBOARDING_VISION_API_KEY (or IMAGE_TYPE_DETECT_API_KEY fallback) "
            "is missing or placeholder"
        )
    base_url = (
        _normalize_env_value(os.getenv("ONBOARDING_VISION_BASE_URL"))
        or "https://open.bigmodel.cn/api/paas/v4/"
    )
    model = (
        _normalize_env_value(os.getenv("ONBOARDING_VISION_MODEL"))
        or "glm-4.6v"
    )
    return ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=temperature,
    )


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
        model="deepseek-chat",
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
