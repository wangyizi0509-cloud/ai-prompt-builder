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
        response = get_ai_response(result)
        assert len(response) > 0, "应该有 AI 回复"
        
        # 简单咨询应该直接结束
        assert result.get("next_action") in ["end_turn", "ask_user"], "应该结束或提问"
    
    def test_workflow_full_onboarding(self, workflow):
        """测试完整首次进入流程"""
        # 第一轮：用户自我介绍
        state = create_initial_state("我叫小明，25岁，在北京做程序员")
        result = workflow.invoke(state)
        assert_state_valid(result)
        
        # 第二轮：介绍 crush
        result = run_workflow_turn(workflow, result, "我喜欢一个女生叫小红，是我同事")
        assert_state_valid(result)
        
        # 第三轮：描述关系
        result = run_workflow_turn(workflow, result, "我们认识三个月了，经常一起吃饭")
        assert_state_valid(result)
        
        # 验证状态累积
        messages = result.get("messages", [])
        assert len(messages) >= 6, "应该有至少6条消息（3轮对话）"
        
        # 验证上下文更新
        user_context = result.get("user_context", {})
        assert user_context is not None, "应该有 user_context"
    
    def test_workflow_agent_chain(self, workflow):
        """测试 Agent 链式调用"""
        # 创建需要完整流程的场景
        state = create_initial_state(
            "我和一个女生认识三个月了，我们是同事，经常一起吃饭，我想知道我们现在是什么阶段，应该怎么推进关系"
        )
        result = workflow.invoke(state)
        assert_state_valid(result)
        
        # 验证可能触发的 Agent 调用
        next_action = result.get("next_action")
        if next_action == "call_status":
            # 继续执行到 status_agent
            result = workflow.invoke(result)
            assert_state_valid(result)
            
            # 如果 status_agent 完成，可能继续调用 plan_agent
            if result.get("completion_status") == "COMPLETED":
                # 回到主 Agent 再决策
                result = workflow.invoke(result)
                assert_state_valid(result)
    
    def test_workflow_resume_mechanism(self, workflow):
        """测试恢复执行机制"""
        # 第一轮：触发提问
        state = create_initial_state("我想追求一个女生")
        result = workflow.invoke(state)
        assert_state_valid(result)
        
        # 如果需要提问
        if result.get("next_action") == "ask_user" and result.get("current_agent"):
            current_agent = result.get("current_agent")
            resume_point = result.get("agent_resume_point")
            
            # 模拟用户回答
            result = run_workflow_turn(workflow, result, "她是我同事，我们认识三个月了")
            
            # 验证恢复执行
            assert_state_valid(result)
            # 应该恢复到之前的 Agent 继续执行
            # 或者已经完成并清除恢复状态
            if result.get("current_agent") == current_agent:
                assert result.get("agent_resume_point") == resume_point, "应该保持恢复点"
            else:
                # 已经完成，清除恢复状态
                assert result.get("current_agent") is None or result.get("current_agent") == "", "应该清除恢复状态"
    
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
    
    def test_workflow_multi_turn_continuity(self, workflow):
        """测试多轮对话连贯性"""
        # 第一轮
        state = create_initial_state("我喜欢一个女生")
        result = workflow.invoke(state)
        
        # 第二轮
        result = run_workflow_turn(workflow, result, "她是我同事")
        
        # 第三轮
        result = run_workflow_turn(workflow, result, "我们认识三个月了")
        
        # 验证对话历史
        messages = result.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) >= 3, "应该有至少3条用户消息"
        
        # 验证上下文保持
        user_context = result.get("user_context", {})
        assert user_context is not None, "应该有 user_context"






