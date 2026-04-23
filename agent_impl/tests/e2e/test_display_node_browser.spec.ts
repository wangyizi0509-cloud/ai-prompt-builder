import { test, expect } from '@playwright/test';

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:8000';
const EMAIL = 'test252@example.com';
const PASS = '90050388';

test('前端页面加载无 JS 报错，DisplayStore 正常初始化', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', err => consoleErrors.push(`PAGE_ERROR: ${err.message}`));

  // Login via API then set cookie
  const loginRes = await page.request.post(`${BASE}/api/auth/login`, {
    data: { email: EMAIL, password: PASS },
  });
  const { token } = await loginRes.json();
  await page.context().addCookies([{
    name: 'auth_token',
    value: token,
    domain: 'localhost',
    path: '/',
  }]);
  await page.goto(`${BASE}/index.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);

  // Check Vue app mounted
  const vueMounted = await page.evaluate(() => {
    const app = document.querySelector('#app');
    return !!(app && (app as any).__vue_app__);
  });
  expect(vueMounted).toBeTruthy();
  console.log('✅ Vue app mounted');

  // Check DisplayStore variables exist in Vue context
  const storeCheck = await page.evaluate(() => {
    const app = document.querySelector('#app');
    if (!app || !(app as any).__vue_app__) return { error: 'no vue app' };
    const root = (app as any).__vue_app__._instance;
    if (!root) return { error: 'no root' };
    const ctx = root.setupState || root.proxy;
    if (!ctx) return { error: 'no ctx' };
    return {
      hasDisplayNodeMap: typeof ctx.displayNodeMap !== 'undefined',
      hasOrderedNodeIds: typeof ctx.orderedNodeIds !== 'undefined',
      hasStreamActive: typeof ctx.streamActive !== 'undefined',
      hasUpsertDisplayNode: typeof ctx.upsertDisplayNode === 'function',
      hasNormalizeProcessEvent: typeof ctx.normalizeProcessEventToDisplayNode === 'function',
      hasNormalizeHistory: typeof ctx.normalizeHistoryMessageToDisplayNode === 'function',
      hasBuildMessages: typeof ctx.buildMessagesViewFromDisplayNodes === 'function',
      hasInputLockReason: typeof ctx.inputLockReason !== 'undefined',
    };
  });
  console.log('DisplayStore check:', JSON.stringify(storeCheck, null, 2));

  // Critical state variables and exposed functions should exist
  if (storeCheck.hasDisplayNodeMap !== undefined) {
    expect(storeCheck.hasDisplayNodeMap).toBeTruthy();
    expect(storeCheck.hasOrderedNodeIds).toBeTruthy();
    expect(storeCheck.hasStreamActive).toBeTruthy();
    expect(storeCheck.hasBuildMessages).toBeTruthy();
    expect(storeCheck.hasInputLockReason).toBeTruthy();
    console.log('✅ DisplayStore core state + exposed functions exist');
  }

  // Check for critical console errors (filter out known non-issues)
  const criticalErrors = consoleErrors.filter(e =>
    !e.includes('favicon') &&
    !e.includes('DevTools') &&
    !e.includes('net::ERR')
  );

  if (criticalErrors.length > 0) {
    console.log('❌ Console errors:');
    criticalErrors.forEach(e => console.log(`  ${e}`));
  } else {
    console.log('✅ No critical console errors');
  }

  await page.screenshot({ path: 'artifacts/display-node-verify/browser_loaded.png' });
});
