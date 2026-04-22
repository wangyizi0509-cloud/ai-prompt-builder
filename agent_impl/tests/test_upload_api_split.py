"""测试 `api/upload.py` 拆分后的 /upload-only 和 /ocr-only 两个端点。

策略：全部用 monkeypatch 替换 `_do_upload` 和 `_do_ocr` helper，不依赖真实
Supabase / OCR provider。
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# 让 sys.path 对齐 agent_impl/
AGENT_IMPL_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_IMPL_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_IMPL_DIR))
os.environ.setdefault("LLM_PROVIDER", "mock")

from api import upload as upload_module  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    """构造一个只挂 upload router 的最小 FastAPI app。"""
    # 确保不被鉴权中间件拦截：auth_utils.get_optional_user 默认就返回 None（匿名）
    app = FastAPI()
    app.include_router(upload_module.router, prefix="/api/upload")
    return TestClient(app)


def _fake_file_bytes() -> bytes:
    # 3 字节随便塞点东西当图片 payload（后端不会真解码，只 io.read 一下）
    return b"\x89\xff\xfe"


# --------------------------------------------------------------------------- #
# /upload-only
# --------------------------------------------------------------------------- #


def test_upload_only_eval_mode_ok(client, monkeypatch):
    """eval_mode=true 走 _do_upload 的快路径，返回 success=True + empty url。"""

    async def fake_do_upload(**kwargs):
        assert kwargs["eval_mode"] is True
        assert kwargs["session_id"] == "sess-abc"
        return {"success": True, "url": "", "path": "", "error": None, "eval_mode": True}

    monkeypatch.setattr(upload_module, "_do_upload", fake_do_upload)

    resp = client.post(
        "/api/upload/upload-only",
        data={"session_id": "sess-abc", "eval_mode": "true"},
        files={"file": ("shot.jpg", io.BytesIO(_fake_file_bytes()), "image/jpeg")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["url"] == ""


def test_upload_only_failure_returns_error_json(client, monkeypatch):
    """_do_upload 抛异常 → 返回 success=False + error 字符串（不 5xx）。"""

    async def fake_do_upload(**kwargs):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(upload_module, "_do_upload", fake_do_upload)

    resp = client.post(
        "/api/upload/upload-only",
        data={"session_id": "sess-xyz", "eval_mode": "false"},
        files={"file": ("shot.jpg", io.BytesIO(_fake_file_bytes()), "image/jpeg")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "supabase down" in (body.get("error") or "") or body.get("error")


# --------------------------------------------------------------------------- #
# /ocr-only
# --------------------------------------------------------------------------- #


def test_ocr_only_success(client, monkeypatch):
    """_do_ocr 返回成功 → 端点直接透传。"""

    async def fake_do_ocr(**kwargs):
        assert kwargs["screenshot_type"] == "screenshot"
        return {
            "success": True,
            "text": "[他] 嗯嗯\n[他] 在忙",
            "screenshot_type": "private_chat_screenshot",
            "error": None,
        }

    monkeypatch.setattr(upload_module, "_do_ocr", fake_do_ocr)

    resp = client.post(
        "/api/upload/ocr-only",
        data={"session_id": "sess-ocr-1", "screenshot_type": "screenshot"},
        files={"file": ("shot.jpg", io.BytesIO(_fake_file_bytes()), "image/jpeg")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "嗯嗯" in body["text"]


def test_ocr_only_failure_graceful(client, monkeypatch):
    """_do_ocr 抛异常 → 端点返回 success=False + error，仍 200（上层前端 graceful）。"""

    async def fake_do_ocr(**kwargs):
        raise RuntimeError("dashscope TLS error")

    monkeypatch.setattr(upload_module, "_do_ocr", fake_do_ocr)

    resp = client.post(
        "/api/upload/ocr-only",
        data={"session_id": "sess-ocr-2", "screenshot_type": "screenshot"},
        files={"file": ("shot.jpg", io.BytesIO(_fake_file_bytes()), "image/jpeg")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "dashscope TLS error" in (body.get("error") or "")
