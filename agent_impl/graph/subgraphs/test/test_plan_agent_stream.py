"""
流式测试：plan_agent 使用 deepseek-reasoner 的执行过程
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
print("流式测试：plan_agent + deepseek-reasoner")
print("=" * 80)


def main():
    checkpointer = MemorySaver()
    app = get_plan_subgraph(checkpointer=checkpointer)
    
    config = {"configurable": {"thread_id": "test_plan_agent_stream"}}
    
    user_input = "我想制定一个学习计划，学习 Python 编程"
    
    print("\n" + "=" * 80)
    print("【用户输入】")
    print("=" * 80)
    print(f"  {user_input}")
    
    print("\n" + "=" * 80)
    print("【开始流式执行】")
    print("=" * 80)
    
    sub_input = {
        "task_spec": {
            "instruction": user_input,
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
    
    event_count = 0
    reasoning_count = 0
    tool_call_count = 0
    
    for event in app.stream(sub_input, config=config, stream_mode="updates"):
        event_count += 1
        
        event_name = event.get("event", "")
        event_data = event.get("data", {})
        
        if "node" in event_data:
            node_name = event_data["node"]
            print(f"\n  [{event_count}] 节点: {node_name}")
            
            if "private_messages" in event_data:
                msgs = event_data["private_messages"]
                print(f"    private_messages: {len(msgs)} 条")
                
                for msg in msgs:
                    msg_dict = convert_message_to_dict(msg)
                    reasoning = extract_reasoning_content(msg_dict)
                    if reasoning:
                        reasoning_count += 1
                        print(f"      ✓ 找到 reasoning_content: {reasoning[:80]}...")
                    
                    tool_calls = msg_dict.get("tool_calls")
                    if tool_calls:
                        tool_call_count += 1
                        print(f"      ✓ 工具调用: {[tc.get('name') for tc in tool_calls]}")
    
    print("\n" + "=" * 80)
    print("【执行统计】")
    print("=" * 80)
    print(f"  总事件数: {event_count}")
    print(f"  找到 reasoning_content: {reasoning_count} 条")
    print(f"  工具调用次数: {tool_call_count}")
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
