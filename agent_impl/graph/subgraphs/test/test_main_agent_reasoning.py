"""
测试 main agent 使用 deepseek-reasoner 的完整流程
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
print("测试：main_agent + deepseek-reasoner 完整流程")
print("=" * 80)


def main():
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    config = {"configurable": {"thread_id": "test_main_agent"}}
    
    user_input = "你好，我是新用户，想了解一下这个系统"
    
    print("\n" + "=" * 80)
    print("【用户输入】")
    print("=" * 80)
    print(f"  {user_input}")
    
    print("\n" + "=" * 80)
    print("【调用主 workflow】")
    print("=" * 80)
    
    state_input = {
        "messages": [],
        "layer2_memory": {},
        "layer3_memory": {},
        "pending_responses": [],
        "runtime": {},
        "tool_patch_log": [],
        "user_input": user_input,
    }
    
    print(f"\n  开始执行...")
    result = app.invoke(state_input, config=config)
    
    print("\n" + "=" * 80)
    print("【分析结果】")
    print("=" * 80)
    
    print(f"\n  返回结果键: {list(result.keys())}")
    
    if "messages" in result:
        msgs = result["messages"]
        print(f"\n  消息数: {len(msgs)}")
        
        reasoning_count = 0
        for msg in msgs:
            msg_dict = convert_message_to_dict(msg)
            reasoning = extract_reasoning_content(msg_dict)
            if reasoning:
                reasoning_count += 1
                print(f"\n  ✓ 找到 reasoning_content #{reasoning_count}: {reasoning[:80]}...")
        
        print(f"\n  包含 reasoning_content 的消息: {reasoning_count} 条")
    
    if "layer3_memory" in result:
        print(f"\n  layer3_memory: {list(result['layer3_memory'].keys())}")
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
