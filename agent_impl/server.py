import os
import sys
import uvicorn
import hashlib
import uuid
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse, JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from langgraph_sdk import get_sync_client

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from utils.logger import get_logger

logger = get_logger("server")


# ---------------------------------------------------------------------------
# Auth Redirect Middleware
# ---------------------------------------------------------------------------
class AuthRedirectMiddleware:
    """未登录用户访问受保护资源时：
    - API 请求 → 401 JSON（含 redirect 字段）
    - 页面请求 → 302 重定向到 /auth.html
    """

    WHITELIST_PATHS = frozenset({
        "/auth.html",
        "/health",
        "/api/health",
    })

    WHITELIST_PREFIXES = (
        "/api/auth/",
    )

    STATIC_EXTENSIONS = (
        ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".ico", ".woff", ".woff2", ".ttf", ".eot", ".map", ".webp",
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")

        # ---- Whitelist checks ----
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if path in self.WHITELIST_PATHS:
            await self.app(scope, receive, send)
            return

        for prefix in self.WHITELIST_PREFIXES:
            if path.startswith(prefix):
                await self.app(scope, receive, send)
                return

        for ext in self.STATIC_EXTENSIONS:
            if path.endswith(ext):
                await self.app(scope, receive, send)
                return

        # ---- Authentication checks ----
        raw_headers = scope.get("headers", [])
        auth_value = b""
        cookie_value = b""
        for name, value in raw_headers:
            if name == b"authorization":
                auth_value = value
            elif name == b"cookie":
                cookie_value = value

        from auth_utils import verify_jwt_token

        # 1) Authorization header (API / fetch calls)
        if auth_value:
            decoded = auth_value.decode(errors="ignore")
            if decoded.startswith("Bearer "):
                token = decoded[7:]
                if verify_jwt_token(token).get("valid"):
                    await self.app(scope, receive, send)
                    return

        # 2) auth_token cookie (browser page navigation)
        if cookie_value:
            token = self._extract_cookie(cookie_value.decode(errors="ignore"), "auth_token")
            if token and verify_jwt_token(token).get("valid"):
                await self.app(scope, receive, send)
                return

        # ---- Not authenticated ----
        if path.startswith("/api/"):
            response = JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated", "redirect": "/auth.html"},
            )
        else:
            response = RedirectResponse(url="/auth.html", status_code=302)

        await response(scope, receive, send)

    @staticmethod
    def _extract_cookie(cookie_header: str, name: str) -> str | None:
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(f"{name}="):
                return part[len(name) + 1:]
        return None


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(title="Crushe AI Agent")

# Auth middleware (inner) – added first so CORS wraps around it.
# 本期 onboarding v2 默认无登录：DISABLE_AUTH 缺省即视为 "1"，显式设置为 "0" 才恢复鉴权。
_auth_disabled = os.getenv("DISABLE_AUTH", "1") == "1"
if not _auth_disabled:
    from auth_utils import is_jwt_configured
    if is_jwt_configured():
        app.add_middleware(AuthRedirectMiddleware)
        logger.info("AuthRedirectMiddleware enabled — unauthenticated requests will be redirected")
    else:
        logger.warning("JWT_SECRET not configured — AuthRedirectMiddleware skipped")
else:
    logger.info("DISABLE_AUTH=1 — AuthRedirectMiddleware skipped（本期 onboarding v2 默认无登录）")

# CORS middleware (outer) – handles OPTIONS preflight before auth checks.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from utils.langgraph_config import (
    LANGGRAPH_URL,
    LANGGRAPH_API_KEY,
    ASSISTANT_ID,
    print_config,
)

print_config()


from api.sdk_client import (
    get_client,
    session_to_thread_id,
    ensure_thread_exists,
)

logger.info("Importing API routers...")
from api import api_router
logger.info("API routers loaded")
app.include_router(api_router)

# ---- Onboarding v2 routes (Agent D) ---------------------------------------
# 两个独立 REST 端点（不走 api_router 的 env_flag 机制，直接在这里挂）。
# 路由模块里已经各自声明 `prefix="/api/onboarding"`，这里不需要再加 prefix。
# Agent B/C 的文件可能尚未产出，因此做惰性导入 + 降级，避免拖垮主进程。
try:
    from api.onboarding_analyze import router as onboarding_analyze_router
    app.include_router(onboarding_analyze_router)
    logger.info("Onboarding v2 analyze router mounted")
except ImportError as exc:
    logger.warning(
        "Onboarding v2 analyze router not mounted (Agent B may not have delivered api/onboarding_analyze.py yet): %s",
        exc,
    )

try:
    from api.onboarding_report import router as onboarding_report_router
    app.include_router(onboarding_report_router)
    logger.info("Onboarding v2 report router mounted")
except ImportError as exc:
    logger.warning(
        "Onboarding v2 report router not mounted (Agent C may not have delivered api/onboarding_report.py yet): %s",
        exc,
    )

# ---- Analytics / track route ----------------------------------------------
try:
    from api.track import router as track_router
    app.include_router(track_router)
    logger.info("Analytics track router mounted at /api/track")
except ImportError as exc:
    logger.warning("Analytics track router not mounted: %s", exc)

try:
    from api.analytics import router as analytics_router
    app.include_router(analytics_router)
    logger.info("Analytics dashboard router mounted at /api/analytics")
except ImportError as exc:
    logger.warning("Analytics dashboard router not mounted: %s", exc)


def _resolve_port() -> int:
    """Resolve runtime port from env (required on PaaS like Zeabur)."""
    raw_port = os.getenv("PORT", "8000")
    try:
        return int(raw_port)
    except (TypeError, ValueError):
        logger.warning(f"Invalid PORT={raw_port!r}, fallback to 8000")
        return 8000


def _is_container_runtime() -> bool:
    # Common container marker files/envs used by PaaS platforms.
    return os.path.exists("/.dockerenv") or os.getenv("KUBERNETES_SERVICE_HOST") is not None


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/health")
async def api_health_check():
    return {"status": "healthy"}


@app.get("/", include_in_schema=False)
async def _root_redirect_to_splash():
    """Onboarding v2：根路径一律跳转到 splash.html。

    保留 /auth.html 的静态服务（供未来恢复登录时使用），
    也保留对 frontend/ 下其他页面（/index.html 等）的直接访问。
    """
    return RedirectResponse(url="/splash.html", status_code=302)


frontend_path = os.path.join(current_dir, "frontend")
if os.path.exists(frontend_path):
    # iOS Safari can be quite aggressive about caching static assets during dev.
    # In DEBUG_MODE=1, disable cache to reduce stale UI issues on real devices.
    debug_mode_for_static = os.getenv("DEBUG_MODE", "0") == "1"

    if debug_mode_for_static:
        class NoCacheStaticFiles(StaticFiles):
            async def get_response(self, path: str, scope):
                response = await super().get_response(path, scope)
                if response.status_code == 200:
                    response.headers["Cache-Control"] = "no-store"
                return response

        app.mount("/", NoCacheStaticFiles(directory=frontend_path, html=True), name="static")
    else:
        app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
else:
    logger.warning(f"Frontend path not found: {frontend_path}")

if __name__ == "__main__":
    port = _resolve_port()
    logger.info(f"Starting server on http://0.0.0.0:{port}")
    debug_mode = os.getenv("DEBUG_MODE", "0") == "1"
    if debug_mode:
        # Keep reload opt-in only; auto-reload frequently fails on container PaaS.
        reload_enabled = os.getenv("UVICORN_RELOAD", "0") == "1"
        if reload_enabled and _is_container_runtime():
            logger.warning("UVICORN_RELOAD=1 ignored in container runtime")
            reload_enabled = False
        if reload_enabled:
            logger.info("DEBUG_MODE=1: Running with auto-reload enabled")
            uvicorn.run(
                "server:app",
                host="0.0.0.0",
                port=port,
                reload=True,
                reload_excludes=[
                    "logs/*",
                    "logs/**",
                    ".cursor/*",
                    ".cursor/**",
                    "*.log",
                ],
            )
        else:
            logger.info("DEBUG_MODE=1: Running without auto-reload (UVICORN_RELOAD=0)")
            uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
    else:
        uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
