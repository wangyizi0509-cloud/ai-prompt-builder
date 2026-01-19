import os
import importlib
from fastapi import APIRouter


def _load_router(module_name: str, env_flag: str | None = None):
    if env_flag and os.getenv(env_flag, "0") == "1":
        print(f"Skipping {module_name} router via {env_flag}=1", flush=True)
        return None
    print(f"Loading {module_name} router...", flush=True)
    module = importlib.import_module(f"{__name__}.{module_name}")
    print(f"Loaded {module_name} router", flush=True)
    return module.router


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
