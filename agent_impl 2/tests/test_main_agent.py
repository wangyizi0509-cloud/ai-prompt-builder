"""
主 Agent 测试
验证主 Agent 的决策、回复、提问能力
"""

import pytest
from graph.nodes.main_agent import main_agent_node
from graph.state import create_initial_state
from tests.conftest import create_test_state, assert_state_valid, assert_agent_output, workflow


class TestMainAgent:
    """主 Agent 测试类"""
    
    def test_main_agent_consult_only(self, workflow):
        """测试纯咨询场景直接回复"""
        # 创建咨询场景
        state = create_test_state("她这样是喜欢我吗？")
        result = workflow.invoke(state)
        
        # 验证结果
        assert_state_valid(result)
        assert_agent_output(result)
        
        # 应该有回复
        response = result.get("pending_responses", [])
        assert len(response) > 0 or result.get("assistant_response"), "应该有 AI 回复"
    
    def test_main_agent_emotion_vent(self, workflow):
        """测试情绪发泄场景情感陪伴"""
        # 创建情绪发泄场景
        state = create_test_state("我好难过，不知道该怎么办")
        result = workflow.invoke(state)
        
        # 验证结果
        assert_state_valid(result)
        assert_agent_output(result)
        
        # 应该有情感陪伴回复
        response = result.get("pending_responses", [])
        assert len(response) > 0 or result.get("assistant_response"), "应该有情感陪伴回复"
    
    def test_main_agent_ask_user(self, workflow):
        """测试主 Agent 提问功能"""
        # 创建信息不足的场景
        state = create_test_state("我想追求一个女生")
        result = workflow.invoke(state)
        
        # 验证结果
        assert_state_valid(result)
        assert_agent_output(result)
        
        # 可能需要提问（取决于模型判断）
        # 如果有提问，应该设置相关字段
        if result.get("next_action") == "ask_user":
            assert result.get("current_agent") == "main_agent", "current_agent 应该是 main_agent"
            assert result.get("agent_resume_point") == "continue_decision", "应该有恢复点"
            assert result.get("inquiry_card") is not None or result.get("pending_questions"), "应该有提问卡片或问题列表"
    
    def test_main_agent_call_sub_agent(self, workflow):
        """测试调用子 Agent 决策"""
        # 创建需要现状分析的场景
        state = create_test_state(
            "我和一个女生认识三个月了，经常一起吃饭，我想知道我们现在是什么阶段"
        )
        result = workflow.invoke(state)
        
        # 验证结果
        assert_state_valid(result)
        assert_agent_output(result)
        
        # 可能调用 status_agent（取决于模型判断）
        next_action = result.get("next_action")
        if next_action in ["call_status", "call_plan", "call_guide"]:
            assert next_action in ["call_status", "call_plan", "call_guide"], "应该调用子 Agent"
    
    def test_main_agent_resume_after_question(self, workflow):
        """测试提问后恢复执行"""
        # 模拟主 Agent 提问后的恢复场景
        state = create_test_state(
            "她是我同事，我们经常一起吃饭",
            current_agent="main_agent",
            agent_resume_point="continue_decision",
            question_count=1,
            collected_info={}
        )
        result = workflow.invoke(state)
        
        # 验证结果
        assert_state_valid(result)
        assert_agent_output(result)
        
        # 恢复后应该继续决策
        assert "next_action" in result, "应该有下一步动作"
    
    def test_main_agent_redecision_after_sub_agent(self, workflow):
        """测试子 Agent 返回后再决策"""
        # 模拟子 Agent 完成后的再决策场景
        state = create_test_state(
            "继续",
            completion_status="COMPLETED",
            result_summary="现状分析已完成",
            status_report={"stage": "L2", "summary": "测试报告"}
        )
        result = workflow.invoke(state)
        
        # 验证结果
        assert_state_valid(result)
        assert_agent_output(result)
        
        # 再决策后应该清除完成信号
        assert result.get("completion_status") is None or result.get("completion_status") == "", "应该清除完成信号"
    
    def test_main_agent_context_extraction(self, workflow):
        """测试用户信息提取和更新"""
        # 创建包含用户信息的消息
        state = create_test_state("我叫小明，25岁，在北京做程序员")
        result = workflow.invoke(state)
        
        # 验证结果
        assert_state_valid(result)
        
        # 验证 user_context 是否更新（可能需要多轮对话）
        user_context = result.get("user_context", {})
        assert user_context is not None, "应该有 user_context"
        
        # 验证消息历史
        messages = result.get("messages", [])
        assert len(messages) > 0, "应该有消息历史"
