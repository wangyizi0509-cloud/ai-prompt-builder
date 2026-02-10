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

    def test_workflow_interrupt_then_resume(self):
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.types import Command

        from graph.workflow import compile_workflow

        checkpointer = MemorySaver()
        app = compile_workflow(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": "test_workflow_interrupt_resume"}, "checkpointer": checkpointer}

        state = create_initial_state(
            "[[TEST_INTERRUPT]] 请调用 ask_human 并立刻 interrupt，等待用户回答。",
            onboarding_completed=True,
            route_to="main_agent",
        )
        state["inquiry_card"] = None
        state["pending_responses"] = []
        state["last_response_for_continuity"] = None

        out1 = app.invoke(state, config=config)
        assert "__interrupt__" in out1
        interrupts = out1.get("__interrupt__") or []
        first = interrupts[0]
        payload = first.get("value") if isinstance(first, dict) else getattr(first, "value", None)
        assert isinstance(payload, dict)
        assert payload.get("type") == "inquiry_card"
        assert isinstance(payload.get("questions"), list) and payload["questions"]
        assert payload["questions"][0].get("id") == "q1"

        resume_payload = {"answers": {"q1": "A"}}
        out2 = app.invoke(Command(resume=resume_payload), config=config)
        assert "__interrupt__" not in out2
        assert out2.get("inquiry_answers") == resume_payload
        pending = out2.get("pending_responses") or []
        assert isinstance(pending, list)
        assert any(isinstance(r, dict) and r.get("content") for r in pending)




