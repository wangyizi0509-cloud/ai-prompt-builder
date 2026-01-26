"""
真实 API 测试：验证维护队列在达到阈值后入队压缩任务

注意：
- 依赖本机服务 http://127.0.0.1:8000
- 依赖 .env 中配置的真实 LLM API Key
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

import pytest


BASE_URL = "http://127.0.0.1:8000"


def _post_json(url: str, payload: dict, timeout: int = 300, retries: int = 2) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                return json.loads(body.decode("utf-8"))
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 + attempt)
            else:
                raise
    raise RuntimeError(f"POST failed: {last_err}")


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


def _chat(session_id: str, message: str, timeout: int = 300) -> dict[str, Any]:
    return _post_json(
        f"{BASE_URL}/api/chat",
        {"message": message, "session_id": session_id},
        timeout=timeout,
    )


def _has_task(queue: list[dict], task_type: str, task_key: str) -> bool:
    for t in queue or []:
        if not isinstance(t, dict):
            continue
        if t.get("type") != task_type:
            continue
        if t.get("task_key") == task_key:
            return True
    return False


@pytest.mark.api_test
def test_real_api_enqueues_layer3_compress_after_threshold():
    _ensure_server_up()

    session_id = f"real_api_compress_{int(time.time())}"

    # 连续发送 5 轮用户消息（阈值 4）
    out = _chat(session_id, "第1轮：测试压缩触发")
    out = _chat(session_id, "第2轮：测试压缩触发")
    out = _chat(session_id, "第3轮：测试压缩触发")
    out = _chat(session_id, "第4轮：测试压缩触发")
    out = _chat(session_id, "第5轮：测试压缩触发")

    state = out.get("state") or {}
    assert isinstance(state, dict)

    queue = state.get("maintenance_queue", [])
    assert _has_task(queue, "layer3_compress", "layer3_compress")
