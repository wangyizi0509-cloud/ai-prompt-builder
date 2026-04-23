#!/usr/bin/env python3
"""Lightweight UI smoke probe for Crushe frontend.

This script runs a minimal user journey:
1) open auth page
2) login with test account
3) send one message
4) verify at least one assistant-side UI signal

It can be called standalone or by e2e_real_api_eval_runner.py.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 60


def _try_import_playwright():
    try:
        from playwright.sync_api import TimeoutError as PWTimeoutError
        from playwright.sync_api import sync_playwright

        return sync_playwright, PWTimeoutError, None
    except Exception as exc:  # pragma: no cover - import guard
        return None, None, exc


def _first_visible(page, selectors: list[str], timeout_ms: int):
    for sel in selectors:
        try:
            locator = page.locator(sel).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator, sel
        except Exception:
            continue
    return None, None


def run_ui_smoke(
    *,
    base_url: str,
    email: str,
    password: str,
    smoke_message: str,
    output_dir: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    headed: bool = False,
) -> dict[str, Any]:
    sync_playwright, pw_timeout_err, import_error = _try_import_playwright()

    ts = int(time.time())
    artifacts_dir = Path(output_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "ok": False,
        "base_url": base_url,
        "timestamp": ts,
        "steps": [],
        "errors": [],
        "screenshot": None,
    }

    if import_error is not None:
        result["errors"].append(f"playwright_import_failed: {import_error}")
        return result

    auth_url = base_url.rstrip("/") + "/auth.html"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        try:
            page.goto(auth_url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            result["steps"].append("open_auth_page")

            email_input, email_sel = _first_visible(
                page,
                [
                    "#email",
                    "input[name='email']",
                    "input[type='email']",
                    "input[placeholder*='邮箱']",
                ],
                timeout_ms=8000,
            )
            if email_input is None:
                raise RuntimeError("email_input_not_found")

            pwd_input, pwd_sel = _first_visible(
                page,
                [
                    "#password",
                    "input[name='password']",
                    "input[type='password']",
                ],
                timeout_ms=5000,
            )
            if pwd_input is None:
                raise RuntimeError("password_input_not_found")

            email_input.fill(email)
            pwd_input.fill(password)
            result["steps"].append(f"fill_login_form:{email_sel}|{pwd_sel}")

            login_btn, login_sel = _first_visible(
                page,
                [
                    "button:has-text('登录')",
                    "button[type='submit']",
                ],
                timeout_ms=5000,
            )
            if login_btn is None:
                raise RuntimeError("login_button_not_found")

            login_btn.click()
            result["steps"].append(f"click_login:{login_sel}")

            try:
                page.wait_for_url("**/index.html", timeout=12000)
            except pw_timeout_err:
                # some deployments keep auth.html while rendering app; continue probing
                pass

            chat_input, chat_sel = _first_visible(
                page,
                [
                    "[data-testid='chat-input']",
                    "input.chatbar-input",
                    "input[placeholder*='请输入']",
                ],
                timeout_ms=15000,
            )
            if chat_input is None:
                raise RuntimeError("chat_input_not_found_after_login")

            chat_input.fill(smoke_message)
            result["steps"].append(f"fill_chat_input:{chat_sel}")

            send_btn, send_sel = _first_visible(
                page,
                [
                    "[data-testid='chat-send-btn']",
                    "button.chatbar-send-btn",
                    "button:has-text('发送')",
                ],
                timeout_ms=5000,
            )
            if send_btn is not None:
                send_btn.click()
                result["steps"].append(f"click_send:{send_sel}")
            else:
                chat_input.press("Enter")
                result["steps"].append("press_enter_to_send")

            # assistant-side success signals (one of them is enough for smoke)
            signal_locators = [
                ".chat-bubble-ai",
                ".bottom-modal.open",
                "text=追问",
                "text=行动反馈",
            ]

            signal_detected = False
            for sel in signal_locators:
                try:
                    page.locator(sel).first.wait_for(state="visible", timeout=20000)
                    result["steps"].append(f"assistant_signal:{sel}")
                    signal_detected = True
                    break
                except Exception:
                    continue

            if not signal_detected:
                raise RuntimeError("assistant_signal_not_detected")

            shot_path = artifacts_dir / f"ui_smoke_{ts}.png"
            page.screenshot(path=str(shot_path), full_page=True)
            result["screenshot"] = str(shot_path)
            result["ok"] = True
        except Exception as exc:
            result["errors"].append(str(exc))
            shot_path = artifacts_dir / f"ui_smoke_failed_{ts}.png"
            try:
                page.screenshot(path=str(shot_path), full_page=True)
                result["screenshot"] = str(shot_path)
            except Exception:
                pass
        finally:
            browser.close()

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run minimal UI smoke probe.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--smoke-message", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--output-json", default="")

    args = parser.parse_args()

    result = run_ui_smoke(
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        smoke_message=args.smoke_message,
        output_dir=args.output_dir,
        timeout_seconds=args.timeout_seconds,
        headed=args.headed,
    )

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
