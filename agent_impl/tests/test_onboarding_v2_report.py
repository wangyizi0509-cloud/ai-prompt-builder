"""
Onboarding v2 · Agent C(诊断报告)单测。

覆盖:
1. happy path:LLM 返回合法 DiagnosisReport → 响应字段齐全 & schema 通过
2. 第一次失败 → 第二次成功的重试能力
3. 两次都失败 → 抛 HTTPException(500, REPORT_GENERATION_FAILED)
4. LLM 返回缺字段 JSON → 第一次 schema 校验失败触发重试
5. FastAPI smoke:POST /api/onboarding/report 全链路打通

策略:全部用 unittest.mock 打桩 `onboarding_v2.nodes.report.get_llm`,
不真调 LLM。每个假 LLM 实现 `with_structured_output` + `invoke`/`ainvoke`
两条路径,让测试可以覆盖两种实现分支。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from onboarding_v2.nodes import report as report_module
from onboarding_v2.nodes.report import run_report
from onboarding_v2.schemas import DiagnosisReport, ReportRequest


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _valid_report_dict() -> dict[str, Any]:
    """一份合法的 DiagnosisReport 字典,schema 校验可通过。"""
    return {
        "report_id": "CR-FROMLLM1",  # 会被后端覆盖,占位就行
        "state_label": {
            "name": "高危滑坡期",
            "severity": "danger",
            "theme_color": "#C00000",
        },
        "scores_5d": {
            "A": {"score": 52, "note": "表白后吸引力被需求感消耗"},
            "C": {"score": 68, "note": "同事接触维持基本舒适感"},
            "R": {"score": 18, "note": "张力几乎归零(敷衍回复)"},
            "T": {"score": 40, "note": "「再想想」压住信任"},
            "E": {"score": 31, "note": "回复延迟 3 倍,投入远大于回应"},
        },
        "core_issues": [
            {
                "title": "需求感暴露过早",
                "evidence": "你在认识第 3 个月就表白,TA 进入被追高位。",
            },
            {
                "title": "互动模式单一化",
                "evidence": "所有互动都在微信文字,形象被锁死在「同事」。",
            },
        ],
        "trend_prediction": {
            "tone": "urgent",
            "text": "按目前趋势,2-3 周内 TA 大概率会拉开距离。",
        },
        "locked_teasers": [
            {
                "section": "完整局势分析 · 对方心理画像",
                "teaser": "TA 处于「混合信号」阶段,行为保留距离但没有明确定性……",
            },
            {
                "section": "专属行动规划 · Phase 1(第 1-2 周)",
                "teaser": "Week 1:主动联系降到现在的 40%。你的具体任务是……",
            },
            {
                "section": "即时行动指南 · 下一条消息",
                "teaser": "当 TA 用「嗯嗯」敷衍时,不要追问,直接……",
            },
        ],
        "urgency_text": "窗口期 2-3 周,越早调整扭转成本越低。",
        "collected_summary": (
            "用户与 Crush 是同事(认识约 3 个月),已主动表白且 TA 回「再想想」,"
            "R=18 偏低,核心问题是需求感暴露过早,当前处于「高危滑坡期」。"
        ),
    }


def _missing_field_dict() -> dict[str, Any]:
    """故意缺 `core_issues` 的 schema 违规 payload。"""
    data = _valid_report_dict()
    data.pop("core_issues")
    return data


def _make_request() -> ReportRequest:
    return ReportRequest(
        session_id="sess-test-0001",
        free_text="他是我同事,认识快 3 个月了,我表白了 TA 说再想想,现在回消息变慢了。",
        ocr_texts=["[他] 嗯嗯\n[他] 在忙", "[我] 周六约电影\n[他] 最近都忙,改天吧"],
        answers={"A3": ["A"], "A4": ["A", "C"], "A5": "C"},
    )


class _FakeLLM:
    """最小假 LLM,**只支持 tool calling 路径**(新 report 节点仅此一路)。

    - `bind_tools(tools, tool_choice=...)` 返回 self(链式)
    - `ainvoke(messages)` 根据 `script` 头部元素决定行为:
        * dict            → AIMessage(content="", tool_calls=[{name:"DiagnosisReport",args:dict,id:...}])
        * DiagnosisReport → 同上,args=实例 model_dump()
        * AIMessage       → 直接返回(方便测试 "tool_calls 为空" 的异常路径)
        * Exception 子类  → raise
        * "__NO_TOOL_CALL__"(str) → AIMessage(content="我只是自然语言没调工具", tool_calls=[])
    """

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls = 0
        self.bind_tools_calls: list[dict[str, Any]] = []
        self.captured_messages: list[Any] = []

    def bind_tools(self, tools, tool_choice=None):  # noqa: ARG002
        self.bind_tools_calls.append(
            {"tools": tools, "tool_choice": tool_choice}
        )
        return self

    def _next(self) -> Any:
        self.calls += 1
        if not self.script:
            raise AssertionError("FakeLLM 脚本已空但仍被调用")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def _to_aimessage(self, item: Any) -> AIMessage:
        if isinstance(item, AIMessage):
            return item
        if isinstance(item, str) and item == "__NO_TOOL_CALL__":
            return AIMessage(content="这里我忘了调工具了", tool_calls=[])
        if isinstance(item, DiagnosisReport):
            args = item.model_dump()
        elif isinstance(item, dict):
            args = dict(item)
        else:
            # 其它类型按 "args 非 dict" 处理 → AIMessage 里塞个 list
            args = item  # type: ignore[assignment]
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "DiagnosisReport",
                    "args": args,
                    "id": "call_fake_1",
                    "type": "tool_call",
                }
            ],
        )

    def invoke(self, messages):
        self.captured_messages.append(messages)
        item = self._next()
        return self._to_aimessage(item)

    async def ainvoke(self, messages):
        self.captured_messages.append(messages)
        item = self._next()
        return self._to_aimessage(item)


@pytest.fixture(autouse=True)
def _reset_prompt_cache(monkeypatch):
    """保证每次测试重新读 prompt(避免别的测试的 monkeypatch 泄漏)。"""
    # 目前 _load_system_prompt 无缓存,不需要清理;留这个 fixture 占位
    # 用一个轻量短 prompt 替代真实文件,加速测试 + 避免磁盘依赖
    monkeypatch.setattr(
        report_module,
        "_load_system_prompt",
        lambda: "SYSTEM: 你是诊断助手,按 schema 输出 JSON。",
    )


# --------------------------------------------------------------------------- #
# Tests for run_report
# --------------------------------------------------------------------------- #


def test_run_report_happy_path(monkeypatch):
    """LLM 第一次就返回合法报告,run_report 应直接成功并覆盖 report_id。"""
    fake = _FakeLLM(script=[_valid_report_dict()])
    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **kw: fake)

    result = asyncio.run(run_report(_make_request()))

    assert isinstance(result, DiagnosisReport)
    # 核心字段齐全
    assert result.report_id.startswith("CR-")
    assert len(result.report_id) == 11  # "CR-" + 8 位十六进制
    assert result.state_label.name == "高危滑坡期"
    assert result.state_label.severity == "danger"
    assert result.scores_5d.A.score == 52
    assert result.scores_5d.R.score == 18
    # 5 维必须齐全(Pydantic 强制,再断言一遍保险)
    for dim in ("A", "C", "R", "T", "E"):
        assert hasattr(result.scores_5d, dim)
    # core_issues 条数在 [2, 3]
    assert 2 <= len(result.core_issues) <= 3
    # locked_teasers 条数在 [3, 6]
    assert 3 <= len(result.locked_teasers) <= 6
    # teaser 应该有「……」悬念(不是强校验,这里只断言有字符)
    for t in result.locked_teasers:
        assert t.teaser
    # trend_prediction tone 必须是 urgent/hopeful
    assert result.trend_prediction.tone in {"urgent", "hopeful"}
    assert result.collected_summary  # 非空
    # fake LLM 被调用一次
    assert fake.calls == 1


def test_run_report_retry_on_first_failure(monkeypatch):
    """第一次 schema 违规 → 第二次成功,最终应返回合法报告。"""
    fake = _FakeLLM(script=[_missing_field_dict(), _valid_report_dict()])
    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **kw: fake)

    result = asyncio.run(run_report(_make_request()))

    assert isinstance(result, DiagnosisReport)
    assert result.state_label.name == "高危滑坡期"
    assert fake.calls == 2  # 重试过一次


def test_run_report_raises_on_double_failure(monkeypatch):
    """连续两次 LLM 抛异常 → run_report 应抛 HTTPException(500)。"""
    fake = _FakeLLM(
        script=[
            RuntimeError("llm timeout round 1"),
            RuntimeError("llm timeout round 2"),
        ]
    )
    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **kw: fake)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(run_report(_make_request()))

    assert exc.value.status_code == 500
    assert "REPORT_GENERATION_FAILED" in str(exc.value.detail)
    assert fake.calls == 2


def test_run_report_schema_violation_triggers_retry(monkeypatch):
    """第一次 tool_call args 缺字段 → ValidationError → 第二次成功。"""
    fake = _FakeLLM(
        script=[
            _missing_field_dict(),  # tool_call args 缺字段 → 校验失败
            _valid_report_dict(),    # 重试成功
        ]
    )
    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **kw: fake)

    result = asyncio.run(run_report(_make_request()))

    assert isinstance(result, DiagnosisReport)
    assert fake.calls == 2, "第一次 schema 违规应触发重试"


def test_run_report_schema_violation_double_failure(monkeypatch):
    """两次 tool_call args 都缺字段 → 抛 HTTPException(500)。"""
    fake = _FakeLLM(
        script=[
            _missing_field_dict(),
            _missing_field_dict(),
        ]
    )
    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **kw: fake)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(run_report(_make_request()))

    assert exc.value.status_code == 500


def test_run_report_no_tool_call_triggers_retry(monkeypatch):
    """模型违规输出自然语言而非 tool_call → ValueError → 触发重试。"""
    fake = _FakeLLM(
        script=[
            "__NO_TOOL_CALL__",       # 第一次没调工具
            _valid_report_dict(),      # 第二次正常
        ]
    )
    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **kw: fake)

    result = asyncio.run(run_report(_make_request()))

    assert isinstance(result, DiagnosisReport)
    assert fake.calls == 2


def test_run_report_overrides_report_id(monkeypatch):
    """后端生成的 report_id 永远覆盖 LLM 输出,不让 LLM 乱编。"""
    payload = _valid_report_dict()
    payload["report_id"] = "CR-LLMFAKE"
    fake = _FakeLLM(script=[payload])
    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **kw: fake)

    result = asyncio.run(run_report(_make_request()))

    assert result.report_id != "CR-LLMFAKE"
    assert result.report_id.startswith("CR-")
    # 8 位十六进制(大写)
    suffix = result.report_id[3:]
    assert len(suffix) == 8
    assert all(c in "0123456789ABCDEF" for c in suffix)


def test_run_report_renders_answers_for_prompt(monkeypatch):
    """验证 user prompt 把 answers 还原成可读文案送给 LLM(避免 schema 漂移)。"""
    fake = _FakeLLM(script=[_valid_report_dict()])
    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **kw: fake)

    asyncio.run(run_report(_make_request()))

    assert fake.captured_messages, "LLM 应当被调用过一次"
    messages = fake.captured_messages[0]
    user_text = messages[1].content  # [system, human]
    assert "主动表白" in user_text, "A3 选项 A 的 label 应出现在 prompt 里"
    assert "TA 回消息越来越慢" in user_text, "A4 选项 A 的 label 应出现在 prompt 里"
    assert "想知道对方到底什么态度" in user_text, "A5 选项 C 的 label 应出现在 prompt 里"
    assert "他是我同事" in user_text, "自由描述原文应出现在 prompt 里"
    assert "嗯嗯" in user_text, "截图 OCR 应出现在 prompt 里"


# --------------------------------------------------------------------------- #
# Test for FastAPI route
# --------------------------------------------------------------------------- #


def test_report_endpoint_smoke(monkeypatch):
    """用 FastAPI TestClient 跑一次 /api/onboarding/report,断言 200 + 完整 schema。"""
    fake = _FakeLLM(script=[_valid_report_dict()])
    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **kw: fake)

    # 临时组装一个 app,只挂 onboarding_report 路由
    from api.onboarding_report import router  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    payload = {
        "session_id": "sess-smoke-0001",
        "free_text": "他是我同事,认识快 3 个月了,我表白了 TA 说再想想。",
        "ocr_texts": ["[他] 嗯嗯\n[他] 在忙"],
        "answers": {"A3": ["A"], "A4": ["A", "C"], "A5": "C"},
    }

    resp = client.post("/api/onboarding/report", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # schema 再过一次校验,确认返回体合规
    report = DiagnosisReport.model_validate(body)
    assert report.state_label.name in {
        "高危滑坡期",
        "舒适区陷阱",
        "临门犹豫期",
        "信号过载期",
        "空白探索期",
        "僵局观察期",
    }
    assert 2 <= len(report.core_issues) <= 3
    assert 3 <= len(report.locked_teasers) <= 6
    assert report.report_id.startswith("CR-")


def test_report_endpoint_returns_500_on_llm_failure(monkeypatch):
    """LLM 连续失败 → 路由应该返回 500 + REPORT_GENERATION_FAILED。"""
    fake = _FakeLLM(
        script=[
            RuntimeError("boom 1"),
            RuntimeError("boom 2"),
        ]
    )
    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **kw: fake)

    from api.onboarding_report import router  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.post(
        "/api/onboarding/report",
        json={
            "session_id": "sess-fail-0001",
            "free_text": "测试失败场景,随便写一些字。",
            "ocr_texts": [],
            "answers": {"A5": "C"},
        },
    )
    assert resp.status_code == 500
    assert "REPORT_GENERATION_FAILED" in resp.text
