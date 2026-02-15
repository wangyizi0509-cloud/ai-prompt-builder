"""
对话消息持久化辅助模块

在 /api/chat 和 /api/chat/stream 完成后调用，
将本轮 user/assistant 消息、interrupt 事件、system_task 事件写入 Supabase。

采用后台任务方式写入，不阻塞主响应。失败仅记录日志。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _safe_json_str(value: Any) -> Optional[str]:
    """安全序列化为 JSON 字符串。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


async def persist_turn_messages(
    user_id: str,
    thread_id: str,
    turn_id: str,
    user_message: Optional[str],
    pending_responses: List[Dict[str, Any]],
    final_state: Dict[str, Any],
    is_resume: bool = False,
    inquiry_card: Optional[Dict[str, Any]] = None,
) -> None:
    """
    将本轮对话消息持久化到 Supabase。

    在后台任务中调用，失败不影响主响应流程。

    Args:
        user_id: 用户 ID（None 表示匿名，跳过持久化）
        thread_id: LangGraph thread_id
        turn_id: 本轮请求的 current_message_id
        user_message: 用户输入文本（resume 时可为空）
        pending_responses: 本轮 assistant 的 pending_responses 列表
        final_state: 本轮结束后的 final_state
        is_resume: 是否为 resume 请求
        inquiry_card: 如有中断，传入 inquiry_card
    """
    if not user_id:
        return

    try:
        from supabase_service.conversation import (
            upsert_conversation,
            get_or_create_turn,
            append_messages,
        )

        # 1. 确保会话存在
        conv = await upsert_conversation(user_id, thread_id)
        if not conv:
            logger.warning("persist_turn_messages: failed to upsert conversation for user=%s thread=%s", user_id, thread_id)
            return

        conversation_id = conv["id"]

        # 2. 获取或创建轮次
        turn = await get_or_create_turn(conversation_id, turn_id)
        if not turn:
            logger.warning("persist_turn_messages: failed to get_or_create_turn for conv=%s turn=%s", conversation_id, turn_id)
            return

        turn_seq = turn["turn_seq"]

        # 3. 收集需要写入的消息
        messages_to_write: List[Dict[str, Any]] = []
        part_idx = 0

        # 3a. 用户消息（非 resume 时写入）
        if user_message and not is_resume:
            messages_to_write.append({
                "role": "user",
                "kind": "chat_text",
                "content": user_message,
                "part_index": part_idx,
            })
            part_idx += 1

        # 3b. resume 回执（用户提交问卷的回执）
        if is_resume:
            inquiry_answers = final_state.get("inquiry_answers")
            if inquiry_answers:
                messages_to_write.append({
                    "role": "user",
                    "kind": "inquiry_receipt",
                    "content": None,
                    "metadata": {
                        "answers": inquiry_answers,
                        "inquiry_card": final_state.get("inquiry_card"),
                    },
                    "part_index": part_idx,
                })
                part_idx += 1

        # 3c. system_task 事件（从 pending_responses 中提取任务卡）
        if isinstance(pending_responses, list):
            for resp in pending_responses:
                if not isinstance(resp, dict):
                    continue

                # 普通 assistant 文本
                content = resp.get("content")
                resp_type = resp.get("type", "text")

                if resp_type == "system_task" or resp.get("taskType"):
                    # system_task 事件
                    messages_to_write.append({
                        "role": "assistant",
                        "kind": "system_task",
                        "content": content,
                        "metadata": {
                            k: v for k, v in resp.items()
                            if k not in ("content",)
                        },
                        "part_index": part_idx,
                    })
                    part_idx += 1
                elif content:
                    # 普通 assistant 文本
                    messages_to_write.append({
                        "role": "assistant",
                        "kind": "chat_text",
                        "content": content,
                        "part_index": part_idx,
                    })
                    part_idx += 1

        # 3d. interrupt 事件（inquiry_card）
        if inquiry_card:
            messages_to_write.append({
                "role": "assistant",
                "kind": "interrupt_inquiry",
                "content": None,
                "metadata": {
                    "inquiry_card": inquiry_card,
                },
                "part_index": part_idx,
            })
            part_idx += 1

        # 4. 批量写入
        if messages_to_write:
            count = await append_messages(
                conversation_id=conversation_id,
                thread_id=thread_id,
                turn_id=turn_id,
                turn_seq=turn_seq,
                messages=messages_to_write,
            )
            logger.info(
                "persist_turn_messages: wrote %d/%d messages for turn=%s conv=%s",
                count, len(messages_to_write), turn_id, conversation_id,
            )

    except Exception as e:
        logger.error("persist_turn_messages failed: %s", e, exc_info=True)


async def persist_stream_turn_messages(
    user_id: str,
    thread_id: str,
    turn_id: str,
    user_message: Optional[str],
    collected_chunks: List[Dict[str, Any]],
    final_state: Optional[Dict[str, Any]],
    is_resume: bool = False,
    inquiry_card: Optional[Dict[str, Any]] = None,
) -> None:
    """
    流式对话结束后的消息持久化。
    从 final_state 中提取 pending_responses 后委托给 persist_turn_messages。
    """
    if not user_id or not final_state:
        return

    pending_responses = final_state.get("pending_responses", []) if isinstance(final_state, dict) else []

    await persist_turn_messages(
        user_id=user_id,
        thread_id=thread_id,
        turn_id=turn_id,
        user_message=user_message,
        pending_responses=pending_responses,
        final_state=final_state,
        is_resume=is_resume,
        inquiry_card=inquiry_card,
    )
