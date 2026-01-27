import time

import pytest

from tests.test_real_http_api_task_system import (
    _ensure_server_up,
    _chat,
    _finish_onboarding,
    _tail_tool_names,
)


@pytest.mark.api_test
def test_return_to_main_after_submit_e2e():
    """
    真实 API: 子 Agent 在提交后调用 return_to_main，转接回主 Agent。
    """
    _ensure_server_up()
    session_id = f"return_to_main_{int(time.time())}"

    _finish_onboarding(session_id)

    msg = (
        "系统验收测试：你必须调用 delegate_to_guide 工具，并在 instruction 中要求 guide_agent：\n"
        "1) 不要提问，直接调用 submit_action_guide 生成最小可用指南（title/one_liner/guide_markdown 均可用“测试”）。\n"
        "2) 在同一轮紧接着调用 return_to_main(reason=\"测试完成\")。\n"
        "注意：严禁只在文字里描述，必须真实调用工具。"
    )

    out = None
    state = {}
    tool_names = []
    for _ in range(3):
        out = _chat(session_id, msg, timeout=180)
        state = out.get("state") or {}
        tool_names = _tail_tool_names(state)
        if "return_to_main" in tool_names:
            break
        time.sleep(0.5)

    assert "delegate_to_guide" in tool_names, f"未观察到 delegate_to_guide 调用，tool_names={tool_names}"
    assert "submit_action_guide" in tool_names, f"未观察到 submit_action_guide 调用，tool_names={tool_names}"
    assert "return_to_main" in tool_names, f"未观察到 return_to_main 调用，tool_names={tool_names}"
