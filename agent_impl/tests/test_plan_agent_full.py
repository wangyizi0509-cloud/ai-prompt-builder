"""
完整测试：plan_agent 使用 deepseek-reasoner 的完整流程

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
from langgraph.types import Command

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
    
    config = {"configurable": {"thread_id": "test_plan_agent_full"}}
    
    user_input = "我想制定一个学习计划，学习 Python 编程"
    
    print("\n" + "=" * 80)
    print("【步骤 1：用户输入】")
    print("=" * 80)
    print(f"  用户消息: {user_input}")
    
    print("\n" + "=" * 80)
    print("【步骤 2：调用 plan_subgraph - 第一轮】")
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
    print("【步骤 3：分析第一轮结果】")
    print("=" * 80)
    
    if "__interrupt__" in result:
        print(f"\n  ⚠️ 触发中断（需要用户回答）")
        interrupt = result["__interrupt__"]
        if hasattr(interrupt, 'value'):
            interrupt_value = interrupt.value
            if isinstance(interrupt_value, dict) and "questions" in interrupt_value:
                print(f"\n  用户需要回答 {len(interrupt_value['questions'])} 个问题：")
                for q in interrupt_value["questions"]:
                    print(f"    - {q.get('question', 'N/A')}")
        
        print("\n" + "=" * 80)
        print("【步骤 4：用户回答问题（Resume）】")
        print("=" * 80)
        
        # 模拟用户回答
        resume_payload = {
            "answers": {
                "exp_level": "零基础，完全没写过代码",
                "time_commitment": "5-10小时（正常节奏）",
                "learning_style": "看视频课程",
            }
        }
        print(f"  用户回答: {resume_payload}")
        
        print("\n" + "=" * 80)
        print("【步骤 5：Resume 执行 - 第二轮】")
        print("=" * 80)
        
        result = app.invoke(Command(resume=resume_payload), config=config)
    
    print("\n" + "=" * 80)
    print("【步骤 6：分析最终结果】")
    print("=" * 80)
    
    print(f"\n  返回结果键: {list(result.keys())}")
    
    if "private_messages" in result:
        private_msgs = result["private_messages"]
        print(f"\n  私有消息数: {len(private_msgs)}")
        
        # 统计 reasoning_content
        reasoning_count = 0
        for msg in private_msgs:
            msg_dict = convert_message_to_dict(msg)
            if extract_reasoning_content(msg_dict):
                reasoning_count += 1
        print(f"  包含 reasoning_content 的消息: {reasoning_count} 条")
        
        print("\n  私有消息详情（只显示有 reasoning_content 和 tool_calls 的）：")
        for i, msg in enumerate(private_msgs):
            msg_dict = convert_message_to_dict(msg)
            reasoning = extract_reasoning_content(msg_dict)
            tool_calls = msg_dict.get("tool_calls")
            
            if reasoning or tool_calls:
                print_message(msg_dict, f"私有消息 {i+1}")
    
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
    print("测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
