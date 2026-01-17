from fastapi import APIRouter

from .auth import router as auth_router
from .upload import router as upload_router
from .chat import router as chat_router
from .stream import router as stream_router
from .guide import router as guide_router
from .debug import router as debug_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/api/auth", tags=["认证"])
api_router.include_router(upload_router, tags=["上传"])
api_router.include_router(chat_router, tags=["聊天"])
api_router.include_router(stream_router, tags=["流式聊天"])
api_router.include_router(guide_router, tags=["指南"])
api_router.include_router(debug_router, prefix="/api/debug", tags=["调试"])
