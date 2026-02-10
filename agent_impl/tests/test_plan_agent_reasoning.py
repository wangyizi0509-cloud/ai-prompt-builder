"""
测试 plan_agent 使用 deepseek-reasoner 的完整流程

展示：
1. 输入
2. 推理（reasoning_content）
3. 调用工具
4. 返回工具内容
5. 清理消息
6. 输出
"""

import os
import sys
import json

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver

from graph.subgraphs.plan import get_plan_subgraph
from graph.state import convert_message_to_dict
from utils.reasoning_content import extract_reasoning_content

load_dotenv()

print("=" * 80)
print("测试：plan_agent + deepseek-reasoner 完整流程")
print("=" * 80)


def print_message(msg, title="消息"):
    """打印消息详情"""
    print(f"\n  [{title}]")
    role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "unknown")
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
    print(f"    Role: {role}")
    print(f"    Content: {(content or '')[:100]}...")
    
    reasoning = extract_reasoning_content(msg)
    if reasoning:
        print(f"    Reasoning: {(reasoning or '')[:100]}...")
    
    tool_calls = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
    if tool_calls:
        print(f"    Tool Calls: {len(tool_calls)} 个")
        for tc in tool_calls:
            name = tc.get("name") if isinstance(tc, dict) else tc.get("name", "unknown")
            args = tc.get("args") if isinstance(tc, dict) else tc.get("args", {})
            print(f"      - {name}: {args}")


def main():
    checkpointer = MemorySaver()
    app = get_plan_subgraph(checkpointer=checkpointer)
    
    config = {"configurable": {"thread_id": "test_plan_agent_reasoning"}}
    
    user_input = "我想制定一个学习计划，学习 Python 编程，目标是三个月内能够独立开发简单的 Web 应用"
    
    print("\n" + "=" * 80)
    print("【步骤 1：用户输入】")
    print("=" * 80)
    print(f"  用户消息: {user_input}")
    
    print("\n" + "=" * 80)
    print("【步骤 2：调用 plan_subgraph】")
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
    
    print("\n  输入状态:")
    print(f"    task_spec.instruction: {sub_input['task_spec']['instruction'][:80]}...")
    print(f"    private_messages: {len(sub_input['private_messages'])} 条")
    
    print("\n  开始执行...")
    result = app.invoke(sub_input, config=config)
    
    print("\n" + "=" * 80)
    print("【步骤 3：分析执行结果】")
    print("=" * 80)
    
    print(f"\n  返回结果键: {list(result.keys())}")
    
    if "private_messages" in result:
        private_msgs = result["private_messages"]
        print(f"\n  私有消息数: {len(private_msgs)}")
        print("  私有消息详情:")
        for i, msg in enumerate(private_msgs):
            msg_dict = convert_message_to_dict(msg)
            print_message(msg_dict, f"私有消息 {i+1}")
    
    if "state_patch" in result:
        state_patch = result["state_patch"]
        print(f"\n  状态更新 (state_patch):")
        for key, value in state_patch.items():
            if isinstance(value, str) and len(value) > 100:
                print(f"    {key}: {value[:100]}...")
            else:
                print(f"    {key}: {value}")
    
    if "__interrupt__" in result:
        print(f"\n  ⚠️ 触发中断: {result['__interrupt__']}")
        return
    
    if "final" in result:
        final_result = result["final"]
        print(f"\n  最终结果 (final):")
        print(f"    Text: {final_result.get('text', '')[:200]}...")
        
        if "reasoning" in final_result:
            print(f"    Reasoning: {final_result.get('reasoning', '')[:100]}...")
        
        if "goal" in final_result:
            print(f"    Goal: {final_result.get('goal', '')[:100]}...")
        
        if "strategy" in final_result:
            print(f"    Strategy: {final_result.get('strategy', '')[:100]}...")
        
        if "phases" in final_result and final_result["phases"]:
            print(f"    Phases: {len(final_result['phases'])} 个")
            for i, phase in enumerate(final_result["phases"][:3]):
                print(f"      {i+1}. {phase.get('title', 'N/A')}")
    
    print("\n" + "=" * 80)
    print("【步骤 4：检查 reasoning_content】")
    print("=" * 80)
    
    reasoning_count = 0
    if "private_messages" in result:
        for msg in result["private_messages"]:
            msg_dict = convert_message_to_dict(msg)
            reasoning = extract_reasoning_content(msg_dict)
            if reasoning:
                reasoning_count += 1
                print(f"\n  找到 reasoning_content #{reasoning_count}:")
                print(f"    长度: {len(reasoning)}")
                print(f"    预览: {reasoning[:150]}...")
    
    print(f"\n  总计: {reasoning_count} 条 reasoning_content")
    
    print("\n" + "=" * 80)
    print("【步骤 5：检查工具调用】")
    print("=" * 80)
    
    tool_call_count = 0
    if "private_messages" in result:
        for msg in result["private_messages"]:
            msg_dict = convert_message_to_dict(msg)
            tool_calls = msg_dict.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    tool_call_count += 1
                    name = tc.get("name", "unknown")
                    args = tc.get("args", {})
                    print(f"\n  工具调用 #{tool_call_count}:")
                    print(f"    工具: {name}")
                    print(f"    参数: {json.dumps(args, ensure_ascii=False)[:100]}...")
    
    print(f"\n  总计: {tool_call_count} 次工具调用")
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
