"""
接口通路冒烟测试（不依赖外网）

目标：验证路由与请求链路可用，而不是验证豆包模型质量。
"""

from __future__ import annotations

import base64
import io
import os
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure imports work when running from repo root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app


# 1x1 PNG
_SAMPLE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO5+JxkAAAAASUVORK5CYII="
)


def _sample_image_bytes() -> bytes:
    return base64.b64decode(_SAMPLE_PNG_B64)


def _mock_auth_headers(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    from auth_utils import verify_jwt_token as _verify_jwt_token
    import auth_utils

    _ = _verify_jwt_token

    def _fake_verify_jwt_token(token: str):
        if token == "smoke-token":
            return {
                "valid": True,
                "user_id": "smoke-user",
                "email": "smoke@example.com",
                "username": "smoke",
            }
        return {"valid": False, "error": "Invalid token"}

    monkeypatch.setattr(auth_utils, "verify_jwt_token", _fake_verify_jwt_token)
    return {"Authorization": "Bearer smoke-token"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_detect_type_route_smoke(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """验证 /api/upload/detect-type 的接口通路。"""
    from utils import image_processor as image_processor_module

    headers = _mock_auth_headers(monkeypatch)

    async def _fake_detect_type(self, image_bytes: bytes):
        _ = self, image_bytes
        return {
            "success": True,
            "screenshot_type": "private_chat_screenshot",
            "confidence": "high",
            "reason": "smoke test",
            "error": None,
        }

    monkeypatch.setattr(image_processor_module.ImageProcessor, "detect_type", _fake_detect_type)

    files = {
        "file": ("sample.png", io.BytesIO(_sample_image_bytes()), "image/png"),
    }
    response = client.post("/api/upload/detect-type", files=files, headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert payload["screenshot_type"] == "private_chat_screenshot"
    assert payload["confidence"] == "high"


def test_upload_screenshot_route_smoke(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """验证 /api/upload/upload-screenshot 的接口通路（mock 外部依赖）。"""
    from api import sdk_client
    from supabase_service import client as supabase_client
    from utils import image_processor as image_processor_module

    headers = _mock_auth_headers(monkeypatch)

    async def _fake_ensure_thread_exists(session_id: str, user_id: str | None = None) -> str:
        _ = user_id
        return f"stub-thread-{session_id}"

    async def _fake_upload_user_image(*args, **kwargs):
        _ = args, kwargs
        return {
            "success": True,
            "url": "https://example.com/fake.png",
            "path": "anonymous/fake.png",
        }

    async def _fake_process_image(self, image_bytes: bytes, screenshot_type: str, additional_context: str | None = None):
        _ = self, image_bytes, additional_context
        return {
            "success": True,
            "text": "mock ocr text",
            "screenshot_type": screenshot_type,
            "error": None,
        }

    monkeypatch.setattr(sdk_client, "ensure_thread_exists", _fake_ensure_thread_exists)
    monkeypatch.setattr(supabase_client, "upload_user_image", _fake_upload_user_image)
    monkeypatch.setattr(image_processor_module.ImageProcessor, "process_image", _fake_process_image)

    files = {
        "file": ("sample.png", io.BytesIO(_sample_image_bytes()), "image/png"),
    }
    data = {
        "screenshot_type": "universal_screenshot_analysis",
        "session_id": "smoke_session_001",
    }

    response = client.post("/api/upload/upload-screenshot", data=data, files=files, headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert payload["screenshot_type"] == "universal_screenshot_analysis"
    assert payload["text"] == "mock ocr text"
    assert payload["image_url"] == "https://example.com/fake.png"
    assert payload["storage_path"] == "anonymous/fake.png"


def test_upload_screenshot_eval_mode_skips_persistence(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """评测模式只跑 OCR，不触发 thread / storage 侧效应。"""
    from api import sdk_client
    from supabase_service import client as supabase_client
    from utils import image_processor as image_processor_module

    headers = _mock_auth_headers(monkeypatch)

    async def _unexpected_ensure_thread_exists(*args, **kwargs):
        raise AssertionError("ensure_thread_exists should be skipped in eval mode")

    async def _unexpected_upload_user_image(*args, **kwargs):
        raise AssertionError("upload_user_image should be skipped in eval mode")

    async def _fake_process_image(self, image_bytes: bytes, screenshot_type: str, additional_context: str | None = None):
        _ = self, image_bytes, additional_context
        return {
            "success": True,
            "text": "mock eval ocr text",
            "screenshot_type": screenshot_type,
            "error": None,
        }

    monkeypatch.setattr(sdk_client, "ensure_thread_exists", _unexpected_ensure_thread_exists)
    monkeypatch.setattr(supabase_client, "upload_user_image", _unexpected_upload_user_image)
    monkeypatch.setattr(image_processor_module.ImageProcessor, "process_image", _fake_process_image)

    files = {
        "file": ("sample.png", io.BytesIO(_sample_image_bytes()), "image/png"),
    }
    data = {
        "screenshot_type": "private_chat_screenshot",
        "session_id": "eval_session_001",
        "eval_mode": "true",
    }

    response = client.post("/api/upload/upload-screenshot", data=data, files=files, headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert payload["screenshot_type"] == "private_chat_screenshot"
    assert payload["text"] == "mock eval ocr text"
    assert payload["eval_mode"] is True
    assert "image_url" not in payload
    assert "storage_path" not in payload
