"""
工作流集成测试
验证完整工作流的编排和状态流转
"""

import pytest
from graph.state import create_initial_state
from tests.conftest import (
    workflow,
    run_workflow_turn,
    assert_state_valid,
    assert_agent_output,
    print_state_summary,
    get_ai_response,
)


class TestWorkflowIntegration:
    """工作流集成测试类"""
    
    def test_workflow_simple_consultation(self, workflow):
        """测试简单咨询流程"""
        # 创建咨询场景
        state = create_initial_state("她这样是喜欢我吗？")
        result = workflow.invoke(state)
        
        # 验证结果
        assert_state_valid(result)
        assert_agent_output(result)
        
        # 应该有回复
        if result.get("__interrupt__"):
            assert isinstance(result.get("__interrupt__"), list)
        else:
            response = get_ai_response(result)
            assert len(response) > 0, "应该有 AI 回复"
    
    def test_workflow_full_onboarding(self, workflow):
        """测试完整首次进入流程"""
        state = create_initial_state("我叫小明，25岁，在北京做程序员")
        result = workflow.invoke(state)
        assert_state_valid(result)
        assert "onboarding_completed" in result
        assert "layer1_memory" in result
    
    def test_workflow_multi_turn_continuity(self, workflow):
        """测试多轮对话连贯性"""
        state = create_initial_state("我喜欢一个女生")
        result = workflow.invoke(state)
        result = run_workflow_turn(workflow, result, "她是我同事")
        result = run_workflow_turn(workflow, result, "我们认识三个月了")
        messages = result.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) >= 3, "应该有至少3条用户消息"
        assert "layer1_memory" in result
    
    def test_workflow_error_handling(self, workflow):
        """测试错误处理"""
        # 测试空消息
        state = create_initial_state("")
        result = workflow.invoke(state)
        assert_state_valid(result)
        
        # 测试特殊字符
        state = create_initial_state("测试消息！@#￥%……&*（）")
        result = workflow.invoke(state)
        assert_state_valid(result)
        
        # 测试超长消息
        long_message = "测试消息" * 1000
        state = create_initial_state(long_message)
        result = workflow.invoke(state)
        assert_state_valid(result)
    
    # 原先的 “resume_point/pending_questions” 两阶段恢复机制已移除（改为 interrupt/resume 协议）





