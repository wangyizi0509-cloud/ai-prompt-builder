"""
直接使用 OpenAI SDK 测试 DeepSeek thinking mode + tool calling
用于验证 reasoning_content 的正确传递方式
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

# 定义工具
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

# 第一轮：用户提问
messages = [
    {"role": "user", "content": "杭州明天天气怎么样？帮我查一下。"}
]

print("=" * 60)
print("第一轮调用")
print("=" * 60)

response1 = client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,
    tools=tools,
    extra_body={"thinking": {"type": "enabled"}},
)

msg1 = response1.choices[0].message
reasoning1 = getattr(msg1, "reasoning_content", None)
tool_calls1 = msg1.tool_calls

print(f"Content: {msg1.content}")
print(f"Reasoning content: {reasoning1[:100] if reasoning1 else 'None'}...")
print(f"Tool calls: {[tc.function.name for tc in (tool_calls1 or [])]}")

# 执行工具
if tool_calls1:
    messages.append({
        "role": "assistant",
        "content": msg1.content,
        "reasoning_content": reasoning1,  # 关键：必须包含 reasoning_content
        "tool_calls": [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
            }
            for tc in tool_calls1
        ],
    })
    
    # 执行 get_date 工具
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
    
    # 第二轮：继续调用
    print("\n" + "=" * 60)
    print("第二轮调用（包含 reasoning_content）")
    print("=" * 60)
    
    response2 = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        tools=tools,
        extra_body={"thinking": {"type": "enabled"}},
    )
    
    msg2 = response2.choices[0].message
    reasoning2 = getattr(msg2, "reasoning_content", None)
    tool_calls2 = msg2.tool_calls
    
    print(f"Content: {msg2.content}")
    print(f"Reasoning content: {reasoning2[:100] if reasoning2 else 'None'}...")
    print(f"Tool calls: {[tc.function.name for tc in (tool_calls2 or [])]}")
    
    print("\n✓ 测试成功！")
