"""
对话消息持久化辅助模块

在 /api/chat 和 /api/chat/stream 完成后调用，
将本轮 user/assistant 消息、interrupt 事件、system_task 事件写入 Supabase。

采用后台任务方式写入，不阻塞主响应。失败仅记录日志。

display_nodes 持久化：每条写入的 message 在 metadata 中统一补齐
node_id / node_type / seq / status / source 等 DisplayNode 字段，
使前端历史恢复时可以用同一套 DisplayNode 模型渲染。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from api.display_events import (
    get_tool_label,
    REPORT_PANEL_TARGET,
    REPORT_DISPLAY_TITLES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# report_kind -> report_type 映射
# (复用 stream.py 中同一映射逻辑)
# ---------------------------------------------------------------------------
_REPORT_KIND_TO_TYPE: Dict[str, str] = {
    "status_report": "status",
    "action_plan": "plan",
    "action_guide": "guide",
}


# ---------------------------------------------------------------------------
# build_display_nodes_for_persistence
# ---------------------------------------------------------------------------

def build_display_nodes_for_persistence(
    *,
    display_nodes: List[Dict[str, Any]] | None = None,
    process_events: List[Dict[str, Any]] | None = None,
    pending_responses: List[Dict[str, Any]] | None = None,
    inquiry_card: Dict[str, Any] | None = None,
    inquiry_receipt_payload: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """
    生成用于持久化的最终 display_nodes 列表。

    优先使用 *display_nodes*（stream.py final 事件中已经汇聚好的最终态）。
    如果为空，则从 process_events + pending_responses 降级重建。

    返回值：按 seq 排好序、同 nodeId 去重（保留最新状态）的节点列表。
    """
    raw_nodes: List[Dict[str, Any]] = []

    if display_nodes:
        raw_nodes = list(display_nodes)
    else:
        # ---- 降级重建 ----
        raw_nodes = _rebuild_nodes_from_events(
            process_events=process_events or [],
            pending_responses=pending_responses or [],
            inquiry_card=inquiry_card,
            inquiry_receipt_payload=inquiry_receipt_payload,
        )

    # 去重：同一 nodeId 保留最后出现的状态，但保留首次出现时的 seq
    seen: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for node in raw_nodes:
        nid = node.get("nodeId", "")
        if not nid:
            # 没有 nodeId 的节点直接保留
            order.append(id(node))
            seen[id(node)] = node
            continue
        if nid in seen:
            old_seq = seen[nid].get("seq")
            seen[nid] = {**node, "seq": old_seq}
        else:
            seen[nid] = node
            order.append(nid)

    result = [seen[key] for key in order if key in seen]
    result.sort(key=lambda n: n.get("seq", 0))
    return result


def _rebuild_nodes_from_events(
    process_events: List[Dict[str, Any]],
    pending_responses: List[Dict[str, Any]],
    inquiry_card: Dict[str, Any] | None,
    inquiry_receipt_payload: Dict[str, Any] | None,
) -> List[Dict[str, Any]]:
    """
    从 process_events + pending_responses 降级重建 DisplayNode 列表。

    仅在 display_nodes 不可用时使用。
    """
    nodes: List[Dict[str, Any]] = []
    seq_counter = 0

    def _next_seq() -> int:
        nonlocal seq_counter
        s = seq_counter
        seq_counter += 1
        return s

    # 1) process_events
    for pe in process_events:
        if not isinstance(pe, dict):
            continue
        # 如果 process_event 已被 stream 层 enrich 过，直接取其展示字段
        if pe.get("node_id"):
            nodes.append({
                "seq": pe.get("seq", _next_seq()),
                "nodeId": pe.get("node_id", ""),
                "nodeType": pe.get("node_type", ""),
                "turnId": pe.get("turn_id", ""),
                "status": pe.get("status", "done"),
                "source": pe.get("source", "main_agent"),
                "payload": pe.get("payload", {}),
            })
        # 否则只提取 event_type 用于最低限度兼容
        elif pe.get("event_type"):
            node = {
                "seq": _next_seq(),
                "nodeId": f"fallback:{pe.get('event_type')}:{seq_counter}",
                "nodeType": pe["event_type"],
                "turnId": "",
                "status": pe.get("status", "done"),
                "source": pe.get("source", "main_agent"),
                "payload": {},
            }
            nodes.append(node)

    # 2) pending_responses -> final / subgraph_thinking
    for pr in pending_responses:
        if not isinstance(pr, dict):
            continue
        phase = pr.get("phase", "")
        content = pr.get("content", "")
        if phase == "final" and content:
            nodes.append({
                "seq": _next_seq(),
                "nodeId": f"final:fallback:{seq_counter}",
                "nodeType": "final_response",
                "turnId": "",
                "status": "done",
                "source": pr.get("source", "main_agent"),
                "payload": {"content": content},
            })
        elif phase == "subgraph_thinking" and content:
            source = pr.get("source", "subgraph")
            nodes.append({
                "seq": _next_seq(),
                "nodeId": f"subgraph:{source}:fallback:{seq_counter}",
                "nodeType": "subgraph_thinking",
                "turnId": "",
                "status": "done",
                "source": source,
                "payload": {"content": content},
            })

    # 3) inquiry_card
    if isinstance(inquiry_card, dict) and inquiry_card:
        nodes.append({
            "seq": _next_seq(),
            "nodeId": f"inquiry:{inquiry_card.get('task_key', 'fallback')}",
            "nodeType": "inquiry_card",
            "turnId": "",
            "status": "new",
            "source": "main_agent",
            "payload": inquiry_card,
        })

    return nodes


# ---------------------------------------------------------------------------
# _enrich_metadata: 将 DisplayNode 字段注入 message metadata
# ---------------------------------------------------------------------------

def _enrich_metadata(
    metadata: Dict[str, Any] | None,
    *,
    node_id: str = "",
    node_type: str = "",
    seq: int | None = None,
    status: str = "",
    source: str = "",
    tool_label: str = "",
    report_type: str = "",
    panel_target: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """
    在现有 metadata dict 上补齐 DisplayNode 统一字段。
    仅写入非空值，避免膨胀。
    """
    meta = dict(metadata) if metadata else {}
    if node_id:
        meta["node_id"] = node_id
    if node_type:
        meta["node_type"] = node_type
    if seq is not None:
        meta["seq"] = seq
    if status:
        meta["status"] = status
    if source:
        meta["source"] = source
    if tool_label:
        meta["tool_label"] = tool_label
    if report_type:
        meta["report_type"] = report_type
    if panel_target:
        meta["panel_target"] = panel_target
    return meta


def _find_display_node(
    display_nodes: List[Dict[str, Any]],
    node_type_hint: str,
    match_key: str = "",
    match_value: str = "",
) -> Dict[str, Any] | None:
    """
    在 display_nodes 列表中按 nodeType 和可选 payload 字段查找匹配节点。
    """
    for dn in display_nodes:
        if dn.get("nodeType") != node_type_hint:
            continue
        if match_key and match_value:
            payload = dn.get("payload") or {}
            if str(payload.get(match_key, "")) == match_value:
                return dn
            # 也检查顶层字段
            if str(dn.get(match_key, "")) == match_value:
                return dn
        else:
            return dn
    return None


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


def _normalize_visible_text_key(value: Any) -> str:
    """用于同轮可见文案去重的轻量文本归一化。"""
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.split()).strip()
    return normalized[:200]


async def persist_turn_messages(
    user_id: str,
    thread_id: str,
    turn_id: str,
    user_message: Optional[str],
    pending_responses: List[Dict[str, Any]],
    final_state: Dict[str, Any],
    is_resume: bool = False,
    inquiry_card: Optional[Dict[str, Any]] = None,
    inquiry_receipt_payload: Optional[Dict[str, Any]] = None,
    process_events: list | None = None,
    display_nodes: List[Dict[str, Any]] | None = None,
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
        display_nodes: stream.py final 事件中汇聚的 DisplayNode 列表
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

        # 2b. 构建最终 display_nodes 用于 metadata 关联
        final_display_nodes = build_display_nodes_for_persistence(
            display_nodes=display_nodes,
            process_events=process_events,
            pending_responses=pending_responses,
            inquiry_card=inquiry_card,
            inquiry_receipt_payload=inquiry_receipt_payload,
        )

        # 3. 收集需要写入的消息
        messages_to_write: List[Dict[str, Any]] = []
        part_idx = 0
        persisted_task_keys: set[str] = set()
        # 追踪 display_nodes 中已被关联的 nodeId，用于兜底
        _used_node_ids: set[str] = set()

        # 3a. 用户消息（非 resume 时写入）
        if user_message and not is_resume:
            _user_dn = _find_display_node(final_display_nodes, "user_message")
            _user_meta = _enrich_metadata(
                None,
                node_id=(_user_dn or {}).get("nodeId", f"user:{turn_id}"),
                node_type="user_message",
                seq=(_user_dn or {}).get("seq"),
                source="user",
            )
            if _user_dn:
                _used_node_ids.add(_user_dn["nodeId"])
            messages_to_write.append({
                "role": "user",
                "kind": "chat_text",
                "content": user_message,
                "metadata": _user_meta or None,
                "part_index": part_idx,
            })
            part_idx += 1

        # 3b. 用户提交问卷的回执
        # 对 resume 来说，inquiry_receipt 是本轮唯一稳定的用户消息，
        # 必须排在 reasoning/tool/report 之前，否则刷新恢复后会出现
        # assistant 过程事件先于用户问卷回执，造成卡片乱序。
        if isinstance(inquiry_receipt_payload, dict) and inquiry_receipt_payload:
            _receipt_dn = _find_display_node(final_display_nodes, "inquiry_receipt")
            _receipt_meta = _enrich_metadata(
                {
                    "summary": inquiry_receipt_payload.get("summary"),
                    "details": inquiry_receipt_payload.get("details"),
                    "taskKey": inquiry_receipt_payload.get("taskKey"),
                    "answers": final_state.get("inquiry_answers"),
                    "inquiry_card": final_state.get("inquiry_card"),
                },
                node_id=(_receipt_dn or {}).get("nodeId", f"inquiry_receipt:{turn_id}"),
                node_type="inquiry_receipt",
                seq=(_receipt_dn or {}).get("seq"),
                status="submitted",
                source="user",
            )
            if _receipt_dn:
                _used_node_ids.add(_receipt_dn["nodeId"])
            messages_to_write.append({
                "role": "user",
                "kind": "inquiry_receipt",
                "content": None,
                "metadata": _receipt_meta,
                "part_index": part_idx,
            })
            part_idx += 1
        elif is_resume:
            inquiry_answers = final_state.get("inquiry_answers")
            if inquiry_answers:
                _receipt_dn = _find_display_node(final_display_nodes, "inquiry_receipt")
                _receipt_meta = _enrich_metadata(
                    {
                        "answers": inquiry_answers,
                        "inquiry_card": final_state.get("inquiry_card"),
                    },
                    node_id=(_receipt_dn or {}).get("nodeId", f"inquiry_receipt:{turn_id}"),
                    node_type="inquiry_receipt",
                    seq=(_receipt_dn or {}).get("seq"),
                    status="submitted",
                    source="user",
                )
                if _receipt_dn:
                    _used_node_ids.add(_receipt_dn["nodeId"])
                messages_to_write.append({
                    "role": "user",
                    "kind": "inquiry_receipt",
                    "content": None,
                    "metadata": _receipt_meta,
                    "part_index": part_idx,
                })
                part_idx += 1

        pending_system_task_keys: set[str] = set()
        pending_visible_text_keys: set[str] = set()
        if isinstance(pending_responses, list):
            for resp in pending_responses:
                if not isinstance(resp, dict):
                    continue
                task_key = str(resp.get("taskKey") or "").strip()
                if (resp.get("type") == "system_task" or resp.get("taskType")) and task_key:
                    pending_system_task_keys.add(task_key)
                content_key = _normalize_visible_text_key(resp.get("content"))
                if content_key:
                    pending_visible_text_keys.add(content_key)

        # 3a_process. process_events（中间过程事件，紧跟 user 消息或 inquiry_receipt 之后）
        # 这里仅保留 reasoning/tool 等过程消息；真正的聊天区正式卡片与可见文案
        # 优先从 pending_responses 落库，避免 report_ready/ai_message 与最终消息双写。
        if isinstance(process_events, list):
            seen_tool_call_ids: set[str] = set()
            for pe in process_events:
                if not isinstance(pe, dict):
                    continue
                event_type = pe.get("event_type")

                if event_type == "ai_message":
                    content = pe.get("content", "").strip()
                    if content and _normalize_visible_text_key(content) not in pending_visible_text_keys:
                        # 查找对应 DisplayNode
                        _ai_dn = _find_display_node(final_display_nodes, "ai_intermediate")
                        _ai_meta = _enrich_metadata(
                            {"phase": pe.get("phase", "intermediate")},
                            node_id=pe.get("node_id") or (_ai_dn or {}).get("nodeId", ""),
                            node_type="ai_intermediate",
                            seq=pe.get("seq") or (_ai_dn or {}).get("seq"),
                            source=pe.get("source", "main_agent"),
                        )
                        if _ai_dn:
                            _used_node_ids.add(_ai_dn["nodeId"])
                        messages_to_write.append({
                            "role": "assistant",
                            "kind": "ai_intermediate",
                            "content": content,
                            "metadata": _ai_meta,
                            "part_index": part_idx,
                        })
                        part_idx += 1

                elif event_type == "subgraph_thinking":
                    # 新增：子图中间思考消息
                    content = pe.get("content", "").strip()
                    if content:
                        _sg_source = pe.get("source", "unknown_agent")
                        _sg_dn = _find_display_node(final_display_nodes, "subgraph_thinking")
                        _sg_meta = _enrich_metadata(
                            {"phase": "subgraph_thinking"},
                            node_id=pe.get("node_id") or (_sg_dn or {}).get("nodeId", ""),
                            node_type="subgraph_thinking",
                            seq=pe.get("seq") or (_sg_dn or {}).get("seq"),
                            source=_sg_source,
                        )
                        if _sg_dn:
                            _used_node_ids.add(_sg_dn["nodeId"])
                        messages_to_write.append({
                            "role": "assistant",
                            "kind": "subgraph_thinking",
                            "content": content,
                            "metadata": _sg_meta,
                            "part_index": part_idx,
                        })
                        part_idx += 1

                elif event_type == "tool_call" and pe.get("status") == "done":
                    # 只落库 done 状态（calling 是瞬态，不需要持久化）
                    tool_call_id = pe.get("tool_call_id", "")
                    tool_name = pe.get("tool_name", "")
                    if tool_call_id and tool_call_id not in seen_tool_call_ids:
                        seen_tool_call_ids.add(tool_call_id)
                        _tool_dn = _find_display_node(
                            final_display_nodes, "tool_call",
                            match_key="tool_call_id", match_value=tool_call_id,
                        )
                        _tool_meta = _enrich_metadata(
                            {
                                "tool_name": tool_name,
                                "tool_call_id": tool_call_id,
                                "result_summary": pe.get("result_summary", ""),
                            },
                            node_id=pe.get("node_id") or (_tool_dn or {}).get("nodeId", ""),
                            node_type="tool_call",
                            seq=pe.get("seq") or (_tool_dn or {}).get("seq"),
                            status="done",
                            source=pe.get("source", "main_agent"),
                            tool_label=get_tool_label(tool_name),
                        )
                        if _tool_dn:
                            _used_node_ids.add(_tool_dn["nodeId"])
                        messages_to_write.append({
                            "role": "assistant",
                            "kind": "tool_event",
                            "content": None,
                            "metadata": _tool_meta,
                            "part_index": part_idx,
                        })
                        part_idx += 1

                elif event_type == "reasoning":
                    content = pe.get("content", "").strip()
                    if content:
                        _r_dn = _find_display_node(final_display_nodes, "reasoning")
                        _r_meta = _enrich_metadata(
                            {},
                            node_id=pe.get("node_id") or (_r_dn or {}).get("nodeId", ""),
                            node_type="reasoning",
                            seq=pe.get("seq") or (_r_dn or {}).get("seq"),
                            source=pe.get("source", "main_agent"),
                        )
                        if _r_dn:
                            _used_node_ids.add(_r_dn["nodeId"])
                        messages_to_write.append({
                            "role": "assistant",
                            "kind": "reasoning_event",
                            "content": content,
                            "metadata": _r_meta,
                            "part_index": part_idx,
                        })
                        part_idx += 1

                elif event_type == "report_ready":
                    report_kind = str(pe.get("report_kind") or "").strip()
                    task_key = str(pe.get("task_key") or "").strip()
                    if task_key and task_key in pending_system_task_keys:
                        continue
                    report_type = _REPORT_KIND_TO_TYPE.get(report_kind, report_kind)
                    if report_kind == "status_report":
                        metadata = {
                            "taskType": "status",
                            "taskKey": task_key or None,
                            "taskState": "done",
                            "label": "STATUS REPORT",
                            "title": "现状分析报告已生成",
                            "desc": "点击查看最新的关系阶段与分析报告",
                        }
                    elif report_kind == "action_plan":
                        metadata = {
                            "taskType": "strategy",
                            "taskKey": task_key or None,
                            "taskState": "done",
                            "label": "PLANNING",
                            "title": "专属情感计划已生成",
                            "desc": "点击查看最新的情感计划",
                        }
                    elif report_kind == "action_guide":
                        metadata = {
                            "taskType": "plan",
                            "taskKey": task_key or None,
                            "taskState": "done",
                            "label": "ACTION GUIDE",
                            "title": "新的行动指南已生成",
                            "desc": pe.get("title") or "点击查看最新的行动指南",
                        }
                    else:
                        metadata = None

                    if metadata:
                        _rpt_dn = _find_display_node(
                            final_display_nodes, "report_card",
                            match_key="report_type", match_value=report_type,
                        )
                        metadata = _enrich_metadata(
                            metadata,
                            node_id=pe.get("node_id") or (_rpt_dn or {}).get("nodeId", ""),
                            node_type="report_card",
                            seq=pe.get("seq") or (_rpt_dn or {}).get("seq"),
                            status="done",
                            source=pe.get("source", "main_agent"),
                            report_type=report_type,
                            panel_target=REPORT_PANEL_TARGET.get(report_type),
                        )
                        if _rpt_dn:
                            _used_node_ids.add(_rpt_dn["nodeId"])
                        messages_to_write.append({
                            "role": "assistant",
                            "kind": "system_task",
                            "content": None,
                            "metadata": metadata,
                            "part_index": part_idx,
                        })
                        if task_key:
                            persisted_task_keys.add(task_key)
                        part_idx += 1

                elif event_type == "report_card":
                    # process_event 中的 report_card 类型（非 report_ready）
                    report_type = pe.get("report_type", "")
                    status_val = pe.get("status", "loading")
                    _rpt_dn = _find_display_node(
                        final_display_nodes, "report_card",
                        match_key="report_type", match_value=report_type,
                    )
                    _rpt_meta = _enrich_metadata(
                        {
                            "report_type": report_type,
                            "report_id": pe.get("report_id", ""),
                        },
                        node_id=pe.get("node_id") or (_rpt_dn or {}).get("nodeId", ""),
                        node_type="report_card",
                        seq=pe.get("seq") or (_rpt_dn or {}).get("seq"),
                        status=status_val,
                        source=pe.get("source", "main_agent"),
                        report_type=report_type,
                        panel_target=REPORT_PANEL_TARGET.get(report_type),
                    )
                    if _rpt_dn:
                        _used_node_ids.add(_rpt_dn["nodeId"])
                    messages_to_write.append({
                        "role": "assistant",
                        "kind": "system_task",
                        "content": None,
                        "metadata": _rpt_meta,
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
                resp_phase = resp.get("phase", "")

                if resp_type == "system_task" or resp.get("taskType"):
                    task_key = str(resp.get("taskKey") or "").strip()
                    if task_key and task_key in persisted_task_keys:
                        continue
                    # system_task 事件
                    _st_base_meta = {
                        k: v for k, v in resp.items()
                        if k not in ("content",)
                    }
                    _st_meta = _enrich_metadata(
                        _st_base_meta,
                        node_type="report_card",
                        status="done",
                        source=resp.get("source", "main_agent"),
                    )
                    messages_to_write.append({
                        "role": "assistant",
                        "kind": "system_task",
                        "content": content,
                        "metadata": _st_meta,
                        "part_index": part_idx,
                    })
                    part_idx += 1
                elif resp_phase == "subgraph_thinking" and content:
                    # subgraph_thinking 从 pending_responses
                    _sg_source = resp.get("source", "subgraph")
                    _sg_dn = _find_display_node(final_display_nodes, "subgraph_thinking")
                    _sg_meta = _enrich_metadata(
                        {"phase": "subgraph_thinking"},
                        node_id=(_sg_dn or {}).get("nodeId", ""),
                        node_type="subgraph_thinking",
                        seq=(_sg_dn or {}).get("seq"),
                        source=_sg_source,
                    )
                    if _sg_dn:
                        _used_node_ids.add(_sg_dn["nodeId"])
                    messages_to_write.append({
                        "role": "assistant",
                        "kind": "subgraph_thinking",
                        "content": content,
                        "metadata": _sg_meta,
                        "part_index": part_idx,
                    })
                    part_idx += 1
                elif resp_phase == "final" and content:
                    # final 回复
                    _final_dn = _find_display_node(final_display_nodes, "final_response")
                    _final_meta = _enrich_metadata(
                        {
                            k: v for k, v in resp.items()
                            if k not in ("content",) and v is not None
                        },
                        node_id=(_final_dn or {}).get("nodeId", f"final:{turn_id}"),
                        node_type="final_response",
                        seq=(_final_dn or {}).get("seq"),
                        status="done",
                        source=resp.get("source", "main_agent"),
                    )
                    if _final_dn:
                        _used_node_ids.add(_final_dn["nodeId"])
                    messages_to_write.append({
                        "role": "assistant",
                        "kind": "chat_text",
                        "content": content,
                        "metadata": _final_meta,
                        "part_index": part_idx,
                    })
                    part_idx += 1
                elif content:
                    metadata = {
                        k: v for k, v in resp.items()
                        if k not in ("content",) and v is not None
                    }
                    # 普通 assistant 文本 -- 尽量关联 display 信息
                    _generic_meta = _enrich_metadata(
                        metadata,
                        node_type="ai_intermediate" if resp_phase != "final" else "final_response",
                        source=resp.get("source", "main_agent"),
                    )
                    messages_to_write.append({
                        "role": "assistant",
                        "kind": "chat_text",
                        "content": content,
                        "metadata": _generic_meta or None,
                        "part_index": part_idx,
                    })
                    part_idx += 1

        pa = final_state.get("preliminary_assessment")
        pa_updated = False
        if isinstance(pending_responses, list) and any(isinstance(r, dict) and r.get("preliminary_assessment") for r in pending_responses):
            pa_updated = True
        tool_patch_log = final_state.get("tool_patch_log")
        if not pa_updated and isinstance(tool_patch_log, list) and tool_patch_log:
            latest_patch = tool_patch_log[-1]
            if isinstance(latest_patch, dict) and "preliminary_assessment" in latest_patch:
                pa_updated = True
        if pa_updated and isinstance(pa, dict) and pa:
            messages_to_write.append({
                "role": "assistant",
                "kind": "preliminary_assessment",
                "content": None,
                "metadata": {
                    "preliminary_assessment": pa,
                },
                "part_index": part_idx,
            })
            part_idx += 1

        # 3d. interrupt 事件（inquiry_card）
        if inquiry_card:
            _inq_dn = _find_display_node(final_display_nodes, "inquiry_card")
            _inq_meta = _enrich_metadata(
                {"inquiry_card": inquiry_card},
                node_id=(_inq_dn or {}).get("nodeId", f"inquiry:{inquiry_card.get('task_key', turn_id)}"),
                node_type="inquiry_card",
                seq=(_inq_dn or {}).get("seq"),
                status="new",
                source="main_agent",
            )
            if _inq_dn:
                _used_node_ids.add(_inq_dn["nodeId"])
            messages_to_write.append({
                "role": "assistant",
                "kind": "interrupt_inquiry",
                "content": None,
                "metadata": _inq_meta,
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
    inquiry_receipt_payload: Optional[Dict[str, Any]] = None,
    process_events: list | None = None,
    display_nodes: List[Dict[str, Any]] | None = None,
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
        inquiry_receipt_payload=inquiry_receipt_payload,
        process_events=process_events,
        display_nodes=display_nodes,
    )


# ---------------------------------------------------------------------------
# 历史恢复：为从数据库读取的消息补充 DisplayNode 展示字段
# ---------------------------------------------------------------------------

# kind -> nodeType 映射，用于历史恢复时的兼容推断
_KIND_TO_NODE_TYPE: Dict[str, str] = {
    "chat_text": "final_response",
    "ai_intermediate": "ai_intermediate",
    "subgraph_thinking": "subgraph_thinking",
    "reasoning_event": "reasoning",
    "tool_event": "tool_call",
    "system_task": "report_card",
    "interrupt_inquiry": "inquiry_card",
    "inquiry_receipt": "inquiry_receipt",
    "preliminary_assessment": "ai_intermediate",
}


def enrich_history_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    为从数据库读取的历史消息补充 DisplayNode 展示字段。

    如果 metadata 中已有 node_id / node_type / seq 等字段（由新版持久化写入），
    直接提升到消息顶层；否则从 kind / role / seq 等字段推断。

    这样前端可以用同一套 DisplayNode 模型渲染历史消息和实时消息。

    注意：此函数就地修改并返回输入列表。
    """
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        meta = msg.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        kind = msg.get("kind", "chat_text")
        role = msg.get("role", "assistant")

        # node_type: 优先从 metadata 读取，否则从 kind 推断
        if "node_type" not in msg:
            msg["node_type"] = meta.get("node_type") or _KIND_TO_NODE_TYPE.get(kind, "")
            # 特殊处理：role=user 的 chat_text 是 user_message
            if kind == "chat_text" and role == "user":
                msg["node_type"] = "user_message"

        # node_id: 优先 metadata，否则构造一个稳定 ID
        if "node_id" not in msg:
            msg["node_id"] = meta.get("node_id") or _infer_node_id(msg)

        # seq: 优先 metadata 中的 DisplayNode seq，否则保留数据库 seq
        if "display_seq" not in msg:
            msg["display_seq"] = meta.get("seq") if meta.get("seq") is not None else msg.get("seq")

        # status
        if "display_status" not in msg:
            msg["display_status"] = meta.get("status") or _infer_status(msg)

        # source
        if "display_source" not in msg:
            msg["display_source"] = meta.get("source") or ("user" if role == "user" else "main_agent")

        # tool_label (仅 tool_call)
        if msg["node_type"] == "tool_call" and "tool_label" not in msg:
            tool_name = meta.get("tool_name", "")
            msg["tool_label"] = meta.get("tool_label") or (get_tool_label(tool_name) if tool_name else "")

        # report_type / panel_target (仅 report_card)
        if msg["node_type"] == "report_card":
            if "report_type" not in msg:
                msg["report_type"] = meta.get("report_type", "")
            if "panel_target" not in msg:
                rt = msg["report_type"]
                msg["panel_target"] = meta.get("panel_target") or REPORT_PANEL_TARGET.get(rt)

    return messages


def _infer_node_id(msg: Dict[str, Any]) -> str:
    """从消息的 kind / turn_id / part_index 推断一个稳定的 node_id。"""
    kind = msg.get("kind", "chat_text")
    turn_id = msg.get("turn_id", "unknown")
    part_index = msg.get("part_index", 0)
    role = msg.get("role", "assistant")
    meta = msg.get("metadata") or {}

    if kind == "chat_text" and role == "user":
        return f"user:{turn_id}"
    if kind == "chat_text":
        return f"final:{turn_id}:{part_index}"
    if kind == "tool_event":
        tcid = meta.get("tool_call_id", "")
        return f"tool:{tcid}" if tcid else f"tool:{turn_id}:{part_index}"
    if kind == "reasoning_event":
        return f"reasoning:{turn_id}:{part_index}"
    if kind == "ai_intermediate":
        return f"ai:{turn_id}:{part_index}"
    if kind == "subgraph_thinking":
        source = meta.get("source", "unknown")
        return f"subgraph:{source}:{turn_id}:{part_index}"
    if kind == "system_task":
        task_key = meta.get("taskKey", "")
        return f"report:{task_key or turn_id}:{part_index}"
    if kind == "interrupt_inquiry":
        task_key = ""
        inq = meta.get("inquiry_card")
        if isinstance(inq, dict):
            task_key = inq.get("task_key", "")
        return f"inquiry:{task_key or turn_id}"
    if kind == "inquiry_receipt":
        return f"inquiry_receipt:{turn_id}:{part_index}"
    return f"{kind}:{turn_id}:{part_index}"


def _infer_status(msg: Dict[str, Any]) -> str:
    """根据 kind 推断默认 status。"""
    kind = msg.get("kind", "")
    if kind == "interrupt_inquiry":
        return "new"
    if kind == "inquiry_receipt":
        return "submitted"
    return "done"
