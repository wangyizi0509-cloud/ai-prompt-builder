"""
本脚本用于“手动走一遍工作流”验证：
- 在不给真实模型联网的情况下，确认 status_agent 在 need_questions 场景下产出 inquiry_card / pending_questions
- 路径：主流程 -> call_status -> status_agent need_questions

使用方式（只跑本脚本，不跑任何全量测试）：
  cd agent_impl
  python scripts/debug_status_agent_questions_flow.py
"""

import json
import sys
from pathlib import Path

# 确保 agent_impl 目录在 sys.path 中（与 tests/conftest.py 一致）
AGENT_IMPL_DIR = Path(__file__).resolve().parent.parent
if str(AGENT_IMPL_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_IMPL_DIR))


class _FakeResponse:
    def __init__(self, content: str, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeLLM:
    def __init__(self, contents: list[str]):
        self._contents = list(contents)
        self._i = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, prompt: str):
        if self._i < len(self._contents):
            content = self._contents[self._i]
        else:
            content = self._contents[-1] if self._contents else "{}"
        self._i += 1
        return _FakeResponse(content=content, tool_calls=[])


def _pretty(x):
    try:
        return json.dumps(x, ensure_ascii=False, indent=2)
    except Exception:
        return str(x)


def main():
    # 你给的复现输入（业务流程输入）
    user_text = """我和他是打排球认识的 最开始我没和他一起打，后来他自己来找我打，然后我俩就两个人单打 : 最开始他扣球不扣我，要不让别人扣我，但是刚开始打排球的人他都扣 : 最开始打完了，他自己很快就走了，现在除了教我动作以外，都会在我周围，不近不远的跟着 : 因为我们这里是东北，所以晚上打球的时候就已经零下了，我说我冷，他就要把手套给我 : 我俩打球的时候啥都聊，处对象啊，学习啊，这些都聊 : 我俩都是不处对象那种人，所以我会经常拿他和帝总（也是男生）处对象开玩笑 : 前天他突然和我说他想处对象，不是和帝总的那种 : 今天我给他做了一个圣诞帽的头像，我俩聊了挺多的，前面都挺开心的，但最后好像聊崩了 :
聊天记录
| 发送者 | 内容 | 时间戳 | 文本序号 |
| --- | --- | --- | --- |
| 用户 | 圣诞帽你真的不戴吗😲 | - | 1 |
| crush | 看看 | - | 2 |
| 用户 | 行，你傲娇 | - | 3 |
| crush | 一会俗晚宁戴个套 | - | 4 |
| 用户 | 啥玩意 | - | 5 |
| 用户 | 说啥呢 | - | 6 |
| crush | 头套吗？ | - | 7 |
| 用户 | 哦 | - | 8 |
| crush | ？ | - | 9 |
| crush | 想啥呢？ | 17:53 | 10 |
| 用户 | 我还以为你前天说相处对象，今天就有了呢 | 17:53 | 11 |
| crush | … | - | 12 |
| crush | 6 | - | 13 |
| 用户 | 低调低调 | - | 14 |
| crush | 你怕不是看多了 | - | 15 |
| 用户 | 你之前不说你脑子里都是打码的嘛 | - | 16 |
| crush | …… | - | 17 |
| crush | 打码的是<br>（图片） | - | 18 |
| 用户 | 你不是说相处对象，不是机帝总的吗 | - | 19 |
| 用户 | 你咋这样呢 | - | 20 |
| crush | 拒绝回答 | - | 21 |
| 用户 | 好好好 | - | 22 |
| crush | 到此为止了 | - | 23 |
| 用户 | 嗯 | - | 24 |
| 用户 | 不堆了不堆了 | - | 25 |

大概就是这样 : 还有希望吗"""

    # 关键：为了不联网，这里用 FakeLLM 固定主流程一定 call_status；
    # 同时让 status_agent “第一阶段只返回 need_questions=true + inquiry_card=null”（模拟 bug 触发点），
    # 看 status_agent 是否还能兜底产出 inquiry_card。
    from graph.state import create_initial_state
    import graph.nodes.main_agent as main_mod
    import graph.nodes.status_agent as status_mod

    main_json = json.dumps(
        {
            "task_id": "debug_task",
            "thought": "route to status agent",
            "response": "我先帮你做现状分析。",
            "intent_type": "action_trigger",
            "next_action": "call_status",
            "need_questions": False,
            "inquiry_card": None,
        },
        ensure_ascii=False,
    )

    status_phase1_json = json.dumps(
        {
            "task_id": "task_001",
            "thought": "need more info",
            "need_questions": True,
            "response": "我还差几个关键细节才能把局势判准～",
            "update_type": "none",
            "report_content": None,
            "inquiry_card": {
                "questions": [
                    {
                        "id": "q1",
                        "type": "free_input_question",
                        "question": "你们认识多久了？最近一次互动发生在什么时候？",
                        "options": None,
                        "is_required": True,
                        "purpose": "补齐关键背景",
                    }
                ],
                "intro": "我先补齐几个关键细节～",
                "reasoning": "need core context",
            },
        },
        ensure_ascii=False,
    )

    main_mod.get_llm = lambda temperature=0.7: _FakeLLM([main_json])  # type: ignore
    status_mod.get_llm = lambda temperature=0.5: _FakeLLM([status_phase1_json])  # type: ignore

    # 跳过 onboarding（等价于 “onboarding结束，把你放到业务流程里去”）
    state = create_initial_state(
        user_text,
        onboarding_completed=True,
        route_to="main_agent",
    )

    # 走 main_agent -> call_status
    out1 = main_mod.main_agent_node(state)
    print("\n=== Step1: main_agent 输出 ===")
    print("next_action =", out1.get("next_action"))

    # 走 status_agent -> need_questions -> inquiry_card?
    # 模拟 workflow：把 main 的产物合并到 state（最小必要字段）
    state2 = dict(state)
    state2.update(out1)
    out2 = status_mod.status_agent_node(state2)

    print("\n=== Step2: status_agent 输出 ===")
    print("current_agent =", out2.get("current_agent"))
    print("agent_resume_point =", out2.get("agent_resume_point"))
    print("question_count =", out2.get("question_count"))
    print("has_inquiry_card =", bool(out2.get("inquiry_card")))
    print("pending_questions =", out2.get("pending_questions"))
    if out2.get("inquiry_card"):
        print("\n[inquiry_card]\n", _pretty(out2.get("inquiry_card")))

    print("\n=== 结论 ===")
    if out2.get("inquiry_card") or out2.get("pending_questions"):
        print("✅ status_agent 已返回提问（inquiry_card / pending_questions 存在）")
    else:
        print("❌ status_agent 未返回提问（需要继续查）")


if __name__ == "__main__":
    main()

