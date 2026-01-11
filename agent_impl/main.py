"""
Crushe AI Agent 入口文件
提供交互式对话界面
"""

import sys
import os

# 添加当前目录到路径，确保模块可以导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt

from graph.state import create_initial_state, AgentState
from graph.workflow import get_workflow


console = Console()


def print_welcome():
    """打印欢迎信息"""
    welcome_text = """
# 👋 你好，我是小话

你的 AI 恋爱军师，专门帮你解决和 Crush 相处的问题。

**我能帮你：**
- 📊 分析你们目前的关系状态
- 📋 制定追求策略和行动规划  
- 📝 给出具体的行动指南和话术

**开始聊天吧！** 告诉我你的情况，或者直接问我问题。

---
输入 `quit` 或 `exit` 退出对话
输入 `reset` 重新开始
输入 `status` 查看当前状态
    """
    console.print(Panel(Markdown(welcome_text), title="Crushe AI", border_style="cyan"))


def print_response(response: str):
    """打印 AI 回复"""
    console.print()
    console.print(Panel(
        Markdown(response),
        title="💬 小话",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


def print_inquiry_card(inquiry_card: dict):
    """打印问题卡片（特殊格式，模拟前端渲染）"""
    if not inquiry_card or not inquiry_card.get("questions"):
        return
    
    console.print()
    console.print(Panel(
        "[bold cyan]📋 请回答以下问题[/bold cyan]",
        border_style="cyan",
    ))
    
    for q in inquiry_card.get("questions", []):
        q_type = q.get("type", "free_input_question")
        question = q.get("question", "")
        q_id = q.get("id", "")
        required = "* " if q.get("required") else ""
        
        console.print()
        console.print(f"[bold]{required}{question}[/bold]")
        
        # 支持旧版本的 "text" 类型（向后兼容）
        if q_type == "free_input_question" or q_type == "text":
            placeholder = q.get("placeholder", "请输入...")
            console.print(f"  [dim]💬 {placeholder}[/dim]")
        
        elif q_type == "single_choice":
            options = q.get("options", [])
            for i, opt in enumerate(options):
                console.print(f"  [dim]○[/dim] {opt.get('label', '')}")
        
        elif q_type == "multi_choice" or q_type == "multiple_choice":
            options = q.get("options", [])
            for i, opt in enumerate(options):
                console.print(f"  [dim]☐[/dim] {opt.get('label', '')}")
        
        elif q_type == "scale":
            min_label = q.get("min_label", "1")
            max_label = q.get("max_label", "5")
            console.print(f"  [dim]{min_label} ◀ ● ● ● ● ● ▶ {max_label}[/dim]")
    
    console.print()
    console.print("[dim]（在终端中请直接输入你的回答）[/dim]")
    console.print()


def print_status(state: AgentState):
    """打印当前状态"""
    console.print()
    console.print(Panel(
        f"""
**用户画像**: {state.get('user_profile', {}) or '暂无'}

**现状分析**: {'已生成' if state.get('status_report') else '未生成'}

**行动规划**: {'已生成' if state.get('action_plan') else '未生成'}

**行动指南**: {'已生成' if state.get('action_guide') else '未生成'}

**对话轮数**: {len(state.get('messages', [])) // 2}
        """,
        title="📊 当前状态",
        border_style="yellow",
    ))
    console.print()


def run_conversation():
    """运行对话循环"""
    print_welcome()
    
    # 获取工作流
    workflow = get_workflow()
    
    # 初始化状态
    state = None
    
    while True:
        try:
            # 获取用户输入
            user_input = Prompt.ask("[bold cyan]你[/bold cyan]").strip()
            
            if not user_input:
                continue
            
            # 处理特殊命令
            if user_input.lower() in ['quit', 'exit', 'q']:
                console.print("\n[yellow]再见！有问题随时回来找我 👋[/yellow]\n")
                break
            
            if user_input.lower() == 'reset':
                state = None
                console.print("\n[yellow]对话已重置，重新开始吧！[/yellow]\n")
                continue
            
            if user_input.lower() == 'status':
                if state:
                    print_status(state)
                else:
                    console.print("\n[yellow]还没有开始对话，先说点什么吧！[/yellow]\n")
                continue
            
            # 构建输入状态
            if state is None:
                # 首次对话
                input_state = create_initial_state(user_input)
            else:
                # 后续对话，更新用户消息
                input_state = state.copy()
                input_state["user_message"] = user_input
                # 添加用户消息到历史
                input_state["messages"] = state.get("messages", []) + [
                    {"role": "user", "content": user_input}
                ]
            
            # 运行工作流
            console.print("\n[dim]思考中...[/dim]")
            
            result = workflow.invoke(input_state)
            
            # 更新状态
            state = result
            
            # 获取并打印回复
            response = result.get("assistant_response", "")
            if response:
                print_response(response)
            else:
                console.print("\n[yellow]（没有回复）[/yellow]\n")
            
            # 如果有问题卡片，显示问题卡片
            inquiry_card = result.get("inquiry_card")
            if inquiry_card:
                print_inquiry_card(inquiry_card)
        
        except KeyboardInterrupt:
            console.print("\n\n[yellow]对话中断，再见！[/yellow]\n")
            break
        
        except Exception as e:
            console.print(f"\n[red]发生错误: {e}[/red]")
            console.print("[dim]请检查 API Key 是否正确配置[/dim]\n")
            
            # 在调试模式下打印完整错误
            import traceback
            if os.getenv("DEBUG"):
                traceback.print_exc()


def main():
    """主函数"""
    # 检查环境变量
    if not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        console.print(Panel(
            """
[red]未检测到 API Key！[/red]

请先配置环境变量：

1. 复制 `env.example` 为 `.env`
2. 填入你的 API Key

例如：
```
cp env.example .env
# 编辑 .env 文件，填入 DEEPSEEK_API_KEY
```
            """,
            title="⚠️ 配置错误",
            border_style="red",
        ))
        return
    
    run_conversation()


if __name__ == "__main__":
    main()

