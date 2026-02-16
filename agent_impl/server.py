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
_auth_disabled = os.getenv("DISABLE_AUTH", "0") == "1"
if not _auth_disabled:
    from auth_utils import is_jwt_configured
    if is_jwt_configured():
        app.add_middleware(AuthRedirectMiddleware)
        logger.info("AuthRedirectMiddleware enabled — unauthenticated requests will be redirected")
    else:
        logger.warning("JWT_SECRET not configured — AuthRedirectMiddleware skipped")
else:
    logger.info("DISABLE_AUTH=1 — AuthRedirectMiddleware skipped")

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
