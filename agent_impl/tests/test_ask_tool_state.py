"""
测试 Ask 工具状态化改造

验证：
1. Phase 1: ask(action="enable") 设置 ask_mode=True
2. Phase 2: ask(questions=[...]) 设置 ask_mode=False
3. ToolMessage 动态简化
"""

import pytest
from tests.conftest import create_test_state


class TestAskToolPhase1:
    """Phase 1: 进入提问模式"""

    def test_ask_enable_sets_ask_mode_true(self, monkeypatch):
        """ask(action="enable") 应该设置 ask_mode=True"""
        state = create_test_state("我想追一个女生")
        state["ask_mode"] = False
        state["messages"].append({
            "role": "assistant",
            "tool_calls": [{
                "id": "tc_enable",
                "name": "ask",
                "args": {"action": "enable"},
            }],
        })

        from graph.workflow import skill_tools_node
        from langgraph.prebuilt import ToolNode

        def _mock_invoke(self, state, config=None):
            return {
                "messages": [{
                    "role": "tool",
                    "content": '{"action": "enable_ask_mode"}',
                    "tool_call_id": "tc_enable",
                    "name": "ask",
                }],
            }

        monkeypatch.setattr(ToolNode, "invoke", _mock_invoke)

        out = skill_tools_node(state)

        # 验证状态设置
        assert out.get("ask_mode") is True
        assert out.get("_pending_action") == "ask"
        assert out.get("ask_mode_tool_message_id") is not None
        
        # 验证 ToolMessage 包含策略内容
        messages = out.get("messages", [])
        assert len(messages) > 0
        tool_msg = messages[0]
        assert "提问模式" in tool_msg.get("content", "")
        assert "提问策略" in tool_msg.get("content", "")


class TestAskToolPhase2:
    """Phase 2: 执行提问"""

    def test_ask_questions_sets_ask_mode_false(self, monkeypatch):
        """ask(questions=[...]) 应该设置 ask_mode=False"""
        state = create_test_state("测试")
        state["ask_mode"] = True  # 已经处于提问模式
        state["current_agent"] = "main_agent"
        state["messages"].append({
            "role": "assistant",
            "tool_calls": [{
                "id": "tc_questions",
                "name": "ask",
                "args": {
                    "questions": [{
                        "id": "q1",
                        "type": "free_input_question",
                        "question": "你们认识多久了？",
                        "is_required": True,
                        "purpose": "了解关系时长",
                    }],
                    "intro": "为了更好地帮你分析",
                    "reasoning": "需要确认基本信息",
                },
            }],
        })

        from graph.workflow import skill_tools_node
        from langgraph.prebuilt import ToolNode

        def _mock_invoke(self, state, config=None):
            return {
                "messages": [{
                    "role": "tool",
                    "content": '{"action": "ask_user", "inquiry_card": {}}',
                    "tool_call_id": "tc_questions",
                    "name": "ask",
                }],
            }

        monkeypatch.setattr(ToolNode, "invoke", _mock_invoke)

        out = skill_tools_node(state)

        # 验证状态恢复
        assert out.get("ask_mode") is False
        
        # 验证 inquiry_card 设置
        assert out.get("inquiry_card") is not None
        assert out.get("pending_questions") == ["你们认识多久了？"]
        assert out.get("agent_resume_point") == "continue_decision"


class TestMessageSimplification:
    """测试消息动态简化"""

    def test_phase1_message_simplified_after_ask_mode_false(self):
        """当 ask_mode=False 时，Phase 1 的 ToolMessage 应该被简化"""
        from graph.message_builder import build_conversation_history
        from graph.tools.ask_tool import ASK_MODE_STRATEGY, ASK_MODE_SIMPLE

        # 创建包含 Phase 1 ToolMessage 的状态
        state = create_test_state("测试")
        phase1_msg_id = "phase1_tool_msg_123"
        state["ask_mode"] = False  # 已经完成提问
        state["ask_mode_tool_message_id"] = phase1_msg_id
        
        # 添加 Phase 1 的详细策略消息
        state["messages"].append({
            "role": "tool",
            "id": phase1_msg_id,
            "name": "ask",
            "content": f"已进入提问模式，请使用 ask 工具向用户提问。\n\n{ASK_MODE_STRATEGY}",
            "tool_call_id": "tc_1",
        })

        # 构建历史消息
        history = build_conversation_history(state, max_turns=10)
        
        # 找到 Phase 1 的消息
        simplified_msg = None
        for msg in history:
            if hasattr(msg, "content") and "提问模式" in msg.content:
                simplified_msg = msg
                break
        
        # 验证消息被简化（不包含详细策略）
        assert simplified_msg is not None
        assert ASK_MODE_SIMPLE in simplified_msg.content or "已进入提问模式" in simplified_msg.content
        assert "题型选择" not in simplified_msg.content  # 详细策略应该被移除


class TestAskToolFactory:
    """测试工具工厂函数"""

    def test_get_ask_tool_returns_enable_version_when_false(self):
        """ask_mode=False 时返回 enable-only 版本"""
        from graph.tools.ask_tool import get_ask_tool

        tool = get_ask_tool(False)
        assert tool.name == "ask"
        # enable 版本的参数只有 action
        schema = tool.args_schema.schema() if hasattr(tool, 'args_schema') else {}
        props = schema.get("properties", {})
        assert "action" in props
        assert "questions" not in props

    def test_get_ask_tool_returns_full_version_when_true(self):
        """ask_mode=True 时返回完整 schema 版本"""
        from graph.tools.ask_tool import get_ask_tool

        tool = get_ask_tool(True)
        assert tool.name == "ask"
        # full 版本的参数包含 questions
        schema = tool.args_schema.schema() if hasattr(tool, 'args_schema') else {}
        props = schema.get("properties", {})
        assert "questions" in props
        assert "intro" in props
        assert "reasoning" in props


class TestBackwardCompatibility:
    """测试向后兼容"""

    def test_ask_user_still_works(self, monkeypatch):
        """原来的 ask_user 调用仍然有效"""
        state = create_test_state("测试")
        state["current_agent"] = "main_agent"
        state["messages"].append({
            "role": "assistant",
            "tool_calls": [{
                "id": "tc_1",
                "name": "ask_user",  # 使用原来的名字
                "args": {
                    "questions": [{"id": "q1", "question": "测试问题"}],
                    "intro": "引导语",
                    "reasoning": "原因",
                },
            }],
        })

        from graph.workflow import skill_tools_node
        from langgraph.prebuilt import ToolNode

        def _mock_invoke(self, state, config=None):
            return {
                "messages": [{
                    "role": "tool",
                    "content": '{"action": "ask_user"}',
                    "tool_call_id": "tc_1",
                    "name": "ask_user",
                }],
            }

        monkeypatch.setattr(ToolNode, "invoke", _mock_invoke)

        out = skill_tools_node(state)

        # 验证原有功能正常
        assert out.get("inquiry_card") is not None
        assert out.get("pending_questions") == ["测试问题"]
