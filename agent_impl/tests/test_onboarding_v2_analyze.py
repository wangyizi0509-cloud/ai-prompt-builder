"""Onboarding v2 · `/api/onboarding/analyze` 单元测试

覆盖：
  - `test_run_analyze_happy_path`：LLM 返回合法 JSON → AnalyzeResponse 合法
  - `test_run_analyze_malformed_json`：LLM 返回乱码 → 走降级
  - `test_run_analyze_missing_fields`：LLM 返回少了 A5 → 走降级
  - `test_run_analyze_fenced_json`：LLM 输出被 ```json ... ``` 包裹 → 仍能解析
  - `test_analyze_endpoint_smoke`：FastAPI TestClient 命中路由 → 200 + schema 合法
  - `test_analyze_endpoint_free_text_too_short`：free_text < 5 → 422（Pydantic 触发）
  - `test_fallback_covers_all_questions`：降级 payload 包含 A1-A5

所有 LLM 调用都通过 `monkeypatch` 替换为同步/异步假函数，不真调模型。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 确保可以从仓库的 agent_impl 目录 import（与 conftest.py 一致）
_AGENT_IMPL_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_IMPL_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_IMPL_DIR))

# 避免触发真实 LLM
os.environ.setdefault("LLM_PROVIDER", "mock")


from onboarding_v2.nodes import analyze as analyze_module  # noqa: E402
from onboarding_v2.nodes.analyze import (  # noqa: E402
    _build_fallback_first_hook,
    run_analyze,
)
from onboarding_v2.nodes.analyze import _SKIPPABLE_QUESTION_IDS  # noqa: E402
from onboarding_v2.question_bank import list_question_ids  # noqa: E402
from onboarding_v2.schemas import AnalyzeRequest, AnalyzeResponse, FirstHook  # noqa: E402


def _happy_first_hook() -> dict:
    """返回 FirstHook 结构化字典，字段齐全、字数落区间。"""
    return {
        "verdict_tag": "信号暴露",
        "verdict_color": "amber",
        "title": "你提到 TA「回复变慢」——这不是冷淡，是在按暂停键。",
        "body": (
            "TA 不是对你没兴趣，而是表白后进入了情绪消化期。"
            "回复变慢 + 没切断联系 = 还在想，不是关门；"
            "接下来几个问题我帮你确认 TA 是借机划线还是等你先给台阶。"
        ),
        "highlights": ["节奏变慢", "关系定义期", "情绪消化"],
        "evidences": [
            "你提到「上周我表白了 TA 说再想想」——这是典型的缓冲型回应。",
            "你说「现在 TA 回复我明显变慢」——这是行为层面的直接信号。",
        ],
        "call_to_action": "接下来 5 道题，每题 15 秒——答完我给你明确的下一步判断。",
    }


# ---------- 通用 fixture ----------


def _sample_request(**overrides) -> AnalyzeRequest:
    payload = {
        "session_id": "sess-test-001",
        "free_text": "我们是同事认识三个月，上周我表白了 TA 说再想想，现在 TA 回复我明显变慢",
        "image_urls": [
            "https://example.com/chat-01.png",
        ],
        "ocr_texts": [
            "[他] 嗯嗯\n[我] 周六有空吗\n[他] 最近忙，改天吧",
        ],
    }
    payload.update(overrides)
    return AnalyzeRequest(**payload)


def _happy_llm_payload() -> dict:
    skip_rules = {}
    for qid in _SKIPPABLE_QUESTION_IDS:
        skip_rules[qid] = {
            "skip": False,
            "reason": None,
            "preselect": None,
            "rewrite": None,
        }
    # 造一条真实业务里会出现的跳过
    skip_rules["A1"] = {
        "skip": True,
        "reason": "用户自述是同事",
        "preselect": None,
        "rewrite": None,
    }
    return {
        "skip_rules": skip_rules,
        "first_hook": _happy_first_hook(),
    }


class _FakeMessage:
    def __init__(self, content):
        self.content = content


def _install_fake_llm(monkeypatch: pytest.MonkeyPatch, output_text: str) -> None:
    """把 `get_onboarding_vision_llm` 替换成一个假 LLM。

    - 默认：content 里放 `output_text`，tool_calls 为空（走文本兜底）
    - 若 `output_text` 是合法 JSON dict（顶层有 skip_rules + first_hook），额外
      以同样 dict 作为 tool_calls[0].args，模拟 GLM-4.6V 的 tool call 行为
    """
    tool_args: dict | None = None
    try:
        parsed = json.loads(output_text)
        if isinstance(parsed, dict) and "skip_rules" in parsed:
            tool_args = parsed
    except Exception:
        tool_args = None

    class _FakeToolMessage:
        def __init__(self, content: str, tool_calls: list):
            self.content = content
            self.tool_calls = tool_calls

    class _FakeLLM:
        def bind_tools(self, tools, tool_choice=None):  # noqa: ARG002
            return self

        async def ainvoke(self, messages):  # noqa: D401
            tool_calls: list = []
            if tool_args is not None:
                tool_calls = [
                    {
                        "name": "AnalyzeResponse",
                        "args": tool_args,
                        "id": "call_fake_1",
                        "type": "tool_call",
                    }
                ]
            return _FakeToolMessage(output_text, tool_calls)

    monkeypatch.setattr(analyze_module, "get_onboarding_vision_llm", lambda **kwargs: _FakeLLM())


# ---------- 基础用例 ----------


def test_run_analyze_happy_path(monkeypatch: pytest.MonkeyPatch):
    """LLM 返回合法 JSON → 解析成功，AnalyzeResponse 合法。"""
    payload = _happy_llm_payload()
    _install_fake_llm(monkeypatch, json.dumps(payload, ensure_ascii=False))

    response = asyncio.run(run_analyze(_sample_request()))

    # 确认是严格模型实例
    assert isinstance(response, AnalyzeResponse)
    # Round-trip：`model_validate(dump())` 仍然成立，且覆盖全部 5 题
    validated = AnalyzeResponse.model_validate(response.model_dump())
    assert set(validated.skip_rules.keys()) == set(_SKIPPABLE_QUESTION_IDS)
    assert validated.skip_rules["A1"].skip is True
    assert isinstance(validated.first_hook, FirstHook)
    assert "回复变慢" in validated.first_hook.title
    assert len(validated.first_hook.evidences) >= 2


def test_run_analyze_fenced_json(monkeypatch: pytest.MonkeyPatch):
    """LLM 把 JSON 包在 ```json ... ``` 代码块里 → 仍能解析。"""
    payload = _happy_llm_payload()
    wrapped = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    _install_fake_llm(monkeypatch, wrapped)

    response = asyncio.run(run_analyze(_sample_request()))
    assert isinstance(response, AnalyzeResponse)
    assert set(response.skip_rules.keys()) == set(_SKIPPABLE_QUESTION_IDS)


def test_run_analyze_malformed_json(monkeypatch: pytest.MonkeyPatch):
    """LLM 返回完全无法解析的文本 → 降级到兜底 payload。"""
    _install_fake_llm(monkeypatch, "完全不是 JSON 的乱码 abc{def)")

    response = asyncio.run(run_analyze(_sample_request()))
    assert isinstance(response, AnalyzeResponse)
    assert response.first_hook == _build_fallback_first_hook()
    assert set(response.skip_rules.keys()) == set(_SKIPPABLE_QUESTION_IDS)
    for qid in _SKIPPABLE_QUESTION_IDS:
        rule = response.skip_rules[qid]
        assert rule.skip is False
        assert rule.preselect is None
        assert rule.rewrite is None


def test_run_analyze_missing_fields(monkeypatch: pytest.MonkeyPatch):
    """LLM 返回合法 JSON 但缺题（例如少 A5）→ 走降级。"""
    payload = _happy_llm_payload()
    # 去掉 A5，制造缺字段
    payload["skip_rules"].pop("A5")
    _install_fake_llm(monkeypatch, json.dumps(payload, ensure_ascii=False))

    response = asyncio.run(run_analyze(_sample_request()))
    assert isinstance(response, AnalyzeResponse)
    # 降级 payload 覆盖 A5
    assert response.first_hook == _build_fallback_first_hook()
    assert "A5" in response.skip_rules


def test_run_analyze_llm_exception(monkeypatch: pytest.MonkeyPatch):
    """LLM 调用抛异常（例如 API 挂了）→ 走降级。"""

    class _ExplodingLLM:
        def bind_tools(self, tools, tool_choice=None):  # noqa: ARG002
            return self

        async def ainvoke(self, messages):
            raise RuntimeError("simulated network error")

    monkeypatch.setattr(
        analyze_module, "get_onboarding_vision_llm", lambda **kwargs: _ExplodingLLM()
    )

    response = asyncio.run(run_analyze(_sample_request()))
    assert isinstance(response, AnalyzeResponse)
    assert response.first_hook == _build_fallback_first_hook()


def test_fallback_covers_all_questions():
    """直接构造降级 payload，确认题号齐整 + 字段合法。"""
    from onboarding_v2.nodes.analyze import _build_fallback_response

    resp = _build_fallback_response()
    assert isinstance(resp, AnalyzeResponse)
    assert set(resp.skip_rules.keys()) == set(_SKIPPABLE_QUESTION_IDS)
    # 确保 model_validate 之后仍合法（重要：防止 future 修改破坏降级路径）
    _ = AnalyzeResponse.model_validate(resp.model_dump())


# ---------- FastAPI 路由冒烟 ----------


@pytest.fixture(scope="module")
def analyze_client() -> TestClient:
    """仅挂 analyze router 的轻量 app，避免拉起整个 server.py。"""
    from fastapi import FastAPI

    from api.onboarding_analyze import router as analyze_router

    app = FastAPI()
    app.include_router(analyze_router)
    return TestClient(app)


def test_analyze_endpoint_smoke(
    analyze_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """TestClient 打 /api/onboarding/analyze → 200 + schema 合法。"""
    payload = _happy_llm_payload()
    _install_fake_llm(monkeypatch, json.dumps(payload, ensure_ascii=False))

    body = {
        "session_id": "sess-smoke-001",
        "free_text": "我们是同事认识三个月，表白过 TA 说再想想，回复变慢",
        "image_urls": [],
        "ocr_texts": [],
    }
    resp = analyze_client.post("/api/onboarding/analyze", json=body)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    validated = AnalyzeResponse.model_validate(data)
    assert set(validated.skip_rules.keys()) == set(_SKIPPABLE_QUESTION_IDS)
    assert isinstance(validated.first_hook, FirstHook)
    assert len(validated.first_hook.evidences) >= 2


def test_analyze_endpoint_free_text_too_short(analyze_client: TestClient):
    """free_text < 5 字 → Pydantic 422（契约要求前端阻止提交）。"""
    body = {
        "session_id": "sess-short",
        "free_text": "哦",
        "image_urls": [],
        "ocr_texts": [],
    }
    resp = analyze_client.post("/api/onboarding/analyze", json=body)
    assert resp.status_code == 422


def test_analyze_endpoint_llm_failure_returns_fallback(
    analyze_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """LLM 炸了，端点仍返回 200 + 降级 payload（不阻断用户）。"""

    class _ExplodingLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("network down")

    monkeypatch.setattr(
        analyze_module, "get_onboarding_vision_llm", lambda **kwargs: _ExplodingLLM()
    )

    body = {
        "session_id": "sess-boom",
        "free_text": "描述稍微长一点点的内容这里",
        "image_urls": [],
        "ocr_texts": [],
    }
    resp = analyze_client.post("/api/onboarding/analyze", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["first_hook"] == _build_fallback_first_hook().model_dump()
    assert set(data["skip_rules"].keys()) == set(_SKIPPABLE_QUESTION_IDS)
