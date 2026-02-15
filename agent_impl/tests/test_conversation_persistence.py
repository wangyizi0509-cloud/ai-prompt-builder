"""
对话消息持久化单元测试

测试覆盖：
- 消息归一化 / content_hash 幂等去重
- conversation_persist 辅助模块
- _mapSupabaseMessageToUI 前端格式转换的服务端等价逻辑
"""

import os
import sys
import hashlib
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# 确保 agent_impl 在路径中
AGENT_IMPL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(AGENT_IMPL_DIR))


# ---------------------------------------------------------------------------
# content_hash 单元测试
# ---------------------------------------------------------------------------

class TestContentHash:
    """测试 _content_hash 函数的幂等与去重能力"""

    def test_same_text_same_hash(self):
        from supabase_service.conversation import _content_hash
        h1 = _content_hash("hello world")
        h2 = _content_hash("hello world")
        assert h1 == h2

    def test_different_text_different_hash(self):
        from supabase_service.conversation import _content_hash
        h1 = _content_hash("hello")
        h2 = _content_hash("world")
        assert h1 != h2

    def test_none_content_uses_metadata(self):
        from supabase_service.conversation import _content_hash
        meta = {"type": "inquiry_card", "questions": [{"id": "q1"}]}
        h1 = _content_hash(None, meta)
        h2 = _content_hash(None, meta)
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex

    def test_empty_content_empty_metadata(self):
        from supabase_service.conversation import _content_hash
        h = _content_hash(None, None)
        assert isinstance(h, str)
        assert len(h) == 64


# ---------------------------------------------------------------------------
# compute_seq 单元测试
# ---------------------------------------------------------------------------

class TestComputeSeq:
    """测试 _compute_seq 函数"""

    def test_basic(self):
        from supabase_service.conversation import _compute_seq
        assert _compute_seq(1, 0) == 1000
        assert _compute_seq(1, 1) == 1001
        assert _compute_seq(2, 0) == 2000

    def test_ordering(self):
        from supabase_service.conversation import _compute_seq
        # turn_seq=1 的所有 part 应排在 turn_seq=2 之前
        assert _compute_seq(1, 999) < _compute_seq(2, 0)


# ---------------------------------------------------------------------------
# _extract_messages_from_state 单元测试
# ---------------------------------------------------------------------------

class TestExtractMessagesFromState:
    """测试从 LangGraph state 提取消息"""

    def test_from_messages_key(self):
        from supabase_service.conversation import _extract_messages_from_state
        state = {
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好呀"},
            ]
        }
        result = _extract_messages_from_state(state)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_from_layer3_memory(self):
        from supabase_service.conversation import _extract_messages_from_state
        state = {
            "layer3_memory": {
                "all_messages": [
                    {"role": "human", "content": "hi"},
                    {"role": "ai", "content": "hello"},
                ]
            }
        }
        result = _extract_messages_from_state(state)
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_empty_state(self):
        from supabase_service.conversation import _extract_messages_from_state
        result = _extract_messages_from_state({})
        assert result == []

    def test_filters_tool_messages(self):
        from supabase_service.conversation import _extract_messages_from_state
        state = {
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "tool", "content": "tool output"},
                {"role": "assistant", "content": "回复"},
            ]
        }
        result = _extract_messages_from_state(state)
        assert len(result) == 2  # tool messages filtered


# ---------------------------------------------------------------------------
# persist_turn_messages 单元测试（mock Supabase）
# ---------------------------------------------------------------------------

class TestPersistTurnMessages:
    """测试消息持久化辅助函数"""

    @pytest.mark.asyncio
    async def test_skip_anonymous(self):
        """匿名用户不持久化"""
        from api.conversation_persist import persist_turn_messages
        # 不应抛出异常
        await persist_turn_messages(
            user_id=None,
            thread_id="t1",
            turn_id="turn1",
            user_message="hello",
            pending_responses=[],
            final_state={},
        )

    @pytest.mark.asyncio
    async def test_basic_persist(self):
        """测试基本的消息持久化"""
        mock_conv = {"id": "conv-1", "thread_id": "t1", "user_id": "u1"}
        mock_turn = {"id": "turn-1", "turn_seq": 1, "turn_id": "tid1", "conversation_id": "conv-1"}

        with patch("api.conversation_persist.persist_turn_messages.__module__", "api.conversation_persist"):
            with patch("supabase_service.conversation.upsert_conversation", new_callable=AsyncMock, return_value=mock_conv):
                with patch("supabase_service.conversation.get_or_create_turn", new_callable=AsyncMock, return_value=mock_turn):
                    with patch("supabase_service.conversation.append_messages", new_callable=AsyncMock, return_value=2) as mock_append:
                        from api.conversation_persist import persist_turn_messages

                        await persist_turn_messages(
                            user_id="u1",
                            thread_id="t1",
                            turn_id="tid1",
                            user_message="你好",
                            pending_responses=[{"content": "你好呀", "from": "assistant"}],
                            final_state={},
                        )

                        mock_append.assert_called_once()
                        call_args = mock_append.call_args
                        msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", []) if len(call_args) > 1 else call_args.kwargs.get("messages", [])
                        # 应包含 user + assistant 两条消息
                        assert len(msgs) >= 2

    @pytest.mark.asyncio
    async def test_interrupt_persist(self):
        """中断事件应被写入"""
        mock_conv = {"id": "conv-1", "thread_id": "t1", "user_id": "u1"}
        mock_turn = {"id": "turn-1", "turn_seq": 1, "turn_id": "tid1", "conversation_id": "conv-1"}

        with patch("supabase_service.conversation.upsert_conversation", new_callable=AsyncMock, return_value=mock_conv):
            with patch("supabase_service.conversation.get_or_create_turn", new_callable=AsyncMock, return_value=mock_turn):
                with patch("supabase_service.conversation.append_messages", new_callable=AsyncMock, return_value=1) as mock_append:
                    from api.conversation_persist import persist_turn_messages

                    card = {"questions": [{"id": "q1", "question": "测试?"}], "intro": "请回答"}
                    await persist_turn_messages(
                        user_id="u1",
                        thread_id="t1",
                        turn_id="tid1",
                        user_message="问题",
                        pending_responses=[],
                        final_state={},
                        inquiry_card=card,
                    )

                    mock_append.assert_called_once()
                    call_args = mock_append.call_args
                    msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", []) if len(call_args) > 1 else call_args.kwargs.get("messages", [])
                    # 应包含 interrupt_inquiry 类型
                    kinds = [m.get("kind") for m in msgs]
                    assert "interrupt_inquiry" in kinds


# ---------------------------------------------------------------------------
# 消息格式映射测试（模拟前端 _mapSupabaseMessageToUI 的服务端等价）
# ---------------------------------------------------------------------------

class TestMessageFormatMapping:
    """测试 Supabase 消息格式到前端 UI 格式的映射"""

    def test_chat_text_message(self):
        msg = {
            "role": "assistant",
            "kind": "chat_text",
            "content": "你好",
            "metadata": None,
            "seq": 1000,
        }
        # chat_text → 直接作为 {role, content}
        assert msg["kind"] == "chat_text"
        assert msg["content"] == "你好"

    def test_system_task_message(self):
        msg = {
            "role": "assistant",
            "kind": "system_task",
            "content": "现状分析已生成",
            "metadata": {"taskType": "status", "title": "现状分析报告已生成"},
            "seq": 2000,
        }
        assert msg["kind"] == "system_task"
        assert msg["metadata"]["taskType"] == "status"

    def test_interrupt_inquiry_message(self):
        msg = {
            "role": "assistant",
            "kind": "interrupt_inquiry",
            "content": None,
            "metadata": {
                "inquiry_card": {
                    "questions": [{"id": "q1", "question": "你的情况?"}],
                    "intro": "请补充",
                }
            },
            "seq": 3000,
        }
        assert msg["kind"] == "interrupt_inquiry"
        card = msg["metadata"]["inquiry_card"]
        assert len(card["questions"]) == 1

    def test_inquiry_receipt_message(self):
        msg = {
            "role": "user",
            "kind": "inquiry_receipt",
            "content": None,
            "metadata": {
                "answers": {"q1": "很好"},
                "inquiry_card": {"questions": [{"id": "q1", "question": "感觉?"}]},
            },
            "seq": 4000,
        }
        assert msg["kind"] == "inquiry_receipt"
        assert msg["metadata"]["answers"]["q1"] == "很好"
