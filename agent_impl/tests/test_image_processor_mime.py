from __future__ import annotations

import asyncio
import base64

from utils.image_processor import ImageProcessor


_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO5+JxkAAAAASUVORK5CYII="
)

_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxAQEBAQEA8QDw8QEA8PEA8QEA8PFREWFhUR"
    "FRUYHSggGBolGxUVITEhJSkrLi4uFx8zODMtNygtLisBCgoKDg0OGxAQGy0lICYtLS0tLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAgMBIgAC"
    "EQEDEQH/xAAXAAEBAQEAAAAAAAAAAAAAAAAAAQID/8QAFhEBAQEAAAAAAAAAAAAAAAAAAAER"
    "/9oADAMBAAIQAxAAAAH6gA//xAAZEAEAAgMAAAAAAAAAAAAAAAAAAQIREiH/2gAIAQEAAQUC"
    "qWQ6b//EABYRAQEBAAAAAAAAAAAAAAAAAAABEf/aAAgBAwEBPwFJ/8QAFhEBAQEAAAAAAAAA"
    "AAAAAAAAAAER/9oACAECAQE/AUn/xAAaEAACAgMAAAAAAAAAAAAAAAABEQAhMUFR/9oACAEB"
    "AAE/IZvY5M8KJ0d//9k="
)


def _build_processor() -> ImageProcessor:
    processor = ImageProcessor()
    processor.api_key = "test_api_key"
    processor.model = "test_model"
    return processor


def test_guess_mime_type_png_and_jpeg():
    processor = _build_processor()
    png_bytes = base64.b64decode(_PNG_B64)
    jpeg_bytes = base64.b64decode(_JPEG_B64)

    assert processor._guess_mime_type(png_bytes) == "image/png"
    assert processor._guess_mime_type(jpeg_bytes) == "image/jpeg"


def test_detect_type_uses_detected_mime(monkeypatch):
    processor = _build_processor()
    png_bytes = base64.b64decode(_PNG_B64)
    captured: dict = {}

    async def _fake_post(payload: dict):
        captured["payload"] = payload
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"type":"private_chat_screenshot","confidence":"high","reason":"ok"}'
                    }
                }
            ]
        }

    monkeypatch.setattr(processor, "_post_chat_completion", _fake_post)
    result = asyncio.run(processor.detect_type(png_bytes))

    image_url = (
        captured["payload"]["messages"][0]["content"][1]["image_url"]["url"]
    )
    assert image_url.startswith("data:image/png;base64,")
    assert result["success"] is True
    assert result["screenshot_type"] == "private_chat_screenshot"


def test_process_image_uses_detected_mime(monkeypatch):
    processor = _build_processor()
    jpeg_bytes = base64.b64decode(_JPEG_B64)
    captured: dict = {}

    async def _fake_post(payload: dict):
        captured["payload"] = payload
        return {
            "choices": [
                {
                    "message": {
                        "content": "mock ocr content"
                    }
                }
            ]
        }

    monkeypatch.setattr(processor, "_post_chat_completion", _fake_post)
    result = asyncio.run(
        processor.process_image(
            image_bytes=jpeg_bytes,
            screenshot_type="universal_screenshot_analysis",
        )
    )

    image_url = (
        captured["payload"]["messages"][0]["content"][1]["image_url"]["url"]
    )
    assert image_url.startswith("data:image/jpeg;base64,")
    assert result["success"] is True
    assert result["text"] == "mock ocr content"
