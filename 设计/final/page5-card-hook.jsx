// page5-card-hook.jsx — 卡片题选完后的「钩子独立页」
// 视觉方案：方案 B 风（白底 / 细线 / 主色 #8A4BFF）
// V1_Report 为主流程使用版本，其余版本保留供参考

// 共用：拿到钩子内容
function getDemoHook(qKey = 'A3') {
  // 这里演示默认用 A3 的 combo_confess_high；后面几个版本也能用其他 key
  if (qKey === 'A3') return { ...window.HOOKS_A3.combo_confess_high, qIdx: 2, total: 5, qLabel: 'Q3 · 行动历史' };
  if (qKey === 'A3-single') return { ...window.HOOKS_A3.confess, qIdx: 2, total: 5, qLabel: 'Q3 · 行动历史' };
  if (qKey === 'A4') return { ...window.HOOKS_A4.combo_friend_any, qIdx: 3, total: 5, qLabel: 'Q4 · 负面信号' };
  if (qKey === 'A1') return { ...window.HOOKS_A1.colleague, qIdx: 0, total: 5, qLabel: 'Q1 · 关系性质' };
  if (qKey === 'A5-last') return {
    tag: '目标确认',
    short: '你的目标是"想先拉近距离 / 让 TA 更有好感"。',
    body: '锁定目标后，接下来我会围绕「好感度提升」为你定制策略，优先处理吸引力 / 舒适感 / 张力中你最薄弱的一维。',
    highlight: '好感度提升',
    feature: null,
    qIdx: 4, total: 5, qLabel: 'Q5 · 目标确认',
  };
  return { ...window.HOOKS_A3.combo_confess_high, qIdx: 2, total: 5, qLabel: 'Q3 · 行动历史' };
}

// ─── SVG 图标（替代所有 emoji） ───
function IconLock() {
  return <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="#8A4BFF" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5 7V5a3 3 0 0 1 6 0v2"/></svg>;
}
function IconGauge() {
  return <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><path d="M8 14A6 6 0 1 1 8 2a6 6 0 0 1 0 12z"/><path d="M8 5v3l2 1.5"/></svg>;
}
function IconRoute() {
  return <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><circle cx="4" cy="4" r="2"/><circle cx="12" cy="12" r="2"/><path d="M6 4h4a2 2 0 0 1 2 2v4"/></svg>;
}
function IconChat() {
  return <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><path d="M2 3h12v8H6l-3 2v-2H2z" strokeLinejoin="round"/></svg>;
}
function IconTarget() {
  return <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3"/><circle cx="8" cy="8" r="0.8" fill="currentColor"/></svg>;
}
function IconGrid() {
  return <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg>;
}

// 通用卡片外壳（紫调阴影 + 微渐变白底 + 品牌 accent bar）
const cardShell = {
  padding: 14,
  background: 'linear-gradient(180deg, #fff 0%, #FDFAFF 100%)',
  borderRadius: 12,
  border: '0.5px solid rgba(138,75,255,0.12)',
  boxShadow: '0 8px 32px rgba(105,124,255,0.10)',
  position: 'relative',
  overflow: 'hidden',
};

// 顶部紫粉渐变装饰线
function AccentBar() {
  return <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: 'linear-gradient(90deg, #8A4BFF, #FF65C2)' }}/>;
}

// 定制 banner（替代旧 DraftBanner）
function DraftBanner() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '6px 10px', marginBottom: 12,
      background: 'linear-gradient(135deg, rgba(138,75,255,0.06), rgba(255,101,194,0.06))',
      borderRadius: 8, borderLeft: '2px solid #8A4BFF',
    }}>
      <IconLock />
      <span style={{ fontSize: 10, color: '#8A4BFF', fontWeight: 600, letterSpacing: 0.2 }}>为你定制中 · 完整版诊断后解锁</span>
    </div>
  );
}

// 底部淡出遮罩（暗示还有更多）
function FadeOut() {
  return <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 20, background: 'linear-gradient(transparent, #FDFAFF)', borderRadius: '0 0 12px 12px', pointerEvents: 'none' }}/>;
}

// 5 种功能预览卡
function FeaturePreview({ feature, variant = 'default' }) {
  if (!feature) return null;
  const frames = {
    '情感罗盘': <SituationFrame variant={variant}/>,
    '局势分析': <SituationFrame variant={variant}/>,
    '行动规划': <PlanFrame variant={variant}/>,
    '聊天指导': <ChatGuideFrame variant={variant}/>,
    '行动指南': <ActionGuideFrame variant={variant}/>,
    '朋友圈指导': <MomentsFrame variant={variant}/>,
  };
  return frames[feature] || null;
}

function SituationFrame({ variant }) {
  const dims = [
    { label: '吸引力', v: 52, color: '#8A4BFF' },
    { label: '舒适感', v: 68, color: '#8A4BFF' },
    { label: '张力',   v: 18, color: '#E84057' },
    { label: '信任度', v: 45, color: '#8A4BFF' },
    { label: '回应度', v: 31, color: '#E84057' },
  ];
  const progress = 34;
  const r = 30, cx = 38, cy = 38, sw = 5;
  const circ = 2 * Math.PI * r;
  return (
    <div style={cardShell}>
      <AccentBar />
      <DraftBanner />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ color: '#8A4BFF' }}><IconGauge /></span>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#1a1a1a' }}>情感罗盘 · 关系快照</span>
        </div>
        <Tag tone="amber" size="xs">需关注</Tag>
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        {/* 左侧：关系进度圆环 — 数字模糊 */}
        <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={{ position: 'relative', width: 76, height: 76 }}>
            <svg width="76" height="76" viewBox="0 0 76 76">
              <circle cx={cx} cy={cy} r={r} fill="none" stroke="#F0EBFA" strokeWidth={sw}/>
              <circle cx={cx} cy={cy} r={r} fill="none" stroke="url(#ringG_sit)" strokeWidth={sw}
                strokeLinecap="round" strokeDasharray={`${circ * progress / 100} ${circ}`}
                transform={`rotate(-90 ${cx} ${cy})`}/>
              <defs><linearGradient id="ringG_sit" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#8A4BFF"/><stop offset="100%" stopColor="#FF65C2"/></linearGradient></defs>
            </svg>
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ fontFamily: 'DM Sans', fontSize: 22, fontWeight: 700, color: '#1a1a1a', lineHeight: 1, filter: 'blur(5px)', userSelect: 'none' }}>34</div>
              <div style={{ fontSize: 8, color: '#999', marginTop: 2 }}>关系进度</div>
            </div>
          </div>
          <div style={{ marginTop: 4, padding: '2px 8px', background: 'rgba(138,75,255,0.08)', borderRadius: 4, fontSize: 9, fontWeight: 600, color: '#8A4BFF' }}>暧昧初期</div>
        </div>
        {/* 右侧：五维健康度 — 进度条模糊 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 5 }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: '#888', marginBottom: 1 }}>5 维健康度</div>
          {dims.map((d, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 36, fontSize: 9, fontWeight: 600, color: d.color, textAlign: 'right', flexShrink: 0 }}>{d.label}</div>
              <div style={{ flex: 1, height: 5, background: '#F0EBFA', borderRadius: 3, overflow: 'hidden', filter: 'blur(3px)' }}>
                <div style={{
                  width: d.v + '%', height: '100%', borderRadius: 3,
                  background: d.color === '#E84057'
                    ? 'linear-gradient(90deg, #E84057, #FF7B8E)'
                    : 'linear-gradient(90deg, #8A4BFF, #B07FFF)',
                }}/>
              </div>
            </div>
          ))}
        </div>
      </div>
      {/* 提示 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, padding: '6px 8px', background: 'rgba(138,75,255,0.04)', borderRadius: 6, marginTop: 8 }}>
        <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="#8A4BFF" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5 7V5a3 3 0 0 1 6 0v2"/></svg>
        <span style={{ fontSize: 9, color: '#8A4BFF', fontWeight: 600 }}>完成诊断后解锁你的真实数据</span>
      </div>
    </div>
  );
}

function PlanFrame({ variant }) {
  const phases = [
    { text: '停止主动 · 让 TA 开始找你' },
    { text: '制造存在感 · 让 TA 觉得你在变化' },
    { text: '精准出手 · 一步推进关系' },
  ];
  return (
    <div style={cardShell}>
      <AccentBar />
      <DraftBanner />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ color: '#8A4BFF' }}><IconRoute /></span>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#1a1a1a' }}>行动规划 · 3 阶段</span>
        </div>
        <Tag tone="violet" size="xs">4 周</Tag>
      </div>
      <div style={{ position: 'relative', paddingLeft: 18 }}>
        <div style={{ position: 'absolute', left: 5, top: 6, bottom: 6, width: 0, borderLeft: '1.5px dashed rgba(138,75,255,0.3)' }}/>
        {phases.map((p, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: i < 2 ? 10 : 0, position: 'relative' }}>
            <div style={{
              position: 'absolute', left: -18, top: 5,
              width: 10, height: 10, borderRadius: '50%',
              background: i === 0 ? '#8A4BFF' : '#fff',
              border: i === 0 ? 'none' : '1.5px solid #8A4BFF',
              boxShadow: i === 0 ? '0 0 0 3px rgba(138,75,255,0.15)' : 'none',
            }}/>
            <div style={{
              flex: 1, padding: '6px 10px', borderRadius: 8,
              background: i === 0 ? 'rgba(138,75,255,0.06)' : '#FAFAFC',
              borderLeft: i === 0 ? '2px solid #8A4BFF' : '2px solid transparent',
              filter: i > 0 ? 'blur(4px)' : 'none',
              userSelect: i > 0 ? 'none' : 'auto',
            }}>
              <span style={{ fontFamily: 'DM Sans', fontSize: 9, fontWeight: 700, color: '#8A4BFF', letterSpacing: 0.5 }}>PHASE {i + 1}</span>
              <div style={{ fontSize: 11, color: '#333', marginTop: 2 }}>{p.text}</div>
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, padding: '6px 8px', background: 'rgba(138,75,255,0.04)', borderRadius: 6, marginTop: 10 }}>
        <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="#8A4BFF" strokeWidth="1.5" strokeLinecap="round"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5 7V5a3 3 0 0 1 6 0v2"/></svg>
        <span style={{ fontSize: 9, color: '#8A4BFF', fontWeight: 600 }}>完成诊断后解锁完整规划</span>
      </div>
    </div>
  );
}

function ChatGuideFrame({ variant }) {
  const annotStyle = {
    position: 'absolute', left: -2, right: -2,
    border: '1.5px solid rgba(138,75,255,0.5)',
    borderRadius: 10, pointerEvents: 'none',
  };
  return (
    <div style={cardShell}>
      <AccentBar />
      <DraftBanner />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ color: '#8A4BFF' }}><IconChat /></span>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#1a1a1a' }}>聊天指导 · 逐条批注</span>
        </div>
        <Tag tone="greenish" size="xs">实时</Tag>
      </div>
      {/* 模拟截图区域 */}
      <div style={{ background: '#F5F5F5', borderRadius: 8, padding: '8px 8px 6px', position: 'relative' }}>
        {/* 截图标签 */}
        <div style={{ position: 'absolute', top: -8, left: 8, padding: '1px 6px', background: '#8A4BFF', borderRadius: 4, fontSize: 8, fontWeight: 700, color: '#fff', letterSpacing: 0.3, zIndex: 2 }}>你的截图</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 2 }}>
          {/* TA 消息 — 无批注 */}
          <div style={{ alignSelf: 'flex-start', maxWidth: '82%', padding: '6px 10px', background: '#fff', borderRadius: '10px 10px 10px 3px', fontSize: 10.5, color: '#333' }}>
            哈哈好久没聊了
          </div>
          {/* 你的回复 — 带批注框 + 连线 */}
          <div style={{ alignSelf: 'flex-end', maxWidth: '82%', position: 'relative' }}>
            <div style={{ padding: '6px 10px', background: '#95EC69', borderRadius: '10px 10px 3px 10px', fontSize: 10.5, color: '#333' }}>
              是啊！最近怎么样
            </div>
            {/* 批注高亮框 */}
            <div style={{ ...annotStyle, top: -3, bottom: -3 }}/>
            {/* 批注引线 + 标签 */}
            <div style={{ position: 'absolute', top: '50%', right: -46, transform: 'translateY(-50%)', display: 'flex', alignItems: 'center', gap: 0 }}>
              <div style={{ width: 12, height: 0, borderTop: '1px dashed #8A4BFF' }}/>
              <div style={{ background: '#8A4BFF', borderRadius: 3, padding: '2px 4px', fontSize: 7, fontWeight: 700, color: '#fff', whiteSpace: 'nowrap' }}>回复过快</div>
            </div>
          </div>
          {/* TA 回复 — 带批注 */}
          <div style={{ alignSelf: 'flex-start', maxWidth: '82%', position: 'relative' }}>
            <div style={{ padding: '6px 10px', background: '#fff', borderRadius: '10px 10px 10px 3px', fontSize: 10.5, color: '#333' }}>
              还行吧，你呢
            </div>
            <div style={{ ...annotStyle, top: -3, bottom: -3, borderColor: 'rgba(232,64,87,0.5)' }}/>
            <div style={{ position: 'absolute', top: '50%', left: -38, transform: 'translateY(-50%)', display: 'flex', alignItems: 'center', gap: 0 }}>
              <div style={{ background: '#E84057', borderRadius: 3, padding: '2px 4px', fontSize: 7, fontWeight: 700, color: '#fff', whiteSpace: 'nowrap' }}>敷衍</div>
              <div style={{ width: 8, height: 0, borderTop: '1px dashed #E84057' }}/>
            </div>
          </div>
        </div>
      </div>
      {/* 军师建议区 */}
      <div style={{ marginTop: 8, background: 'linear-gradient(135deg, rgba(138,75,255,0.06), rgba(255,101,194,0.04))', borderRadius: 8, padding: '7px 10px', borderLeft: '2px solid #8A4BFF' }}>
        <div style={{ fontSize: 9, fontWeight: 700, color: '#8A4BFF', marginBottom: 4, letterSpacing: 0.3 }}>小话建议回复</div>
        <div style={{ fontSize: 10, color: '#333', lineHeight: 1.5 }}>"哈哈在搞一个新东西，还挺有意思的"</div>
        <div style={{ fontSize: 8, color: '#8A4BFF', fontWeight: 600, marginTop: 3, opacity: 0.7 }}>策略：制造好奇 · 不正面回答 · 2h 后发</div>
      </div>
      <div style={{ marginTop: 6, fontSize: 9, color: '#999', textAlign: 'center' }}>截图发给小话 · 逐句标注 + 回复建议</div>
    </div>
  );
}

function ActionGuideFrame({ variant }) {
  const r2 = 20, cx2 = 28, cy2 = 28, sw2 = 4;
  const circ2 = 2 * Math.PI * r2;
  return (
    <div style={cardShell}>
      <AccentBar />
      <DraftBanner />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ color: '#8A4BFF' }}><IconTarget /></span>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#1a1a1a' }}>行动指南 · 邀约推演</span>
        </div>
      </div>
      {/* 成功率大数字 + 环形 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
        <div style={{ position: 'relative', width: 56, height: 56, flexShrink: 0 }}>
          <svg width="56" height="56" viewBox="0 0 56 56">
            <circle cx={cx2} cy={cy2} r={r2} fill="none" stroke="#F0EBFA" strokeWidth={sw2}/>
            <circle cx={cx2} cy={cy2} r={r2} fill="none" stroke="url(#ringGrad)" strokeWidth={sw2}
              strokeLinecap="round" strokeDasharray={`${circ2 * 0.72} ${circ2}`}
              transform={`rotate(-90 ${cx2} ${cy2})`}/>
            <defs><linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#8A4BFF"/><stop offset="100%" stopColor="#FF65C2"/></linearGradient></defs>
          </svg>
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontFamily: 'DM Sans', fontSize: 18, fontWeight: 700, color: '#8A4BFF' }}>72%</span>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: '#999', marginBottom: 4 }}>邀约成功率预估</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {[
              { t: '周三晚', bg: 'rgba(138,75,255,0.08)', fg: '#8A4BFF' },
              { t: '电影首映', bg: 'rgba(255,101,194,0.08)', fg: '#D44FA0' },
            ].map((p, i) => (
              <span key={i} style={{ padding: '2px 7px', borderRadius: 4, background: p.bg, fontSize: 9, fontWeight: 600, color: p.fg }}>{p.t}</span>
            ))}
          </div>
        </div>
      </div>
      {/* 话术预览 + 右侧淡出 */}
      <div style={{ position: 'relative', overflow: 'hidden' }}>
        <div style={{ padding: '7px 10px', background: '#FAFAFC', borderRadius: 8, fontSize: 10, color: '#444', lineHeight: 1.6 }}>
          "你不是想看这个吗，周六有场，要不要一起……"
        </div>
        <div style={{ position: 'absolute', top: 0, right: 0, bottom: 0, width: 40, background: 'linear-gradient(to right, transparent, #FAFAFC)' }}/>
      </div>
      <div style={{ marginTop: 8, fontSize: 9, color: '#8A4BFF', fontWeight: 500, textAlign: 'center' }}>完整版含最优时机 + 3 套话术备选</div>
    </div>
  );
}

function MomentsFrame({ variant }) {
  const items = [
    { title: '不刷存在感', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#8A4BFF" strokeWidth="1.2" opacity="0.25"><circle cx="8" cy="6" r="3"/><path d="M3 14c0-3 2-5 5-5s5 2 5 5"/></svg> },
    { title: '晒成长感', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#D44FA0" strokeWidth="1.2" opacity="0.25"><path d="M2 12l4-4 3 3 5-6"/></svg> },
    { title: '制造神秘感', icon: <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#8A4BFF" strokeWidth="1.2" opacity="0.25"><circle cx="8" cy="8" r="5"/><path d="M8 6v0m0 4v0" strokeWidth="2" strokeLinecap="round"/></svg> },
  ];
  return (
    <div style={cardShell}>
      <AccentBar />
      <DraftBanner />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ color: '#8A4BFF' }}><IconGrid /></span>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#1a1a1a' }}>朋友圈指导 · 本周建设</span>
        </div>
        <Tag tone="violet" size="xs">3 条</Tag>
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        {items.map((it, i) => (
          <div key={i} style={{
            flex: 1, borderRadius: 8, overflow: 'hidden',
            border: '0.5px solid rgba(138,75,255,0.1)',
          }}>
            {/* 色块占位图 */}
            <div style={{
              height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: i === 1 ? 'linear-gradient(135deg,#FFF0F9,#F6F0FF)' : 'linear-gradient(135deg,#F6F0FF,#EEEAFF)',
            }}>
              {it.icon}
            </div>
            <div style={{ padding: '5px 6px', fontSize: 9, fontWeight: 600, color: '#6B3FB0', textAlign: 'center', lineHeight: 1.3 }}>{it.title}</div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 8, fontSize: 9, color: '#999', textAlign: 'center' }}>本周 3 条 · 含配图建议 + 发布时间</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 版本 1：经典报告页（判断标题 · 正文 · 能力预览 · CTA）——主流程使用版本
// ═══════════════════════════════════════════════════════════════════════
function CardHook_V1_Report({ onNext, onBack, hookKey = 'A3', hookData }) {
  const H = hookData || getDemoHook(hookKey);

  // 根据 A0 性别选择，取对应版本文案；兜底用中性版
  const g = window.GENDER;
  const short = (g === 'male'   && H.short_m) ? H.short_m
              : (g === 'female' && H.short_f) ? H.short_f
              : H.short;
  const body  = (g === 'male'   && H.body_m)  ? H.body_m
              : (g === 'female' && H.body_f)  ? H.body_f
              : H.body;

  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10, background: '#F7F7FA' }}>
        <button onClick={onBack} style={iconBtn36}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
        <Eyebrow>诊断反馈 · {H.qLabel}</Eyebrow>
        <div style={{ width: 36 }}/>
      </div>
      {/* 题目小进度条 */}
      <div style={{ position: 'absolute', top: 94, left: 21, right: 21, display: 'flex', gap: 4, zIndex: 10 }}>
        {Array.from({length: H.total}).map((_, i) => (
          <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= H.qIdx ? '#8A4BFF' : '#E5E0F5' }}/>
        ))}
      </div>

      <div style={{ position: 'absolute', top: 110, bottom: 100, left: 0, right: 0, overflowY: 'auto', padding: '14px 21px 20px', zIndex: 2 }}>
        {/* Tag + 大标题 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Tag tone="violet" size="sm">{H.tag}</Tag>
          <span style={{ fontSize: 11, color: '#999' }}>基于你的选择生成</span>
        </div>
        <div style={{ marginTop: 14, fontSize: 20, fontWeight: 700, lineHeight: 1.5, color: '#1a1a1a', letterSpacing: -0.2, whiteSpace: 'pre-line' }}>
          {short}
        </div>

        {/* 正文卡 */}
        <div style={{ marginTop: 14, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5', padding: 14 }}>
          <div style={{ fontSize: 14, lineHeight: 1.85, color: '#333', whiteSpace: 'pre-line' }}>
            {highlightBody(body, H.highlight)}
          </div>
        </div>

        {/* 产品功能预览 */}
        {H.feature && (
          <>
            <div style={{ marginTop: 18, display: 'flex', alignItems: 'center', gap: 6 }}>
              <Eyebrow>相关能力 · FEATURE</Eyebrow>
              <span style={{ fontSize: 11, color: '#8A4BFF', fontWeight: 700 }}>{H.feature}</span>
            </div>
            <div style={{ marginTop: 8 }}>
              <FeaturePreview feature={H.feature}/>
            </div>
            <div style={{ marginTop: 8, fontSize: 10, color: '#999', lineHeight: 1.6, textAlign: 'center' }}>
              诊断完成后解锁完整版
            </div>
          </>
        )}
      </div>

      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        {H.qIdx >= H.total - 1 ? (
          <>
            <PrimaryBtn onClick={onNext}>生成完整诊断报告 →</PrimaryBtn>
            <div style={{ textAlign: 'center', fontSize: 11, color: '#AAA', marginTop: 8 }}>所有问题已完成 · 即将输出专属报告</div>
          </>
        ) : (
          <>
            <PrimaryBtn onClick={onNext}>下一题 →</PrimaryBtn>
            <div style={{ textAlign: 'center', fontSize: 11, color: '#AAA', marginTop: 8 }}>剩 {H.total - H.qIdx - 1} 题 · 约 30 秒</div>
          </>
        )}
      </div>
    </Frame>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 版本 2：深色告警页（把这一条诊断做成"高冲击"）
// 适合严重信号（表白+被拒、好人卡+冷淡等），冲击感最强
// ═══════════════════════════════════════════════════════════════════════
function CardHook_V2_DarkAlert({ onNext, onBack, hookKey = 'A3' }) {
  const H = getDemoHook(hookKey);
  return (
    <Frame bg="#1a1a2e" dark>
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10 }}>
        <button onClick={onBack} style={{ ...iconBtn36, background: 'rgba(255,255,255,.08)', borderColor: 'rgba(255,255,255,.2)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg>
        </button>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 2, color: 'rgba(255,255,255,.7)' }}>{H.qLabel.toUpperCase()} · READ</div>
        <div style={{ width: 36 }}/>
      </div>
      <div style={{ position: 'absolute', top: 94, left: 21, right: 21, display: 'flex', gap: 4, zIndex: 10 }}>
        {Array.from({length: H.total}).map((_, i) => (
          <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= H.qIdx ? '#FF65C2' : 'rgba(255,255,255,.15)' }}/>
        ))}
      </div>

      {/* 渐变球装饰 */}
      <div style={{ position: 'absolute', right: -60, top: 100, width: 200, height: 200, borderRadius: '50%', background: 'radial-gradient(circle,rgba(255,101,194,.35) 0%,transparent 70%)' }}/>
      <div style={{ position: 'absolute', left: -80, top: 380, width: 220, height: 220, borderRadius: '50%', background: 'radial-gradient(circle,rgba(138,75,255,.35) 0%,transparent 70%)' }}/>

      <div style={{ position: 'absolute', top: 110, bottom: 100, left: 0, right: 0, overflowY: 'auto', padding: '14px 21px 20px', zIndex: 2 }}>
        {/* Tag */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ padding: '3px 8px', borderRadius: 6, background: 'rgba(255,101,194,.2)', color: '#FFB4E6', fontSize: 10, fontWeight: 700, letterSpacing: 0.5 }}>⚠ {H.tag}</span>
          <span style={{ fontSize: 10, color: 'rgba(255,255,255,.5)' }}>AI · 即时</span>
        </div>
        {/* 大字标题 */}
        <div style={{ marginTop: 14, fontSize: 22, fontWeight: 700, lineHeight: 1.45, color: '#fff', letterSpacing: -0.3 }}>
          {H.short}
        </div>

        {/* 正文 */}
        <div style={{ marginTop: 18, padding: 18, background: 'rgba(255,255,255,.06)', borderRadius: 16, border: '0.5px solid rgba(255,255,255,.1)', backdropFilter: 'blur(10px)' }}>
          <div style={{ fontSize: 14, lineHeight: 1.85, color: 'rgba(255,255,255,.92)' }}>
            {highlightBody(H.body, H.highlight, true)}
          </div>
        </div>

        {/* 功能预览（深色包装） */}
        {H.feature && (
          <div style={{ marginTop: 20 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 2, color: 'rgba(255,255,255,.5)', marginBottom: 8 }}>
              ↓ 相关能力 · {H.feature}
            </div>
            <div style={{ background: '#fff', borderRadius: 14, padding: 4 }}>
              <FeaturePreview feature={H.feature}/>
            </div>
          </div>
        )}
      </div>

      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        <button onClick={onNext} style={{
          width: '100%', height: 52, borderRadius: 14, background: '#fff', color: '#1a1a2e',
          border: 'none', fontWeight: 700, fontSize: 16, cursor: 'pointer', fontFamily: 'inherit',
          boxShadow: '0 10px 30px rgba(0,0,0,.4)'
        }}>下一题 →</button>
        <div style={{ textAlign: 'center', fontSize: 11, color: 'rgba(255,255,255,.5)', marginTop: 8 }}>剩 {H.total - H.qIdx - 1} 题</div>
      </div>
    </Frame>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 版本 3：对话气泡页（小话老师在"跟你说话"）
// 保持诊所骨架，但用小话老师头像+气泡增加陪伴感
// 功能预览变成"附图卡片"挂在气泡下面
// ═══════════════════════════════════════════════════════════════════════
function CardHook_V3_Companion({ onNext, onBack, hookKey = 'A3' }) {
  const H = getDemoHook(hookKey);
  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '10px 21px 12px', zIndex: 10, background: '#F7F7FA', borderBottom: '0.5px solid #EEE' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <button onClick={onBack} style={iconBtn36}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 26, height: 26, borderRadius: '50%', background: '#fff', border: '0.5px solid #E5E0F5', overflow: 'hidden' }}>
              <img src="assets/teacher-avatar.png" style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt=""/>
            </div>
            <span style={{ fontSize: 13, fontWeight: 700 }}>小话老师 · 读到 {H.qLabel}</span>
          </div>
          <div style={{ width: 36 }}/>
        </div>
        <div style={{ marginTop: 10, display: 'flex', gap: 4 }}>
          {Array.from({length: H.total}).map((_, i) => (
            <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= H.qIdx ? '#8A4BFF' : '#E5E0F5' }}/>
          ))}
        </div>
      </div>

      <div style={{ position: 'absolute', top: 122, bottom: 100, left: 0, right: 0, overflowY: 'auto', padding: '14px 21px 20px', zIndex: 2 }}>
        {/* 用户选择气泡（淡） */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
          <div style={{ maxWidth: 260, padding: '8px 12px', borderRadius: '14px 4px 14px 14px', background: '#8A4BFF', color: '#fff', fontSize: 12, lineHeight: 1.5 }}>
            {hookKey === 'A3' ? '我选了：表白过 + 天天主动聊' : hookKey === 'A4' ? '我选了：好人卡 + 回复冷淡' : '我选了：同事'}
          </div>
        </div>

        {/* 小话老师气泡 */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#fff', border: '0.5px solid #E5E0F5', overflow: 'hidden', flexShrink: 0 }}>
            <img src="assets/teacher-avatar.png" style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt=""/>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ background: '#fff', borderRadius: '4px 16px 16px 16px', padding: '12px 14px', border: '0.5px solid #E5E0F5' }}>
              <Tag tone="violet" size="xs">{H.tag}</Tag>
              <div style={{ marginTop: 8, fontSize: 14, lineHeight: 1.8, color: '#222' }}>
                {highlightBody(H.body, H.highlight)}
              </div>
            </div>
            {/* 功能示意卡挂在气泡下 */}
            {H.feature && (
              <>
                <div style={{ marginTop: 10, fontSize: 11, color: '#8A4BFF', fontWeight: 600 }}>
                  ↓ 我会用这个能力帮你 · <b>{H.feature}</b>
                </div>
                <div style={{ marginTop: 6 }}>
                  <FeaturePreview feature={H.feature}/>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        <PrimaryBtn onClick={onNext}>下一题 →</PrimaryBtn>
      </div>
    </Frame>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 版本 4：双区块对比页（左"问题" + 右"我们怎么帮"）
// 信息结构最清晰——适合有组合诊断的复杂钩子
// 垂直上下堆叠（手机宽度下）：上方是问题诊断、下方是解决能力
// ═══════════════════════════════════════════════════════════════════════
function CardHook_V4_Split({ onNext, onBack, hookKey = 'A3' }) {
  const H = getDemoHook(hookKey);
  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10, background: '#F7F7FA' }}>
        <button onClick={onBack} style={iconBtn36}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
        <Eyebrow>诊断反馈 · {H.qLabel}</Eyebrow>
        <div style={{ width: 36 }}/>
      </div>
      <div style={{ position: 'absolute', top: 94, left: 21, right: 21, display: 'flex', gap: 4, zIndex: 10 }}>
        {Array.from({length: H.total}).map((_, i) => (
          <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= H.qIdx ? '#8A4BFF' : '#E5E0F5' }}/>
        ))}
      </div>

      <div style={{ position: 'absolute', top: 110, bottom: 100, left: 0, right: 0, overflowY: 'auto', padding: '14px 21px 20px', zIndex: 2 }}>
        {/* 上区：问题诊断（左边红色竖线强调） */}
        <div style={{ background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5', padding: 16, borderLeft: '3px solid #C00' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.5, color: '#C00' }}>PROBLEM · 我看到的问题</span>
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.45, color: '#1a1a1a' }}>{H.short}</div>
          <div style={{ marginTop: 10, fontSize: 13, lineHeight: 1.8, color: '#444' }}>
            {/* 把 body 切半 */}
            {splitBody(H.body, true)}
          </div>
        </div>

        {/* 下区：解决方案（左边紫色竖线强调） */}
        <div style={{ marginTop: 12, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5', padding: 16, borderLeft: '3px solid #8A4BFF' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.5, color: '#8A4BFF' }}>SOLUTION · 我们能帮你</span>
            {H.feature && <Tag tone="violet" size="xs">{H.feature}</Tag>}
          </div>
          <div style={{ fontSize: 13, lineHeight: 1.8, color: '#444' }}>
            {splitBody(H.body, false)}
          </div>

          {/* 功能卡 */}
          {H.feature && (
            <div style={{ marginTop: 12 }}>
              <FeaturePreview feature={H.feature}/>
            </div>
          )}
        </div>
      </div>

      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        <PrimaryBtn onClick={onNext}>下一题 →</PrimaryBtn>
        <div style={{ textAlign: 'center', fontSize: 11, color: '#AAA', marginTop: 8 }}>剩 {H.total - H.qIdx - 1} 题</div>
      </div>
    </Frame>
  );
}

// ─── helpers ───

// 在正文中把 highlight 词高亮
function highlightBody(body, highlight, isDark) {
  if (!body) return null;
  if (!highlight) return body;
  const parts = body.split(highlight);
  if (parts.length < 2) return body;
  return parts.map((p, i) =>
    i === 0 ? <React.Fragment key={i}>{p}</React.Fragment>
            : <React.Fragment key={i}>
                <span style={{
                  fontWeight: 700,
                  color: isDark ? '#FFB4E6' : '#8A4BFF',
                  background: isDark ? 'rgba(255,101,194,.15)' : 'rgba(138,75,255,.1)',
                  padding: '1px 4px', borderRadius: 4,
                }}>{highlight}</span>{p}
              </React.Fragment>
  );
}

// 把 body 按"问题描述 / 解决方案"大致切分
function splitBody(body, firstHalf) {
  if (!body) return null;
  // 大致按第一个句号或分号切
  const m = body.match(/^([^。；]+[。；])(.*)$/s);
  if (!m) return firstHalf ? body : '';
  return firstHalf ? m[1] : m[2];
}

const iconBtn36 = {
  width: 36, height: 36, borderRadius: 10,
  background: '#fff', border: '0.5px solid #E5E0F5',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer',
};

Object.assign(window, {
  CardHook_V1_Report, CardHook_V2_DarkAlert, CardHook_V3_Companion, CardHook_V4_Split,
  FeaturePreview,
});
