/**
 * Onboarding v2 · 报告页 + 付费闸门
 * 归属：Agent F
 * 版本：V2_DarkHero（深色 hero band 风格，对齐 prototype.html 指定版本）
 *
 * 职责：
 *  1. 读取 localStorage 里的 onboarding 进度，渲染诊断报告
 *  2. 如 localStorage 没有 report 但有必要字段 → 调 /api/onboarding/report 获取
 *  3. 渲染 V2 结构：深色 hero band / 玻璃态 hero 卡 / 问题列表 / 编号锁住表 / 信任横条 / 深色付费卡
 *  4. mock 支付：弹 loading 1s → localStorage 写 paid=true, stage='paid' → 跳 /index.html
 *
 * 契约参考：
 *  - onboarding_v2/schemas.py::DiagnosisReport
 *  - onboarding_v2/LOCAL_STORAGE_PROTOCOL.md
 *  - onboarding_v2/API_CONTRACT.md §3
 */

(function () {
  'use strict';

  // ───────────────────────────────────────────────────────
  // 常量
  // ───────────────────────────────────────────────────────

  var STORAGE_KEY = 'crushe_onboarding_v2';
  var PROTOCOL_VERSION = 1;
  var REPORT_ENDPOINT = '/api/onboarding/report';
  // DeepSeek v3.2 thinking + tool_call 的典型延迟 60-90s，设 150s 足够
  var REPORT_TIMEOUT_MS = 150000;

  // 5 维 key 中文标签（schemas.py: A/C/R/T/E）
  var SCORE_LABELS = {
    A: '吸引力',
    C: '舒适感',
    R: '张力',
    T: '信任度',
    E: '回应度',
  };

  // 状态标签配色：对应 schemas.py StateLabel.severity 的 5 个枚举
  var SEVERITY_STYLES = {
    danger:      { bg: '#FFE6E6', color: '#C00000' },
    warning:     { bg: '#FFEDE0', color: '#D85400' },
    opportunity: { bg: '#E6F7EB', color: '#1E8C3A' },
    neutral:     { bg: '#F0EBFA', color: '#6B3FB0' },
    observation: { bg: '#E8F1FF', color: '#0B5EFE' },
  };

  // 状态标签中文 → 副标题文案（6 选一；对齐 schemas.py StateLabel.name）
  var STATE_TITLES = {
    '高危滑坡期': '你处于「高危滑坡期」的阶段',
    '舒适区陷阱': '你处于「舒适区陷阱」的阶段',
    '临门犹豫期': '你处于「临门犹豫期」的阶段',
    '信号过载期': '你处于「信号过载期」的阶段',
    '空白探索期': '你处于「空白探索期」的阶段',
    '僵局观察期': '你处于「僵局观察期」的阶段',
  };

  // 3 个能力模块（固定展示顺序）：按 schemas.py.LockedTeaser.section 的字面匹配
  var CAPABILITY_SECTIONS = [
    {
      id: 'analysis',
      no: '01',
      title: '完整局势分析',
      matchKeywords: ['局势分析', '局势', '对方心理', '走势', '阻力'],
      fallback: ['对方心理画像', '关系走势预测', '核心阻力深度拆解'],
    },
    {
      id: 'plan',
      no: '02',
      title: '专属行动规划',
      matchKeywords: ['行动规划', '规划', 'Phase', '里程碑', '阶段'],
      fallback: ['Phase 1 · 节奏重置', 'Phase 2 · 张力建立', '关键里程碑清单'],
    },
    {
      id: 'guide',
      no: '03',
      title: '即时行动指南',
      matchKeywords: ['行动指南', '指南', '下一条', '聊天', '朋友圈', '见面'],
      fallback: ['下一条消息怎么发', '本周朋友圈建设方案', '下次见面策略推演'],
    },
  ];

  // ───────────────────────────────────────────────────────
  // localStorage 工具
  // ───────────────────────────────────────────────────────

  function loadStore() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var data = JSON.parse(raw);
      if (!data || data.protocol_version !== PROTOCOL_VERSION) return null;
      return data;
    } catch (e) {
      return null;
    }
  }

  function saveStore(data) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (e) {
      // ignore quota errors; degrade gracefully
    }
  }

  function patchStore(patch) {
    var cur = loadStore() || {
      protocol_version: PROTOCOL_VERSION,
      session_id: generateSessionId(),
      stage: 'report',
      free_text: '',
      uploaded_images: [],
      analysis: null,
      answers: {},
      report: null,
      paid: false,
      paid_at: null,
    };
    for (var k in patch) {
      if (Object.prototype.hasOwnProperty.call(patch, k)) {
        cur[k] = patch[k];
      }
    }
    saveStore(cur);
    return cur;
  }

  function generateSessionId() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID();
    }
    // fallback
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  // session_id 取后 6 位作为 CR-xxxxxx 编号
  function getReportId() {
    var store = loadStore();
    var sid = (store && store.session_id) || '';
    var hash = sid.replace(/-/g, '').slice(-6).toUpperCase();
    return 'CR-' + (hash || '428103');
  }

  // ───────────────────────────────────────────────────────
  // 入口
  // ───────────────────────────────────────────────────────

  function init() {
    var store = loadStore();

    // 已付费 → 直接去主对话
    if (store && store.paid === true) {
      window.location.replace('/index.html');
      return;
    }
    if (store && store.stage === 'paid') {
      // 走到这一步说明发生过 mock 支付中断，按已付处理
      store.paid = true;
      store.paid_at = store.paid_at || new Date().toISOString();
      store.stage = 'done';
      saveStore(store);
      window.location.replace('/index.html');
      return;
    }

    // 已有本地 report → 直接渲染
    if (store && store.report) {
      renderReport(store.report);
      return;
    }

    // 没报告也没问答数据 → 提示没有数据
    if (!store || (!store.free_text && (!store.ocr_texts || !store.ocr_texts.length) &&
                   (!store.answers || Object.keys(store.answers).length === 0))) {
      renderEmptyState();
      return;
    }

    // 有问答数据但没报告 → 调 /report
    fetchReport(store);
  }

  // ───────────────────────────────────────────────────────
  // 拉取 report
  // ───────────────────────────────────────────────────────

  function fetchReport(store) {
    renderLoading('正在深度分析你的情况…', '深度诊断模式运行中，通常 1-2 分钟，请稍候');

    var body = buildReportRequest(store);

    var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var timer = setTimeout(function () {
      if (ctrl) ctrl.abort();
    }, REPORT_TIMEOUT_MS);

    var fetchOpts = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    };
    if (ctrl) fetchOpts.signal = ctrl.signal;

    fetch(REPORT_ENDPOINT, fetchOpts)
      .then(function (resp) {
        clearTimeout(timer);
        if (!resp.ok) {
          return resp.text().then(function (text) {
            throw new Error('report_http_' + resp.status + (text ? (': ' + text.slice(0, 160)) : ''));
          });
        }
        return resp.json();
      })
      .then(function (report) {
        patchStore({ report: report, stage: 'report' });
        renderReport(report);
      })
      .catch(function (err) {
        clearTimeout(timer);
        renderError(err);
      });
  }

  function buildReportRequest(store) {
    var ocr = [];
    if (Array.isArray(store.ocr_texts)) {
      ocr = store.ocr_texts.slice();
    } else if (Array.isArray(store.uploaded_images)) {
      ocr = store.uploaded_images.map(function (i) { return (i && i.ocr) || ''; });
    }
    return {
      session_id: store.session_id || generateSessionId(),
      free_text: store.free_text || '',
      ocr_texts: ocr,
      answers: store.answers || {},
    };
  }

  // ───────────────────────────────────────────────────────
  // 渲染：loading / error / 空状态
  // ───────────────────────────────────────────────────────

  function renderLoading(title, desc) {
    var root = document.getElementById('rp-root');
    root.innerHTML = [
      '<div class="rp-splash-state" role="status" aria-live="polite">',
      '  <div class="rp-spinner" aria-hidden="true"></div>',
      '  <div class="rp-splash-state-title">' + escapeHtml(title || '加载中…') + '</div>',
      '  <div class="rp-splash-state-desc">' + escapeHtml(desc || '') + '</div>',
      '</div>',
    ].join('');
  }

  function renderError(err) {
    var root = document.getElementById('rp-root');
    var msg = '诊断报告生成失败，可能是网络抖动。请重试一次，通常就好。';
    if (err && err.message && err.message.indexOf('report_http_422') === 0) {
      msg = '问答数据不完整，请回到上一步确认。';
    }
    root.innerHTML = [
      '<div class="rp-splash-state">',
      '  <div class="rp-splash-state-title">报告暂时生成不出来</div>',
      '  <div class="rp-splash-state-desc">' + escapeHtml(msg) + '</div>',
      '  <button type="button" class="rp-splash-state-retry" id="rp-retry-btn">重新生成</button>',
      '</div>',
    ].join('');
    var btn = document.getElementById('rp-retry-btn');
    if (btn) btn.addEventListener('click', function () { init(); });
  }

  function renderEmptyState() {
    var root = document.getElementById('rp-root');
    root.innerHTML = [
      '<div class="rp-splash-state">',
      '  <div class="rp-splash-state-title">还没做诊断</div>',
      '  <div class="rp-splash-state-desc">请先完成自由描述和答题，再回来查看诊断报告。</div>',
      '  <button type="button" class="rp-splash-state-retry" id="rp-goto-splash">去开始诊断</button>',
      '</div>',
    ].join('');
    var btn = document.getElementById('rp-goto-splash');
    if (btn) btn.addEventListener('click', function () {
      window.location.href = '/splash.html';
    });
  }

  // ───────────────────────────────────────────────────────
  // 渲染：V2_DarkHero 报告主视图
  // ───────────────────────────────────────────────────────

  function renderReport(report) {
    var root = document.getElementById('rp-root');
    if (!report || !report.state_label || !report.scores_5d) {
      renderError(new Error('malformed_report'));
      return;
    }

    var sev = report.state_label.severity;
    var style = SEVERITY_STYLES[sev] || SEVERITY_STYLES.danger;
    var themeColor = report.state_label.theme_color || style.color;
    var stateName = report.state_label.name;
    var stateTitle = STATE_TITLES[stateName] || '你处于「' + stateName + '」的阶段';
    var trendText = (report.trend_prediction && report.trend_prediction.text) || '';
    var reportId = getReportId();

    // 核心问题 HTML（ProblemRowFlat 风格 — 白卡 + 严重度 tag）
    var problemHtml = (report.core_issues || []).map(function (p, idx) {
      var title = p.title || '';
      var parts = title.split('——');
      var mainTitle = parts[0];
      var subTitle = parts[1] || '';
      var sevKey = idx === 0 || idx === 1 ? 'high' : 'mid';
      var sevMap = {
        high: { bg: '#FFE6E6', color: '#C00' },
        mid:  { bg: '#FFF4E0', color: '#E88F00' },
        low:  { bg: '#E8F1FF', color: '#0B5EFE' },
      };
      var sevStyle = sevMap[sevKey];
      return [
        '<div class="rp-problem-card">',
        '  <div class="rp-problem-head">',
        '    <span class="rp-problem-idx">#' + pad2(idx + 1) + '</span>',
        '    <span class="rp-problem-sev" style="background:' + sevStyle.bg + ';color:' + sevStyle.color + ';">',
        escapeHtml(['高优', '高优', '中优'][idx] || '提示'),
        '</span>',
        '  </div>',
        '  <div class="rp-problem-title">' + escapeHtml(mainTitle) + '</div>',
        (subTitle ? '  <div class="rp-problem-sub">' + escapeHtml(subTitle) + '</div>' : ''),
        '  <div class="rp-problem-evidence">' + escapeHtml(p.evidence || '') + '</div>',
        '</div>',
      ].join('');
    }).join('');

    // 5 维 mini 雷达（darkMode，颜色 #FFB4E6）
    var miniRadarSvg = buildRadarSvg(report.scores_5d, { size: 140, color: '#FFB4E6', darkMode: true });

    // 5 维分数行 HTML（白字 dark mode 风格）
    var miniScoresHtml = buildMiniScoresHtml(report.scores_5d);

    // 锁住编号表 HTML（LockedTableRow 风格）
    var lockedTableHtml = buildLockedTableHtml(report.locked_teasers || []);

    // 信任横条头像
    var avatarColors = ['#FF65C2', '#8A4BFF', '#BDA3FF'];
    var avatarsHtml = avatarColors.map(function (c, i) {
      return '<div class="rp-trust-avatar" style="background:' + c + ';margin-left:' + (i > 0 ? '-6px' : '0') + '"></div>';
    }).join('');

    var urgencyText = escapeHtml(report.urgency_text || '窗口期约 2-3 周\n越早介入，扭转成本越低').replace(/\n/g, '<br/>');

    var html = [
      /* ① Sticky 深色顶栏 */
      '<header class="rp-header-dark">',
      '  <span class="rp-header-spacer" aria-hidden="true"></span>',
      '  <span class="rp-header-dark-title">DIAGNOSTIC REPORT</span>',
      '  <span class="rp-header-dark-id">' + escapeHtml(reportId) + '</span>',
      '</header>',

      /* 固定底层：不随内容滚动，模拟原型手机框里的紫底 + 白底 */
      '<div class="rp-fixed-backdrop" aria-hidden="true">',
      '  <div class="rp-backdrop-dark"></div>',
      '  <div class="rp-backdrop-light"></div>',
      '</div>',

      /* 可滚动主内容区 */
      '<div class="rp-scroll-body">',
      '<section class="rp-hero-stage">',

      /* ② Hero 卡（浮在独立深色底层上的玻璃态） */
      '<div class="rp-hero-card">',
      '  <div class="rp-hero-pill" style="background:' + escapeAttr(style.bg) + ';color:' + escapeAttr(themeColor) + ';">',
      '    <span class="rp-hero-pill-dot" style="background:' + escapeAttr(themeColor) + ';"></span>',
      escapeHtml(stateName),
      '  </div>',
      '  <div class="rp-hero-title">' + escapeHtml(stateTitle) + '</div>',
      '  <div class="rp-hero-trend">' + escapeHtml(trendText) + '</div>',
      '</div>',

      /* 5 维 mini 预览 */
      '<div class="rp-hero-acr">',
      '  <div class="rp-hero-acr-label">5 维健康度 · 吸引 / 舒适 / 张力 / 信任 / 回应</div>',
      '  <div class="rp-hero-acr-body">',
      '    <div class="rp-hero-acr-radar">' + miniRadarSvg + '</div>',
      '    <div class="rp-hero-acr-scores">' + miniScoresHtml + '</div>',
      '  </div>',
      '</div>',
      '</section>',

      '<div class="rp-light-content">',

      /* ③ 核心问题（白底区域） */
      '<div class="rp-section-header">',
      '  <div>',
      '    <div class="rp-section-title-dark">识别出的关键问题</div>',
      '    <div class="rp-section-subtitle">按严重程度降序</div>',
      '  </div>',
      '  <span class="rp-problem-count-tag">' + (report.core_issues || []).length + ' 项</span>',
      '</div>',
      '<div class="rp-problem-list">' + problemHtml + '</div>',

      /* ④ 锁住完整方案 3 大能力（编号表） */
      '<div class="rp-locked-title">🔒 完整方案 · 3 大能力</div>',
      '<div class="rp-locked-table">' + lockedTableHtml + '</div>',

      /* ⑤ 信任横条 */
      '<div class="rp-trust-bar">',
      '  <div class="rp-trust-avatars">' + avatarsHtml + '</div>',
      '  <span class="rp-trust-text">已有 <b>2,847</b> 人用此方案推进关系</span>',
      '</div>',

      /* ⑥ 底部渐变过渡带 */
      '<div class="rp-transition-grad" aria-hidden="true"></div>',

      /* ⑦ 深色付费大卡 */
      '<div class="rp-paycard-wrap">',
      '<div class="rp-paycard-dark">',
      '  <div class="rp-paycard-unlock-label">UNLOCK</div>',
      '  <div class="rp-paycard-urgency">' + urgencyText + '</div>',
      '  <div class="rp-paycard-feat-list">',
      buildFeatDarkHtml('完整诊断 · PDF 导出'),
      buildFeatDarkHtml('3 阶段推进方案 · 里程碑可追踪'),
      buildFeatDarkHtml('每次关键对话前实时建议'),
      buildFeatDarkHtml('7 天 1 对 1 小话老师陪跑'),
      '  </div>',
      '  <div class="rp-price-row">',
      buildPriceChipDarkHtml('包周', '9.9', '体验版', false),
      buildPriceChipDarkHtml('包一个 Crush', '99', '推荐', true),
      '  </div>',
      '  <button type="button" class="rp-cta-btn" id="rp-unlock-btn">立即解锁 · ¥99</button>',
      '  <div class="rp-refund-note">💙 7 天无理由退款</div>',
      '</div>',
      '</div>',
      '</div>',

      '</div>', /* end rp-scroll-body */
    ].join('');

    root.innerHTML = html;

    try {
      window.Tracker && window.Tracker.track('report_view', {
        state_label: (report && report.state_label && report.state_label.name) || null,
        report_id: (report && report.report_id) || null
      });
    } catch (_) {}

    // 绑定解锁按钮
    var unlockBtn = document.getElementById('rp-unlock-btn');
    if (unlockBtn) unlockBtn.addEventListener('click', onUnlockClick);

    // 保证 stage 记成 'report'
    if ((loadStore() || {}).stage !== 'report') {
      patchStore({ stage: 'report' });
    }
  }

  // ───────────────────────────────────────────────────────
  // 渲染：5 维 mini 分数行（深色卡内）
  // ───────────────────────────────────────────────────────

  function buildMiniScoresHtml(scores) {
    var keys = ['A', 'C', 'R', 'T', 'E'];
    return keys.map(function (k) {
      var item = scores[k] || { score: 0, note: '' };
      var s = Math.max(0, Math.min(100, Math.round(item.score || 0)));
      var label = SCORE_LABELS[k] || k;
      // 颜色规则：< 40 粉 #FF65C2，< 60 浅粉 #FFB4E6，否则白
      var scoreColor = s < 40 ? '#FF65C2' : (s < 60 ? '#FFB4E6' : '#fff');
      // 进度条颜色：< 60 粉，否则 #FFB4E6
      var barColor = s < 60 ? '#FF65C2' : '#FFB4E6';
      return [
        '<div class="rp-mini-score-row">',
        '  <div class="rp-mini-score-label-row">',
        '    <span class="rp-mini-score-label">' + escapeHtml(label) + '</span>',
        '    <span class="rp-mini-score-val" style="color:' + scoreColor + ';">' + s + '</span>',
        '  </div>',
        '  <div class="rp-mini-score-bar-bg">',
        '    <div class="rp-mini-score-bar-fill" style="width:' + s + '%;background:' + barColor + ';"></div>',
        '  </div>',
        '</div>',
      ].join('');
    }).join('');
  }

  // ───────────────────────────────────────────────────────
  // 渲染：锁住编号表（LockedTableRow 风格）
  // ───────────────────────────────────────────────────────

  function buildLockedTableHtml(teasers) {
    // V2_DarkHero 的锁住预览用固定的 3 大能力 × 3 子项结构（与 jsx 对齐）。
    // LLM 返回的 teasers 数据 section 粒度不一致，直接用 fallback 的规整子项展示。
    var lockIcon = '<svg class="rp-locked-row-lock" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a5 5 0 00-5 5v3H6a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2v-8a2 2 0 00-2-2h-1V7a5 5 0 00-5-5zm-3 8V7a3 3 0 016 0v3H9z"/></svg>';

    return CAPABILITY_SECTIONS.map(function (cap, capIdx) {
      var isLast = capIdx === CAPABILITY_SECTIONS.length - 1;
      var items = cap.fallback.slice(0, 3);

      var itemsHtml = items.map(function (n) {
        return [
          '<div class="rp-locked-row-item">',
          '  <span class="rp-locked-row-dot">·</span>',
          '  <span class="rp-locked-row-item-text">' + escapeHtml(n) + '</span>',
          '  <span class="rp-locked-row-stripe"></span>',
          '</div>',
        ].join('');
      }).join('');

      return [
        '<div class="rp-locked-table-row' + (isLast ? ' last' : '') + '">',
        '  <div class="rp-locked-table-row-head">',
        '    <span class="rp-locked-table-row-no">' + cap.no + '</span>',
        '    <span class="rp-locked-table-row-title">' + escapeHtml(cap.title) + '</span>',
        '    ' + lockIcon,
        '  </div>',
        '  <div class="rp-locked-table-row-items">' + itemsHtml + '</div>',
        '</div>',
      ].join('');
    }).join('');
  }

  // ───────────────────────────────────────────────────────
  // 渲染：FeatDark（深色勾选项）
  // ───────────────────────────────────────────────────────

  function buildFeatDarkHtml(text) {
    return [
      '<div class="rp-feat-dark">',
      '  <svg viewBox="0 0 24 24" fill="none" stroke="#FFB4E6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">',
      '    <path d="M20 6L9 17l-5-5"/>',
      '  </svg>',
      '  <span>' + escapeHtml(text) + '</span>',
      '</div>',
    ].join('');
  }

  // ───────────────────────────────────────────────────────
  // 渲染：PriceChipDark（深色价格 chip）
  // ───────────────────────────────────────────────────────

  function buildPriceChipDarkHtml(title, price, sub, featured) {
    var badgeHtml = featured
      ? '<span class="rp-price-chip-dark-badge">推荐</span>'
      : '';
    return [
      '<div class="rp-price-chip-dark' + (featured ? ' featured' : '') + '">',
      badgeHtml,
      '  <div class="rp-price-chip-dark-title">' + escapeHtml(title) + '</div>',
      '  <div class="rp-price-chip-dark-price">',
      '    <span class="rp-price-chip-dark-currency">¥</span>',
      '    <span class="rp-price-chip-dark-num">' + escapeHtml(price) + '</span>',
      '  </div>',
      '  <div class="rp-price-chip-dark-sub">' + escapeHtml(sub) + '</div>',
      '</div>',
    ].join('');
  }

  // ───────────────────────────────────────────────────────
  // 渲染：ACR 5 维雷达 SVG
  // 支持 darkMode 参数（深色网格线 + 白色标签）
  // ───────────────────────────────────────────────────────

  function buildRadarSvg(scores, opts) {
    var size = (opts && opts.size) || 220;
    var color = (opts && opts.color) || '#8A4BFF';
    var darkMode = !!(opts && opts.darkMode);
    var gridColor = darkMode ? 'rgba(255,255,255,.18)' : '#E5E0F5';
    var labelColor = darkMode ? 'rgba(255,255,255,.9)' : '#333333';
    // 顺序强制 A/C/R/T/E，对齐 schema
    var keys = ['A', 'C', 'R', 'T', 'E'];
    var cx = size / 2;
    var cy = size / 2;
    var r = size / 2 - 34;

    function angle(i) {
      return (Math.PI * 2 * i) / keys.length - Math.PI / 2;
    }
    function pt(i, v) {
      return [
        cx + Math.cos(angle(i)) * r * v / 100,
        cy + Math.sin(angle(i)) * r * v / 100,
      ];
    }

    var parts = [];
    parts.push('<svg width="' + size + '" height="' + size +
               '" viewBox="0 0 ' + size + ' ' + size + '" role="img" aria-label="5 维关系健康度雷达图">');

    // 4 圈网格
    [0.25, 0.5, 0.75, 1].forEach(function (k) {
      var ptsStr = keys.map(function (_, i) {
        return pt(i, k * 100).join(',');
      }).join(' ');
      parts.push('<polygon points="' + ptsStr + '" fill="none" stroke="' + gridColor + '" stroke-width="1"/>');
    });

    // 5 条轴
    keys.forEach(function (_, i) {
      var p = pt(i, 100);
      parts.push('<line x1="' + cx + '" y1="' + cy + '" x2="' + p[0] + '" y2="' + p[1] +
                 '" stroke="' + gridColor + '" stroke-width="1"/>');
    });

    // 数据多边形
    var dataPts = keys.map(function (k, i) {
      var item = scores[k] || { score: 0 };
      var s = Math.max(0, Math.min(100, item.score || 0));
      return pt(i, s).join(',');
    }).join(' ');
    parts.push('<polygon points="' + dataPts + '" fill="' + color + '" fill-opacity="0.22" stroke="' +
               color + '" stroke-width="2" stroke-linejoin="round"/>');

    // 数据点
    keys.forEach(function (k, i) {
      var item = scores[k] || { score: 0 };
      var s = Math.max(0, Math.min(100, item.score || 0));
      var p = pt(i, s);
      parts.push('<circle cx="' + p[0] + '" cy="' + p[1] + '" r="4" fill="' + color + '"/>');
    });

    // 顶点 label（仅英文缩写，对齐 page7-report.jsx ACRRadar 的简洁风格）
    keys.forEach(function (k, i) {
      var p = pt(i, 124);
      parts.push('<text x="' + p[0] + '" y="' + p[1] +
                 '" text-anchor="middle" dominant-baseline="middle" font-size="11" font-weight="700" fill="' +
                 labelColor + '">' + k + '</text>');
    });

    parts.push('</svg>');
    return parts.join('');
  }

  // ───────────────────────────────────────────────────────
  // 付费：mock 支付流程
  // ───────────────────────────────────────────────────────

  function onUnlockClick() {
    var btn = document.getElementById('rp-unlock-btn');
    if (btn) {
      btn.disabled = true;
      btn.textContent = '处理中…';
    }

    try { window.Tracker && window.Tracker.track('pay_click'); } catch (_) {}

    // 先把 stage 标成 paid（标识进入支付流程）
    patchStore({ stage: 'paid' });

    // Loading 遮罩
    var overlay = document.createElement('div');
    overlay.className = 'rp-pay-overlay';
    overlay.innerHTML = [
      '<div class="rp-pay-overlay-card">',
      '  <div class="rp-spinner" aria-hidden="true"></div>',
      '  <div class="rp-pay-text">正在连接支付…</div>',
      '</div>',
    ].join('');
    document.body.appendChild(overlay);

    // mock：1000ms 后置 success
    setTimeout(function () {
      overlay.innerHTML = [
        '<div class="rp-pay-overlay-card success">',
        '  <div class="rp-check" aria-hidden="true">',
        '    <svg viewBox="0 0 24 24" fill="none" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">',
        '      <path d="M20 6L9 17l-5-5"/>',
        '    </svg>',
        '  </div>',
        '  <div class="rp-pay-text">解锁成功，为你跳转主页面</div>',
        '</div>',
      ].join('');

      // v2.1:付费成功后 stage 保留在 'paid',由 index.html 的 onMounted 自动首轮
      // 完成 /api/chat/stream 后再调 markDone() 推进到 'done'。
      patchStore({
        paid: true,
        paid_at: new Date().toISOString(),
        stage: 'paid',
      });

      try {
        window.Tracker && window.Tracker.track('pay_success');
        window.Tracker && window.Tracker.flush();
      } catch (_) {}

      setTimeout(function () {
        window.location.href = '/index.html';
      }, 650);
    }, 1000);
  }

  // ───────────────────────────────────────────────────────
  // 工具
  // ───────────────────────────────────────────────────────

  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function escapeAttr(s) {
    return escapeHtml(s);
  }
  function pad2(n) {
    n = String(n);
    return n.length < 2 ? ('0' + n) : n;
  }

  // ───────────────────────────────────────────────────────
  // 启动
  // ───────────────────────────────────────────────────────

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // 暴露出 testing hook（e2e 里可以直接调）
  window.__rp_renderReport = renderReport;
})();
