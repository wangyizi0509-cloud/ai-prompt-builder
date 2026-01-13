#!/usr/bin/env python3
"""
万能 Agent 调试脚本 (Universal Agent Debugger)

功能：
1. 快速模拟用户输入，运行完整的工作流
2. 捕获所有中间状态、LLM 原始响应、工具调用
3. 自动生成详细的排查日志文件 (debug_logs/debug_YYYYMMDD_HHMMSS.txt)
4. 控制台高亮显示关键节点

使用方法：
    # 1. 运行默认场景（提问测试）
    python3 debug_agent.py

    # 2. 运行特定场景
    python3 debug_agent.py --scenario consult
    python3 debug_agent.py --scenario inquiry

    # 3. 自定义输入测试
    python3 debug_agent.py --input "他昨天没回我消息，我该怎么办？"

"""

import sys
import os
import json
import argparse
import datetime
from pathlib import Path
from typing import Dict, Any, List

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.getcwd(), "agent_impl"))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich import box

from langchain_core.messages import ToolMessage, AIMessage, HumanMessage

# 尝试导入核心模块，如果失败给出提示
try:
    from agent_impl.graph.workflow import get_workflow
    from agent_impl.graph.state import create_initial_state
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请确保你在项目根目录下运行此脚本，并且 agent_impl 目录存在。")
    sys.exit(1)

console = Console()

# === 预定义测试场景 ===
SCENARIOS = {
    "inquiry": {
        "desc": "测试提问 Skill (Inquiry Card 生成)",
        "input": "我想约她这周末出来玩，但我不知道该怎么开口，也不知道她喜不喜欢这类活动。"
    },
    "consult": {
        "desc": "测试纯咨询/情感分析 Skill",
        "input": "他昨天回我消息特别慢，而且只回了几个字，是不是对我不感兴趣？我该怎么回复？"
    },
    "emotion": {
        "desc": "测试情感陪伴 Skill",
        "input": "我好难过，刚才看到他在朋友圈发了和别人的合照，感觉自己没戏了。"
    },
    "status": {
        "desc": "测试现状分析 (Status Agent 路由)",
        "input": "帮我分析一下我现在的情况，我和他是同事，认识三个月了，偶尔聊天。"
    },
    "plan": {
        "desc": "测试行动规划 (Plan Agent 路由)",
        "input": "帮我制定一个追求计划，目标是下个月能约他单独出来。"
    }
}

class DebugLogger:
    def __init__(self):
        self.logs = []
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = f"debug_logs/debug_{self.timestamp}.txt"
        
    def log(self, title: str, content: Any):
        """记录日志到内存和文件"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        # 格式化内容
        if isinstance(content, (dict, list)):
            try:
                formatted_content = json.dumps(content, indent=2, ensure_ascii=False, default=str)
            except Exception:
                formatted_content = str(content)
        else:
            formatted_content = str(content)
            
        entry = f"\n{'='*20} [{timestamp}] {title} {'='*20}\n{formatted_content}\n"
        self.logs.append(entry)
        
        # 实时追加写入文件
        with open(self.filename, "a", encoding="utf-8") as f:
            f.write(entry)

    def get_log_path(self):
        return self.filename

def print_step_header(step_name):
    console.print(f"\n[bold blue]➤ {step_name}[/bold blue]")

def analyze_result(result: Dict[str, Any], logger: DebugLogger):
    """分析运行结果并打印关键信息"""
    
    console.print(Panel("[bold green]✅ 工作流执行完成[/bold green]", border_style="green"))
    
    # 1. 检查 Debug Log
    debug_logs = result.get("debug_log", [])
    if debug_logs:
        console.print("\n[bold cyan]📜 内部执行路径:[/bold cyan]")
        table = Table(box=box.SIMPLE)
        table.add_column("Node", style="cyan")
        table.add_column("Step", style="white")
        table.add_column("Details", style="dim")
        
        for log in debug_logs:
            node = log.get("node", "Unknown")
            step = log.get("step", "Unknown")
            details = ""
            
            # 提取关键信息用于展示
            if "tool_calls" in log:
                details = f"Tools: {log['tool_calls']}"
            elif "response" in log:
                # 截断过长的响应
                resp = log['response']
                details = (resp[:50] + "...") if len(resp) > 50 else resp
            elif "next_action" in log: # 兼容某些旧日志格式
                 details = f"Next: {log.get('next_action')}"

            table.add_row(node, step, details)
        
        console.print(table)
        logger.log("Debug Trace", debug_logs)

    # 2. 检查 Tool Calls & Output (关键排查点)
    messages = result.get("messages", [])
    tool_calls_found = []
    tool_outputs_found = []
    
    for msg in messages:
        # Tool Calls
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_calls_found.extend(msg.tool_calls)
        elif isinstance(msg, dict) and msg.get("tool_calls"): # 兼容
            tool_calls_found.extend(msg.get("tool_calls"))
            
        # Tool Outputs
        if isinstance(msg, ToolMessage):
            tool_outputs_found.append(msg)
        elif isinstance(msg, dict) and msg.get("role") == "tool":
            tool_outputs_found.append(msg)

    if tool_calls_found:
        console.print(f"\n[bold magenta]🛠️ 触发工具调用 ({len(tool_calls_found)}):[/bold magenta]")
        for tc in tool_calls_found:
            console.print(f"  - {tc}")
    
    if tool_outputs_found:
        console.print(f"\n[bold magenta]📦 获取工具输出 ({len(tool_outputs_found)}):[/bold magenta]")
        for output in tool_outputs_found:
            content = output.content if hasattr(output, "content") else output.get("content")
            preview = (content[:100] + "...") if len(content) > 100 else content
            console.print(f"  - {preview}")
    
    logger.log("Messages History", messages)

    # 3. 检查最终状态关键字段
    console.print("\n[bold yellow]📊 最终状态快照:[/bold yellow]")
    
    key_fields = {
        "intent_type": result.get("intent_type"),
        "next_action": result.get("next_action"),
        "need_questions": result.get("need_questions"),
        "inquiry_card": "✅ Present" if result.get("inquiry_card") else "❌ None",
        "pending_responses": len(result.get("pending_responses", [])),
    }
    console.print_json(data=key_fields)
    
    # 特别检查 Inquiry Card
    if result.get("inquiry_card"):
        console.print("\n[bold green]📋 Inquiry Card Detail:[/bold green]")
        # Pretty print just the questions
        card = result.get("inquiry_card")
        questions = card.get("questions", [])
        for i, q in enumerate(questions):
            console.print(f"  {i+1}. [{q.get('type')}] {q.get('question')}")
    
    # 打印最终回复
    final_response = result.get("response_content", "")
    if final_response:
        console.print(Panel(final_response, title="🤖 Agent Final Response", border_style="blue"))
    else:
        # 尝试从 pending_responses 找
        pending = result.get("pending_responses", [])
        if pending:
             last_resp = pending[-1].get("content", "")
             console.print(Panel(last_resp, title="🤖 Agent Final Response (from pending)", border_style="blue"))


def run_debug(input_text: str):
    logger = DebugLogger()
    console.print(f"[dim]日志文件: {logger.get_log_path()}[/dim]")
    
    logger.log("User Input", input_text)
    
    try:
        # 1. 初始化
        print_step_header("Initialize State")
        initial_state = create_initial_state(input_text)
        logger.log("Initial State", initial_state)
        
        # 2. 加载工作流
        print_step_header("Load Workflow")
        workflow = get_workflow()
        
        # 3. 执行
        print_step_header("Invoke Workflow (This may take a few seconds...)")
        result = workflow.invoke(initial_state)
        
        # 4. 分析
        analyze_result(result, logger)
        
        # 5. 记录完整结果
        logger.log("Final Full Result", result)
        
        console.print(f"\n[bold reversed] 📝 完整日志已保存至: {logger.get_log_path()} [/bold reversed]")
        console.print("如果遇到问题，请将该文件内容发给我。")

    except Exception as e:
        console.print(Panel(f"[bold red]💥 系统崩溃 Exception[/bold red]\n{str(e)}", border_style="red"))
        import traceback
        tb = traceback.format_exc()
        console.print(tb)
        logger.log("Exception Traceback", tb)

def main():
    parser = argparse.ArgumentParser(description="Agent 万能调试工具")
    parser.add_argument("--input", "-i", type=str, help="自定义测试输入文本")
    parser.add_argument("--scenario", "-s", type=str, choices=list(SCENARIOS.keys()), default="inquiry", help="选择预定义测试场景")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有可用场景")
    
    args = parser.parse_args()
    
    if args.list:
        console.print(Panel("📋 可用测试场景", style="bold blue"))
        for key, info in SCENARIOS.items():
            console.print(f"[bold cyan]{key}[/bold cyan]: {info['desc']}")
            console.print(f"  Input: [dim]{info['input']}[/dim]\n")
        return

    # 确定输入
    if args.input:
        input_text = args.input
        console.print(f"[bold green]🔍 使用自定义输入:[/bold green] {input_text}")
    else:
        scenario = SCENARIOS[args.scenario]
        input_text = scenario["input"]
        console.print(f"[bold green]🔍 运行场景: {args.scenario}[/bold green]")
        console.print(f"[dim]{scenario['desc']}[/dim]")
        console.print(f"输入: {input_text}")
        
    run_debug(input_text)

if __name__ == "__main__":
    main()

