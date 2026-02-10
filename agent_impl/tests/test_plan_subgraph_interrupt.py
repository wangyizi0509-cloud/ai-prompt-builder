from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from graph.subgraphs.plan import get_plan_subgraph


def test_plan_subgraph_interrupt_then_resume_persists_and_clears_private_messages():
    checkpointer = MemorySaver()
    app = get_plan_subgraph(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "test_plan_subgraph_interrupt"}}

    sub_in = {
        "task_spec": {
            "instruction": "[[TEST_INTERRUPT]] 请先问我一个问题再继续。",
            "parent_state": {
                "messages": [],
                "layer2_memory": {},
                "layer3_memory": {},
                "pending_responses": [],
                "runtime": {},
                "tool_patch_log": [],
            },
        },
        "private_messages": [],
    }

    out1 = app.invoke(sub_in, config=config)
    assert "__interrupt__" in out1

    resume_payload = {"answers": {"q1": "A"}}
    out2 = app.invoke(Command(resume=resume_payload), config=config)

    assert out2.get("final") is not None
    assert isinstance(out2.get("state_patch"), dict)
    assert out2["state_patch"]["inquiry_answers"] == resume_payload
    assert out2.get("private_messages") == []

