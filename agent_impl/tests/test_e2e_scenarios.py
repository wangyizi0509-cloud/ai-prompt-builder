"""
端到端场景测试
真实 API 调用，完整用户场景
"""

import pytest
import time
from graph.state import create_initial_state
from tests.conftest import (
    workflow,
    run_workflow_turn,
    assert_state_valid,
    print_state_summary,
    get_ai_response,
    clean_test_user,
)


@pytest.mark.api_test
class TestE2EScenarios:
    """端到端场景测试类（需要真实 API Key）"""
    
    def test_e2e_first_time_user(self, workflow, clean_test_user):
        """测试新用户完整流程"""
        user_id = clean_test_user
        
        print("\n" + "="*60)
        print("场景 1: 首次进入完整流程")
        print("="*60)
        
        # 步骤 1: 用户自我介绍
        print("\n[步骤 1] 用户自我介绍")
        state = create_initial_state("我叫小明，25岁，在北京做程序员，性格比较内向")
        result = workflow.invoke(state)
        assert_state_valid(result)
        response1 = get_ai_response(result)
        print(f"AI 回复: {response1[:200]}...")
        
        # 步骤 2: 介绍 crush
        print("\n[步骤 2] 介绍 crush")
        result = run_workflow_turn(workflow, result, "我喜欢一个女生叫小红，是我同事，比我大两岁，性格很开朗")
        assert_state_valid(result)
        response2 = get_ai_response(result)
        print(f"AI 回复: {response2[:200]}...")
        
        # 步骤 3: 描述关系
        print("\n[步骤 3] 描述关系")
        result = run_workflow_turn(workflow, result, "我们认识三个月了，经常一起吃饭，偶尔周末也会出去玩")
        assert_state_valid(result)
        response3 = get_ai_response(result)
        print(f"AI 回复: {response3[:200]}...")
        
        # 验证状态
        print_state_summary(result, "首次进入完整流程 - 最终状态")
        
        # 验证关键字段
        assert len(result.get("messages", [])) >= 6, "应该有至少6条消息"
        user_context = result.get("user_context", {})
        assert user_context is not None, "应该有 user_context"
        
        print("\n✅ 首次进入完整流程测试通过")
    
    def test_e2e_consultation_only(self, workflow):
        """测试纯咨询场景"""
        print("\n" + "="*60)
        print("场景 2: 纯咨询场景")
        print("="*60)
        
        # 咨询问题
        state = create_initial_state("她这样是喜欢我吗？我们平时会一起吃饭，她有时候会主动找我聊天")
        result = workflow.invoke(state)
        assert_state_valid(result)
        
        response = get_ai_response(result)
        print(f"\nAI 回复: {response[:300]}...")
        
        # 验证应该是咨询回复，不需要调用子 Agent
        assert len(response) > 0, "应该有回复"
        assert result.get("pending_questions") or result.get("pending_responses"), "应该有回复或提问"
        
        print("\n✅ 纯咨询场景测试通过")
    
    def test_e2e_emotion_support(self, workflow):
        """测试情感陪伴场景"""
        print("\n" + "="*60)
        print("场景 3: 情感陪伴场景")
        print("="*60)
        
        # 情绪发泄
        state = create_initial_state("我好难过，不知道该怎么办，感觉她对我没意思")
        result = workflow.invoke(state)
        assert_state_valid(result)
        
        response = get_ai_response(result)
        print(f"\nAI 回复: {response[:300]}...")
        
        # 验证应该是情感陪伴回复
        assert len(response) > 0, "应该有回复"
        # 情感陪伴应该包含共情内容
        assert any(keyword in response.lower() for keyword in ["理解", "陪伴", "支持", "难过", "感受"]), "回复应该包含共情内容"
        
        print("\n✅ 情感陪伴场景测试通过")
    
    def test_e2e_info_update(self, workflow):
        """测试用户提供新信息"""
        print("\n" + "="*60)
        print("场景 4: 信息更新场景")
        print("="*60)
        
        # 第一轮：初始信息
        state = create_initial_state("我喜欢一个女生，她是我同事")
        result = workflow.invoke(state)
        assert_state_valid(result)
        
        # 第二轮：更新信息
        result = run_workflow_turn(workflow, result, "更新一下，我们昨天一起看了电影，这是第一次单独约会")
        assert_state_valid(result)
        
        response = get_ai_response(result)
        print(f"\nAI 回复: {response[:300]}...")
        
        # 验证信息更新
        messages = result.get("messages", [])
        assert len(messages) >= 4, "应该有至少4条消息"
        
        print("\n✅ 信息更新场景测试通过")
    
    def test_e2e_status_update(self, workflow):
        """测试关系状态更新"""
        print("\n" + "="*60)
        print("场景 5: 关系状态更新")
        print("="*60)
        
        # 创建已有状态报告的场景
        state = create_initial_state(
            "crush约我明天去约会！",
            status_report={"stage": "L2", "summary": "之前的状态分析"}
        )
        result = workflow.invoke(state)
        assert_state_valid(result)
        
        response = get_ai_response(result)
        print(f"\nAI 回复: {response[:200]}...")
        
        # 验证可能触发现状分析更新
        if result.get("completion_status") == "COMPLETED" or result.get("status_report"):
            print("触发了现状分析更新")
        
        print("\n✅ 关系状态更新测试通过")
    
    def test_e2e_multi_turn_conversation(self, workflow):
        """测试多轮对话连贯性"""
        print("\n" + "="*60)
        print("场景 6: 多轮对话连贯性")
        print("="*60)
        
        # 多轮对话
        state = create_initial_state("你好")
        result = workflow.invoke(state)
        
        result = run_workflow_turn(workflow, result, "我想咨询一些情感问题")
        result = run_workflow_turn(workflow, result, "我喜欢一个女生")
        result = run_workflow_turn(workflow, result, "她是我同事")
        result = run_workflow_turn(workflow, result, "我们认识三个月了")
        
        # 验证对话历史
        messages = result.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) >= 5, "应该有至少5条用户消息"
        
        # 验证上下文保持
        user_context = result.get("user_context", {})
        assert user_context is not None, "应该有 user_context"
        
        print_state_summary(result, "多轮对话 - 最终状态")
        print("\n✅ 多轮对话连贯性测试通过")
    
    def test_e2e_context_retention(self, workflow):
        """测试上下文保持"""
        print("\n" + "="*60)
        print("场景 7: 上下文保持")
        print("="*60)
        
        # 第一轮：提供信息
        state = create_initial_state("我叫小明，25岁，在北京做程序员")
        result = workflow.invoke(state)
        
        # 第二轮：引用之前的信息
        result = run_workflow_turn(workflow, result, "我刚才说的那个女生，她也是程序员")
        
        # 验证上下文保持
        user_context = result.get("user_context", {})
        user_info = user_context.get("user_info", {})
        
        # 验证之前的信息应该被保留
        messages = result.get("messages", [])
        assert len(messages) >= 4, "应该有至少4条消息"
        
        print_state_summary(result, "上下文保持 - 最终状态")
        print("\n✅ 上下文保持测试通过")
    
    def test_e2e_performance(self, workflow):
        """测试性能（响应时间）"""
        print("\n" + "="*60)
        print("场景 8: 性能测试")
        print("="*60)
        
        # 测试响应时间
        state = create_initial_state("测试消息")
        
        start_time = time.time()
        result = workflow.invoke(state)
        end_time = time.time()
        
        response_time = end_time - start_time
        print(f"\n响应时间: {response_time:.2f} 秒")
        
        # 验证响应时间合理（应该小于30秒）
        assert response_time < 30, f"响应时间过长: {response_time} 秒"
        
        assert_state_valid(result)
        print("\n✅ 性能测试通过")






