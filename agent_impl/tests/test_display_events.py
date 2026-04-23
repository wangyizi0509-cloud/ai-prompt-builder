"""
display_events.py 单元测试

覆盖：SeqAllocator、get_tool_label、各 build_*_node 构造函数、DisplayNodeCollector。
纯逻辑测试，无需 mock LLM 或网络调用。
"""

import sys
sys.path.insert(0, ".")

from api.display_events import (
    SeqAllocator,
    get_tool_label,
    build_tool_call_node,
    build_report_card_node,
    build_reasoning_node,
    build_ai_intermediate_node,
    build_subgraph_thinking_node,
    build_inquiry_node,
    build_final_response_node,
    build_user_message_node,
    DisplayNodeCollector,
)


# ---------------------------------------------------------------------------
# 1. SeqAllocator 单调递增
# ---------------------------------------------------------------------------

def test_seq_allocator_monotonic():
    alloc = SeqAllocator(turn_seq=3)
    seqs = [alloc.next_seq() for _ in range(5)]
    for i in range(1, len(seqs)):
        assert seqs[i] > seqs[i - 1], f"seq 不单调递增: {seqs}"


def test_seq_allocator_base_offset():
    """turn_seq=3 → base=3000，首个 seq 应该是 3000。"""
    alloc = SeqAllocator(turn_seq=3)
    assert alloc.next_seq() == 3000
    assert alloc.next_seq() == 3001


def test_seq_allocator_current_count():
    alloc = SeqAllocator(turn_seq=0)
    assert alloc.current_count == 0
    alloc.next_seq()
    alloc.next_seq()
    assert alloc.current_count == 2


# ---------------------------------------------------------------------------
# 2. 工具中文名映射
# ---------------------------------------------------------------------------

def test_get_tool_label_known():
    assert get_tool_label("call_status_agent") == "分析感情现状"
    assert get_tool_label("call_plan_agent") == "制定行动策略"
    assert get_tool_label("load_skill") == "加载技能"


def test_get_tool_label_unknown():
    assert get_tool_label("nonexistent_tool") == "执行操作"
    assert get_tool_label("") == "执行操作"


# ---------------------------------------------------------------------------
# 3. tool_call nodeId 复用
# ---------------------------------------------------------------------------

def test_tool_call_node_same_tool_call_id_reuses_node_id():
    """同一 tool_call_id 构建的 loading 和 done 节点，nodeId 必须相同。"""
    loading = build_tool_call_node(
        seq=0, turn_id="t1", tool_name="call_status_agent",
        tool_call_id="tc_abc", status="loading",
    )
    done = build_tool_call_node(
        seq=1, turn_id="t1", tool_name="call_status_agent",
        tool_call_id="tc_abc", status="done",
    )
    assert loading["nodeId"] == done["nodeId"]
    assert loading["nodeId"] == "tool:tc_abc"


def test_tool_call_node_different_tool_call_id():
    """不同 tool_call_id 应生成不同 nodeId。"""
    a = build_tool_call_node(
        seq=0, turn_id="t1", tool_name="x", tool_call_id="id_1",
    )
    b = build_tool_call_node(
        seq=1, turn_id="t1", tool_name="x", tool_call_id="id_2",
    )
    assert a["nodeId"] != b["nodeId"]


def test_tool_call_node_no_tool_call_id_fallback():
    """未提供 tool_call_id 时，使用 tool_name + local_counter 作为 nodeId。"""
    node = build_tool_call_node(
        seq=0, turn_id="t1", tool_name="load_skill", local_counter=2,
    )
    assert node["nodeId"] == "tool:load_skill:2"


def test_tool_call_node_payload_contains_label():
    node = build_tool_call_node(
        seq=0, turn_id="t1", tool_name="call_plan_agent", tool_call_id="tc1",
    )
    assert node["payload"]["tool_label"] == "制定行动策略"


# ---------------------------------------------------------------------------
# 4. report_card loading → done nodeId 复用
# ---------------------------------------------------------------------------

def test_report_card_same_report_id_reuses_node_id():
    loading = build_report_card_node(
        seq=0, turn_id="t1", report_type="status",
        report_id="r1", status="loading",
    )
    done = build_report_card_node(
        seq=1, turn_id="t1", report_type="status",
        report_id="r1", status="done",
    )
    assert loading["nodeId"] == done["nodeId"]
    assert loading["nodeId"] == "report:status:r1"


def test_report_card_title_reflects_status():
    loading = build_report_card_node(
        seq=0, turn_id="t1", report_type="plan",
        report_id="r1", status="loading",
    )
    done = build_report_card_node(
        seq=1, turn_id="t1", report_type="plan",
        report_id="r1", status="done",
    )
    assert loading["payload"]["title"] == "正在制定行动策略..."
    assert done["payload"]["title"] == "行动策略已完成"


def test_report_card_panel_target():
    node = build_report_card_node(
        seq=0, turn_id="t1", report_type="guide", report_id="g1",
    )
    assert node["payload"]["panel_target"]["tab"] == "plan"
    assert node["payload"]["panel_target"]["planTab"] == "plan"


# ---------------------------------------------------------------------------
# 5. DisplayNodeCollector upsert
# ---------------------------------------------------------------------------

def test_collector_upsert_new_node_increases_length():
    c = DisplayNodeCollector()
    assert len(c) == 0
    c.upsert({"nodeId": "a", "seq": 1, "data": "x"})
    assert len(c) == 1
    c.upsert({"nodeId": "b", "seq": 2, "data": "y"})
    assert len(c) == 2


def test_collector_upsert_same_node_id_keeps_seq():
    """upsert 同 nodeId 节点时保留原始 seq，但更新其余字段。"""
    c = DisplayNodeCollector()
    c.upsert({"nodeId": "a", "seq": 10, "status": "loading"})
    c.upsert({"nodeId": "a", "seq": 99, "status": "done"})
    # 长度不变
    assert len(c) == 1
    node = c.get_node("a")
    # seq 保持首次的 10，status 更新为 done
    assert node["seq"] == 10
    assert node["status"] == "done"


def test_collector_get_ordered_nodes_insertion_order():
    c = DisplayNodeCollector()
    c.upsert({"nodeId": "c", "seq": 30})
    c.upsert({"nodeId": "a", "seq": 10})
    c.upsert({"nodeId": "b", "seq": 20})
    ordered = c.get_ordered_nodes()
    assert [n["nodeId"] for n in ordered] == ["c", "a", "b"]


def test_collector_get_node_returns_none_for_missing():
    c = DisplayNodeCollector()
    assert c.get_node("missing") is None


# ---------------------------------------------------------------------------
# 6. 各构造函数基本验证
# ---------------------------------------------------------------------------

def test_build_reasoning_node():
    node = build_reasoning_node(
        seq=0, turn_id="t1", part_index=0, content="thinking...",
    )
    assert node["nodeType"] == "reasoning"
    assert node["nodeId"] == "reasoning:t1:0"
    assert node["payload"]["content"] == "thinking..."


def test_build_ai_intermediate_node():
    node = build_ai_intermediate_node(
        seq=1, turn_id="t1", part_index=2, content="mid text",
    )
    assert node["nodeType"] == "ai_intermediate"
    assert node["nodeId"] == "ai:t1:2"
    assert node["payload"]["content"] == "mid text"


def test_build_subgraph_thinking_node():
    node = build_subgraph_thinking_node(
        seq=2, turn_id="t1", part_index=1, content="sub thought",
        source="status_agent",
    )
    assert node["nodeType"] == "subgraph_thinking"
    assert node["nodeId"] == "subgraph:status_agent:t1:1"
    assert node["source"] == "status_agent"


def test_build_inquiry_node():
    node = build_inquiry_node(
        seq=3, turn_id="t1", task_key="crush_name", status="new",
        payload={"question": "你 crush 叫什么?"},
    )
    assert node["nodeType"] == "inquiry_card"
    assert node["nodeId"] == "inquiry:crush_name"
    assert node["status"] == "new"
    assert node["payload"]["question"] == "你 crush 叫什么?"


def test_build_inquiry_node_default_task_key():
    node = build_inquiry_node(seq=0, turn_id="t1")
    assert node["nodeId"] == "inquiry:t1"


def test_build_final_response_node():
    node = build_final_response_node(
        seq=5, turn_id="t1", content="最终回复",
    )
    assert node["nodeType"] == "final_response"
    assert node["nodeId"] == "final:t1"
    assert node["payload"]["content"] == "最终回复"


def test_build_user_message_node():
    node = build_user_message_node(
        seq=0, turn_id="t1", content="用户消息",
    )
    assert node["nodeType"] == "user_message"
    assert node["nodeId"] == "user:t1"
    assert node["source"] == "user"
    assert node["payload"]["content"] == "用户消息"
