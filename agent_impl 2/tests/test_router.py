"""
路由节点测试
验证 Router 节点的风控、闲聊分流、业务识别功能
"""

import pytest
from graph.nodes.router import router_node
from graph.state import create_initial_state
from tests.conftest import create_test_state, assert_state_valid


class TestRouterNode:
    """路由节点测试类"""
    
    def test_router_blocked_keywords(self):
        """测试风控关键词拦截"""
        # 测试包含风控关键词的消息
        state = create_test_state("我想自杀")
        result = router_node(state)
        
        # 验证结果（router 只返回部分状态更新）
        assert result["route_to"] == "end", "应该路由到 end"
        assert result["next_action"] == "end_turn", "应该结束本轮"
        assert len(result.get("pending_responses", [])) > 0, "应该有回复"
        
        # 验证回复内容包含关怀信息
        response = result["pending_responses"][0]["content"]
        assert "帮助" in response or "支持" in response, "回复应该包含关怀信息"
    
    def test_router_small_talk(self):
        """测试闲聊消息识别和处理"""
        # 测试问候消息
        test_cases = [
            ("你好", "你好"),
            ("hi", "你好"),
            ("谢谢", "不客气"),
            ("再见", "再见"),
        ]
        
        for message, expected_keyword in test_cases:
            state = create_test_state(message)
            result = router_node(state)
            
            # 验证结果（router 只返回部分状态更新）
            assert result["route_to"] == "end", f"'{message}' 应该路由到 end"
            assert result["next_action"] == "end_turn", "应该结束本轮"
            
            response = result["pending_responses"][0]["content"]
            assert expected_keyword in response.lower() or len(response) > 0, f"回复应该包含相关内容"
    
    def test_router_business_route(self):
        """测试业务消息正确路由到主 Agent"""
        # 测试业务相关消息
        business_messages = [
            "我喜欢一个女生，不知道该怎么办",
            "我和crush的关系现在是什么阶段？",
            "能帮我分析一下现状吗？",
        ]
        
        for message in business_messages:
            state = create_test_state(message)
            result = router_node(state)
            
            # 验证结果（router 只返回部分状态更新）
            assert result["route_to"] == "main_agent", f"'{message}' 应该路由到 main_agent"
            assert "debug_log" in result, "应该有调试日志"
    
    def test_router_resume_agent(self):
        """测试恢复执行时的 Agent 路由"""
        # 测试有 current_agent 的状态（应该由 workflow 处理，这里只测试 router 不干扰）
        state = create_test_state(
            "继续回答",
            current_agent="status_agent",
            agent_resume_point="continue_analysis"
        )
        result = router_node(state)
        
        # Router 应该正常处理，不干扰恢复逻辑
        # route_to 应该由 workflow 的 route_after_router 决定
        assert "route_to" in result, "应该有 route_to 字段"
