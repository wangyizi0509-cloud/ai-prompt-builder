"""
测试 LangChain ChatOpenAI 对 deepseek-reasoner reasoning_content 的支持
"""

import os
import sys
import json

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

load_dotenv()

print("=" * 60)
print("测试：LangChain ChatOpenAI + deepseek-reasoner")
print("=" * 60)

llm = ChatOpenAI(
    model="deepseek-reasoner",
    openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
    openai_api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    temperature=0.2,
)

prompt = "请简要判断 2+2 是否等于 4，并给出结论。"
response = llm.invoke([HumanMessage(content=prompt)])

print(f"\nResponse 类型: {type(response)}")
print(f"Response 类名: {response.__class__.__name__}")
print(f"\nResponse attributes:")
for attr in dir(response):
    if not attr.startswith('_'):
        try:
            val = getattr(response, attr)
            if not callable(val) and 'message' not in attr.lower():
                print(f"  {attr}: {type(val).__name__}")
        except:
            pass

print(f"\nContent: {response.content}")
print(f"\nAdditional kwargs: {response.additional_kwargs}")
print(f"\nResponse metadata: {response.response_metadata}")

# 检查 reasoning_content 在不同位置
reasoning_locations = []
if hasattr(response, 'reasoning_content') and response.reasoning_content:
    reasoning_locations.append(('attribute', response.reasoning_content))
if 'reasoning_content' in response.additional_kwargs:
    reasoning_locations.append(('additional_kwargs', response.additional_kwargs['reasoning_content']))
if 'reasoning_content' in response.response_metadata:
    reasoning_locations.append(('response_metadata', response.response_metadata['reasoning_content']))

print(f"\nReasoning content 查找结果:")
if reasoning_locations:
    for loc, content in reasoning_locations:
        print(f"  找到在 {loc}: {content[:100]}...")
else:
    print("  未找到 reasoning_content")

# 检查 usage 信息
if 'usage' in response.response_metadata:
    usage = response.response_metadata['usage']
    print(f"\nUsage 信息:")
    print(f"  Total tokens: {usage.get('total_tokens')}")
    if hasattr(usage, 'completion_tokens_details'):
        details = usage.completion_tokens_details
        print(f"  Reasoning tokens: {details.reasoning_tokens if hasattr(details, 'reasoning_tokens') else 'N/A'}")
