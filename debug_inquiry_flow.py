
import sys
import os
import json
from rich.console import Console
from rich.panel import Panel

# 添加当前目录到路径
sys.path.insert(0, os.path.join(os.getcwd(), "agent_impl"))

from agent_impl.graph.workflow import get_workflow
from agent_impl.graph.state import create_initial_state
from langchain_core.messages import ToolMessage, AIMessage

console = Console()

def debug_inquiry_flow():
    """
    调试 Inquiry 流程：模拟用户请求 -> 触发提问 -> 加载工具 -> 生成 Card
    """
    console.print(Panel("[bold yellow]🚀 开始调试 Inquiry 流程[/bold yellow]", border_style="yellow"))
    
    workflow = get_workflow()
    
    # 1. 模拟用户输入，触发提问意图
    user_input = "我想约她这周末出来玩，但我不知道该怎么开口，也不知道她喜不喜欢这类活动。"
    console.print(f"[bold green]👤 用户输入:[/bold green] {user_input}")
    
    initial_state = create_initial_state(user_input)
    
    # 运行工作流
    print("\n[DEBUG] Invoking workflow...")
    
    try:
        # 注意：这里模拟的是一次完整的 invoke，实际上 LangGraph 内部会处理 Tool Loop
        # 如果是本地 invoke，它应该能自动跑完整个循环：
        # MainAgent (ask_user) -> SkillTools (load) -> MainAgent (generate card) -> End
        
        result = workflow.invoke(initial_state)
        
        console.print(Panel("[bold green]✅ 工作流执行完成[/bold green]", border_style="green"))
        
        # 检查 Debug Log
        debug_logs = result.get("debug_log", [])
        if debug_logs:
            console.print("\n[bold cyan]📜 调试日志:[/bold cyan]")
            for log in debug_logs:
                step = log.get("step", "Unknown Step")
                node = log.get("node", "Unknown Node")
                console.print(f"- [{node}] {step}")
                
                # 如果有 Skill Instructions 注入的记录
                if "Injecting skill instructions" in str(log):
                     console.print(f"  [bold yellow]✨ 成功检测到 Skill 指令注入![/bold yellow]")
                
                # 打印 MainAgent 的原始响应（如果是 Response Generated 步骤）
                if node == "main_agent" and step == "Response Generated":
                    raw_response = log.get("response", "No response captured")
                    console.print(Panel(f"[dim]{raw_response}[/dim]", title="MainAgent Raw Response", border_style="dim"))

        # 检查 Tool Calls
        messages = result.get("messages", [])
        tool_calls_found = False
        tool_output_found = False
        
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                tool_calls_found = True
                console.print(f"\n[bold magenta]🛠️ 发现工具调用:[/bold magenta] {msg.tool_calls}")
            
            if isinstance(msg, ToolMessage) or (isinstance(msg, dict) and msg.get("role") == "tool"):
                tool_output_found = True
                content_preview = str(msg.content)[:100] + "..." if hasattr(msg, "content") else str(msg.get("content"))[:100] + "..."
                console.print(f"\n[bold magenta]📦 发现工具输出:[/bold magenta] {content_preview}")
        
        if not tool_calls_found:
             console.print("\n[bold red]❌ 未触发工具调用 (MainAgent 没决定加载 Skill)[/bold red]")
        elif not tool_output_found:
             console.print("\n[bold red]❌ 未发现工具输出 (SkillLoader 没执行或没返回)[/bold red]")
        else:
             console.print("\n[bold green]✅ 工具链执行完整[/bold green]")

        # 检查最终输出的 Inquiry Card
        inquiry_card = result.get("inquiry_card")
        console.print("\n[bold cyan]📋 最终 Inquiry Card:[/bold cyan]")
        
        if inquiry_card:
            console.print_json(data=inquiry_card)
            
            questions = inquiry_card.get("questions", [])
            if questions:
                console.print(f"\n[bold green]✅ 成功生成 {len(questions)} 个问题[/bold green]")
                console.print("[dim]检查 question 类型:[/dim]")
                for q in questions:
                    console.print(f"- {q.get('type')}: {q.get('question')}")
            else:
                console.print("\n[bold red]❌ Inquiry Card 存在但没有 questions[/bold red]")
        else:
            console.print("\n[bold red]❌ 未生成 Inquiry Card (MainAgent 第二次调用没输出)[/bold red]")
            
            # 打印 MainAgent 的最后一次回复内容，看看它说了什么
            console.print(f"MainAgent Response Content: {result.get('response_content')}")
            console.print(f"Next Action: {result.get('next_action')}")

    except Exception as e:
        console.print(Panel(f"[bold red]💥 执行出错:[/bold red] {str(e)}", border_style="red"))
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_inquiry_flow()

