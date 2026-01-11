"""
Onboarding Agent: preliminary_assessment 透传单测（不触发真实 LLM）。

目的：
- 当 needs_more=false 时，若模型输出 preliminary_assessment，应出现在：
  1) 节点返回的顶层字段 result["preliminary_assessment"]
  2) pending_responses[0]["preliminary_assessment"]（便于前端/调试）
- 用户可见回复优先使用 parsed["response"]，否则降级为 recommendation
"""

from unittest.mock import MagicMock, patch

from graph.state import create_initial_state
from onboarding.onboarding_agent import onboarding_agent_node


@patch("onboarding.onboarding_agent.get_llm")
def test_onboarding_completed_includes_preliminary_assessment(mock_get_llm):
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
    mock_get_llm.return_value = mock_llm

    state = create_initial_state("你好")
    state["user_message"] = "你好"

    result = onboarding_agent_node(state)

    assert result.get("onboarding_completed") is True
    assert isinstance(result.get("preliminary_assessment"), dict)
    assert result["preliminary_assessment"]["verdict"] == "🟡迷雾"

    pending = result.get("pending_responses") or []
    assert pending and isinstance(pending, list)
    assert "局势初判卡" in pending[0]["content"]
    assert isinstance(pending[0].get("preliminary_assessment"), dict)

