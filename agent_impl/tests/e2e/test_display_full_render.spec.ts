import { test, expect } from '@playwright/test';
import { mkdirSync } from 'fs';

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:8000';
const EMAIL = process.env.E2E_USER_EMAIL || 'test200@example.com';
const PASS = process.env.E2E_USER_PASSWORD || '69779346';
const DIR = 'artifacts/display-render';

test.beforeAll(() => mkdirSync(DIR, { recursive: true }));

test('DisplayNode 全链路前端渲染验证', async ({ page }) => {
  test.setTimeout(600_000);

  const consoleErrors: string[] = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', err => consoleErrors.push(`PAGE_ERROR: ${err.message}`));

  // ── Step 0: Login via API + cookie ──
  const loginRes = await page.request.post(`${BASE}/api/auth/login`, {
    data: { email: EMAIL, password: PASS },
  });
  expect(loginRes.ok()).toBeTruthy();
  const { token } = await loginRes.json();
  await page.context().addCookies([{
    name: 'auth_token', value: token, domain: 'localhost', path: '/',
  }]);
  await page.goto(`${BASE}/index.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${DIR}/00_initial.png`, fullPage: true });
  console.log('Step 0: Logged in');

  // ── Step 1: 跳过 onboarding（使用已完成 onboarding 的账号） ──
  console.log('Step 1: Using account with completed onboarding');

  // ── Step 2: 发消息触发 main_agent ──
  console.log('\nStep 2: Sending message to trigger main_agent...');
  const inputEl = page.locator('.chatbar-input').first();
  await expect(inputEl).toBeVisible({ timeout: 15000 });
  await inputEl.fill('帮我做一次感情现状诊断，分析我目前和对方是什么阶段');
  await page.screenshot({ path: `${DIR}/02_message_typed.png` });

  const sendBtn = page.locator('.chatbar-send-btn').first();
  await sendBtn.click();
  console.log('  Message sent, watching for DisplayNode rendering...');

  // ── Step 3: 逐秒监控流式渲染 ──
  let foundReasoning = false;
  let foundToolCall = false;
  let foundInquiry = false;
  let foundReportCard = false;

  for (let i = 1; i <= 40; i++) {
    await page.waitForTimeout(5000);
    const sec = i * 5;
    await page.screenshot({ path: `${DIR}/03_stream_${sec}s.png`, fullPage: true });

    // 获取可见文本内容（非 HTML source）
    const visibleText = await page.evaluate(() => document.body.innerText);

    // 检查 reasoning 卡片（"深度思考"、"AI 正在思考" 等中文文案）
    if (!foundReasoning) {
      const reasoningEl = await page.locator('[class*="deep-think"], [class*="reasoning-card"], .message-reasoning').first().isVisible({ timeout: 200 }).catch(() => false);
      if (reasoningEl || visibleText.includes('深度思考') || visibleText.includes('正在思考')) {
        foundReasoning = true;
        console.log(`  ✅ Reasoning visible at ${sec}s`);
        await page.screenshot({ path: `${DIR}/04_reasoning.png`, fullPage: true });
      }
    }

    // 检查 tool_call 卡片（中文工具名 "分析感情现状" / "制定行动方案" 等）
    if (!foundToolCall) {
      const toolLabels = ['分析感情现状', '制定行动方案', '生成行动指南', '向用户提问', '加载情感档案'];
      const hasToolLabel = toolLabels.some(l => visibleText.includes(l));
      if (hasToolLabel) {
        foundToolCall = true;
        console.log(`  ✅ Tool call card visible at ${sec}s`);
        await page.screenshot({ path: `${DIR}/05_tool_call.png`, fullPage: true });
      }
    }

    // 检查 report_card（"情感罗盘" / "行动蓝图" / "执行中" / "已完成"）
    if (!foundReportCard) {
      if (visibleText.includes('情感罗盘') || visibleText.includes('行动蓝图') || visibleText.includes('行动指南')) {
        foundReportCard = true;
        console.log(`  ✅ Report card visible at ${sec}s`);
        await page.screenshot({ path: `${DIR}/06_report_card.png`, fullPage: true });
      }
    }

    // 检查 inquiry 卡片（问卷问题）
    if (!foundInquiry) {
      if (visibleText.includes('请先回答') || visibleText.includes('问卷')) {
        foundInquiry = true;
        console.log(`  ✅ Inquiry card visible at ${sec}s`);
        await page.screenshot({ path: `${DIR}/07_inquiry.png`, fullPage: true });
      }
      // Also check for inquiry card DOM
      const inquiryCard = await page.locator('[class*="inquiry"], .inquiry-card').first().isVisible({ timeout: 200 }).catch(() => false);
      if (inquiryCard) {
        foundInquiry = true;
        console.log(`  ✅ Inquiry card DOM visible at ${sec}s`);
        await page.screenshot({ path: `${DIR}/07_inquiry.png`, fullPage: true });
      }
    }

    // 检查输入锁定
    const isInputDisabled = await inputEl.isDisabled().catch(() => false);
    if (isInputDisabled && sec <= 15) {
      console.log(`  ✅ Input locked during streaming at ${sec}s`);
    }

    // 检查是否流结束
    if (!isInputDisabled && sec >= 30) {
      console.log(`  Stream completed at ${sec}s`);
      break;
    }
  }

  await page.screenshot({ path: `${DIR}/08_final_state.png`, fullPage: true });

  // ── Step 4: 检查 DisplayStore 状态 ──
  const displayState = await page.evaluate(() => {
    try {
      const app = document.querySelector('#app');
      if (!app || !(app as any).__vue_app__) return { error: 'no vue' };
      const root = (app as any).__vue_app__._instance;
      const ctx = root?.setupState || root?.proxy;
      if (!ctx) return { error: 'no ctx' };
      const result: any = {};
      if (ctx.displayNodeMap) {
        result.displayNodeCount = ctx.displayNodeMap.size;
        result.nodes = [];
        ctx.displayNodeMap.forEach((node: any, key: string) => {
          result.nodes.push({
            nodeId: key,
            nodeType: node.nodeType,
            seq: node.seq,
            status: node.status,
          });
        });
      }
      if (ctx.orderedNodeIds) result.orderedCount = ctx.orderedNodeIds.length;
      if (ctx.streamActive !== undefined) result.streamActive = ctx.streamActive;
      if (ctx.messages) result.messageCount = ctx.messages.length;
      return result;
    } catch (e: any) { return { error: e.message }; }
  });
  console.log('\nStep 4: DisplayStore state:', JSON.stringify(displayState, null, 2));

  // ── Step 5: 刷新验证历史恢复 ──
  console.log('\nStep 5: Refreshing...');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(8000);
  await page.screenshot({ path: `${DIR}/09_after_refresh.png`, fullPage: true });

  const postRefresh = await page.evaluate(() => {
    try {
      const app = document.querySelector('#app');
      if (!app || !(app as any).__vue_app__) return { error: 'no vue' };
      const root = (app as any).__vue_app__._instance;
      const ctx = root?.setupState || root?.proxy;
      if (!ctx) return { error: 'no ctx' };
      const result: any = {};
      if (ctx.displayNodeMap) {
        result.displayNodeCount = ctx.displayNodeMap.size;
        result.nodes = [];
        ctx.displayNodeMap.forEach((node: any, key: string) => {
          result.nodes.push({ nodeId: key, nodeType: node.nodeType, seq: node.seq });
        });
      }
      if (ctx.messages) result.messageCount = ctx.messages.length;
      return result;
    } catch (e: any) { return { error: e.message }; }
  });
  console.log('Post-refresh:', JSON.stringify(postRefresh, null, 2));

  // ── Summary ──
  console.log('\n=== VERIFICATION SUMMARY ===');
  console.log(`Reasoning card: ${foundReasoning ? '✅' : '❌'}`);
  console.log(`Tool call card: ${foundToolCall ? '✅' : '❌'}`);
  console.log(`Report card: ${foundReportCard ? '✅' : '❌'}`);
  console.log(`Inquiry card: ${foundInquiry ? '✅' : '❌'}`);
  console.log(`Console errors: ${consoleErrors.length}`);
  if (consoleErrors.length > 0) {
    consoleErrors.slice(0, 5).forEach(e => console.log(`  ❌ ${e.substring(0, 200)}`));
  }
  console.log(`DisplayNodes: ${displayState.displayNodeCount || 0}`);
  console.log(`Messages before refresh: ${displayState.messageCount || '?'}`);
  console.log(`Messages after refresh: ${postRefresh.messageCount || '?'}`);
});
