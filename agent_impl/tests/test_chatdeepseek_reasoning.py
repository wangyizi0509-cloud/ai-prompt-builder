"""
测试 ChatDeepSeek 对 deepseek-reasoner reasoning_content 的支持
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage

load_dotenv()

print("=" * 60)
print("测试：ChatDeepSeek + deepseek-reasoner")
print("=" * 60)

llm = ChatDeepSeek(
    model="deepseek-reasoner",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL"),
    temperature=0.2,
)

prompt = "请简要判断 2+2 是否等于 4，并给出结论。"
response = llm.invoke([HumanMessage(content=prompt)])

print(f"\nResponse 类型: {type(response)}")
print(f"Response 类名: {response.__class__.__name__}")
print(f"\nContent: {response.content}")
print(f"\nAdditional kwargs keys: {list(response.additional_kwargs.keys())}")
print(f"\nResponse metadata keys: {list(response.response_metadata.keys())}")

# 检查 reasoning_content
if "reasoning_content" in response.additional_kwargs:
    reasoning_content = response.additional_kwargs["reasoning_content"]
    print(f"\n✓ 找到 reasoning_content!")
    print(f"  长度: {len(reasoning_content)}")
    print(f"  预览: {reasoning_content[:200]}...")
else:
    print("\n✗ 未找到 reasoning_content")

# 检查 usage 信息
if "token_usage" in response.response_metadata:
    usage = response.response_metadata["token_usage"]
    print(f"\nToken 使用:")
    print(f"  Total: {usage.get('total_tokens')}")
    if "completion_tokens_details" in usage:
        details = usage["completion_tokens_details"]
        reasoning_tokens = details.get("reasoning_tokens")
        if reasoning_tokens:
            print(f"  Reasoning tokens: {reasoning_tokens}")

print("\n" + "=" * 60)
