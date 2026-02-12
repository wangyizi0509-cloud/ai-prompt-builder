"""Onboarding preliminary_assessment 透传单测（固定走 legacy fallback）。"""

from unittest.mock import MagicMock

from graph.state import create_initial_state
from onboarding import onboarding_agent as onboarding_module


def test_onboarding_completed_includes_preliminary_assessment(monkeypatch):
    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = """```json
{
  "needs_more": false,
  "response": "我先给你一张局势初判卡，咱们再决定要不要深挖。",
  "preliminary_assessment": {
    "verdict": "🟡迷雾",
    "evidence": "对方回复忽冷忽热，且关键问题上回避。",
    "projection": "短期可能继续观望，但仍有窗口期。",
    "call_to_action": "把你们最近3次关键互动发我"
  },
  "recommendation": "信息足够，建议进入主流程做深度分析。",
  "suggested_action": "建议进行现状分析",
  "reason": "已满足 MAS"
}
```"""
    mock_llm.invoke.return_value = mock_resp
    monkeypatch.setattr(onboarding_module, "get_llm", lambda *args, **kwargs: mock_llm)

    def _force_fallback(**kwargs):
        raise RuntimeError("force legacy fallback in test")

    monkeypatch.setattr(onboarding_module, "_run_onboarding_supervisor", _force_fallback)

    state = create_initial_state("你好")
    state["user_message"] = "你好"

    result = onboarding_module.onboarding_agent_node(state)

    assert result.get("onboarding_completed") is False
    assert result.get("pending_crushe_guide") is True
    assert isinstance(result.get("preliminary_assessment"), dict)
    assert result["preliminary_assessment"]["verdict"] == "🟡迷雾"

    pending = result.get("pending_responses") or []
    assert pending and isinstance(pending, list)
    assert "局势初判卡" in pending[0]["content"]
    assert isinstance(pending[0].get("preliminary_assessment"), dict)
