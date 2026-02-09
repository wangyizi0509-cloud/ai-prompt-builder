"""
详细测试：完整流程展示
输入 → 推理 → 调用工具 → 返回工具内容 → 清理消息 → 输出
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

print("=" * 100)
print("详细测试：完整流程展示")
print("=" * 100)


def print_section(title, char="="):
    print(f"\n{char * 100}")
    print(f"【{title}】")
    print(f"{char * 100}")


def print_message_details(msg, idx, show_reasoning=True, show_tool_calls=True):
    msg_dict = convert_message_to_dict(msg)
    role = msg_dict.get("role", "unknown")
    content = msg_dict.get("content", "")
    
    print(f"\n  消息 #{idx} [{role}]")
    if content:
        preview = content[:100] if len(content) > 100 else content
        print(f"    Content: {preview}{'...' if len(content) > 100 else ''}")
    
    reasoning = extract_reasoning_content(msg_dict)
    if reasoning and show_reasoning:
        print(f"\n    🔍 推理过程 (reasoning_content):")
        lines = reasoning.split('\n')
        for line in lines[:10]:
            print(f"      {line}")
        if len(lines) > 10:
            print(f"      ... (共 {len(lines)} 行)")
    
    tool_calls = msg_dict.get("tool_calls")
    if tool_calls and show_tool_calls:
        print(f"\n    🛠️ 工具调用:")
        for tc in tool_calls:
            name = tc.get("name", "unknown")
            args = tc.get("args", {})
            print(f"      - {name}")
            if args:
                for k, v in args.items():
                    print(f"          {k}: {v}")


def main():
    checkpointer = MemorySaver()
    app = get_plan_subgraph(checkpointer=checkpointer)
    
    config = {"configurable": {"thread_id": "test_full_process_detailed"}}
    
    user_input = "我想制定一个学习计划，学习 Python 编程"
    
    print_section("第一步：用户输入", "=")
    print(f"  用户输入: {user_input}")
    
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
    
    print_section("第二步：开始执行（流式捕获）", "=")
    
    reasoning_count = 0
    tool_call_count = 0
    all_messages = []
    
    for event in app.stream(sub_input, config=config, stream_mode="updates"):
        event_name = list(event.keys())[0] if event else ""
        event_data = event.get(event_name, {})
        
        print(f"\n  📍 节点: {event_name}")
        
        if "private_messages" in event_data:
            msgs = event_data["private_messages"]
            print(f"    收到 {len(msgs)} 条消息")
            
            for i, msg in enumerate(msgs):
                msg_dict = convert_message_to_dict(msg)
                all_messages.append(msg_dict)
                
                reasoning = extract_reasoning_content(msg_dict)
                if reasoning:
                    reasoning_count += 1
                    print(f"\n  🧠 推理 #{reasoning_count}:")
                    print(f"    {reasoning[:150]}...")
                
                tool_calls = msg_dict.get("tool_calls")
                if tool_calls:
                    tool_call_count += 1
                    print(f"\n  🛠️ 工具调用 #{tool_call_count}:")
                    for tc in tool_calls:
                        name = tc.get("name", "unknown")
                        args = tc.get("args", {})
                        print(f"    - {name}")
                        if args:
                            for k, v in args.items():
                                print(f"        {k}: {v}")
    
    print_section("第三步：执行统计", "=")
    print(f"  总消息数: {len(all_messages)}")
    print(f"  推理次数: {reasoning_count}")
    print(f"  工具调用次数: {tool_call_count}")
    
    print_section("第四步：消息详情（完整）", "=")
    for i, msg_dict in enumerate(all_messages):
        print_message_details(msg_dict, i)
    
    print_section("第五步：检查中断", "=")
    state = app.get_state(config)
    if hasattr(state, 'values'):
        values = state.values
        if "__interrupt__" in values:
            print(f"  ✓ 触发中断")
            interrupts = values["__interrupt__"]
            if interrupts:
                payload = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
                print(f"  中断内容: {payload}")
            
            print_section("第六步：Resume（用户回答）", "=")
            resume_payload = {
                "answers": {
                    "exp_level": "零基础，完全没写过代码",
                    "time_commitment": "5-10小时（正常节奏）",
                    "learning_style": "看视频课程",
                }
            }
            print(f"  用户回答:")
            for k, v in resume_payload["answers"].items():
                print(f"    {k}: {v}")
            
            print_section("第七步：Resume 后执行（流式捕获）", "=")
            
            reasoning_count_resume = 0
            tool_call_count_resume = 0
            all_messages_resume = []
            
            for event in app.stream(Command(resume=resume_payload), config=config, stream_mode="updates"):
                event_name = list(event.keys())[0] if event else ""
                event_data = event.get(event_name, {})
                
                print(f"\n  📍 节点: {event_name}")
                
                if "private_messages" in event_data:
                    msgs = event_data["private_messages"]
                    print(f"    收到 {len(msgs)} 条消息")
                    
                    for i, msg in enumerate(msgs):
                        msg_dict = convert_message_to_dict(msg)
                        all_messages_resume.append(msg_dict)
                        
                        reasoning = extract_reasoning_content(msg_dict)
                        if reasoning:
                            reasoning_count_resume += 1
                            print(f"\n  🧠 推理 (Resume #{reasoning_count_resume}):")
                            print(f"    {reasoning[:150]}...")
                        
                        tool_calls = msg_dict.get("tool_calls")
                        if tool_calls:
                            tool_call_count_resume += 1
                            print(f"\n  🛠️ 工具调用 (Resume #{tool_call_count_resume}):")
                            for tc in tool_calls:
                                name = tc.get("name", "unknown")
                                args = tc.get("args", {})
                                print(f"    - {name}")
                                if args:
                                    for k, v in args.items():
                                        print(f"        {k}: {v}")
            
            print_section("第八步：Resume 执行统计", "=")
            print(f"  总消息数: {len(all_messages_resume)}")
            print(f"  推理次数: {reasoning_count_resume}")
            print(f"  工具调用次数: {tool_call_count_resume}")
            
            print_section("第九步：Resume 消息详情（完整）", "=")
            for i, msg_dict in enumerate(all_messages_resume):
                print_message_details(msg_dict, i)
            
            print_section("第十步：最终结果", "=")
            final_state = app.get_state(config)
            if hasattr(final_state, 'values'):
                final_values = final_state.values
                if "final" in final_values:
                    final = final_values["final"]
                    print(f"  ✓ 有 final 结果")
                    print(f"    Text: {final.get('text', '')[:200]}...")
                    if "plan" in final:
                        plan = final["plan"]
                        print(f"\n    📋 学习计划:")
                        print(f"      {plan[:300]}...")
        else:
            print(f"  ✗ 没有触发中断")
            
            print_section("第五步：最终结果", "=")
            final_state = app.get_state(config)
            if hasattr(final_state, 'values'):
                final_values = final_state.values
                if "final" in final_values:
                    final = final_values["final"]
                    print(f"  ✓ 有 final 结果")
                    print(f"    Text: {final.get('text', '')[:200]}...")
    
    print_section("总结", "=")
    print(f"  第一轮推理: {reasoning_count} 次")
    if 'reasoning_count_resume' in locals():
        print(f"  Resume推理: {reasoning_count_resume} 次")
        print(f"  总推理次数: {reasoning_count + reasoning_count_resume}")
    print(f"  第一轮工具调用: {tool_call_count} 次")
    if 'tool_call_count_resume' in locals():
        print(f"  Resume工具调用: {tool_call_count_resume} 次")
        print(f"  总工具调用: {tool_call_count + tool_call_count_resume}")
    print("\n  ✓ 完整流程测试完成")


if __name__ == "__main__":
    main()
