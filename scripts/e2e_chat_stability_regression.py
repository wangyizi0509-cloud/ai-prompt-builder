#!/usr/bin/env python3
"""
Regression checks for chat stability fixes:
1) Refresh must show history loading state instead of empty welcome.
2) Image upload flow must trigger follow-up /api/chat call.
3) 200-empty packet must render explicit error state with retry entry.

Runs fully with mocked APIs against static frontend page.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import socketserver
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError as exc:
    raise SystemExit(
        "Playwright is not installed. Run:\n"
        "  pip install playwright\n"
        "  python -m playwright install chromium"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = ROOT / "output" / "playwright"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class StaticServer:
    def __init__(self, root: Path):
        self.root = root
        self.port: int | None = None
        self._httpd: ReusableTCPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        handler = partial(SimpleHTTPRequestHandler, directory=str(self.root))
        self._httpd = ReusableTCPServer(("127.0.0.1", 0), handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None


def log(message: str) -> None:
    print(f"[chat-stability] {message}")


async def wait_until(predicate, timeout_sec: float = 8.0, interval_sec: float = 0.1, timeout_msg: str = "condition timeout") -> None:
    start = time.time()
    while True:
        if await predicate():
            return
        if time.time() - start > timeout_sec:
            raise AssertionError(timeout_msg)
        await asyncio.sleep(interval_sec)


async def save_screenshot(page, name: str) -> str:
    path = ARTIFACTS_DIR / f"chat_stability_{name}_{int(time.time())}.png"
    await page.screenshot(path=str(path), full_page=True)
    return str(path)


def ensure_dummy_png() -> Path:
    path = ARTIFACTS_DIR / "chat_stability_dummy_upload.png"
    if path.exists():
        return path
    png_base64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axl7n8AAAAASUVORK5CYII="
    )
    path.write_bytes(base64.b64decode(png_base64))
    return path


async def run_refresh_restore_scenario(browser, base_url: str) -> dict[str, Any]:
    context = await browser.new_context(viewport={"width": 540, "height": 960})
    page = await context.new_page()
    result: dict[str, Any] = {
        "name": "refresh_restore",
        "ok": False,
        "history_calls": 0,
    }

    await page.add_init_script(
        """
        localStorage.setItem('token', 'mock-token');
        localStorage.setItem('user', JSON.stringify({ user_id: 'u_test40', username: 'test40' }));
        """
    )

    counters = {"history": 0}

    async def handler(route, request):
        path = urlparse(request.url).path
        if path == "/api/auth/me":
            await route.fulfill(status=200, content_type="application/json", body=json.dumps({"user": {"user_id": "u_test40", "username": "test40"}}, ensure_ascii=False))
            return
        if path == "/api/auth/me/thread":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": True, "thread_id": "fe057e53-fe69-16ed-2614-668b8afadc74"}, ensure_ascii=False),
            )
            return
        if path.startswith("/api/chat/history/"):
            counters["history"] += 1
            await asyncio.sleep(1.6)
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "success": True,
                        "messages": [
                            {"role": "user", "content": "历史消息-用户"},
                            {"role": "assistant", "content": "历史消息-助手"},
                        ],
                        "state": {"status_report": "历史状态已恢复"},
                    },
                    ensure_ascii=False,
                ),
            )
            return
        await route.continue_()

    await page.route("**/api/**", handler)

    try:
        await page.goto(f"{base_url}/agent_impl/frontend/index.html", wait_until="commit", timeout=60000)
        await page.wait_for_selector("text=历史消息-助手", timeout=12000)

        await page.reload(wait_until="commit", timeout=60000)
        await page.wait_for_selector("text=正在恢复你的会话...", timeout=5000)
        welcome_visible_during_loading = await page.locator("text=你好，我是小话").first.is_visible()
        if welcome_visible_during_loading:
            raise AssertionError("history loading stage showed empty welcome text")

        await page.wait_for_selector("text=历史消息-助手", timeout=12000)
        screenshot = await save_screenshot(page, "refresh_restore")

        result.update(
            {
                "ok": True,
                "history_calls": counters["history"],
                "welcome_visible_during_loading": welcome_visible_during_loading,
                "screenshot": screenshot,
            }
        )
        return result
    finally:
        await context.close()


async def run_image_upload_chain_scenario(browser, base_url: str) -> dict[str, Any]:
    context = await browser.new_context(viewport={"width": 540, "height": 960})
    page = await context.new_page()
    result: dict[str, Any] = {
        "name": "image_upload_chain",
        "ok": False,
        "upload_calls": 0,
        "chat_calls": 0,
    }
    counters = {"upload": 0, "chat": 0}

    async def handler(route, request):
        path = urlparse(request.url).path
        if path == "/api/upload/detect-type":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": True, "screenshot_type": "private_chat_screenshot"}, ensure_ascii=False),
            )
            return
        if path == "/api/upload/upload-screenshot":
            counters["upload"] += 1
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": True, "text": "OCR内容", "image_url": "https://example.com/img.png"}, ensure_ascii=False),
            )
            return
        if path == "/api/chat":
            counters["chat"] += 1
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "response": "",
                        "pending_responses": [{"from": "assistant", "content": "图片链路已触发聊天"}],
                        "state": {},
                        "error_code": None,
                        "error_message": None,
                        "retryable": False,
                    },
                    ensure_ascii=False,
                ),
            )
            return
        await route.continue_()

    await page.route("**/api/**", handler)

    try:
        await page.goto(f"{base_url}/agent_impl/frontend/index.html", wait_until="commit", timeout=60000)
        await page.wait_for_selector("input.chatbar-input", timeout=8000)

        dummy = ensure_dummy_png()
        await page.set_input_files('input[type="file"][multiple]', str(dummy))
        await page.fill("input.chatbar-input", "UI图片链路测试：请结合截图给建议。")
        await page.click("button.chatbar-send-btn")

        async def _chat_called():
            return counters["chat"] > 0

        await wait_until(_chat_called, timeout_sec=10, timeout_msg="no /api/chat call after image upload")
        if counters["upload"] <= 0:
            raise AssertionError("no /api/upload/upload-screenshot call observed")

        await page.wait_for_selector("text=图片链路已触发聊天", timeout=10000)
        screenshot = await save_screenshot(page, "image_chain")

        result.update(
            {
                "ok": True,
                "upload_calls": counters["upload"],
                "chat_calls": counters["chat"],
                "screenshot": screenshot,
            }
        )
        return result
    finally:
        await context.close()


async def run_empty_packet_retry_scenario(browser, base_url: str) -> dict[str, Any]:
    context = await browser.new_context(viewport={"width": 540, "height": 960})
    page = await context.new_page()
    result: dict[str, Any] = {
        "name": "empty_packet_retry",
        "ok": False,
        "chat_calls": 0,
    }

    counters = {"chat": 0}

    async def handler(route, request):
        path = urlparse(request.url).path
        if path == "/api/chat":
            counters["chat"] += 1
            if counters["chat"] == 1:
                payload = {
                    "response": "",
                    "pending_responses": [],
                    "state": {},
                    "error_code": "EMPTY_OUTPUT",
                    "error_message": "系统暂时没有返回可展示结果，请点击重试。",
                    "retryable": True,
                }
            else:
                payload = {
                    "response": "",
                    "pending_responses": [{"from": "assistant", "content": "重试成功回复"}],
                    "state": {},
                    "error_code": None,
                    "error_message": None,
                    "retryable": False,
                }
            await route.fulfill(status=200, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))
            return
        await route.continue_()

    await page.route("**/api/**", handler)

    try:
        await page.goto(f"{base_url}/agent_impl/frontend/index.html", wait_until="commit", timeout=60000)
        await page.wait_for_selector("input.chatbar-input", timeout=8000)
        await page.fill("input.chatbar-input", "空包场景测试")
        await page.click("button.chatbar-send-btn")

        await page.wait_for_selector("text=错误码：EMPTY_OUTPUT", timeout=12000)
        retry_btn = page.locator("button", has_text="重试").first
        await retry_btn.wait_for(state="visible", timeout=5000)
        await retry_btn.click()

        async def _second_call_done():
            return counters["chat"] >= 2

        await wait_until(_second_call_done, timeout_sec=8, timeout_msg="retry did not trigger second /api/chat call")
        await page.wait_for_selector("text=重试成功回复", timeout=8000)

        screenshot = await save_screenshot(page, "empty_packet_retry")
        result.update(
            {
                "ok": True,
                "chat_calls": counters["chat"],
                "screenshot": screenshot,
            }
        )
        return result
    finally:
        await context.close()


async def run_all(base_url: str, headed: bool = False) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "ok": False,
        "base_url": base_url,
        "timestamp": int(time.time()),
        "scenarios": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        try:
            scenarios = [
                await run_refresh_restore_scenario(browser, base_url),
                await run_image_upload_chain_scenario(browser, base_url),
                await run_empty_packet_retry_scenario(browser, base_url),
            ]
            summary["scenarios"] = scenarios
            summary["ok"] = all(bool(s.get("ok")) for s in scenarios)
            return summary
        finally:
            await browser.close()


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Run chat stability UI regressions with Playwright")
    parser.add_argument("--headed", action="store_true", help="run browser with UI")
    args = parser.parse_args()

    server = StaticServer(root=ROOT)
    port = server.start()
    base_url = f"http://127.0.0.1:{port}"
    log(f"static server started: {base_url}")

    result_path = ARTIFACTS_DIR / f"chat_stability_regression_{int(time.time())}.json"
    try:
        result = await run_all(base_url=base_url, headed=args.headed)
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"result written: {result_path}")
        if not result.get("ok"):
            return 1
        return 0
    except (AssertionError, PlaywrightTimeoutError) as exc:
        fail_payload = {"ok": False, "error": str(exc)}
        result_path.write_text(json.dumps(fail_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"FAILED: {exc}")
        log(f"result written: {result_path}")
        return 1
    finally:
        server.stop()
        log("static server stopped")


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
