"""
直接使用 OpenAI SDK 测试 reasoning_content 返回
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)

print("=" * 60)
print("测试 1: deepseek-chat + thinking:enabled")
print("=" * 60)

response1 = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "2+2 等于几？"}],
    extra_body={"thinking": {"type": "enabled"}},
)

msg1 = response1.choices[0].message
print(f"Content: {msg1.content}")
print(f"Has reasoning_content: {hasattr(msg1, 'reasoning_content')}")
if hasattr(msg1, 'reasoning_content') and msg1.reasoning_content:
    print(f"Reasoning content length: {len(msg1.reasoning_content)}")
    print(f"Reasoning content (preview): {msg1.reasoning_content[:200]}...")
else:
    print("No reasoning_content attribute")

print(f"\nUsage: {response1.usage}")

print("\n" + "=" * 60)
print("测试 2: deepseek-reasoner")
print("=" * 60)

response2 = client.chat.completions.create(
    model="deepseek-reasoner",
    messages=[{"role": "user", "content": "3+3 等于几？"}],
)

msg2 = response2.choices[0].message
print(f"Content: {msg2.content}")
print(f"Has reasoning_content: {hasattr(msg2, 'reasoning_content')}")
if hasattr(msg2, 'reasoning_content') and msg2.reasoning_content:
    print(f"Reasoning content length: {len(msg2.reasoning_content)}")
    print(f"Reasoning content (preview): {msg2.reasoning_content[:200]}...")
else:
    print("No reasoning_content attribute")

print(f"\nUsage: {response2.usage}")

print("\n" + "=" * 60)
print("测试 3: deepseek-chat + thinking:enabled + 工具调用")
print("=" * 60)

response3 = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "今天是几号？"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_date",
            "description": "获取当前日期",
            "parameters": {"type": "object", "properties": {}},
        }
    }],
    extra_body={"thinking": {"type": "enabled"}},
)

msg3 = response3.choices[0].message
print(f"Content: {msg3.content}")
print(f"Has reasoning_content: {hasattr(msg3, 'reasoning_content')}")
if hasattr(msg3, 'reasoning_content') and msg3.reasoning_content:
    print(f"Reasoning content length: {len(msg3.reasoning_content)}")
    print(f"Reasoning content (preview): {msg3.reasoning_content[:200]}...")
else:
    print("No reasoning_content attribute")

print(f"Tool calls: {[tc.function.name for tc in (msg3.tool_calls or [])]}")
print(f"\nUsage: {response3.usage}")
