"""
测试 plan_agent 的 resume 流程
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
print("测试：plan_agent resume 流程")
print("=" * 80)


def main():
    checkpointer = MemorySaver()
    app = get_plan_subgraph(checkpointer=checkpointer)
    
    config = {"configurable": {"thread_id": "test_plan_resume"}}
    
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
        
        # 第二轮：resume
        print("\n【第二轮：Resume】")
        resume_payload = {
            "answers": {
                "exp_level": "零基础，完全没写过代码",
                "time_commitment": "5-10小时（正常节奏）",
                "learning_style": "看视频课程",
            }
        }
        print(f"Resume payload: {resume_payload}")
        
        result2 = app.invoke(Command(resume=resume_payload), config=config)
        
        print("\n【最终结果】")
        print(f"  键: {list(result2.keys())}")
        
        if "final" in result2:
            print(f"  ✓ 有 final 结果")
            final = result2["final"]
            print(f"    Text: {final.get('text', '')[:100]}...")
        else:
            print(f"  ✗ 没有 final 结果")
            if "__interrupt__" in result2:
                print(f"  又触发了中断")
            if "private_messages" in result2:
                print(f"  private_messages: {len(result2['private_messages'])} 条")
        
        # 检查 reasoning_content
        if "private_messages" in result2:
            reasoning_count = 0
            for msg in result2["private_messages"]:
                msg_dict = convert_message_to_dict(msg)
                if extract_reasoning_content(msg_dict):
                    reasoning_count += 1
            print(f"\n  Resume 后的 reasoning_content: {reasoning_count} 条")
    else:
        print("✗ 没有触发中断")


if __name__ == "__main__":
    main()
