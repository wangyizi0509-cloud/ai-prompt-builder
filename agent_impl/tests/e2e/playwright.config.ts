import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.ts',
  // 全流程测试（含 LLM 响应）超时设 15 分钟；其他 spec 可在各自 test.setTimeout 内覆盖
  timeout: 900_000,
  expect: {
    timeout: 15_000,
  },
  reporter: [
    ['list'],
    ['html', { outputFolder: '../../../artifacts/e2e/playwright-report', open: 'never' }],
    ['json', { outputFile: '../../../artifacts/e2e/test-results.json' }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:8000',
    // 失败时自动截图（手动截图由测试代码自己管理，存到 artifacts/e2e/full-journey/）
    screenshot: 'only-on-failure',
    // 失败时保留视频和 trace，方便回放
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    // 移动端视口（产品主要在手机上使用）
    viewport: { width: 390, height: 844 },
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        headless: true,
        viewport: { width: 390, height: 844 },
        launchOptions: {
          args: ['--no-sandbox', '--disable-setuid-sandbox'],
        },
      },
    },
  ],
  workers: 1,
});
