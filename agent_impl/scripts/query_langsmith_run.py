#!/usr/bin/env python3
"""
查询 LangSmith run 详情的调试脚本
"""

import os
import json
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from langsmith import Client

# 目标 run ID
RUN_ID = "019c03e3-dd5b-72b0-b14a-ac2dda1ba290"

def main():
    client = Client(
        api_key=os.getenv("LANGSMITH_API_KEY"),
    )
    
    # 搜索与这个 trace 相关的所有 run
    print("🔍 SEARCHING FOR ALL RUNS IN THIS TRACE:")
    print("=" * 80)
    
    try:
        all_runs = list(client.list_runs(
            project_name=os.getenv("LANGSMITH_PROJECT", "crushe-agent-debug"),
            filter=f'eq(trace_id, "{RUN_ID}")',
        ))
        
        print(f"Total runs in trace: {len(all_runs)}")
        
        # 找到所有 LLM 调用（通常是 type=llm）
        llm_runs = [r for r in all_runs if r.run_type == 'llm']
        print(f"LLM runs: {len(llm_runs)}")
        
        # 找 plan_agent 相关的 LLM 调用
        for run in all_runs:
            if 'plan' in (run.name or '').lower() or (run.run_type == 'llm' and run.parent_run_id):
                # 检查父 run 是否是 plan_agent
                parent_is_plan = False
                for p_run in all_runs:
                    if p_run.id == run.parent_run_id and 'plan' in (p_run.name or '').lower():
                        parent_is_plan = True
                        break
                
                if 'plan' in (run.name or '').lower() or parent_is_plan:
                    print(f"\n{'='*80}")
                    print(f"Run: {run.name} (type={run.run_type})")
                    print(f"ID: {run.id}")
                    print(f"Parent ID: {run.parent_run_id}")
                    print(f"Status: {run.status}")
                    
                    if run.run_type == 'llm':
                        print(f"\n📥 LLM INPUTS (Messages sent to model):")
                        print("-" * 40)
                        if run.inputs:
                            # 打印完整的 messages
                            messages = run.inputs.get('messages', [])
                            for i, msg in enumerate(messages):
                                print(f"\n--- Message {i+1} ---")
                                if isinstance(msg, dict):
                                    role = msg.get('role', msg.get('type', 'unknown'))
                                    content = msg.get('content', '')
                                    print(f"Role: {role}")
                                    if isinstance(content, str):
                                        print(f"Content (first 2000 chars):\n{content[:2000]}")
                                    else:
                                        print(f"Content: {json.dumps(content, ensure_ascii=False, default=str)[:2000]}")
                                else:
                                    print(f"Message: {str(msg)[:2000]}")
                            
                            # 打印 tools 如果有
                            if 'tools' in run.inputs or 'functions' in run.inputs:
                                print(f"\n🔧 TOOLS bound to LLM:")
                                tools = run.inputs.get('tools', run.inputs.get('functions', []))
                                for tool in tools:
                                    if isinstance(tool, dict):
                                        print(f"  - {tool.get('name', tool.get('function', {}).get('name', 'unknown'))}")
                        
                        print(f"\n📤 LLM OUTPUTS:")
                        print("-" * 40)
                        if run.outputs:
                            print(json.dumps(run.outputs, indent=2, ensure_ascii=False, default=str)[:3000])
                    
                    elif run.run_type == 'chain':
                        print(f"\n📤 CHAIN OUTPUTS (truncated):")
                        if run.outputs:
                            print(json.dumps(run.outputs, indent=2, ensure_ascii=False, default=str)[:2000])
                            
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
