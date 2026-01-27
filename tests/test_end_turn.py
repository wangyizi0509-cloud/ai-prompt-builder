"""
end_turn 工具单元测试
"""

import json
import sys
import os

# 添加 agent_impl 到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent_impl"))

from graph.tools.delegate_tools import end_turn
from graph.workflow import route_after_skill_tools


def test_end_turn_tool_returns_correct_action():
    """测试 end_turn 工具返回正确的 action"""
    result = end_turn.invoke({"reason": ""})
    data = json.loads(result)
    
    assert data["action"] == "end_turn", f"Expected action='end_turn', got {data['action']}"
    assert data["reason"] == "", f"Expected empty reason, got {data['reason']}"
    print("✓ test_end_turn_tool_returns_correct_action passed")


def test_end_turn_tool_with_reason():
    """测试 end_turn 工具带 reason 参数"""
    reason = "子 Agent 已完整说明，无需重复"
    result = end_turn.invoke({"reason": reason})
    data = json.loads(result)
    
    assert data["action"] == "end_turn", f"Expected action='end_turn', got {data['action']}"
    assert data["reason"] == reason, f"Expected reason='{reason}', got {data['reason']}"
    print("✓ test_end_turn_tool_with_reason passed")


def test_route_after_skill_tools_detects_end_turn():
    """测试 route_after_skill_tools 能检测 _end_turn 标记"""
    state = {
        "_end_turn": True,
        "_iteration_count": 1,
    }
    
    result = route_after_skill_tools(state)
    
    assert result == "end", f"Expected 'end', got '{result}'"
    print("✓ test_route_after_skill_tools_detects_end_turn passed")


def test_route_after_skill_tools_without_end_turn():
    """测试没有 _end_turn 标记时正常路由"""
    state = {
        "_end_turn": False,
        "_iteration_count": 1,
        "current_agent": "main_agent",
    }
    
    result = route_after_skill_tools(state)
    
    # 没有其他特殊标记，应该返回 current_agent
    assert result == "main_agent", f"Expected 'main_agent', got '{result}'"
    print("✓ test_route_after_skill_tools_without_end_turn passed")


def test_route_end_turn_priority_over_other_flags():
    """测试 _end_turn 优先级高于其他标记"""
    state = {
        "_end_turn": True,
        "_pending_action": "ask",  # 这个标记正常会返回 current_agent
        "_iteration_count": 1,
        "current_agent": "main_agent",
    }
    
    result = route_after_skill_tools(state)
    
    # _end_turn 应该优先，直接返回 "end"
    assert result == "end", f"Expected 'end' (end_turn priority), got '{result}'"
    print("✓ test_route_end_turn_priority_over_other_flags passed")


if __name__ == "__main__":
    print("\n=== Running end_turn tests ===\n")
    
    test_end_turn_tool_returns_correct_action()
    test_end_turn_tool_with_reason()
    test_route_after_skill_tools_detects_end_turn()
    test_route_after_skill_tools_without_end_turn()
    test_route_end_turn_priority_over_other_flags()
    
    print("\n=== All tests passed! ===\n")
