#!/usr/bin/env python3
"""
通过 LangSmith Studio (langgraph dev) 跑真实测试用例
目标：在 Studio 里可视化完整链路 + 压缩归档
"""

from __future__ import annotations

import json
import uuid
import urllib.request
import sys
import os
from typing import Optional


ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
AGENT_DIR = os.path.join(ROOT_DIR, "agent_impl")
STUDIO_BASE = "http://127.0.0.1:2024"
ASSISTANT_ID = "2fc6ac8a-846e-51c4-9b55-ae03499aac03"

sys.path.insert(0, AGENT_DIR)
from graph.state import create_initial_state  # noqa: E402
from utils.message_utils import count_user_turns  # noqa: E402


USER_PROFILE = {
    "user": {
        "name": "小明",
        "gender": "男",
        "age": "26",
        "city": "北京",
        "job": "软件工程师",
        "experience_level": "进阶",
    },
    "crush": {
        "name": "小红",
        "gender": "女",
        "age": "25",
        "relation": "同事",
        "known_duration": "3个月",
    },
    "context": {
        "goal": "想找机会约她吃饭并逐步升温",
        "pain_points": "不确定她是否有男朋友，担心被拒后尴尬",
        "interaction": "一周微信聊2-3次，线下茶水间会打招呼",
        "signals": "她偶尔主动分享工作动态，但很少主动约",
        "constraints": "不油腻、不暴露需求感、不过早表白",
    },
}


def _post_json(url: str, payload: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if not data:
        return {}
    return json.loads(data)


def _get_json(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def _answer_for_question(q: str) -> str:
    q = q or ""
    if "性别" in q and "对方" not in q and "Ta" not in q:
        return USER_PROFILE["user"]["gender"]
    if "出生" in q:
        return "1999"
    if "年龄" in q and ("对方" in q or "Ta" in q or "她" in q):
        return USER_PROFILE["crush"]["age"]
    if "年龄" in q:
        return USER_PROFILE["user"]["age"]
    if "昵称" in q or "备注" in q or "名字" in q:
        return USER_PROFILE["crush"]["name"]
    if "Ta 的性别" in q or ("对方" in q and "性别" in q):
        return USER_PROFILE["crush"]["gender"]
    if "认识" in q or "相识" in q:
        return "同事，项目对接认识，平时在公司会碰面"
    if "头疼" in q or "痛点" in q or "困扰" in q:
        return USER_PROFILE["context"]["pain_points"]
    if "经验" in q or "阶段" in q:
        return USER_PROFILE["user"]["experience_level"]
    if "职业" in q or "工作" in q:
        return USER_PROFILE["user"]["job"]
    if "城市" in q or "地点" in q:
        return USER_PROFILE["user"]["city"]
    if "聊天" in q or "截图" in q or "记录" in q:
        return (
            "最近聊天摘录：\n"
            "1) 我：\"你最近项目忙吗？\" 她：\"有点忙，但还好。\"\n"
            "2) 她：\"周五要加班\" 我：\"辛苦了，注意休息\"\n"
            "3) 我：\"下周有空一起吃个饭吗？\" 她：\"最近可能排得满，改天吧\""
        )
    return (
        "我们是同事，认识3个月。她25岁，性格偏安静。"
        "一周微信聊2-3次，线下茶水间会打招呼。"
        "我想约她吃饭但不想太冒进。"
    )


def build_inquiry_answer(inquiry_card: Optional[dict]) -> str:
    if not inquiry_card or not inquiry_card.get("questions"):
        return (
            "我叫小明，男，26，北京，软件工程师。"
            "她叫小红，女，25，同事，认识3个月。"
            "我想约她吃饭但怕尴尬，想稳妥推进。"
        )
    parts = []
    for idx, q in enumerate(inquiry_card.get("questions", []), start=1):
        q_text = q.get("question", "") if isinstance(q, dict) else str(q)
        ans = _answer_for_question(q_text)
        parts.append(f"{idx}. {q_text}\n答：{ans}")
    return "\n".join(parts)


def _safe_memory_summary(layer1: dict) -> str:
    full = (layer1 or {}).get("full_data", {})
    user_info = full.get("user_info", {})
    crush_info = full.get("crush_info", {})
    both_info = full.get("both_info", {})

    def count(mem: dict) -> int:
        return len(mem.get("user_provide", [])) + len(mem.get("fact", [])) + len(mem.get("ai_provide", []))

    return f"user={count(user_info)}, crush={count(crush_info)}, both={count(both_info)}"


def print_checkpoint(turn: int, values: dict) -> None:
    layer1 = values.get("layer1_memory", {}) or {}
    layer2 = values.get("layer2_memory", {}) or {}
    layer3 = values.get("layer3_memory", {}) or {}
    queue = values.get("maintenance_queue", []) or []

    summaries = layer3.get("conversation_summaries", []) or []
    all_messages = layer3.get("all_messages", []) or []
    dynamic_intels = layer2.get("dynamic_intels", []) or []

    print(f"=== 轮次 {turn} 检查点 ===")
    print(f"- 当前 Agent: {values.get('current_agent', 'none')}")
    print(f"- next_action: {values.get('next_action', 'none')}")
    print(f"- Layer1 记忆摘要: {_safe_memory_summary(layer1)}")
    print(f"- Layer2 动态情报数: {len(dynamic_intels)}")
    print(f"- Layer3 对话摘要数: {len(summaries)}")
    print(f"- Layer3 消息数: {len(all_messages)}")
    print(f"- 维护队列长度: {len(queue)}")
    print(f"- 当前用户轮次: {count_user_turns(all_messages)}")


def main() -> int:
    thread_id = str(uuid.uuid4())
    _post_json(f"{STUDIO_BASE}/threads", {"thread_id": thread_id})

    messages = [
        "我想追公司里的一个女同事，但不知道怎么开口。",
        "帮我分析一下现在的情况。我和她是同事，认识3个月。"
        "平时茶水间会聊天，微信一周2-3次。她偶尔主动分享工作动态，"
        "但很少主动约。最近她说项目很忙。我不确定她是否单身，"
        "想稳妥推进。",
        "给我一个具体的行动计划。目标是下周找机会约她吃饭，"
        "不油腻、不暴露需求感，最好能自然过渡到私下见面。",
        "下周的具体行动步骤是什么？请给我可执行的细节，"
        "比如聊天节奏、时间点和一句话话术示例。",
    ]

    # Turn 1: 完整初始状态
    init_state = create_initial_state(messages[0])
    _post_json(
        f"{STUDIO_BASE}/threads/{thread_id}/runs/wait",
        {
            "assistant_id": ASSISTANT_ID,
            "input": init_state,
            "config": {"configurable": {"thread_id": thread_id}, "recursion_limit": 80},
        },
    )
    values = _get_json(f"{STUDIO_BASE}/threads/{thread_id}/state").get("values", {})
    print_checkpoint(1, values)

    # Turn 2+ : 按需回答卡片，再推进主流程
    turn = 2
    msg_idx = 1
    while turn <= 10:
        inquiry_card = values.get("inquiry_card")
        onboarding_completed = bool(values.get("onboarding_completed"))

        if inquiry_card:
            user_message = build_inquiry_answer(inquiry_card)
        elif msg_idx < len(messages):
            user_message = messages[msg_idx]
            msg_idx += 1
        else:
            user_message = "好的，继续。"

        # 拉取最新状态作为输入，避免 messages 丢失
        current_state = _get_json(f"{STUDIO_BASE}/threads/{thread_id}/state").get("values", {}) or {}
        next_state = dict(current_state)
        next_state["user_message"] = user_message
        next_state["messages"] = (current_state.get("messages", []) or []) + [{"role": "user", "content": user_message}]
        next_state["_iteration_count"] = 0
        next_state["debug_log"] = []
        next_state["inquiry_card"] = None
        next_state["pending_questions"] = []
        next_state["pending_responses"] = []
        next_state["last_response_for_continuity"] = None

        _post_json(
            f"{STUDIO_BASE}/threads/{thread_id}/runs/wait",
            {
                "assistant_id": ASSISTANT_ID,
                "input": next_state,
                "config": {"configurable": {"thread_id": thread_id}, "recursion_limit": 80},
            },
        )
        values = _get_json(f"{STUDIO_BASE}/threads/{thread_id}/state").get("values", {})
        print_checkpoint(turn, values)

        if onboarding_completed and not inquiry_card and msg_idx >= len(messages):
            break
        turn += 1

    print("\n✅ Studio 测试完成")
    print(f"thread_id: {thread_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
