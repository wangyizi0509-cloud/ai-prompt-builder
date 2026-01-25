"""
子 Agent 测试
验证三个子 Agent 的功能和恢复执行机制
"""

import pytest
from graph.nodes.status_agent import status_agent_node
from graph.nodes.plan_agent import plan_agent_node
from graph.nodes.guide_agent import guide_agent_node
from graph.state import create_initial_state
from tests.conftest import create_test_state, assert_state_valid, assert_agent_output, workflow


class TestStatusAgent:
    """现状分析 Agent 测试类"""
    
    def test_status_agent_analysis(self, workflow):
        """测试现状分析生成"""
        # 创建有足够信息的场景
        state = create_test_state(
            "我和一个女生认识三个月了，我们是同事，经常一起吃饭，偶尔周末也会出去玩"
        )
        result = workflow.invoke(state)
        
        assert_state_valid(result)
        
        # 验证是否有状态报告（可能需要多轮）
        status_report = result.get("status_report")
        if status_report:
            # v3.x：status_report 可能是 Markdown 字符串（前端直接渲染），不再是 dict
            if isinstance(status_report, dict):
                assert "stage" in status_report or "summary" in status_report, "状态报告应该有内容"
            else:
                assert "情感罗盘" in str(status_report) or "现状分析" in str(status_report), "状态报告应该有内容"
    
    def test_status_agent_ask_questions(self, workflow):
        """测试信息不足时提问"""
        # 创建信息不足的场景
        state = create_test_state("我想追求一个女生")
        result = workflow.invoke(state)
        
        # 如果需要提问
        if result.get("current_agent") == "status_agent" and result.get("agent_resume_point"):
            assert result.get("inquiry_card") is not None or result.get("pending_questions"), "应该有提问卡片"
            assert result.get("question_count", 0) > 0, "应该增加提问计数"
    
    def test_status_agent_resume_after_question(self, workflow):
        """测试提问后恢复执行"""
        # 模拟提问后的恢复场景
        state = create_test_state(
            "她是我同事，我们认识三个月了",
            current_agent="status_agent",
            agent_resume_point="continue_analysis",
            question_count=1,
            collected_info={}
        )
        result = status_agent_node(state)
        
        # 验证结果（node 直接调用可能只返回部分状态）
        assert isinstance(result, dict), "应返回状态字典"
        assert "debug_log" in result, "应包含调试日志"
    
    def test_status_agent_completion_signal(self, workflow):
        """测试完成信号正确设置"""
        # 创建完整的分析场景
        state = create_test_state(
            "我和一个女生认识三个月了，我们是同事，经常一起吃饭"
        )
        result = workflow.invoke(state)
        
        # 如果 status_agent 完成
        if result.get("completion_status"):
            assert result["completion_status"] in ["COMPLETED", "NEED_MORE_INFO", "BLOCKED"], "完成状态应该有效"
            assert "result_summary" in result, "应该有结果摘要"


class TestPlanAgent:
    """行动规划 Agent 测试类"""
    
    def test_plan_agent_generation(self, workflow):
        """测试行动规划生成"""
        # 创建有现状分析的场景
        state = create_test_state(
            "帮我制定一个追求计划",
            status_report={"stage": "L2", "summary": "测试现状分析"}
        )
        result = workflow.invoke(state)
        
        assert_state_valid(result)
        
        # 验证是否有行动规划（可能需要多轮）
        action_plan = result.get("action_plan")
        if action_plan:
            # v3.x：action_plan 可能是 Markdown 字符串（前端直接渲染），不再是 dict
            if isinstance(action_plan, dict):
                assert "goal" in action_plan or "strategy" in action_plan, "行动规划应该有内容"
            else:
                assert "阶段目标" in str(action_plan) or "核心策略" in str(action_plan), "行动规划应该有内容"
    
    def test_plan_agent_ask_questions(self, workflow):
        """测试规划前信息收集"""
        # 创建信息不足的场景
        state = create_test_state(
            "帮我制定计划",
            status_report={"stage": "L2"}
        )
        result = workflow.invoke(state)
        
        # 如果需要提问
        if result.get("current_agent") == "plan_agent" and result.get("agent_resume_point"):
            assert result.get("inquiry_card") is not None or result.get("pending_questions"), "应该有提问卡片"
    
    def test_plan_agent_resume_after_question(self, workflow):
        """测试恢复执行"""
        # 模拟提问后的恢复场景
        state = create_test_state(
            "我想寒假见面时尝试升温",
            current_agent="plan_agent",
            agent_resume_point="continue_planning",
            question_count=1,
            collected_info={},
            status_report={"stage": "L2"}
        )
        result = plan_agent_node(state)
        
        # 验证结果（node 直接调用可能只返回部分状态）
        assert isinstance(result, dict), "应返回状态字典"
        assert "debug_log" in result, "应包含调试日志"


class TestGuideAgent:
    """行动指南 Agent 测试类"""
    
    def test_guide_agent_generation(self, workflow):
        """测试行动指南生成"""
        # 创建有规划的场景
        state = create_test_state(
            "给我具体的行动建议",
            status_report={"stage": "L2"},
            action_plan={"goal": "测试目标", "strategy": "测试策略"}
        )
        result = workflow.invoke(state)
        
        assert_state_valid(result)
        
        # 验证是否有行动指南（可能需要多轮）
        action_guides = result.get("action_guides", [])
        action_guide = result.get("action_guide")
        if action_guides or action_guide:
            assert len(action_guides) > 0 or action_guide is not None, "应该有行动指南"
    
    def test_guide_agent_ask_questions(self, workflow):
        """测试指南生成前提问"""
        # 创建信息不足的场景
        state = create_test_state(
            "给我建议",
            status_report={"stage": "L2"},
            action_plan={"goal": "测试目标"}
        )
        result = workflow.invoke(state)
        
        # 如果需要提问
        if result.get("current_agent") == "guide_agent" and result.get("agent_resume_point"):
            assert result.get("inquiry_card") is not None or result.get("pending_questions"), "应该有提问卡片"
    
    def test_guide_agent_resume_after_question(self, workflow):
        """测试恢复执行"""
        # 模拟提问后的恢复场景
        state = create_test_state(
            "今晚发朋友圈",
            current_agent="guide_agent",
            agent_resume_point="continue_guide",
            question_count=1,
            collected_info={},
            status_report={"stage": "L2"},
            action_plan={"goal": "测试目标"}
        )
        result = guide_agent_node(state)
        
        # 验证结果（node 直接调用可能只返回部分状态）
        assert isinstance(result, dict), "应返回状态字典"
        assert "debug_log" in result, "应包含调试日志"






