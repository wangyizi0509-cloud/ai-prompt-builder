/**
 * Diagnostic script: open localhost:3000, capture console errors/warnings,
 * failed network requests, take a screenshot, and print a summary.
 *
 * Run with:
 *   cd agent_impl/tests/e2e
 *   npx playwright test check_localhost_3000 --reporter=list
 *
 * Screenshot saved to: artifacts/e2e/localhost_3000_check.png
 */

import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

test("diagnose localhost:3000", async ({ page }) => {
  const consoleErrors: string[] = [];
  const consoleWarnings: string[] = [];
  const failedRequests: { url: string; status: number | null }[] = [];

  // Capture console messages
  page.on("console", (msg) => {
    const text = `[${msg.type()}] ${msg.text()}`;
    if (msg.type() === "error") consoleErrors.push(text);
    else if (msg.type() === "warning") consoleWarnings.push(text);
  });

  // Capture uncaught page errors
  page.on("pageerror", (err) => {
    consoleErrors.push(`[pageerror] ${err.message}`);
  });

  // Capture failed network requests
  page.on("requestfailed", (req) => {
    failedRequests.push({ url: req.url(), status: null });
  });

  page.on("response", (res) => {
    if (res.status() >= 400) {
      failedRequests.push({ url: res.url(), status: res.status() });
    }
  });

  // Navigate
  const response = await page.goto("http://localhost:3000", {
    waitUntil: "networkidle",
    timeout: 15000,
  });

  // Screenshot
  const screenshotDir = path.resolve(__dirname, "../../../artifacts/e2e");
  fs.mkdirSync(screenshotDir, { recursive: true });
  const screenshotPath = path.join(screenshotDir, "localhost_3000_check.png");
  await page.screenshot({ path: screenshotPath, fullPage: true });

  // ── Summary ──────────────────────────────────────────────────────────────
  console.log("\n========== DIAGNOSTIC SUMMARY ==========");
  console.log(`Page status : ${response?.status() ?? "N/A"} ${response?.statusText() ?? ""}`);
  console.log(`Screenshot  : ${screenshotPath}`);

  if (consoleErrors.length === 0) {
    console.log("Console errors  : none");
  } else {
    console.log(`\nConsole errors (${consoleErrors.length}):`);
    consoleErrors.forEach((e) => console.log("  •", e));
  }

  if (consoleWarnings.length === 0) {
    console.log("Console warnings: none");
  } else {
    console.log(`\nConsole warnings (${consoleWarnings.length}):`);
    consoleWarnings.forEach((w) => console.log("  •", w));
  }

  if (failedRequests.length === 0) {
    console.log("Failed requests : none");
  } else {
    console.log(`\nFailed requests (${failedRequests.length}):`);
    failedRequests.forEach((r) =>
      console.log(`  • [${r.status ?? "aborted"}] ${r.url}`)
    );
  }

  // Likely issue heuristic
  console.log("\n--- Likely issue ---");
  if (response === null || (response.status() >= 400 && response.status() < 600)) {
    console.log("  Server not responding or returned an error page.");
  } else if (consoleErrors.some((e) => /CORS/i.test(e))) {
    console.log("  CORS policy blocking API calls.");
  } else if (consoleErrors.some((e) => /network|fetch|XHR|api/i.test(e))) {
    console.log("  Network/API request failure — check backend is running.");
  } else if (consoleErrors.some((e) => /undefined|null|TypeError|ReferenceError/i.test(e))) {
    console.log("  JavaScript runtime error — likely a null/undefined access or missing variable.");
  } else if (consoleErrors.some((e) => /chunk|module|import|webpack|vite/i.test(e))) {
    console.log("  Asset loading failure — possible build artefact missing or bad import.");
  } else if (consoleErrors.length > 0) {
    console.log("  Unknown JS error — see console errors above.");
  } else if (consoleWarnings.length > 0) {
    console.log("  No hard errors, but warnings present — may be React prop or deprecation issues.");
  } else {
    console.log("  No errors detected. Page looks clean.");
  }
  console.log("=========================================\n");

  // Don't fail the test; this is a diagnostic, not an assertion
  expect(true).toBe(true);
});
