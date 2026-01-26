import time

import pytest

from tests.test_real_http_api_task_system import (
    _ensure_server_up,
    _chat,
    _finish_onboarding,
    _tail_tool_names,
)


@pytest.mark.api_test
def test_delegate_to_status_e2e():
    """
    真实 API: main_agent 调用 delegate_to_status，验证 handoff 到 status_agent。
    """
    _ensure_server_up()
    session_id = f"delegate_status_{int(time.time())}"

    _finish_onboarding(session_id)

    msg = "我和一个女生认识三个月了，我想知道我们现在是什么阶段"
    out = _chat(session_id, msg, timeout=180)
    state = out.get("state") or {}

    tool_names = _tail_tool_names(state)
    has_delegate = "delegate_to_status" in tool_names
    has_report = bool(state.get("status_report"))
    assert has_delegate or has_report, f"未观察到 delegate 或报告产出，tool_names={tool_names}"


@pytest.mark.api_test
def test_inquiry_two_phase_e2e():
    """
    真实 API: 信息不足场景，验证 load_skill("inquiry") → ask_user 两阶段。
    """
    _ensure_server_up()
    session_id = f"inquiry_2phase_{int(time.time())}"

    _finish_onboarding(session_id)

    msg = "我想追求一个女生"
    out = _chat(session_id, msg, timeout=180)
    state = out.get("state") or {}

    inquiry_card = state.get("inquiry_card")
    pending_questions = state.get("pending_questions")
    current_agent = state.get("current_agent")
    agent_resume_point = state.get("agent_resume_point")

    if inquiry_card or pending_questions:
        assert current_agent is not None, "提问后应设置 current_agent"
        assert agent_resume_point is not None, "提问后应设置 agent_resume_point"

    if current_agent:
        out2 = _chat(session_id, "她是我同事，26岁，我们认识三个月了", timeout=180)
        state2 = out2.get("state") or {}
        assert state2.get("messages"), "恢复执行后应有新消息"
