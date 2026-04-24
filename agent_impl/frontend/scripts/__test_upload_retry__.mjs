// Node.js test harness for upload retry logic (copied verbatim from onboarding_flow.js).
// Run:  node __test_upload_retry__.mjs

// ─── SUT (from onboarding_flow.js) ───
function fetchWithTimeout(url, options, timeoutMs) {
  const ctrl = new AbortController();
  const opts = Object.assign({}, options, { signal: ctrl.signal });
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  return fetch(url, opts).finally(() => clearTimeout(timer));
}

async function withRetry(fn, { retries = 2, baseDelayMs = 800, onlyRetryIf = () => true } = {}) {
  let lastErr;
  for (let i = 0; i <= retries; i++) {
    try {
      return await fn(i);
    } catch (e) {
      lastErr = e;
      if (i === retries || !onlyRetryIf(e)) break;
      const delay = baseDelayMs * Math.pow(2, i);
      await new Promise(r => setTimeout(r, delay));
    }
  }
  throw lastErr;
}

// Mirror of uploadOnly's error-classification logic
async function uploadOnlyLike(fetchImpl) {
  const origFetch = globalThis.fetch;
  globalThis.fetch = fetchImpl;
  try {
    return await withRetry(async () => {
      let resp;
      try {
        resp = await fetchWithTimeout('/api/upload/upload-only', { method: 'POST' }, 200);
      } catch (e) {
        if (e && e.name === 'AbortError') {
          const err = new Error('上传超时，请重试'); err.retryable = true; throw err;
        }
        const err = new Error('网络异常，请检查后重试'); err.retryable = true; throw err;
      }
      if (!resp.ok) {
        const err = new Error('上传失败: HTTP ' + resp.status);
        err.retryable = resp.status >= 500 || resp.status === 408 || resp.status === 429;
        throw err;
      }
      return await resp.json();
    }, { retries: 2, baseDelayMs: 30, onlyRetryIf: (e) => !!(e && e.retryable) });
  } finally { globalThis.fetch = origFetch; }
}

// ─── Harness ───
let passed = 0, failed = 0;
const lines = [];
function assert(cond, name) {
  if (cond) { passed++; lines.push('✓ ' + name); }
  else       { failed++; lines.push('✗ ' + name); }
}

// ─── Tests ───

async function testTimeoutAborts() {
  const fakeFetch = (url, opts) => new Promise((_r, rej) => {
    opts.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), { name: 'AbortError' })));
  });
  const origFetch = globalThis.fetch;
  globalThis.fetch = fakeFetch;
  try {
    const t0 = Date.now();
    let caught = null;
    try { await fetchWithTimeout('/x', { method: 'POST' }, 150); } catch (e) { caught = e; }
    const dt = Date.now() - t0;
    assert(caught && caught.name === 'AbortError', 'fetchWithTimeout: timeout triggers AbortError');
    assert(dt >= 140 && dt < 400, `fetchWithTimeout: fires ~150ms (dt=${dt})`);
  } finally { globalThis.fetch = origFetch; }
}

async function testFastFetchPasses() {
  const origFetch = globalThis.fetch;
  globalThis.fetch = () => Promise.resolve(new Response('ok', { status: 200 }));
  try {
    const r = await fetchWithTimeout('/x', {}, 500);
    assert(r.ok, 'fetchWithTimeout: fast fetch passes through');
  } finally { globalThis.fetch = origFetch; }
}

async function testWithRetrySuccessOnThird() {
  let n = 0;
  const fn = async () => {
    n++;
    if (n < 3) { const e = new Error('flaky'); e.retryable = true; throw e; }
    return 'ok';
  };
  const t0 = Date.now();
  const r = await withRetry(fn, { retries: 2, baseDelayMs: 50, onlyRetryIf: (e) => !!e.retryable });
  const dt = Date.now() - t0;
  assert(r === 'ok', 'withRetry: succeeds after retries');
  assert(n === 3, `withRetry: called 3 times (n=${n})`);
  assert(dt >= 140, `withRetry: backoff >= 50+100ms (dt=${dt})`);
}

async function testWithRetryGivesUp() {
  let n = 0;
  const fn = async () => { n++; const e = new Error('boom'); e.retryable = true; throw e; };
  let caught = null;
  try { await withRetry(fn, { retries: 2, baseDelayMs: 10, onlyRetryIf: () => true }); } catch (e) { caught = e; }
  assert(caught && caught.message === 'boom', 'withRetry: propagates last error after max retries');
  assert(n === 3, `withRetry: exactly 3 attempts (n=${n})`);
}

async function testWithRetryRespectsPredicate() {
  let n = 0;
  const fn = async () => { n++; const e = new Error('fatal'); e.retryable = false; throw e; };
  let caught = null;
  try { await withRetry(fn, { retries: 2, baseDelayMs: 10, onlyRetryIf: (e) => !!e.retryable }); } catch (e) { caught = e; }
  assert(caught && caught.message === 'fatal', 'withRetry: non-retryable error propagates');
  assert(n === 1, `withRetry: only 1 attempt for non-retryable (n=${n})`);
}

async function testWithRetryImmediateSuccess() {
  let n = 0;
  const fn = async () => { n++; return 'first-try'; };
  const t0 = Date.now();
  const r = await withRetry(fn, { retries: 2, baseDelayMs: 1000 });
  const dt = Date.now() - t0;
  assert(r === 'first-try' && n === 1, 'withRetry: no retry on first success');
  assert(dt < 80, `withRetry: no delay when no retry (dt=${dt})`);
}

// ─── Integration: uploadOnly-like ───

function makeSeqFetch(seq) {
  let i = 0;
  return (url, opts) => {
    const step = seq[i++];
    if (!step) return Promise.reject(new Error('sequence exhausted'));
    if (step === 'timeout') {
      return new Promise((_r, rej) => {
        opts.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), { name: 'AbortError' })));
      });
    }
    const body = JSON.stringify({ url: 'https://cdn/x.png', success: true });
    return Promise.resolve(new Response(body, {
      status: step.status,
      headers: { 'Content-Type': 'application/json' },
    }));
  };
}

async function testUploadOnly_500Then200() {
  const r = await uploadOnlyLike(makeSeqFetch([{status:500}, {status:200}]));
  assert(r && r.url === 'https://cdn/x.png', 'uploadOnly: 500→200 retries and succeeds');
}

async function testUploadOnly_429Then200() {
  const r = await uploadOnlyLike(makeSeqFetch([{status:429}, {status:200}]));
  assert(r && r.url === 'https://cdn/x.png', 'uploadOnly: 429→200 retries and succeeds');
}

async function testUploadOnly_400NoRetry() {
  let caught = null;
  try { await uploadOnlyLike(makeSeqFetch([{status:400}, {status:200}])); } catch (e) { caught = e; }
  assert(caught && /HTTP 400/.test(caught.message), 'uploadOnly: 400 does not retry (client error)');
}

async function testUploadOnly_TimeoutThen200() {
  const r = await uploadOnlyLike(makeSeqFetch(['timeout', {status:200}]));
  assert(r && r.url === 'https://cdn/x.png', 'uploadOnly: timeout→200 retries and succeeds');
}

async function testUploadOnly_ThreeFailures() {
  let caught = null;
  try { await uploadOnlyLike(makeSeqFetch([{status:502}, {status:503}, 'timeout'])); } catch (e) { caught = e; }
  assert(caught && /超时|HTTP/.test(caught.message), `uploadOnly: gives up after 3 failures (msg=${caught && caught.message})`);
}

// ─── Run ───
(async () => {
  await testTimeoutAborts();
  await testFastFetchPasses();
  await testWithRetrySuccessOnThird();
  await testWithRetryGivesUp();
  await testWithRetryRespectsPredicate();
  await testWithRetryImmediateSuccess();
  await testUploadOnly_500Then200();
  await testUploadOnly_429Then200();
  await testUploadOnly_400NoRetry();
  await testUploadOnly_TimeoutThen200();
  await testUploadOnly_ThreeFailures();

  for (const l of lines) console.log(l);
  const total = passed + failed;
  console.log(`\n── summary ──\npassed: ${passed}/${total}\nfailed: ${failed}`);
  process.exit(failed === 0 ? 0 : 1);
})().catch(e => { console.error('UNCAUGHT', e); process.exit(2); });
