"""
Demo: 比较 bind_tools vs 不 bind_tools 的模型行为

用法:
  python scripts/demo_tool_binding.py
"""

import os
import sys

# 确保能从 agent_impl 根目录导入
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import get_llm
from skills.tool import create_inquiry_only_loader


PROMPT_SUFFICIENT = """
你是一个分析助手。请先评估信息是否充足：
如果信息充足（Confidence >= 70%），**禁止调用任何工具**，只输出一段简短 JSON：
{"action": "report", "reason": "info_sufficient"}

如果信息不足（Confidence < 70%），调用工具获取提问指令。

信息如下：
1) 用户给了完整背景
2) 有完整聊天记录
3) 关键冲突点清晰
"""

PROMPT_INSUFFICIENT = """
你是一个分析助手。请先评估信息是否充足：
如果信息不足（Confidence < 70%），调用工具获取提问指令。
如果信息充足（Confidence >= 70%），输出 JSON：
{"action": "report", "reason": "info_sufficient"}

信息如下：
1) 只有一句话，没有聊天记录
2) 没有关键时间节点
3) 不知道对方具体反应
"""

def print_result(tag, response):
    content = getattr(response, "content", "") or ""
    tool_calls = getattr(response, "tool_calls", []) or []
    finish_reason = ""
    meta = getattr(response, "response_metadata", {}) or {}
    finish_reason = meta.get("finish_reason", "")

    print("=" * 80)
    print(tag)
    print("- finish_reason:", finish_reason)
    print("- content:", content.strip()[:300])
    print("- tool_calls:", tool_calls)


def main():
    llm = get_llm(temperature=0.2)

    # Case A: 信息充足
    resp_no_tools = llm.invoke(PROMPT_SUFFICIENT)
    print_result("No tools / sufficient", resp_no_tools)

    inquiry_tool = create_inquiry_only_loader()
    llm_with_tools = llm.bind_tools([inquiry_tool])
    resp_with_tools = llm_with_tools.invoke(PROMPT_SUFFICIENT)
    print_result("With bind_tools / sufficient", resp_with_tools)

    # Case B: 信息不足
    resp_no_tools = llm.invoke(PROMPT_INSUFFICIENT)
    print_result("No tools / insufficient", resp_no_tools)

    resp_with_tools = llm_with_tools.invoke(PROMPT_INSUFFICIENT)
    print_result("With bind_tools / insufficient", resp_with_tools)


if __name__ == "__main__":
    main()
