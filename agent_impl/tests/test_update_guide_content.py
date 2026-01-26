"""
测试 update_guide_content 工具
验证指南内容原地更新功能
"""

import pytest
from graph.state import create_initial_state
from graph.context_types import (
    create_action_guide_item,
    create_empty_layer2_memory,
    ActionGuideContent,
)
from graph.tools.submit_tools import apply_submit_tool_state_update


class TestUpdateGuideContent:
    """update_guide_content 工具测试"""

    def test_create_guide_with_version(self):
        """测试创建指南时包含版本字段"""
        guide_content = ActionGuideContent(
            current_task="测试任务",
            steps=["步骤1", "步骤2"],
            guide_content="# 测试指南\n测试内容",
        )
        guide_item = create_action_guide_item(
            guide=guide_content,
            guide_id=1,
            title="测试指南",
        )
        
        # 验证版本字段初始化
        assert guide_item["version"] == 1, "初始版本应该是1"
        assert guide_item["content_history"] == [], "初始历史应该为空"
        assert guide_item["guide_id"] == 1, "guide_id 应该正确"

    def test_update_guide_content_basic(self):
        """测试基本的内容更新"""
        # 创建初始状态和指南
        state = create_initial_state("测试消息")
        layer2_memory = create_empty_layer2_memory()
        
        guide_content = ActionGuideContent(
            current_task="原始任务",
            steps=["原始步骤1"],
            guide_content="# 原始指南\n原始内容",
        )
        guide_item = create_action_guide_item(
            guide=guide_content,
            guide_id=1,
            title="原始标题",
            one_liner="原始摘要",
        )
        guide_uid = guide_item["id"]
        
        layer2_memory["action_guides"] = [guide_item]
        state["layer2_memory"] = layer2_memory
        
        # 调用 update_guide_content
        tool_args = {
            "guide_id": guide_uid,
            "guide_markdown": "# 更新后的指南\n新内容",
            "title": "新标题",
            "one_liner": "新摘要",
            "current_task": "新任务",
            "steps": ["新步骤1", "新步骤2"],
            "update_reason": "测试更新",
        }
        
        result = apply_submit_tool_state_update(state, "update_guide_content", tool_args)
        
        # 验证返回结果
        assert result, "应该返回状态更新"
        assert "_submit_result" in result, "应该有 _submit_result"
        assert result["_submit_result"]["type"] == "guide_content_update", "类型应该正确"
        assert result["_submit_result"]["guide_uid"] == guide_uid, "guide_uid 应该正确"
        assert result["_submit_result"]["guide_id"] == 1, "guide_id 应该正确"
        
        # 验证更新后的指南
        updated_guides = result["layer2_memory"]["action_guides"]
        assert len(updated_guides) == 1, "应该仍然只有1个指南"
        
        updated_guide = updated_guides[0]
        assert updated_guide["version"] == 2, "版本应该递增到2"
        assert updated_guide["title"] == "新标题", "标题应该更新"
        assert updated_guide["one_liner"] == "新摘要", "摘要应该更新"
        assert updated_guide["guide"]["current_task"] == "新任务", "任务应该更新"
        assert updated_guide["guide"]["steps"] == ["新步骤1", "新步骤2"], "步骤应该更新"
        assert updated_guide["guide"]["guide_content"] == "# 更新后的指南\n新内容", "内容应该更新"
        
        # 验证历史版本保存
        assert len(updated_guide["content_history"]) == 1, "应该有1个历史版本"
        history = updated_guide["content_history"][0]
        assert history["version"] == 1, "历史版本号应该是1"
        assert history["title"] == "原始标题", "历史标题应该正确"
        assert history["guide"]["current_task"] == "原始任务", "历史任务应该正确"
        assert history["update_reason"] == "测试更新", "更新原因应该正确"

    def test_update_guide_content_preserve_unchanged_fields(self):
        """测试更新时保留未指定的字段"""
        state = create_initial_state("测试消息")
        layer2_memory = create_empty_layer2_memory()
        
        guide_content = ActionGuideContent(
            current_task="原始任务",
            steps=["原始步骤"],
            guide_content="原始内容",
        )
        guide_item = create_action_guide_item(
            guide=guide_content,
            guide_id=1,
            title="原始标题",
        )
        guide_uid = guide_item["id"]
        
        layer2_memory["action_guides"] = [guide_item]
        state["layer2_memory"] = layer2_memory
        
        # 只更新 guide_markdown，不更新 title
        tool_args = {
            "guide_id": guide_uid,
            "guide_markdown": "新内容",
            # title 不传，应该保留原标题
        }
        
        result = apply_submit_tool_state_update(state, "update_guide_content", tool_args)
        updated_guide = result["layer2_memory"]["action_guides"][0]
        
        # 标题应该保留原值
        assert updated_guide["title"] == "原始标题", "未更新的标题应该保留"
        # 内容应该更新
        assert updated_guide["guide"]["guide_content"] == "新内容", "内容应该更新"

    def test_update_guide_content_multiple_updates(self):
        """测试多次连续更新"""
        state = create_initial_state("测试消息")
        layer2_memory = create_empty_layer2_memory()
        
        guide_content = ActionGuideContent(
            current_task="V1任务",
            guide_content="V1内容",
        )
        guide_item = create_action_guide_item(
            guide=guide_content,
            guide_id=1,
            title="V1标题",
        )
        guide_uid = guide_item["id"]
        
        layer2_memory["action_guides"] = [guide_item]
        state["layer2_memory"] = layer2_memory
        
        # 第一次更新
        result1 = apply_submit_tool_state_update(state, "update_guide_content", {
            "guide_id": guide_uid,
            "guide_markdown": "V2内容",
            "title": "V2标题",
            "update_reason": "第一次更新",
        })
        state["layer2_memory"] = result1["layer2_memory"]
        
        # 第二次更新
        result2 = apply_submit_tool_state_update(state, "update_guide_content", {
            "guide_id": guide_uid,
            "guide_markdown": "V3内容",
            "title": "V3标题",
            "update_reason": "第二次更新",
        })
        
        updated_guide = result2["layer2_memory"]["action_guides"][0]
        
        # 验证最终版本
        assert updated_guide["version"] == 3, "版本应该是3"
        assert updated_guide["title"] == "V3标题", "标题应该是V3"
        assert updated_guide["guide"]["guide_content"] == "V3内容", "内容应该是V3"
        
        # 验证历史记录
        assert len(updated_guide["content_history"]) == 2, "应该有2个历史版本"
        assert updated_guide["content_history"][0]["version"] == 1, "第一个历史版本应该是V1"
        assert updated_guide["content_history"][0]["title"] == "V1标题"
        assert updated_guide["content_history"][1]["version"] == 2, "第二个历史版本应该是V2"
        assert updated_guide["content_history"][1]["title"] == "V2标题"

    def test_update_guide_content_nonexistent_guide(self):
        """测试更新不存在的指南"""
        state = create_initial_state("测试消息")
        layer2_memory = create_empty_layer2_memory()
        layer2_memory["action_guides"] = []
        state["layer2_memory"] = layer2_memory
        
        tool_args = {
            "guide_id": "nonexistent-id",
            "guide_markdown": "新内容",
        }
        
        result = apply_submit_tool_state_update(state, "update_guide_content", tool_args)
        
        # 应该返回空，表示更新失败
        assert result == {}, "更新不存在的指南应该返回空"

    def test_update_guide_content_empty_guide_id(self):
        """测试空 guide_id"""
        state = create_initial_state("测试消息")
        
        tool_args = {
            "guide_id": "",
            "guide_markdown": "新内容",
        }
        
        result = apply_submit_tool_state_update(state, "update_guide_content", tool_args)
        assert result == {}, "空 guide_id 应该返回空"

    def test_update_guide_content_empty_markdown(self):
        """测试空 guide_markdown"""
        state = create_initial_state("测试消息")
        
        tool_args = {
            "guide_id": "some-id",
            "guide_markdown": "",
        }
        
        result = apply_submit_tool_state_update(state, "update_guide_content", tool_args)
        assert result == {}, "空 markdown 应该返回空"

    def test_update_guide_content_preserve_guide_id_number(self):
        """测试更新后 guide_id（编号）保持不变"""
        state = create_initial_state("测试消息")
        layer2_memory = create_empty_layer2_memory()
        
        guide_content = ActionGuideContent(guide_content="原始内容")
        guide_item = create_action_guide_item(
            guide=guide_content,
            guide_id=5,  # 编号为5
            title="原始标题",
        )
        guide_uid = guide_item["id"]
        
        layer2_memory["action_guides"] = [guide_item]
        state["layer2_memory"] = layer2_memory
        
        tool_args = {
            "guide_id": guide_uid,
            "guide_markdown": "新内容",
        }
        
        result = apply_submit_tool_state_update(state, "update_guide_content", tool_args)
        updated_guide = result["layer2_memory"]["action_guides"][0]
        
        # guide_id（编号）应该保持不变
        assert updated_guide["guide_id"] == 5, "编号应该保持不变"
        # id（UUID）也应该保持不变
        assert updated_guide["id"] == guide_uid, "UUID 应该保持不变"

    def test_update_guide_content_in_tool_names(self):
        """测试 update_guide_content 在 SUBMIT_TOOL_NAMES 中"""
        from graph.tools.submit_tools import SUBMIT_TOOL_NAMES, is_submit_tool
        
        assert "update_guide_content" in SUBMIT_TOOL_NAMES, "应该在 SUBMIT_TOOL_NAMES 中"
        assert is_submit_tool("update_guide_content"), "is_submit_tool 应该返回 True"
