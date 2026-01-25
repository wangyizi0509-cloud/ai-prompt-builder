"""
上下文规格验证测试
对齐 02_Specs 的输出格式与提取逻辑
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import pytest

from graph.context_builder import (
    build_context,
    build_context_dict,
    extract_layer1,
    extract_layer2,
    extract_layer3,
)
from graph.context_types import (
    create_empty_layer1_memory,
    create_empty_layer2_memory,
    create_empty_layer3_memory,
    create_reasoning_note,
)
from graph.state import create_initial_state
from tests.conftest import run_workflow_turn


def _atomic(
    *,
    mem_id: str,
    content: str,
    created_at: str,
    source_type: str,
    confidence: float | None = None,
    confidence_reason: str | None = None,
) -> dict:
    item: dict = {
        "id": mem_id,
        "content": content,
        "created_at": created_at,
        "source_type": source_type,
    }
    if confidence is not None:
        item["confidence"] = confidence
    if confidence_reason:
        item["confidence_reason"] = confidence_reason
    return item


def create_test_layer1_memory() -> dict:
    layer1 = create_empty_layer1_memory()
    layer1["full_data"] = {
        "user_info": {
            "user_provide": [
                _atomic(
                    mem_id="u1",
                    content="姓名：小明",
                    created_at="2026-01-10T10",
                    source_type="onboarding",
                ),
            ],
            "fact": [
                _atomic(
                    mem_id="u2",
                    content="朋友圈发了健身照",
                    created_at="2026-01-12T14",
                    source_type="conversation",
                ),
            ],
            "ai_provide": [
                _atomic(
                    mem_id="u3",
                    content="依恋类型：焦虑型",
                    created_at="2026-01-12T09",
                    source_type="report",
                    confidence=0.85,
                    confidence_reason="基于追问行为推断",
                ),
            ],
        },
        "crush_info": {
            "crush_name": "小红",
            "user_provide": [
                _atomic(
                    mem_id="c1",
                    content="年龄：25",
                    created_at="2026-01-10T10",
                    source_type="onboarding",
                )
            ],
            "fact": [
                _atomic(
                    mem_id="c2",
                    content="说周末要加班",
                    created_at="2026-01-12T15",
                    source_type="conversation",
                )
            ],
            "ai_provide": [
                _atomic(
                    mem_id="c3",
                    content="沟通风格：直接型",
                    created_at="2026-01-12T09",
                    source_type="report",
                    confidence=0.8,
                    confidence_reason="基于聊天记录分析",
                )
            ],
        },
        "both_info": {
            "user_provide": [
                _atomic(
                    mem_id="b1",
                    content="认识方式：朋友介绍",
                    created_at="2026-01-10T10",
                    source_type="onboarding",
                )
            ],
            "fact": [
                _atomic(
                    mem_id="b2",
                    content="上周一起吃了晚饭",
                    created_at="2026-01-12T20",
                    source_type="conversation",
                )
            ],
            "ai_provide": [
                _atomic(
                    mem_id="b3",
                    content="关系阶段：暧昧期",
                    created_at="2026-01-12T09",
                    source_type="report",
                    confidence=0.9,
                    confidence_reason="基于互动频率判断",
                )
            ],
        },
    }
    return layer1


def create_test_layer2_memory() -> dict:
    layer2 = create_empty_layer2_memory()
    now = datetime.now()
    future = (now + timedelta(days=7)).strftime("%Y-%m-%dT%H")
    expired = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H")

    layer2["dynamic_intels"] = [
        {
            "id": "di1",
            "content": "下周三要去上海见 Crush",
            "created_at": now.strftime("%Y-%m-%dT%H"),
            "expire_at": future,
            "subject": "user",
            "category": "日程",
            "confidence": 0.95,
            "confidence_reason": "用户明确表述",
            "source_type": "conversation",
        },
        {
            "id": "di2",
            "content": "Crush 最近工作压力大，心情不太好",
            "created_at": now.strftime("%Y-%m-%dT%H"),
            "expire_at": future,
            "subject": "crush",
            "category": "情绪状态",
            "confidence": 0.7,
            "confidence_reason": "用户转述",
            "source_type": "conversation",
        },
        {
            "id": "di3",
            "content": "已过期的旧情报",
            "created_at": now.strftime("%Y-%m-%dT%H"),
            "expire_at": expired,
            "subject": "user",
            "category": "状态",
            "confidence": 0.6,
            "confidence_reason": "过期测试",
            "source_type": "conversation",
        },
    ]

    layer2["current_status_report"] = {
        "report_id": "sr1",
        "report_content": "当前关系处于好感期初期，需要稳步推进。",
        "created_at": now.strftime("%Y-%m-%dT%H"),
        "version": 3,
    }
    layer2["current_action_plan"] = {
        "plan_id": "ap1",
        "plan_content": "本周目标：建立稳定聊天节奏，周末尝试邀约。",
        "created_at": now.strftime("%Y-%m-%dT%H"),
        "version": 2,
    }
    layer2["action_guides"] = [
        {
            "id": "g1",
            "title": "破冰话题准备",
            "status": "in_progress",
            "guide": {"guide_content": "准备3个轻松话题，避免压力型问题。"},
            "created_at": now.strftime("%Y-%m-%dT%H"),
            "expire_at": future,
        },
        {
            "id": "g2",
            "title": "深度话题储备",
            "status": "paused",
            "summary": "准备了3个深度话题，暂时用不上。",
            "created_at": now.strftime("%Y-%m-%dT%H"),
        },
        {
            "id": "g3",
            "title": "周末邀约",
            "status": "pending",
            "summary": "周四发出邀约，周末一起看电影。",
            "expected_start_at": now.strftime("%Y-%m-%dT%H"),
            "created_at": now.strftime("%Y-%m-%dT%H"),
        },
        {
            "id": "g4",
            "title": "首次破冰对话",
            "status": "completed",
            "summary": "用户发送破冰消息，Crush 回复积极。",
            "user_feedback": "她回复了，说周末有空。",
            "completed_at": now.strftime("%Y-%m-%dT%H"),
            "created_at": now.strftime("%Y-%m-%dT%H"),
        },
        {
            "id": "g5",
            "title": "送礼物计划",
            "status": "cancelled",
            "one_liner": "时机不成熟，暂缓。",
            "created_at": now.strftime("%Y-%m-%dT%H"),
        },
        {
            "id": "g6",
            "title": "节日祝福",
            "status": "expired",
            "one_liner": "错过时机。",
            "expire_at": expired,
            "created_at": now.strftime("%Y-%m-%dT%H"),
        },
    ]
    layer2["status_report_history"] = [
        {
            "report_id": "sr0",
            "summary": "关系处于好感期初期，互动频率稳定但缺乏深度话题。",
            "one_liner": "处于好感期初期",
            "created_at": (now - timedelta(days=2)).strftime("%Y-%m-%dT%H"),
        }
    ]
    return layer2


def create_test_layer3_memory() -> dict:
    layer3 = create_empty_layer3_memory()
    layer3["conversation_summaries"] = [
        {
            "id": "cs1",
            "summary": "用户约饭被拒绝，军师建议降低压力。",
            "topics": "约会,冷淡,回避型",
            "created_at": "2026-01-13T16",
            "turn_range": "1-25",
        }
    ]
    layer3["task_registry"] = {
        "main_agent": [
            {
                "task_id": "task_1",
                "title": "判断crush态度",
                "summary": "判断 crush 是否喜欢用户",
                "status": "active",
                "reasoning_notes": [
                    create_reasoning_note("决定采用降低压力策略", "task_1"),
                    create_reasoning_note("排除了第三者可能性", "task_1"),
                ],
                "bound_contexts": [],
                "started_at": datetime.now().isoformat(),
            }
        ]
    }
    return layer3


def create_test_messages() -> list[dict]:
    base_time = datetime(2026, 1, 15, 14, 30, 0)
    msg1 = {
        "role": "user",
        "content": "她今天没回我消息",
        "created_at": base_time.isoformat(),
    }
    ai_payload = {
        "response": "我理解你的焦虑，不过一天没回消息不一定代表什么。",
        "inquiry_card": {
            "questions": [
                {"question": "你们最近一次见面是什么时候？"},
                {"question": "见面时她态度怎么样？"},
            ]
        },
    }
    msg2 = {
        "role": "assistant",
        "content": json.dumps(ai_payload, ensure_ascii=False),
        "created_at": (base_time + timedelta(minutes=1)).isoformat(),
    }
    msg3 = {
        "role": "assistant",
        "content": "现状报告已更新",
        "created_at": (base_time + timedelta(minutes=2)).isoformat(),
    }
    return [msg1, msg2, msg3]


def print_full_context(context_dict: dict) -> None:
    print("\n====== Context Dict ======")
    for key, value in context_dict.items():
        print(f"\n[{key}]\n{value}\n")


class TestLayer1Format:
    def test_layer1_output_format(self):
        state = {"layer1_memory": create_test_layer1_memory()}
        output = extract_layer1(state)

        assert "## 情报概览" in output
        assert "事实 > AI分析 > 用户提供" in output

        pattern = r"\[(\d{2}-\d{2} \d{2}:\d{2})/(事实|AI|用户)\]"
        matches = re.findall(pattern, output)
        assert len(matches) >= 3

        assert "### 用户" in output
        assert "### Crush（小红）" in output
        assert "### 双方关系" in output


class TestLayer2Format:
    def test_layer2_dynamic_intel_format(self):
        state = {"layer2_memory": create_test_layer2_memory()}
        output = extract_layer2(state)

        assert "## 动态情报板" in output
        assert "### 用户" in output
        assert "### Crush" in output

        assert "已过期的旧情报" not in output
        assert "(置信度: 0.95 - 用户明确表述)" in output

    def test_layer2_report_plan_format(self):
        state = {"layer2_memory": create_test_layer2_memory()}
        output = extract_layer2(state)

        assert "## 现状分析" in output
        assert "### 当前报告" in output
        assert "\"\"\"" in output
        assert "## 行动规划" in output
        assert "### 当前规划" in output

    def test_layer2_action_guides_format(self):
        state = {"layer2_memory": create_test_layer2_memory()}
        output = extract_layer2(state)

        assert "## 行动指南" in output
        assert "🔥 当前进行中" in output
        assert "📋 其他指南" in output
        assert "首次破冰对话" in output

    def test_layer2_history_summaries_format(self):
        state = {"layer2_memory": create_test_layer2_memory()}
        output = extract_layer2(state)
        assert "## 历史摘要" in output
        assert "### 近期报告" in output


class TestLayer3Format:
    def test_layer3_history_and_notes_format(self):
        state = {
            "messages": create_test_messages(),
            "layer3_memory": create_test_layer3_memory(),
            "current_agent": "main_agent",
        }
        output = extract_layer3(state)

        assert "## 历史摘要" in output
        assert "## 任务笔记" in output
        assert "## 对话" in output

        assert "[01-15 14:30]" in output
        assert "[01-15 14:31]" in output
        assert "[01-15 14:32]" in output

    def test_layer3_assistant_message_slimming(self):
        state = {
            "messages": create_test_messages(),
            "layer3_memory": create_test_layer3_memory(),
            "current_agent": "main_agent",
        }
        output = extract_layer3(state)
        assert "我理解你的焦虑" in output
        assert "【提问】" in output
        assert "Q1:" in output


class TestAssemblyOrder:
    def test_context_assembly_order_and_boundaries(self):
        state = create_initial_state("测试上下文")
        state["onboarding_completed"] = True
        state["layer1_memory"] = create_test_layer1_memory()
        state["layer2_memory"] = create_test_layer2_memory()
        state["layer3_memory"] = create_test_layer3_memory()
        state["messages"] = create_test_messages()

        text = build_context(state, include_layer0=True)

        # 基本顺序校验
        idx_l0 = text.find("信任优先级说明")
        idx_l1 = text.find("## 情报概览")
        idx_l2 = text.find("## 现状分析")
        idx_l3 = text.find("## 对话")
        assert idx_l0 != -1 and idx_l1 != -1 and idx_l2 != -1 and idx_l3 != -1
        assert idx_l0 < idx_l1 < idx_l2 < idx_l3

        # 边界符号存在
        assert "##" in text
        assert "###" in text
        assert "---" in text
        assert "\"\"\"" in text


class TestE2EContextAssembly:
    @pytest.mark.api_test
    def test_e2e_context_assembly(self, workflow):
        state = create_initial_state("我叫小明，25岁，喜欢一个叫小红的女生")
        state["onboarding_completed"] = True

        # 多轮对话，主动回答 Agent 提问
        state = workflow.invoke(state)
        state = run_workflow_turn(workflow, state, "我们认识三个月，最近聊天频率还行，她会主动找我。")
        state = run_workflow_turn(workflow, state, "上周一起看了电影，她反馈挺开心。")
        state = run_workflow_turn(workflow, state, "我想知道现在是什么阶段，下一步怎么推进。")

        # 注入测试数据（用于格式验证）
        state["layer1_memory"] = create_test_layer1_memory()
        state["layer2_memory"] = create_test_layer2_memory()
        state["layer3_memory"] = create_test_layer3_memory()

        context_dict = build_context_dict(state)

        assert "user_context" in context_dict
        assert "status_report" in context_dict
        assert "conversation_history" in context_dict

        print_full_context(context_dict)
