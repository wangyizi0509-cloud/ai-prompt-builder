import os
import time
import uuid
from typing import Any, Dict, Optional

import requests


DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_EMAIL = os.getenv("TEST_USER_EMAIL", "test01@example.com")
DEFAULT_PASSWORD = os.getenv("TEST_USER_PASSWORD", "password123")


def get_base_url() -> str:
    return os.getenv("TEST_BASE_URL", DEFAULT_BASE_URL)


def login(base_url: str, email: str, password: str) -> Dict[str, Any]:
    payload = {"email": email, "password": password}
    resp = requests.post(f"{base_url}/api/auth/login", json=payload, timeout=60.0)
    if resp.status_code != 200:
        raise AssertionError(f"登录失败: {resp.status_code} {resp.text}")
    data = resp.json()
    if not data.get("success") or not data.get("token"):
        raise AssertionError(f"登录返回异常: {data}")
    return data


def get_user_thread_id(base_url: str, token: str) -> Optional[str]:
    resp = requests.get(
        f"{base_url}/api/auth/me/thread",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    if not data.get("success"):
        return None
    return data.get("thread_id")


def post_chat(
    base_url: str,
    session_id: str,
    message: str,
    token: Optional[str] = None,
    feedback_mode: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "message": message,
        "session_id": session_id,
    }
    if feedback_mode is not None:
        payload["feedback_mode"] = feedback_mode
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.post(
        f"{base_url}/api/chat",
        json=payload,
        headers=headers,
        timeout=300.0,
    )
    if resp.status_code != 200:
        raise AssertionError(f"/api/chat 失败: {resp.status_code} {resp.text}")
    return resp.json()


def ensure_thread_id(base_url: str, token: str) -> str:
    existing = get_user_thread_id(base_url, token)
    if existing:
        return existing
    session_id = str(uuid.uuid4())
    post_chat(base_url, session_id, "初始化会话", token=token)
    bound = get_user_thread_id(base_url, token)
    return bound or session_id


def get_debug_context(base_url: str, session_id: str) -> Dict[str, Any]:
    resp = requests.get(f"{base_url}/api/debug/context/{session_id}", timeout=60.0)
    if resp.status_code != 200:
        raise AssertionError(f"获取 debug context 失败: {resp.status_code} {resp.text}")
    return resp.json()


def get_chat_history(base_url: str, thread_id: str, token: Optional[str] = None) -> Dict[str, Any]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(
        f"{base_url}/api/chat/history/{thread_id}",
        headers=headers,
        timeout=60.0,
    )
    if resp.status_code != 200:
        raise AssertionError(f"获取历史失败: {resp.status_code} {resp.text}")
    return resp.json()


def update_guide_status(
    base_url: str,
    session_id: str,
    guide_id: str,
    new_status: str,
    completion_status: Optional[str] = None,
    completion_detail: Optional[str] = None,
    feedback_summary: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "guide_id": guide_id,
        "new_status": new_status,
        "session_id": session_id,
    }
    if completion_status:
        payload["completion_status"] = completion_status
    if completion_detail:
        payload["completion_detail"] = completion_detail
    if feedback_summary:
        payload["feedback_summary"] = feedback_summary
    resp = requests.post(f"{base_url}/api/update_guide_status", json=payload, timeout=60.0)
    if resp.status_code != 200:
        raise AssertionError(f"更新指南状态失败: {resp.status_code} {resp.text}")
    return resp.json()


def extract_guides(state: Any) -> list[Dict[str, Any]]:
    if isinstance(state, list):
        return [g for g in state if isinstance(g, dict)]
    if not isinstance(state, dict):
        return []
    # 优先从 layer2_memory 提取（真源）
    layer2_memory = state.get("layer2_memory") or {}
    if isinstance(layer2_memory, dict):
        guides = layer2_memory.get("action_guides") or []
        if guides:
            return [g for g in guides if isinstance(g, dict)]
    # fallback 到顶层 action_guides
    guides = state.get("action_guides") or []
    return [g for g in guides if isinstance(g, dict)]


def create_action_guide(
    base_url: str,
    session_id: str,
    token: str,
    prompt: str,
    max_attempts: int = 3,
    sleep_seconds: float = 1.5,
) -> Dict[str, Any]:
    existing_ids: set[str] = set()
    try:
        debug_state = get_debug_context(base_url, session_id)
        debug_guides = extract_guides((debug_state.get("layer2_working") or {}).get("action_guides") or [])
        existing_ids = {g.get("id") for g in debug_guides if g.get("id")}
    except Exception:
        existing_ids = set()
    for attempt in range(max_attempts):
        response = post_chat(base_url, session_id, prompt, token=token)
        state = response.get("state") or {}
        guides = extract_guides(state)
        # Debug: 打印提取到的指南数量
        print(f"[DEBUG] Attempt {attempt + 1}: extracted {len(guides)} guides from state")
        if guides:
            print(f"[DEBUG] Guide IDs: {[g.get('id') for g in guides]}")
        new_guides = [g for g in guides if g.get("id") not in existing_ids]
        if new_guides:
            return new_guides[-1]
        existing_ids.update({g.get("id") for g in guides if g.get("id")})
        debug_state = get_debug_context(base_url, session_id)
        debug_guides = extract_guides((debug_state.get("layer2_working") or {}).get("action_guides") or [])
        print(f"[DEBUG] Attempt {attempt + 1}: extracted {len(debug_guides)} guides from debug_context")
        existing_ids.update({g.get("id") for g in debug_guides if g.get("id")})
        time.sleep(sleep_seconds * (attempt + 1))
    raise AssertionError("未能生成新的行动指南")


def find_guide_by_id(guides: list[Dict[str, Any]], guide_id: str) -> Optional[Dict[str, Any]]:
    for guide in guides:
        if str(guide.get("id")) == str(guide_id):
            return guide
    return None
