"""
真实 API 测试：图片类型识别与 OCR

覆盖：
1) ImageProcessor.detect_type (真实豆包 Vision)
2) ImageProcessor.process_image (真实豆包 Vision)
3) POST /api/upload/detect-type (真实接口)
4) POST /api/upload/upload-screenshot (接口层；mock thread/supabase，保留真实 OCR)
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient


# Ensure imports work when running from repo root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app
from utils.image_processor import get_image_processor


HAS_DOUBAO_CONFIG = bool(os.getenv("DOUBAO_API_KEY") and os.getenv("DOUBAO_ENDPOINT_ID"))
SKIP_REASON = "需要 DOUBAO_API_KEY 和 DOUBAO_ENDPOINT_ID 环境变量"

ALLOWED_TYPES = {
    "private_chat_screenshot",
    "group_chat_screenshot",
    "moments_screenshot",
    "other_social_media_screenshot",
    "universal_screenshot_analysis",
}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}

# 1x1 PNG (fallback sample image)
FALLBACK_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO5+JxkAAAAASUVORK5CYII="
)


@pytest.fixture(scope="session")
def sample_image_bytes() -> bytes:
    """优先使用仓库内已有截图；找不到则使用内置 PNG。"""
    candidates = [
        Path("artifacts/e2e/no_guide_card_1769847818.png"),
        Path("artifacts/e2e/no_guide_card_1769847993.png"),
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path.read_bytes()

    return base64.b64decode(FALLBACK_PNG_B64)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def ensure_real_api_ready():
    """
    真实 API 前置检查：
    1) 必要环境变量
    2) 豆包域名可解析（CI/沙箱无外网时自动 skip）
    """
    if not HAS_DOUBAO_CONFIG:
        pytest.skip(SKIP_REASON)

    base_url = os.getenv("DOUBAO_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3"
    host = urlparse(base_url).hostname
    if not host:
        pytest.skip(f"DOUBAO_BASE_URL 无法解析 host: {base_url}")

    try:
        socket.gethostbyname(host)
    except OSError as e:
        pytest.skip(f"豆包域名不可达: {host} ({e})")


@pytest.mark.api_test
@pytest.mark.skipif(not HAS_DOUBAO_CONFIG, reason=SKIP_REASON)
def test_image_processor_detect_type_real_api(sample_image_bytes: bytes, ensure_real_api_ready):
    _ = ensure_real_api_ready
    processor = get_image_processor()
    result = asyncio.run(processor.detect_type(sample_image_bytes))

    assert isinstance(result, dict)
    assert "success" in result
    assert "screenshot_type" in result
    assert "confidence" in result

    assert result["success"] is True, f"detect_type failed: {result.get('error')}"
    assert result["screenshot_type"] in ALLOWED_TYPES
    assert result["confidence"] in ALLOWED_CONFIDENCE


@pytest.mark.api_test
@pytest.mark.skipif(not HAS_DOUBAO_CONFIG, reason=SKIP_REASON)
def test_image_processor_ocr_real_api(sample_image_bytes: bytes, ensure_real_api_ready):
    _ = ensure_real_api_ready
    processor = get_image_processor()
    result = asyncio.run(
        processor.process_image(
            image_bytes=sample_image_bytes,
            screenshot_type="universal_screenshot_analysis",
            additional_context=None,
        )
    )

    assert isinstance(result, dict)
    assert result["success"] is True, f"process_image failed: {result.get('error')}"
    assert result.get("screenshot_type") == "universal_screenshot_analysis"
    assert isinstance(result.get("text"), str)
    assert result.get("text", "").strip() != ""


@pytest.mark.api_test
@pytest.mark.skipif(not HAS_DOUBAO_CONFIG, reason=SKIP_REASON)
def test_detect_type_endpoint_real_api(client: TestClient, sample_image_bytes: bytes, ensure_real_api_ready):
    _ = ensure_real_api_ready
    files = {
        "file": ("sample.png", io.BytesIO(sample_image_bytes), "image/png"),
    }
    response = client.post("/api/upload/detect-type", files=files)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("success") is True, data
    assert data.get("screenshot_type") in ALLOWED_TYPES
    assert data.get("confidence") in ALLOWED_CONFIDENCE


@pytest.mark.api_test
@pytest.mark.skipif(not HAS_DOUBAO_CONFIG, reason=SKIP_REASON)
def test_upload_screenshot_endpoint_real_ocr_with_stubbed_storage(
    client: TestClient,
    sample_image_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
    ensure_real_api_ready,
):
    _ = ensure_real_api_ready
    # 避免依赖 LangGraph thread & Supabase，只验证接口层 + 真实 OCR
    from api import sdk_client
    from supabase_service import client as supabase_client

    async def _fake_ensure_thread_exists(session_id: str, user_id: str | None = None) -> str:
        _ = user_id
        return f"stub-thread-{session_id}"

    async def _fake_upload_user_image(*args, **kwargs):
        _ = args, kwargs
        return {"success": False, "error": "stubbed in test"}

    monkeypatch.setattr(sdk_client, "ensure_thread_exists", _fake_ensure_thread_exists)
    monkeypatch.setattr(supabase_client, "upload_user_image", _fake_upload_user_image)

    files = {
        "file": ("sample.png", io.BytesIO(sample_image_bytes), "image/png"),
    }
    data = {
        "screenshot_type": "universal_screenshot_analysis",
        "session_id": "real_api_image_test_session",
    }

    response = client.post("/api/upload/upload-screenshot", data=data, files=files)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("success") is True, payload
    assert payload.get("screenshot_type") == "universal_screenshot_analysis"
    assert isinstance(payload.get("text"), str)
    assert payload.get("text", "").strip() != ""
