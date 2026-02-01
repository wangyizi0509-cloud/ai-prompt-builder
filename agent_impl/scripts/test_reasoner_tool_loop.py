"""
测试 deepseek-reasoner 的多轮工具调用（验证是否需要 reasoning_content 回传）
"""

import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_date",
            "description": "获取当前日期",
            "parameters": {"type": "object", "properties": {}},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市名称"},
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD"},
                },
                "required": ["location", "date"],
            },
        }
    },
]

messages = [
    {"role": "user", "content": "杭州明天天气怎么样？帮我查一下。"}
]

print("=" * 60)
print("测试 deepseek-reasoner 多轮工具调用")
print("=" * 60)

# 第一轮
print("\n第一轮调用")
response1 = client.chat.completions.create(
    model="deepseek-reasoner",
    messages=messages,
    tools=tools,
)

msg1 = response1.choices[0].message
reasoning1 = getattr(msg1, "reasoning_content", None)
tool_calls1 = msg1.tool_calls

print(f"Content: {msg1.content}")
print(f"Reasoning: {reasoning1[:100] if reasoning1 else 'None'}...")
print(f"Tool calls: {[tc.function.name for tc in (tool_calls1 or [])]}")

if tool_calls1:
    # 添加 assistant 消息
    assistant_msg = {
        "role": "assistant",
        "content": msg1.content or "",
    }
    if reasoning1:
        assistant_msg["reasoning_content"] = reasoning1
    assistant_msg["tool_calls"] = [
        {
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
        }
        for tc in tool_calls1
    ]
    messages.append(assistant_msg)
    
    # 执行工具
    for tc in tool_calls1:
        if tc.function.name == "get_date":
            from datetime import datetime
            result = datetime.now().strftime("%Y-%m-%d")
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
            print(f"\n执行工具 {tc.function.name}: {result}")
    
    # 第二轮
    print("\n第二轮调用（包含 reasoning_content）")
    try:
        response2 = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=messages,
            tools=tools,
        )
        
        msg2 = response2.choices[0].message
        reasoning2 = getattr(msg2, "reasoning_content", None)
        tool_calls2 = msg2.tool_calls
        
        print(f"✓ 成功")
        print(f"Content: {msg2.content}")
        print(f"Reasoning: {reasoning2[:100] if reasoning2 else 'None'}...")
        print(f"Tool calls: {[tc.function.name for tc in (tool_calls2 or [])]}")
        
        print("\n✓ deepseek-reasoner 支持多轮工具调用！")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        if "reasoning_content" in str(e).lower():
            print("⚠ reasoner 的工具调用也需要 reasoning_content 回传")
else:
    print("\n第一轮没有工具调用")
