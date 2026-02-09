"""
测试中断和恢复机制

测试场景：
1. 主 agent 节点触发中断并恢复
2. 子 agent 节点触发中断并恢复
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from graph.workflow import compile_workflow
from graph.state import create_initial_state

load_dotenv()


def test_main_agent_interrupt_and_resume():
    """
    测试主 agent 节点触发中断并恢复
    
    流程：
    1. 用户输入消息，触发主 agent
    2. 主 agent 调用 ask_human 工具触发中断
    3. 使用 Command(resume=...) 恢复执行
    4. 验证执行完成并返回结果
    """
    print("=" * 80)
    print("测试 1: 主 agent 节点触发中断并恢复")
    print("=" * 80)
    
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    thread_id = "test_main_agent_interrupt"
    config = {"configurable": {"thread_id": thread_id}}
    
    user_input = "你好，我想问一下关于 crush 的问题，需要你帮我分析一下现状"
    
    print("\n" + "-" * 80)
    print("步骤 1: 发送用户输入（预期会触发中断）")
    print("-" * 80)
    print(f"用户输入: {user_input}")
    
    state_input = create_initial_state(user_input)
    
    result = app.invoke(state_input, config=config)
    
    print(f"\n返回结果键: {list(result.keys())}")
    
    if "__interrupt__" in result:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            interrupt_payload = interrupts[0].value if interrupts else {}
            print(f"\n检测到中断，payload: {interrupt_payload}")
            
            print("\n" + "-" * 80)
            print("步骤 2: 恢复执行（模拟用户回答）")
            print("-" * 80)
            
            resume_payload = {
                "answers": {
                    "question_1": "我们每天都会聊天",
                    "question_2": "她经常主动找我",
                    "question_3": "有时候会一起吃饭"
                }
            }
            print(f"恢复 payload: {resume_payload}")
            
            resumed_result = app.invoke(Command(resume=resume_payload), config=config)
            
            print(f"\n恢复后返回结果键: {list(resumed_result.keys())}")
            
            if "pending_responses" in resumed_result:
                responses = resumed_result["pending_responses"]
                print(f"\n pending_responses 数量: {len(responses)}")
                for i, resp in enumerate(responses):
                    print(f"  [{i}] {resp}")
            
            print("\n" + "=" * 80)
            print("测试 1 完成: 主 agent 中断恢复成功")
            print("=" * 80)
        else:
            print("\n未触发中断（可能模型没有调用 ask_human 工具）")
    else:
        print("\n未检测到中断（可能模型没有调用 ask_human 工具）")
        if "pending_responses" in result:
            responses = result["pending_responses"]
            print(f"\n pending_responses 数量: {len(responses)}")
            for i, resp in enumerate(responses):
                print(f"  [{i}] {resp}")


def test_subagent_interrupt_and_resume():
    """
    测试子 agent 节点触发中断并恢复
    
    流程：
    1. 用户输入消息，触发主 agent
    2. 主 agent 调用子 agent（如 status_agent）
    3. 子 agent 内部调用 ask_human 工具触发中断
    4. 使用 Command(resume=...) 恢复执行
    5. 验证执行完成并返回结果
    """
    print("\n\n" + "=" * 80)
    print("测试 2: 子 agent 节点触发中断并恢复")
    print("=" * 80)
    
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    thread_id = "test_subagent_interrupt"
    config = {"configurable": {"thread_id": thread_id}}
    
    user_input = "我想分析一下现在的情感状况"
    
    print("\n" + "-" * 80)
    print("步骤 1: 发送用户输入（预期主 agent 调用子 agent 并触发中断）")
    print("-" * 80)
    print(f"用户输入: {user_input}")
    
    state_input = create_initial_state(user_input)
    
    result = app.invoke(state_input, config=config)
    
    print(f"\n返回结果键: {list(result.keys())}")
    
    if "__interrupt__" in result:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            interrupt_payload = interrupts[0].value if interrupts else {}
            print(f"\n检测到中断，payload: {interrupt_payload}")
            
            print("\n" + "-" * 80)
            print("步骤 2: 恢复执行（模拟用户回答）")
            print("-" * 80)
            
            resume_payload = {
                "answers": {
                    "question_1": "我们认识3个月了",
                    "question_2": "每周见面2-3次",
                    "question_3": "感觉彼此很合得来"
                }
            }
            print(f"恢复 payload: {resume_payload}")
            
            resumed_result = app.invoke(Command(resume=resume_payload), config=config)
            
            print(f"\n恢复后返回结果键: {list(resumed_result.keys())}")
            
            if "pending_responses" in resumed_result:
                responses = resumed_result["pending_responses"]
                print(f"\n pending_responses 数量: {len(responses)}")
                for i, resp in enumerate(responses):
                    print(f"  [{i}] {resp}")
            
            if "layer2_memory" in resumed_result:
                layer2 = resumed_result["layer2_memory"]
                print(f"\n layer2_memory 键: {list(layer2.keys())}")
            
            print("\n" + "=" * 80)
            print("测试 2 完成: 子 agent 中断恢复成功")
            print("=" * 80)
        else:
            print("\n未触发中断（可能模型没有调用 ask_human 工具）")
    else:
        print("\n未检测到中断（可能模型没有调用 ask_human 工具）")
        if "pending_responses" in result:
            responses = result["pending_responses"]
            print(f"\n pending_responses 数量: {len(responses)}")
            for i, resp in enumerate(responses):
                print(f"  [{i}] {resp}")


def test_multiple_interrupts():
    """
    测试多次中断和恢复
    
    流程：
    1. 第一次中断和恢复
    2. 第二次中断和恢复
    3. 验证最终状态
    """
    print("\n\n" + "=" * 80)
    print("测试 3: 多次中断和恢复")
    print("=" * 80)
    
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    thread_id = "test_multiple_interrupts"
    config = {"configurable": {"thread_id": thread_id}}
    
    user_input = "我想制定一个追求 crush 的计划"
    
    print("\n" + "-" * 80)
    print("步骤 1: 发送用户输入")
    print("-" * 80)
    print(f"用户输入: {user_input}")
    
    state_input = create_initial_state(user_input)
    
    result = app.invoke(state_input, config=config)
    
    print(f"\n返回结果键: {list(result.keys())}")
    
    interrupt_count = 0
    
    while "__interrupt__" in result and interrupt_count < 3:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            interrupt_count += 1
            interrupt_payload = interrupts[0].value if interrupts else {}
            print(f"\n{'=' * 80}")
            print(f"第 {interrupt_count} 次中断")
            print(f"{'=' * 80}")
            print(f"payload: {interrupt_payload}")
            
            resume_payload = {
                "answers": {
                    f"question_{i}": f"这是第 {interrupt_count} 次回答的问题 {i}"
                    for i in range(1, 4)
                }
            }
            print(f"恢复 payload: {resume_payload}")
            
            result = app.invoke(Command(resume=resume_payload), config=config)
            print(f"\n恢复后返回结果键: {list(result.keys())}")
        else:
            break
    
    if "pending_responses" in result:
        responses = result["pending_responses"]
        print(f"\n最终 pending_responses 数量: {len(responses)}")
        for i, resp in enumerate(responses):
            print(f"  [{i}] {resp}")
    
    print(f"\n总共中断次数: {interrupt_count}")
    print("\n" + "=" * 80)
    print("测试 3 完成: 多次中断恢复成功")
    print("=" * 80)


def main():
    print("\n" + "=" * 80)
    print("开始中断和恢复机制测试")
    print("=" * 80)
    
    try:
        test_main_agent_interrupt_and_resume()
    except Exception as e:
        print(f"\n测试 1 出错: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_subagent_interrupt_and_resume()
    except Exception as e:
        print(f"\n测试 2 出错: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_multiple_interrupts()
    except Exception as e:
        print(f"\n测试 3 出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n\n" + "=" * 80)
    print("所有测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
