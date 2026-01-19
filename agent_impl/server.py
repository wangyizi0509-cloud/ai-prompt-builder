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

print("Importing API routers...", flush=True)
from api import api_router
print("API routers loaded", flush=True)
app.include_router(api_router)


frontend_path = os.path.join(current_dir, "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
else:
    logger.warning(f"Frontend path not found: {frontend_path}")

if __name__ == "__main__":
    logger.info("Starting server on http://0.0.0.0:8000")
    debug_mode = os.getenv("DEBUG_MODE", "0") == "1"
    if debug_mode:
        logger.info("DEBUG_MODE=1: Running with auto-reload enabled")
        uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
    else:
        uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
