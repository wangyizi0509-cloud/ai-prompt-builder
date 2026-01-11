"""
Onboarding handoff 摘要格式化的最小单测（不触发 LLM）。

目的：确保 suggested_action 变为自然语言（str）后，主流程拼接【Onboarding总结】不会因类型/空值而报错。
"""

from graph.nodes.main_agent import _format_onboarding_handoff_summary


def test_onboarding_handoff_summary_accepts_text_suggested_action():
    handoff = {
        "recommendation": "信息够了，开始做深度复盘",
        "suggested_action": "建议先做现状分析，再决定要不要追问更多细节",
        "reason": "已满足 MAS",
    }
    out = _format_onboarding_handoff_summary(handoff)
    assert "建议:" in out
    assert "动作:" in out
    assert "理由:" in out

