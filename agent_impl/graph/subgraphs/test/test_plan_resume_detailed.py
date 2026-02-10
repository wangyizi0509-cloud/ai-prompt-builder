"""
详细测试：plan_agent resume 流程（捕获 reasoning_content）
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from graph.subgraphs.plan import get_plan_subgraph
from graph.state import convert_message_to_dict
from utils.reasoning_content import extract_reasoning_content

load_dotenv()

print("=" * 80)
print("详细测试：plan_agent resume 流程（捕获 reasoning_content）")
print("=" * 80)


def main():
    checkpointer = MemorySaver()
    app = get_plan_subgraph(checkpointer=checkpointer)
    
    config = {"configurable": {"thread_id": "test_plan_resume_detailed"}}
    
    # 第一轮：触发中断
    print("\n【第一轮：触发中断】")
    sub_input = {
        "task_spec": {
            "instruction": "我想制定一个学习计划，学习 Python 编程",
            "parent_state": {
                "messages": [],
                "layer2_memory": {},
                "layer3_memory": {},
                "pending_responses": [],
                "runtime": {},
                "tool_patch_log": [],
            },
        },
        "private_messages": [],
    }
    
    result1 = app.invoke(sub_input, config=config)
    
    if "__interrupt__" in result1:
        print("✓ 触发中断")
        
        # 统计第一轮的 reasoning_content
        if "private_messages" in result1:
            reasoning_count_1 = 0
            for msg in result1["private_messages"]:
                msg_dict = convert_message_to_dict(msg)
                if extract_reasoning_content(msg_dict):
                    reasoning_count_1 += 1
            print(f"  第一轮 reasoning_content: {reasoning_count_1} 条")
        
        # 第二轮：resume（流式捕获）
        print("\n【第二轮：Resume（流式捕获）】")
        resume_payload = {
            "answers": {
                "exp_level": "零基础，完全没写过代码",
                "time_commitment": "5-10小时（正常节奏）",
                "learning_style": "看视频课程",
            }
        }
        print(f"Resume payload: {resume_payload}")
        
        reasoning_count_2 = 0
        tool_call_count_2 = 0
        
        for event in app.stream(Command(resume=resume_payload), config=config, stream_mode="updates"):
            event_data = event.get("data", {})
            if "private_messages" in event_data:
                msgs = event_data["private_messages"]
                for msg in msgs:
                    msg_dict = convert_message_to_dict(msg)
                    reasoning = extract_reasoning_content(msg_dict)
                    if reasoning:
                        reasoning_count_2 += 1
                        print(f"\n  ✓ 找到 reasoning_content (Resume 第{reasoning_count_2}条): {reasoning[:80]}...")
                    
                    tool_calls = msg_dict.get("tool_calls")
                    if tool_calls:
                        tool_call_count_2 += 1
                        print(f"  ✓ 工具调用 (Resume 第{tool_call_count_2}次): {[tc.get('name') for tc in tool_calls]}")
        
        print(f"\n  Resume reasoning_content 总计: {reasoning_count_2} 条")
        print(f"  Resume 工具调用总计: {tool_call_count_2} 次")
        
        # 获取最终结果
        result2 = app.get_state(config)
        
        print("\n【最终结果】")
        if hasattr(result2, 'values'):
            final_values = result2.values
            if "final" in final_values:
                print(f"  ✓ 有 final 结果")
                final = final_values["final"]
                print(f"    Text: {final.get('text', '')[:100]}...")
            else:
                print(f"  ✗ 没有 final 结果")
    
    else:
        print("✗ 没有触发中断")


if __name__ == "__main__":
    main()
