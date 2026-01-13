"""
状态管理测试
验证状态管理、持久化、恢复机制
"""

import pytest
from graph.state import (
    create_initial_state,
    AgentState,
    migrate_user_profile_to_context,
    get_active_action_guides,
    get_completed_action_guides,
)
from graph.state_storage import save_state, load_state, delete_state
from graph.context_types import create_empty_user_context, create_empty_history_archive
from tests.conftest import create_test_state, assert_state_valid, clean_test_user


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
        
        # 验证上下文字段
        assert "user_context" in state, "应该有 user_context"
        assert "user_profile" in state, "应该有 user_profile"
        assert "status_report" in state, "应该有 status_report"
        assert "action_plan" in state, "应该有 action_plan"
        assert "action_guides" in state, "应该有 action_guides"
        
        # 验证流程控制字段
        assert "intent_type" in state, "应该有 intent_type"
        assert "next_action" in state, "应该有 next_action"
        assert state["next_action"] == "end_turn", "初始 next_action 应该是 end_turn"
        
        # 验证 Agent 执行状态字段
        assert "current_agent" in state, "应该有 current_agent"
        assert state["current_agent"] is None, "初始 current_agent 应该是 None"
        assert "agent_resume_point" in state, "应该有 agent_resume_point"
        assert "question_count" in state, "应该有 question_count"
        assert state["question_count"] == 0, "初始 question_count 应该是 0"
    
    def test_state_update(self):
        """测试状态更新"""
        state = create_initial_state("初始消息")
        
        # 更新状态
        state["user_message"] = "新消息"
        state["next_action"] = "call_status"
        state["current_agent"] = "status_agent"
        state["question_count"] = 1
        
        # 验证更新
        assert state["user_message"] == "新消息", "user_message 应该更新"
        assert state["next_action"] == "call_status", "next_action 应该更新"
        assert state["current_agent"] == "status_agent", "current_agent 应该更新"
        assert state["question_count"] == 1, "question_count 应该更新"
    
    def test_state_persistence(self, clean_test_user):
        """测试状态持久化"""
        user_id = clean_test_user
        
        # 创建测试状态
        original_state = create_initial_state("测试消息")
        original_state["user_context"]["user_info"]["user_provide"] = "测试用户信息"
        original_state["user_context"]["crush_info"]["crush_name"] = "测试Crush"
        original_state["status_report"] = {"stage": "L2", "summary": "测试报告"}
        original_state["action_plan"] = {"goal": "测试目标", "strategy": "测试策略"}
        
        # 保存状态
        save_state(user_id, original_state)
        
        # 加载状态
        loaded_state = load_state(user_id)
        assert loaded_state is not None, "应该能加载状态"
        
        # 验证关键字段
        assert loaded_state.get("user_message") == original_state.get("user_message"), "user_message 应该一致"
        assert loaded_state.get("user_context", {}).get("user_info", {}).get("user_provide") == "测试用户信息", "user_info 应该一致"
        assert loaded_state.get("user_context", {}).get("crush_info", {}).get("crush_name") == "测试Crush", "crush_name 应该一致"
        assert loaded_state.get("status_report", {}).get("stage") == "L2", "status_report 应该一致"
        assert loaded_state.get("action_plan", {}).get("goal") == "测试目标", "action_plan 应该一致"
        
        # 验证 messages
        assert len(loaded_state.get("messages", [])) == len(original_state.get("messages", [])), "messages 数量应该一致"
    
    def test_state_restore(self, clean_test_user):
        """测试状态恢复"""
        user_id = clean_test_user
        
        # 创建并保存状态
        original_state = create_initial_state("原始消息")
        original_state["user_context"]["user_info"]["user_provide"] = "原始信息"
        save_state(user_id, original_state)
        
        # 修改状态
        original_state["user_message"] = "修改后的消息"
        original_state["user_context"]["user_info"]["user_provide"] = "修改后的信息"
        
        # 从存储恢复
        restored_state = load_state(user_id)
        
        # 验证恢复的状态是原始状态，不是修改后的
        assert restored_state.get("user_message") == "原始消息", "应该恢复原始消息"
        assert restored_state.get("user_context", {}).get("user_info", {}).get("user_provide") == "原始信息", "应该恢复原始信息"
    
    def test_state_resume_agent(self):
        """测试 Agent 恢复执行状态"""
        # 创建恢复状态
        state = create_test_state(
            "继续回答",
            current_agent="status_agent",
            agent_resume_point="continue_analysis",
            question_count=1,
            collected_info={"answer1": "回答1"}
        )
        
        # 验证恢复状态字段
        assert state["current_agent"] == "status_agent", "current_agent 应该正确"
        assert state["agent_resume_point"] == "continue_analysis", "agent_resume_point 应该正确"
        assert state["question_count"] == 1, "question_count 应该正确"
        assert state["collected_info"]["answer1"] == "回答1", "collected_info 应该正确"
        
        # 模拟恢复后清除状态
        state["current_agent"] = None
        state["agent_resume_point"] = None
        state["question_count"] = 0
        
        assert state["current_agent"] is None, "应该清除 current_agent"
        assert state["agent_resume_point"] is None, "应该清除 agent_resume_point"
        assert state["question_count"] == 0, "应该重置 question_count"
    
    def test_state_context_layers(self):
        """测试分层上下文管理"""
        state = create_initial_state("测试消息")
        
        # Layer 1: 静态情报
        user_context = state.get("user_context", {})
        assert user_context is not None, "应该有 Layer 1: user_context"
        assert "user_info" in user_context, "应该有 user_info"
        assert "crush_info" in user_context, "应该有 crush_info"
        assert "both_info" in user_context, "应该有 both_info"
        
        # Layer 2: 工作上下文
        assert "status_report" in state, "应该有 Layer 2: status_report"
        assert "action_plan" in state, "应该有 Layer 2: action_plan"
        assert "action_guides" in state, "应该有 Layer 2: action_guides"
        
        # Layer 3: 滚动对话区
        assert "messages" in state, "应该有 Layer 3: messages"
        assert isinstance(state["messages"], list), "messages 应该是列表"
        
        # Layer 4: 历史存档
        assert "history_archive" in state, "应该有 Layer 4: history_archive"
        history_archive = state.get("history_archive", {})
        assert "status_history" in history_archive, "应该有 status_history"
        assert "guide_history" in history_archive, "应该有 guide_history"
        assert "conversation_archive" in history_archive, "应该有 conversation_archive"
    
    def test_state_migration(self):
        """测试状态迁移（UserProfile -> UserContext）"""
        # 创建旧版 UserProfile
        old_profile = {
            "name": "小明",
            "age": 25,
            "gender": "男",
            "occupation": "程序员",
            "crush_info": "小红，同事",
            "relationship_context": "认识三个月",
            "known_facts": ["经常一起吃饭", "周末出去玩"]
        }
        
        # 迁移到新版 UserContext
        new_context = migrate_user_profile_to_context(old_profile)
        
        # 验证迁移结果
        assert new_context is not None, "应该生成新上下文"
        assert "user_info" in new_context, "应该有 user_info"
        assert "crush_info" in new_context, "应该有 crush_info"
        assert "both_info" in new_context, "应该有 both_info"
        
        # 验证内容迁移
        user_provide = new_context["user_info"].get("user_provide", "")
        assert "小明" in user_provide or "25" in user_provide, "用户信息应该迁移"
        
        crush_provide = new_context["crush_info"].get("user_provide", "")
        assert "小红" in crush_provide, "Crush 信息应该迁移"
        
        both_provide = new_context["both_info"].get("user_provide", "")
        assert "认识三个月" in both_provide, "关系信息应该迁移"
        
        both_fact = new_context["both_info"].get("fact", "")
        assert "一起吃饭" in both_fact or "出去玩" in both_fact, "已知事实应该迁移"
    
    def test_state_action_guides_filter(self):
        """测试行动指南过滤函数"""
        # 创建包含多个指南的状态
        state = create_initial_state("测试")
        state["action_guides"] = [
            {"id": "guide1", "status": "pending", "content": "指南1"},
            {"id": "guide2", "status": "in_progress", "content": "指南2"},
            {"id": "guide3", "status": "completed", "content": "指南3"},
            {"id": "guide4", "status": "pending", "content": "指南4"},
        ]
        
        # 测试获取活跃指南
        active_guides = get_active_action_guides(state["action_guides"])
        assert len(active_guides) == 3, "应该有3个活跃指南"
        assert all(g.get("status") in ["pending", "in_progress"] for g in active_guides), "活跃指南状态应该正确"
        
        # 测试获取已完成指南
        completed_guides = get_completed_action_guides(state["action_guides"])
        assert len(completed_guides) == 1, "应该有1个已完成指南"
        assert completed_guides[0].get("status") == "completed", "已完成指南状态应该正确"
