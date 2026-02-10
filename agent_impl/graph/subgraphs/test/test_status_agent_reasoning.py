"""
测试 status agent 使用 deepseek-reasoner 的完整流程
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from graph.subgraphs.status import get_status_subgraph
from graph.state import convert_message_to_dict
from utils.reasoning_content import extract_reasoning_content

load_dotenv()

print("=" * 80)
print("测试：status_agent + deepseek-reasoner 完整流程")
print("=" * 80)


def main():
    checkpointer = MemorySaver()
    app = get_status_subgraph(checkpointer=checkpointer)
    
    config = {"configurable": {"thread_id": "test_status_agent"}}
    
    user_input = "最近和女朋友相处有点冷淡，想了解下现状"
    
    print("\n" + "=" * 80)
    print("【用户输入】")
    print("=" * 80)
    print(f"  {user_input}")
    
    print("\n" + "=" * 80)
    print("【调用 status_subgraph】")
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
    
    print(f"\n  开始执行...")
    result = app.invoke(sub_input, config=config)
    
    print("\n" + "=" * 80)
    print("【分析结果】")
    print("=" * 80)
    
    print(f"\n  返回结果键: {list(result.keys())}")
    
    if "private_messages" in result:
        private_msgs = result["private_messages"]
        print(f"\n  私有消息数: {len(private_msgs)}")
        
        reasoning_count = 0
        for msg in private_msgs:
            msg_dict = convert_message_to_dict(msg)
            reasoning = extract_reasoning_content(msg_dict)
            if reasoning:
                reasoning_count += 1
                print(f"\n  ✓ 找到 reasoning_content #{reasoning_count}: {reasoning[:80]}...")
        
        print(f"\n  包含 reasoning_content 的消息: {reasoning_count} 条")
    
    if "final" in result:
        final_result = result["final"]
        print(f"\n  最终结果 (final):")
        print(f"    Text: {final_result.get('text', '')[:200]}...")
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
