from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from graph.tools.ask_human import ask_human


def test_ask_human_interrupt_then_resume_returns_tool_result():
    def node(state: dict) -> dict:
        inquiry_card = {
            "questions": [
                {
                    "id": "q1",
                    "type": "single_choice",
                    "question": "你更在意哪一点？",
                    "options": ["聊天频率", "回应态度"],
                    "is_required": True,
                    "purpose": "确认优先级",
                }
            ],
            "intro": "我先确认一个关键信息：",
            "reasoning": "避免在信息不足时给出误导建议",
        }
        result = ask_human.invoke({"inquiry_card": inquiry_card})
        return {"tool_result": result}

    graph = StateGraph(dict)
    graph.add_node("n", node)
    graph.set_entry_point("n")
    graph.add_edge("n", END)
    app = graph.compile(checkpointer=MemorySaver())

    config = {"configurable": {"thread_id": "test_interrupt_ask_human"}}

    out1 = app.invoke({}, config=config)
    assert "__interrupt__" in out1
    interrupts = out1["__interrupt__"]
    assert len(interrupts) == 1
    assert interrupts[0].value["questions"][0]["id"] == "q1"

    resume_payload = {"answers": {"q1": "聊天频率"}}
    out2 = app.invoke(Command(resume=resume_payload), config=config)

    tool_result = out2["tool_result"]
    assert tool_result["ok"] is True
    assert tool_result["state_patch"]["inquiry_card"]["questions"][0]["id"] == "q1"
    assert tool_result["state_patch"]["inquiry_answers"] == resume_payload
