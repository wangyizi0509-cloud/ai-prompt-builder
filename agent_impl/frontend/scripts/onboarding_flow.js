/*
 * Onboarding v2 · 前端主流程（Splash 衔接的后继 stage）
 *
 * - storage key：`crushe_onboarding_v2`（详见 onboarding_v2/LOCAL_STORAGE_PROTOCOL.md）
 * - 题库 + 钩子：从 <script id="qbank"> 内嵌 JSON 读取
 * - 接口：POST /api/onboarding/analyze、POST /api/upload/upload-screenshot?eval_mode=true
 *
 * 无 Vue / 无 React，纯 DOM + setState 风格的最小状态机。
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'crushe_onboarding_v2';
  const PROTOCOL_VERSION = 1;

  // ───────────────────────────────────────── helpers

  /** 读取 localStorage。返回 null 表示 key 不存在或协议版本不匹配。 */
  function readStore() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.protocol_version !== PROTOCOL_VERSION) {
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
      return parsed;
    } catch (e) {
      console.warn('[onboarding] localStorage parse failed, reset', e);
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
  }

  /** 以 patch 方式合并写回 localStorage。 */
  function writeStore(patch) {
    const current = readStore() || defaultStore();
    const next = Object.assign({}, current, patch);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    return next;
  }

  function defaultStore() {
    return {
      protocol_version: PROTOCOL_VERSION,
      session_id: generateSessionId(),
      stage: 'splash',
      free_text: '',
      uploaded_images: [],
      analysis: null,
      answers: {},
      report: null,
      paid: false,
      paid_at: null,
    };
  }

  function generateSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    // fallback（老浏览器）
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  /** 按 protocol §4.2 的规则把 stage 映射到页面，返回目标 URL；null 表示无需跳转。 */
  function targetPathForStage(stage) {
    switch (stage) {
      case 'splash':
        return '/splash.html';
      case 'free_input':
      case 'questions':
        return '/onboarding.html';
      case 'report':
        return '/report.html';
      case 'paid':
        return '/report.html'; // paid 页本期复用 report.html 的付费闸门
      case 'done':
        return '/index.html';
      default:
        return '/splash.html';
    }
  }

  /** 从内嵌 <script type="application/json"> 加载题库数据。 */
  function loadQuestionBank() {
    const node = document.getElementById('qbank');
    if (!node) {
      throw new Error('题库 <script id="qbank"> 未挂载');
    }
    const raw = node.textContent.trim();
    try {
      return JSON.parse(raw);
    } catch (e) {
      throw new Error('题库 JSON 解析失败: ' + e.message);
    }
  }

  /** 按 A1-A5 顺序返回题号列表。 */
  function orderedQuestionIds() {
    return ['A1', 'A2', 'A3', 'A4', 'A5'];
  }

  /** 每道题的副标题（与 design/shared.jsx 的 QUESTIONS[i].sub 对齐）。 */
  const QUESTION_SUBS = {
    A1: '认识方式决定了后续策略的边界',
    A2: '时间窗口决定策略的紧迫度',
    A3: '可多选 · 行动历史决定当前你的「明牌」程度',
    A4: '可多选 · TA 的负面信号强度分级',
    A5: '锁定目标后我们就能给你匹配最近的策略',
  };

  /** 判断一道题是否 skip（含默认 false）。 */
  function isSkipped(analysis, qid) {
    if (!analysis || !analysis.skip_rules) return false;
    const rule = analysis.skip_rules[qid];
    return !!(rule && rule.skip === true);
  }

  /** 找到「第一道还未回答且未 skip」的题号；没有 → 返回 null。 */
  function findNextQuestion(bankData, store) {
    for (const qid of orderedQuestionIds()) {
      if (!bankData.question_bank[qid]) continue;
      if (isSkipped(store.analysis, qid)) continue;
      const answer = store.answers && store.answers[qid];
      if (answer === undefined || answer === null
          || (Array.isArray(answer) && answer.length === 0)) {
        return qid;
      }
    }
    return null;
  }

  /** 根据 analysis 的 rewrite / preselect 生成一道题的「运行时副本」。 */
  function composeRuntimeQuestion(bankData, qid, analysis) {
    const base = bankData.question_bank[qid];
    if (!base) return null;
    const rule = (analysis && analysis.skip_rules && analysis.skip_rules[qid]) || {};
    const runtime = JSON.parse(JSON.stringify(base));
    if (rule.rewrite) {
      runtime.question = rule.rewrite;
    }
    runtime.preselect = Array.isArray(rule.preselect) ? rule.preselect.slice() : null;
    return runtime;
  }

  /** 解析多选题的钩子（优先 multi_rules，否则按 priority 取 single）。 */
  function resolveHook(bankData, qid, answer) {
    const hooks = bankData.hooks && bankData.hooks[qid];
    if (!hooks) return null;
    const selected = Array.isArray(answer) ? answer : [answer];
    const single = hooks.single || {};

    // 多选组合匹配
    if (Array.isArray(hooks.multi_rules)) {
      for (const rule of hooks.multi_rules) {
        if (!rule || !rule.match) continue;
        if (rule.match.fallback === true) continue; // fallback 最后兜底
        if (matchesMultiRule(rule.match, selected)) {
          return rule.hook;
        }
      }
    }

    // priority 匹配单选项
    if (Array.isArray(hooks.priority)) {
      for (const key of hooks.priority) {
        if (selected.includes(key) && single[key]) {
          return single[key];
        }
      }
    }

    // 其他单选分支（比如 A1/A2）
    if (selected.length === 1 && single[selected[0]]) {
      return single[selected[0]];
    }

    // fallback 兜底
    if (Array.isArray(hooks.multi_rules)) {
      const fb = hooks.multi_rules.find(r => r && r.match && r.match.fallback === true);
      if (fb) return fb.hook;
    }
    return null;
  }

  function matchesMultiRule(match, selected) {
    if (Array.isArray(match.required) && match.required.length) {
      for (const req of match.required) {
        if (!selected.includes(req)) return false;
      }
    }
    if (Array.isArray(match.any_of) && match.any_of.length) {
      const hit = match.any_of.some(k => selected.includes(k));
      if (!hit) return false;
    }
    if (Array.isArray(match.any_of_sets) && match.any_of_sets.length) {
      const hit = match.any_of_sets.some(set =>
        Array.isArray(set) && set.every(k => selected.includes(k))
      );
      if (!hit) return false;
    }
    return true;
  }

  /** 转换钩子 body 里的 **加粗** 语法 → <strong>。 */
  function formatHookBody(text) {
    if (!text) return '';
    // 转 markdown 的 **xxx**
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    return escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  }

  /** 根据 A3/A4 答卷生成 summary 里的 {definition}。 */
  function deriveSummaryDefinition(answers) {
    const a3 = Array.isArray(answers.A3) ? answers.A3 : [];
    const a4 = Array.isArray(answers.A4) ? answers.A4 : [];
    if (a3.includes('A')) {
      return '表白过之后对方开始拉距离，属于「明牌后的回撤」';
    }
    if (a4.includes('D')) {
      return '已经收到过「我们是朋友」之类的暗示，属于「定性拉扯期」';
    }
    if (a4.includes('F')) {
      return '对方把你当成「有用的人」，属于「工具人化」预警';
    }
    if (a3.includes('G') && a4.includes('G')) {
      return '你一直没敢有明显动作，但对方也没有明显拒绝，属于「早期卡点」';
    }
    if (a4.some(k => ['A', 'B', 'C', 'E'].includes(k))) {
      return '对方的冷淡信号开始累积，属于「关系降温前兆」';
    }
    return '属于「需要系统性评估」的常见卡点';
  }

  // ───────────────────────────────────────── upload

  async function uploadScreenshot(file, sessionId) {
    // 合并端点（上传+OCR 一次）—— 保留供别处用；onboarding v2 流程已改走
    // uploadOnly() + ocrOnly() 并行，不再调用这个函数
    const form = new FormData();
    form.append('file', file);
    form.append('screenshot_type', 'screenshot');
    form.append('session_id', sessionId);
    form.append('eval_mode', 'true');
    const resp = await fetch('/api/upload/upload-screenshot?eval_mode=true', {
      method: 'POST',
      body: form,
    });
    if (!resp.ok) {
      throw new Error('上传失败: HTTP ' + resp.status);
    }
    const data = await resp.json();
    return {
      url: data.image_url || '',
      text: data.text || '',
      success: !!data.success,
      error: data.error || null,
    };
  }

  /** 只上传图片，~2s 返回 URL。用于 onboarding v2 并行流水线的第 1 步。 */
  async function uploadOnly(file, sessionId) {
    const form = new FormData();
    form.append('file', file);
    form.append('session_id', sessionId);
    form.append('eval_mode', 'true');
    const resp = await fetch('/api/upload/upload-only', {
      method: 'POST',
      body: form,
    });
    if (!resp.ok) {
      throw new Error('上传失败: HTTP ' + resp.status);
    }
    const data = await resp.json();
    return {
      url: data.url || '',
      path: data.path || '',
      success: !!data.success,
      error: data.error || null,
    };
  }

  /** 只跑 OCR，慢路径（~60-90s）。后台异步调用，结果写回 localStorage。 */
  async function ocrOnly(file, sessionId) {
    const form = new FormData();
    form.append('file', file);
    form.append('screenshot_type', 'screenshot');
    form.append('session_id', sessionId);
    const resp = await fetch('/api/upload/ocr-only', {
      method: 'POST',
      body: form,
    });
    if (!resp.ok) {
      throw new Error('OCR 失败: HTTP ' + resp.status);
    }
    const data = await resp.json();
    return {
      text: data.text || '',
      success: !!data.success,
      error: data.error || null,
    };
  }

  async function submitAnalyze({ sessionId, freeText, imageUrls, ocrTexts }) {
    const resp = await fetch('/api/onboarding/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        free_text: freeText,
        image_urls: imageUrls,
        ocr_texts: ocrTexts,
      }),
    });
    if (resp.status === 422) {
      throw new Error('描述字数不足（后端要求 ≥ 5 字）');
    }
    if (!resp.ok) {
      throw new Error('analyze 失败: HTTP ' + resp.status);
    }
    return await resp.json();
  }

  // ───────────────────────────────────────── app

  function initOnboardingPage() {
    const bankData = loadQuestionBank();
    const store = readStore() || defaultStore();
    writeStore(store); // 确保 key 存在

    // 恢复跳转：若 stage 已经到 report/paid/done，按协议跳走
    const preferred = targetPathForStage(store.stage);
    if (preferred && preferred !== '/onboarding.html' && preferred !== window.location.pathname) {
      window.location.replace(preferred);
      return;
    }

    // 若 stage = splash，说明用户直接进了 onboarding.html，先推进到 free_input
    if (store.stage === 'splash') {
      writeStore({ stage: 'free_input' });
    }

    const state = {
      bank: bankData,
      store: readStore(),
      uploading: 0,             // 正在上传的张数（用于禁用按钮）
      currentQuestionId: null,
      draftAnswer: null,        // 当前题的选中值（单选 string / 多选 array）
      draftFreeInput: {},       // 当前题 option 的自由输入: { optionId: text }
      currentHook: null,        // { hookText, hookImage, nextQid }
      summaryShown: false,
    };

    const els = {
      errorBanner: document.getElementById('error-banner'),
      topbarLabel: document.getElementById('topbar-label'),
      // stage elements
      freeInput: document.getElementById('stage-free-input'),
      openingHook: document.getElementById('stage-opening-hook'),
      question: document.getElementById('stage-question'),
      cardHook: document.getElementById('stage-card-hook'),
      loading: document.getElementById('stage-loading'),
      progress: document.getElementById('progress-wrap'),
      // free input
      descTextarea: document.getElementById('desc-textarea'),
      descCounter: document.getElementById('desc-counter'),
      descCounterStatus: document.getElementById('desc-counter-status'),
      uploadGrid: document.getElementById('upload-grid'),
      uploadCounter: document.getElementById('upload-counter'),
      uploadFileInput: document.getElementById('upload-file-input'),
      submitBtn: document.getElementById('submit-free-input'),
      submitHint: document.getElementById('submit-hint'),
      // opening hook
      openingTag: document.getElementById('opening-hook-tag'),
      openingBody: document.getElementById('opening-hook-body'),
      openingContinue: document.getElementById('opening-continue'),
      // question
      qNum: document.getElementById('q-num'),
      qLabel: document.getElementById('q-label'),
      qText: document.getElementById('q-text'),
      qMultiHint: document.getElementById('q-multi-hint'),
      qOptions: document.getElementById('q-options'),
      qConfirm: document.getElementById('q-confirm'),
      qBackBtn: document.getElementById('q-back'),
      // card hook
      cardHookTag: document.getElementById('card-hook-tag'),
      cardHookQLabel: document.getElementById('card-hook-qlabel'),
      cardHookBody: document.getElementById('card-hook-body'),
      cardHookFeatureWrap: document.getElementById('card-hook-feature-wrap'),
      cardHookFeatureImg: document.getElementById('card-hook-feature-img'),
      cardHookContinue: document.getElementById('card-hook-continue'),
    };

    // ── 功能函数

    function refreshStore() { state.store = readStore() || defaultStore(); }

    function showStage(name) {
      const stages = ['free-input', 'opening-hook', 'question', 'card-hook', 'loading'];
      stages.forEach(s => {
        const el = document.getElementById('stage-' + s);
        if (el) el.classList.toggle('active', s === name);
      });
      // 进度条只在 question/card-hook 显示
      if (els.progress) {
        els.progress.style.display = ['question', 'card-hook'].includes(name) ? 'flex' : 'none';
      }
      // 不同 stage 切换顶栏 eyebrow 文字
      if (els.topbarLabel) {
        const labels = {
          'free-input':  '情感评估 · 开场',
          'opening-hook':'首发诊断 · FIRST READ',
          'question':    '情感评估 · 进行中',
          'card-hook':   '诊断反馈',
          'loading':     '',
        };
        els.topbarLabel.textContent = labels[name] || '情感评估 · 进行中';
      }
    }

    function updateProgress() {
      if (!els.progress) return;
      // 只数未 skip 的题有多少，以及当前答完了几道
      const active = orderedQuestionIds().filter(qid =>
        state.bank.question_bank[qid] && !isSkipped(state.store.analysis, qid)
      );
      const total = active.length || 1;
      const answered = active.filter(qid => {
        const ans = state.store.answers[qid];
        return ans !== undefined && ans !== null && !(Array.isArray(ans) && ans.length === 0);
      }).length;
      els.progress.innerHTML = '';
      for (let i = 0; i < total; i++) {
        const cell = document.createElement('div');
        cell.className = 'progress-cell' + (i < answered ? ' active' : '');
        els.progress.appendChild(cell);
      }
    }

    function showError(msg) {
      if (!els.errorBanner) return;
      els.errorBanner.textContent = msg;
      els.errorBanner.classList.remove('hidden');
      clearTimeout(showError._t);
      showError._t = setTimeout(() => els.errorBanner.classList.add('hidden'), 4500);
    }

    function clearError() {
      if (els.errorBanner) els.errorBanner.classList.add('hidden');
    }

    // ── 阶段 A · 自由描述

    function renderFreeInput() {
      refreshStore();
      if (els.descTextarea && state.store.free_text) {
        els.descTextarea.value = state.store.free_text;
      }
      updateDescCounter();
      renderUploadGrid();
      refreshSubmitBtn();
      showStage('free-input');
    }

    function updateDescCounter() {
      const txt = (els.descTextarea && els.descTextarea.value) || '';
      if (els.descCounter) els.descCounter.textContent = txt.length + ' 字';
      if (els.descCounterStatus) {
        if (txt.trim().length >= 10) {
          els.descCounterStatus.textContent = '✓ 描述已足够';
          els.descCounterStatus.classList.add('ok');
        } else if (txt.trim().length >= 5) {
          els.descCounterStatus.textContent = '✓ 可以提交 · 建议再多说几句';
          els.descCounterStatus.classList.add('ok');
        } else {
          els.descCounterStatus.textContent = '再写 ' + Math.max(0, 5 - txt.trim().length) + ' 字';
          els.descCounterStatus.classList.remove('ok');
        }
      }
    }

    function renderUploadGrid() {
      if (!els.uploadGrid) return;
      els.uploadGrid.innerHTML = '';
      const imgs = state.store.uploaded_images || [];
      if (els.uploadCounter) els.uploadCounter.textContent = '已上传 ' + imgs.length + ' 张 · 建议 2-4 张';
      imgs.forEach((img, idx) => {
        const thumb = document.createElement('div');
        thumb.className = 'upload-thumb';
        if (img.preview_url || img.url) {
          const imgEl = document.createElement('img');
          imgEl.src = img.preview_url || img.url;
          imgEl.alt = 'screenshot';
          imgEl.onerror = () => { imgEl.style.display = 'none'; };
          thumb.appendChild(imgEl);
        }
        if (img.status === 'uploading') {
          const s = document.createElement('div');
          s.className = 'thumb-status';
          s.textContent = '上传中';
          thumb.appendChild(s);
        } else if (img.status === 'failed') {
          const s = document.createElement('div');
          s.className = 'thumb-status';
          s.textContent = '失败';
          thumb.appendChild(s);
        }
        const rm = document.createElement('button');
        rm.className = 'thumb-remove';
        rm.type = 'button';
        rm.textContent = '×';
        rm.addEventListener('click', () => removeImage(idx));
        thumb.appendChild(rm);
        els.uploadGrid.appendChild(thumb);
      });
      if (imgs.length < 6) {
        const slot = document.createElement('button');
        slot.className = 'upload-slot';
        slot.type = 'button';
        slot.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg><span>添加</span>';
        slot.addEventListener('click', () => els.uploadFileInput && els.uploadFileInput.click());
        els.uploadGrid.appendChild(slot);
      }
    }

    function removeImage(idx) {
      const imgs = (state.store.uploaded_images || []).slice();
      imgs.splice(idx, 1);
      state.store = writeStore({ uploaded_images: imgs });
      renderUploadGrid();
      refreshSubmitBtn();
    }

    function refreshSubmitBtn() {
      const text = (els.descTextarea && els.descTextarea.value || '').trim();
      const imgs = state.store.uploaded_images || [];
      // 并行流水线：只要 URL 拿到了（status='ocr-pending' 或 'ready'）就能提交；
      // OCR 状态不阻塞。state.uploading 仅追踪"step1 上传"这一步。
      const usableCount = imgs.filter(
        i => i.status === 'ocr-pending' || i.status === 'ready'
      ).length;
      const uploading = imgs.some(i => i.status === 'uploading');
      const canSubmit =
        text.length >= 5 && usableCount >= 1 && !uploading && state.uploading === 0;
      if (els.submitBtn) {
        els.submitBtn.disabled = !canSubmit;
        els.submitBtn.classList.toggle('disabled', !canSubmit);
        if (canSubmit) {
          els.submitBtn.textContent = '提交 · 开始诊断';
        } else if (uploading) {
          els.submitBtn.textContent = '截图还在上传…';
        } else if (text.length < 5) {
          els.submitBtn.textContent = '请先简单描述一下情况';
        } else {
          els.submitBtn.textContent = '请至少上传 1 张截图';
        }
      }
      if (els.submitHint) {
        if (uploading) {
          els.submitHint.textContent = '截图上传中…';
        } else if (text.length < 5) {
          els.submitHint.textContent = '再描述几句（≥ 5 字）';
        } else if (usableCount < 1) {
          els.submitHint.textContent = '至少上传 1 张聊天截图';
        } else {
          els.submitHint.textContent = '可以提交 · 约 30 秒生成诊断';
        }
      }
    }

    async function handleUpload(files) {
      if (!files || !files.length) return;
      const fileList = Array.from(files).slice(0, 6 - (state.store.uploaded_images || []).length);
      for (const file of fileList) {
        if (!file.type || !file.type.startsWith('image/')) {
          showError('只能上传图片文件');
          continue;
        }
        const preview = URL.createObjectURL(file);
        const placeholder = {
          status: 'uploading',
          preview_url: preview,
          url: '',
          ocr: '',
        };
        const imgs = (state.store.uploaded_images || []).slice();
        imgs.push(placeholder);
        state.store = writeStore({ uploaded_images: imgs });
        state.uploading += 1;
        renderUploadGrid();
        refreshSubmitBtn();

        // Step 1（快，~2s）：上传拿 URL → 立刻解锁提交按钮
        let uploadOk = false;
        try {
          const resp = await uploadOnly(file, state.store.session_id);
          refreshStore();
          const updated = (state.store.uploaded_images || []).slice();
          const idx = updated.findIndex(
            i => i.preview_url === preview && i.status === 'uploading'
          );
          if (idx >= 0) {
            updated[idx] = {
              status: 'ocr-pending',
              preview_url: preview,
              url: resp.url || '',
              ocr: '',
              ocr_failed: false,
            };
            state.store = writeStore({ uploaded_images: updated });
            uploadOk = true;
          }
        } catch (e) {
          refreshStore();
          const updated = (state.store.uploaded_images || []).slice();
          const idx = updated.findIndex(
            i => i.preview_url === preview && i.status === 'uploading'
          );
          if (idx >= 0) {
            updated[idx] = Object.assign({}, updated[idx], { status: 'failed' });
            state.store = writeStore({ uploaded_images: updated });
          }
          showError(e.message || '上传异常');
        } finally {
          state.uploading -= 1;
          renderUploadGrid();
          refreshSubmitBtn();
        }

        // Step 2（慢，~60-90s）：OCR 后台 fire-and-forget，不 await，不阻塞按钮
        if (uploadOk) {
          ocrOnly(file, state.store.session_id)
            .then((resp) => {
              refreshStore();
              const updated = (state.store.uploaded_images || []).slice();
              const idx = updated.findIndex(
                i => i.preview_url === preview && i.status === 'ocr-pending'
              );
              if (idx < 0) return;
              updated[idx] = Object.assign({}, updated[idx], {
                status: 'ready',
                ocr: resp.text || '',
                ocr_failed: !resp.success,
              });
              state.store = writeStore({ uploaded_images: updated });
              renderUploadGrid();
            })
            .catch((e) => {
              refreshStore();
              const updated = (state.store.uploaded_images || []).slice();
              const idx = updated.findIndex(
                i => i.preview_url === preview && i.status === 'ocr-pending'
              );
              if (idx < 0) return;
              updated[idx] = Object.assign({}, updated[idx], {
                status: 'ready',
                ocr: '',
                ocr_failed: true,
                ocr_error: e.message || 'OCR 异常',
              });
              state.store = writeStore({ uploaded_images: updated });
              renderUploadGrid();
              console.warn('[onboarding] OCR 后台失败（不影响主流程）:', e.message);
            });
        }
      }
      if (els.uploadFileInput) els.uploadFileInput.value = '';
    }

    async function handleSubmitFreeInput() {
      clearError();
      const text = (els.descTextarea && els.descTextarea.value || '').trim();
      // 并行流水线：ocr-pending 或 ready 都能用（analyze 不消费 OCR，只看 URL）
      const imgs = (state.store.uploaded_images || []).filter(
        i => i.status === 'ocr-pending' || i.status === 'ready'
      );
      if (text.length < 5 || imgs.length < 1) {
        refreshSubmitBtn();
        return;
      }

      try {
        window.Tracker && window.Tracker.track('description_submit', {
          text_len: text.length,
          image_count: imgs.length,
          ocr_count: imgs.filter(i => i.ocr).length
        });
      } catch (_) {}

      state.store = writeStore({ free_text: text });

      // 锁按钮、显示 loading
      if (els.submitBtn) { els.submitBtn.disabled = true; els.submitBtn.classList.add('disabled'); }
      showStage('loading');

      try {
        // 过滤掉空 URL（eval_mode 下 upload-only 返回 url=""，不应塞给 vision）
        const validImageUrls = imgs.map(i => i.url || '').filter(u => u);
        const analysis = await submitAnalyze({
          sessionId: state.store.session_id,
          freeText: text,
          imageUrls: validImageUrls,
          // analyze 后端已不消费 ocr_texts（直接吃图），这里传空数组即可；
          // OCR 结果由后台 Step 2 写回 localStorage，留给最终 /report 用
          ocrTexts: [],
        });
        state.store = writeStore({ analysis: analysis, stage: 'questions' });
        renderOpeningHook();
      } catch (e) {
        console.error('[onboarding] /analyze failed', e);
        showError(e.message || '诊断服务暂时不可用，请稍后重试');
        showStage('free-input');
        refreshSubmitBtn();
      }
    }

    // ── 阶段 B · 第一个钩子

    /**
     * 按 FirstHook schema 渲染开场钩子：
     *   { verdict_tag, verdict_color, title, body, highlights, evidences, call_to_action }
     *
     * 兼容性：若后端降级成 legacy 字符串（老契约），保留 1-句拆分的旧逻辑当兜底。
     */
    function renderOpeningHook() {
      refreshStore();
      const analysis = state.store.analysis || {};
      const rawHook = analysis.first_hook;
      const hook = _normalizeFirstHook(rawHook);

      // Tag
      if (els.openingTag) {
        els.openingTag.textContent = hook.verdict_tag || '首发诊断';
        // verdict_color 映射到 tag 的 data-tone（CSS 可按需钩取）
        els.openingTag.setAttribute('data-tone', hook.verdict_color || 'violet');
      }

      // Title（支持「」/"" 内容高亮）
      const titleEl = document.getElementById('opening-hook-title');
      if (titleEl) {
        const titleText = (hook.title || '').trim();
        if (titleText) {
          titleEl.innerHTML = _highlightQuotes(titleText);
          titleEl.style.display = 'block';
        } else {
          titleEl.style.display = 'none';
        }
      }

      // Body
      if (els.openingBody) {
        els.openingBody.innerHTML = formatHookBody(hook.body || '');
      }

      // Highlights chips
      const chipsEl = document.getElementById('opening-hook-chips');
      if (chipsEl) {
        const highlights = Array.isArray(hook.highlights) ? hook.highlights.slice(0, 4) : [];
        if (highlights.length) {
          chipsEl.style.display = 'flex';
          chipsEl.innerHTML = highlights.map(h =>
            '<span class="hook-chip">⚠ ' + _escHtml(String(h || '')) + '</span>'
          ).join('');
        } else {
          chipsEl.style.display = 'none';
        }
      }

      // Evidences 列表
      const evWrap = document.getElementById('opening-hook-evidences-wrap');
      const evList = document.getElementById('opening-hook-evidences');
      if (evWrap && evList) {
        const evs = Array.isArray(hook.evidences) ? hook.evidences.filter(e => e && String(e).trim()) : [];
        if (evs.length) {
          evWrap.style.display = 'block';
          evList.innerHTML = evs.map((e, i) =>
            '<div class="hook-evidence-item">' +
              '<div class="hook-evidence-index">#' + (i + 1) + '</div>' +
              '<div class="hook-evidence-text">' + _highlightQuotes(String(e)) + '</div>' +
            '</div>'
          ).join('');
        } else {
          evWrap.style.display = 'none';
        }
      }

      // Call to action（替换静态下一步文案）
      const ctaEl = document.getElementById('opening-hook-cta');
      if (ctaEl && hook.call_to_action && String(hook.call_to_action).trim()) {
        ctaEl.innerHTML = _escHtml(String(hook.call_to_action));
      }
      // 否则保留 HTML 里的静态兜底文案（含粗体）

      updateProgress();
      showStage('opening-hook');
    }

    // —— FirstHook 兼容层：object / 降级 string / 空值 三种情况都能喂出同一个对象 ——
    function _normalizeFirstHook(raw) {
      if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
        return {
          verdict_tag: raw.verdict_tag || '首发诊断',
          verdict_color: raw.verdict_color || 'violet',
          title: raw.title || '',
          body: raw.body || '',
          highlights: Array.isArray(raw.highlights) ? raw.highlights : [],
          evidences: Array.isArray(raw.evidences) ? raw.evidences : [],
          call_to_action: raw.call_to_action || '',
        };
      }
      // 老字符串兜底：1-句拆出 title，余下当 body
      const text = (typeof raw === 'string' && raw.trim())
        ? raw.trim()
        : '我大概了解了你的情况，咱们先通过几个问题把细节说清楚，我再给你看专业的诊断。';
      const m = text.match(/^([^。]+。)\s*(.*)$/s);
      return {
        verdict_tag: '首发诊断',
        verdict_color: 'violet',
        title: m ? m[1].trim() : '',
        body: m ? m[2].trim() : text,
        highlights: [],
        evidences: [],
        call_to_action: '',
      };
    }

    function _escHtml(s) {
      return String(s || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    function _highlightQuotes(s) {
      // 先转义，再把「xxx」/"xxx" 包成 .hl-highlight
      const esc = _escHtml(s);
      return esc.replace(/(「[^」]+」|"[^"]+")/g, '<span class="hl-highlight">$1</span>');
    }

    function handleContinueFromOpening() {
      advanceToNextQuestionOrSummary();
    }

    // ── 阶段 B · 题卡循环

    function advanceToNextQuestionOrSummary() {
      const nextQid = findNextQuestion(state.bank, state.store);
      if (!nextQid) {
        // 正常路径下 A5 由 confirmAnswer 特判直接收尾；走到这里是兜底
        finishOnboardingAndGenerateReport();
        return;
      }
      renderQuestion(nextQid);
    }

    function renderQuestion(qid) {
      state.currentQuestionId = qid;
      const runtime = composeRuntimeQuestion(state.bank, qid, state.store.analysis);
      if (!runtime) {
        advanceToNextQuestionOrSummary();
        return;
      }
      state.draftFreeInput = {};
      // 复现已有 answer / 或 preselect 的初始值
      const existing = state.store.answers[qid];
      if (existing !== undefined) {
        state.draftAnswer = Array.isArray(existing) ? existing.slice() : existing;
      } else if (runtime.preselect && runtime.preselect.length) {
        state.draftAnswer = runtime.allow_multi ? runtime.preselect.slice() : runtime.preselect[0];
      } else {
        state.draftAnswer = runtime.allow_multi ? [] : null;
      }

      // header
      const active = orderedQuestionIds().filter(q =>
        state.bank.question_bank[q] && !isSkipped(state.store.analysis, q)
      );
      const idx = orderedQuestionIds().indexOf(qid);
      const displayIdx = active.indexOf(qid);
      const total = active.length;
      if (els.qNum) els.qNum.textContent = 'Q' + (displayIdx + 1);
      if (els.qLabel) els.qLabel.textContent = 'DIAGNOSTIC QUESTION';
      if (els.qText) els.qText.textContent = runtime.question;
      if (els.topbarLabel) els.topbarLabel.textContent = '情感评估 · Q' + (displayIdx + 1) + ' / ' + total;
      const subEl = document.getElementById('q-sub');
      if (subEl) subEl.textContent = QUESTION_SUBS[qid] || '基于你的自由描述 · AI 已预筛';
      if (els.qMultiHint) {
        els.qMultiHint.style.display = runtime.allow_multi ? 'block' : 'none';
      }
      const singleHintEl = document.getElementById('q-single-hint');
      if (singleHintEl) {
        // 单选未选择前不显示；选中后显示"已选择 · 将自动生成反馈"
        singleHintEl.style.display = (!runtime.allow_multi && state.draftAnswer) ? 'block' : 'none';
      }
      if (els.qConfirm) {
        // A5（最后一题）即便是单选也展示按钮，让用户明确点击"生成完整诊断报告"
        const showConfirm = runtime.allow_multi || runtime.id === 'A5';
        els.qConfirm.style.display = showConfirm ? 'flex' : 'none';
        if (showConfirm) updateConfirmBtn(runtime);
      }
      renderOptions(runtime);
      updateProgress();
      showStage('question');
      // showStage 会覆盖 topbar 文字；此处二次设置为 Q N/total
      if (els.topbarLabel) els.topbarLabel.textContent = '情感评估 · Q' + (displayIdx + 1) + ' / ' + total;
    }

    function renderOptions(runtime) {
      if (!els.qOptions) return;
      els.qOptions.innerHTML = '';
      const isMulti = runtime.allow_multi;
      runtime.options.forEach(opt => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'option';
        const selected = isMulti
          ? Array.isArray(state.draftAnswer) && state.draftAnswer.includes(opt.id)
          : state.draftAnswer === opt.id;
        if (selected) btn.classList.add('selected');
        btn.innerHTML = '<div class="option-marker ' + (isMulti ? 'multi' : 'single') + '">' +
          (selected ? '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"><path d="M20 6L9 17l-5-5"/></svg>' : '') +
          '</div>' +
          '<span class="option-label">' + opt.label + '</span>';
        btn.addEventListener('click', () => onOptionClick(runtime, opt));
        els.qOptions.appendChild(btn);

        if (selected && opt.allow_free_input) {
          const wrap = document.createElement('div');
          wrap.className = 'option-free-input';
          const inp = document.createElement('input');
          inp.type = 'text';
          inp.placeholder = '请补充一下…';
          inp.value = state.draftFreeInput[opt.id] || '';
          inp.addEventListener('input', () => {
            state.draftFreeInput[opt.id] = inp.value;
          });
          wrap.appendChild(inp);
          els.qOptions.appendChild(wrap);
        }
      });

      updateConfirmBtn(runtime);
    }

    function onOptionClick(runtime, opt) {
      const isMulti = runtime.allow_multi;
      if (isMulti) {
        let cur = Array.isArray(state.draftAnswer) ? state.draftAnswer.slice() : [];
        if (opt.is_exclusive) {
          // 点互斥项 → 清空其他只留它（或取消它）
          cur = cur.includes(opt.id) ? [] : [opt.id];
        } else {
          // 先把任何互斥项踢掉
          const exclusives = runtime.options.filter(o => o.is_exclusive).map(o => o.id);
          cur = cur.filter(id => !exclusives.includes(id));
          if (cur.includes(opt.id)) {
            cur = cur.filter(id => id !== opt.id);
          } else {
            cur.push(opt.id);
          }
        }
        state.draftAnswer = cur;
        renderOptions(runtime);
      } else {
        state.draftAnswer = opt.id;
        renderOptions(runtime);
        const singleHintEl = document.getElementById('q-single-hint');
        if (singleHintEl) singleHintEl.style.display = 'block';
        // A5（最后一题 · 目标确认）：展示"提交生成完整诊断报告"按钮，点击才跳；
        // 其它单选题：点完后自动确认，给用户 500ms 反馈窗口
        if (runtime.id === 'A5') {
          updateConfirmBtn(runtime);
        } else {
          setTimeout(() => confirmAnswer(runtime), 500);
        }
      }
    }

    function updateConfirmBtn(runtime) {
      if (!els.qConfirm) return;
      // A5（最后一题 · 单选）：按钮文案 = "提交 · 生成完整诊断报告"
      if (runtime.id === 'A5') {
        const picked = state.draftAnswer != null;
        els.qConfirm.style.display = 'flex';
        els.qConfirm.disabled = !picked;
        els.qConfirm.classList.toggle('disabled', !picked);
        els.qConfirm.textContent = picked ? '提交 · 生成完整诊断报告' : '请先选择一项';
        return;
      }
      if (!runtime.allow_multi) return;
      const n = Array.isArray(state.draftAnswer) ? state.draftAnswer.length : 0;
      const canConfirm = n > 0;
      els.qConfirm.disabled = !canConfirm;
      els.qConfirm.classList.toggle('disabled', !canConfirm);
      els.qConfirm.textContent = canConfirm ? ('确认 · 已选 ' + n + ' 项') : '请至少选择 1 项';
    }

    function confirmAnswer(runtime) {
      const qid = runtime.id;
      const answer = runtime.allow_multi
        ? (Array.isArray(state.draftAnswer) ? state.draftAnswer.slice() : [])
        : state.draftAnswer;
      if (runtime.allow_multi && (!Array.isArray(answer) || answer.length === 0)) return;
      if (!runtime.allow_multi && answer == null) return;

      const nextAnswers = Object.assign({}, state.store.answers || {}, { [qid]: answer });
      state.store = writeStore({ answers: nextAnswers });

      try {
        window.Tracker && window.Tracker.track('question_answer', {
          question_id: qid,
          answer: answer,
          allow_multi: !!runtime.allow_multi
        });
      } catch (_) {}

      // A5（最后一题 · 目标确认）：不走题后钩子、不走总结页，直接进 loading → 跳 report
      if (qid === 'A5') {
        finishOnboardingAndGenerateReport();
        return;
      }

      // 题后钩子
      const hook = resolveHook(state.bank, qid, answer);
      renderCardHook(qid, runtime, hook);
    }

    function finishOnboardingAndGenerateReport() {
      state.store = writeStore({ stage: 'report' });
      updateProgress();
      try {
        const answered = Object.keys(state.store.answers || {}).length;
        window.Tracker && window.Tracker.track('onboarding_complete', {
          answered_count: answered
        });
        window.Tracker && window.Tracker.flush();
      } catch (_) {}
      showStage('loading');

      // 最多等 OCR 后台 60s；超时/完成都跳 report.html
      // report 会从 localStorage 读 uploaded_images[i].ocr（可能部分为空，report 后端容忍）
      const OCR_MAX_WAIT_MS = 60000;
      const POLL_INTERVAL_MS = 500;
      const startTs = Date.now();

      const ocrStillPending = () => {
        refreshStore();
        return (state.store.uploaded_images || []).some(i => i.status === 'ocr-pending');
      };

      const goReport = () => {
        window.location.href = '/report.html';
      };

      if (!ocrStillPending()) {
        // OCR 已全部完成（或全失败），给个短暂过渡显示就跳
        setTimeout(goReport, 800);
        return;
      }

      // 显示转圈等待文案（如果 loading 页有 .loading-sub 元素可改文案）
      const loadingSub = document.querySelector('#stage-loading .loading-sub');
      const originalHtml = loadingSub ? loadingSub.innerHTML : '';
      const updateWaitText = () => {
        if (!loadingSub) return;
        const elapsed = Math.round((Date.now() - startTs) / 1000);
        loadingSub.innerHTML =
          '✓ 正在整理截图（' + elapsed + 's）…<br>' +
          'OCR 完成后立刻生成完整诊断报告';
      };
      updateWaitText();

      const timer = setInterval(() => {
        if (!ocrStillPending()) {
          clearInterval(timer);
          if (loadingSub) loadingSub.innerHTML = originalHtml;
          goReport();
          return;
        }
        if (Date.now() - startTs >= OCR_MAX_WAIT_MS) {
          clearInterval(timer);
          if (loadingSub) loadingSub.innerHTML = originalHtml;
          console.warn('[onboarding] OCR 等待超时，以当前状态进入报告');
          goReport();
          return;
        }
        updateWaitText();
      }, POLL_INTERVAL_MS);
      return;
    }

    // ── 阶段 B · 题后钩子

    function renderCardHook(qid, runtime, hook) {
      refreshStore();
      const active = orderedQuestionIds().filter(q =>
        state.bank.question_bank[q] && !isSkipped(state.store.analysis, q)
      );
      const idx = orderedQuestionIds().indexOf(qid);
      const displayIdx = active.indexOf(qid);
      const total = active.length;
      const remaining = Math.max(0, total - displayIdx - 1);

      const qLabel = 'Q' + (displayIdx + 1) + ' · ' + (runtime.allow_multi ? '组合诊断' : '即时反馈');
      if (els.topbarLabel) els.topbarLabel.textContent = '诊断反馈 · ' + qLabel;

      if (els.cardHookTag) {
        els.cardHookTag.textContent = runtime.allow_multi ? '组合诊断' : '即时反馈';
      }
      // Headline（从 body 首句提取；如无 。 则不显示）
      const headlineEl = document.getElementById('card-hook-headline');
      const bodyText = (hook && hook.text) || '收到。我会把这一条纳入总评估。';
      const m = bodyText.match(/^([^。]+。)\s*(.*)$/s);
      if (headlineEl) {
        if (m && m[1].length < 40) {
          headlineEl.textContent = m[1].trim();
          headlineEl.style.display = 'block';
          els.cardHookBody.innerHTML = formatHookBody(m[2].trim());
        } else {
          headlineEl.style.display = 'none';
          els.cardHookBody.innerHTML = formatHookBody(bodyText);
        }
      }

      // FeaturePreview：image 路径里藏着 feature key（如 .../行动规划.png）
      const featureName = deriveFeatureName(hook && hook.image);
      const featureWrap = document.getElementById('card-hook-feature-wrap');
      const featureNameEl = document.getElementById('card-hook-feature-name');
      const featureBodyEl = document.getElementById('card-hook-feature-body');
      if (featureWrap) {
        if (featureName) {
          featureWrap.style.display = 'block';
          if (featureNameEl) featureNameEl.textContent = featureName;
          if (featureBodyEl) featureBodyEl.innerHTML = renderFeaturePreview(featureName);
        } else {
          featureWrap.style.display = 'none';
        }
      }

      // CTA：最后一题文案不同
      const continueBtn = els.cardHookContinue;
      const remainingEl = document.getElementById('card-hook-remaining');
      if (continueBtn) {
        if (remaining === 0) {
          continueBtn.textContent = '生成完整诊断报告 →';
          if (remainingEl) remainingEl.textContent = '所有问题已完成 · 即将输出专属报告';
        } else {
          continueBtn.textContent = '下一题 →';
          if (remainingEl) remainingEl.textContent = '剩 ' + remaining + ' 题 · 约 ' + (remaining * 15) + ' 秒';
        }
      }

      updateProgress();
      showStage('card-hook');
      if (els.topbarLabel) els.topbarLabel.textContent = '诊断反馈 · ' + qLabel;
    }

    /** 从 image 路径中提取"局势分析/行动规划/聊天指导/行动指南/朋友圈指导"。 */
    function deriveFeatureName(imagePath) {
      if (!imagePath) return null;
      const names = ['局势分析', '行动规划', '聊天指导', '行动指南', '朋友圈指导'];
      for (const n of names) if (imagePath.indexOf(n) >= 0) return n;
      return null;
    }

    /** 渲染 FeaturePreview HTML（对齐 design/page5-card-hook.jsx 的 5 种 Frame）。 */
    function renderFeaturePreview(feature) {
      switch (feature) {
        case '局势分析':
          return [
            '<div class="feature-card">',
            '  <div class="feature-card__head">',
            '    <span class="feature-card__title">📊 局势分析 · 现状快照</span>',
            '    <span class="feature-tag feature-tag--amber">T+3 天</span>',
            '  </div>',
            '  <div>',
            [['吸引力 A', 52, false], ['舒适感 C', 68, false], ['张力 R', 18, true]].map(([k,v,d]) =>
              '<div class="feature-acr__row">' +
                '<span class="feature-acr__label">' + k + '</span>' +
                '<div class="feature-acr__bar-wrap"><div class="feature-acr__bar' + (d?' danger':'') + '" style="width:' + v + '%"></div></div>' +
                '<span class="feature-acr__score" style="color:' + (d?'#C00':'#8A4BFF') + '">' + v + '</span>' +
              '</div>'
            ).join(''),
            '  </div>',
            '  <div class="feature-acr__trend">',
            '    <svg width="40" height="12" viewBox="0 0 40 12"><polyline points="0,4 8,3 16,5 24,7 32,9 40,10" fill="none" stroke="#C00" stroke-width="1.5"/></svg>',
            '    <span>张力持续下滑，预计 2 周内触底</span>',
            '  </div>',
            '</div>'
          ].join('');
        case '行动规划':
          return [
            '<div class="feature-card">',
            '  <div class="feature-card__head">',
            '    <span class="feature-card__title">🧭 行动规划 · 3 阶段</span>',
            '    <span class="feature-tag feature-tag--violet">4 周</span>',
            '  </div>',
            '  <div>',
            [
              { s: 'Phase 1', w: 'W1-2', t: '回撤密度 · 重置节奏', first: true },
              { s: 'Phase 2', w: 'W3',   t: '制造稀缺 · 建立张力', first: false },
              { s: 'Phase 3', w: 'W4',   t: '精准邀约 · 推进关系', first: false },
            ].map(p =>
              '<div class="feature-plan__row ' + (p.first?'first':'rest') + '">' +
                '<span class="feature-plan__stage">' + p.s + '</span>' +
                '<span class="feature-plan__week">' + p.w + '</span>' +
                '<span class="feature-plan__text">' + p.t + '</span>' +
              '</div>'
            ).join(''),
            '  </div>',
            '</div>'
          ].join('');
        case '聊天指导':
          return [
            '<div class="feature-card">',
            '  <div class="feature-card__head">',
            '    <span class="feature-card__title">💬 聊天指导 · 逐条批注</span>',
            '    <span class="feature-tag feature-tag--green">实时</span>',
            '  </div>',
            '  <div class="feature-chat">',
            '    <div class="feature-chat__bubble">最近你都没主动找我玩了 😃</div>',
            '    <div class="feature-chat__note">',
            '      <span class="feature-chat__note-chip">⚠ 试探</span>',
            '      <span>建议：不解释 · 反问回去</span>',
            '    </div>',
            '    <div class="feature-chat__bubble me">是你先不理我的吧？</div>',
            '  </div>',
            '</div>'
          ].join('');
        case '行动指南':
          return [
            '<div class="feature-card">',
            '  <div class="feature-card__head">',
            '    <span class="feature-card__title">🎯 行动指南 · 邀约推演</span>',
            '  </div>',
            '  <div class="feature-action__body">',
            '    <div><b>时机：</b>周三晚 · 对方刚下班</div>',
            '    <div style="margin-top:4px"><b>理由：</b>你偶然聊过的那部电影首映</div>',
            '    <div style="margin-top:4px"><b>话术：</b>"…你不是想看这个吗，周六有场..."</div>',
            '  </div>',
            '  <div class="feature-action__meta">',
            '    <span>成功率预估 72%</span>',
            '    <span>↗ vs 上周 +18%</span>',
            '  </div>',
            '</div>'
          ].join('');
        case '朋友圈指导':
          return [
            '<div class="feature-card">',
            '  <div class="feature-card__head">',
            '    <span class="feature-card__title">📷 朋友圈指导 · 本周建设</span>',
            '    <span class="feature-tag feature-tag--violet">3 条</span>',
            '  </div>',
            '  <div class="feature-moments">',
            '    <div class="feature-moments__cell">📸 周二<br/>晒风景</div>',
            '    <div class="feature-moments__cell">🍳 周五<br/>生活感</div>',
            '    <div class="feature-moments__cell">🎧 周日<br/>品味感</div>',
            '  </div>',
            '</div>'
          ].join('');
        default:
          return '';
      }
    }

    function handleContinueFromCardHook() {
      advanceToNextQuestionOrSummary();
    }

    // ── 初始渲染路由：根据 stage 决定进入哪个子阶段

    function bootStage() {
      refreshStore();
      if (state.store.stage === 'free_input') {
        renderFreeInput();
      } else if (state.store.stage === 'questions') {
        // 有 analysis → 可以恢复
        if (!state.store.analysis) {
          // 丢了 analysis，退回自由描述
          state.store = writeStore({ stage: 'free_input' });
          renderFreeInput();
          return;
        }
        // 如果没答过任何题，先看首发钩子；否则直接进下一题
        const answeredCount = Object.keys(state.store.answers || {}).length;
        if (answeredCount === 0) {
          renderOpeningHook();
        } else {
          advanceToNextQuestionOrSummary();
        }
      } else {
        renderFreeInput();
      }
    }

    // ── 事件绑定

    if (els.descTextarea) {
      let debounce = null;
      els.descTextarea.addEventListener('input', () => {
        updateDescCounter();
        refreshSubmitBtn();
        clearTimeout(debounce);
        debounce = setTimeout(() => {
          refreshStore();
          writeStore({ free_text: els.descTextarea.value });
        }, 500);
      });
    }
    if (els.uploadFileInput) {
      els.uploadFileInput.addEventListener('change', (ev) => {
        handleUpload(ev.target.files);
      });
    }
    if (els.submitBtn) {
      els.submitBtn.addEventListener('click', handleSubmitFreeInput);
    }
    if (els.openingContinue) {
      els.openingContinue.addEventListener('click', handleContinueFromOpening);
    }
    if (els.qConfirm) {
      els.qConfirm.addEventListener('click', () => {
        const qid = state.currentQuestionId;
        if (!qid) return;
        const runtime = composeRuntimeQuestion(state.bank, qid, state.store.analysis);
        confirmAnswer(runtime);
      });
    }
    if (els.qBackBtn) {
      els.qBackBtn.addEventListener('click', () => {
        // 回退到首发钩子，让用户喘口气（不清除已答）
        renderOpeningHook();
      });
    }
    if (els.cardHookContinue) {
      els.cardHookContinue.addEventListener('click', handleContinueFromCardHook);
    }

    bootStage();
  }

  function initSplashPage() {
    const store = readStore();
    if (store && store.stage && store.stage !== 'splash') {
      const target = targetPathForStage(store.stage);
      if (target && target !== window.location.pathname) {
        window.location.replace(target);
        return;
      }
    }
    // 初始化 key（若尚未）
    if (!store) writeStore({ stage: 'splash' });

    const cta = document.getElementById('splash-cta');
    if (cta) {
      cta.addEventListener('click', () => {
        writeStore({ stage: 'free_input' });
        window.location.href = '/onboarding.html';
      });
    }
  }

  // 暴露到 window，供 HTML <script> 直接调用
  window.CrusheOnboarding = {
    initSplashPage: initSplashPage,
    initOnboardingPage: initOnboardingPage,
    // exported for debugging
    _internal: {
      readStore: readStore,
      writeStore: writeStore,
      defaultStore: defaultStore,
      resolveHook: resolveHook,
      composeRuntimeQuestion: composeRuntimeQuestion,
      findNextQuestion: findNextQuestion,
    },
  };
})();
