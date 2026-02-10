"""
测试主 Agent 与子 Agent 的联动（简化版）
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
print("测试：主 Agent 与子 Agent 联动")
print("=" * 80)

checkpointer = MemorySaver()
app = compile_workflow(checkpointer=checkpointer)

thread_id = "test_linkage_scenario_1"
config = {"configurable": {"thread_id": thread_id}}

user_input = "我最近心情很不好，感觉对喜欢的人失去了信心"

print(f"\n用户输入: {user_input}")

state_input = create_initial_state(user_input)

print(f"\n执行 workflow...")
result = app.invoke(state_input, config=config)

print(f"\n结果键: {list(result.keys())}")

pending_responses = result.get("pending_responses", [])
print(f"\nPending Responses 数量: {len(pending_responses)}")

for i, resp in enumerate(pending_responses):
    print(f"\nResponse #{i+1}:")
    print(f"  From: {resp.get('from')}")
    content = resp.get('content', '')[:100]
    print(f"  Content: {content}...")

layer2_memory = result.get("layer2_memory", {})
status_report = layer2_memory.get("status_report")
if status_report:
    print(f"\n✓ Status Report 已生成")
    print(f"  Summary: {str(status_report.get('summary', ''))[:100]}...")
else:
    print(f"\n✗ 未生成 Status Report")

tool_patch_log = result.get("tool_patch_log", [])
print(f"\nTool Patch Log 条目数: {len(tool_patch_log)}")
if tool_patch_log:
    print(f"Tool Patch 详情:")
    for i, patch in enumerate(tool_patch_log[:3]):
        print(f"  #{i+1}: {patch}")
