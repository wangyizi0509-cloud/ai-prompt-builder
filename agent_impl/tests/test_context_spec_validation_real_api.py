"""
真实 HTTP + 真实模型调用：
验证各层上下文输出格式（基于 build_context_dict）

注意：
- 依赖本机服务 http://127.0.0.1:8000
- 依赖 .env 中配置的真实 LLM API Key
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

import pytest

from graph.context_builder import build_context_dict


BASE_URL = "http://127.0.0.1:8000"


def _post_json(url: str, payload: dict, timeout: int = 300, retries: int = 2) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                return json.loads(body.decode("utf-8"))
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 + attempt)
            else:
                raise
    raise RuntimeError(f"POST failed: {last_err}")


def _get(url: str, timeout: int = 30) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read()


def _ensure_server_up() -> None:
    try:
        code, _ = _get(f"{BASE_URL}/openapi.json", timeout=10)
        if code != 200:
            raise RuntimeError(f"openapi not ok: {code}")
    except Exception as e:
        pytest.skip(f"本机 API 服务不可用（{BASE_URL}）：{e}")


def _chat(session_id: str, message: str, timeout: int = 300) -> dict[str, Any]:
    return _post_json(
        f"{BASE_URL}/api/chat",
        {"message": message, "session_id": session_id},
        timeout=timeout,
    )


def _print_context_dict(context_dict: dict) -> None:
    print("\n====== Context Dict (Real API) ======")
    for key, value in context_dict.items():
        print(f"\n[{key}]\n{value}\n")


def _compose_inquiry_answers(inquiry_card: dict) -> str:
    questions = inquiry_card.get("questions") if isinstance(inquiry_card, dict) else None
    if not questions:
        return ""
    lines = []
    for idx, q in enumerate(questions, 1):
        q_text = q.get("question") if isinstance(q, dict) else ""
        if "聊天记录" in (q_text or "") or "截图" in (q_text or ""):
            answer = (
                "聊天记录摘录（含时间）：\n"
                "1) 18:35 她：下班了吗？\n"
                "   18:37 我：刚下班。\n"
                "   18:38 她：辛苦啦，今晚还忙吗？\n"
                "   18:40 我：不忙，想放松下。\n"
                "   18:41 她：那你今天看起来挺开心呀～\n"
                "2) 21:15 她：你上次说的那家店我去看了，感觉不错。\n"
                "   21:18 我：哈哈你也去啦，那下次一起去？\n"
                "   21:19 她：可以呀。\n"
                "3) 23:05 她：今天挺开心的，下次换个别的吧。\n"
                "   23:06 我：好啊，你想看什么类型？\n"
                "   23:08 她：喜剧或轻松一点的都行。\n"
                "截图我这边先文字转述，核心是她两次主动开场并接受了下次邀约。"
            )
        elif "回复" in (q_text or ""):
            answer = (
                "回复速度：工作日一般30分钟到2小时内，晚间更快；"
                "偶尔忙会隔半天，但当天一定回并解释原因。"
            )
        elif "话题" in (q_text or "") or "开场" in (q_text or ""):
            answer = (
                "她主动开启略多，常以分享生活/工作小事开场，"
                "也会问我近况、周末安排，偶尔提我们一起看电影的细节。"
            )
        elif "电影" in (q_text or "") or "约会" in (q_text or ""):
            answer = (
                "电影是我提的，她很快确认时间地点。看完后她主动提观后感，"
                "还说下次换个别的；这周聊天频率更高，语气更轻松。"
            )
        else:
            answer = "信息如上，若需要我可以继续补充细节。"
        lines.append(f"Q{idx}: {answer}")
    return "\n".join(lines)


def _answer_if_needed(session_id: str, out: dict, *, max_rounds: int = 5) -> dict:
    state = out.get("state") or {}
    for _ in range(max_rounds):
        inquiry_card = state.get("inquiry_card")
        pending_questions = state.get("pending_questions")
        if inquiry_card:
            reply = _compose_inquiry_answers(inquiry_card)
            if reply:
                out = _chat(session_id, reply)
                state = out.get("state") or {}
                continue
        if pending_questions:
            reply = "\n".join(
                [
                    f"Q{i+1}: 我补充细节：她没有明显回避，互动频率稳定，"
                    "我主动邀约时她愿意配合并给出具体时间。"
                    for i in range(len(pending_questions))
                ]
            )
            out = _chat(session_id, reply)
            state = out.get("state") or {}
            continue
        break
    return out


@pytest.mark.api_test
def test_real_api_context_spec_validation():
    _ensure_server_up()

    session_id = f"real_api_context_{int(time.time())}"

    # 多轮对话：尽量覆盖 L1/L2/L3
    out = _chat(
        session_id,
        "我叫小明，27岁，北京程序员，性格有点内向。",
    )
    out = _chat(
        session_id,
        "我喜欢的女生叫小红，是我同事，26岁，性格外向。",
    )
    out = _chat(
        session_id,
        "我们认识三个月，最近聊天频率还行，她会主动找我。上周一起看了电影，她反馈挺开心。",
    )
    out = _chat(
        session_id,
        "电影是我主动约的，结束后她说挺开心，这周我们聊天比之前更频繁。",
    )
    out = _chat(
        session_id,
        "她最近主动找我时主要聊日常和工作，也会分享生活小事。",
    )
    # 触发 Status/Plan/Guide 的需求
    out = _chat(
        session_id,
        "我想知道我们现在是什么阶段，下一步怎么推进？",
    )
    out = _chat(
        session_id,
        "请给我一个阶段性的行动规划，并给出本周可以执行的具体行动指南。",
    )
    out = _answer_if_needed(session_id, out, max_rounds=3)
    # 再给一次追问，尽量产出报告/规划/指南
    out = _chat(
        session_id,
        "如果你需要更多信息可以直接问，但请先给出初步判断和下一步行动。",
    )
    out = _answer_if_needed(session_id, out, max_rounds=3)
    # 主动补充更多事实信息，尽量促进动态情报与对话历史形成
    out = _chat(
        session_id,
        "补充：她说下周三要出差，最近加班比较多，情绪有点疲惫。",
    )
    out = _chat(
        session_id,
        "补充：我们昨晚聊到兴趣，她说最近在追综艺，周末想放松一下。",
    )
    out = _chat(
        session_id,
        "补充：我本周准备周五请她喝咖啡，她说可以。",
    )

    state = out.get("state") or {}
    assert isinstance(state, dict)

    # 用真实 state 组装上下文（便于对齐规格）
    context_dict = build_context_dict(state)
    _print_context_dict(context_dict)

    # 基础字段存在性（不做过严约束，避免真实模型波动）
    assert "user_context" in context_dict
    assert "conversation_history" in context_dict
    assert "status_report" in context_dict
    assert "action_plan" in context_dict

    # 输出格式基本特征（允许内容为空，但格式头需正确）
    user_context = context_dict.get("user_context", "")
    assert "## 情报概览" in user_context
    # 真实 API 下可能尚未沉淀 Layer1，允许空内容但保留格式头
    if "### 用户" in user_context:
        assert "事实 > AI分析 > 用户提供" in user_context
    else:
        assert user_context.strip() in (
            "## 情报概览\n> 信息可靠性：事实 > AI分析 > 用户提供。当信息冲突时，以高可靠性信息为准。",
            "暂无详细信息，需要进一步了解。",
        )

    conversation_history = context_dict.get("conversation_history", "")
    assert "## 对话" in conversation_history or "无历史对话" in conversation_history

    status_report = context_dict.get("status_report", "")
    if status_report and "暂无现状分析报告" not in status_report:
        assert "> 更新时间:" in status_report
        assert "\"\"\"" in status_report

    action_plan = context_dict.get("action_plan", "")
    if action_plan and "暂无行动规划" not in action_plan:
        assert "> 更新时间:" in action_plan
        assert "\"\"\"" in action_plan

    dynamic_intel = context_dict.get("dynamic_intel", "")
    if dynamic_intel:
        assert "## 动态情报板" in dynamic_intel or dynamic_intel.strip() == ""

    action_guides = context_dict.get("action_guides", "")
    if action_guides and "暂无行动指南" not in action_guides:
        assert "###" in action_guides
