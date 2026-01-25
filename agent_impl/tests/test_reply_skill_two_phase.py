"""
测试回复 Skill 两阶段状态化改造

验证 consult_answer 和 emotion_support 的：
1. Phase 1: xxx(action="enable") 设置 xxx_mode=True
2. Phase 2: xxx(action="complete") 设置 xxx_mode=False
3. ToolMessage 动态简化
4. 兜底重试逻辑
"""

import pytest
from tests.conftest import create_test_state


# ============================================================
# Consult Answer Tool Tests
# ============================================================

class TestConsultAnswerPhase1:
    """Phase 1: 进入解答模式"""

    def test_consult_enable_sets_consult_mode_true(self, monkeypatch):
        """consult_answer(action="enable") 应该设置 consult_mode=True"""
        state = create_test_state("什么是推拉？")
        state["consult_mode"] = False
        state["messages"].append({
            "role": "assistant",
            "tool_calls": [{
                "id": "tc_enable",
                "name": "consult_answer",
                "args": {"action": "enable"},
            }],
        })

        from graph.workflow import skill_tools_node
        from langgraph.prebuilt import ToolNode

        def _mock_invoke(self, state, config=None):
            return {
                "messages": [{
                    "role": "tool",
                    "content": '{"action": "enable_consult_mode"}',
                    "tool_call_id": "tc_enable",
                    "name": "consult_answer",
                }],
            }

        monkeypatch.setattr(ToolNode, "invoke", _mock_invoke)

        out = skill_tools_node(state)

        # 验证状态设置
        assert out.get("consult_mode") is True
        assert out.get("consult_mode_tool_message_id") is not None
        # 注意：不设置 _pending_action
        assert out.get("_pending_action") is None or out.get("_pending_action") == ""
        
        # 验证 ToolMessage 包含策略内容
        messages = out.get("messages", [])
        assert len(messages) > 0
        tool_msg = messages[0]
        assert "解答模式" in tool_msg.get("content", "")
        assert "解答" in tool_msg.get("content", "")


class TestConsultAnswerPhase2:
    """Phase 2: 完成解答"""

    def test_consult_complete_sets_consult_mode_false(self, monkeypatch):
        """consult_answer(action="complete") 应该设置 consult_mode=False"""
        state = create_test_state("测试")
        state["consult_mode"] = True  # 已经处于解答模式
        state["current_agent"] = "main_agent"
        state["messages"].append({
            "role": "assistant",
            "content": "推拉就是忽冷忽热...",  # 模型的回复内容
            "tool_calls": [{
                "id": "tc_complete",
                "name": "consult_answer",
                "args": {"action": "complete"},
            }],
        })

        from graph.workflow import skill_tools_node
        from langgraph.prebuilt import ToolNode

        def _mock_invoke(self, state, config=None):
            return {
                "messages": [{
                    "role": "tool",
                    "content": '{"action": "complete_consult_mode"}',
                    "tool_call_id": "tc_complete",
                    "name": "consult_answer",
                }],
            }

        monkeypatch.setattr(ToolNode, "invoke", _mock_invoke)

        out = skill_tools_node(state)

        # 验证状态恢复
        assert out.get("consult_mode") is False
        
        # 验证 ToolMessage 包含关闭确认
        messages = out.get("messages", [])
        assert len(messages) > 0
        tool_msg = messages[0]
        assert "已关闭" in tool_msg.get("content", "") or "解答模式" in tool_msg.get("content", "")


# ============================================================
# Emotion Support Tool Tests
# ============================================================

class TestEmotionSupportPhase1:
    """Phase 1: 进入陪伴模式"""

    def test_emotion_enable_sets_emotion_mode_true(self, monkeypatch):
        """emotion_support(action="enable") 应该设置 emotion_mode=True"""
        state = create_test_state("好烦啊")
        state["emotion_mode"] = False
        state["messages"].append({
            "role": "assistant",
            "tool_calls": [{
                "id": "tc_enable",
                "name": "emotion_support",
                "args": {"action": "enable"},
            }],
        })

        from graph.workflow import skill_tools_node
        from langgraph.prebuilt import ToolNode

        def _mock_invoke(self, state, config=None):
            return {
                "messages": [{
                    "role": "tool",
                    "content": '{"action": "enable_emotion_mode"}',
                    "tool_call_id": "tc_enable",
                    "name": "emotion_support",
                }],
            }

        monkeypatch.setattr(ToolNode, "invoke", _mock_invoke)

        out = skill_tools_node(state)

        # 验证状态设置
        assert out.get("emotion_mode") is True
        assert out.get("emotion_mode_tool_message_id") is not None
        # 注意：不设置 _pending_action
        assert out.get("_pending_action") is None or out.get("_pending_action") == ""
        
        # 验证 ToolMessage 包含策略内容
        messages = out.get("messages", [])
        assert len(messages) > 0
        tool_msg = messages[0]
        assert "陪伴模式" in tool_msg.get("content", "")


class TestEmotionSupportPhase2:
    """Phase 2: 完成陪伴"""

    def test_emotion_complete_sets_emotion_mode_false(self, monkeypatch):
        """emotion_support(action="complete") 应该设置 emotion_mode=False"""
        state = create_test_state("测试")
        state["emotion_mode"] = True  # 已经处于陪伴模式
        state["current_agent"] = "main_agent"
        state["messages"].append({
            "role": "assistant",
            "content": "害，谁还没个想原地爆炸的时候...",  # 模型的回复内容
            "tool_calls": [{
                "id": "tc_complete",
                "name": "emotion_support",
                "args": {"action": "complete"},
            }],
        })

        from graph.workflow import skill_tools_node
        from langgraph.prebuilt import ToolNode

        def _mock_invoke(self, state, config=None):
            return {
                "messages": [{
                    "role": "tool",
                    "content": '{"action": "complete_emotion_mode"}',
                    "tool_call_id": "tc_complete",
                    "name": "emotion_support",
                }],
            }

        monkeypatch.setattr(ToolNode, "invoke", _mock_invoke)

        out = skill_tools_node(state)

        # 验证状态恢复
        assert out.get("emotion_mode") is False
        
        # 验证 ToolMessage 包含关闭确认
        messages = out.get("messages", [])
        assert len(messages) > 0
        tool_msg = messages[0]
        assert "已关闭" in tool_msg.get("content", "") or "陪伴模式" in tool_msg.get("content", "")


# ============================================================
# Message Simplification Tests
# ============================================================

class TestMessageSimplification:
    """测试消息动态简化"""

    def test_consult_phase1_message_simplified_after_mode_false(self):
        """当 consult_mode=False 时，Phase 1 的 ToolMessage 应该被简化"""
        from graph.message_builder import build_conversation_history
        from graph.tools.consult_answer_tool import CONSULT_MODE_STRATEGY, CONSULT_MODE_SIMPLE

        # 创建包含 Phase 1 ToolMessage 的状态
        state = create_test_state("测试")
        phase1_msg_id = "phase1_consult_msg_123"
        state["consult_mode"] = False  # 已经完成解答
        state["consult_mode_tool_message_id"] = phase1_msg_id
        
        # 添加 Phase 1 的详细策略消息
        state["messages"].append({
            "role": "tool",
            "id": phase1_msg_id,
            "name": "consult_answer",
            "content": f"已进入解答模式。\n\n{CONSULT_MODE_STRATEGY}",
            "tool_call_id": "tc_1",
        })

        # 构建历史消息
        history = build_conversation_history(state, max_turns=10)
        
        # 找到 Phase 1 的消息
        simplified_msg = None
        for msg in history:
            if hasattr(msg, "content") and "解答" in msg.content:
                simplified_msg = msg
                break
        
        # 验证消息被简化（不包含详细策略）
        assert simplified_msg is not None
        assert CONSULT_MODE_SIMPLE in simplified_msg.content or "已开启" in simplified_msg.content
        assert "核心定位" not in simplified_msg.content  # 详细策略应该被移除

    def test_emotion_phase1_message_simplified_after_mode_false(self):
        """当 emotion_mode=False 时，Phase 1 的 ToolMessage 应该被简化"""
        from graph.message_builder import build_conversation_history
        from graph.tools.emotion_support_tool import EMOTION_MODE_STRATEGY, EMOTION_MODE_SIMPLE

        # 创建包含 Phase 1 ToolMessage 的状态
        state = create_test_state("测试")
        phase1_msg_id = "phase1_emotion_msg_123"
        state["emotion_mode"] = False  # 已经完成陪伴
        state["emotion_mode_tool_message_id"] = phase1_msg_id
        
        # 添加 Phase 1 的详细策略消息
        state["messages"].append({
            "role": "tool",
            "id": phase1_msg_id,
            "name": "emotion_support",
            "content": f"已进入陪伴模式。\n\n{EMOTION_MODE_STRATEGY}",
            "tool_call_id": "tc_1",
        })

        # 构建历史消息
        history = build_conversation_history(state, max_turns=10)
        
        # 找到 Phase 1 的消息
        simplified_msg = None
        for msg in history:
            if hasattr(msg, "content") and "陪伴" in msg.content:
                simplified_msg = msg
                break
        
        # 验证消息被简化（不包含详细策略）
        assert simplified_msg is not None
        assert EMOTION_MODE_SIMPLE in simplified_msg.content or "已开启" in simplified_msg.content
        assert "核心定位" not in simplified_msg.content  # 详细策略应该被移除


# ============================================================
# Tool Factory Tests
# ============================================================

class TestToolFactory:
    """测试工具工厂函数"""

    def test_get_consult_tool_returns_enable_version_when_false(self):
        """consult_mode=False 时返回 enable-only 版本"""
        from graph.tools.consult_answer_tool import get_consult_tool

        tool = get_consult_tool(False)
        assert tool.name == "consult_answer"
        # enable 版本的参数只有 action="enable"
        schema = tool.args_schema.schema() if hasattr(tool, 'args_schema') else {}
        props = schema.get("properties", {})
        assert "action" in props

    def test_get_consult_tool_returns_complete_version_when_true(self):
        """consult_mode=True 时返回 complete 版本"""
        from graph.tools.consult_answer_tool import get_consult_tool

        tool = get_consult_tool(True)
        assert tool.name == "consult_answer"
        # complete 版本的参数只有 action="complete"
        schema = tool.args_schema.schema() if hasattr(tool, 'args_schema') else {}
        props = schema.get("properties", {})
        assert "action" in props

    def test_get_emotion_tool_returns_enable_version_when_false(self):
        """emotion_mode=False 时返回 enable-only 版本"""
        from graph.tools.emotion_support_tool import get_emotion_tool

        tool = get_emotion_tool(False)
        assert tool.name == "emotion_support"
        schema = tool.args_schema.schema() if hasattr(tool, 'args_schema') else {}
        props = schema.get("properties", {})
        assert "action" in props

    def test_get_emotion_tool_returns_complete_version_when_true(self):
        """emotion_mode=True 时返回 complete 版本"""
        from graph.tools.emotion_support_tool import get_emotion_tool

        tool = get_emotion_tool(True)
        assert tool.name == "emotion_support"
        schema = tool.args_schema.schema() if hasattr(tool, 'args_schema') else {}
        props = schema.get("properties", {})
        assert "action" in props


# ============================================================
# State Independence Tests
# ============================================================

class TestStateIndependence:
    """测试 consult_mode 和 emotion_mode 互不干扰"""

    def test_consult_mode_independent_of_emotion_mode(self, monkeypatch):
        """consult_mode 和 emotion_mode 应该互不干扰"""
        state = create_test_state("测试")
        state["consult_mode"] = False
        state["emotion_mode"] = True  # emotion_mode 开启
        state["messages"].append({
            "role": "assistant",
            "tool_calls": [{
                "id": "tc_enable",
                "name": "consult_answer",
                "args": {"action": "enable"},
            }],
        })

        from graph.workflow import skill_tools_node
        from langgraph.prebuilt import ToolNode

        def _mock_invoke(self, state, config=None):
            return {
                "messages": [{
                    "role": "tool",
                    "content": '{"action": "enable_consult_mode"}',
                    "tool_call_id": "tc_enable",
                    "name": "consult_answer",
                }],
            }

        monkeypatch.setattr(ToolNode, "invoke", _mock_invoke)

        out = skill_tools_node(state)

        # consult_mode 应该变为 True
        assert out.get("consult_mode") is True
        # emotion_mode 不应该被影响（保持 True）
        assert out.get("emotion_mode") is None or out.get("emotion_mode") is True
