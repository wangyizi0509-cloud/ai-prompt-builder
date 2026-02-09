"""
测试主 agent 的中断、resume 和多轮思考
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from graph.workflow import compile_workflow
from graph.state import convert_message_to_dict
from utils.reasoning_content import extract_reasoning_content

load_dotenv()

print("=" * 80)
print("测试：主 Agent 中断 + Resume + 多轮思考")
print("=" * 80)


def main():
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    config = {"configurable": {"thread_id": "test_interrupt_reasoning"}}
    
    # 第一轮：触发中断（通过调用子 agent）
    print("\n【第一轮：触发中断】")
    user_input1 = "我想分析一下我目前的感情状况，最近有些迷茫"
    
    state_input1 = {
        "messages": [],
        "layer2_memory": {"user_profile": {"name": "测试用户"}},
        "layer3_memory": {"all_messages": []},
        "pending_responses": [],
        "runtime": {},
        "tool_patch_log": [],
        "user_input": user_input1,
        "user_message": user_input1,
        "onboarding_completed": True,
    }
    
    print(f"用户输入: {user_input1}")
    
    result1 = app.invoke(state_input1, config=config)
    
    reasoning_count_1 = 0
    if "messages" in result1:
        for msg in result1["messages"]:
            msg_dict = convert_message_to_dict(msg)
            reasoning = extract_reasoning_content(msg_dict)
            if reasoning:
                reasoning_count_1 += 1
                print(f"  ✓ Reasoning #{reasoning_count_1}: {reasoning[:100]}...")
    
    print(f"第一轮 reasoning_content: {reasoning_count_1} 条")
    
    # 检查是否触发中断
    if "__interrupt__" in result1:
        print("  ✓ 触发中断")
        interrupt_value = result1["__interrupt__"]
        print(f"  中断类型: {type(interrupt_value)}")
        if hasattr(interrupt_value, "value"):
            print(f"  中断内容: {interrupt_value.value}")
        
        # 第二轮：Resume
        print("\n【第二轮：Resume】")
        resume_payload = {
            "answers": {
                "q1": "最近和 crush 聊天变少了",
                "q2": "感到焦虑和失落",
            }
        }
        print(f"Resume payload: {resume_payload}")
        
        result2 = app.invoke(Command(resume=resume_payload), config=config)
        
        reasoning_count_2 = 0
        if "messages" in result2:
            for msg in result2["messages"]:
                msg_dict = convert_message_to_dict(msg)
                reasoning = extract_reasoning_content(msg_dict)
                if reasoning:
                    reasoning_count_2 += 1
                    print(f"  ✓ Reasoning (Resume #{reasoning_count_2}): {reasoning[:100]}...")
        
        print(f"Resume reasoning_content: {reasoning_count_2} 条")
        
        # 第三轮：继续对话（多轮思考）
        print("\n【第三轮：继续对话】")
        user_input2 = "那你觉得我该怎么办呢？"
        
        state_input2 = {
            "messages": result2.get("messages", []),
            "layer2_memory": result2.get("layer2_memory", {}),
            "layer3_memory": result2.get("layer3_memory", {}),
            "pending_responses": [],
            "runtime": result2.get("runtime", {}),
            "tool_patch_log": result2.get("tool_patch_log", []),
            "user_input": user_input2,
            "user_message": user_input2,
            "onboarding_completed": True,
        }
        
        print(f"用户输入: {user_input2}")
        
        result3 = app.invoke(state_input2, config=config)
        
        reasoning_count_3 = 0
        if "messages" in result3:
            for msg in result3["messages"]:
                msg_dict = convert_message_to_dict(msg)
                reasoning = extract_reasoning_content(msg_dict)
                if reasoning:
                    reasoning_count_3 += 1
                    print(f"  ✓ Reasoning (Round 3 #{reasoning_count_3}): {reasoning[:100]}...")
        
        print(f"第三轮 reasoning_content: {reasoning_count_3} 条")
        
        # 总结
        print("\n【总结】")
        total_reasoning = reasoning_count_1 + reasoning_count_2 + reasoning_count_3
        print(f"  总 reasoning_content: {total_reasoning} 条")
        print(f"    - 第一轮: {reasoning_count_1} 条")
        print(f"    - Resume: {reasoning_count_2} 条")
        print(f"    - 第三轮: {reasoning_count_3} 条")
    else:
        print("  ✗ 没有触发中断")
        print("  尝试直接多轮对话测试...")
        
        # 第二轮：继续对话
        print("\n【第二轮：继续对话】")
        user_input2 = "那你觉得我该怎么办呢？"
        
        state_input2 = {
            "messages": result1.get("messages", []),
            "layer2_memory": result1.get("layer2_memory", {}),
            "layer3_memory": result1.get("layer3_memory", {}),
            "pending_responses": [],
            "runtime": result1.get("runtime", {}),
            "tool_patch_log": result1.get("tool_patch_log", []),
            "user_input": user_input2,
            "user_message": user_input2,
            "onboarding_completed": True,
        }
        
        print(f"用户输入: {user_input2}")
        
        result2 = app.invoke(state_input2, config=config)
        
        reasoning_count_2 = 0
        if "messages" in result2:
            for msg in result2["messages"]:
                msg_dict = convert_message_to_dict(msg)
                reasoning = extract_reasoning_content(msg_dict)
                if reasoning:
                    reasoning_count_2 += 1
                    print(f"  ✓ Reasoning (Round 2 #{reasoning_count_2}): {reasoning[:100]}...")
        
        print(f"第二轮 reasoning_content: {reasoning_count_2} 条")
        
        print("\n【总结】")
        total_reasoning = reasoning_count_1 + reasoning_count_2
        print(f"  总 reasoning_content: {total_reasoning} 条")
        print(f"    - 第一轮: {reasoning_count_1} 条")
        print(f"    - 第二轮: {reasoning_count_2} 条")
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
