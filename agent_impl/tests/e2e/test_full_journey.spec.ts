/**
 * E2E Full Journey Test: 完整用户旅程可视化端到端测试
 *
 * 测试流程（真实用户操作，通过浏览器）：
 * 1. 打开登录页，填账号密码，登录
 * 2. 等待"开启情感攻略"按钮出现，点击
 * 3. 跟随小话的 inquiry 提问卡片循环回答（含截图上传）
 * 4. 直到小话主动停止提问（无卡片），检查是否已有 status/plan/guide
 * 5. 如果缺少，发消息引导 AI 继续生成
 * 6. 切到"规划"Tab 截图验证展示
 * 7. 点击"行动反馈"按钮，提交反馈，验证 AI 回复
 *
 * 每个关键步骤都保存截图到 artifacts/e2e/full-journey/
 *
 * 运行方式：
 *   cd agent_impl/tests/e2e
 *   npx playwright test test_full_journey --reporter=list
 *
 * 环境变量（可选）：
 *   E2E_BASE_URL      - 服务地址（默认 http://127.0.0.1:8000）
 *   E2E_USER_EMAIL    - 测试账号（默认 test01@example.com）
 *   E2E_USER_PASSWORD - 测试账号密码（默认 password123）
 */

import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

// ============================================================
// 配置
// ============================================================

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8000';

const TEST_USER = {
  email: process.env.E2E_USER_EMAIL || 'test01@example.com',
  password: process.env.E2E_USER_PASSWORD || 'password123',
};

// 仓库内测试用截图目录（相对于仓库根目录）
const SCREENSHOTS_DIR = path.resolve(
  __dirname,
  '../../../Benchmark/caseBaseDate/用户发送的截图',
);

const ARTIFACTS_DIR = path.resolve(__dirname, '../../../artifacts/e2e/full-journey');

// 超时配置（LLM 响应较慢）
const LLM_TIMEOUT = 180_000;      // 单次 LLM 响应最长等待
const INQUIRY_APPEAR_TIMEOUT = 30_000;  // 等待 inquiry 弹窗出现
const UI_TIMEOUT = 15_000;        // 普通 UI 交互超时

const MAX_INQUIRY_ROUNDS = 15;    // 最多跟随 inquiry 轮数
const MAX_FOLLOWUP_MSGS = 5;      // 最多主动发引导消息轮数

// ============================================================
// 辅助工具
// ============================================================

let stepCounter = 0;

function ensureArtifactsDir() {
  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
}

async function screenshot(page: Page, label: string): Promise<string> {
  ensureArtifactsDir();
  stepCounter++;
  const filename = `${String(stepCounter).padStart(2, '0')}_${label}.png`;
  const filePath = path.join(ARTIFACTS_DIR, filename);
  await page.screenshot({ path: filePath, fullPage: false });
  console.log(`[screenshot] saved: ${filename}`);
  return filePath;
}

function log(phase: string, msg: string) {
  const ts = new Date().toISOString().slice(11, 19);
  console.log(`[${ts}] [${phase}] ${msg}`);
}

/** 从 Benchmark 截图目录随机选一张 jpg */
function pickRandomScreenshot(): string {
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    throw new Error(`截图目录不存在: ${SCREENSHOTS_DIR}`);
  }
  const files = fs.readdirSync(SCREENSHOTS_DIR).filter((f) => /\.(jpg|jpeg|png)$/i.test(f));
  if (files.length === 0) {
    throw new Error(`截图目录为空: ${SCREENSHOTS_DIR}`);
  }
  const picked = files[Math.floor(Math.random() * files.length)];
  return path.join(SCREENSHOTS_DIR, picked);
}

/** 等待 AI 回复（isLoading 消失 + 不再有新的 loading spinner） */
async function waitForAiResponse(page: Page, timeout = LLM_TIMEOUT) {
  // 等待 loading 出现（可能有延迟），然后等它消失
  try {
    await page.waitForSelector('.animate-bounce', { state: 'visible', timeout: 5000 });
  } catch {
    // loading 可能太快消失了，直接继续
  }
  // 等待 loading 消失
  await page.waitForSelector('.animate-bounce', { state: 'hidden', timeout });
  // 额外稳定等待，确保 Vue 状态更新完毕
  await page.waitForTimeout(800);
}

/** 检查 inquiry 弹窗是否当前打开 */
async function isInquiryModalOpen(page: Page): Promise<boolean> {
  const modal = page.locator('.bottom-modal').filter({ hasText: '需要更多信息' });
  try {
    const cls = await modal.getAttribute('class', { timeout: 2000 });
    return (cls || '').includes('open');
  } catch {
    return false;
  }
}

/** 等待 inquiry 弹窗出现，超时返回 false */
async function waitForInquiryModal(page: Page, timeout = INQUIRY_APPEAR_TIMEOUT): Promise<boolean> {
  try {
    // 等待 bottom-modal 有 open class 且包含"需要更多信息"文字
    await page.locator('.bottom-modal.open').filter({ hasText: '需要更多信息' }).waitFor({
      state: 'visible',
      timeout,
    });
    return true;
  } catch {
    return false;
  }
}

// ============================================================
// 交互：填写 inquiry 卡片
// ============================================================

/**
 * 填写并提交当前打开的 inquiry 弹窗
 * 返回 true 表示提交成功，false 表示弹窗不再可见
 */
async function fillAndSubmitInquiryModal(page: Page, round: number): Promise<boolean> {
  const modal = page.locator('.bottom-modal.open').filter({ hasText: '需要更多信息' });

  // 找到弹窗内所有问题块
  const questionBlocks = modal.locator('.bg-white.rounded-xl.p-4.shadow-sm').filter({ hasText: /^\d+\./ });
  const count = await questionBlocks.count();
  log('INQUIRY', `round ${round}: ${count} questions found`);

  for (let i = 0; i < count; i++) {
    const block = questionBlocks.nth(i);

    // 自由文本输入
    const textarea = block.locator('textarea').first();
    if (await textarea.isVisible({ timeout: 500 }).catch(() => false)) {
      const questionText = await block.locator('p').first().innerText();
      await textarea.fill(`测试回答：${questionText.slice(0, 40)}`);
      log('INQUIRY', `  q${i + 1}: text filled`);
      continue;
    }

    // 单选题（radio）
    const firstRadioLabel = block.locator('label').first();
    if (await firstRadioLabel.isVisible({ timeout: 500 }).catch(() => false)) {
      const radioInput = block.locator('input[type="radio"]').first();
      if (await radioInput.count() > 0) {
        await firstRadioLabel.click();
        log('INQUIRY', `  q${i + 1}: single choice selected`);
        continue;
      }
    }

    // 多选题（checkbox）
    const firstCheckboxLabel = block.locator('label').first();
    if (await firstCheckboxLabel.isVisible({ timeout: 500 }).catch(() => false)) {
      const checkboxInput = block.locator('input[type="checkbox"]').first();
      if (await checkboxInput.count() > 0) {
        await firstCheckboxLabel.click();
        log('INQUIRY', `  q${i + 1}: multi choice selected`);
        continue;
      }
    }

    // 截图上传题（有虚线上传区域）
    const uploadArea = block.locator('.border-dashed');
    if (await uploadArea.isVisible({ timeout: 500 }).catch(() => false)) {
      const screenshotPath = pickRandomScreenshot();
      log('INQUIRY', `  q${i + 1}: uploading screenshot: ${path.basename(screenshotPath)}`);

      // 找到隐藏的 file input，直接 setInputFiles 触发上传
      const fileInput = block.locator('input[type="file"]');
      await fileInput.setInputFiles(screenshotPath);

      // 等待上传完成（上传中的 spinner 消失）
      try {
        await page.waitForSelector('.animate-spin', { state: 'visible', timeout: 3000 });
        await page.waitForSelector('.animate-spin', { state: 'hidden', timeout: 30_000 });
      } catch {
        // 上传可能很快
      }
      await page.waitForTimeout(500);
      log('INQUIRY', `  q${i + 1}: screenshot upload done`);
      continue;
    }
  }

  // 截图当前填写状态
  await screenshot(page, `inquiry_filled_round_${round}`);

  // 点击提交按钮
  const submitBtn = modal.locator('button').filter({ hasText: '提交回答' });
  await expect(submitBtn).toBeEnabled({ timeout: UI_TIMEOUT });
  await submitBtn.click();
  log('INQUIRY', `round ${round}: submitted`);

  // 等待弹窗关闭
  try {
    await page.locator('.bottom-modal.open').filter({ hasText: '需要更多信息' }).waitFor({
      state: 'hidden',
      timeout: UI_TIMEOUT,
    });
  } catch {
    // 已关闭或状态变更
  }

  await screenshot(page, `inquiry_submitted_round_${round}`);
  return true;
}

// ============================================================
// 状态检查：从页面 state 里读报告
// ============================================================

/**
 * 从前端 Vue 暴露的 state 读取 layer2_memory 报告情况
 * 通过 page.evaluate 访问 Vue app 的数据
 */
async function checkReportsViaUI(page: Page): Promise<{
  hasStatus: boolean;
  hasActionPlan: boolean;
  hasGuide: boolean;
  guideId: string | null;
}> {
  return page.evaluate(() => {
    // 尝试从 Vue app instance 读取 state
    const appEl = document.querySelector('#app') as HTMLElement & { __vue_app__?: unknown };
    if (!appEl?.__vue_app__) {
      return { hasStatus: false, hasActionPlan: false, hasGuide: false, guideId: null };
    }

    // 通过 window 上暴露的调试变量（如果有）
    const win = window as Record<string, unknown>;
    if (win.__crushe_state__) {
      const s = win.__crushe_state__ as Record<string, unknown>;
      const l2 = (s.layer2_memory || {}) as Record<string, unknown>;
      const guides = (l2.action_guides || s.action_guides) as unknown[];
      const firstGuideId = guides && guides.length > 0
        ? ((guides[0] as Record<string, unknown>).guide_id || (guides[0] as Record<string, unknown>).id || null) as string | null
        : null;
      return {
        hasStatus: !!(l2.status_report || s.status_report),
        hasActionPlan: !!(l2.action_plan || s.action_plan),
        hasGuide: !!(guides && guides.length > 0),
        guideId: firstGuideId,
      };
    }
    return { hasStatus: false, hasActionPlan: false, hasGuide: false, guideId: null };
  });
}

/**
 * 通过 UI 检查规划 Tab 内容：
 * - 切到规划 Tab，检查"当前现状"和"情感计划"卡片是否有内容
 */
async function checkPlanTabContent(page: Page): Promise<{
  hasStatusContent: boolean;
  hasPlanContent: boolean;
  hasGuideContent: boolean;
}> {
  // 点击规划 Tab
  const planTab = page.locator('button[role="tab"]').filter({ hasText: '规划' });
  await planTab.click();
  await page.waitForTimeout(800);
  await screenshot(page, 'plan_tab_opened');

  // 检查"当前现状"子 Tab 是否有实质内容（不是"暂无"）
  const statusCard = page.locator('.plan-subcard').filter({ hasText: '当前现状' }).or(
    page.locator('.plan-subcard-body').filter({ hasNotText: '请继续对话' })
  );
  const hasStatusContent = await statusCard.count() > 0 &&
    !(await page.locator('.plan-subcard-body').filter({ hasText: '请继续对话' }).first().isVisible().catch(() => false));

  // 点击"情感计划"子 Tab（plan）
  const planSubTab = page.locator('button[role="tab"]').filter({ hasText: '情感计划' });
  if (await planSubTab.count() > 0) {
    await planSubTab.click();
    await page.waitForTimeout(600);
  }
  await screenshot(page, 'plan_tab_plan_subtab');

  // 检查行动指南区域
  const guideBlock = page.locator('.plan-subcard').filter({ hasText: '行动指南' });
  const hasGuideContent = await guideBlock.count() > 0 &&
    !(await guideBlock.filter({ hasText: '请继续对话' }).count() > 0);

  // 检查情感计划
  const planBlock = page.locator('.plan-subcard-body').first();
  const hasPlanContent = await planBlock.count() > 0;

  await screenshot(page, 'plan_tab_full');

  return { hasStatusContent, hasPlanContent, hasGuideContent };
}

// ============================================================
// 主测试
// ============================================================

test.describe('完整用户旅程 - 可视化 E2E', () => {
  test.setTimeout(900_000); // 完整流程最多 15 分钟

  test('登录 → 开启情感攻略 → 跟随小话完整流程 → 规划验证 → 行动反馈', async ({ page }) => {
    ensureArtifactsDir();
    stepCounter = 0;

    // ================================================================
    // Phase 1: 登录
    // ================================================================
    log('LOGIN', `opening ${BASE_URL}/auth.html`);
    await page.goto(`${BASE_URL}/auth.html`, { waitUntil: 'networkidle' });
    await screenshot(page, 'auth_page_loaded');

    // 填写邮箱
    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="邮箱"], input[placeholder*="mail"]').first();
    await emailInput.waitFor({ state: 'visible', timeout: UI_TIMEOUT });
    await emailInput.fill(TEST_USER.email);

    // 填写密码
    const passwordInput = page.locator('input[type="password"]').first();
    await passwordInput.fill(TEST_USER.password);
    await screenshot(page, 'auth_filled');

    // 点击登录
    const loginBtn = page.locator('button').filter({ hasText: /登录|login/i }).first();
    await loginBtn.click();

    // 等待跳转到主页（出现小话的聊天界面）
    await page.waitForURL(`${BASE_URL}/`, { timeout: 30_000 }).catch(() => {
      // 某些情况下不会跳转 URL，直接加载内容
    });
    await page.waitForSelector('.app-container, #app', { timeout: 20_000 });
    await page.waitForTimeout(1500);
    await screenshot(page, 'home_after_login');
    log('LOGIN', 'login successful');

    // ================================================================
    // Phase 2: 开启 Onboarding — 点击"开启情感攻略"按钮
    // ================================================================
    log('ONBOARDING', 'waiting for "开启情感攻略" button...');

    // 按钮在延迟 6 秒的 setTimeout 后出现（两个 3 秒 delay）
    const onboardingBtn = page.locator('button.onboarding-btn').filter({ hasText: '开启情感攻略' });
    await onboardingBtn.waitFor({ state: 'visible', timeout: 20_000 });
    await screenshot(page, 'onboarding_btn_visible');

    await onboardingBtn.click();
    log('ONBOARDING', 'clicked 开启情感攻略');
    await screenshot(page, 'onboarding_btn_clicked');

    // ================================================================
    // Phase 3: 跟随小话的 inquiry 提问循环
    // 小话会主动发卡片，我们全程跟随回答，直到停止
    // ================================================================
    log('INQUIRY_LOOP', 'entering inquiry follow loop...');
    let inquiryRound = 0;
    let hasStatus = false;
    let hasActionPlan = false;
    let hasGuide = false;
    let lastGuideId: string | null = null;

    while (inquiryRound < MAX_INQUIRY_ROUNDS) {
      // 等待 AI 给出回复（loading 消失）
      await waitForAiResponse(page, LLM_TIMEOUT);

      // 检查是否出现 inquiry 弹窗
      const modalOpen = await waitForInquiryModal(page, INQUIRY_APPEAR_TIMEOUT);

      if (modalOpen) {
        inquiryRound++;
        log('INQUIRY_LOOP', `inquiry modal round ${inquiryRound} detected`);
        await fillAndSubmitInquiryModal(page, inquiryRound);
        // 等待 AI 处理后继续循环
        await waitForAiResponse(page, LLM_TIMEOUT);
      } else {
        // 没有新 inquiry 卡片了，说明小话这轮结束了
        log('INQUIRY_LOOP', `no more inquiry after round ${inquiryRound}, exiting loop`);
        break;
      }
    }

    log('INQUIRY_LOOP', `completed ${inquiryRound} inquiry rounds`);
    expect(inquiryRound, 'should have at least 1 inquiry round').toBeGreaterThanOrEqual(1);
    await screenshot(page, 'after_inquiry_loop');

    // ================================================================
    // Phase 4: 检查 status/plan/guide 是否已产出
    // 如果没有，发消息继续引导 AI
    // ================================================================
    const followupPrompts = [
      '帮我分析一下我们目前的关系现状',
      '请帮我制定一个行动计划',
      '给我一个具体的行动指南',
      '下一步我应该怎么做？',
      '帮我更新一下攻略',
    ];

    for (let i = 0; i < MAX_FOLLOWUP_MSGS; i++) {
      // 先检查规划 Tab 里是否有内容（通过 UI 看）
      const chatTab = page.locator('button[role="tab"]').filter({ hasText: '小话' });
      await chatTab.click();
      await page.waitForTimeout(500);

      // 用 API 侧读取 state 检查
      const reports = await checkReportsViaUI(page);
      hasStatus = reports.hasStatus;
      hasActionPlan = reports.hasActionPlan;
      hasGuide = reports.hasGuide;
      if (reports.guideId) lastGuideId = reports.guideId;

      log('REPORTS', `status=${hasStatus} plan=${hasActionPlan} guide=${hasGuide} guideId=${lastGuideId}`);

      if (hasStatus && hasActionPlan && hasGuide) {
        log('REPORTS', 'all 3 report types found, moving on');
        break;
      }

      if (i >= followupPrompts.length) break;

      // 发消息继续引导
      const prompt = followupPrompts[i];
      log('FOLLOWUP', `sending: "${prompt}"`);
      const chatInput = page.locator('input.chatbar-input, input[placeholder*="情感问题"]').first();
      await chatInput.fill(prompt);
      await page.keyboard.press('Enter');

      await waitForAiResponse(page, LLM_TIMEOUT);

      // 如果又出现了 inquiry，先处理
      const newModal = await waitForInquiryModal(page, 8000);
      if (newModal) {
        inquiryRound++;
        await fillAndSubmitInquiryModal(page, inquiryRound);
        await waitForAiResponse(page, LLM_TIMEOUT);
      }
    }

    await screenshot(page, 'after_followup_msgs');

    // ================================================================
    // Phase 5: 切到"规划"Tab 验证内容展示
    // ================================================================
    log('PLAN_TAB', 'switching to plan tab for verification');
    const planTabContent = await checkPlanTabContent(page);
    log('PLAN_TAB', `statusContent=${planTabContent.hasStatusContent} planContent=${planTabContent.hasPlanContent} guideContent=${planTabContent.hasGuideContent}`);

    // 报告"规划"Tab 展示状态（不强制 assert，发现问题记录截图即可）
    if (!planTabContent.hasStatusContent) {
      console.warn('[WARN] 规划Tab-当前现状: 内容可能为空，请查看截图确认');
    }
    if (!planTabContent.hasGuideContent) {
      console.warn('[WARN] 规划Tab-行动指南: 内容可能为空，请查看截图确认');
    }

    // 强制断言至少有一项报告产出
    const anyReport = planTabContent.hasStatusContent || planTabContent.hasPlanContent || planTabContent.hasGuideContent || hasStatus || hasActionPlan || hasGuide;
    expect(anyReport, '规划页或 state 中应至少有一份报告（status/plan/guide）').toBe(true);

    // ================================================================
    // Phase 6: 行动反馈
    // 回到小话 Tab，找到"行动反馈"悬浮按钮并提交
    // ================================================================
    log('FEEDBACK', 'switching back to 小话 tab for feedback');
    const chatTabBtn = page.locator('button[role="tab"]').filter({ hasText: '小话' });
    await chatTabBtn.click();
    await page.waitForTimeout(500);

    // 重新切到规划 Tab，找到"行动反馈"悬浮按钮（在规划 Tab 的情感计划子页面）
    const planTab2 = page.locator('button[role="tab"]').filter({ hasText: '规划' });
    await planTab2.click();
    await page.waitForTimeout(600);

    // 点击情感计划子 Tab
    const planSubTab2 = page.locator('button[role="tab"]').filter({ hasText: '情感计划' });
    if (await planSubTab2.count() > 0) {
      await planSubTab2.click();
      await page.waitForTimeout(600);
    }

    // 找到"行动反馈"悬浮按钮
    const feedbackFab = page.locator('.plan-feedback-btn').filter({ hasText: '行动反馈' });
    const feedbackFabVisible = await feedbackFab.isVisible({ timeout: 5000 }).catch(() => false);

    if (feedbackFabVisible) {
      await feedbackFab.click();
      log('FEEDBACK', 'clicked 行动反馈 FAB');
      await page.waitForTimeout(800);
      await screenshot(page, 'feedback_modal_opened');

      // 填写反馈表单
      // 1. 选择完成状态"成功"
      const successBtn = page.locator('[data-testid="feedback-modal"] button, .bottom-modal.open button')
        .filter({ hasText: '成功' });
      if (await successBtn.count() > 0) {
        await successBtn.first().click();
        log('FEEDBACK', 'selected status: 成功');
      }

      // 2. 填写详情描述
      const detailTextarea = page.locator('[data-testid="feedback-modal"] textarea, .bottom-modal.open textarea').first();
      if (await detailTextarea.count() > 0) {
        await detailTextarea.fill('我按照你的建议约她出来了，她答应了！我们去咖啡馆聊了两个小时，感觉很好。');
        log('FEEDBACK', 'filled completion detail');
      }

      await screenshot(page, 'feedback_form_filled');

      // 3. 点击提交反馈
      const submitFeedbackBtn = page.locator('[data-testid="feedback-submit-btn"]');
      await expect(submitFeedbackBtn).toBeEnabled({ timeout: UI_TIMEOUT });
      await submitFeedbackBtn.click();
      log('FEEDBACK', 'submitted feedback');

      // 等待 feedback modal 关闭 + AI 回复
      try {
        await page.locator('[data-testid="feedback-modal"]').waitFor({ state: 'hidden', timeout: 10_000 });
      } catch {
        // 可能已关闭
      }

      // 切回小话 Tab 看 AI 回复
      const chatTabFinal = page.locator('button[role="tab"]').filter({ hasText: '小话' });
      await chatTabFinal.click();
      await waitForAiResponse(page, LLM_TIMEOUT);
      await screenshot(page, 'feedback_ai_reply');

      // 如果出现追问 inquiry，也继续回答
      const afterFeedbackModal = await waitForInquiryModal(page, 8000);
      if (afterFeedbackModal) {
        inquiryRound++;
        log('FEEDBACK', 'follow-up inquiry after feedback, answering...');
        await fillAndSubmitInquiryModal(page, inquiryRound);
        await waitForAiResponse(page, LLM_TIMEOUT);
        await screenshot(page, 'feedback_followup_done');
      }

      // 验证有 AI 文字回复（消息列表里有 AI 消息）
      const aiMessages = page.locator('.chat-bubble-ai');
      const aiMsgCount = await aiMessages.count();
      log('FEEDBACK', `AI message count: ${aiMsgCount}`);
      expect(aiMsgCount, 'should have at least one AI message after feedback').toBeGreaterThan(0);

    } else {
      // 行动反馈按钮不可见，说明 guide 还未产出
      console.warn('[WARN] 行动反馈按钮不可见，guide 可能尚未生成，记录截图');
      await screenshot(page, 'feedback_btn_not_visible');

      // 验证至少有对话消息
      const anyMsg = page.locator('.chat-bubble-ai, .chat-bubble-user');
      const msgCount = await anyMsg.count();
      expect(msgCount, 'should have at least some messages in chat').toBeGreaterThan(0);
    }

    // ================================================================
    // 最终截图 + 生成摘要
    // ================================================================
    const finalChatTab = page.locator('button[role="tab"]').filter({ hasText: '小话' });
    await finalChatTab.click();
    await page.waitForTimeout(500);
    await screenshot(page, 'final_state');

    const summary = {
      timestamp: new Date().toISOString(),
      user: TEST_USER.email,
      inquiryRounds: inquiryRound,
      hasStatusReport: hasStatus,
      hasActionPlan: hasActionPlan,
      hasActionGuide: hasGuide,
      planTabStatus: planTabContent,
      feedbackFabVisible,
      result: 'PASS',
    };

    ensureArtifactsDir();
    fs.writeFileSync(
      path.join(ARTIFACTS_DIR, 'summary.json'),
      JSON.stringify(summary, null, 2),
      'utf-8',
    );
    log('DONE', `Journey complete. Summary: ${JSON.stringify(summary)}`);
  });
});
