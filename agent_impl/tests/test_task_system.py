"""
任务系统验收测试 (Task System Acceptance Tests)

验收标准（来自 PRD）：
1. 已存在任务 A/B/C，活跃为 A：用户输入属于 B → 工具切换后活跃为 B
2. 切换到 C 不会创建新的 C（不会出现重复 task_id）
3. 创建新任务 D 后，任务列表新增 D 且 D 为活跃
4. 追加任务笔记后，下一轮能在"当前活跃任务信息"中看到新增内容
5. 任意时刻只有一个活跃任务

基于 Task_System/task_system_spec.md 规范：
- 使用 status 字段替代 is_active
- 使用 reasoning_notes 替代 reasoning
"""

import pytest
import json
from datetime import datetime

from graph.state import create_initial_state
from graph.context_types import (
    create_new_task,
    create_empty_layer3_memory,
    create_empty_task_registry,
    create_reasoning_note,
)
from graph.tools.task_tools import (
    switch_task_impl,
    create_task_impl,
    append_task_note_impl,
    format_task_index,
    format_active_task_payload,
    get_task_list_for_agent,
    get_active_task,
    get_task_by_id,
    apply_task_tool_state_update,
    is_task_tool,
    TASK_TOOL_NAMES,
)
from graph.context_builder import build_context_dict


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def state_with_tasks():
    """创建包含 3 个任务（A/B/C）的状态，A 为活跃"""
    state = create_initial_state("测试消息")
    
    # 创建任务 A（活跃）
    task_a = create_new_task("分析crush态度", "分析crush态度", "分析 crush 对用户的态度")
    task_a["status"] = "active"
    
    # 创建任务 B
    task_b = create_new_task("写开场白", "写开场白", "帮用户写一个开场白")
    task_b["status"] = "pending"
    task_b["reasoning_notes"] = [
        create_reasoning_note("用户想重新开启话题", "写开场白"),
        create_reasoning_note("建议使用轻松的方式", "写开场白"),
    ]
    
    # 创建任务 C
    task_c = create_new_task("约会规划", "约会规划", "规划第一次约会")
    task_c["status"] = "pending"
    
    # 构建 layer3_memory
    layer3_memory = create_empty_layer3_memory()
    layer3_memory["task_registry"] = {
        "main_agent": [task_a, task_b, task_c],
        "status_agent": [],
        "plan_agent": [],
        "guide_agent": [],
    }
    state["layer3_memory"] = layer3_memory
    
    return state


@pytest.fixture
def empty_state():
    """创建没有任务的空状态"""
    return create_initial_state("测试消息")


# ============================================================
# Test: 任务切换 (switch_task)
# ============================================================

class TestSwitchTask:
    """测试任务切换功能"""
    
    def test_switch_to_existing_task(self, state_with_tasks):
        """US1: 切换到已存在的任务 B，活跃任务应变为 B"""
        state = state_with_tasks
        
        # 切换到任务 B
        state_update, result_json = switch_task_impl(state, "写开场白", "main_agent")
        result = json.loads(result_json)
        
        # 验证切换成功
        assert result["success"] is True
        assert "写开场白" in result["message"]
        
        # 验证活跃任务变为 B
        active_task = result["active_task"]
        assert active_task["task_id"] == "写开场白"
        assert len(active_task["reasoning_notes"]) == 2  # B 有 2 条笔记
        
        # 验证状态更新正确
        assert "layer3_memory" in state_update
        new_task_list = state_update["layer3_memory"]["task_registry"]["main_agent"]
        
        # 只有一个活跃任务
        active_count = sum(1 for t in new_task_list if t.get("status") == "active")
        assert active_count == 1
        
        # 活跃任务是 B
        active_task_in_list = next(t for t in new_task_list if t.get("status") == "active")
        assert active_task_in_list["task_id"] == "写开场白"
    
    def test_switch_to_nonexistent_task_fails(self, state_with_tasks):
        """切换到不存在的任务应失败"""
        state = state_with_tasks
        
        state_update, result_json = switch_task_impl(state, "不存在的任务", "main_agent")
        result = json.loads(result_json)
        
        assert result["success"] is False
        assert "不存在" in result["error"]
        assert "hint" in result
        
        # 状态不应有更新
        assert state_update == {}
    
    def test_switch_preserves_task_uniqueness(self, state_with_tasks):
        """切换任务不会创建重复的 task_id"""
        state = state_with_tasks
        
        # 切换到 C
        state_update, _ = switch_task_impl(state, "约会规划", "main_agent")
        
        # 验证任务列表中没有重复
        new_task_list = state_update["layer3_memory"]["task_registry"]["main_agent"]
        task_ids = [t["task_id"] for t in new_task_list]
        assert len(task_ids) == len(set(task_ids))  # 无重复
        assert task_ids.count("约会规划") == 1


# ============================================================
# Test: 创建任务 (create_task)
# ============================================================

class TestCreateTask:
    """测试任务创建功能"""
    
    def test_create_new_task(self, state_with_tasks):
        """US2: 创建新任务 D，应新增到列表且设为活跃"""
        state = state_with_tasks
        
        state_update, result_json = create_task_impl(
            state, "表白时机", "表白时机", "判断何时表白最合适", "main_agent"
        )
        result = json.loads(result_json)
        
        # 验证创建成功
        assert result["success"] is True
        assert "表白时机" in result["message"]
        
        # 验证新任务在列表中
        new_task_list = state_update["layer3_memory"]["task_registry"]["main_agent"]
        task_ids = [t["task_id"] for t in new_task_list]
        assert "表白时机" in task_ids
        
        # 验证新任务是活跃的
        new_task = next(t for t in new_task_list if t["task_id"] == "表白时机")
        assert new_task["status"] == "active"
        assert new_task["summary"] == "判断何时表白最合适"
        
        # 验证原活跃任务 A 变为非活跃
        task_a = next(t for t in new_task_list if t["task_id"] == "分析crush态度")
        assert task_a["status"] == "pending"
    
    def test_create_duplicate_task_fails(self, state_with_tasks):
        """尝试创建已存在的 task_id 应失败"""
        state = state_with_tasks
        
        state_update, result_json = create_task_impl(
            state, "分析crush态度", "分析crush态度", "重复的任务", "main_agent"
        )
        result = json.loads(result_json)
        
        assert result["success"] is False
        assert "已存在" in result["error"]
        assert "switch_task" in result["hint"]
        
        # 状态不应有更新
        assert state_update == {}
    
    def test_create_task_with_default_summary(self, empty_state):
        """创建任务时不提供 summary 应使用默认值"""
        state = empty_state
        
        state_update, result_json = create_task_impl(
            state, "新任务名称很长很长的ID", "新任务名称很长很长的ID", "", "main_agent"
        )
        result = json.loads(result_json)
        
        assert result["success"] is True
        
        new_task_list = state_update["layer3_memory"]["task_registry"]["main_agent"]
        new_task = new_task_list[0]
        assert "新任务名称很长很长的ID"[:20] in new_task["summary"]


# ============================================================
# Test: 追加任务笔记 (append_task_note)
# ============================================================

class TestAppendTaskNote:
    """测试追加任务笔记功能"""
    
    def test_append_note_to_active_task(self, state_with_tasks):
        """追加笔记到当前活跃任务"""
        state = state_with_tasks
        
        state_update, result_json = append_task_note_impl(
            state, "用户情绪比较焦虑，需要先安抚", None, "main_agent"
        )
        result = json.loads(result_json)
        
        assert result["success"] is True
        assert result["note_count"] >= 1
        
        # 验证笔记已追加
        new_task_list = state_update["layer3_memory"]["task_registry"]["main_agent"]
        active_task = next(t for t in new_task_list if t.get("status") == "active")
        
        # 检查 reasoning_notes 而不是 reasoning
        notes = active_task.get("reasoning_notes", [])
        assert len(notes) >= 1
        assert any("用户情绪比较焦虑" in n.get("content", "") for n in notes)
    
    def test_append_note_to_specific_task(self, state_with_tasks):
        """追加笔记到指定任务（非活跃）"""
        state = state_with_tasks
        
        state_update, result_json = append_task_note_impl(
            state, "补充：用户喜欢幽默风格", "写开场白", "main_agent"
        )
        result = json.loads(result_json)
        
        assert result["success"] is True
        
        # 验证笔记追加到了 B
        new_task_list = state_update["layer3_memory"]["task_registry"]["main_agent"]
        task_b = next(t for t in new_task_list if t["task_id"] == "写开场白")
        
        notes = task_b.get("reasoning_notes", [])
        assert any("用户喜欢幽默风格" in n.get("content", "") for n in notes)
        assert len(notes) == 3  # 原有 2 条 + 新增 1 条
    
    def test_append_note_to_nonexistent_task_fails(self, state_with_tasks):
        """追加笔记到不存在的任务应失败"""
        state = state_with_tasks
        
        state_update, result_json = append_task_note_impl(
            state, "一些笔记", "不存在的任务", "main_agent"
        )
        result = json.loads(result_json)
        
        assert result["success"] is False
        assert "不存在" in result["error"]
    
    def test_append_note_without_active_task_fails(self, empty_state):
        """没有活跃任务时追加笔记（不指定 task_id）应失败"""
        state = empty_state
        
        state_update, result_json = append_task_note_impl(
            state, "一些笔记", None, "main_agent"
        )
        result = json.loads(result_json)
        
        assert result["success"] is False
        assert "没有活跃任务" in result["error"]


# ============================================================
# Test: 任务列表格式化
# ============================================================

class TestTaskIndexFormat:
    """测试任务列表格式化"""
    
    def test_format_task_index(self, state_with_tasks):
        """验证任务列表格式正确"""
        state = state_with_tasks
        task_list = get_task_list_for_agent(state, "main_agent")
        
        task_index = format_task_index(task_list)
        
        # 验证新版分区格式
        assert "## 任务列表" in task_index
        assert "### 当前任务" in task_index
        assert "### 其他任务" in task_index
        assert "| title | status | summary |" in task_index
        # 验证活跃标记
        assert "[active]" in task_index
    
    def test_format_empty_task_list(self):
        """空任务列表应返回提示"""
        task_index = format_task_index([])
        assert "暂无任务记录" in task_index


# ============================================================
# Test: 活跃任务信息格式化
# ============================================================

class TestActiveTaskPayload:
    """测试活跃任务信息格式化"""
    
    def test_format_active_task_payload(self, state_with_tasks):
        """验证活跃任务信息格式正确"""
        state = state_with_tasks
        task_list = get_task_list_for_agent(state, "main_agent")
        active_task = get_active_task(task_list)
        
        payload = format_active_task_payload(active_task)
        
        assert payload["task_id"] == "分析crush态度"
        assert "分析 crush 对用户的态度" in payload["summary"]
        assert isinstance(payload["reasoning_notes"], list)
        assert isinstance(payload["bound_contexts"], list)
    
    def test_format_none_active_task(self):
        """无活跃任务时返回空信息"""
        payload = format_active_task_payload(None)
        
        assert payload["task_id"] == ""
        assert payload["reasoning_notes"] == []
        assert payload["bound_contexts"] == []


# ============================================================
# Test: 上下文注入
# ============================================================

class TestContextInjection:
    """测试上下文构建器的任务信息注入"""
    
    def test_context_dict_contains_task_fields(self, state_with_tasks):
        """验证上下文字典包含任务相关字段"""
        state = state_with_tasks
        
        context = build_context_dict(state, target_agent="main_agent")
        
        assert "task_index" in context
        assert "active_task_payload" in context
        
        # task_index 应包含任务列表
        assert "分析crush态度" in context["task_index"]
        assert "写开场白" in context["task_index"]
        
        # active_task_payload 应是 JSON 字符串
        payload = json.loads(context["active_task_payload"])
        assert payload["task_id"] == "分析crush态度"


# ============================================================
# Test: 工具识别
# ============================================================

class TestToolIdentification:
    """测试工具识别函数"""
    
    def test_is_task_tool(self):
        """验证任务工具识别"""
        assert is_task_tool("switch_task") is True
        assert is_task_tool("create_task") is True
        assert is_task_tool("append_task_note") is True
        assert is_task_tool("complete_task") is True
        assert is_task_tool("bind_context") is True
        assert is_task_tool("unbind_context") is True
        assert is_task_tool("refresh_context") is True
        
        assert is_task_tool("load_inquiry_skill_instructions") is False
        assert is_task_tool("") is False
    
    def test_task_tool_names_constant(self):
        """验证工具名称常量"""
        assert "switch_task" in TASK_TOOL_NAMES
        assert "create_task" in TASK_TOOL_NAMES
        assert "append_task_note" in TASK_TOOL_NAMES
        assert "complete_task" in TASK_TOOL_NAMES
        assert "bind_context" in TASK_TOOL_NAMES
        assert "unbind_context" in TASK_TOOL_NAMES
        assert "refresh_context" in TASK_TOOL_NAMES


# ============================================================
# Test: 状态更新应用
# ============================================================

class TestApplyStateUpdate:
    """测试状态更新应用函数"""
    
    def test_apply_switch_task_update(self, state_with_tasks):
        """验证 switch_task 状态更新"""
        state = state_with_tasks
        
        update = apply_task_tool_state_update(
            state, "switch_task", {"task_id": "写开场白"}, "main_agent"
        )
        
        assert "layer3_memory" in update
        task_list = update["layer3_memory"]["task_registry"]["main_agent"]
        active_task = next(t for t in task_list if t.get("status") == "active")
        assert active_task["task_id"] == "写开场白"
    
    def test_apply_create_task_update(self, state_with_tasks):
        """验证 create_task 状态更新"""
        state = state_with_tasks
        
        update = apply_task_tool_state_update(
            state, "create_task", {"task_id": "新任务", "title": "新任务", "summary": "新任务摘要"}, "main_agent"
        )
        
        assert "layer3_memory" in update
        task_list = update["layer3_memory"]["task_registry"]["main_agent"]
        assert any(t["task_id"] == "新任务" for t in task_list)
    
    def test_apply_append_note_update(self, state_with_tasks):
        """验证 append_task_note 状态更新"""
        state = state_with_tasks
        
        update = apply_task_tool_state_update(
            state, "append_task_note", {"note": "测试笔记"}, "main_agent"
        )
        
        assert "layer3_memory" in update


# ============================================================
# Test: 唯一活跃任务保证
# ============================================================

class TestSingleActiveTask:
    """测试任意时刻只有一个活跃任务"""
    
    def test_only_one_active_after_switch(self, state_with_tasks):
        """切换后只有一个活跃任务"""
        state = state_with_tasks
        
        # 多次切换
        state_update, _ = switch_task_impl(state, "写开场白", "main_agent")
        task_list = state_update["layer3_memory"]["task_registry"]["main_agent"]
        
        active_count = sum(1 for t in task_list if t.get("status") == "active")
        assert active_count == 1
        
        # 再次切换
        state["layer3_memory"] = state_update["layer3_memory"]
        state_update2, _ = switch_task_impl(state, "约会规划", "main_agent")
        task_list2 = state_update2["layer3_memory"]["task_registry"]["main_agent"]
        
        active_count2 = sum(1 for t in task_list2 if t.get("status") == "active")
        assert active_count2 == 1
    
    def test_only_one_active_after_create(self, state_with_tasks):
        """创建新任务后只有一个活跃任务"""
        state = state_with_tasks
        
        state_update, _ = create_task_impl(state, "新任务1", "新任务1", "摘要1", "main_agent")
        task_list = state_update["layer3_memory"]["task_registry"]["main_agent"]
        
        active_count = sum(1 for t in task_list if t.get("status") == "active")
        assert active_count == 1
        
        # 创建更多任务
        state["layer3_memory"] = state_update["layer3_memory"]
        state_update2, _ = create_task_impl(state, "新任务2", "新任务2", "摘要2", "main_agent")
        task_list2 = state_update2["layer3_memory"]["task_registry"]["main_agent"]
        
        active_count2 = sum(1 for t in task_list2 if t.get("status") == "active")
        assert active_count2 == 1
