"""
Onboarding v2 · server 挂载冒烟测试（Agent D 产出）

验证三件事：
1. 两个新路由 `/api/onboarding/analyze` 和 `/api/onboarding/report` 已经挂到 app
   （发 OPTIONS 足够，不真调 LLM）
2. 根路径 `/` 返回 302 并跳转到 `/splash.html`
3. DISABLE_AUTH=1 时 `/api/chat` 不会被 `AuthRedirectMiddleware` 吃掉

注意：
- 如果 Agent B/C 还没产出 `api/onboarding_analyze.py` / `api/onboarding_report.py`，
  路由冒烟测试会走 skip（看 `app.routes` 里是否有对应 path 判断）。
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Iterable

import pytest
from fastapi.testclient import TestClient

# 确保从仓库根也能 import server
AGENT_IMPL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if AGENT_IMPL_DIR not in sys.path:
    sys.path.insert(0, AGENT_IMPL_DIR)


# ---------- helpers ----------


def _fresh_app(monkeypatch: pytest.MonkeyPatch, *, disable_auth: str = "1"):
    """每个测试一个干净的 app：按需设置 DISABLE_AUTH，重新 import server。"""
    monkeypatch.setenv("DISABLE_AUTH", disable_auth)
    # 兼容以往 import 过 server 的情况
    for name in ("server", "api"):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    import server  # noqa: WPS433 — 动态 import 是有意的
    importlib.reload(server)
    return server.app


def _collect_paths(app) -> Iterable[str]:
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            yield path


# ---------- 1. 路由是否挂上 ----------


def _onboarding_routes_available() -> bool:
    """检查 Agent B/C 的路由模块是否都到位了。"""
    try:
        importlib.import_module("api.onboarding_analyze")
        importlib.import_module("api.onboarding_report")
        return True
    except ImportError:
        return False


@pytest.mark.skipif(
    not _onboarding_routes_available(),
    reason="Agent B/C 尚未产出 api/onboarding_analyze.py / api/onboarding_report.py，路由冒烟跳过。",
)
def test_onboarding_analyze_route_is_mounted(monkeypatch: pytest.MonkeyPatch):
    app = _fresh_app(monkeypatch)
    paths = list(_collect_paths(app))
    assert "/api/onboarding/analyze" in paths, (
        f"/api/onboarding/analyze 未挂到 app，已有路由前缀：{[p for p in paths if 'onboarding' in p]}"
    )


@pytest.mark.skipif(
    not _onboarding_routes_available(),
    reason="Agent B/C 尚未产出 api/onboarding_analyze.py / api/onboarding_report.py，路由冒烟跳过。",
)
def test_onboarding_report_route_is_mounted(monkeypatch: pytest.MonkeyPatch):
    app = _fresh_app(monkeypatch)
    paths = list(_collect_paths(app))
    assert "/api/onboarding/report" in paths, (
        f"/api/onboarding/report 未挂到 app，已有路由前缀：{[p for p in paths if 'onboarding' in p]}"
    )


# ---------- 2. 根路径 302 到 splash.html ----------


def test_root_redirects_to_splash(monkeypatch: pytest.MonkeyPatch):
    app = _fresh_app(monkeypatch, disable_auth="1")
    with TestClient(app, follow_redirects=False) as client:
        resp = client.get("/")
    assert resp.status_code == 302, (
        f"根路径应返回 302，实际：{resp.status_code} / {resp.headers}"
    )
    location = resp.headers.get("location", "")
    assert location.endswith("/splash.html"), (
        f"根路径应跳 /splash.html，实际 Location={location!r}"
    )


# ---------- 3. DISABLE_AUTH=1 时 /api/chat 不被 auth 中间件拦 ----------


def test_disable_auth_bypasses_middleware_on_chat(monkeypatch: pytest.MonkeyPatch):
    """关掉 auth 后，/api/chat 的 OPTIONS 应走到 CORS / 路由，而不是 401。

    注意：这里不真调 /api/chat 的 POST 业务逻辑（那会触发 LangGraph 依赖），
    只检查中间件层面——OPTIONS 不会被 AuthRedirectMiddleware 截成 401 或 302。
    """
    app = _fresh_app(monkeypatch, disable_auth="1")
    with TestClient(app, follow_redirects=False) as client:
        resp = client.options(
            "/api/chat",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
    # CORS 一般给 200 / 204；中间件如果拦，会是 401 或 302。
    assert resp.status_code not in (301, 302, 401), (
        f"DISABLE_AUTH=1 时 /api/chat OPTIONS 不应被重定向或 401，实际：{resp.status_code}"
    )
