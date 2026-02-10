from agents.tooling.patch import merge_state_patch
from graph.tools.task_tools import create_task_tools


def test_task_manager_create_returns_state_patch_and_updates_registry():
    state = {"layer3_memory": {"task_registry": {}}}
    tools = create_task_tools(lambda: state, agent_name="main_agent")
    tool = tools[0]

    out = tool.invoke({"action": "create", "task_id": "t1", "title": "T1", "summary": "S1", "note": ""})
    assert out["ok"] is True
    assert out["state_patch"].get("layer3_memory")

    new_state = merge_state_patch(state, out["state_patch"])
    tasks = ((new_state.get("layer3_memory") or {}).get("task_registry") or {}).get("main_agent") or []
    assert tasks
    assert any(t.get("task_id") == "t1" for t in tasks)


def test_task_manager_append_note_returns_state_patch():
    state = {"layer3_memory": {"task_registry": {}}}
    tool = create_task_tools(lambda: state, agent_name="main_agent")[0]

    out1 = tool.invoke({"action": "create", "task_id": "t1", "title": "T1", "summary": "S1", "note": ""})
    state = merge_state_patch(state, out1["state_patch"])

    tool = create_task_tools(lambda: state, agent_name="main_agent")[0]
    out2 = tool.invoke({"action": "append_note", "task_id": "", "title": "", "summary": "", "note": "n1"})
    assert out2["ok"] is True
    state = merge_state_patch(state, out2["state_patch"])

    tasks = ((state.get("layer3_memory") or {}).get("task_registry") or {}).get("main_agent") or []
    active = next((t for t in tasks if t.get("status") == "active"), None)
    assert active
    assert active.get("reasoning_notes")
