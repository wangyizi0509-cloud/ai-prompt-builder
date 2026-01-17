#!/usr/bin/env python3
"""
真实 API 调用测试：验证对话压缩与归档机制

约束：
- 不打印/不泄露任何 .env 内容或 API key
- 只输出关键字段，避免读取完整 messages/报告正文
"""

from __future__ import annotations

import os
import sys
import json
import datetime as dt
from dataclasses import dataclass
from typing import Any, Optional


ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
AGENT_DIR = os.path.join(ROOT_DIR, "agent_impl")


# -----------------------------
# 追踪 LLM 调用（只记录关键信息）
# -----------------------------

@dataclass
class InvokeRecord:
    idx: int
    agent: str
    model: str
    provider: str
    tool_calls: int


class TracedLLM:
    def __init__(self, llm: Any, *, agent: str, records: list[InvokeRecord]):
        self._llm = llm
        self._agent = agent
        self._records = records

    def bind_tools(self, tools: list[Any], *args: Any, **kwargs: Any) -> "TracedLLM":
        bound = self._llm.bind_tools(tools, *args, **kwargs)
        return TracedLLM(bound, agent=self._agent, records=self._records)

    def invoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        resp = self._llm.invoke(prompt, *args, **kwargs)

        tool_calls = getattr(resp, "tool_calls", None) or []
        tool_calls_count = len(tool_calls) if isinstance(tool_calls, list) else 1

        model = getattr(self._llm, "model_name", None) or getattr(self._llm, "model", "") or ""
        provider = os.getenv("LLM_PROVIDER", "") or ""

        self._records.append(
            InvokeRecord(
                idx=len(self._records) + 1,
                agent=self._agent,
                model=str(model),
                provider=str(provider),
                tool_calls=tool_calls_count,
            )
        )
        return resp

    def __getattr__(self, item: str) -> Any:
        return getattr(self._llm, item)


def _patch_get_llm(records: list[InvokeRecord]) -> None:
    from config import get_llm as real_get_llm  # type: ignore

    def make(agent_name: str):
        def _get_llm(temperature: float = 0.7):
            return TracedLLM(real_get_llm(temperature=temperature), agent=agent_name, records=records)
        return _get_llm

    from graph.nodes import main_agent as mod_main  # type: ignore
    from graph.nodes import status_agent as mod_status  # type: ignore
    from graph.nodes import plan_agent as mod_plan  # type: ignore
    from graph.nodes import guide_agent as mod_guide  # type: ignore
    from graph.nodes import organize_agent as mod_org  # type: ignore

    mod_main.get_llm = make("main_agent")  # type: ignore[attr-defined]
    mod_status.get_llm = make("status_agent")  # type: ignore[attr-defined]
    mod_plan.get_llm = make("plan_agent")  # type: ignore[attr-defined]
    mod_guide.get_llm = make("guide_agent")  # type: ignore[attr-defined]
    mod_org.get_llm = make("organize_agent")  # type: ignore[attr-defined]

    try:
        from onboarding import onboarding_agent as mod_onb  # type: ignore
        mod_onb.get_llm = make("onboarding_agent")  # type: ignore[attr-defined]
    except Exception:
        pass


# -----------------------------
# 用户画像与回答生成
# -----------------------------

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
    if "聊天" in q or "截图" in q or "记录" in q:
        return (
            "最近聊天摘录：\n"
            "1) 我：\"你最近项目忙吗？\" 她：\"有点忙，但还好。\"\n"
            "2) 她：\"周五要加班\" 我：\"辛苦了，注意休息\"\n"
            "3) 我：\"下周有空一起吃个饭吗？\" 她：\"最近可能排得满，改天吧\""
        )
    if "职业" in q or "工作" in q:
        return USER_PROFILE["user"]["job"]
    if "城市" in q or "地点" in q:
        return USER_PROFILE["user"]["city"]
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


def get_main_intents() -> list[str]:
    return [
        "帮我分析一下现在的情况。我和她是同事，认识3个月。"
        "平时茶水间会聊天，微信一周2-3次。她偶尔主动分享工作动态，"
        "但很少主动约。最近她说项目很忙。我不确定她是否单身，"
        "想稳妥推进。",
        "给我一个具体的行动计划。目标是下周找机会约她吃饭，"
        "不油腻、不暴露需求感，最好能自然过渡到私下见面。",
        "下周的具体行动步骤是什么？请给我可执行的细节，"
        "比如聊天节奏、时间点和一句话话术示例。",
    ]


# -----------------------------
# 检查点输出（5-10 行）
# -----------------------------

def _count_atomic(mem: dict) -> int:
    return len(mem or [])


def _safe_memory_summary(layer1: dict) -> str:
    full = (layer1 or {}).get("full_data", {})
    user_info = full.get("user_info", {})
    crush_info = full.get("crush_info", {})
    both_info = full.get("both_info", {})
    user_count = _count_atomic(user_info.get("user_provide", [])) + _count_atomic(user_info.get("fact", [])) + _count_atomic(user_info.get("ai_provide", []))
    crush_count = _count_atomic(crush_info.get("user_provide", [])) + _count_atomic(crush_info.get("fact", [])) + _count_atomic(crush_info.get("ai_provide", []))
    both_count = _count_atomic(both_info.get("user_provide", [])) + _count_atomic(both_info.get("fact", [])) + _count_atomic(both_info.get("ai_provide", []))
    return f"user={user_count}, crush={crush_count}, both={both_count}"


def print_checkpoint(turn: int, state: dict, *, compression_needed: bool) -> None:
    layer1 = state.get("layer1_memory", {}) or {}
    layer2 = state.get("layer2_memory", {}) or {}
    layer3 = state.get("layer3_memory", {}) or {}
    queue = state.get("maintenance_queue", []) or []

    summaries = layer3.get("conversation_summaries", []) or []
    all_messages = layer3.get("all_messages", []) or []
    dynamic_intels = layer2.get("dynamic_intels", []) or []

    print(f"=== 轮次 {turn} 检查点 ===")
    print(f"- 当前 Agent: {state.get('current_agent', 'none')}")
    print(f"- next_action: {state.get('next_action', 'none')}")
    print(f"- 压缩触发检查: {compression_needed}")
    print(f"- Layer1 记忆摘要: { _safe_memory_summary(layer1) }")
    print(f"- Layer2 动态情报数: {len(dynamic_intels)}")
    print(f"- Layer3 对话摘要数: {len(summaries)}")
    print(f"- Layer3 消息数: {len(all_messages)}")
    print(f"- 维护队列长度: {len(queue)}")
    print(f"- Layer3 总轮次: {layer3.get('total_turns', 0)}")


# -----------------------------
# 主流程
# -----------------------------

def _run_turn(workflow: Any, state: dict, user_message: str, *, thread_id: str) -> dict:
    state["user_message"] = user_message
    state["messages"] = (state.get("messages", []) or []) + [{"role": "user", "content": user_message}]
    # 提前同步到 layer3_memory，确保本轮压缩检查能看到最新轮次
    from graph.state import sync_new_messages_to_fullstore  # type: ignore
    sync_updates = sync_new_messages_to_fullstore(state)
    if sync_updates:
        state.update(sync_updates)
    state["debug_log"] = []
    state["inquiry_card"] = None
    state["pending_questions"] = []
    state["pending_responses"] = []
    state["last_response_for_continuity"] = None
    return workflow.invoke(state, config={"configurable": {"thread_id": thread_id}})


def main() -> int:
    sys.path.insert(0, AGENT_DIR)

    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(AGENT_DIR, ".env"))
    os.environ["STUDIO_SYNC_MAINTENANCE"] = "1"

    records: list[InvokeRecord] = []
    _patch_get_llm(records)

    from graph.workflow import get_workflow  # type: ignore
    from graph.state import create_initial_state  # type: ignore
    from graph.archive_manager import check_layer3_compression_needed  # type: ignore

    workflow = get_workflow()
    thread_id = f"compression_real_api_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    main_intents = get_main_intents()

    # Turn 1: 初始触发（Onboarding）
    state = create_initial_state("我想追公司里的一个女同事，但不知道怎么开口。")
    result = workflow.invoke(state, config={"configurable": {"thread_id": thread_id}})
    print_checkpoint(1, result, compression_needed=check_layer3_compression_needed(result))

    # Turn 2-10
    current = result
    for turn in range(2, 11):
        inquiry_card = current.get("inquiry_card")
        onboarding_completed = bool(current.get("onboarding_completed"))

        if inquiry_card:
            user_message = build_inquiry_answer(inquiry_card)
        elif not onboarding_completed:
            user_message = build_inquiry_answer(None)
        else:
            user_message = main_intents.pop(0) if main_intents else "谢谢，继续。"

        current = _run_turn(workflow, current, user_message, thread_id=thread_id)
        print_checkpoint(turn, current, compression_needed=check_layer3_compression_needed(current))

        if not inquiry_card and onboarding_completed and not main_intents:
            break

    # --------- 结果验证 ---------
    agent_set = sorted({r.agent for r in records})
    organize_called = any(r.agent == "organize_agent" for r in records)

    layer1 = current.get("layer1_memory", {}) or {}
    layer2 = current.get("layer2_memory", {}) or {}
    layer3 = current.get("layer3_memory", {}) or {}

    summaries = layer3.get("conversation_summaries", []) or []
    dynamic_intels = layer2.get("dynamic_intels", []) or []

    report = {
        "agents_called": agent_set,
        "organize_agent_called": organize_called,
        "conversation_summaries": len(summaries),
        "layer1_update_count": layer1.get("update_count", 0),
        "layer2_dynamic_intels": len(dynamic_intels),
        "layer3_total_turns": layer3.get("total_turns", 0),
        "onboarding_completed": bool(current.get("onboarding_completed")),
    }

    print("\n=== 最终测试摘要 ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
