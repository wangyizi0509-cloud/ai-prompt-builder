"""
详细测试：main agent 使用 deepseek-reasoner 的完整流程（流式捕获）
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from graph.workflow import compile_workflow
from graph.state import convert_message_to_dict
from utils.reasoning_content import extract_reasoning_content

load_dotenv()

print("=" * 80)
print("详细测试：main_agent + deepseek-reasoner（流式捕获）")
print("=" * 80)


def main():
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    config = {"configurable": {"thread_id": "test_main_agent_detailed"}}
    
    user_input = "我想制定一个学习 Python 的计划"
    
    print("\n" + "=" * 80)
    print("【用户输入】")
    print("=" * 80)
    print(f"  {user_input}")
    
    print("\n" + "=" * 80)
    print("【开始流式执行】")
    print("=" * 80)
    
    state_input = {
        "messages": [],
        "layer2_memory": {},
        "layer3_memory": {},
        "pending_responses": [],
        "runtime": {},
        "tool_patch_log": [],
        "user_input": user_input,
        "user_message": user_input,
    }
    
    reasoning_count = 0
    tool_call_count = 0
    node_executions = []
    
    for event in app.stream(state_input, config=config, stream_mode="updates"):
        event_name = list(event.keys())[0] if event else ""
        event_data = event.get(event_name, {})
        
        print(f"\n  【节点】 {event_name}")
        
        node_executions.append(event_name)
        
        if "messages" in event_data:
            msgs = event_data["messages"]
            if msgs:
                latest_msg = msgs[-1] if isinstance(msgs, list) and len(msgs) > 0 else msgs
                msg_dict = convert_message_to_dict(latest_msg) if hasattr(latest_msg, 'content') else latest_msg
                reasoning = extract_reasoning_content(msg_dict)
                if reasoning:
                    reasoning_count += 1
                    print(f"    ✓ 找到 reasoning_content #{reasoning_count}: {reasoning[:80]}...")
        
        if "tool_patch_log" in event_data:
            patches = event_data["tool_patch_log"]
            if patches:
                for patch in patches:
                    tool_name = patch.get("tool_name") if isinstance(patch, dict) else None
                    if tool_name:
                        tool_call_count += 1
                        print(f"    ✓ 工具调用 #{tool_call_count}: {tool_name}")
    
    print("\n" + "=" * 80)
    print("【执行统计】")
    print("=" * 80)
    print(f"  执行的节点: {node_executions}")
    print(f"  找到 reasoning_content: {reasoning_count} 条")
    print(f"  工具调用次数: {tool_call_count}")
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
