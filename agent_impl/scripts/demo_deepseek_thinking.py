"""
Demo: 验证 DeepSeek Thinking Mode / reasoning_content 是否返回

用法:
  python scripts/demo_deepseek_thinking.py
"""

import os
import sys
import json

from dotenv import load_dotenv

# 确保能从 agent_impl 根目录导入
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from langchain_openai import ChatOpenAI


def main():
    load_dotenv()
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY")

    llm = ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=0.2,
        # DeepSeek thinking mode（官方文档推荐通过 extra_body 传参）
        extra_body={"thinking": {"type": "enabled"}},
    )

    prompt = "请简要判断 2+2 是否等于 4，并给出结论。"
    response = llm.invoke(prompt)

    # LangChain 会把 reasoning_content 放在 additional_kwargs 里（DeepSeek 返回字段）
    reasoning = getattr(response, "additional_kwargs", {}).get("reasoning_content")
    content = getattr(response, "content", "")
    metadata = getattr(response, "response_metadata", {})

    print("model:", model)
    print("finish_reason:", metadata.get("finish_reason"))
    print("has_reasoning_content:", bool(reasoning))
    print("reasoning_content (preview):", (reasoning or "")[:200])
    print("content (preview):", (content or "")[:200])

    # 额外输出可用字段，便于排查
    print("additional_kwargs keys:", list(getattr(response, "additional_kwargs", {}).keys()))
    print("response_metadata keys:", list(metadata.keys()))


if __name__ == "__main__":
    main()
