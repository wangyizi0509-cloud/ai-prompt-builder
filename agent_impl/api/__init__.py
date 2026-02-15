import os
import importlib
import logging
from fastapi import APIRouter


logger = logging.getLogger(__name__)


def _load_router(module_name: str, env_flag: str | None = None):
    if env_flag and os.getenv(env_flag, "0") == "1":
        logger.info("Skipping %s router via %s=1", module_name, env_flag)
        return None
    logger.info("Loading %s router...", module_name)
    try:
        module = importlib.import_module(f"{__name__}.{module_name}")
        logger.info("Loaded %s router", module_name)
        return module.router
    except Exception:
        strict = os.getenv("STRICT_ROUTER_LOAD", "0") == "1"
        logger.exception("Failed to load %s router (strict=%s)", module_name, strict)
        if strict:
            raise
        # Fail-open in production to keep service bootable for health checks.
        return None


auth_router = _load_router("auth", "DISABLE_AUTH")
upload_router = _load_router("upload", "DISABLE_UPLOAD")
chat_router = _load_router("chat", "DISABLE_CHAT")
stream_router = _load_router("stream", "DISABLE_STREAM")
guide_router = _load_router("guide", "DISABLE_GUIDE")
debug_router = _load_router("debug", "DISABLE_DEBUG")

api_router = APIRouter()

if auth_router is not None:
    api_router.include_router(auth_router, prefix="/api/auth", tags=["认证"])
if upload_router is not None:
    api_router.include_router(upload_router, prefix="/api/upload", tags=["上传"])
if chat_router is not None:
    api_router.include_router(chat_router, tags=["聊天"])
if stream_router is not None:
    api_router.include_router(stream_router, tags=["流式聊天"])
if guide_router is not None:
    api_router.include_router(guide_router, prefix="/api/guide", tags=["指南"])
if debug_router is not None:
    api_router.include_router(debug_router, prefix="/api/debug", tags=["调试"])
