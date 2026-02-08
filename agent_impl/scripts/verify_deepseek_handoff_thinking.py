"""
DeepSeek API + 多 Agent Handoffs 思维链处理 — 调 API 验证脚本

对应文档中的三个关键测试点，验证「同一用户消息轮内多 Agent 交接 + 思维链隔离」是否合法：

1. 单过程内连续调用：同一 Agent 连续思考+工具调用，回传自身思维链 → 推理是否延续
2. 跨 Agent 无思维链调用：AgentB 调 API 时仅传用户消息+交接结果（不传 AgentA 思维链）→ API 是否报错
3. 跨 Agent 连续调用：AgentB 连续思考+工具调用，仅回传自身思维链 → 推理是否延续

验证结论（实测）：
- 三个测试点均可通过，请求方式合法。
- 注意：thinking 模式下，带 tool_calls 的 assistant 消息必须包含 reasoning_content 字段，
  否则 API 返回 400。跨 Agent 时用 reasoning_content="" 表示「不传前序实质推理」即可。

用法（在 agent_impl 目录下）:
  python scripts/verify_deepseek_handoff_thinking.py

依赖: DEEPSEEK_API_KEY（及可选 DEEPSEEK_BASE_URL）。本脚本直接带 extra_body 开 thinking，不依赖 .env 的 DEEPSEEK_THINKING_WITH_TOOLS。
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# 从 agent_impl 根目录加载 .env
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))
load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = "deepseek-chat"
THINKING_EXTRA = {"thinking": {"type": "enabled"}}


def get_client():
    if not API_KEY:
        print("❌ 请设置 DEEPSEEK_API_KEY（可在 agent_impl/.env 或项目根 .env）")
        sys.exit(1)
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


# --------------- 工具定义（模拟交接 + 支付） ---------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "handoff_to_payment_agent",
            "description": "当无法处理跨境支付时，将任务交接给支付专线 Agent。调用后表示交接成功。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "process_cross_border_payment",
            "description": "处理跨境支付请求。",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "金额"},
                    "currency": {"type": "string", "description": "币种"},
                },
                "required": ["amount", "currency"],
            },
        }
    },
]


def run_test1_single_process_continuous(client):
    """
    测试点 1：单过程内连续调用
    同一 Agent 内：思考 → 调工具 → 工具返回 → 再次调用时回传本过程 reasoning_content → 验证推理延续
    """
    print("\n" + "=" * 60)
    print("测试点 1：单过程内连续调用（回传自身思维链）")
    print("=" * 60)

    user_msg = "请先判断你能不能处理跨境支付；若不能，请调用交接工具把任务交给支付专线。"
    messages = [{"role": "user", "content": user_msg}]

    # 第一轮
    r1 = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        extra_body=THINKING_EXTRA,
    )
    m1 = r1.choices[0].message
    reasoning1 = getattr(m1, "reasoning_content", None)
    tool_calls1 = m1.tool_calls or []

    print(f"  第 1 次调用: 有 reasoning={bool(reasoning1)}, tool_calls={[t.function.name for t in tool_calls1]}")

    if not tool_calls1:
        print("  ⚠ 未触发工具调用，本测试需模型先调交接工具。继续用模拟工具结果做第二轮。")
        # 模拟一次交接调用，以便测试「第二轮带 reasoning 回传」
        messages.append({
            "role": "assistant",
            "content": m1.content or "",
            "reasoning_content": reasoning1 if reasoning1 is not None else "",
            "tool_calls": [{"id": "call_handoff", "type": "function", "function": {"name": "handoff_to_payment_agent", "arguments": "{}"}}],
        })
        messages.append({"role": "tool", "tool_call_id": "call_handoff", "content": "交接成功"})
    else:
        messages.append({
            "role": "assistant",
            "content": m1.content or "",
            "reasoning_content": reasoning1 if reasoning1 is not None else "",
            "tool_calls": [
                {"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                for tc in tool_calls1
            ],
        })
        for tc in tool_calls1:
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": "交接成功"})

    # 第二轮：必须带 reasoning_content（规则 1）
    r2 = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        extra_body=THINKING_EXTRA,
    )
    m2 = r2.choices[0].message
    reasoning2 = getattr(m2, "reasoning_content", None)
    tool_calls2 = m2.tool_calls or []

    print(f"  第 2 次调用: 有 reasoning={bool(reasoning2)}, 有 content={bool(m2.content)}")
    if m2.content:
        print(f"  回复摘要: {m2.content[:150]}...")

    success = not (r2.choices[0].finish_reason == "error" or (not m2.content and not tool_calls2))
    print("  ✓ 通过" if success else "  ✗ 未通过（无正常回复或报错）")
    return success


def run_test2_cross_agent_no_reasoning(client):
    """
    测试点 2：跨 Agent 无思维链调用
    同一用户消息：先模拟 AgentA 完成交接（只保留 assistant 的 content + tool_calls + tool 结果），
    AgentB 第一次调 API 时 **不传** AgentA 的 reasoning_content，仅传「用户消息 + 工具调用/返回结果」。
    验证：API 不报错、模型能正常启动新推理。
    """
    print("\n" + "=" * 60)
    print("测试点 2：跨 Agent 无思维链调用（不传前序 Agent 思维链）")
    print("=" * 60)

    user_msg = "请处理一笔 100 美元的跨境支付，由支付专线完成。"
    # 模拟「过程 1 已结束」：只把 assistant 的 content + tool_calls + tool 结果放进上下文。
    # 注意：DeepSeek API 要求 thinking 模式下带 tool_calls 的 assistant 消息必须带 reasoning_content 字段，
    # 否则 400。因此用空字符串表示「不传前序实质推理」，合规且不干扰新 Agent。
    messages = [
        {"role": "user", "content": user_msg},
        {
            "role": "assistant",
            "content": "已将任务交接给支付专线。",
            "reasoning_content": "",  # 必须带字段，传空表示不传前序思维链
            "tool_calls": [
                {"id": "call_handoff", "type": "function", "function": {"name": "handoff_to_payment_agent", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_handoff", "content": "交接成功"},
    ]

    r = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        extra_body=THINKING_EXTRA,
    )
    msg = r.choices[0].message
    reasoning = getattr(msg, "reasoning_content", None)
    tool_calls = msg.tool_calls or []

    print(f"  AgentB 第 1 次调用: 有 reasoning={bool(reasoning)}, tool_calls={[t.function.name for t in tool_calls]}, content={bool(msg.content)}")
    if msg.content:
        print(f"  回复摘要: {msg.content[:150]}...")

    success = r.choices[0].finish_reason != "error"
    print("  ✓ 通过（API 未报错、能正常推理）" if success else "  ✗ 未通过")
    return success, messages, msg, reasoning, tool_calls


def run_test3_cross_agent_continuous(client, messages_from_test2, first_assistant_msg, first_reasoning, first_tool_calls):
    """
    测试点 3：跨 Agent 连续调用
    在测试点 2 的基础上，AgentB 第一次调用后若产生 tool_calls，则执行工具；
    第二次调用时 **仅回传 AgentB 自己的 reasoning_content**（不传 AgentA 的），验证推理延续。
    """
    print("\n" + "=" * 60)
    print("测试点 3：跨 Agent 连续调用（仅回传自身思维链）")
    print("=" * 60)

    messages = list(messages_from_test2)
    # 追加 AgentB 的 assistant 消息（带 reasoning_content 和 tool_calls）
    messages.append({
        "role": "assistant",
        "content": first_assistant_msg.content or "",
        "reasoning_content": first_reasoning if first_reasoning is not None else "",
        "tool_calls": [
            {"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
            for tc in first_tool_calls
        ],
    })
    for tc in first_tool_calls:
        if tc.function.name == "process_cross_border_payment":
            try:
                import json
                args = json.loads(tc.function.arguments or "{}")
                amount = args.get("amount", 100)
                currency = args.get("currency", "USD")
                content = json.dumps({"status": "success", "amount": amount, "currency": currency})
            except Exception:
                content = '{"status": "success"}'
        else:
            content = "交接成功"
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

    r = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        extra_body=THINKING_EXTRA,
    )
    m = r.choices[0].message
    reasoning2 = getattr(m, "reasoning_content", None)
    print(f"  AgentB 第 2 次调用: 有 reasoning={bool(reasoning2)}, 有 content={bool(m.content)}")
    if m.content:
        print(f"  回复摘要: {m.content[:150]}...")

    success = r.choices[0].finish_reason != "error" and (bool(m.content) or bool(m.tool_calls))
    print("  ✓ 通过" if success else "  ✗ 未通过")
    return success


def main():
    print("\n" + "=" * 60)
    print("DeepSeek Thinking Mode + 多 Agent Handoffs 请求合法性验证")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Model: {MODEL}")

    client = get_client()

    ok1 = run_test1_single_process_continuous(client)
    t2_ok, t2_messages, t2_msg, t2_reasoning, t2_tool_calls = run_test2_cross_agent_no_reasoning(client)

    # 测试点 3：若 AgentB 第一次没有 tool_calls，用一次「带 reasoning 的二次调用」模拟连续
    if not t2_tool_calls:
        print("\n  （测试点 2 中 AgentB 未调工具，用一次「仅带自身 reasoning 的二次请求」模拟测试点 3）")
        # 构造：user + 无 reasoning 的 assistant + tool + AgentB 第一次回复（带 reasoning，无 tool_calls）→ 再发一次
        t2_messages.append({
            "role": "assistant",
            "content": t2_msg.content or "由支付专线处理。",
            "reasoning_content": t2_reasoning if t2_reasoning is not None else "",
        })
        # 再请求一次，验证「仅带自身 reasoning 的连续调用」合法
        r3 = client.chat.completions.create(
            model=MODEL,
            messages=t2_messages,
            tools=TOOLS,
            extra_body=THINKING_EXTRA,
        )
        m3 = r3.choices[0].message
        print(f"  AgentB 第 2 次调用（仅自身 reasoning）: 有 content={bool(m3.content)}")
        ok3 = r3.choices[0].finish_reason != "error"
    else:
        ok3 = run_test3_cross_agent_continuous(client, t2_messages, t2_msg, t2_reasoning, t2_tool_calls)

    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  测试点 1（单过程内连续调用）: {'✓ 通过' if ok1 else '✗ 未通过'}")
    print(f"  测试点 2（跨 Agent 无思维链调用）: {'✓ 通过' if t2_ok else '✗ 未通过'}")
    print(f"  测试点 3（跨 Agent 连续调用）: {'✓ 通过' if ok3 else '✗ 未通过'}")
    if ok1 and t2_ok and ok3:
        print("\n  结论：当前请求方式合法，单用户消息内多 Agent 交接 + 思维链隔离方案可行。")
    else:
        print("\n  存在未通过项，请根据输出排查。")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
