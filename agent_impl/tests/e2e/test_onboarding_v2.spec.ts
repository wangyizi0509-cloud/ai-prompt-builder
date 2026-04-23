/**
 * E2E · Onboarding v2 销售漏斗完整用户旅程（Agent H · P2 产出）
 *
 * 测试流程（浏览器真实操作）：
 *  1. 打开根路径 → 期望 302 到 /splash.html
 *  2. 点「开始诊断」CTA → 跳 /onboarding.html
 *  3. 填自由描述（含「同事/3 个月/表白」关键词钩子命中文案）
 *  4. 上传真实截图（从 Benchmark 语料里随机取 1 张）
 *  5. 等待 /api/onboarding/analyze 返回 → 看首发钩子
 *  6. 按题循环点选 A1-A5 里未 skip 的题，每题截图
 *  7. 总结页 → 点「生成完整诊断报告」→ /report.html
 *  8. 等待诊断报告渲染（雷达图、状态胶囊、核心问题卡都到齐）
 *  9. 点「立即解锁」→ mock 付费 loading → 自动跳 /index.html
 * 10. 付费后前端自动触发首轮 /api/chat/stream（无需用户输入）
 *     - body.onboarding_payload.{free_text,ocr_texts,answers} 与 localStorage 一致
 *     - body.message === ""（首轮完全由 onboarding_payload 驱动）
 *     - body 中不应再出现 onboarding_summary 字段
 * 11. 断言首条用户可见气泡是 AI 作者（非用户手动发消息）
 *
 * 前置条件（必须在用户本机手动启动）：
 *   cd agent_impl && bash start_dev.sh
 *
 * 运行：
 *   cd agent_impl/tests/e2e
 *   npx playwright test test_onboarding_v2 --reporter=list
 *
 * 环境变量：
 *   E2E_BASE_URL — 默认 http://127.0.0.1:8000
 *   E2E_TEST_FREE_TEXT — 覆盖自由描述（留空走默认）
 *
 * 截图保存位置：artifacts/e2e/onboarding-v2/
 */

import { test, expect, Page, Request } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

// ============================================================
// 常量 & 配置
// ============================================================

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8000';

const DEFAULT_FREE_TEXT =
  '他是我同事，我们认识快 3 个月了。上周我跟他表白了，他说再想想，' +
  '现在回我消息明显变慢了，我想知道还有没有机会重新推进关系。';

const FREE_TEXT = process.env.E2E_TEST_FREE_TEXT || DEFAULT_FREE_TEXT;

const SCREENSHOTS_DIR = path.resolve(
  __dirname,
  '../../../Benchmark/caseBaseDate/用户发送的截图',
);
const ARTIFACTS_DIR = path.resolve(__dirname, '../../../artifacts/e2e/onboarding-v2');

const ANALYZE_TIMEOUT = 150_000;         // /api/onboarding/analyze 真实 vision LLM 实测 45-90s
const REPORT_TIMEOUT = 150_000;          // /api/onboarding/report LLM 最多 35s × 2 重试
const CHAT_FIRST_TURN_TIMEOUT = 120_000; // main_agent 首轮响应较慢
const UI_TIMEOUT = 15_000;

// ============================================================
// 辅助
// ============================================================

let stepCounter = 0;

function ensureArtifactsDir() {
  fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });
}

async function screenshot(page: Page, label: string): Promise<string> {
  ensureArtifactsDir();
  stepCounter += 1;
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

/** 从 Benchmark 截图目录随机选一张 jpg/png */
function pickRandomScreenshot(): string {
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    throw new Error(`截图目录不存在: ${SCREENSHOTS_DIR}`);
  }
  const files = fs
    .readdirSync(SCREENSHOTS_DIR)
    .filter((f) => /\.(jpg|jpeg|png)$/i.test(f));
  if (files.length === 0) {
    throw new Error(`截图目录为空: ${SCREENSHOTS_DIR}`);
  }
  const picked = files[Math.floor(Math.random() * files.length)];
  return path.join(SCREENSHOTS_DIR, picked);
}

/** 把当前 localStorage 读回到测试上下文（调试/断言用） */
async function dumpLocalStore(page: Page): Promise<Record<string, unknown> | null> {
  return page.evaluate(() => {
    const raw = localStorage.getItem('crushe_onboarding_v2');
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  });
}

/** 清空所有 onboarding localStorage（避免上一次 e2e 污染） */
async function clearStore(page: Page): Promise<void> {
  await page.evaluate(() => {
    try {
      localStorage.removeItem('crushe_onboarding_v2');
    } catch {
      /* ignore */
    }
  });
}

// ============================================================
// 主测试
// ============================================================

test.describe('Onboarding v2 · 销售漏斗 E2E', () => {
  test.setTimeout(900_000); // 完整流程 5-15 分钟

  test('splash → 描述+截图 → 题库 → 报告 → mock 付费 → 主聊天自动触发首轮 onboarding_payload', async ({
    page,
  }) => {
    ensureArtifactsDir();
    stepCounter = 0;

    // ────────────────────────────────────────────────────────────────
    // Phase 0: 清洁起步 —— 清掉可能残留的 localStorage，避免命中 I 的守卫
    // ────────────────────────────────────────────────────────────────
    // 先访问一次域名才有 localStorage 权限
    await page.goto(`${BASE_URL}/splash.html`);
    await clearStore(page);

    // ────────────────────────────────────────────────────────────────
    // Phase 1: 根路径 302 到 splash
    // ────────────────────────────────────────────────────────────────
    log('SPLASH', `visiting ${BASE_URL}/`);
    await page.goto(`${BASE_URL}/`);
    await expect(page).toHaveURL(/splash\.html$/, { timeout: UI_TIMEOUT });
    // 页面标题/CTA 存在
    const cta = page.locator('#splash-cta');
    await expect(cta).toBeVisible({ timeout: UI_TIMEOUT });
    await screenshot(page, 'splash');

    // ────────────────────────────────────────────────────────────────
    // Phase 2: 点「开始诊断」跳 /onboarding.html
    // ────────────────────────────────────────────────────────────────
    await cta.click();
    await page.waitForURL(/onboarding\.html$/, { timeout: UI_TIMEOUT });
    log('ONBOARDING', 'arrived at /onboarding.html');

    // ────────────────────────────────────────────────────────────────
    // Phase 3: 填自由描述
    // ────────────────────────────────────────────────────────────────
    const descTextarea = page.locator('#desc-textarea');
    await expect(descTextarea).toBeVisible({ timeout: UI_TIMEOUT });
    await descTextarea.fill(FREE_TEXT);
    log('FREE_INPUT', `filled free text (${FREE_TEXT.length} chars)`);

    // ────────────────────────────────────────────────────────────────
    // Phase 4: 上传 1 张截图（从 Benchmark 目录随机取）
    // ────────────────────────────────────────────────────────────────
    const screenshotPath = pickRandomScreenshot();
    log('UPLOAD', `picked screenshot: ${path.basename(screenshotPath)}`);
    const fileInput = page.locator('#upload-file-input');
    await fileInput.setInputFiles(screenshotPath);

    // 等待至少 1 张截图处于 ready（提交按钮被解锁）
    const submitBtn = page.locator('#submit-free-input');
    await expect(submitBtn).toBeEnabled({ timeout: 60_000 });
    await screenshot(page, 'free_input_filled');

    // ────────────────────────────────────────────────────────────────
    // Phase 5: 点提交 → 等 /api/onboarding/analyze 返回
    // ────────────────────────────────────────────────────────────────
    const analyzeRespPromise = page.waitForResponse(
      (r) =>
        r.url().includes('/api/onboarding/analyze') && r.request().method() === 'POST',
      { timeout: ANALYZE_TIMEOUT },
    );
    await submitBtn.click();
    const analyzeResp = await analyzeRespPromise;
    expect(analyzeResp.ok(), 'analyze 接口应 200').toBeTruthy();

    // 首发钩子（opening-hook stage）
    await expect(page.locator('#stage-opening-hook.active')).toBeVisible({
      timeout: 10_000,
    });
    const openingHookText = await page.locator('#opening-hook-body').innerText();
    expect(openingHookText.trim().length, 'first_hook 文案不应为空').toBeGreaterThan(0);
    log('OPENING_HOOK', `hook text len=${openingHookText.length}`);
    await screenshot(page, 'first_hook');

    // 点「继续」进入第一道题
    await page.locator('#opening-continue').click();

    // ────────────────────────────────────────────────────────────────
    // Phase 6: 题库循环 —— 最多 A1-A5 五道题，未 skip 的逐个点选
    // ────────────────────────────────────────────────────────────────
    let questionsAnswered = 0;
    const MAX_QUESTIONS = 5;
    for (let i = 0; i < MAX_QUESTIONS; i++) {
      // 循环终点有两种：进入 closing stage 或意外跳转
      // question stage 未激活 → 说明已经走到总结页或报告页
      const questionStage = page.locator('#stage-question.active');
      const closingStage = page.locator('#stage-closing.active');

      // 先等 0.5s 给状态机一点切换时间
      await page.waitForTimeout(500);

      const onClosing = await closingStage.isVisible().catch(() => false);
      if (onClosing) {
        log('QUESTIONS', `reached closing stage after ${questionsAnswered} questions`);
        break;
      }

      const onQuestion = await questionStage.isVisible().catch(() => false);
      if (!onQuestion) {
        // 可能还在 card-hook → 点「下一题」继续
        const cardHookContinue = page.locator('#card-hook-continue');
        if (await cardHookContinue.isVisible({ timeout: 1500 }).catch(() => false)) {
          await cardHookContinue.click();
          continue;
        }
        // 不在题卡也不在钩子，可能已到 closing；下一轮再判断
        continue;
      }

      // 在题卡上
      const qNumText = await page.locator('#q-num').innerText();
      const qText = await page.locator('#q-text').innerText();
      log('QUESTION', `${qNumText}: ${qText.slice(0, 40)}`);

      // 选项点击策略:找第一个「未被 preselect 选中」的选项再 click
      // 如果所有选项都已被选中(罕见),就强制 click 一次再 click 回来,保证留下至少 1 项
      // 这样避免"点到已 preselect 的首项 → 多选题逻辑把它取消 → draftAnswer 为空"
      const optionButtons = page.locator('#q-options > button.option');
      const optCount = await optionButtons.count();
      let clicked = false;
      for (let oi = 0; oi < optCount; oi++) {
        const optBtn = optionButtons.nth(oi);
        const isSelected = await optBtn.evaluate((el) => el.classList.contains('selected'));
        if (!isSelected) {
          await optBtn.click();
          clicked = true;
          break;
        }
      }
      if (!clicked && optCount > 0) {
        // 所有选项都已 preselect:任意点一次保留当前形态即可
        // (多选题点已选项会取消它,再点一次复原;这里简化为点第一个两次)
        const first = optionButtons.first();
        await first.click();
        await first.click();
      }

      // 多选题会显示确认按钮（#q-confirm），单选题会自动推进
      const confirmBtn = page.locator('#q-confirm');
      const confirmVisible = await confirmBtn.isVisible({ timeout: 1500 }).catch(
        () => false,
      );
      if (confirmVisible) {
        // 等按钮从 disabled 变 enabled
        await expect(confirmBtn).toBeEnabled({ timeout: UI_TIMEOUT });
        await confirmBtn.click();
      }

      // 题后状态:A5(最后一题 · 单选)直接进 loading → 跳 report.html,不走 card-hook
      // 其它题(多选 A1-A4)必出现题后钩子
      await page.waitForTimeout(800);
      const onCardHook = await page.locator('#stage-card-hook.active').isVisible().catch(() => false);
      const onLoadingOrReport = await page.locator('#stage-loading.active').isVisible().catch(() => false)
        || page.url().includes('report.html');

      if (onCardHook) {
        // 钩子可能渲染成 headline + body 两部分,只要任一非空就算有内容
        const hookBody = await page.locator('#card-hook-body').innerText().catch(() => '');
        const hookHead = await page.locator('#card-hook-headline').innerText().catch(() => '');
        expect(
          (hookBody.trim().length + hookHead.trim().length),
          `Q${i + 1} 题后钩子(headline + body)不应同时为空`,
        ).toBeGreaterThan(0);
        questionsAnswered += 1;
        await screenshot(page, `q${questionsAnswered}_hook`);
        await page.locator('#card-hook-continue').click();
      } else if (onLoadingOrReport) {
        questionsAnswered += 1;
        log('QUESTIONS', `A5 answered, skipping card-hook, flowing into loading/report`);
        await screenshot(page, `q${questionsAnswered}_final_submit`);
        break;
      } else {
        // 异常:既不在钩子也不在 loading/report
        await screenshot(page, `q${i + 1}_unexpected_stage`);
        throw new Error(`Q${i + 1} 答题后既未出现 card-hook 也未进入 loading/report`);
      }
    }

    // ────────────────────────────────────────────────────────────────
    // Phase 7: 等 /api/onboarding/report 返回 + URL 跳到 /report.html
    // ────────────────────────────────────────────────────────────────
    const reportRespPromise = page.waitForResponse(
      (r) =>
        r.url().includes('/api/onboarding/report') && r.request().method() === 'POST',
      { timeout: REPORT_TIMEOUT },
    );
    await page.waitForURL(/report\.html$/, { timeout: UI_TIMEOUT });

    // 等 /api/onboarding/report 返回
    const reportResp = await reportRespPromise;
    expect(reportResp.ok(), 'report 接口应 200').toBeTruthy();

    // 报告主视图三个关键区块(v2.1 新版样式)
    await expect(page.locator('.rp-hero-pill').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('.rp-hero-acr-radar').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('.rp-problem-card').first()).toBeVisible({ timeout: 10_000 });
    // core_issues 至少 2 条（schema 约束 2-3）
    const problemCount = await page.locator('.rp-problem-card').count();
    expect(problemCount, 'core_issues 至少 2 条').toBeGreaterThanOrEqual(2);

    log('REPORT', `problem cards rendered=${problemCount}`);
    await screenshot(page, 'report_rendered');

    // 收藏 localStorage 里的 onboarding 原始素材 + collected_summary，供后续断言
    const storeAfterReport = await dumpLocalStore(page);
    const reportBlock =
      (storeAfterReport && (storeAfterReport.report as Record<string, unknown>)) || {};
    const collectedSummary = (reportBlock.collected_summary as string) || '';
    expect(
      typeof collectedSummary === 'string' && collectedSummary.length >= 10,
      'collected_summary 应该被 Agent C 返回且写入 localStorage（/api/onboarding/report 保留该字段）',
    ).toBeTruthy();

    // 同时拿到原始 payload 素材,首轮 body 应与之一致。
    // 注意:localStorage 里 OCR 原始字段是 uploaded_images[i].ocr,
    // 前端 helper 会把它重组成 [{ocr_result, ocr_failed}]。
    const storedFreeText = (storeAfterReport?.free_text as string) || '';
    const storedUploadedImages = Array.isArray(storeAfterReport?.uploaded_images)
      ? (storeAfterReport!.uploaded_images as Array<Record<string, unknown>>)
      : [];
    const storedAnswers = (storeAfterReport?.answers as Record<string, unknown>) || {};
    log(
      'STORE',
      `storedFreeText.len=${storedFreeText.length} uploaded_images=${storedUploadedImages.length} answers=${Object.keys(storedAnswers).length}`,
    );

    // ────────────────────────────────────────────────────────────────
    // Phase 8: 监听下一次 /api/chat/stream POST（在点付费前就挂监听，
    //          因为 index.html 载入后会自动触发首轮，不会给我们留点按钮的机会）
    // ────────────────────────────────────────────────────────────────
    const chatBodyPromise: Promise<Record<string, unknown>> = new Promise((resolve) => {
      const handler = (req: Request) => {
        if (
          req.method() === 'POST' &&
          (req.url().includes('/api/chat/stream') || req.url().endsWith('/api/chat'))
        ) {
          try {
            const raw = req.postData() || '{}';
            const parsed = JSON.parse(raw);
            page.off('request', handler);
            resolve(parsed);
          } catch {
            /* 若 JSON 解析失败就跳过这个 request，继续等下一个 */
          }
        }
      };
      page.on('request', handler);
    });

    // ────────────────────────────────────────────────────────────────
    // Phase 9: 点「立即解锁」→ mock 付费 → 跳 /index.html → 前端自动触发首轮
    // ────────────────────────────────────────────────────────────────
    const unlockBtn = page.locator('#rp-unlock-btn');
    await expect(unlockBtn).toBeVisible({ timeout: UI_TIMEOUT });
    await unlockBtn.click();
    log('PAY', 'clicked 立即解锁');

    await page.waitForURL(/index\.html$|\/$/, { timeout: 15_000 });
    await page.waitForSelector('#app', { timeout: 20_000 });
    await screenshot(page, 'index_after_paid');

    // ────────────────────────────────────────────────────────────────
    // Phase 10: 断言自动触发的首轮 body：
    //   - onboarding_payload.{free_text, ocr_texts, answers} 与 localStorage 一致
    //   - body.message === ""（无用户输入）
    //   - 不应存在旧字段 onboarding_summary
    // ────────────────────────────────────────────────────────────────
    const chatBody = await Promise.race([
      chatBodyPromise,
      new Promise<null>((resolve) =>
        setTimeout(() => resolve(null), CHAT_FIRST_TURN_TIMEOUT),
      ),
    ]);
    expect(chatBody, '应捕获到首轮 /api/chat 或 /api/chat/stream 请求 body').not.toBeNull();

    const body = chatBody as Record<string, unknown>;

    // 旧字段必须彻底消失
    expect(
      Object.prototype.hasOwnProperty.call(body, 'onboarding_summary'),
      'onboarding_summary 字段已下线，首轮 body 不应再携带',
    ).toBeFalsy();

    // 首轮 message 必须为空（没有用户输入，完全由 payload 驱动）
    expect(body.message ?? '', '首轮 body.message 应为空串').toBe('');

    // onboarding_payload 必须存在且结构正确
    const payload = body.onboarding_payload as Record<string, unknown> | undefined;
    expect(payload, '首轮 body 必须携带 onboarding_payload').toBeTruthy();
    expect(typeof payload!.free_text, 'payload.free_text 应为 string').toBe('string');
    expect(Array.isArray(payload!.ocr_texts), 'payload.ocr_texts 应为数组').toBeTruthy();
    expect(
      payload!.answers && typeof payload!.answers === 'object' && !Array.isArray(payload!.answers),
      'payload.answers 应为 object',
    ).toBeTruthy();

    // payload 内容应与 localStorage 存储值一致
    expect(payload!.free_text, 'payload.free_text 应与 localStorage 一致').toBe(storedFreeText);
    expect(
      (payload!.ocr_texts as unknown[]).length,
      'payload.ocr_texts 长度应与 localStorage.uploaded_images 一致',
    ).toBe(storedUploadedImages.length);
    expect(
      Object.keys(payload!.answers as Record<string, unknown>).sort(),
      'payload.answers 键集合应与 localStorage 一致',
    ).toEqual(Object.keys(storedAnswers).sort());

    log(
      'CHAT_BODY',
      `first-turn payload ok: free_text.len=${(payload!.free_text as string).length} ocr=${(payload!.ocr_texts as unknown[]).length} answers=${Object.keys(payload!.answers as Record<string, unknown>).length}`,
    );

    // ────────────────────────────────────────────────────────────────
    // Phase 11: 首条用户可见气泡应是 AI（无人输入，AI 自己先开口）
    // ────────────────────────────────────────────────────────────────
    const aiBubble = page.locator('.chat-bubble-ai');
    await expect(aiBubble.first()).toBeVisible({ timeout: CHAT_FIRST_TURN_TIMEOUT });
    // 给流式回复收尾一点时间
    await page.waitForTimeout(3_000);
    const aiMsgCount = await aiBubble.count();
    const userBubbleCount = await page.locator('.chat-bubble-user').count().catch(() => 0);
    log('AI_REPLY', `AI=${aiMsgCount} user=${userBubbleCount}`);
    expect(aiMsgCount, 'AI 应至少产出 1 条回复').toBeGreaterThanOrEqual(1);
    expect(userBubbleCount, '首轮应无用户手动输入的气泡').toBe(0);

    await screenshot(page, 'main_chat_ai_replied');

    // ────────────────────────────────────────────────────────────────
    // Phase 12: 生成摘要
    // ────────────────────────────────────────────────────────────────
    const summaryJson = {
      timestamp: new Date().toISOString(),
      baseUrl: BASE_URL,
      freeTextUsed: FREE_TEXT,
      questionsAnswered,
      problemCardCount: problemCount,
      payloadFreeTextLen: (payload!.free_text as string).length,
      payloadOcrCount: (payload!.ocr_texts as unknown[]).length,
      payloadAnswerCount: Object.keys(payload!.answers as Record<string, unknown>).length,
      aiMessageCount: aiMsgCount,
      userBubbleCount,
      result: 'PASS',
    };
    fs.writeFileSync(
      path.join(ARTIFACTS_DIR, 'summary.json'),
      JSON.stringify(summaryJson, null, 2),
      'utf-8',
    );
    log('DONE', `Onboarding v2 journey complete: ${JSON.stringify(summaryJson)}`);
  });
});
