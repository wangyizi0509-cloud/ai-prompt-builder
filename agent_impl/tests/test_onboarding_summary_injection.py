"""Onboarding v2 → main_agent 首轮消息渲染的单元测试。

对应本次迭代的改造：
1. `api.onboarding_handoff_prompt.render_onboarding_first_turn_message` 将
   `OnboardingPayload` 渲染成「系统指令 + 诊断素材」固定模板
2. `ChatRequest` 字段更名为 `onboarding_payload`（dict），不再接受
   旧的 `onboarding_summary` 字符串字段
3. `create_initial_state` 默认 `onboarding_completed=True`
"""

from __future__ import annotations

import pytest


# ---------- 渲染模板 ----------


@pytest.fixture
def render():
    from api.onboarding_handoff_prompt import render_onboarding_first_turn_message

    return render_onboarding_first_turn_message


@pytest.fixture
def payload_cls():
    from api.onboarding_handoff_prompt import OnboardingPayload

    return OnboardingPayload


def test_render_full_payload_contains_all_sections(render, payload_cls):
    """完整 payload 应包含系统指令 + 诊断素材标头 + 三段小标题。"""
    payload = payload_cls(
        free_text="我们是同事，认识三个月，上周表白被婉拒。",
        ocr_texts=[{"ocr_result": "[他] 在忙\n[我] 周末有空吗", "ocr_failed": False}],
        answers={"A1": "A"},
    )
    out = render(payload)

    assert "[系统指令 · 仅本轮]" in out
    assert "[诊断素材]" in out
    assert "## 用户自由描述" in out
    assert "## 截图 OCR" in out
    assert "## 筛题答卷" in out


def test_render_empty_free_text_marks_placeholder(render, payload_cls):
    """free_text 为空时显示占位符 (用户未填写)。"""
    payload = payload_cls(free_text="", ocr_texts=[], answers={})
    out = render(payload)
    assert "## 用户自由描述" in out
    assert "(用户未填写)" in out


def test_render_empty_free_text_whitespace_still_marked(render, payload_cls):
    """纯空白 free_text 等价于空。"""
    payload = payload_cls(free_text="   \n\t  ", ocr_texts=[], answers={})
    out = render(payload)
    assert "(用户未填写)" in out


def test_render_skips_ocr_section_when_empty(render, payload_cls):
    """ocr_texts 为空时不出现 OCR 小节。"""
    payload = payload_cls(free_text="hi", ocr_texts=[], answers={})
    out = render(payload)
    assert "## 截图 OCR" not in out


def test_render_skips_answers_section_when_empty(render, payload_cls):
    """answers 为空时不出现筛题小节。"""
    payload = payload_cls(free_text="hi", ocr_texts=[], answers={})
    out = render(payload)
    assert "## 筛题答卷" not in out


def test_render_answers_labels_single_and_multi_choice(render, payload_cls):
    """单选和多选题应渲染成题目简称 + 选项 code=label。"""
    payload = payload_cls(
        free_text="",
        ocr_texts=[],
        answers={"A1": "A", "A3": ["A", "C"]},
    )
    out = render(payload)

    # 单选 A1
    assert "A1(你们是怎么认识的):A=同事（同公司/同团队）" in out
    # 多选 A3: A 和 C 的 label
    assert (
        "A3(到目前为止，你有没有做过下面这些事):"
        "A=主动表白 / 说过喜欢 TA, C=频繁主动找 TA 聊天（每天主动开话题）"
    ) in out


def test_render_unknown_question_id_falls_back_to_raw(render, payload_cls):
    """未知题号不应丢弃数据，直接走 `- {id}: {raw}` fallback。"""
    payload = payload_cls(free_text="", ocr_texts=[], answers={"ZZ": "X"})
    out = render(payload)
    assert "- ZZ: X" in out


def test_render_ocr_failed_marked_when_no_text(render, payload_cls):
    """OCR 失败且无文本时输出 (OCR 失败)。"""
    payload = payload_cls(
        free_text="",
        ocr_texts=[{"ocr_result": "", "ocr_failed": True}],
        answers={},
    )
    out = render(payload)
    assert "(OCR 失败)" in out


# ---------- ChatRequest schema ----------


@pytest.fixture
def chat_request_cls():
    from api.chat import ChatRequest

    return ChatRequest


def test_chat_request_accepts_onboarding_payload_dict(chat_request_cls):
    """ChatRequest 接受 dict 形式的 onboarding_payload，并解析为 OnboardingPayload。"""
    req = chat_request_cls(
        message="",
        session_id="sess-1",
        onboarding_payload={
            "free_text": "我们是同事",
            "ocr_texts": [{"ocr_result": "hi", "ocr_failed": False}],
            "answers": {"A1": "A"},
        },
    )
    assert req.onboarding_payload is not None
    assert req.onboarding_payload.free_text == "我们是同事"
    assert req.onboarding_payload.answers == {"A1": "A"}
    assert req.onboarding_payload.ocr_texts[0].ocr_result == "hi"


def test_chat_request_rejects_old_onboarding_summary_key(chat_request_cls):
    """旧字段 `onboarding_summary` 已经下线，不再出现在 model_dump 中。"""
    req = chat_request_cls(message="hi", session_id="s1")
    dumped = req.model_dump()
    assert "onboarding_summary" not in dumped
    # 但 onboarding_payload 仍然是已声明字段
    assert "onboarding_payload" in dumped


def test_chat_request_onboarding_payload_defaults_to_none(chat_request_cls):
    req = chat_request_cls(message="hi", session_id="s1")
    assert req.onboarding_payload is None


# ---------- state 默认值 ----------


def test_create_initial_state_default_onboarding_completed():
    """Onboarding v2 上线后，初始 state 默认 onboarding_completed=True。"""
    from graph.state import create_initial_state

    state = create_initial_state("hello")
    assert state["onboarding_completed"] is True


def test_create_initial_state_allows_override_onboarding_completed():
    """显式 overrides 仍然可以把 onboarding_completed 改回 False。"""
    from graph.state import create_initial_state

    state = create_initial_state("hello", onboarding_completed=False)
    assert state["onboarding_completed"] is False
