"""
真实 API 测试：回复 Skill 两阶段流程

验证模型能正确理解和执行：
1. 识别需要使用 consult_answer 或 emotion_support
2. 调用 enable 进入模式
3. 输出回复内容 + 调用 complete
"""

import os
import pytest
from tests.conftest import create_test_state

# 跳过条件：没有 API Key
SKIP_REASON = "需要 OPENAI_API_KEY 或 DEEPSEEK_API_KEY 环境变量"
HAS_API_KEY = bool(os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY"))


@pytest.mark.skipif(not HAS_API_KEY, reason=SKIP_REASON)
class TestConsultAnswerRealAPI:
    """真实 API 测试：解答模式"""

    def test_tool_schema_valid(self):
        """验证工具 schema 有效"""
        from graph.tools.consult_answer_tool import consult_enable, consult_complete
        
        # enable 版本
        enable_schema = consult_enable.args_schema.model_json_schema()
        assert "action" in enable_schema.get("properties", {})
        assert consult_enable.name == "consult_answer"
        
        # complete 版本
        complete_schema = consult_complete.args_schema.model_json_schema()
        assert "action" in complete_schema.get("properties", {})
        assert consult_complete.name == "consult_answer"

    def test_consult_flow_phase1_enable(self):
        """测试 Phase 1：模型调用 enable"""
        from config import get_llm
        from graph.tools.consult_answer_tool import consult_enable
        
        llm = get_llm(temperature=0.3)
        llm_with_tools = llm.bind_tools([consult_enable])
        
        messages = [
            {"role": "system", "content": "你是一个恋爱顾问。当用户询问情感相关概念时，使用 consult_answer 工具进入解答模式。"},
            {"role": "user", "content": "什么是推拉啊？感觉好累"},
        ]
        
        response = llm_with_tools.invoke(messages)
        
        # 验证模型调用了 consult_answer(action="enable")
        assert hasattr(response, "tool_calls") and response.tool_calls
        tool_call = response.tool_calls[0]
        assert tool_call["name"] == "consult_answer"
        assert tool_call["args"].get("action") == "enable"
        print(f"✅ Phase 1: 模型正确调用 consult_answer(action='enable')")

    def test_consult_flow_phase2_complete(self):
        """测试 Phase 2：模型输出回复 + 调用 complete"""
        from config import get_llm
        from graph.tools.consult_answer_tool import consult_complete, CONSULT_MODE_STRATEGY
        
        llm = get_llm(temperature=0.3)
        llm_with_tools = llm.bind_tools([consult_complete])
        
        # 模拟 Phase 1 已完成，现在进入 Phase 2
        messages = [
            {"role": "system", "content": "你是一个恋爱顾问。"},
            {"role": "user", "content": "什么是推拉啊？感觉好累"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "tc1", "name": "consult_answer", "args": {"action": "enable"}}]},
            {"role": "tool", "content": f"已进入解答模式。回复完成后，调用 consult_answer(action=\"complete\")。\n\n{CONSULT_MODE_STRATEGY}", "tool_call_id": "tc1", "name": "consult_answer"},
        ]
        
        response = llm_with_tools.invoke(messages)
        
        # 验证模型输出了内容
        assert response.content, "模型应该输出回复内容"
        print(f"✅ Phase 2: 模型输出内容: {response.content[:100]}...")
        
        # 验证模型调用了 complete
        assert hasattr(response, "tool_calls") and response.tool_calls
        tool_call = response.tool_calls[0]
        assert tool_call["name"] == "consult_answer"
        assert tool_call["args"].get("action") == "complete"
        print(f"✅ Phase 2: 模型正确调用 consult_answer(action='complete')")


@pytest.mark.skipif(not HAS_API_KEY, reason=SKIP_REASON)
class TestEmotionSupportRealAPI:
    """真实 API 测试：陪伴模式"""

    def test_tool_schema_valid(self):
        """验证工具 schema 有效"""
        from graph.tools.emotion_support_tool import emotion_enable, emotion_complete
        
        # enable 版本
        enable_schema = emotion_enable.args_schema.model_json_schema()
        assert "action" in enable_schema.get("properties", {})
        assert emotion_enable.name == "emotion_support"
        
        # complete 版本
        complete_schema = emotion_complete.args_schema.model_json_schema()
        assert "action" in complete_schema.get("properties", {})
        assert emotion_complete.name == "emotion_support"

    def test_emotion_flow_phase1_enable(self):
        """测试 Phase 1：模型调用 enable"""
        from config import get_llm
        from graph.tools.emotion_support_tool import emotion_enable
        
        llm = get_llm(temperature=0.3)
        llm_with_tools = llm.bind_tools([emotion_enable])
        
        messages = [
            {"role": "system", "content": "你是一个恋爱顾问。当用户表达情绪需要倾诉时，使用 emotion_support 工具进入陪伴模式。"},
            {"role": "user", "content": "好烦啊，不想理他了"},
        ]
        
        response = llm_with_tools.invoke(messages)
        
        # 验证模型调用了 emotion_support(action="enable")
        assert hasattr(response, "tool_calls") and response.tool_calls
        tool_call = response.tool_calls[0]
        assert tool_call["name"] == "emotion_support"
        assert tool_call["args"].get("action") == "enable"
        print(f"✅ Phase 1: 模型正确调用 emotion_support(action='enable')")

    def test_emotion_flow_phase2_complete(self):
        """测试 Phase 2：模型输出回复 + 调用 complete"""
        from config import get_llm
        from graph.tools.emotion_support_tool import emotion_complete, EMOTION_MODE_STRATEGY
        
        llm = get_llm(temperature=0.3)
        llm_with_tools = llm.bind_tools([emotion_complete])
        
        # 模拟 Phase 1 已完成，现在进入 Phase 2
        messages = [
            {"role": "system", "content": "你是一个恋爱顾问。"},
            {"role": "user", "content": "好烦啊，不想理他了"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "tc1", "name": "emotion_support", "args": {"action": "enable"}}]},
            {"role": "tool", "content": f"已进入陪伴模式。回复完成后，调用 emotion_support(action=\"complete\")。\n\n{EMOTION_MODE_STRATEGY}", "tool_call_id": "tc1", "name": "emotion_support"},
        ]
        
        response = llm_with_tools.invoke(messages)
        
        # 验证模型输出了内容
        assert response.content, "模型应该输出回复内容"
        print(f"✅ Phase 2: 模型输出内容: {response.content[:100]}...")
        
        # 验证模型调用了 complete
        assert hasattr(response, "tool_calls") and response.tool_calls
        tool_call = response.tool_calls[0]
        assert tool_call["name"] == "emotion_support"
        assert tool_call["args"].get("action") == "complete"
        print(f"✅ Phase 2: 模型正确调用 emotion_support(action='complete')")


@pytest.mark.skipif(not HAS_API_KEY, reason=SKIP_REASON)
class TestRetryMechanism:
    """测试兜底重试机制"""

    def test_retry_helper_function(self):
        """测试兜底辅助函数"""
        # 模拟模型输出有 content 但没有 complete 调用
        from langchain_core.messages import AIMessage
        
        response_with_complete = AIMessage(
            content="这就对了...",
            tool_calls=[{"id": "tc1", "name": "consult_answer", "args": {"action": "complete"}}]
        )
        
        response_without_complete = AIMessage(
            content="这就对了...",
            tool_calls=[]
        )
        
        def _has_complete_call(resp, tool_name: str) -> bool:
            if not hasattr(resp, "tool_calls") or not resp.tool_calls:
                return False
            for tc in resp.tool_calls:
                if tc.get("name") == tool_name and tc.get("args", {}).get("action") == "complete":
                    return True
            return False
        
        # 有 complete 调用
        assert _has_complete_call(response_with_complete, "consult_answer") is True
        
        # 没有 complete 调用
        assert _has_complete_call(response_without_complete, "consult_answer") is False
        
        print("✅ 兜底检测函数工作正常")
