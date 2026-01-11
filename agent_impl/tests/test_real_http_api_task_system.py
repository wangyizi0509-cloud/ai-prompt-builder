"""
真实 HTTP + 真实模型调用的 Task System 端到端测试

特点：
- 通过 FastAPI 服务的 /api/chat 走完整 HTTP 链路
- 由服务端触发真实 LLM Provider（依赖你本机 server.py 读取到的 .env）
- 断言核心产物写入 state（layer3_memory.task_registry）

注意：
- 该测试假设本机已有服务监听在 http://127.0.0.1:8000
- 该测试不使用 httpx（在本机环境下 httpx 会返回 502，curl/urllib 正常）
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Any

import pytest


BASE_URL = "http://127.0.0.1:8000"


def _post_json(url: str, payload: dict, timeout: int = 180) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return json.loads(body.decode("utf-8"))


def _get(url: str, timeout: int = 30) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read()


def _ensure_server_up() -> None:
    try:
        code, _ = _get(f"{BASE_URL}/openapi.json", timeout=10)
        if code != 200:
            raise RuntimeError(f"openapi not ok: {code}")
    except Exception as e:
        pytest.skip(f"本机 API 服务不可用（{BASE_URL}）：{e}")


def _chat(session_id: str, message: str, timeout: int = 180) -> dict[str, Any]:
    return _post_json(
        f"{BASE_URL}/api/chat",
        {"message": message, "session_id": session_id},
        timeout=timeout,
    )


def _finish_onboarding(session_id: str) -> dict[str, Any]:
    """
    Onboarding 最多 3 轮；我们直接喂 3 条高信息密度输入，保证进入主流程。
    """
    m1 = "我需要你帮我解决一个恋爱推进问题。我是男生，27岁，北京，程序员。"
    m2 = "我喜欢的女生是同事，26岁，性格外向，我们认识3个月。"
    m3 = "我们最近每天都会聊几句，她会主动发消息，周末她约我看电影。我的目标是推进关系。"

    out = _chat(session_id, m1)
    out = _chat(session_id, m2)
    out = _chat(session_id, m3)

    state = out.get("state") or {}
    assert isinstance(state, dict)
    assert state.get("onboarding_turn_count", 0) >= 1
    return out


def _get_main_task_list(state: dict) -> list[dict]:
    layer3 = state.get("layer3_memory") or {}
    registry = layer3.get("task_registry") or {}
    tasks = registry.get("main_agent") or []
    assert isinstance(tasks, list)
    return tasks


def _get_active_task(tasks: list[dict]) -> dict | None:
    active = [t for t in tasks if (t.get("is_active") or t.get("status") == "active")]
    if not active:
        return None
    # 约束：只允许一个
    assert len(active) == 1
    return active[0]

def _tail_tool_names(state: dict, tail: int = 30) -> list[str]:
    """
    从 state.messages 的末尾提取 tool_calls / tool message 的名称（用于判断是否触发了工具调用）。
    """
    names: list[str] = []
    msgs = state.get("messages") or []
    if not isinstance(msgs, list):
        return names
    for m in msgs[-tail:]:
        if not isinstance(m, dict):
            continue
        # tool message
        if m.get("role") == "tool" or m.get("type") == "tool":
            nm = m.get("name") or ""
            if nm:
                names.append(str(nm))
        # ai message tool_calls
        tcs = m.get("tool_calls")
        if isinstance(tcs, list):
            for tc in tcs:
                if isinstance(tc, dict) and tc.get("name"):
                    names.append(str(tc["name"]))
    return names


@pytest.mark.api_test
def test_http_task_create_append_switch_smoke():
    """
    真实 HTTP + 真实模型调用：
    1) 完成 onboarding
    2) create_task 创建任务 A
    3) append_task_note 追加笔记
    4) create_task 创建任务 B
    5) switch_task 切回任务 A
    """
    _ensure_server_up()

    session_id = f"real_http_task_{int(time.time())}"

    # 1) onboarding
    _finish_onboarding(session_id)

    # 2) create_task A（强约束提示，尽量稳定触发工具）
    msg_create_a = (
        "这是系统验收测试，请你严格执行：\n"
        "你必须先调用工具 create_task 创建新任务：\n"
        "- task_id = \"test_task_A\"\n"
        "- summary = \"测试任务A\"\n"
        "然后在同一轮继续输出最终 JSON。\n"
        "严禁把创建任务这件事只写在 JSON 里，必须通过工具完成。\n"
        "同时：不要调用任何子 Agent，不要做现状分析，只做任务系统动作。"
    )

    # 真实模型下可能偶发不按约束调用工具；这里最多重试 3 次（避免测试过度脆弱）。
    out = None
    state = {}
    tasks = []
    tool_names = []
    for _ in range(3):
        out = _chat(session_id, msg_create_a)
        state = out.get("state") or {}
        tasks = _get_main_task_list(state)
        tool_names = _tail_tool_names(state)
        has_task = any(t.get("task_id") == "test_task_A" for t in tasks)
        active = _get_active_task(tasks)
        ok = ("create_task" in tool_names) and has_task and active and active.get("task_id") == "test_task_A"
        if ok:
            break
        time.sleep(0.5)

    assert "create_task" in tool_names, f"未观察到 create_task 工具调用，tool_names_tail={tool_names}"
    assert any(t.get("task_id") == "test_task_A" for t in tasks), f"未在 task_registry 中发现 test_task_A，task_ids={[t.get('task_id') for t in tasks]}"
    active = _get_active_task(tasks)
    assert active and active.get("task_id") == "test_task_A", f"create_task 后活跃任务不为 test_task_A，active={active.get('task_id') if active else None}"

    # 3) append_task_note
    msg_append = (
        "继续系统验收：你必须调用工具 append_task_note，note=\"A任务笔记-1：已进入推进策略阶段\"。\n"
        "调用后再输出你的最终 JSON 回复。"
    )
    out = _chat(session_id, msg_append)
    state = out.get("state") or {}
    tasks = _get_main_task_list(state)
    tool_names = _tail_tool_names(state)
    assert "append_task_note" in tool_names, f"未观察到 append_task_note 工具调用，tool_names_tail={tool_names}"

    active = _get_active_task(tasks)
    assert active and active.get("task_id") == "test_task_A"
    reasoning = active.get("reasoning") or []
    assert isinstance(reasoning, list)
    assert any("A任务笔记-1" in str(x) for x in reasoning), "未发现 append_task_note 写入的笔记"

    # 4) create_task B
    msg_create_b = (
        "继续系统验收：你必须调用工具 create_task 创建新任务：\n"
        "- task_id = \"test_task_B\"\n"
        "- summary = \"测试任务B\"\n"
        "然后继续输出最终 JSON。"
    )
    out = _chat(session_id, msg_create_b)
    state = out.get("state") or {}
    tasks = _get_main_task_list(state)
    tool_names = _tail_tool_names(state)
    assert "create_task" in tool_names, f"未观察到 create_task 工具调用（创建B），tool_names_tail={tool_names}"
    assert any(t.get("task_id") == "test_task_B" for t in tasks), "未在 task_registry 中发现 test_task_B"
    active = _get_active_task(tasks)
    assert active and active.get("task_id") == "test_task_B"

    # 5) switch_task 回到 A
    msg_switch_a = (
        "继续系统验收：你必须调用工具 switch_task 切换到 task_id=\"test_task_A\"，\n"
        "然后在同一轮基于 A 的 reasoning_notes 继续输出最终 JSON。"
    )
    out = _chat(session_id, msg_switch_a)
    state = out.get("state") or {}
    tasks = _get_main_task_list(state)
    tool_names = _tail_tool_names(state)
    assert "switch_task" in tool_names, f"未观察到 switch_task 工具调用，tool_names_tail={tool_names}"
    active = _get_active_task(tasks)
    assert active and active.get("task_id") == "test_task_A"


@pytest.mark.api_test
def test_http_task_create_duplicate_rejected():
    """
    真实 HTTP + 真实模型调用：
    - create_task 创建任务 A
    - 再次 create_task 同名任务 A，应被工具拒绝，且不会产生重复 task_id
    """
    _ensure_server_up()

    session_id = f"real_http_task_dup_{int(time.time())}"
    _finish_onboarding(session_id)

    # create A
    out = _chat(
        session_id,
        "系统验收：必须调用 create_task 创建 task_id=\"test_task_A\" summary=\"测试任务A\"，不要做其它分析。",
    )
    state = out.get("state") or {}
    tasks = _get_main_task_list(state)
    tool_names = _tail_tool_names(state)
    assert "create_task" in tool_names
    assert any(t.get("task_id") == "test_task_A" for t in tasks)
    assert _get_active_task(tasks) and _get_active_task(tasks).get("task_id") == "test_task_A"
    before_count = len(tasks)

    # create A again (should be rejected by tool)
    out = _chat(
        session_id,
        "系统验收：现在请再次调用 create_task 创建同名 task_id=\"test_task_A\" summary=\"重复\"。\n"
        "注意：这是测试唯一性，你必须调用 create_task 工具，即使它会失败。",
    )
    state = out.get("state") or {}
    tasks = _get_main_task_list(state)
    tool_names = _tail_tool_names(state)
    assert "create_task" in tool_names, f"未观察到 create_task 工具调用（重复创建），tool_names_tail={tool_names}"

    # 不应新增重复记录
    assert len(tasks) == before_count, f"重复创建后任务数量发生变化：before={before_count}, after={len(tasks)}"
    ids = [t.get("task_id") for t in tasks]
    assert ids.count("test_task_A") == 1, f"出现重复 task_id：{ids}"
    active = _get_active_task(tasks)
    assert active and active.get("task_id") == "test_task_A"


@pytest.mark.api_test
def test_http_task_switch_nonexistent_no_change():
    """
    真实 HTTP + 真实模型调用：
    - create_task 创建任务 A
    - switch_task 切换到不存在任务，应失败且不改变当前活跃任务
    """
    _ensure_server_up()

    session_id = f"real_http_task_switch404_{int(time.time())}"
    _finish_onboarding(session_id)

    out = _chat(
        session_id,
        "系统验收：必须调用 create_task 创建 task_id=\"test_task_A\" summary=\"测试任务A\"，不要做其它分析。",
    )
    state = out.get("state") or {}
    tasks = _get_main_task_list(state)
    assert any(t.get("task_id") == "test_task_A" for t in tasks)
    active = _get_active_task(tasks)
    assert active and active.get("task_id") == "test_task_A"
    before_ids = [t.get("task_id") for t in tasks]

    # switch to nonexistent
    out = _chat(
        session_id,
        "系统验收：你必须调用 switch_task 切换到 task_id=\"no_such_task_404\"。\n"
        "注意：这是测试不存在任务的处理逻辑，你必须真的调用工具，即使会失败。",
    )
    state = out.get("state") or {}
    tasks = _get_main_task_list(state)
    tool_names = _tail_tool_names(state)
    assert "switch_task" in tool_names, f"未观察到 switch_task 工具调用，tool_names_tail={tool_names}"

    active = _get_active_task(tasks)
    assert active and active.get("task_id") == "test_task_A", "切换不存在任务后，不应改变当前活跃任务"
    after_ids = [t.get("task_id") for t in tasks]
    assert after_ids == before_ids, f"切换不存在任务后任务列表不应变化：before={before_ids}, after={after_ids}"

