import time

import pytest

playwright = pytest.importorskip("playwright.sync_api", reason="playwright 未安装，跳过 UI 端到端测试")
expect = playwright.expect
sync_playwright = playwright.sync_playwright

from tests.helpers.feedback_test_utils import (
    create_action_guide,
    find_guide_by_id,
    get_chat_history,
    get_debug_context,
    post_chat,
    update_guide_status,
)


pytestmark = pytest.mark.api_test


def _build_guide_prompt(unique_tag: str) -> str:
    return (
        "请直接生成一条可执行的行动指南，包含明确的当前任务与步骤，"
        "不要追问。情境：和对方约会后需要跟进沟通。"
        f"唯一标记:{unique_tag}"
    )


def _complete_feedback_via_api(
    base_url: str,
    session_id: str,
    token: str,
    guide_id: str,
    guide_title: str,
    detail: str,
    followup_answer: str,
) -> dict:
    first_message = (
        f"[行动反馈] {guide_title}\n完成状态：成功\n完成详情：{detail}"
    )
    response = post_chat(
        base_url,
        session_id,
        first_message,
        token=token,
        feedback_mode={
            "guide_id": guide_id,
            "completion_status": "success",
            "completion_detail": detail,
        },
    )
    if response.get("feedback_status") == "asking":
        response = post_chat(
            base_url,
            session_id,
            followup_answer,
            token=token,
            feedback_mode={"guide_id": guide_id},
        )
    return response


def _login_via_ui(page, base_url: str, email: str, password: str) -> None:
    page.goto(f"{base_url}/auth.html")
    page.fill("#email", email)
    page.fill("#password", password)
    page.click("button:has-text('登录')")
    page.wait_for_url("**/index.html")


def _open_plan_drawer(page) -> None:
    page.click("button:has-text('02 计划')")
    expect(page.locator(".top-drawer.open")).to_be_visible()
    expect(page.locator("h4:has-text('行动指南')")).to_be_visible()


def _get_last_guide_card(page):
    header = page.locator(".top-drawer.open h4:has-text('行动指南')").last
    expect(header).to_be_visible()
    return header.locator("xpath=ancestor::div[contains(@class,'rounded-xl')][1]")


def _open_feedback_modal_on_last_guide(page):
    card = _get_last_guide_card(page)
    button = card.locator("button:has-text('反馈')")
    expect(button).to_be_visible()
    button.click()
    modal = page.locator(".bottom-modal.open")
    expect(modal.locator("h3:has-text('行动反馈')")).to_be_visible()
    return modal


def test_feedback_button_flow_with_followup(
    base_url,
    session_id,
    auth_token,
    test_credentials,
    unique_tag,
):
    guide = create_action_guide(
        base_url,
        session_id,
        auth_token,
        _build_guide_prompt(unique_tag),
    )
    guide_id = guide.get("id")
    assert guide_id, "guide_id 未生成"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        _login_via_ui(page, base_url, test_credentials["email"], test_credentials["password"])
        _open_plan_drawer(page)

        modal = _open_feedback_modal_on_last_guide(page)
        submit_button = modal.locator("button:has-text('提交反馈')")
        expect(submit_button).to_be_disabled()

        modal.locator("select").select_option("success")
        modal.locator("textarea").first.fill("做了尝试，但细节先不展开。")
        expect(submit_button).to_be_enabled()
        submit_button.click()

        expect(modal.locator("text=追问")).to_be_visible(timeout=60000)
        modal.locator("textarea").nth(1).fill("补充：对方回复积极，约了下次见面。")
        modal.locator("button:has-text('提交回答')").click()
        expect(page.locator(".bottom-modal.open")).to_have_count(0)
        browser.close()

    context = get_debug_context(base_url, session_id)
    guides = (context.get("layer2_working") or {}).get("action_guides", [])
    target = find_guide_by_id(guides, guide_id)
    assert target, "未在存储中找到反馈指南"
    feedback = target.get("feedback_data") or {}
    assert feedback.get("completion_status")
    assert feedback.get("completion_detail")
    assert feedback.get("qa_history")
    assert feedback.get("feedback_summary")


def test_delegate_feedback_prefill_text_entry(
    base_url,
    session_id,
    auth_token,
    test_credentials,
    unique_tag,
):
    guide = create_action_guide(
        base_url,
        session_id,
        auth_token,
        _build_guide_prompt(unique_tag),
    )
    title = guide.get("title") or "行动指南"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        _login_via_ui(page, base_url, test_credentials["email"], test_credentials["password"])
        page.fill("input[placeholder='请输入您的情感问题...']", f"我已经完成了{title}，情况是对方回复正常但还不够明确。")
        page.keyboard.press("Enter")
        modal = page.locator(".bottom-modal.open")
        expect(modal.locator("h3:has-text('行动反馈')")).to_be_visible(timeout=60000)
        select = modal.locator("select")
        expect(select).to_be_enabled()
        select.select_option("partial")
        modal.locator("textarea").first.fill("执行完成一半，对方回复但没有进一步表态。")
        modal.locator("button:has-text('提交反馈')").click()
        browser.close()


def test_feedback_resume_flow(
    base_url,
    session_id,
    auth_token,
    test_credentials,
    unique_tag,
):
    create_action_guide(
        base_url,
        session_id,
        auth_token,
        _build_guide_prompt(unique_tag),
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        _login_via_ui(page, base_url, test_credentials["email"], test_credentials["password"])
        _open_plan_drawer(page)
        modal = _open_feedback_modal_on_last_guide(page)
        modal.locator("select").select_option("success")
        modal.locator("textarea").first.fill("先简单反馈，等待追问。")
        modal.locator("button:has-text('提交反馈')").click()
        expect(modal.locator("text=追问")).to_be_visible(timeout=60000)

        page.click(".drawer-overlay")
        expect(page.locator(".bottom-modal.open")).to_have_count(0)

        page.fill("input[placeholder='请输入您的情感问题...']", "我先继续聊一下别的问题。")
        page.keyboard.press("Enter")
        expect(page.locator(".bottom-modal.open")).to_have_count(1, timeout=60000)
        browser.close()


def test_feedback_edge_cases(
    base_url,
    session_id,
    auth_token,
    test_credentials,
    unique_tag,
):
    guide = create_action_guide(
        base_url,
        session_id,
        auth_token,
        _build_guide_prompt(unique_tag),
    )
    guide_id = guide.get("id")
    assert guide_id, "guide_id 未生成"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        _login_via_ui(page, base_url, test_credentials["email"], test_credentials["password"])
        _open_plan_drawer(page)
        feedback_buttons_before = page.locator("button:has-text('反馈')").count()
        assert feedback_buttons_before > 0

        modal = _open_feedback_modal_on_last_guide(page)
        submit_button = modal.locator("button:has-text('提交反馈')")
        expect(submit_button).to_be_disabled()
        page.click(".drawer-overlay")

        update_guide_status(base_url, session_id, guide_id, "cancelled")
        page.reload()
        _open_plan_drawer(page)
        feedback_buttons_after_cancel = page.locator("button:has-text('反馈')").count()
        assert feedback_buttons_after_cancel <= feedback_buttons_before - 1
        browser.close()


def test_storage_and_compression_check(
    base_url,
    session_id,
    auth_token,
    unique_tag,
):
    guide = create_action_guide(
        base_url,
        session_id,
        auth_token,
        _build_guide_prompt(unique_tag),
    )
    guide_id = guide.get("id")
    guide_title = guide.get("title") or "行动指南"

    _complete_feedback_via_api(
        base_url,
        session_id,
        auth_token,
        guide_id,
        guide_title,
        detail="执行顺利，对方回应积极。",
        followup_answer="补充：对方愿意下次见面，具体时间待定。",
    )

    context = get_debug_context(base_url, session_id)
    guides = (context.get("layer2_working") or {}).get("action_guides", [])
    target = find_guide_by_id(guides, guide_id)
    assert target, "存储中未找到反馈指南"
    feedback = target.get("feedback_data") or {}
    assert feedback.get("feedback_summary")

    history = get_chat_history(base_url, session_id, token=auth_token)
    messages = history.get("messages") or []
    contents = [m.get("content", "") for m in messages if isinstance(m, dict)]
    assert any("[反馈完成]" in c for c in contents), "未找到反馈总结标记"
    assert not any("[行动反馈]" in c for c in contents), "反馈原始内容未被压缩"


def test_real_llm_regression_two_paths(
    base_url,
    session_id,
    auth_token,
    unique_tag,
):
    guide = create_action_guide(
        base_url,
        session_id,
        auth_token,
        _build_guide_prompt(unique_tag),
    )
    guide_id = guide.get("id")
    guide_title = guide.get("title") or "行动指南"

    asking_response = post_chat(
        base_url,
        session_id,
        f"[行动反馈] {guide_title}\n完成状态：成功\n完成详情：做了，但细节暂时没补充。",
        token=auth_token,
        feedback_mode={
            "guide_id": guide_id,
            "completion_status": "success",
            "completion_detail": "做了，但细节暂时没补充。",
        },
    )
    assert asking_response.get("feedback_status") in ("asking", "completed")

    if asking_response.get("feedback_status") == "asking":
        post_chat(
            base_url,
            session_id,
            "补充：对方回复积极，我们达成下次联系共识。",
            token=auth_token,
            feedback_mode={"guide_id": guide_id},
        )

    direct_response = _complete_feedback_via_api(
        base_url,
        session_id,
        auth_token,
        guide_id,
        guide_title,
        detail="执行后对方积极回应，并确认下次见面时间。",
        followup_answer="补充：对方还提到愿意配合调整节奏。",
    )
    assert direct_response.get("feedback_status") in ("asking", "completed")
