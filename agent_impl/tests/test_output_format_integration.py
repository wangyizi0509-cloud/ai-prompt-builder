import pytest

from graph.context_builder import build_context_dict
from graph.state import create_initial_state


NEW_STATUS_REPORT = """## 🧭 情感罗盘

### 当前阶段
你们目前处于暧昧初期...
"""

NEW_ACTION_PLAN = """## 阶段目标
建立稳定的约会关系
"""

NEW_GUIDE_CONTENT = "## 📋 任务卡片：发一条朋友圈"

LEGACY_STATUS_REPORT = {
    "stage": "L2-吸引期",
    "stage_description": "你们处于吸引期",
    "acr_analysis": {"A": "中", "C": "低", "R": "上升"},
    "key_issues": ["需求感过高"],
    "report_content": "## 情感罗盘\n...",
}

LEGACY_ACTION_PLAN = {
    "goal": "建立约会关系",
    "strategy": "循序渐进",
    "phases": [],
    "key_principles": ["保持真诚"],
    "summary": "规划摘要",
}

LEGACY_ACTION_GUIDE = {
    "current_task": "发朋友圈",
    "steps": ["选择照片", "编写文案"],
    "guide_content": "## 任务卡片\n...",
}


class TestOutputFormatIntegration:
    """测试完整流程中的输出格式"""

    def test_status_report_in_context_dict(self):
        state = create_initial_state("测试状态")
        state["status_report"] = NEW_STATUS_REPORT
        ctx = build_context_dict(state, target_agent="status_agent")
        assert isinstance(ctx["status_report"], str)
        assert "情感罗盘" in ctx["status_report"]

    def test_action_plan_in_context_dict(self):
        state = create_initial_state("测试规划")
        state["action_plan"] = NEW_ACTION_PLAN
        ctx = build_context_dict(state, target_agent="plan_agent")
        assert isinstance(ctx["action_plan"], str)
        assert "阶段目标" in ctx["action_plan"]

    def test_action_guides_in_context_dict(self):
        state = create_initial_state("测试指南")
        state["action_guides"] = [
            {"id": "guide_1", "status": "pending", "guide_content": NEW_GUIDE_CONTENT}
        ]
        ctx = build_context_dict(state, target_agent="guide_agent")
        assert isinstance(ctx["action_guides"], str)
        # 旧版兼容路径：pending 指南仍会被渲染为完整内容
        assert "任务卡片" in ctx["action_guides"]

    def test_context_builder_reads_new_format(self):
        state = create_initial_state("全量测试")
        state["status_report"] = NEW_STATUS_REPORT
        state["action_plan"] = NEW_ACTION_PLAN
        state["action_guides"] = [
            {"id": "guide_1", "status": "pending", "guide_content": NEW_GUIDE_CONTENT}
        ]
        ctx = build_context_dict(state, target_agent="main_agent")
        assert "情感罗盘" in ctx["status_report"]
        assert "阶段目标" in ctx["action_plan"]
        assert "任务卡片" in ctx["action_guides"]

    def test_instruction_in_context_dict(self):
        """
        v3.0: Main Agent -> 专家 Brief（instruction）必须能被 context_builder 传递给下游。
        """
        state = create_initial_state("测试 instruction")
        state["instruction"] = "请优先分析关系阶段是否发生变化，并给出关键证据链。"
        ctx = build_context_dict(state, target_agent="status_agent")
        assert "instruction" in ctx
        assert isinstance(ctx["instruction"], str)
        assert "证据链" in ctx["instruction"]

    def test_progressive_disclosure_only_in_progress_expanded(self):
        """
        新版：只有 in_progress 指南完整展开，其他状态输出元数据表格并提示可用工具加载详情。
        """
        state = create_initial_state("测试渐进式披露")
        # 使用 v3.1 真源：layer2_memory.action_guides
        from graph.context_types import create_empty_layer2_memory
        layer2 = create_empty_layer2_memory()
        layer2["action_guides"] = [
            {
                "id": "g_inp",
                "guide_id": 3,
                "status": "in_progress",
                "title": "周五约会准备",
                "one_liner": "准备约会要点",
                "guide": {"guide_content": "## 📋 任务卡片：周五约会准备\n\n### 👣 执行步骤\n1. ..."},
                "created_at": "2025-01-01T00:00:00",
            },
            {
                "id": "g_pen",
                "guide_id": 4,
                "status": "pending",
                "title": "下周约饭",
                "one_liner": "计划下周三晚约饭",
                "guide": {"guide_content": "## 📋 任务卡片：下周约饭"},
                "created_at": "2025-01-02T00:00:00",
            },
            {
                "id": "g_cmp",
                "guide_id": 1,
                "status": "completed",
                "title": "第一次搭讪",
                "one_liner": "成功建立初步联系",
                "guide": {"guide_content": "## 📋 任务卡片：第一次搭讪"},
                "created_at": "2025-01-03T00:00:00",
                "completed_at": "2025-01-04T00:00:00",
            },
        ]
        state["layer2_memory"] = layer2

        ctx = build_context_dict(state, target_agent="main_agent")
        guides_section = ctx.get("action_guides", "")
        assert isinstance(guides_section, str)

        # in_progress：完整内容应该出现
        assert "当前进行中" in guides_section
        assert "周五约会准备" in guides_section
        assert "执行步骤" in guides_section

        # 其他状态：应当是表格元数据，并提示工具
        assert "context_loader" in guides_section
        assert "| g_pen |" in guides_section
        assert "| g_cmp |" in guides_section


class TestLegacyDataCompatibility:
    """测试旧版数据格式的兼容性"""

    def test_legacy_dict_status_report(self):
        state = create_initial_state("旧状态")
        state["status_report"] = LEGACY_STATUS_REPORT
        ctx = build_context_dict(state, target_agent="status_agent")
        assert "情感罗盘" in ctx["status_report"]

    def test_legacy_dict_action_plan(self):
        state = create_initial_state("旧规划")
        state["action_plan"] = LEGACY_ACTION_PLAN
        ctx = build_context_dict(state, target_agent="plan_agent")
        assert "阶段性目标" in ctx["action_plan"] or "核心策略" in ctx["action_plan"]

    def test_legacy_nested_action_guide(self):
        state = create_initial_state("旧指南")
        state["action_guides"] = [
            {"id": "guide_old", "status": "pending", "guide": {"guide_content": "## 旧指南"}}
        ]
        ctx = build_context_dict(state, target_agent="guide_agent")
        assert "旧指南" in ctx["action_guides"]

    def test_mixed_format_handling(self):
        state = create_initial_state("混合格式")
        state["status_report"] = LEGACY_STATUS_REPORT
        state["action_plan"] = NEW_ACTION_PLAN
        state["action_guides"] = [
            {"id": "guide_new", "status": "pending", "guide_content": NEW_GUIDE_CONTENT},
            {"id": "guide_old", "status": "pending", "guide": {"guide_content": "## 旧指南"}},
        ]
        ctx = build_context_dict(state, target_agent="main_agent")
        assert "情感罗盘" in ctx["status_report"]
        assert "阶段目标" in ctx["action_plan"]
        assert "任务卡片" in ctx["action_guides"] and "旧指南" in ctx["action_guides"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




