"""
测试三个子 Agent 的调用
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent_impl'))

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver

from graph.workflow import compile_workflow
from graph.state import create_initial_state

load_dotenv()

print("=" * 80)
print("测试：三个子 Agent (Status/Plan/Guide) 的调用")
print("=" * 80)


def test_status_agent():
    """
    测试 Status Agent：情感状态分析
    使用更明确的触发词来调用 status agent
    """
    print("\n" + "=" * 80)
    print("【测试 Status Agent】")
    print("=" * 80)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    thread_id = "test_status_agent"
    config = {"configurable": {"thread_id": thread_id}}

    user_input = "请帮我分析一下我的情感状态，我现在感觉很迷茫，不知道TA对我到底是什么意思"

    print(f"\n  用户输入: {user_input}")

    state_input = create_initial_state(user_input)
    state_input["onboarding_completed"] = True

    print(f"\n  执行 workflow...")
    result = app.invoke(state_input, config=config)

    tool_patch_log = result.get("tool_patch_log", [])
    print(f"\n  Tool Patch Log 条目数: {len(tool_patch_log)}")

    if tool_patch_log:
        print(f"\n  Tool Patch 详情:")
        for i, patch in enumerate(tool_patch_log):
            print(f"    #{i+1}: {patch}")

    layer2_memory = result.get("layer2_memory", {})
    status_report = layer2_memory.get("status_report")
    if status_report:
        print(f"\n  ✓ Status Report 已生成:")
        print(f"    Summary: {str(status_report.get('summary', ''))[:200]}...")
        return True
    else:
        print(f"\n  ✗ 未生成 Status Report")
        return False


def test_plan_agent():
    """
    测试 Plan Agent：行动规划
    """
    print("\n" + "=" * 80)
    print("【测试 Plan Agent】")
    print("=" * 80)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    thread_id = "test_plan_agent"
    config = {"configurable": {"thread_id": thread_id}}

    user_input = "我想制定一个详细的行动计划，帮我分析应该怎么做才能和TA建立更好的关系"

    print(f"\n  用户输入: {user_input}")

    state_input = create_initial_state(user_input)
    state_input["onboarding_completed"] = True

    print(f"\n  执行 workflow...")
    result = app.invoke(state_input, config=config)

    tool_patch_log = result.get("tool_patch_log", [])
    print(f"\n  Tool Patch Log 条目数: {len(tool_patch_log)}")

    if tool_patch_log:
        print(f"\n  Tool Patch 详情:")
        for i, patch in enumerate(tool_patch_log):
            print(f"    #{i+1}: {patch}")

    layer2_memory = result.get("layer2_memory", {})
    action_plan = layer2_memory.get("action_plan")
    if action_plan:
        print(f"\n  ✓ Action Plan 已生成:")
        goals = action_plan.get('goals', [])
        print(f"    Goals: {str(goals)[:200]}...")
        return True
    else:
        print(f"\n  ✗ 未生成 Action Plan")
        return False


def test_guide_agent():
    """
    测试 Guide Agent：分步指导
    """
    print("\n" + "=" * 80)
    print("【测试 Guide Agent】")
    print("=" * 80)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    thread_id = "test_guide_agent"
    config = {"configurable": {"thread_id": thread_id}}

    user_input = "我想知道具体该怎么和TA聊天，给我一些具体的聊天技巧和话术指导"

    print(f"\n  用户输入: {user_input}")

    state_input = create_initial_state(user_input)
    state_input["onboarding_completed"] = True

    print(f"\n  执行 workflow...")
    result = app.invoke(state_input, config=config)

    tool_patch_log = result.get("tool_patch_log", [])
    print(f"\n  Tool Patch Log 条目数: {len(tool_patch_log)}")

    if tool_patch_log:
        print(f"\n  Tool Patch 详情:")
        for i, patch in enumerate(tool_patch_log):
            print(f"    #{i+1}: {patch}")

    layer2_memory = result.get("layer2_memory", {})
    action_guide = layer2_memory.get("action_guide")
    if action_guide:
        print(f"\n  ✓ Action Guide 已生成:")
        print(f"    Content: {str(action_guide)[:200]}...")
        return True
    else:
        print(f"\n  ✗ 未生成 Action Guide")
        return False


def main():
    print("\n" + "=" * 80)
    print("开始测试三个子 Agent...")
    print("=" * 80)

    results = []

    try:
        result1 = test_status_agent()
        results.append(("Status Agent", result1))
    except Exception as e:
        print(f"\n  ✗ Status Agent 测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Status Agent", f"error: {e}"))

    try:
        result2 = test_plan_agent()
        results.append(("Plan Agent", result2))
    except Exception as e:
        print(f"\n  ✗ Plan Agent 测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Plan Agent", f"error: {e}"))

    try:
        result3 = test_guide_agent()
        results.append(("Guide Agent", result3))
    except Exception as e:
        print(f"\n  ✗ Guide Agent 测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Guide Agent", f"error: {e}"))

    print("\n\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)

    for name, status in results:
        symbol = "✓" if status is True else "✗"
        print(f"  {symbol} {name}: {status}")

    success_count = sum(1 for _, s in results if s is True)
    print(f"\n  成功调用子 Agent 数量: {success_count}/3")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
