"""
测试前后端字段统一改造

验证：
1. Status Agent 输出 status_report 为 Markdown string
2. Plan Agent 输出 action_plan 为 Markdown string
3. Guide Agent 同时更新 action_guides 列表
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

# 导入被测模块
from graph.nodes.status_agent import status_agent_node, _parse_response as status_parse
from graph.nodes.plan_agent import plan_agent_node, _format_plan_as_markdown, _parse_response as plan_parse
from graph.nodes.guide_agent import guide_agent_node, _parse_response as guide_parse
from graph.state import create_initial_state
from graph.context_builder import (
    _format_status_report,
    _format_action_plan,
    _format_action_guides,
    _format_legacy_action_guide,
    build_context_dict,
)

# 公共测试数据
NEW_STATUS_REPORT = """## 🧭 情感罗盘

### 当前阶段
你们目前处于暧昧初期...

### 证据链
- 吸引力：中等
- 舒适感：较高
"""

NEW_ACTION_PLAN = """## 阶段目标
建立稳定的约会关系

## 核心策略
先建立信任，再制造机会
"""

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


class TestStatusAgentOutput:
    """测试 Status Agent 输出格式"""
    
    def test_status_report_is_string(self):
        """验证 status_report 输出为 Markdown string 而非 object"""
        # 模拟 LLM 输出
        mock_llm_response = """```json
{
    "need_questions": false,
    "report_content": "## 🧭 情感罗盘\\n\\n### 当前阶段\\n你们目前处于暧昧初期...",
    "stage": "暧昧初期",
    "acr_analysis": {"A": "中", "C": "低", "R": "上升"}
}
```"""
        
        parsed = status_parse(mock_llm_response)
        
        # 验证 report_content 是字符串
        assert "report_content" in parsed
        assert isinstance(parsed["report_content"], str)
        assert "情感罗盘" in parsed["report_content"]
    
    @patch('graph.nodes.status_agent.get_llm')
    def test_status_agent_node_output_type(self, mock_get_llm):
        """验证 status_agent_node 实际输出类型"""
        # 创建 mock LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """```json
{
    "need_questions": false,
    "report_content": "## 现状分析报告\\n\\n这是测试报告内容"
}
```"""
        mock_response.tool_calls = None
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        # 创建初始状态
        state = create_initial_state("我想追一个女生")
        state["last_response_for_continuity"] = "好的，我来帮你分析"
        
        # 调用节点
        result = status_agent_node(state)
        
        # 验证输出
        assert "status_report" in result
        # 关键断言：status_report 应该是 string
        assert isinstance(result["status_report"], str), \
            f"status_report 应该是 string，实际是 {type(result['status_report'])}"
        assert "status_report_id" in result

    @patch('graph.nodes.status_agent.get_llm')
    def test_status_agent_need_questions_true_without_inquiry_card_should_ask(self, mock_get_llm):
        """
        回归测试：
        - 模型按“第一阶段”输出了 need_questions=true 但 inquiry_card=null（或缺失）
        - status_agent_node 不应直接生成报告
        - 严格模式：不做纠错、不做兜底；应显式返回错误，且不产出报告
        """
        mock_llm = MagicMock()
        resp = MagicMock()
        resp.content = """```json
{
  "need_questions": true,
  "response": "我需要再确认几个点。",
  "inquiry_card": null,
  "report_content": null
}
```"""
        resp.tool_calls = None

        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = resp
        mock_get_llm.return_value = mock_llm

        state = create_initial_state("我想追一个女生")
        state["last_response_for_continuity"] = "好的，我来帮你分析"

        result = status_agent_node(state)

        # 不产出报告
        assert result.get("status_report") is None
        assert result.get("inquiry_card") is None
        # 显式错误提示（便于排查，不吞 bug）
        msgs = result.get("messages", [])
        assert msgs and "系统异常" in (msgs[0].get("content") if isinstance(msgs[0], dict) else "")
        # 进入暂停态，避免同一轮回到 main_agent 覆盖错误
        assert result.get("current_agent") == "status_agent"
        assert result.get("agent_resume_point") == "continue_analysis"


class TestPlanAgentOutput:
    """测试 Plan Agent 输出格式"""
    
    def test_format_plan_as_markdown(self):
        """验证 _format_plan_as_markdown 函数"""
        plan_data = {
            "goal": "建立稳定的约会关系",
            "strategy": "先建立信任，再制造机会",
            "phases": [
                {
                    "name": "建立信任期",
                    "description": "通过日常互动建立舒适感",
                    "duration": "1-2周",
                    "milestone": "能够自然地约出来"
                },
                {
                    "name": "推进期",
                    "description": "制造单独相处的机会",
                    "duration": "2-3周",
                    "milestone": "有暧昧的氛围"
                }
            ],
            "key_principles": ["保持真诚", "不要太主动", "观察对方反应"]
        }
        
        markdown = _format_plan_as_markdown(plan_data)
        
        # 验证是字符串
        assert isinstance(markdown, str)
        
        # 验证包含关键内容
        assert "## 阶段目标" in markdown
        assert "建立稳定的约会关系" in markdown
        assert "## 核心策略" in markdown
        assert "## 分阶段计划" in markdown
        assert "### 阶段 1: 建立信任期" in markdown
        assert "### 阶段 2: 推进期" in markdown
        assert "## 关键原则" in markdown
        assert "- 保持真诚" in markdown
    
    def test_format_plan_as_markdown_empty(self):
        """验证空数据时的处理"""
        markdown = _format_plan_as_markdown({})
        assert isinstance(markdown, str)
        assert markdown == ""
    
    @patch('graph.nodes.plan_agent.get_llm')
    def test_plan_agent_node_output_type(self, mock_get_llm):
        """验证 plan_agent_node 实际输出类型"""
        # 创建 mock LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """```json
{
    "need_questions": false,
    "goal": "测试目标",
    "strategy": "测试策略",
    "phases": [],
    "key_principles": ["原则1"],
    "summary": "测试总结"
}
```"""
        mock_response.tool_calls = None
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        # 创建初始状态
        state = create_initial_state("我想追一个女生")
        state["last_response_for_continuity"] = "好的，我来帮你制定计划"
        state["status_report"] = "已有现状分析"
        
        # 调用节点
        result = plan_agent_node(state)
        
        # 验证输出
        assert "action_plan" in result
        # 关键断言：action_plan 应该是 string
        assert isinstance(result["action_plan"], str), \
            f"action_plan 应该是 string，实际是 {type(result['action_plan'])}"
        assert "action_plan_id" in result


class TestGuideAgentOutput:
    """测试 Guide Agent 输出格式"""
    
    @patch('graph.nodes.guide_agent.get_llm')
    def test_guide_agent_updates_action_guides_list(self, mock_get_llm):
        """验证 guide_agent_node 同时更新 action_guides 列表"""
        # 创建 mock LLM
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """```json
{
    "need_questions": false,
    "guide_content": "## 📋 任务卡片：发一条朋友圈\\n\\n### 执行步骤\\n1. 选择一张好看的照片..."
}
```"""
        mock_response.tool_calls = None
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        # 创建初始状态，预设一个已有的指南（v3.1 真源：layer2_memory.all_action_guides）
        state = create_initial_state("我想追一个女生")
        state["last_response_for_continuity"] = "好的，我来给你具体指导"
        state["status_report"] = "已有现状分析"
        state["action_plan"] = "已有行动规划"
        from graph.context_types import create_empty_layer2_memory
        state["layer2_memory"] = create_empty_layer2_memory()
        state["layer2_memory"]["all_action_guides"] = [{
            "id": "g_existing",
            "guide_id": 1,
            "status": "completed",
            "title": "旧指南",
            "one_liner": "旧指南摘要",
            "guide": {"guide_content": "旧指南内容"},
            "created_at": "2025-01-01T00:00:00",
            "completed_at": "2025-01-02T00:00:00",
        }]
        # 向后兼容字段（可选）
        state["action_guides"] = list(state["layer2_memory"]["all_action_guides"])
        
        # 调用节点
        result = guide_agent_node(state)
        
        # 验证输出
        assert "action_guides" in result
        assert isinstance(result["action_guides"], list)
        
        # 关键断言：列表应该有 2 个元素（1个旧的 + 1个新的）
        assert len(result["action_guides"]) == 2, \
            f"action_guides 应该有 2 个元素，实际有 {len(result['action_guides'])} 个"
        
        # 验证新指南的结构
        new_guide = result["action_guides"][-1]
        assert "id" in new_guide
        assert isinstance(new_guide["id"], str) and len(new_guide["id"]) > 0
        assert new_guide["status"] == "pending"
        assert "guide" in new_guide and isinstance(new_guide["guide"], dict)
        assert isinstance(new_guide["guide"].get("guide_content", ""), str)
        assert "任务卡片" in new_guide["guide"]["guide_content"]
        
        # 验证旧版兼容字段
        assert "action_guide" in result
        assert isinstance(result["action_guide"], str)
    
    @patch('graph.nodes.guide_agent.get_llm')
    def test_guide_agent_first_guide(self, mock_get_llm):
        """验证第一次生成指南时 action_guides 列表正确初始化"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """```json
{
    "need_questions": false,
    "guide_content": "## 第一个指南\\n内容..."
}
```"""
        mock_response.tool_calls = None
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        # 创建初始状态，action_guides 为空
        state = create_initial_state("测试")
        state["last_response_for_continuity"] = "测试"
        state["action_guides"] = []  # 空列表
        
        result = guide_agent_node(state)
        
        # 验证
        assert "action_guides" in result
        assert len(result["action_guides"]) == 1
        assert result["action_guides"][0]["status"] == "pending"


class TestContextBuilderCompatibility:
    """测试 context_builder 对新旧格式的兼容性"""

    def test_format_status_report_string(self):
        formatted = _format_status_report(NEW_STATUS_REPORT)
        assert NEW_STATUS_REPORT in formatted

    def test_format_status_report_dict(self):
        formatted = _format_status_report(LEGACY_STATUS_REPORT)
        assert "情感罗盘" in formatted

    def test_format_action_plan_string(self):
        formatted = _format_action_plan(NEW_ACTION_PLAN)
        assert "阶段目标" in formatted

    def test_format_action_plan_dict(self):
        formatted = _format_action_plan(LEGACY_ACTION_PLAN)
        assert "核心策略" in formatted or "阶段性目标" in formatted

    def test_format_action_guides_new_format(self):
        guides = [{"id": "guide_1", "status": "pending", "guide_content": "## 📋 新指南"}]
        formatted = _format_action_guides(guides)
        assert "新指南" in formatted

    def test_format_action_guides_legacy_format(self):
        guides = [{"id": "guide_old", "status": "pending", "guide": {"guide_content": "## 旧指南"}}]
        formatted = _format_action_guides(guides)
        assert "旧指南" in formatted

    def test_format_legacy_action_guide_string(self):
        formatted = _format_legacy_action_guide("## 单指南")
        assert "单指南" in formatted

    def test_format_legacy_action_guide_dict(self):
        formatted = _format_legacy_action_guide(LEGACY_ACTION_GUIDE)
        assert "任务卡片" in formatted or "当前任务" in formatted


class TestReportIdGeneration:
    """测试报告编号生成"""

    @patch("graph.nodes.status_agent.get_llm")
    def test_status_report_id_increment(self, mock_get_llm):
        mock_llm = MagicMock()
        resp1 = MagicMock()
        resp2 = MagicMock()
        resp1.content = """```json
{
    "need_questions": false,
    "report_content": "## 报告一"
}
```"""
        resp2.content = """```json
{
    "need_questions": false,
    "report_content": "## 报告二"
}
```"""
        resp1.tool_calls = None
        resp2.tool_calls = None
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [resp1, resp2]
        mock_get_llm.return_value = mock_llm

        state = create_initial_state("测试编号")
        state["last_response_for_continuity"] = "开始"

        res1 = status_agent_node(state)
        state.update(res1)
        state["last_response_for_continuity"] = "继续"

        res2 = status_agent_node(state)

        assert res1["status_report_id"] == 1
        assert res2["status_report_id"] == 2
        assert res2["report_counter"]["status_report"] == 2

    @patch("graph.nodes.plan_agent.get_llm")
    def test_action_plan_id_increment(self, mock_get_llm):
        mock_llm = MagicMock()
        resp1 = MagicMock()
        resp2 = MagicMock()
        for resp, title in [(resp1, "规划一"), (resp2, "规划二")]:
            resp.content = f"""```json
{{
    "need_questions": false,
    "goal": "{title}",
    "strategy": "测试策略",
    "phases": [],
    "key_principles": ["原则1"],
    "summary": "测试总结"
}}
```"""
            resp.tool_calls = None
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [resp1, resp2]
        mock_get_llm.return_value = mock_llm

        state = create_initial_state("规划编号")
        state["status_report"] = "已有现状"
        state["last_response_for_continuity"] = "好的"

        res1 = plan_agent_node(state)
        state.update(res1)
        state["last_response_for_continuity"] = "继续"

        res2 = plan_agent_node(state)

        assert res1["action_plan_id"] == 1
        assert res2["action_plan_id"] == 2
        assert res2["report_counter"]["action_plan"] == 2

    @patch("graph.nodes.guide_agent.get_llm")
    def test_action_guide_id_format(self, mock_get_llm):
        mock_llm = MagicMock()
        resp = MagicMock()
        resp.content = """```json
{
    "need_questions": false,
    "guide_content": "## 指南编号测试"
}
```"""
        resp.tool_calls = None
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = resp
        mock_get_llm.return_value = mock_llm

        state = create_initial_state("指南编号")
        state["status_report"] = "已有现状"
        state["action_plan"] = "已有规划"
        state["last_response_for_continuity"] = "好的"

        res = guide_agent_node(state)
        guide_id = res["action_guides"][0]["id"]
        assert isinstance(guide_id, str) and len(guide_id) > 0


class TestActionGuidesListAppendExtended:
    """测试 action_guides 列表追加和状态字段"""

    @patch("graph.nodes.guide_agent.get_llm")
    def test_multiple_guides_accumulation(self, mock_get_llm):
        mock_llm = MagicMock()
        resp1 = MagicMock()
        resp2 = MagicMock()
        resp1.content = """```json
{
    "need_questions": false,
    "guide_content": "## 第一个指南"
}
```"""
        resp2.content = """```json
{
    "need_questions": false,
    "guide_content": "## 第二个指南"
}
```"""
        resp1.tool_calls = None
        resp2.tool_calls = None
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [resp1, resp2]
        mock_get_llm.return_value = mock_llm

        state = create_initial_state("测试多指南")
        state["status_report"] = "已有现状"
        state["action_plan"] = "已有规划"
        state["action_guides"] = []
        state["last_response_for_continuity"] = "好的"

        res1 = guide_agent_node(state)
        state.update(res1)
        state["last_response_for_continuity"] = "继续"

        res2 = guide_agent_node(state)

        assert len(res2["action_guides"]) == 2
        assert any("第一个指南" in (g.get("guide", {}) or {}).get("guide_content", "") for g in res2["action_guides"])
        assert any("第二个指南" in (g.get("guide", {}) or {}).get("guide_content", "") for g in res2["action_guides"])

    @patch("graph.nodes.guide_agent.get_llm")
    def test_guide_status_fields(self, mock_get_llm):
        mock_llm = MagicMock()
        resp = MagicMock()
        resp.content = """```json
{
    "need_questions": false,
    "guide_content": "## 状态字段测试"
}
```"""
        resp.tool_calls = None
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = resp
        mock_get_llm.return_value = mock_llm

        state = create_initial_state("状态字段")
        state["status_report"] = "已有现状"
        state["action_plan"] = "已有规划"
        state["last_response_for_continuity"] = "好的"

        res = guide_agent_node(state)
        guide = res["action_guides"][0]
        assert guide["status"] == "pending"
        assert guide.get("created_at") is not None
        assert guide.get("completed_at") is None
        assert isinstance((guide.get("title") or ""), str)
        assert isinstance((guide.get("one_liner") or ""), str)


class TestParseResponseFunctions:
    """测试各 Agent 的 _parse_response 函数"""
    
    def test_status_parse_with_markdown_block(self):
        """测试带 markdown 代码块的解析"""
        content = """我来分析一下你的情况。

```json
{
    "need_questions": false,
    "report_content": "## 报告内容"
}
```

希望对你有帮助。"""
        
        parsed = status_parse(content)
        assert parsed["need_questions"] == False
        assert parsed["report_content"] == "## 报告内容"
    
    def test_plan_parse_with_phases(self):
        """测试解析包含 phases 的规划"""
        content = """```json
{
    "need_questions": false,
    "goal": "目标",
    "strategy": "策略",
    "phases": [{"name": "阶段1", "description": "描述"}],
    "key_principles": ["原则"]
}
```"""
        
        parsed = plan_parse(content)
        assert parsed["goal"] == "目标"
        assert len(parsed["phases"]) == 1
    
    def test_guide_parse_content(self):
        """测试解析指南内容"""
        content = """```json
{
    "need_questions": false,
    "guide_content": "## 任务卡片\\n步骤..."
}
```"""
        
        parsed = guide_parse(content)
        assert "guide_content" in parsed
        assert "任务卡片" in parsed["guide_content"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

