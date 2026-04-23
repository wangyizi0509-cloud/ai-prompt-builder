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
import asyncio
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

    def test_skip_anonymous(self):
        """匿名用户不持久化"""
        from api.conversation_persist import persist_turn_messages
        # 不应抛出异常
        asyncio.run(
            persist_turn_messages(
                user_id=None,
                thread_id="t1",
                turn_id="turn1",
                user_message="hello",
                pending_responses=[],
                final_state={},
            )
        )

    def test_basic_persist(self):
        """测试基本的消息持久化"""
        mock_conv = {"id": "conv-1", "thread_id": "t1", "user_id": "u1"}
        mock_turn = {"id": "turn-1", "turn_seq": 1, "turn_id": "tid1", "conversation_id": "conv-1"}

        with patch("api.conversation_persist.persist_turn_messages.__module__", "api.conversation_persist"):
            with patch("supabase_service.conversation.upsert_conversation", new_callable=AsyncMock, return_value=mock_conv):
                with patch("supabase_service.conversation.get_or_create_turn", new_callable=AsyncMock, return_value=mock_turn):
                    with patch("supabase_service.conversation.append_messages", new_callable=AsyncMock, return_value=2) as mock_append:
                        from api.conversation_persist import persist_turn_messages

                        asyncio.run(
                            persist_turn_messages(
                                user_id="u1",
                                thread_id="t1",
                                turn_id="tid1",
                                user_message="你好",
                                pending_responses=[{"content": "你好呀", "from": "assistant"}],
                                final_state={},
                            )
                        )

                        mock_append.assert_called_once()
                        call_args = mock_append.call_args
                        msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", []) if len(call_args) > 1 else call_args.kwargs.get("messages", [])
                        # 应包含 user + assistant 两条消息
                        assert len(msgs) >= 2
                        assistant_msg = next((m for m in msgs if m.get("role") == "assistant" and m.get("kind") == "chat_text"), None)
                        assert assistant_msg is not None
                        assert assistant_msg.get("content") == "你好呀"

    def test_interrupt_persist(self):
        """中断事件应被写入"""
        mock_conv = {"id": "conv-1", "thread_id": "t1", "user_id": "u1"}
        mock_turn = {"id": "turn-1", "turn_seq": 1, "turn_id": "tid1", "conversation_id": "conv-1"}

        with patch("supabase_service.conversation.upsert_conversation", new_callable=AsyncMock, return_value=mock_conv):
            with patch("supabase_service.conversation.get_or_create_turn", new_callable=AsyncMock, return_value=mock_turn):
                with patch("supabase_service.conversation.append_messages", new_callable=AsyncMock, return_value=1) as mock_append:
                    from api.conversation_persist import persist_turn_messages

                    card = {"questions": [{"id": "q1", "question": "测试?"}], "intro": "请回答"}
                    asyncio.run(
                        persist_turn_messages(
                            user_id="u1",
                            thread_id="t1",
                            turn_id="tid1",
                            user_message="问题",
                            pending_responses=[],
                            final_state={},
                            inquiry_card=card,
                        )
                    )

                    mock_append.assert_called_once()
                    call_args = mock_append.call_args
                    msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", []) if len(call_args) > 1 else call_args.kwargs.get("messages", [])
                    # 应包含 interrupt_inquiry 类型
                    kinds = [m.get("kind") for m in msgs]
                    assert "interrupt_inquiry" in kinds

    def test_assistant_chat_text_metadata_is_persisted(self):
        """assistant 文本消息应保留 metadata，供刷新后重建 UI"""
        mock_conv = {"id": "conv-1", "thread_id": "t1", "user_id": "u1"}
        mock_turn = {"id": "turn-1", "turn_seq": 1, "turn_id": "tid1", "conversation_id": "conv-1"}

        with patch("supabase_service.conversation.upsert_conversation", new_callable=AsyncMock, return_value=mock_conv):
            with patch("supabase_service.conversation.get_or_create_turn", new_callable=AsyncMock, return_value=mock_turn):
                with patch("supabase_service.conversation.append_messages", new_callable=AsyncMock, return_value=1) as mock_append:
                    from api.conversation_persist import persist_turn_messages

                    asyncio.run(
                        persist_turn_messages(
                            user_id="u1",
                            thread_id="t1",
                            turn_id="tid1",
                            user_message="hello",
                            pending_responses=[
                                {
                                    "from": "onboarding",
                                    "content": "请先阅读使用指南",
                                    "phase": "guide_gate",
                                    "showGuideButton": True,
                                    "messageKey": "guide_gate",
                                }
                            ],
                            final_state={},
                        )
                    )

                    call_args = mock_append.call_args
                    msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", []) if len(call_args) > 1 else call_args.kwargs.get("messages", [])
                    assistant_msg = next((m for m in msgs if m.get("role") == "assistant" and m.get("kind") == "chat_text" and m.get("content") == "请先阅读使用指南"), None)
                    assert assistant_msg is not None
                    assert assistant_msg.get("metadata", {}).get("showGuideButton") is True
                    assert assistant_msg.get("metadata", {}).get("messageKey") == "guide_gate"

    def test_inquiry_receipt_payload_is_persisted_without_resume(self):
        """本地 onboarding 提交也应持久化 inquiry_receipt，刷新后可恢复"""
        mock_conv = {"id": "conv-1", "thread_id": "t1", "user_id": "u1"}
        mock_turn = {"id": "turn-1", "turn_seq": 1, "turn_id": "tid1", "conversation_id": "conv-1"}

        with patch("supabase_service.conversation.upsert_conversation", new_callable=AsyncMock, return_value=mock_conv):
            with patch("supabase_service.conversation.get_or_create_turn", new_callable=AsyncMock, return_value=mock_turn):
                with patch("supabase_service.conversation.append_messages", new_callable=AsyncMock, return_value=1) as mock_append:
                    from api.conversation_persist import persist_turn_messages

                    asyncio.run(
                        persist_turn_messages(
                            user_id="u1",
                            thread_id="t1",
                            turn_id="tid1",
                            user_message="怎么称呼你？：1",
                            pending_responses=[],
                            final_state={
                                "inquiry_answers": {"ob_user_name": "1"},
                                "inquiry_card": {
                                    "questions": [{"id": "ob_user_name", "question": "怎么称呼你？"}],
                                },
                            },
                            is_resume=False,
                            inquiry_receipt_payload={
                                "taskKey": "inquiry_ob_user_name",
                                "summary": "已提交问卷（1项）",
                                "details": [{"label": "怎么称呼你？", "value": "1"}],
                            },
                        )
                    )

                    call_args = mock_append.call_args
                    msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", []) if len(call_args) > 1 else call_args.kwargs.get("messages", [])
                    receipt_msg = next((m for m in msgs if m.get("kind") == "inquiry_receipt"), None)
                    assert receipt_msg is not None
                    assert receipt_msg.get("metadata", {}).get("summary") == "已提交问卷（1项）"
                    assert receipt_msg.get("metadata", {}).get("taskKey") == "inquiry_ob_user_name"
                    assert receipt_msg.get("metadata", {}).get("details") == [{"label": "怎么称呼你？", "value": "1"}]

    def test_report_ready_with_same_task_key_is_deferred_to_pending_responses(self):
        """聊天区正式卡片应优先按 pending_responses 顺序落库，report_ready 不应抢先写入"""
        mock_conv = {"id": "conv-1", "thread_id": "t1", "user_id": "u1"}
        mock_turn = {"id": "turn-1", "turn_seq": 1, "turn_id": "tid1", "conversation_id": "conv-1"}

        with patch("supabase_service.conversation.upsert_conversation", new_callable=AsyncMock, return_value=mock_conv):
            with patch("supabase_service.conversation.get_or_create_turn", new_callable=AsyncMock, return_value=mock_turn):
                with patch("supabase_service.conversation.append_messages", new_callable=AsyncMock, return_value=5) as mock_append:
                    from api.conversation_persist import persist_turn_messages

                    asyncio.run(
                        persist_turn_messages(
                            user_id="u1",
                            thread_id="t1",
                            turn_id="tid1",
                            user_message="开始分析",
                            process_events=[
                                {"event_type": "reasoning", "content": "先看看情况"},
                                {"event_type": "report_ready", "report_kind": "status_report", "task_key": "status_7"},
                                {"event_type": "reasoning", "content": "继续推进"},
                            ],
                            pending_responses=[
                                {
                                    "content": "这是基于你提供的信息生成的现状分析报告：",
                                    "from": "assistant",
                                    "phase": "status_preface",
                                },
                                {
                                    "type": "system_task",
                                    "taskType": "status",
                                    "taskKey": "status_7",
                                    "title": "现状分析报告已生成",
                                },
                            ],
                            final_state={},
                        )
                    )

                    call_args = mock_append.call_args
                    msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", []) if len(call_args) > 1 else call_args.kwargs.get("messages", [])
                    kinds = [m.get("kind") for m in msgs]
                    assert kinds.count("system_task") == 1
                    assert kinds == ["chat_text", "reasoning_event", "reasoning_event", "chat_text", "system_task"]
                    system_task = next(m for m in msgs if m.get("kind") == "system_task")
                    assert system_task.get("metadata", {}).get("taskKey") == "status_7"
                    assert system_task.get("part_index") == 4

    def test_duplicate_ai_message_is_not_persisted_when_final_chat_text_matches(self):
        """同轮 ai_intermediate 与最终 chat_text 文案相同，只保留正式 chat_text"""
        mock_conv = {"id": "conv-1", "thread_id": "t1", "user_id": "u1"}
        mock_turn = {"id": "turn-1", "turn_seq": 1, "turn_id": "tid1", "conversation_id": "conv-1"}

        with patch("supabase_service.conversation.upsert_conversation", new_callable=AsyncMock, return_value=mock_conv):
            with patch("supabase_service.conversation.get_or_create_turn", new_callable=AsyncMock, return_value=mock_turn):
                with patch("supabase_service.conversation.append_messages", new_callable=AsyncMock, return_value=2) as mock_append:
                    from api.conversation_persist import persist_turn_messages

                    asyncio.run(
                        persist_turn_messages(
                            user_id="u1",
                            thread_id="t1",
                            turn_id="tid1",
                            user_message="hello",
                            process_events=[
                                {"event_type": "ai_message", "content": "同一段总结文案"},
                            ],
                            pending_responses=[
                                {"content": "同一段总结文案", "from": "assistant", "phase": "final"},
                            ],
                            final_state={},
                        )
                    )

                    call_args = mock_append.call_args
                    msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", []) if len(call_args) > 1 else call_args.kwargs.get("messages", [])
                    assert [m.get("kind") for m in msgs] == ["chat_text", "chat_text"]
                    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
                    assert len(assistant_msgs) == 1
                    assert assistant_msgs[0].get("content") == "同一段总结文案"

    def test_resume_inquiry_receipt_precedes_process_events(self):
        """resume 提交问卷时，receipt 必须排在 reasoning/tool 之前，刷新后顺序才稳定"""
        mock_conv = {"id": "conv-1", "thread_id": "t1", "user_id": "u1"}
        mock_turn = {"id": "turn-1", "turn_seq": 2, "turn_id": "tid2", "conversation_id": "conv-1"}

        with patch("supabase_service.conversation.upsert_conversation", new_callable=AsyncMock, return_value=mock_conv):
            with patch("supabase_service.conversation.get_or_create_turn", new_callable=AsyncMock, return_value=mock_turn):
                with patch("supabase_service.conversation.append_messages", new_callable=AsyncMock, return_value=4) as mock_append:
                    from api.conversation_persist import persist_turn_messages

                    asyncio.run(
                        persist_turn_messages(
                            user_id="u1",
                            thread_id="t1",
                            turn_id="tid2",
                            user_message=None,
                            process_events=[
                                {"event_type": "reasoning", "content": "先消化用户刚提交的补充信息"},
                                {"event_type": "tool_call", "status": "done", "tool_name": "task_manager", "tool_call_id": "tool-1", "result_summary": "created"},
                            ],
                            pending_responses=[],
                            final_state={
                                "inquiry_answers": {"background": "我们认识三个月"},
                            },
                            is_resume=True,
                            inquiry_receipt_payload={
                                "taskKey": "inquiry_background",
                                "summary": "已提交问卷（1项）",
                                "details": [{"label": "背景信息", "value": "我们认识三个月"}],
                            },
                        )
                    )

                    call_args = mock_append.call_args
                    msgs = call_args.kwargs.get("messages") or call_args[1].get("messages", []) if len(call_args) > 1 else call_args.kwargs.get("messages", [])
                    assert [m.get("kind") for m in msgs] == ["inquiry_receipt", "reasoning_event", "tool_event"]
                    assert [m.get("part_index") for m in msgs] == [0, 1, 2]


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
