"""
Onboarding v2 · 后端集成冒烟测试（Agent H · P2）

本文件是整个 onboarding v2 销售漏斗后端侧的**端到端串联测试**：
analyze → report → chat 三个端点在一个测试里按顺序跑一次，
mock 掉所有 LLM 调用（不启 LangGraph 服务），只验证：

  1. 数据契约在三个端点之间对齐（AnalyzeResponse → ReportRequest →
     DiagnosisReport.collected_summary → ChatRequest.onboarding_summary）
  2. Agent D 的路由挂载降级逻辑落地：两个新路由在 app.routes 里真的能找到
  3. 根路径 `/` 302 跳 /splash.html，DISABLE_AUTH=1 时静态资源不被吞

所有 LLM 调用都被 monkeypatch 替换，因此不需要 API key、不需要网络、
不需要启动 langgraph dev 子进程——保持在 CI 里可复现。
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 确保 agent_impl/ 在 sys.path（与 conftest.py 对齐）
_AGENT_IMPL_DIR = Path(__file__).resolve().parent.parent
if str(_AGENT_IMPL_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_IMPL_DIR))

# 强制使用 mock LLM 并默认关闭 auth（与 start_dev.sh 一致）
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("DISABLE_AUTH", "1")


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #


_FREE_TEXT = (
    "他是我同事，认识快 3 个月了。上周我跟他表白了，他说再想想，"
    "现在回我消息明显变慢了，我想知道还有没有机会。"
)
_OCR_TEXT = (
    "[他] 嗯嗯\n[他] 在忙\n[我] 周六有空吗想约你看电影\n[他] 最近都忙，改天吧"
)
_IMAGE_URL = "https://example.com/onboarding/chat-01.png"


def _analyze_payload_mock() -> dict:
    """LLM 节点①的伪输出：A1/A2 skip，A3 有 rewrite，A4/A5 普通题。"""
    from onboarding_v2.question_bank import list_question_ids

    rules: dict[str, dict] = {}
    for qid in list_question_ids():
        rules[qid] = {
            "skip": False,
            "reason": None,
            "preselect": None,
            "rewrite": None,
        }
    rules["A1"] = {
        "skip": True,
        "reason": "用户自述是同事",
        "preselect": None,
        "rewrite": None,
    }
    rules["A2"] = {
        "skip": True,
        "reason": "用户已说「快 3 个月」",
        "preselect": None,
        "rewrite": None,
    }
    rules["A3"] = {
        "skip": False,
        "reason": "用户已表白，让 TA 再选一次细节",
        "preselect": ["A"],
        "rewrite": "TA 当时怎么回应？后面相处有变化吗？",
    }
    return {
        "skip_rules": rules,
        "first_hook": {
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
                "你说「现在 TA 回复我明显变慢」——行为层的直接信号。",
            ],
            "call_to_action": "接下来 5 道题，每题 15 秒——答完我给你明确的下一步判断。",
        },
    }


def _diagnosis_report_mock() -> dict:
    """LLM 节点③的伪输出：一份合法 DiagnosisReport。"""
    return {
        "report_id": "CR-PLACEHDR",  # 会被后端覆盖
        "state_label": {
            "name": "高危滑坡期",
            "severity": "danger",
            "theme_color": "#C00000",
        },
        "scores_5d": {
            "A": {"score": 52, "note": "表白后吸引力被需求感消耗"},
            "C": {"score": 68, "note": "日常同事接触维持基本舒适感"},
            "R": {"score": 18, "note": "张力几乎归零，见截图"},
            "T": {"score": 40, "note": "「再想想」压住信任"},
            "E": {"score": 31, "note": "回复延迟 3 倍，投入远大于回应"},
        },
        "core_issues": [
            {
                "title": "需求感暴露过早",
                "evidence": "认识第 3 个月就表白，TA 进入被追高位。",
            },
            {
                "title": "互动模式单一化",
                "evidence": "所有互动都在微信文字，形象被锁死。",
            },
        ],
        "trend_prediction": {
            "tone": "urgent",
            "text": "按目前趋势，2-3 周内 TA 大概率进一步拉开距离。",
        },
        "locked_teasers": [
            {
                "section": "完整局势分析 · 对方心理画像",
                "teaser": "TA 处于「混合信号」阶段，行为保留距离但没有明确定性……",
            },
            {
                "section": "专属行动规划 · Phase 1",
                "teaser": "Week 1：主动联系降到现在的 40%，不追问状态……",
            },
            {
                "section": "即时行动指南 · 下一条消息",
                "teaser": "当 TA 用「嗯嗯」敷衍时，不要追问，直接……",
            },
        ],
        "urgency_text": "窗口期 2-3 周，越早调整成本越低。",
        "collected_summary": (
            "用户与 Crush 是同事（认识约 3 个月），已主动表白且 TA 回「再想想」，"
            "随后出现回复变慢+邀约被拒（截图佐证）。核心问题是需求感暴露过早，"
            "当前处于「高危滑坡期」。"
        ),
    }


class _FakeMessage:
    """模仿 AIMessage：只有 .content 属性，够 run_analyze 用。"""

    def __init__(self, content: str):
        self.content = content


class _FakeAnalyzeLLM:
    """给 run_analyze 用的假 LLM：支持 bind_tools → tool_calls 路径。"""

    def __init__(self, payload: dict):
        self._payload = payload
        self._text = json.dumps(payload, ensure_ascii=False)

    def bind_tools(self, tools):
        payload = self._payload

        class _Bound:
            async def ainvoke(self, messages):
                msg = _FakeMessage("")
                msg.tool_calls = [{"name": "AnalyzeResponse", "args": payload, "id": "tc_fake"}]
                return msg

        return _Bound()

    async def ainvoke(self, messages):
        return _FakeMessage(self._text)


class _FakeReportLLM:
    """给 run_report 用的假 LLM：兼容 bind_tools / with_structured_output / ainvoke 路径。"""

    def __init__(self, payload: dict):
        self._payload = dict(payload)
        self.calls = 0

    def bind_tools(self, tools):
        payload = self._payload
        parent = self

        class _Bound:
            async def ainvoke(self, messages):
                parent.calls += 1
                msg = _FakeMessage("")
                msg.tool_calls = [{"name": "DiagnosisReport", "args": payload, "id": "tc_report_fake"}]
                return msg

            def invoke(self, messages):
                parent.calls += 1
                msg = _FakeMessage("")
                msg.tool_calls = [{"name": "DiagnosisReport", "args": payload, "id": "tc_report_fake"}]
                return msg

        return _Bound()

    def with_structured_output(self, _schema):
        parent = self

        class _Structured:
            async def ainvoke(self, _messages):
                parent.calls += 1
                return dict(parent._payload)

            def invoke(self, _messages):
                parent.calls += 1
                return dict(parent._payload)

        return _Structured()

    async def ainvoke(self, _messages):
        self.calls += 1
        return _FakeMessage(json.dumps(self._payload, ensure_ascii=False))

    def invoke(self, _messages):
        self.calls += 1
        return _FakeMessage(json.dumps(self._payload, ensure_ascii=False))


@pytest.fixture
def onboarding_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """构造只挂载 analyze + report 两路由的轻量 app，模拟 server.py 的行为但不拖 LangGraph。"""
    from api.onboarding_analyze import router as analyze_router
    from api.onboarding_report import router as report_router

    app = FastAPI(title="onboarding-v2-integration-test")
    app.include_router(analyze_router)
    app.include_router(report_router)
    return app


# --------------------------------------------------------------------------- #
# 1. 完整后端旅程（analyze → report → collected_summary 链路）
# --------------------------------------------------------------------------- #


def test_full_backend_journey_mock_llm(
    onboarding_app: FastAPI, monkeypatch: pytest.MonkeyPatch
):
    """三个端点按销售漏斗顺序打一遍,验证数据在契约之间对齐。

    不走 /api/chat 真实调用(那需要 LangGraph 服务),而是验证
    `ChatRequest(onboarding_payload=...)` 能被正确解析,且
    `render_onboarding_first_turn_message()` 会把 payload 渲染成
    首轮「[系统指令 · 仅本轮] + [诊断素材]」消息。
    """
    # ── Step 1: /api/onboarding/analyze ───────────────────────────────────
    from onboarding_v2.nodes import analyze as analyze_module
    from onboarding_v2.schemas import AnalyzeResponse

    monkeypatch.setattr(
        analyze_module,
        "get_onboarding_vision_llm",
        lambda **_kw: _FakeAnalyzeLLM(_analyze_payload_mock()),
    )

    client = TestClient(onboarding_app)
    analyze_body = {
        "session_id": "integration-sess-001",
        "free_text": _FREE_TEXT,
        "image_urls": [_IMAGE_URL],
        "ocr_texts": [_OCR_TEXT],
    }
    analyze_resp = client.post("/api/onboarding/analyze", json=analyze_body)
    assert analyze_resp.status_code == 200, analyze_resp.text

    analyze_data = analyze_resp.json()
    analyze_validated = AnalyzeResponse.model_validate(analyze_data)
    # 契约要求：skip_rules 必须覆盖全部题目（含 A0 性别题）
    from onboarding_v2.question_bank import list_question_ids
    assert set(analyze_validated.skip_rules.keys()) == set(list_question_ids())
    assert analyze_validated.first_hook, "first_hook 不能为空"
    assert analyze_validated.first_hook.title, "first_hook.title 不能为空"
    assert len(analyze_validated.first_hook.evidences) >= 2, "evidences 至少 2 条"
    # 抽查一下业务语义：A1/A2 skip=True（命中同事/3 个月关键词），A3 有 rewrite
    assert analyze_validated.skip_rules["A1"].skip is True
    assert analyze_validated.skip_rules["A2"].skip is True
    assert analyze_validated.skip_rules["A3"].rewrite is not None

    # ── Step 2: /api/onboarding/report ────────────────────────────────────
    from onboarding_v2.nodes import report as report_module
    from onboarding_v2.schemas import DiagnosisReport

    monkeypatch.setattr(
        report_module,
        "get_thinking_llm",
        lambda **_kw: _FakeReportLLM(_diagnosis_report_mock()),
    )
    # 避免磁盘读 prompt 文件；与 test_onboarding_v2_report.py 的 fixture 对齐
    monkeypatch.setattr(
        report_module,
        "_load_system_prompt",
        lambda: "SYSTEM: 你是诊断助手，严格按 schema 输出 JSON。",
    )

    # 答卷只提交未被 skip 的题（A3/A4/A5），模拟前端 payload 构造逻辑
    report_body = {
        "session_id": "integration-sess-001",
        "free_text": _FREE_TEXT,
        "ocr_texts": [_OCR_TEXT],
        "answers": {
            "A3": ["A"],
            "A4": ["A", "C"],
            "A5": "C",
        },
    }
    report_resp = client.post("/api/onboarding/report", json=report_body)
    assert report_resp.status_code == 200, report_resp.text

    report_data = report_resp.json()
    report_validated = DiagnosisReport.model_validate(report_data)

    # 五维齐全
    for dim in ("A", "C", "R", "T", "E"):
        dim_item = getattr(report_validated.scores_5d, dim)
        assert 0 <= dim_item.score <= 100
        assert dim_item.note, f"{dim} 维度 note 不能为空"

    # 2-3 条 core_issues
    assert 2 <= len(report_validated.core_issues) <= 3
    # 3-6 条 locked_teasers
    assert 3 <= len(report_validated.locked_teasers) <= 6
    # collected_summary 必须有内容（Agent G 会用它做首轮注入）
    summary = report_validated.collected_summary
    assert summary and len(summary.strip()) >= 10

    # ── Step 3: ChatRequest 接受 onboarding_payload,由模板渲染首轮消息 ────
    from api.chat import ChatRequest, _is_first_turn_for_thread
    from api.onboarding_handoff_prompt import (
        OnboardingPayload,
        OnboardingOcr,
        render_onboarding_first_turn_message,
    )

    payload = OnboardingPayload(
        free_text=_FREE_TEXT,
        ocr_texts=[OnboardingOcr(ocr_result=_OCR_TEXT)],
        answers={"A3": ["A"], "A4": ["A", "C"], "A5": "C"},
    )
    chat_req = ChatRequest(
        session_id="integration-sess-001",
        message="",  # 首轮自动触发时前端不带用户输入
        onboarding_payload=payload,
    )

    # 契约字段原样保留
    assert chat_req.onboarding_payload is not None
    assert chat_req.onboarding_payload.free_text == _FREE_TEXT

    # 首轮判定：base_state=None 视为首轮
    assert _is_first_turn_for_thread(None) is True

    # 契约:首轮由模板渲染为「[系统指令 · 仅本轮] + [诊断素材]」结构
    rendered = render_onboarding_first_turn_message(chat_req.onboarding_payload)
    assert rendered.startswith("[系统指令 · 仅本轮]"), rendered[:60]
    assert "[诊断素材]" in rendered
    assert "## 用户自由描述" in rendered
    assert _FREE_TEXT.strip() in rendered
    # OCR 段存在且带原文
    assert "## 截图 OCR" in rendered
    assert _OCR_TEXT.strip() in rendered
    # 答题段按人话渲染
    assert "## 筛题答卷" in rendered
    assert "A3" in rendered and "A5" in rendered
    # collected_summary 字段仍然由 report 端点产出,供分析/日志用,但不再注入 chat 消息
    assert summary and summary not in rendered


# --------------------------------------------------------------------------- #
# 2. 路由挂载：坐实 Agent D 的降级 import 在 B/C 已到位时真的挂上了
# --------------------------------------------------------------------------- #


def _reload_server_fresh(monkeypatch: pytest.MonkeyPatch):
    """重新 import server，让 DISABLE_AUTH / import onboarding_* 走一次。"""
    monkeypatch.setenv("DISABLE_AUTH", "1")
    for name in ("server",):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    import server  # noqa: WPS433

    importlib.reload(server)
    return server


def test_routes_mounted_after_p1(monkeypatch: pytest.MonkeyPatch):
    """Agent D 用了 try/except ImportError 做惰性挂载，B/C 产出后两条新路由必须存在。

    这个测试的价值：server.py 的降级分支在 B/C 未产出时会 logger.warning
    然后不挂路由——本测试从 app.routes 里验证路由真正被挂上了（不是假阳性）。
    """
    server_module = _reload_server_fresh(monkeypatch)
    paths = {getattr(r, "path", "") for r in server_module.app.routes}

    assert "/api/onboarding/analyze" in paths, (
        "Agent D 的降级分支未把 analyze 路由挂上，请检查 api.onboarding_analyze 是否可 import。"
    )
    assert "/api/onboarding/report" in paths, (
        "Agent D 的降级分支未把 report 路由挂上，请检查 api.onboarding_report 是否可 import。"
    )

    # 同步确认老的 /api/chat 还在（没被覆盖）
    assert "/api/chat" in paths, "/api/chat 路由消失，可能 api_router 挂载出问题"


# --------------------------------------------------------------------------- #
# 3. 根路径重定向 + DISABLE_AUTH=1 生效
# --------------------------------------------------------------------------- #


def test_root_redirects_to_splash_without_auth(monkeypatch: pytest.MonkeyPatch):
    """DISABLE_AUTH=1 时根路径应 302 到 /splash.html，且 AuthRedirectMiddleware 未注入。"""
    server_module = _reload_server_fresh(monkeypatch)

    # 1) auth 中间件状态
    assert server_module._auth_disabled is True, (
        "DISABLE_AUTH 缺省被定义为 '1'，server._auth_disabled 应为 True"
    )

    # 2) / 的 302 行为（不 follow redirect，直接看 Location）
    with TestClient(server_module.app, follow_redirects=False) as client:
        resp = client.get("/")
    assert resp.status_code == 302, f"根路径应 302，实际 {resp.status_code}"
    location = resp.headers.get("location", "")
    assert location.endswith("/splash.html"), (
        f"根路径 Location 应指向 /splash.html，实际：{location!r}"
    )


# --------------------------------------------------------------------------- #
# 4. 降级路径：LLM 炸了仍返回 200 + 兜底 payload（不阻断漏斗）
# --------------------------------------------------------------------------- #


def test_analyze_fallback_keeps_journey_alive(
    onboarding_app: FastAPI, monkeypatch: pytest.MonkeyPatch
):
    """analyze 的 LLM 一旦失败，前端应该仍能拿到合法 AnalyzeResponse 继续答题。

    这是销售漏斗可用性保证——API_CONTRACT §2 的降级行为。
    """
    from onboarding_v2.nodes import analyze as analyze_module

    class _ExplodingLLM:
        def bind_tools(self, tools):
            class _Bound:
                async def ainvoke(self, _messages):
                    raise RuntimeError("simulated provider outage")
            return _Bound()

        async def ainvoke(self, _messages):
            raise RuntimeError("simulated provider outage")

    monkeypatch.setattr(analyze_module, "get_onboarding_vision_llm", lambda **_kw: _ExplodingLLM())

    client = TestClient(onboarding_app)
    resp = client.post(
        "/api/onboarding/analyze",
        json={
            "session_id": "fallback-sess",
            "free_text": "描述一段足够长的内容用于满足契约最小长度",
            "image_urls": [],
            "ocr_texts": [],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # 契约：降级时 skip_rules 覆盖可筛题（A1-A5），不含 A0 性别题（不参与筛题逻辑）
    from onboarding_v2.question_bank import list_question_ids
    assert set(data["skip_rules"].keys()) == set(list_question_ids()) - {"A0"}
    for qid, rule in data["skip_rules"].items():
        assert rule["skip"] is False, f"降级 payload {qid} 不应预设 skip=True"
    assert isinstance(data["first_hook"], dict)
    assert data["first_hook"].get("title")
    assert isinstance(data["first_hook"].get("evidences"), list)


def test_report_failure_returns_503_style(
    onboarding_app: FastAPI, monkeypatch: pytest.MonkeyPatch
):
    """report 的 LLM 连续失败应返回 5xx，避免前端把半成品当成功报告展示。

    对应 API_CONTRACT §3 的降级行为；onboarding_v2/nodes/report.py 里是 500。
    """
    from onboarding_v2.nodes import report as report_module

    class _ExplodingLLM:
        def with_structured_output(self, _schema):
            raise RuntimeError("structured bind failed")

        async def ainvoke(self, _messages):
            raise RuntimeError("provider down")

        def invoke(self, _messages):
            raise RuntimeError("provider down")

    monkeypatch.setattr(report_module, "get_thinking_llm", lambda **_kw: _ExplodingLLM())
    monkeypatch.setattr(
        report_module,
        "_load_system_prompt",
        lambda: "SYSTEM: 测试降级",
    )

    client = TestClient(onboarding_app)
    resp = client.post(
        "/api/onboarding/report",
        json={
            "session_id": "fail-sess",
            "free_text": "测试降级场景的描述文本。",
            "ocr_texts": [],
            "answers": {"A5": "C"},
        },
    )
    assert resp.status_code == 500, resp.text
    assert "REPORT_GENERATION_FAILED" in resp.text


# --------------------------------------------------------------------------- #
# 5. ChatRequest 首轮 / 非首轮的注入行为（集成层断言）
# --------------------------------------------------------------------------- #


def test_chat_request_non_first_turn_drops_payload():
    """非首轮请求即使带 onboarding_payload,也不应触发模板前置(契约 §4 规则 1)。"""
    from api.chat import ChatRequest, _build_user_message_with_images, _is_first_turn_for_thread
    from api.onboarding_handoff_prompt import OnboardingPayload

    req = ChatRequest(
        session_id="s",
        message="下一步该怎么办？",
        onboarding_payload=OnboardingPayload(free_text="应被忽略"),
    )
    # 模拟 base_state 里已经有 messages(非首轮)
    base_state = {"messages": [{"role": "user", "content": "之前的消息"}]}
    assert _is_first_turn_for_thread(base_state) is False

    # 非首轮:chat.py 主流程会显式清掉 payload——这里模拟这一步
    req.onboarding_payload = None
    out = _build_user_message_with_images(req)
    assert "[系统指令 · 仅本轮]" not in out
    assert "[诊断素材]" not in out
    assert out == "下一步该怎么办？"
