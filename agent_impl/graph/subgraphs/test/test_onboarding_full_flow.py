"""
测试 Onboarding 完整流程

验证从新用户首次输入到完成 onboarding 的完整流程：
1. Router 检测新用户，路由到 onboarding
2. Onboarding 子图收集信息或提问
3. 信息充足后生成 handoff
4. Router 检测 onboarding 完成，路由到 main_agent
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_IMPL_DIR = os.path.join(ROOT_DIR, "agent_impl")
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if AGENT_IMPL_DIR not in sys.path:
    sys.path.insert(0, AGENT_IMPL_DIR)

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver

from graph.workflow import compile_workflow

load_dotenv()

print("=" * 80)
print("测试：Onboarding 完整流程")
print("=" * 80)


def test_onboarding_first_turn():
    """
    测试首次进入 onboarding 的流程
    """
    print("\n" + "=" * 80)
    print("【测试 1：首次用户输入】")
    print("=" * 80)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "test_onboarding_flow"}}
    user_input = "你好，我是新用户"

    print(f"  用户输入: {user_input}")

    state_input = {
        "messages": [],
        "layer2_memory": {},
        "layer3_memory": {},
        "pending_responses": [],
        "runtime": {},
        "tool_patch_log": [],
        "user_message": user_input,
    }

    result = app.invoke(state_input, config=config)

    print(f"\n  路由决策: {result.get('route_to', 'unknown')}")
    print(f"  Onboarding 完成: {result.get('onboarding_completed', False)}")

    if result.get("onboarding_completed"):
        print(f"  ✅ Onboarding 在首次输入即完成")
        print(f"  Handoff 建议: {result.get('onboarding_handoff', {}).get('suggested_action', 'N/A')}")
    else:
        print(f"  ⏳ Onboarding 需要更多信息")
        inquiry_card = result.get("inquiry_card")
        if inquiry_card:
            questions = inquiry_card.get("questions", [])
            if questions:
                print(f"  问题: {questions[0].get('question', 'N/A')}")

    return result, config


def test_onboarding_second_turn(first_result, first_config):
    """
    测试第二轮对话，继续 onboarding
    """
    print("\n" + "=" * 80)
    print("【测试 2：第二轮对话】")
    print("=" * 80)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    user_input = "我是男生，22岁，喜欢一个女生"

    print(f"  用户输入: {user_input}")

    state_input = {
        "messages": first_result.get("messages", []),
        "collected_info": first_result.get("collected_info", {}),
        "onboarding_turn_count": first_result.get("onboarding_turn_count", 0),
        "last_onboarding_question": first_result.get("last_onboarding_question"),
        "onboarding_completed": first_result.get("onboarding_completed", False),
        "onboarding_max_turns": 3,
        "layer2_memory": {},
        "layer3_memory": {},
        "pending_responses": [],
        "runtime": {},
        "tool_patch_log": [],
        "user_message": user_input,
    }

    result = app.invoke(state_input, config=first_config)

    print(f"\n  路由决策: {result.get('route_to', 'unknown')}")
    print(f"  Onboarding 完成: {result.get('onboarding_completed', False)}")

    if result.get("onboarding_completed"):
        print(f"  ✅ Onboarding 在第二轮完成")
        handoff = result.get("onboarding_handoff", {})
        print(f"  Handoff 建议: {handoff.get('suggested_action', 'N/A')}")
        print(f"  Handoff 理由: {handoff.get('reason', 'N/A')}")
        preliminary = result.get("preliminary_assessment")
        if preliminary:
            print(f"  局势初判: {preliminary.get('verdict', 'N/A')}")
    else:
        print(f"  ⏳ Onboarding 仍需更多信息")
        inquiry_card = result.get("inquiry_card")
        if inquiry_card:
            questions = inquiry_card.get("questions", [])
            if questions:
                print(f"  问题: {questions[0].get('question', 'N/A')}")

    return result, first_config


def test_onboarding_third_turn(second_result, config):
    """
    测试第三轮对话，应该完成 onboarding
    """
    print("\n" + "=" * 80)
    print("【测试 3：第三轮对话（应完成）】")
    print("=" * 80)

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    user_input = "她是我同事，每天一起吃午饭，但我不知道她对我有没有意思"

    print(f"  用户输入: {user_input}")

    state_input = {
        "messages": second_result.get("messages", []),
        "collected_info": second_result.get("collected_info", {}),
        "onboarding_turn_count": second_result.get("onboarding_turn_count", 0),
        "last_onboarding_question": second_result.get("last_onboarding_question"),
        "onboarding_completed": second_result.get("onboarding_completed", False),
        "onboarding_max_turns": 3,
        "layer2_memory": {},
        "layer3_memory": {},
        "pending_responses": [],
        "runtime": {},
        "tool_patch_log": [],
        "user_message": user_input,
    }

    result = app.invoke(state_input, config=config)

    print(f"\n  路由决策: {result.get('route_to', 'unknown')}")
    print(f"  Onboarding 完成: {result.get('onboarding_completed', False)}")

    if result.get("onboarding_completed"):
        print(f"  ✅ Onboarding 已完成")
        handoff = result.get("onboarding_handoff", {})
        print(f"  Handoff 建议: {handoff.get('suggested_action', 'N/A')}")
        print(f"  Handoff 理由: {handoff.get('reason', 'N/A')}")
        preliminary = result.get("preliminary_assessment")
        if preliminary:
            print(f"  局势初判: {preliminary.get('verdict', 'N/A')}")
            print(f"  证据: {preliminary.get('evidence', 'N/A')[:50]}...")
    else:
        print(f"  ⚠️ Onboarding 仍未完成（可能需要更多轮次）")

    return result, config


def test_post_onboarding_handoff(onboarding_result, config):
    """
    测试 onboarding 完成后的 handoff 流程
    """
    print("\n" + "=" * 80)
    print("【测试 4：Onboarding 完成后的 Handoff】")
    print("=" * 80)

    if not onboarding_result.get("onboarding_completed"):
        print("  ⚠️ Onboarding 未完成，跳过 handoff 测试")
        return onboarding_result, config

    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)

    user_input = "那我现在该怎么办？"

    print(f"  用户输入: {user_input}")

    state_input = {
        "messages": onboarding_result.get("messages", []),
        "collected_info": onboarding_result.get("collected_info", {}),
        "onboarding_completed": True,
        "onboarding_handoff": onboarding_result.get("onboarding_handoff"),
        "layer2_memory": onboarding_result.get("layer2_memory", {}),
        "layer3_memory": onboarding_result.get("layer3_memory", {}),
        "pending_responses": [],
        "runtime": {},
        "tool_patch_log": [],
        "user_message": user_input,
    }

    result = app.invoke(state_input, config=config)

    print(f"\n  路由决策: {result.get('route_to', 'unknown')}")
    print(f"  是否有 pending_responses: {bool(result.get('pending_responses'))}")

    pending = result.get("pending_responses", [])
    if pending:
        print(f"  回复来源: {[p.get('from', 'unknown') for p in pending]}")

    handoff_from_state = result.get("onboarding_handoff")
    if handoff_from_state:
        print(f"  Handoff 已传递: {handoff_from_state.get('suggested_action', 'N/A')}")

    return result, config


def main():
    try:
        first_result, first_config = test_onboarding_first_turn()
        second_result, second_config = test_onboarding_second_turn(first_result, first_config)
        third_result, third_config = test_onboarding_third_turn(second_result, second_config)

        if third_result.get("onboarding_completed"):
            post_result, _ = test_post_onboarding_handoff(third_result, third_config)

        print("\n" + "=" * 80)
        print("测试完成")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
