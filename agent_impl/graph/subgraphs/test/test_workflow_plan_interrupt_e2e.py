from __future__ import annotations

import os

os.environ["LLM_PROVIDER"] = "mock"

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from graph.state import create_initial_state
from graph.workflow import compile_workflow


def test_workflow_main_to_plan_interrupt_then_resume():
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    thread_cfg = {"configurable": {"thread_id": "test_workflow_main_plan_interrupt_e2e"}, "checkpointer": checkpointer}

    state = create_initial_state(
        "[[TEST_CALL_PLAN_INTERRUPT]]",
        onboarding_completed=True,
        onboarding_handoff=None,
        onboarding_turn_count=999,
    )

    out1 = app.invoke(state, config=thread_cfg)
    assert "__interrupt__" in out1
    interrupts = out1.get("__interrupt__") or []
    assert interrupts
    payload = interrupts[0].value
    qids = [q.get("id") for q in (payload.get("questions") or []) if isinstance(q, dict)]
    assert qids == ["q1"]

    out2 = app.invoke(Command(resume={"q1": "A"}), config=thread_cfg)
    assert "__interrupt__" not in out2
    assert out2.get("inquiry_answers") == {"q1": "A"}


def test_workflow_main_to_plan_two_interrupts_then_finish():
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    thread_cfg = {"configurable": {"thread_id": "test_workflow_main_plan_two_interrupts_e2e"}, "checkpointer": checkpointer}

    state = create_initial_state(
        "[[TEST_CALL_PLAN_INTERRUPT_TWICE]]",
        onboarding_completed=True,
        onboarding_handoff=None,
        onboarding_turn_count=999,
    )

    out1 = app.invoke(state, config=thread_cfg)
    assert "__interrupt__" in out1
    payload1 = (out1.get("__interrupt__") or [None])[0].value
    qids1 = [q.get("id") for q in (payload1.get("questions") or []) if isinstance(q, dict)]
    assert qids1 == ["q1"]

    out2 = app.invoke(Command(resume={"q1": "A"}), config=thread_cfg)
    assert "__interrupt__" in out2
    payload2 = (out2.get("__interrupt__") or [None])[0].value
    qids2 = [q.get("id") for q in (payload2.get("questions") or []) if isinstance(q, dict)]
    assert qids2 == ["q2"]

    out3 = app.invoke(Command(resume={"q2": "C"}), config=thread_cfg)
    assert "__interrupt__" not in out3


if __name__ == "__main__":
    test_workflow_main_to_plan_interrupt_then_resume()
    test_workflow_main_to_plan_two_interrupts_then_finish()
    print("ok")
