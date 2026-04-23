"""
统一展示节点模型 (DisplayNode)

所有前端聊天区展示内容——无论来自实时流、最终态、还是历史恢复——
都必须先转换成 DisplayNode，再进入渲染、排序和持久化链路。

参考文档: agent_impl/docs/frontend_display_recommended_solution.md §五
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Literal, Optional

# ---------------------------------------------------------------------------
# 1. 类型常量
# ---------------------------------------------------------------------------

NodeType = Literal[
    "user_message",
    "reasoning",
    "subgraph_thinking",
    "tool_call",
    "report_card",
    "inquiry_card",
    "inquiry_receipt",
    "ai_intermediate",
    "final_response",
]

NodeStatus = Literal["loading", "done", "error", "new", "submitted"]

# ---------------------------------------------------------------------------
# 2. 工具中文映射
# ---------------------------------------------------------------------------

_TOOL_LABEL_MAP: Dict[str, str] = {
    "call_status_agent": "分析感情现状",
    "call_plan_agent": "制定行动策略",
    "call_guide_agent": "生成行动指南",
    "load_skill": "加载技能",
    "ask_human": "向你提问",
    "task_manager": "管理任务",
    "context_loader": "加载上下文",
    "submit_status_report": "提交现状分析",
    "submit_action_plan": "提交行动策略",
    "submit_action_guide": "提交行动指南",
    "update_guide_status": "更新指南状态",
    "update_guide_content": "更新指南内容",
    "return_to_main": "返回主流程",
}

_FALLBACK_TOOL_LABEL = "执行操作"


def get_tool_label(tool_name: str) -> str:
    """返回工具的中文展示名，未匹配则返回兜底文案。"""
    return _TOOL_LABEL_MAP.get(tool_name, _FALLBACK_TOOL_LABEL)


# ---------------------------------------------------------------------------
# 3. 报告类型 → 面板跳转映射
# ---------------------------------------------------------------------------

REPORT_PANEL_TARGET: Dict[str, Dict[str, str]] = {
    "status": {"tab": "plan", "planTab": "status", "anchor": ""},
    "plan": {"tab": "plan", "planTab": "status", "anchor": "#plan-analysis"},
    "guide": {"tab": "plan", "planTab": "plan", "anchor": ""},
}

REPORT_DISPLAY_TITLES: Dict[str, Dict[str, str]] = {
    "status": {"loading": "正在生成现状分析...", "done": "现状分析已完成"},
    "plan": {"loading": "正在制定行动策略...", "done": "行动策略已完成"},
    "guide": {"loading": "正在生成行动指南...", "done": "行动指南已生成"},
}


# ---------------------------------------------------------------------------
# 4. Seq 分配器 (线程安全，每轮一个实例)
# ---------------------------------------------------------------------------

class SeqAllocator:
    """
    为一轮对话生成单调递增的 seq。

    seq = turn_seq * 1000 + part_index
    part_index 从 0 开始自增。
    """

    def __init__(self, turn_seq: int):
        self._base = turn_seq * 1000
        self._counter = 0
        self._lock = threading.Lock()

    def next_seq(self) -> int:
        with self._lock:
            seq = self._base + self._counter
            self._counter += 1
            return seq

    @property
    def current_count(self) -> int:
        return self._counter


# ---------------------------------------------------------------------------
# 5. DisplayNode 构造函数
# ---------------------------------------------------------------------------

def _make_node(
    *,
    seq: int,
    turn_id: str,
    node_id: str,
    node_type: NodeType,
    status: Optional[NodeStatus] = None,
    source: str = "main_agent",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造一个 DisplayNode dict。"""
    node: Dict[str, Any] = {
        "seq": seq,
        "turnId": turn_id,
        "nodeId": node_id,
        "nodeType": node_type,
        "source": source,
        "payload": payload or {},
    }
    if status is not None:
        node["status"] = status
    return node


def build_reasoning_node(
    *,
    seq: int,
    turn_id: str,
    part_index: int,
    content: str,
    source: str = "main_agent",
) -> Dict[str, Any]:
    return _make_node(
        seq=seq,
        turn_id=turn_id,
        node_id=f"reasoning:{turn_id}:{part_index}",
        node_type="reasoning",
        source=source,
        payload={"content": content},
    )


def build_ai_intermediate_node(
    *,
    seq: int,
    turn_id: str,
    part_index: int,
    content: str,
    source: str = "main_agent",
) -> Dict[str, Any]:
    return _make_node(
        seq=seq,
        turn_id=turn_id,
        node_id=f"ai:{turn_id}:{part_index}",
        node_type="ai_intermediate",
        source=source,
        payload={"content": content},
    )


def build_tool_call_node(
    *,
    seq: int,
    turn_id: str,
    tool_name: str,
    tool_call_id: str = "",
    status: NodeStatus = "loading",
    args_preview: str = "",
    result_summary: str = "",
    local_counter: int = 0,
) -> Dict[str, Any]:
    nid = (
        f"tool:{tool_call_id}"
        if tool_call_id
        else f"tool:{tool_name}:{local_counter}"
    )
    return _make_node(
        seq=seq,
        turn_id=turn_id,
        node_id=nid,
        node_type="tool_call",
        status=status,
        payload={
            "tool_name": tool_name,
            "tool_label": get_tool_label(tool_name),
            "tool_call_id": tool_call_id,
            "args_preview": args_preview,
            "result_summary": result_summary,
        },
    )


def build_report_card_node(
    *,
    seq: int,
    turn_id: str,
    report_type: str,
    report_id: str = "",
    status: NodeStatus = "loading",
    tool_call_id: str = "",
) -> Dict[str, Any]:
    nid = f"report:{report_type}:{report_id or tool_call_id or turn_id}"
    titles = REPORT_DISPLAY_TITLES.get(report_type, {"loading": "正在生成报告...", "done": "报告已完成"})
    panel = REPORT_PANEL_TARGET.get(report_type, {"tab": "plan", "planTab": "status", "anchor": ""})
    return _make_node(
        seq=seq,
        turn_id=turn_id,
        node_id=nid,
        node_type="report_card",
        status=status,
        payload={
            "report_type": report_type,
            "report_id": report_id,
            "panel_target": panel,
            "title": titles.get(status, titles.get("loading", "")),
        },
    )


def build_subgraph_thinking_node(
    *,
    seq: int,
    turn_id: str,
    part_index: int,
    content: str,
    source: str,
) -> Dict[str, Any]:
    return _make_node(
        seq=seq,
        turn_id=turn_id,
        node_id=f"subgraph:{source}:{turn_id}:{part_index}",
        node_type="subgraph_thinking",
        source=source,
        payload={"content": content},
    )


def build_inquiry_node(
    *,
    seq: int,
    turn_id: str,
    task_key: str = "",
    status: NodeStatus = "new",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    nid = f"inquiry:{task_key or turn_id}"
    return _make_node(
        seq=seq,
        turn_id=turn_id,
        node_id=nid,
        node_type="inquiry_card",
        status=status,
        payload=payload or {},
    )


def build_inquiry_receipt_node(
    *,
    seq: int,
    turn_id: str,
    task_key: str = "",
    answers: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    nid = f"inquiry_receipt:{task_key or turn_id}"
    return _make_node(
        seq=seq,
        turn_id=turn_id,
        node_id=nid,
        node_type="inquiry_receipt",
        status="submitted",
        payload={"answers": answers or {}},
    )


def build_final_response_node(
    *,
    seq: int,
    turn_id: str,
    content: str,
    source: str = "main_agent",
) -> Dict[str, Any]:
    return _make_node(
        seq=seq,
        turn_id=turn_id,
        node_id=f"final:{turn_id}",
        node_type="final_response",
        source=source,
        payload={"content": content},
    )


def build_user_message_node(
    *,
    seq: int,
    turn_id: str,
    content: str,
) -> Dict[str, Any]:
    return _make_node(
        seq=seq,
        turn_id=turn_id,
        node_id=f"user:{turn_id}",
        node_type="user_message",
        source="user",
        payload={"content": content},
    )


# ---------------------------------------------------------------------------
# 6. DisplayNode 列表管理 (用于 stream 层汇聚当轮所有节点)
# ---------------------------------------------------------------------------

class DisplayNodeCollector:
    """
    收集一轮对话中产生的所有 DisplayNode。

    支持 upsert 语义：同一 nodeId 的节点只保留最新状态，
    但保持首次出现时的 seq（位置不变）。
    """

    def __init__(self):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []

    def upsert(self, node: Dict[str, Any]) -> None:
        nid = node["nodeId"]
        if nid in self._nodes:
            old_seq = self._nodes[nid]["seq"]
            self._nodes[nid] = {**node, "seq": old_seq}
        else:
            self._nodes[nid] = node
            self._order.append(nid)

    def get_ordered_nodes(self) -> List[Dict[str, Any]]:
        return [self._nodes[nid] for nid in self._order if nid in self._nodes]

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self._nodes.get(node_id)

    def __len__(self) -> int:
        return len(self._order)
