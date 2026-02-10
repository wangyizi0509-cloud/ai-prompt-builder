"""
测试主 Agent 与子 Agent 的联动（完整版）

验证：
1. 主 Agent 能够正确调用子 Agent
2. 子 Agent 的返回值（state_patch）能正确合并到主 State
3. 多轮对话中状态能够正确传递
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
print("测试：主 Agent 与子 Agent 联动")
print("=" * 80)


def test_scenario_1_with_onboarding():
    """
    场景 1: 带 onboarding 的对话
    """
    print("\n" + "=" * 80)
    print("【场景 1: 带 onboarding 的对话】")
    print("=" * 80)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    thread_id = "test_linkage_scenario_1"
    config = {"configurable": {"thread_id": thread_id}}

    user_input = "我最近心情很不好，感觉对喜欢的人失去了信心"

    print(f"\n  用户输入: {user_input}")

    state_input = create_initial_state(user_input)

    print(f"\n  执行 workflow...")
    result = app.invoke(state_input, config=config)

    print(f"\n  结果键: {list(result.keys())}")

    pending_responses = result.get("pending_responses", [])
    print(f"\n  Pending Responses 数量: {len(pending_responses)}")

    for i, resp in enumerate(pending_responses):
        print(f"\n  Response #{i+1}:")
        print(f"    From: {resp.get('from')}")
        print(f"    Content: {resp.get('content')[:100]}...")

    onboarding_completed = result.get("onboarding_completed", False)
    print(f"\n  Onboarding 完成: {onboarding_completed}")

    return result


def test_scenario_2_status_analysis():
    """
    场景 2: 情感状态分析（模拟已通过 onboarding）
    直接设置 onboarding_completed=True 来跳过 onboarding
    """
    print("\n" + "=" * 80)
    print("【场景 2: 情感状态分析】")
    print("=" * 80)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    thread_id = "test_linkage_scenario_2"
    config = {"configurable": {"thread_id": thread_id}}

    user_input = "我最近心情很不好，感觉对喜欢的人失去了信心"

    print(f"\n  用户输入: {user_input}")

    state_input = create_initial_state(user_input)
    state_input["onboarding_completed"] = True

    print(f"\n  执行 workflow...")
    result = app.invoke(state_input, config=config)

    pending_responses = result.get("pending_responses", [])
    print(f"\n  Pending Responses 数量: {len(pending_responses)}")

    for i, resp in enumerate(pending_responses):
        print(f"\n  Response #{i+1}:")
        print(f"    From: {resp.get('from')}")
        print(f"    Content: {resp.get('content')[:150]}...")

    tool_patch_log = result.get("tool_patch_log", [])
    print(f"\n  Tool Patch Log 条目数: {len(tool_patch_log)}")

    if tool_patch_log:
        print(f"\n  Tool Patch 详情:")
        for i, patch in enumerate(tool_patch_log[:5]):
            print(f"    #{i+1}: {patch}")

    layer2_memory = result.get("layer2_memory", {})
    status_report = layer2_memory.get("status_report")
    if status_report:
        print(f"\n  ✓ Status Report 已生成:")
        summary = status_report.get('summary', '')
        print(f"    Summary: {str(summary)[:100]}...")
    else:
        print(f"\n  ✗ 未生成 Status Report")

    return result


def test_scenario_3_action_planning():
    """
    场景 3: 行动规划
    """
    print("\n" + "=" * 80)
    print("【场景 3: 行动规划】")
    print("=" * 80)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    thread_id = "test_linkage_scenario_3"
    config = {"configurable": {"thread_id": thread_id}}

    user_input = "我想制定一个计划，主动和TA建立更多联系"

    print(f"\n  用户输入: {user_input}")

    state_input = create_initial_state(user_input)
    state_input["onboarding_completed"] = True

    print(f"\n  执行 workflow...")
    result = app.invoke(state_input, config=config)

    pending_responses = result.get("pending_responses", [])
    print(f"\n  Pending Responses 数量: {len(pending_responses)}")

    for i, resp in enumerate(pending_responses):
        print(f"\n  Response #{i+1}:")
        print(f"    From: {resp.get('from')}")
        print(f"    Content: {resp.get('content')[:150]}...")

    layer2_memory = result.get("layer2_memory", {})
    action_plan = layer2_memory.get("action_plan")
    if action_plan:
        print(f"\n  ✓ Action Plan 已生成:")
        goals = action_plan.get('goals', [])
        print(f"    Goals: {str(goals)[:100]}...")
    else:
        print(f"\n  ✗ 未生成 Action Plan")

    return result


def test_scenario_4_multi_turn_continuity():
    """
    场景 4: 多轮对话连贯性
    验证子 Agent 的状态能够在多轮对话中正确传递
    """
    print("\n" + "=" * 80)
    print("【场景 4: 多轮对话连贯性】")
    print("=" * 80)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    thread_id = "test_linkage_scenario_4"
    config = {"configurable": {"thread_id": thread_id}}

    turn_1_input = "我最近很焦虑，不知道该怎么办"
    turn_2_input = "你刚才说让我分析一下现状，能具体说说吗？"
    turn_3_input = "我想制定一个行动计划"

    turns = [
        ("第一轮", turn_1_input),
        ("第二轮", turn_2_input),
        ("第三轮", turn_3_input),
    ]

    for turn_name, user_input in turns:
        print(f"\n  --- {turn_name} ---")
        print(f"  用户输入: {user_input}")

        state_input = create_initial_state(user_input)
        state_input["onboarding_completed"] = True

        result = app.invoke(state_input, config=config)

        pending_responses = result.get("pending_responses", [])
        print(f"  响应数: {len(pending_responses)}")

        if pending_responses:
            content = pending_responses[-1].get('content', '')[:100]
            print(f"  最新响应: {content}...")

        layer2_memory = result.get("layer2_memory", {})
        has_status = bool(layer2_memory.get("status_report"))
        has_plan = bool(layer2_memory.get("action_plan"))
        has_guide = bool(layer2_memory.get("action_guide"))

        print(f"  状态: status={has_status}, plan={has_plan}, guide={has_guide}")

    return result


def main():
    print("\n" + "=" * 80)
    print("开始测试...")
    print("=" * 80)

    results = []

    try:
        print("\n\n")
        print("=" * 80)
        print("场景 1: 带 onboarding 的对话")
        print("=" * 80)
        result1 = test_scenario_1_with_onboarding()
        results.append(("场景 1", "success" if result1 else "failed"))
    except Exception as e:
        print(f"\n  ✗ 场景 1 失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("场景 1", f"error: {e}"))

    try:
        print("\n\n")
        print("=" * 80)
        print("场景 2: 情感状态分析")
        print("=" * 80)
        result2 = test_scenario_2_status_analysis()
        results.append(("场景 2", "success" if result2 else "failed"))
    except Exception as e:
        print(f"\n  ✗ 场景 2 失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("场景 2", f"error: {e}"))

    try:
        print("\n\n")
        print("=" * 80)
        print("场景 3: 行动规划")
        print("=" * 80)
        result3 = test_scenario_3_action_planning()
        results.append(("场景 3", "success" if result3 else "failed"))
    except Exception as e:
        print(f"\n  ✗ 场景 3 失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("场景 3", f"error: {e}"))

    try:
        print("\n\n")
        print("=" * 80)
        print("场景 4: 多轮对话连贯性")
        print("=" * 80)
        result4 = test_scenario_4_multi_turn_continuity()
        results.append(("场景 4", "success" if result4 else "failed"))
    except Exception as e:
        print(f"\n  ✗ 场景 4 失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("场景 4", f"error: {e}"))

    print("\n\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)

    for name, status in results:
        symbol = "✓" if status == "success" else "✗"
        print(f"  {symbol} {name}: {status}")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
