#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E2E: Mobile background/network interruption recovery test (real backend)

Scenario:
1) Login on mobile viewport.
2) Send message.
3) Immediately go offline for N seconds.
4) Back online + trigger visibility recovery.
5) Assert assistant message eventually appears and no 'load failed' style error bubble is shown.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("Please install Playwright first:")
    print("  pip install playwright")
    print("  python -m playwright install chromium")
    raise SystemExit(1)


DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_EMAIL = "test01@example.com"
DEFAULT_PASSWORD = "password123"
ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "e2e"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


async def save_artifacts(page, prefix: str) -> tuple[Path, Path]:
    stamp = int(time.time())
    png = ARTIFACTS_DIR / f"{prefix}_{stamp}.png"
    html = ARTIFACTS_DIR / f"{prefix}_{stamp}.html"
    await page.screenshot(path=str(png), full_page=True)
    html.write_text(await page.content(), encoding="utf-8")
    log(f"artifact screenshot: {png}")
    log(f"artifact html: {html}")
    return png, html


async def wait_until(predicate, timeout_sec: float, interval_sec: float = 0.2, timeout_msg: str = "timeout"):
    start = time.time()
    while True:
        if await predicate():
            return
        if time.time() - start > timeout_sec:
            raise AssertionError(timeout_msg)
        await asyncio.sleep(interval_sec)


async def login_if_needed(page, base_url: str, email: str, password: str) -> None:
    await page.goto(f"{base_url}/", wait_until="domcontentloaded")

    # already logged in
    if await page.locator("input.chatbar-input").count() > 0:
        return

    await page.goto(f"{base_url}/auth.html", wait_until="domcontentloaded")

    email_selectors = [
        'input[type="email"]',
        'input[name="email"]',
        'input[placeholder*="邮箱"]',
        'input[placeholder*="email"]',
        '#email',
    ]
    async def _find_email_input():
        for selector in email_selectors:
            loc = page.locator(selector)
            if await loc.count() > 0:
                return loc.first
        return None

    email_input = await _find_email_input()

    # New auth UI requires clicking a "登录" button to open the form sheet first.
    if email_input is None:
        login_trigger = page.locator("button.btn-primary, button:has-text('登录')").first
        if await login_trigger.count() > 0:
            await login_trigger.click()
            await asyncio.sleep(0.5)
            email_input = await _find_email_input()

    if email_input is None:
        if await page.locator("input.chatbar-input").count() > 0:
            return
        raise AssertionError("Cannot find email input on auth page")

    password_input = page.locator('input[type="password"]').first
    await email_input.fill(email)
    await password_input.fill(password)

    submit_selectors = [
        'button[type="submit"]',
        'button:has-text("登录")',
        'button:has-text("Login")',
        'input[type="submit"]',
    ]
    submit_btn = None
    for selector in submit_selectors:
        loc = page.locator(selector)
        if await loc.count() > 0:
            submit_btn = loc.first
            break

    if submit_btn is None:
        raise AssertionError("Cannot find login submit button")

    await submit_btn.click()

    async def _chat_input_ready():
        return await page.locator("input.chatbar-input").count() > 0

    await wait_until(_chat_input_ready, timeout_sec=20, timeout_msg="chat input not visible after login")


async def count_assistant_text_messages(page) -> int:
    return await page.eval_on_selector_all(
        ".chat-bubble-ai",
        """(els) => els
            .map(el => (el.innerText || '').trim())
            .filter(t => t && t !== '...' && t !== '…' && !/^\\.+$/.test(t))
            .length""",
    )


async def get_recent_messages(page, limit: int = 20) -> list[str]:
    return await page.eval_on_selector_all(
        ".chat-bubble-ai, .chat-bubble-user",
        """(els, lim) => els.slice(-lim).map(el => (el.innerText || '').trim()).filter(Boolean)""",
        limit,
    )


async def send_message(page, text: str) -> None:
    input_box = page.locator("input.chatbar-input").first
    await input_box.fill(text)
    send_btn = page.locator("button.chatbar-send-btn").first
    await send_btn.click()


async def assert_no_load_failed_visible(page) -> None:
    body_text = (await page.locator("body").inner_text()).lower()
    banned = ["load failed", "failed to fetch"]
    for b in banned:
        if b in body_text:
            raise AssertionError(f"found banned visible text: {b}")


async def assert_input_enabled(page) -> None:
    async def _enabled():
        disabled = await page.locator("input.chatbar-input").first.get_attribute("disabled")
        return disabled is None
    await wait_until(_enabled, timeout_sec=20, interval_sec=0.5, timeout_msg="chat input remains disabled")


async def run_round(page, context, round_idx: int, base_message: str, offline_seconds: int, timeout_sec: int) -> None:
    msg = f"{base_message} [round-{round_idx}] {int(time.time())}"
    before_count = await count_assistant_text_messages(page)
    log(f"round {round_idx}: assistant before={before_count}")

    await send_message(page, msg)
    await asyncio.sleep(0.2)

    log(f"round {round_idx}: offline for {offline_seconds}s")
    await context.set_offline(True)
    await asyncio.sleep(max(1, offline_seconds))

    log(f"round {round_idx}: back online and trigger visibility recovery")
    await context.set_offline(False)
    await page.bring_to_front()
    await page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")

    async def _assistant_increased():
        return (await count_assistant_text_messages(page)) > before_count

    await wait_until(
        _assistant_increased,
        timeout_sec=timeout_sec,
        interval_sec=0.5,
        timeout_msg=f"round {round_idx}: assistant reply not observed in {timeout_sec}s",
    )

    after_count = await count_assistant_text_messages(page)
    log(f"round {round_idx}: assistant after={after_count}")
    await assert_no_load_failed_visible(page)
    await assert_input_enabled(page)


async def main(args) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not args.headed,
            args=[
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ],
        )

        device = p.devices["iPhone 12"]
        context = await browser.new_context(**device)
        page = await context.new_page()

        try:
            log("checking and login")
            await login_if_needed(page, args.base_url, args.email, args.password)

            # ensure chat page
            await page.goto(f"{args.base_url}/", wait_until="domcontentloaded")
            await wait_until(lambda: page.locator("input.chatbar-input").count(), timeout_sec=20, timeout_msg="chat input not found")

            for i in range(1, args.rounds + 1):
                await run_round(
                    page=page,
                    context=context,
                    round_idx=i,
                    base_message=args.message,
                    offline_seconds=args.offline_seconds,
                    timeout_sec=args.timeout_seconds,
                )

            recent = await get_recent_messages(page)
            log("recent messages:\n- " + "\n- ".join(recent[-10:]))
            log("PASS: mobile background recovery scenario")
            return 0
        except Exception as e:
            log(f"FAIL: {e}")
            await save_artifacts(page, "mobile_background_recovery_fail")
            recent = await get_recent_messages(page)
            if recent:
                log("recent messages:\n- " + "\n- ".join(recent[-10:]))
            return 1
        finally:
            await context.close()
            await browser.close()


def parse_args():
    parser = argparse.ArgumentParser(description="E2E mobile background recovery test")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--message", default="移动端后台恢复测试消息")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--offline-seconds", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
