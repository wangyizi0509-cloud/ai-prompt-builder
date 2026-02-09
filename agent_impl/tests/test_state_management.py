"""
状态管理测试
验证状态管理、持久化、恢复机制
"""

import pytest
from graph.state import (
    create_initial_state,
    AgentState,
)
from graph.workflow import _wrap_step_counter
from graph.context_types import (
    get_active_action_guides,
    get_completed_action_guides,
)
from tests.conftest import create_test_state, assert_state_valid


class TestStateManagement:
    """状态管理测试类"""
    
    def test_state_initialization(self):
        """测试状态初始化"""
        state = create_initial_state("测试消息")
        
        # 验证必需字段
        assert state["user_message"] == "测试消息", "user_message 应该正确"
        assert len(state["messages"]) == 1, "应该有1条初始消息"
        assert state["messages"][0]["role"] == "user", "第一条消息应该是用户消息"
        assert state["messages"][0]["content"] == "测试消息", "消息内容应该正确"
        assert state.get("current_message_id"), "current_message_id 应该存在"
        assert state["messages"][0].get("id") == state["current_message_id"], "首条消息 id 应与 current_message_id 一致"
        
        assert "layer1_memory" in state
        assert "layer2_memory" in state
        assert "layer3_memory" in state
        assert isinstance(state.get("runtime"), dict)
        assert isinstance(state.get("tool_patch_log"), list)
        
        # 验证流程控制字段
        assert "intent_type" in state, "应该有 intent_type"
        
        legacy_keys = {
            "current_agent",
            "agent_resume_point",
            "_tool_caller",
            "_pending_action",
            "_reply_skill_complete",
            "_handoff_target",
            "_handoff_instruction",
            "_submit_result",
            "ask_mode",
            "consult_mode",
            "emotion_mode",
            "status_report",
            "action_plan",
            "action_guides",
            "action_guide",
            "history_archive",
            "task_registry",
            "user_context",
            "user_profile",
        }
        assert legacy_keys.isdisjoint(state.keys())
    
    def test_state_update(self):
        """测试状态更新"""
        state = create_initial_state("初始消息")
        
        # 更新状态
        state["user_message"] = "新消息"
        state["runtime"] = {"foo": "bar"}
        
        # 验证更新
        assert state["user_message"] == "新消息", "user_message 应该更新"
        assert state["runtime"]["foo"] == "bar"
    
    def test_state_context_layers(self):
        """测试分层上下文管理"""
        state = create_initial_state("测试消息")
        
        # Layer 1: 静态情报
        layer1_memory = state.get("layer1_memory", {})
        assert layer1_memory is not None
        assert "full_data" in layer1_memory
        
        # Layer 2: 工作上下文
        assert "layer2_memory" in state
        
        # Layer 3: 滚动对话区
        assert "messages" in state, "应该有 Layer 3: messages"
        assert isinstance(state["messages"], list), "messages 应该是列表"
    
    def test_state_action_guides_filter(self):
        """测试行动指南过滤函数"""
        # 创建包含多个指南的状态
        state = create_initial_state("测试")
        layer2_memory = state.get("layer2_memory", {})
        layer2_memory["action_guides"] = [
            {"id": "guide1", "status": "pending", "content": "指南1"},
            {"id": "guide2", "status": "in_progress", "content": "指南2"},
            {"id": "guide3", "status": "completed", "content": "指南3"},
            {"id": "guide5", "status": "paused", "content": "指南5"},
            {"id": "guide6", "status": "cancelled", "content": "指南6"},
            {"id": "guide4", "status": "pending", "content": "指南4"},
        ]
        state["layer2_memory"] = layer2_memory
        
        # 测试获取活跃指南
        active_guides = get_active_action_guides(state["layer2_memory"])
        assert len(active_guides) == 4, "应该有4个活跃指南"
        assert all(g.get("status") in ["pending", "in_progress", "paused"] for g in active_guides), "活跃指南状态应该正确"
        
        # 测试获取终态指南（已归档）
        completed_guides = get_completed_action_guides(state["layer2_memory"])
        assert len(completed_guides) == 2, "应该有2个终态指南"
        assert all(g.get("status") in ["completed", "cancelled", "expired"] for g in completed_guides), "终态指南状态应该正确"

    def test_wrap_step_counter_adds_message_id(self):
        """测试统一 wrapper 会为 messages 补 id 且不覆盖已有 id"""
        def dummy_node(_state):
            return {"messages": [{"role": "assistant", "content": "hi"}]}

        wrapped = _wrap_step_counter("dummy", dummy_node)
        out = wrapped({})
        assert out["messages"][0].get("id"), "wrapper 应该为消息补 id"

        def dummy_node_with_id(_state):
            return {"messages": [{"role": "assistant", "content": "ok", "id": "fixed-id"}]}

        wrapped_with_id = _wrap_step_counter("dummy_with_id", dummy_node_with_id)
        out_with_id = wrapped_with_id({})
        assert out_with_id["messages"][0].get("id") == "fixed-id", "wrapper 不应覆盖已有 id"





