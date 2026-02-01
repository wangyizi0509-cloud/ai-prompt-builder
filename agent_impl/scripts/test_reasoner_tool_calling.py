"""
测试 deepseek-reasoner 是否支持工具调用（V3.2）
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
]

print("=" * 60)
print("测试 deepseek-reasoner 是否支持工具调用")
print("=" * 60)

messages = [
    {"role": "user", "content": "今天是几号？"}
]

try:
    response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=messages,
        tools=tools,
    )
    
    msg = response.choices[0].message
    reasoning_content = getattr(msg, "reasoning_content", None)
    tool_calls = msg.tool_calls
    
    print(f"✓ API 调用成功")
    print(f"Content: {msg.content}")
    print(f"Reasoning content: {reasoning_content[:100] if reasoning_content else 'None'}...")
    print(f"Tool calls: {[tc.function.name for tc in (tool_calls or [])]}")
    
    if tool_calls:
        print("\n✓ deepseek-reasoner 支持工具调用！")
    else:
        print("\n⚠ deepseek-reasoner 没有调用工具（可能是模型选择不调用，或者不支持）")
        
except Exception as e:
    print(f"\n❌ 错误: {e}")
    if "function calling" in str(e).lower() or "not support" in str(e).lower():
        print("✗ deepseek-reasoner 不支持工具调用")
    else:
        print("可能是其他错误，需要进一步排查")
