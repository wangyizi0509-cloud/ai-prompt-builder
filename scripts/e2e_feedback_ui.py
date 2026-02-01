#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E2E UI 自动化测试：行动指南反馈弹窗功能
使用 Playwright 进行真实浏览器测试，必须连接真实 LLM API（不 mock）
"""

import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("❌ 请先安装 Playwright:")
    print("   pip install playwright")
    print("   python -m playwright install chromium")
    sys.exit(1)

BASE_URL = "http://localhost:8000"
TEST_EMAIL = "test01@example.com"
TEST_PASSWORD = "password123"
TIMEOUT_SHORT = 5  # 减少超时时间
TIMEOUT_LONG = 60  # 减少长超时（从120秒降到60秒）
MAX_FOLLOWUP_ROUNDS = 3  # 减少最大追问轮数

ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts" / "e2e"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def log_step(step_name: str, status: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    status_emoji = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️"}
    emoji = status_emoji.get(status, "ℹ️")
    print(f"[{timestamp}] {emoji} [{status}] {step_name}")


async def save_screenshot(page, name: str):
    screenshot_path = ARTIFACTS_DIR / f"{name}_{int(time.time())}.png"
    await page.screenshot(path=str(screenshot_path))
    log_step(f"截图已保存: {screenshot_path}", "INFO")
    return screenshot_path


async def check_server_available():
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return resp.status == 200
    except Exception:
        return False


async def login(page):
    log_step("开始登录流程", "INFO")
    
    # 先尝试访问主页，检查是否已登录
    try:
        await page.goto(f"{BASE_URL}/", timeout=TIMEOUT_SHORT * 1000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        # 检查是否有聊天输入框（说明已登录）
        try:
            chat_input = await page.wait_for_selector('[data-testid="chat-input"]', timeout=5000)
            log_step("已登录状态（检测到聊天输入框）", "PASS")
            return True
        except PlaywrightTimeoutError:
            log_step("未登录，需要登录", "INFO")
    except Exception as e:
        log_step(f"访问主页失败: {e}，尝试登录页面", "INFO")
    
    # 访问登录页面
    try:
        await page.goto(f"{BASE_URL}/auth.html", timeout=TIMEOUT_SHORT * 1000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)
    except PlaywrightTimeoutError:
        log_step("无法访问 auth.html，尝试主页登录", "INFO")
        await page.goto(f"{BASE_URL}/", timeout=TIMEOUT_SHORT * 1000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
    
    # 尝试多种方式找到登录表单
    try:
        # 方法1: 标准 email/password 输入框
        email_input = None
        password_input = None
        
        # 尝试多种选择器
        selectors_email = [
            'input[type="email"]',
            'input[name="email"]',
            'input[placeholder*="邮箱"]',
            'input[placeholder*="email"]',
            'input[placeholder*="Email"]',
            '#email',
            '[name="email"]'
        ]
        
        for selector in selectors_email:
            try:
                email_input = await page.wait_for_selector(selector, timeout=2000)
                if email_input:
                    break
            except:
                continue
        
        if not email_input:
            # 检查是否已经登录
            try:
                await page.wait_for_selector('[data-testid="chat-input"]', timeout=3000)
                log_step("登录后自动跳转，已登录", "PASS")
                return True
            except:
                pass
            
            log_step("找不到邮箱输入框", "FAIL")
            await save_screenshot(page, "login_no_email_input")
            return False
        
        password_input = await page.wait_for_selector('input[type="password"]', timeout=TIMEOUT_SHORT * 1000)
        
        # 填写登录信息
        await email_input.fill(TEST_EMAIL)
        await password_input.fill(TEST_PASSWORD)
        await asyncio.sleep(0.3)  # 减少等待时间
        
        # 查找提交按钮
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("登录")',
            'button:has-text("Login")',
            'button:has-text("登 录")',
            'input[type="submit"]'
        ]
        
        submit_btn = None
        for selector in submit_selectors:
            try:
                submit_btn = await page.wait_for_selector(selector, timeout=2000)
                if submit_btn:
                    break
            except:
                continue
        
        if not submit_btn:
            log_step("找不到提交按钮", "FAIL")
            await save_screenshot(page, "login_no_submit_btn")
            return False
        
        await submit_btn.click()
        log_step("已点击登录按钮，等待跳转", "INFO")
        
        # 等待登录完成（跳转到主页或出现聊天输入框）
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        # 验证登录成功
        try:
            await page.wait_for_selector('[data-testid="chat-input"]', timeout=TIMEOUT_SHORT * 1000)
            log_step("登录成功", "PASS")
            return True
        except PlaywrightTimeoutError:
            # 再等待一下
            await asyncio.sleep(1)  # 减少等待时间
            try:
                await page.wait_for_selector('[data-testid="chat-input"]', timeout=5000)
                log_step("登录成功（延迟检测）", "PASS")
                return True
            except:
                log_step("登录后未检测到聊天输入框", "FAIL")
                await save_screenshot(page, "login_no_chat_input")
                return False
        
    except Exception as e:
        log_step(f"登录过程出错: {e}", "FAIL")
        await save_screenshot(page, "login_error")
        import traceback
        traceback.print_exc()
        return False


async def wait_for_guide_card(page, timeout_seconds=TIMEOUT_LONG):
    log_step(f"等待 guide 卡片出现（超时: {timeout_seconds}秒）", "INFO")
    try:
        # 方法1: 等待 testid 选择器
        try:
            await page.wait_for_selector('[data-testid="guide-card"]', timeout=timeout_seconds * 1000, state='attached')
            existing_cards = await page.query_selector_all('[data-testid="guide-card"]')
            if existing_cards:
                log_step(f"发现 {len(existing_cards)} 个 guide 卡片", "PASS")
                return True
        except PlaywrightTimeoutError:
            pass
        
        # 方法2: 等待 Vue 渲染 - 检查包含"行动指南"文本的卡片
        log_step("尝试通过文本内容查找 guide 卡片", "INFO")
        try:
            # 等待包含"行动指南"的卡片出现
            await page.wait_for_function(
                """
                () => {
                    const cards = document.querySelectorAll('[data-testid="guide-card"]');
                    return cards.length > 0;
                }
                """,
                timeout=timeout_seconds * 1000
            )
            existing_cards = await page.query_selector_all('[data-testid="guide-card"]')
            if existing_cards:
                log_step(f"通过 Vue 渲染检测到 {len(existing_cards)} 个 guide 卡片", "PASS")
                return True
        except PlaywrightTimeoutError:
            pass
        
        # 方法3: 检查是否有"行动指南"文本且包含反馈按钮
        log_step("尝试通过反馈按钮查找 guide 卡片", "INFO")
        try:
            await page.wait_for_selector('[data-testid="guide-feedback-btn"]', timeout=30 * 1000)
            feedback_btns = await page.query_selector_all('[data-testid="guide-feedback-btn"]')
            if feedback_btns:
                log_step(f"发现 {len(feedback_btns)} 个反馈按钮，说明 guide 卡片已存在", "PASS")
                return True
        except PlaywrightTimeoutError:
            pass
        
        # 如果都失败了，报告失败
        log_step("等待超时：guide 卡片未出现", "FAIL")
        # 检查页面中是否有相关元素
        try:
            action_guides = await page.query_selector_all('.bg-white.p-4.rounded-xl.shadow-sm')
            log_step(f"页面中找到 {len(action_guides)} 个可能的卡片元素", "INFO")
            
            # 检查是否有 action_guides 相关的文本
            page_text = await page.inner_text('body')
            if "行动指南" in page_text:
                log_step("页面中包含'行动指南'文本", "INFO")
            if "action_guides" in await page.content():
                log_step("页面 HTML 中包含 action_guides", "INFO")
            
            # 检查 Vue app 状态
            vue_state = await page.evaluate("""
                () => {
                    try {
                        const app = document.querySelector('#app').__vue_app__;
                        return app ? 'Vue app found' : 'Vue app not found';
                    } catch(e) {
                        return 'Cannot access Vue app: ' + e.message;
                    }
                }
            """)
            log_step(f"Vue 状态: {vue_state}", "INFO")
        except Exception as e:
            log_step(f"检查页面状态时出错: {e}", "INFO")
        
        await save_screenshot(page, "no_guide_card")
        # 保存页面 HTML
        try:
            html_path = ARTIFACTS_DIR / f"no_guide_card_html_{int(time.time())}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(await page.content())
            log_step(f"页面 HTML 已保存: {html_path}", "INFO")
        except:
            pass
        return False
    except Exception as e:
        log_step(f"等待 guide 卡片时出错: {e}", "FAIL")
        await save_screenshot(page, "wait_guide_card_error")
        return False


async def trigger_guide_generation(page):
    log_step("发送消息触发 guide 生成", "INFO")
    try:
        chat_input = await page.wait_for_selector('[data-testid="chat-input"]', timeout=TIMEOUT_SHORT * 1000)
        test_message = "我想追回前任，请给我一些行动指南"
        await chat_input.fill(test_message)
        await asyncio.sleep(0.3)  # 减少等待时间
        send_btn = await page.wait_for_selector('[data-testid="chat-send-btn"]', timeout=TIMEOUT_SHORT * 1000)
        await send_btn.click()
        log_step("消息已发送，等待响应", "INFO")
        await asyncio.sleep(3)
        
        # 等待响应加载完成
        log_step("等待页面响应完成", "INFO")
        try:
            # 等待 loading 状态消失
            await page.wait_for_function(
                "document.querySelector('[data-testid=\"chat-input\"]') && !document.querySelector('[data-testid=\"chat-input\"]').disabled",
                timeout=30 * 1000
            )
        except:
            pass
        
        # 检查页面内容
        page_content = await page.content()
        if "action_guides" in page_content or "action_guide" in page_content:
            log_step("检测到 guide 相关内容在页面中", "INFO")
        
        return await wait_for_guide_card(page)
    except PlaywrightTimeoutError as e:
        log_step(f"发送消息失败: {e}", "FAIL")
        await save_screenshot(page, "send_message_failed")
        # 保存页面 HTML 用于调试
        try:
            html_path = ARTIFACTS_DIR / f"page_html_{int(time.time())}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(await page.content())
            log_step(f"页面 HTML 已保存: {html_path}", "INFO")
        except:
            pass
        return False


async def click_feedback_button(page):
    log_step("查找并点击反馈按钮", "INFO")
    try:
        await page.wait_for_selector('[data-testid="guide-card"]', timeout=TIMEOUT_SHORT * 1000)
        feedback_btn = await page.wait_for_selector('[data-testid="guide-feedback-btn"]', timeout=TIMEOUT_SHORT * 1000)
        await feedback_btn.click()
        await page.wait_for_selector('[data-testid="feedback-modal"]', timeout=TIMEOUT_SHORT * 1000)
        modal = page.locator('[data-testid="feedback-modal"]')
        await modal.wait_for(state="visible", timeout=TIMEOUT_SHORT * 1000)
        log_step("反馈弹窗已打开", "PASS")
        return True
    except PlaywrightTimeoutError as e:
        log_step(f"打开反馈弹窗失败: {e}", "FAIL")
        await save_screenshot(page, "open_feedback_modal_failed")
        return False


async def fill_feedback_form(page, status="success", detail="我按指南做了，对方回应积极"):
    log_step("填写反馈表单", "INFO")
    try:
        status_select = await page.wait_for_selector('[data-testid="feedback-status-select"]', timeout=TIMEOUT_SHORT * 1000)
        await status_select.select_option(status)
        await asyncio.sleep(0.3)  # 减少等待时间
        detail_textarea = await page.wait_for_selector('[data-testid="feedback-detail-textarea"]', timeout=TIMEOUT_SHORT * 1000)
        await detail_textarea.fill(detail)
        await asyncio.sleep(0.3)  # 减少等待时间
        log_step("反馈表单填写完成", "PASS")
        return True
    except PlaywrightTimeoutError as e:
        log_step(f"填写表单失败: {e}", "FAIL")
        await save_screenshot(page, "fill_form_failed")
        return False


async def submit_feedback(page):
    log_step("提交反馈", "INFO")
    try:
        submit_btn = await page.wait_for_selector('[data-testid="feedback-submit-btn"]', timeout=TIMEOUT_SHORT * 1000)
        await submit_btn.wait_for(state="visible", timeout=TIMEOUT_SHORT * 1000)
        is_disabled = await submit_btn.get_attribute("disabled")
        if is_disabled:
            log_step("提交按钮被禁用，等待表单验证", "INFO")
            await asyncio.sleep(1)  # 减少等待时间
        await submit_btn.click()
        log_step("反馈已提交", "PASS")
        await asyncio.sleep(3)
        return True
    except PlaywrightTimeoutError as e:
        log_step(f"提交反馈失败: {e}", "FAIL")
        await save_screenshot(page, "submit_feedback_failed")
        return False


async def handle_followup_questions(page, max_rounds=MAX_FOLLOWUP_ROUNDS):
    log_step("检查是否有追问", "INFO")
    for round_num in range(1, max_rounds + 1):
        try:
            followup_block = page.locator('[data-testid="feedback-followup-block"]')
            await asyncio.sleep(1)  # 减少等待时间
            is_visible = await followup_block.is_visible()
            if not is_visible:
                modal = page.locator('[data-testid="feedback-modal"]')
                modal_visible = await modal.is_visible()
                if not modal_visible:
                    log_step("弹窗已关闭，反馈流程完成", "PASS")
                    return True
                else:
                    log_step(f"第 {round_num} 轮：等待追问出现...", "INFO")
                    await asyncio.sleep(3)  # 减少等待时间
                    continue
            
            try:
                question_element = await page.wait_for_selector('[data-testid="feedback-followup-question"]', timeout=TIMEOUT_SHORT * 1000)
                question_text = await question_element.inner_text()
                log_step(f"第 {round_num} 轮追问: {question_text[:50]}...", "INFO")
            except PlaywrightTimeoutError:
                log_step(f"第 {round_num} 轮：无法读取追问文本", "INFO")
            
            try:
                answer_textarea = await page.wait_for_selector('[data-testid="feedback-followup-textarea"]', timeout=TIMEOUT_SHORT * 1000)
                answer = f"第{round_num}轮回答：我按照指南执行了，效果不错"
                await answer_textarea.fill(answer)
                await asyncio.sleep(0.3)  # 减少等待时间
                submit_btn = await page.wait_for_selector('[data-testid="feedback-submit-btn"]', timeout=TIMEOUT_SHORT * 1000)
                await submit_btn.click()
                log_step(f"第 {round_num} 轮回答已提交", "PASS")
                await asyncio.sleep(3)  # 减少等待时间
            except PlaywrightTimeoutError as e:
                log_step(f"第 {round_num} 轮回答失败: {e}", "FAIL")
                await save_screenshot(page, f"followup_round_{round_num}_failed")
                return False
        except Exception as e:
            log_step(f"处理追问时出错: {e}", "FAIL")
            await save_screenshot(page, f"followup_error_round_{round_num}")
            return False
    
    log_step(f"已达到最大追问轮数 ({max_rounds})，但流程未完成", "FAIL")
    await save_screenshot(page, "max_followup_rounds_reached")
    return False


async def verify_feedback_completed(page):
    log_step("验证反馈流程完成", "INFO")
    try:
        modal = page.locator('[data-testid="feedback-modal"]')
        is_visible = await modal.is_visible()
        if is_visible:
            log_step("弹窗未关闭", "FAIL")
            await save_screenshot(page, "modal_not_closed")
            return False
        log_step("弹窗已关闭", "PASS")
        chat_input = await page.wait_for_selector('[data-testid="chat-input"]', timeout=TIMEOUT_SHORT * 1000)
        is_disabled = await chat_input.get_attribute("disabled")
        if is_disabled:
            log_step("聊天输入框被禁用", "FAIL")
            await save_screenshot(page, "chat_input_disabled")
            return False
        log_step("聊天输入框可用", "PASS")
        return True
    except PlaywrightTimeoutError as e:
        log_step(f"验证失败: {e}", "FAIL")
        await save_screenshot(page, "verification_failed")
        return False


async def run_test():
    print("=" * 60)
    print("🚀 开始 E2E UI 自动化测试：行动指南反馈弹窗")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"BASE_URL: {BASE_URL}")
    print(f"截图目录: {ARTIFACTS_DIR}")
    print("=" * 60)
    print()
    
    log_step("检查服务器是否可用", "INFO")
    server_available = await check_server_available()
    if not server_available:
        log_step(f"服务器 {BASE_URL} 不可用", "FAIL")
        print()
        print("💡 提示：请先启动服务：")
        print("   python3 .trae/skills/service-manager/scripts/start_services.py --mode dev")
        return False
    
    log_step("服务器可用", "PASS")
    print()
    
    async with async_playwright() as p:
        # 使用更轻量的浏览器配置，减少内存占用
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-dev-shm-usage',  # 减少共享内存使用
                '--disable-gpu',  # 禁用 GPU
                '--no-sandbox',  # 禁用沙箱（减少内存）
                '--disable-setuid-sandbox',
                '--disable-extensions',  # 禁用扩展
                '--disable-background-networking',  # 禁用后台网络
                '--disable-background-timer-throttling',
                '--disable-renderer-backgrounding',
                '--disable-backgrounding-occluded-windows',
                '--disable-ipc-flooding-protection',
                '--memory-pressure-off',  # 关闭内存压力检测
            ]
        )
        context = await browser.new_context(
            viewport={"width": 800, "height": 600},  # 减小视口
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            # 禁用不必要的功能
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True,
        )
        # 设置更短的超时
        context.set_default_timeout(TIMEOUT_SHORT * 1000)
        context.set_default_navigation_timeout(TIMEOUT_SHORT * 1000)
        page = await context.new_page()
        
        # 注意：不拦截资源，因为可能影响页面正常渲染
        # 如果需要进一步优化内存，可以取消下面的注释
        # await page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_())
        
        try:
            if not await login(page):
                return False
            print()
            if not await trigger_guide_generation(page):
                return False
            print()
            if not await click_feedback_button(page):
                return False
            print()
            if not await fill_feedback_form(page):
                return False
            print()
            if not await submit_feedback(page):
                return False
            print()
            if not await handle_followup_questions(page):
                log_step("追问处理可能未完成，继续验证", "INFO")
            print()
            if not await verify_feedback_completed(page):
                return False
            print()
            print("=" * 60)
            log_step("🎉 所有测试步骤通过！", "PASS")
            print("=" * 60)
            return True
        except Exception as e:
            log_step(f"测试执行出错: {e}", "FAIL")
            import traceback
            traceback.print_exc()
            await save_screenshot(page, "test_exception")
            return False
        finally:
            # 确保清理所有资源
            try:
                await page.close()
            except:
                pass
            try:
                await context.close()
            except:
                pass
            try:
                await browser.close()
            except:
                pass
            # 强制垃圾回收
            import gc
            gc.collect()


def main():
    try:
        success = asyncio.run(run_test())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ 测试脚本执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
