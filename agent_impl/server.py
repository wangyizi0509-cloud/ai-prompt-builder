import os
import sys
import uvicorn
import hashlib
import uuid
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from langgraph_sdk import get_sync_client

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from utils.logger import get_logger

logger = get_logger("server")

app = FastAPI(title="Crushe AI Agent")

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
    logger.info("Starting server on http://0.0.0.0:8000")
    debug_mode = os.getenv("DEBUG_MODE", "0") == "1"
    if debug_mode:
        reload_enabled = os.getenv("UVICORN_RELOAD", "1") != "0"
        if reload_enabled:
            logger.info("DEBUG_MODE=1: Running with auto-reload enabled")
            uvicorn.run(
                "server:app",
                host="0.0.0.0",
                port=8000,
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
            uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
    else:
        uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
