/**
 * Crushe 数据仪表盘 · 前端渲染
 *
 * 无任何前端框架依赖。tab 切换触发 fetch 对应 API + 渲染。
 */
(function () {
  'use strict';

  var content = document.getElementById('content');
  var tabs = document.getElementById('tabs');
  var subtitle = document.getElementById('subtitle');
  var refreshBtn = document.getElementById('refresh-btn');

  var currentTab = 'today';

  function setLoading() {
    content.innerHTML = '<div class="card loading">读取中…</div>';
  }
  function setError(msg) {
    content.innerHTML = '<div class="card error">加载失败：' + escapeHtml(msg) + '</div>';
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c];
    });
  }

  function fmtTime(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    // 显示北京时间，格式 MM-DD HH:mm:ss
    var beijing = new Date(d.getTime() + (8 * 60 - (-d.getTimezoneOffset())) * 60 * 1000);
    var m = String(beijing.getMonth() + 1).padStart(2, '0');
    var day = String(beijing.getDate()).padStart(2, '0');
    var h = String(beijing.getHours()).padStart(2, '0');
    var mi = String(beijing.getMinutes()).padStart(2, '0');
    var s = String(beijing.getSeconds()).padStart(2, '0');
    return m + '-' + day + ' ' + h + ':' + mi + ':' + s;
  }

  function updateSubtitle() {
    var now = new Date();
    var h = String(now.getHours()).padStart(2, '0');
    var mi = String(now.getMinutes()).padStart(2, '0');
    subtitle.textContent = '当前数据快照于本机时间 ' + h + ':' + mi + ' · 切换标签或点刷新更新';
  }

  // ─── 渲染：漏斗 ─────────────────────────────
  function renderFunnel(data) {
    var steps = data.steps || [];
    if (!steps.length) {
      return '<div class="card empty">暂无事件数据</div>';
    }
    var rows = steps.map(function (s, idx) {
      var convPrev = s.conv_from_prev;
      var convFirst = s.conv_from_first;
      var firstLine = (idx === 0)
        ? '起点'
        : (convPrev !== null
            ? '相对上一步 <span class="pct">' + convPrev + '%</span>'
            : '—');
      var secondLine = (idx === 0)
        ? ''
        : (convFirst !== null
            ? '累计漏斗 ' + convFirst + '%'
            : '');
      return '' +
        '<div class="funnel-step">' +
        '  <div class="funnel-label">' +
        '    <span class="step-no">STEP ' + (idx + 1) + '</span>' +
        '    <span>' + escapeHtml(s.label) + '</span>' +
        '  </div>' +
        '  <div class="funnel-users">' + s.users + '</div>' +
        '  <div class="funnel-conv">' + firstLine + (secondLine ? '<br>' + secondLine : '') + '</div>' +
        '</div>';
    }).join('');

    return '' +
      '<div class="card">' +
      '  <h2>销售漏斗 <span class="range-tag">' + escapeHtml(data.label || '') + '</span></h2>' +
      rows +
      '  <div style="margin-top:12px;font-size:11px;color:var(--muted);">' +
      '    区间事件总数：' + (data.total_events || 0) + ' · 以 anonymous_id 去重' +
      '  </div>' +
      '</div>';
  }

  // ─── 渲染：最近事件 ──────────────────────────
  function renderRecentEvents(data) {
    var list = data.events || [];
    if (!list.length) {
      return '<div class="card empty">暂无事件</div>';
    }
    var rows = list.map(function (e) {
      var props = e.props || {};
      var propsStr = Object.keys(props).length
        ? JSON.stringify(props)
        : '—';
      return '' +
        '<tr>' +
        '  <td>' + escapeHtml(fmtTime(e.created_at)) + '</td>' +
        '  <td class="name-cell">' + escapeHtml(e.event_name) + '</td>' +
        '  <td class="anon-cell">' + escapeHtml((e.anonymous_id || '').slice(0, 12)) + '</td>' +
        '  <td><span style="font-size:11px;color:var(--muted);">' + escapeHtml(e.source || '') + '</span></td>' +
        '  <td class="props-cell">' + escapeHtml(propsStr) + '</td>' +
        '</tr>';
    }).join('');

    return '' +
      '<div class="card">' +
      '  <h2>最近事件明细 <span class="range-tag">' + list.length + ' 条</span></h2>' +
      '  <table class="events-table">' +
      '    <thead><tr><th>时间（北京）</th><th>事件</th><th>Anon</th><th>来源</th><th>Props</th></tr></thead>' +
      '    <tbody>' + rows + '</tbody>' +
      '  </table>' +
      '</div>';
  }

  // ─── 渲染：LLM 健康 ──────────────────────────
  function renderLLMHealth(data) {
    function fmtRate(p) {
      if (p === null || p === undefined) return '—';
      var cls = p >= 95 ? 'llm-ok' : (p >= 80 ? 'llm-warn' : 'llm-bad');
      return '<span class="llm-value ' + cls + '">' + p + '%</span>';
    }
    function fmtDur(ms) {
      if (ms === null || ms === undefined) return '—';
      if (ms >= 1000) return '<span class="llm-value">' + (ms / 1000).toFixed(1) + 's</span>';
      return '<span class="llm-value">' + ms + ' ms</span>';
    }
    function row(name, b) {
      return '<div class="llm-row">' +
        '  <div class="llm-endpoint">' + name + '</div>' +
        '  <div>总调用 <span class="llm-value">' + b.total + '</span></div>' +
        '  <div>成功率 ' + fmtRate(b.success_rate_pct) + '</div>' +
        '  <div>平均耗时 ' + fmtDur(b.avg_duration_ms) + '</div>' +
        '</div>';
    }
    return '' +
      '<div class="card">' +
      '  <h2>LLM 端点健康 <span class="range-tag">' + escapeHtml(data.label || '') + '</span></h2>' +
      '  <div class="llm-row head">' +
      '    <div>端点</div><div>总调用</div><div>成功率</div><div>平均耗时</div>' +
      '  </div>' +
      row('analyze', data.analyze || {total:0, success_rate_pct:null, avg_duration_ms:null}) +
      row('report', data.report || {total:0, success_rate_pct:null, avg_duration_ms:null}) +
      '  <div style="margin-top:12px;font-size:11px;color:var(--muted);">' +
      '    analyze 的失败包含「降级兜底」（LLM 超时 / 解析失败，前端仍拿到兜底内容）' +
      '  </div>' +
      '</div>';
  }

  // ─── 路由：tab → fetch ───────────────────────
  function load(tab) {
    setLoading();
    updateSubtitle();
    var url, render;
    if (tab === 'today' || tab === 'yesterday' || tab === '7d') {
      url = '/api/analytics/funnel?range=' + tab;
      render = renderFunnel;
    } else if (tab === 'recent') {
      url = '/api/analytics/events/recent?limit=100';
      render = renderRecentEvents;
    } else if (tab === 'llm') {
      url = '/api/analytics/llm_health?range=7d';
      render = renderLLMHealth;
    } else {
      setError('unknown tab: ' + tab);
      return;
    }

    fetch(url, { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        content.innerHTML = render(data);
      })
      .catch(function (err) {
        setError(err.message || String(err));
      });
  }

  // ─── 绑定 ─────────────────────────────────────
  tabs.addEventListener('click', function (ev) {
    var btn = ev.target.closest('.tab');
    if (!btn) return;
    var all = tabs.querySelectorAll('.tab');
    for (var i = 0; i < all.length; i++) all[i].classList.remove('active');
    btn.classList.add('active');
    currentTab = btn.getAttribute('data-tab');
    load(currentTab);
  });

  refreshBtn.addEventListener('click', function () { load(currentTab); });

  // 初始加载
  load(currentTab);
})();
