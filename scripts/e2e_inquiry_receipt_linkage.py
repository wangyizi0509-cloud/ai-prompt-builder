#!/usr/bin/env python3
"""
E2E UI automation for inquiry receipt linkage flow.

Scenarios:
1) Single-card success.
2) Failure then retry success.
3) Failure then edit-and-resubmit success.
4) Multi-card isolation (task card focuses matching receipt by taskKey).

This script serves the repo as static files and mocks /api/chat responses,
so it does not depend on backend runtime.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import socketserver
import threading
import time
from dataclasses import dataclass, field
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
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


def log(msg: str) -> None:
    print(f"[E2E] {msg}")


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


@dataclass
class StaticServer:
    root: Path
    port: int | None = None
    _httpd: ReusableTCPServer | None = None
    _thread: threading.Thread | None = None

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


@dataclass
class MockResponseSpec:
    status: int
    payload: dict[str, Any]
    delay_ms: int = 0


@dataclass
class ChatMockQueue:
    queue: list[MockResponseSpec] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def enqueue_success(self, payload: dict[str, Any], delay_ms: int = 0) -> None:
        self.queue.append(MockResponseSpec(status=200, payload=payload, delay_ms=delay_ms))

    def enqueue_error(self, status: int = 500, payload: dict[str, Any] | None = None, delay_ms: int = 0) -> None:
        body = payload or {"error": "mock error"}
        self.queue.append(MockResponseSpec(status=status, payload=body, delay_ms=delay_ms))

    def pop(self) -> MockResponseSpec:
        if self.queue:
            return self.queue.pop(0)
        return MockResponseSpec(status=200, payload={"pending_responses": [], "state": {}}, delay_ms=0)


def build_text_inquiry_card(prefix: str, intro: str) -> dict[str, Any]:
    return {
        "intro": intro,
        "questions": [
            {
                "id": f"{prefix}_q1",
                "type": "text",
                "question": f"{prefix}补充信息一",
                "is_required": True,
            },
            {
                "id": f"{prefix}_q2",
                "type": "text",
                "question": f"{prefix}补充信息二",
                "is_required": True,
            },
        ],
    }


async def wait_until(predicate, timeout_sec: float = 8.0, interval_sec: float = 0.1, timeout_msg: str = "condition timeout") -> None:
    start = time.time()
    while True:
        if await predicate():
            return
        if time.time() - start > timeout_sec:
            raise AssertionError(timeout_msg)
        await asyncio.sleep(interval_sec)


async def save_screenshot(page, name: str) -> Path:
    path = ARTIFACTS_DIR / f"e2e_inquiry_receipt_{name}_{int(time.time())}.png"
    await page.screenshot(path=str(path), full_page=True)
    log(f"screenshot: {path}")
    return path


async def setup_chat_mock(page, mock: ChatMockQueue) -> None:
    async def route_handler(route, request):
        if request.method.upper() != "POST":
            await route.continue_()
            return
        post_data = request.post_data or ""
        try:
            parsed = json.loads(post_data) if post_data else {}
        except Exception:
            parsed = {"_raw": post_data}
        mock.calls.append(parsed)

        spec = mock.pop()
        if spec.delay_ms > 0:
            await asyncio.sleep(spec.delay_ms / 1000.0)
        await route.fulfill(
            status=spec.status,
            content_type="application/json",
            body=json.dumps(spec.payload, ensure_ascii=False),
        )

    await page.route("**/api/chat", route_handler)


async def get_task_keys(page) -> list[str]:
    return await page.eval_on_selector_all(
        ".task-card.type-inquiry[data-task-key]",
        "els => els.map(el => el.getAttribute('data-task-key') || '').filter(Boolean)",
    )


async def wait_new_task_key(page, known_keys: set[str], timeout_sec: float = 8.0) -> str:
    key_holder = {"value": ""}

    async def _check():
        keys = await get_task_keys(page)
        for k in keys:
            if k not in known_keys:
                key_holder["value"] = k
                return True
        return False

    await wait_until(_check, timeout_sec=timeout_sec, timeout_msg="new inquiry task key not found")
    return key_holder["value"]


async def open_task_card(page, task_key: str) -> None:
    locator = page.locator(f'.task-card.type-inquiry[data-task-key="{task_key}"]')
    await locator.first.click()


async def wait_modal_open(page, timeout_ms: int = 8000):
    await page.locator(".bottom-modal.open").first.wait_for(state="visible", timeout=timeout_ms)


async def fill_onboarding_modal(page, marker: str) -> None:
    modal = page.locator(".bottom-modal.open").first
    textareas = modal.locator("textarea")
    count = await textareas.count()
    if count < 3:
        raise AssertionError(f"onboarding modal textareas unexpected: {count}")
    await textareas.nth(0).fill(f"{marker}_user")
    await textareas.nth(1).fill(f"{marker}_crush")
    await textareas.nth(2).fill(f"{marker}_intent")

    age_option = modal.locator('label:has-text("23-26岁 (职场新人)")')
    age_count = await age_option.count()
    if age_count < 2:
        raise AssertionError(f"onboarding age options missing: {age_count}")
    await age_option.nth(0).click()
    await age_option.nth(1).click()


async def fill_text_only_modal(page, marker: str) -> None:
    modal = page.locator(".bottom-modal.open").first
    textareas = modal.locator("textarea")
    count = await textareas.count()
    if count <= 0:
        raise AssertionError("text modal has no textarea")
    for i in range(count):
        await textareas.nth(i).fill(f"{marker}_text_{i + 1}")


async def submit_modal(page) -> None:
    await page.get_by_role("button", name="提交回答").click()


async def wait_receipt_status(page, task_key: str, status_class: str, timeout_ms: int = 10000) -> None:
    await page.locator(
        f'.inquiry-receipt-row[data-task-key="{task_key}"] .inquiry-receipt-card.{status_class}'
    ).first.wait_for(state="visible", timeout=timeout_ms)


async def click_retry_on_receipt(page, task_key: str) -> None:
    await page.locator(
        f'.inquiry-receipt-row[data-task-key="{task_key}"] .inquiry-receipt-btn.primary'
    ).first.click()


async def click_edit_on_receipt(page, task_key: str) -> None:
    await page.locator(
        f'.inquiry-receipt-row[data-task-key="{task_key}"] .inquiry-receipt-btn:not(.primary)'
    ).first.click()


async def assert_receipt_highlighted_for_task(page, task_key: str, timeout_sec: float = 3.0) -> None:
    async def _check():
        count = await page.locator(
            f'.inquiry-receipt-row[data-task-key="{task_key}"] .inquiry-receipt-card.highlight'
        ).count()
        return count > 0

    await wait_until(_check, timeout_sec=timeout_sec, timeout_msg=f"receipt highlight not found for task_key={task_key}")


async def run_flow(base_url: str, headed: bool = False) -> dict[str, Any]:
    ts = int(time.time())
    result: dict[str, Any] = {
        "ok": False,
        "timestamp": ts,
        "base_url": base_url,
        "scenarios": {},
    }

    mock = ChatMockQueue()
    card2 = build_text_inquiry_card("R2", "第二轮补充信息")
    card3 = build_text_inquiry_card("R3", "第三轮补充信息")
    mock.enqueue_success(
        {
            "pending_responses": [{"content": "[mock] round1 ok"}],
            "state": {"inquiry_card": card2},
        },
        delay_ms=450,
    )
    mock.enqueue_error(status=500, payload={"error": "mock round2 failed"}, delay_ms=100)
    mock.enqueue_success(
        {
            "pending_responses": [{"content": "[mock] retry round2 ok"}],
            "state": {"inquiry_card": card3},
        },
        delay_ms=250,
    )
    mock.enqueue_error(status=500, payload={"error": "mock round3 failed"}, delay_ms=100)
    mock.enqueue_success(
        {"pending_responses": [{"content": "[mock] round3 edited ok"}], "state": {}},
        delay_ms=200,
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()
        await setup_chat_mock(page, mock)
        await page.goto(
            f"{base_url}/agent_impl/frontend/index.html",
            wait_until="commit",
            timeout=60000,
        )
        await page.wait_for_timeout(600)

        # Step 0: open onboarding starter and wait inquiry task card.
        start_btn = page.locator('button:has-text("开启情感攻略")').first
        await start_btn.wait_for(state="visible", timeout=12000)
        await start_btn.click()

        async def _has_first_card():
            return (await page.locator(".task-card.type-inquiry").count()) > 0

        await wait_until(
            _has_first_card,
            timeout_sec=10,
            timeout_msg="first inquiry task card not shown",
        )
        keys = await get_task_keys(page)
        if not keys:
            raise AssertionError("no inquiry task keys found")
        key1 = keys[0]
        known_keys = {key1}
        result["task_key_1"] = key1

        # Scenario 1: single-card success.
        await open_task_card(page, key1)
        await wait_modal_open(page)
        await fill_onboarding_modal(page, "case1")
        await save_screenshot(page, "case1_before_submit")
        await submit_modal(page)
        await wait_receipt_status(page, key1, "is-submitting")
        await wait_receipt_status(page, key1, "is-done")
        await open_task_card(page, key1)
        await assert_receipt_highlighted_for_task(page, key1)
        result["scenarios"]["single_card_success"] = "pass"

        # Scenario 2: failed submit then retry success.
        key2 = await wait_new_task_key(page, known_keys, timeout_sec=10)
        known_keys.add(key2)
        result["task_key_2"] = key2
        await open_task_card(page, key2)
        await wait_modal_open(page)
        await fill_text_only_modal(page, "case2")
        await submit_modal(page)
        await wait_receipt_status(page, key2, "is-error")
        await click_retry_on_receipt(page, key2)
        await wait_receipt_status(page, key2, "is-done")
        result["scenarios"]["failure_then_retry"] = "pass"

        # Scenario 3: failed submit then edit-and-resubmit.
        key3 = await wait_new_task_key(page, known_keys, timeout_sec=10)
        known_keys.add(key3)
        result["task_key_3"] = key3
        await open_task_card(page, key3)
        await wait_modal_open(page)
        await fill_text_only_modal(page, "case3")
        await submit_modal(page)
        await wait_receipt_status(page, key3, "is-error")
        await click_edit_on_receipt(page, key3)
        await wait_modal_open(page)

        first_textarea = page.locator(".bottom-modal.open textarea").first
        prefilled = (await first_textarea.input_value()).strip()
        if "case3_text_1" not in prefilled:
            raise AssertionError(f"edit mode not prefilled as expected, got={prefilled!r}")
        await first_textarea.fill(f"{prefilled}_edited")
        await submit_modal(page)
        await wait_receipt_status(page, key3, "is-done")
        result["scenarios"]["failure_edit_resubmit"] = "pass"

        # Scenario 4: multi-card isolation by taskKey.
        await open_task_card(page, key1)
        await assert_receipt_highlighted_for_task(page, key1)
        await open_task_card(page, key2)
        await assert_receipt_highlighted_for_task(page, key2)
        result["scenarios"]["multi_card_isolation"] = "pass"

        await save_screenshot(page, "final")
        result["mock_api_calls"] = len(mock.calls)
        result["ok"] = True

        await context.close()
        await browser.close()

    return result


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Run inquiry receipt linkage E2E")
    parser.add_argument("--headed", action="store_true", help="run browser headed")
    args = parser.parse_args()

    server = StaticServer(root=ROOT)
    port = server.start()
    base_url = f"http://127.0.0.1:{port}"
    log(f"static server started: {base_url}")

    result_path = ARTIFACTS_DIR / f"e2e_inquiry_receipt_result_{int(time.time())}.json"
    try:
        result = await run_flow(base_url=base_url, headed=args.headed)
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
    code = asyncio.run(async_main())
    raise SystemExit(code)


if __name__ == "__main__":
    main()
