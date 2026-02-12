from __future__ import annotations

from agents.tooling.patch import merge_state_patch
from onboarding import onboarding_agent as onboarding_module


def test_onboarding_turn_count_increments_only_for_new_answers():
    state = {
        "onboarding_turn_count": 0,
        "onboarding_last_answer_fingerprint": None,
    }

    patch1 = onboarding_module._build_onboarding_answer_progress_patch(
        state, {"answers": {"q1": "A"}}
    )
    assert patch1.get("onboarding_turn_count") == 1
    assert isinstance(patch1.get("onboarding_last_answer_fingerprint"), str)
    state = merge_state_patch(state, patch1)

    patch2 = onboarding_module._build_onboarding_answer_progress_patch(
        state, {"answers": {"q1": "A"}}
    )
    assert "onboarding_turn_count" not in patch2
    assert patch2.get("onboarding_last_answer_fingerprint") == state.get("onboarding_last_answer_fingerprint")

    patch3 = onboarding_module._build_onboarding_answer_progress_patch(
        state, {"answers": {"q1": "B"}}
    )
    assert patch3.get("onboarding_turn_count") == 2


def test_onboarding_turn_count_not_incremented_for_empty_or_invalid_answers():
    state = {"onboarding_turn_count": 3, "onboarding_last_answer_fingerprint": "x"}

    assert onboarding_module._build_onboarding_answer_progress_patch(state, None) == {}
    assert onboarding_module._build_onboarding_answer_progress_patch(state, {}) == {}
    assert onboarding_module._build_onboarding_answer_progress_patch(state, {"answers": {}}) == {}
    assert onboarding_module._build_onboarding_answer_progress_patch(state, "bad") == {}
