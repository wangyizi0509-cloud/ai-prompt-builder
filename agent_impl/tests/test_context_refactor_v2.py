"""
上下文工程重构 v2 测试
"""

import re
from datetime import datetime, timedelta

from graph.context_types import (
    create_atomic_memory,
    create_empty_layer1_memory,
    create_empty_layer2_memory,
    create_new_task,
    create_bound_context,
)
from graph.context_builder import extract_layer1, extract_layer2, extract_layer3
from graph.tools.task_tools import append_task_note_impl, complete_task_impl, format_task_index
from graph.tools.context_loader import create_context_loader
from graph.layer1_writer import save_atomic_memory


def _base_state():
    return {
        "messages": [],
        "layer1_memory": {},
        "layer2_memory": create_empty_layer2_memory(),
        "layer3_memory": {"task_registry": {"main_agent": []}},
    }


class TestAtomicMemoryTypes:
    def test_create_atomic_memory(self):
        mem = create_atomic_memory("职业：程序员", "onboarding", created_at="2026-01-10T10")
        assert mem["content"] == "职业：程序员"
        assert mem["created_at"] == "2026-01-10T10"
        assert mem["source_type"] == "onboarding"
        assert "id" in mem

    def test_info_source_v2_structure(self):
        layer1 = create_empty_layer1_memory()
        user_info = layer1["full_data"]["user_info"]
        assert isinstance(user_info["user_provide"], list)
        assert isinstance(user_info["fact"], list)
        assert isinstance(user_info["ai_provide"], list)

    def test_layer1_memory_v2_factory(self):
        layer1 = create_empty_layer1_memory()
        assert layer1["version"] == 1
        assert layer1["extraction_config"]["mode"] == "full"


class TestLayer1OutputFormat:
    def test_v2_compact_output(self):
        layer1 = create_empty_layer1_memory()
        layer1["full_data"]["user_info"]["user_provide"].append(
            create_atomic_memory("姓名：小明", "onboarding", created_at="2026-01-10T10")
        )
        state = _base_state()
        state["layer1_memory"] = layer1
        text = extract_layer1(state)
        assert "## 情报概览" in text
        assert "- [01-10 10:00/用户] 姓名：小明" in text

    def test_v1_backward_compat(self):
        state = _base_state()
        state["user_context"] = {
            "user_info": {"user_provide": "姓名：小明", "fact": "", "ai_provide": ""},
            "crush_info": {"crush_name": "", "user_provide": "", "fact": "", "ai_provide": ""},
            "both_info": {"user_provide": "", "fact": "", "ai_provide": ""},
        }
        text = extract_layer1(state)
        assert "用户信息" in text or "暂无" in text

    def test_mixed_version_extraction(self):
        layer1 = create_empty_layer1_memory()
        layer1["full_data"]["user_info"]["user_provide"].append(
            create_atomic_memory("年龄：26", "onboarding", created_at="2026-01-10T10")
        )
        state = _base_state()
        state["layer1_memory"] = layer1
        text = extract_layer1(state)
        assert "年龄：26" in text


class TestBoundContext:
    def test_create_bound_context(self):
        ctx = create_bound_context("action_guide", "标题", "内容")
        assert ctx["type"] == "action_guide"
        assert "id" in ctx

    def test_bound_context_dedup(self):
        state = _base_state()
        task = create_new_task("任务A", "摘要")
        state["layer3_memory"]["task_registry"]["main_agent"] = [task]
        state["layer2_memory"]["action_guides"] = [{
            "id": "g1",
            "title": "指南A",
            "status": "pending",
            "created_at": "2026-01-10T10:00:00",
            "guide_content": "内容1",
            "guide": {"current_task": "指南A", "guide_content": "内容1"},
        }]

        tool = create_context_loader(lambda: state, "main_agent")
        tool.invoke({"action": "bind", "context_type": "action_guide", "context_id": "g1"})
        state["layer2_memory"]["action_guides"][0]["guide_content"] = "内容2"
        tool.invoke({"action": "bind", "context_type": "action_guide", "context_id": "g1"})
        active = state["layer3_memory"]["task_registry"]["main_agent"][0]
        bound = active.get("bound_contexts", [])
        assert len(bound) == 1
        assert bound[0]["content_md"] == "内容2"


class TestTaskStateV2:
    def test_task_with_title(self):
        task = create_new_task("判断Crush态度", "摘要")
        assert task["title"] == "判断Crush态度"

    def test_completion_summary(self):
        state = _base_state()
        task = create_new_task("任务A", "摘要")
        state["layer3_memory"]["task_registry"]["main_agent"] = [task]
        state_update, _ = complete_task_impl(state, "结论摘要")
        state["layer3_memory"] = state_update["layer3_memory"]
        active = state["layer3_memory"]["task_registry"]["main_agent"][0]
        assert active["status"] == "completed"
        assert active["completion_summary"] == "结论摘要"

    def test_reasoning_notes_limit(self):
        state = _base_state()
        task = create_new_task("任务A", "摘要")
        state["layer3_memory"]["task_registry"]["main_agent"] = [task]
        for i in range(9):
            update, _ = append_task_note_impl(state, f"note-{i}")
            state["layer3_memory"] = update["layer3_memory"]
        active = state["layer3_memory"]["task_registry"]["main_agent"][0]
        notes = active.get("reasoning_notes", [])
        assert len(notes) == 8


class TestMarkdownHistory:
    def test_markdown_format_output(self):
        state = _base_state()
        state["messages"] = [
            {"role": "user", "content": "你好", "created_at": "2026-01-15T14:30:00"},
            {"role": "assistant", "content": "你好，我在", "created_at": "2026-01-15T14:31:00"},
        ]
        text = extract_layer3(state)
        assert "## 对话" in text
        assert "[01-15 14:30]" in text
        assert "[01-15 14:31]" in text

    def test_no_thought_in_output(self):
        state = _base_state()
        state["messages"] = [
            {"role": "assistant", "content": '{"thought":"不要输出"}', "created_at": "2026-01-15T14:31:00"},
        ]
        text = extract_layer3(state)
        assert "<thought>" not in text

    def test_reasoning_notes_block(self):
        task = create_new_task("任务A", "摘要")
        task["reasoning_notes"] = [
            {"id": "n1", "content": "结论1", "created_at": "2026-01-15T14:00:00", "task_id": "任务A"}
        ]
        state = _base_state()
        state["layer3_memory"]["task_registry"]["main_agent"] = [task]
        text = extract_layer3(state)
        assert "## 任务笔记" in text
        assert "结论1" in text


class TestTaskTools:
    def test_task_list_display_limit(self):
        tasks = []
        for i in range(10):
            t = create_new_task(f"任务{i}", "摘要")
            t["status"] = "pending"
            t["is_active"] = False
            tasks.append(t)
        for i in range(5):
            t = create_new_task(f"完成{i}", "摘要")
            t["status"] = "completed"
            t["completion_summary"] = "结论"
            t["is_active"] = False
            tasks.append(t)
        tasks[0]["is_active"] = True
        text = format_task_index(tasks)
        assert text.count("|") > 0
        completed_section = text.split("### 已完成任务")[-1]
        rows = [line for line in completed_section.splitlines() if line.startswith("| 完成")]
        assert len(rows) <= 3


class TestLayer1Writer:
    def test_semantic_dedup_same(self):
        layer1 = create_empty_layer1_memory()
        layer2 = create_empty_layer2_memory()

        def fake_llm(prompt: str) -> str:
            return "duplicate"

        layer1, layer2 = save_atomic_memory(
            layer1,
            layer2,
            target="user_info",
            source="user_provide",
            content="姓名：小明",
            source_type="onboarding",
            llm=fake_llm,
        )
        # 第二次应被去重
        layer1, layer2 = save_atomic_memory(
            layer1,
            layer2,
            target="user_info",
            source="user_provide",
            content="姓名：小明",
            source_type="onboarding",
            llm=fake_llm,
        )
        assert len(layer1["full_data"]["user_info"]["user_provide"]) == 1

    def test_semantic_dedup_different(self):
        layer1 = create_empty_layer1_memory()
        layer2 = create_empty_layer2_memory()

        def fake_llm(prompt: str) -> str:
            return "new"

        layer1, layer2 = save_atomic_memory(
            layer1,
            layer2,
            target="user_info",
            source="user_provide",
            content="姓名：小明",
            source_type="onboarding",
            llm=fake_llm,
        )
        layer1, layer2 = save_atomic_memory(
            layer1,
            layer2,
            target="user_info",
            source="user_provide",
            content="年龄：26",
            source_type="onboarding",
            llm=fake_llm,
        )
        assert len(layer1["full_data"]["user_info"]["user_provide"]) == 2

    def test_long_short_term_split(self):
        layer1 = create_empty_layer1_memory()
        layer2 = create_empty_layer2_memory()

        def fake_llm(prompt: str) -> str:
            return "short_term"

        layer1, layer2 = save_atomic_memory(
            layer1,
            layer2,
            target="crush_info",
            source="fact",
            content="下周要出差",
            source_type="conversation",
            llm=fake_llm,
        )
        assert len(layer1["full_data"]["crush_info"]["fact"]) == 0
        assert len(layer2["dynamic_intels"]) == 1


class TestContextAssemblyOrder:
    def test_dynamic_intel_before_guides(self):
        state = _base_state()
        layer2 = create_empty_layer2_memory()
        layer2["dynamic_intels"] = [
            {
                "id": "i1",
                "content": "下周出差",
                "category": "status",
                "subject": "user",
                "valid_from": "2026-01-10T10:00:00",
                "expire_at": "2026-01-20T00:00:00",
                "confidence": 0.8,
                "confidence_reason": "用户明确表述",
                "created_at": "2026-01-10T10",
                "source_type": "conversation",
            }
        ]
        layer2["action_guides"] = [
            {"id": "g1", "status": "in_progress", "guide": {"guide_content": "指南内容"}}
        ]
        state["layer2_memory"] = layer2
        text = extract_layer2(state)
        assert text.find("动态情报板") < text.find("行动指南")
