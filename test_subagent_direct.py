"""
直接测试子 Agent 的调用（简化版）
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent_impl'))

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver

from graph.workflow import compile_workflow
from graph.state import create_initial_state

load_dotenv()

print("=" * 80)
print("测试：直接调用子 Agent")
print("=" * 80)

checkpointer = MemorySaver()
app = compile_workflow(checkpointer=checkpointer)

thread_id = "test_direct_subagent"
config = {"configurable": {"thread_id": thread_id}}

user_input = "call_status_agent: 请帮我分析一下我的情感状态，我最近感觉很迷茫"

print(f"\n  用户输入: {user_input}")

state_input = create_initial_state(user_input)
state_input["onboarding_completed"] = True

print(f"\n  执行 workflow...")
result = app.invoke(state_input, config=config)

print(f"\n  结果键: {list(result.keys())}")

tool_patch_log = result.get("tool_patch_log", [])
print(f"\n  Tool Patch Log 条目数: {len(tool_patch_log)}")

if tool_patch_log:
    print(f"\n  Tool Patch 详情:")
    for i, patch in enumerate(tool_patch_log):
        print(f"    #{i+1}: {patch}")

layer2_memory = result.get("layer2_memory", {})
status_report = layer2_memory.get("status_report")
if status_report:
    print(f"\n  ✓ Status Report 已生成:")
    print(f"    Summary: {str(status_report.get('summary', ''))[:200]}...")
else:
    print(f"\n  ✗ 未生成 Status Report")

pending_responses = result.get("pending_responses", [])
print(f"\n  Pending Responses 数量: {len(pending_responses)}")
for i, resp in enumerate(pending_responses):
    print(f"\n  Response #{i+1}:")
    print(f"    From: {resp.get('from')}")
    print(f"    Content: {resp.get('content')[:150]}...")
