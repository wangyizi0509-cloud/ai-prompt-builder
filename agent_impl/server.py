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


def get_client():
    return get_sync_client(url=LANGGRAPH_URL, api_key=LANGGRAPH_API_KEY)


def session_to_thread_id(session_id: str) -> str:
    try:
        uuid.UUID(session_id)
        return session_id
    except ValueError:
        hash_obj = hashlib.md5(session_id.encode())
        hex_digest = hash_obj.hexdigest()
        return str(uuid.UUID(hex=hex_digest[:32]))


async def ensure_thread_exists(session_id: str, user_id: str = None) -> str:
    client = get_client()
    thread_id = session_to_thread_id(session_id)
    
    try:
        client.threads.get(thread_id)
    except Exception:
        client.threads.create(thread_id=thread_id)
    
    if user_id:
        from supabase_service.client import get_or_create_user_thread
        await get_or_create_user_thread(user_id, thread_id)
    
    return thread_id


print("Importing API routers...", flush=True)
from api import api_router
print("API routers loaded", flush=True)
app.include_router(api_router)


frontend_path = os.path.join(current_dir, "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
else:
    print(f"Warning: Frontend path not found: {frontend_path}")

if __name__ == "__main__":
    print("Starting server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
