"""
验证“同一 agent 连续提问 <=3 轮；中间发生非提问动作即清零”的新规则。

本脚本只跑 status_agent_node，并使用 FakeLLM，不联网、不跑 E2E。

运行：
  cd agent_impl
  python3 scripts/debug_question_streak_status_agent.py
"""

import json
import sys
from pathlib import Path

AGENT_IMPL_DIR = Path(__file__).resolve().parent.parent
if str(AGENT_IMPL_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_IMPL_DIR))


class _FakeResponse:
    def __init__(self, content: str, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    def bind_tools(self, tools):
        return self

    def invoke(self, prompt: str):
        return _FakeResponse(self._content, tool_calls=[])


def _mk_need_questions_with_card():
    return json.dumps(
        {
            "task_id": "task_001",
            "thought": "need more",
            "need_questions": True,
            "response": "我还差几个关键细节～",
            "report_content": None,
            "inquiry_card": {
                "questions": [
                    {
                        "id": "q1",
                        "type": "free_input_question",
                        "question": "你们认识多久了？最近一次互动是什么？",
                        "options": None,
                        "is_required": True,
                        "purpose": "补齐时间与互动证据",
                    }
                ],
                "intro": "先补齐几个关键细节～",
                "reasoning": "need baseline context",
            },
        },
        ensure_ascii=False,
    )


def _mk_report():
    return json.dumps(
        {
            "task_id": "task_001",
            "thought": "enough",
            "need_questions": False,
            "response": "我来给你一个现状分析结论。",
            "report_content": "## 🧭 情感罗盘\n\n### 当前阶段\n（测试报告）",
            "inquiry_card": None,
        },
        ensure_ascii=False,
    )


def main():
    import graph.nodes.status_agent as status_mod
    from graph.state import create_initial_state

    # 固定返回 need_questions=true 且携带 inquiry_card，验证问答连贯与提问计数
    status_mod.get_llm = lambda temperature=0.5: _FakeLLM(_mk_need_questions_with_card())  # type: ignore

    state = create_initial_state("我想追求一个女生", onboarding_completed=True, route_to="status_agent")

    print("\n=== 连续提问轮次 1 ===")
    out1 = status_mod.status_agent_node(state)
    print("streak_agent/count =", out1.get("question_streak_agent"), out1.get("question_streak_count"))
    print("has_questions =", bool(out1.get("pending_questions")))

    # 模拟用户回答并恢复（连续第二轮）
    state2 = dict(state)
    state2.update(out1)
    state2["user_message"] = "补充：我们认识三个月，最近一周他更主动。"

    print("\n=== 连续提问轮次 2 ===")
    out2 = status_mod.status_agent_node(state2)
    print("streak_agent/count =", out2.get("question_streak_agent"), out2.get("question_streak_count"))
    print("has_questions =", bool(out2.get("pending_questions")))

    state3 = dict(state2)
    state3.update(out2)
    state3["user_message"] = "补充：线下每周一起打球2-3次，线上也会聊。"

    print("\n=== 连续提问轮次 3 ===")
    out3 = status_mod.status_agent_node(state3)
    print("streak_agent/count =", out3.get("question_streak_agent"), out3.get("question_streak_count"))
    print("has_questions =", bool(out3.get("pending_questions")))

    # 第 4 次：仍 need_questions=true，但应当被“连续<=3轮”拦住，转去生成报告（或至少不再 ask_user）
    state4 = dict(state3)
    state4.update(out3)
    state4["user_message"] = "补充：刚聊完，他说到此为止了。"

    # 这次让模型返回报告，观察 streak 是否被清零
    status_mod.get_llm = lambda temperature=0.5: _FakeLLM(_mk_report())  # type: ignore

    print("\n=== 第 4 次（应转非提问动作 -> 清零 streak） ===")
    out4 = status_mod.status_agent_node(state4)
    print("current_agent =", out4.get("current_agent"))
    print("completion_status =", out4.get("completion_status"))
    print("streak_agent/count =", out4.get("question_streak_agent"), out4.get("question_streak_count"))
    print("has_status_report =", bool(out4.get("status_report")))

    print("\n=== 结论 ===")
    if (out3.get("question_streak_count") == 3) and (out4.get("question_streak_count") == 0):
        print("✅ 连续提问计数与清零逻辑符合预期")
    else:
        print("❌ 连续提问计数或清零逻辑不符合预期，请检查实现")


if __name__ == "__main__":
    main()

