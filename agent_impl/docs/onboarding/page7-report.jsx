// page7-report.jsx — 诊断报告 + 付费页 3 版
// 所有版本都覆盖 brief 4.2 的 4 个区块：
//   ① 诊断报告（状态标签 / ACR 雷达 / 核心问题 / 趋势预判）
//   ② 付费内容预览（3 大块 × 3 子项，锁住）
//   ③ 信任背书（数据条 + 1-2 条短评）
//   ④ 付费 CTA（紧迫感文案 + 价格 + 包含列表 + 立即解锁）
// 差异点：视觉节奏、锁住内容的处理方式、CTA 的触达策略

// ─── 公共子组件：5 维健康度雷达（ACR + Trust + Reciprocity） ───
function ACRRadar({ data, size = 220, color = '#8A4BFF', darkMode }) {
  // data = { 'A': {score, note}, 'C': {...}, 'R': {...} }
  const keys = Object.keys(data);
  const cx = size / 2, cy = size / 2, r = size / 2 - 34;
  const angle = (i) => (Math.PI * 2 * i) / keys.length - Math.PI / 2;
  const pt = (i, v) => [cx + Math.cos(angle(i)) * r * v / 100, cy + Math.sin(angle(i)) * r * v / 100];
  const gridColor = darkMode ? 'rgba(255,255,255,.18)' : '#E5E0F5';
  const labelColor = darkMode ? 'rgba(255,255,255,.9)' : '#333';

  const rings = [0.25, 0.5, 0.75, 1].map(k =>
    keys.map((_, i) => pt(i, k * 100).join(',')).join(' ')
  );
  const dataPoly = keys.map((k, i) => pt(i, data[k].score).join(',')).join(' ');

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {rings.map((pts, i) => <polygon key={i} points={pts} fill="none" stroke={gridColor} strokeWidth="1"/>)}
      {keys.map((_, i) => {
        const [x, y] = pt(i, 100);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke={gridColor} strokeWidth="1"/>;
      })}
      <polygon points={dataPoly} fill={color} fillOpacity={0.22} stroke={color} strokeWidth="2" strokeLinejoin="round"/>
      {keys.map((k, i) => {
        const [x, y] = pt(i, data[k].score);
        return <circle key={i} cx={x} cy={y} r="4" fill={color}/>;
      })}
      {keys.map((k, i) => {
        const [x, y] = pt(i, 124);
        return (
          <text key={k} x={x} y={y} textAnchor="middle" dominantBaseline="middle"
                fontSize="11" fontWeight="700" fill={labelColor}>{k}</text>
        );
      })}
    </svg>
  );
}

// 状态标签色表
const STATE_STYLES = {
  '高危滑坡期': { bg: '#FFE6E6', color: '#C00' },
  '舒适区陷阱': { bg: '#FFEDE0', color: '#D85400' },
  '临门犹豫期': { bg: '#FFF6DC', color: '#A67500' },
  '信号过载期': { bg: '#FFEDE0', color: '#D85400' },
  '空白探索期': { bg: '#E8F1FF', color: '#0B5EFE' },
  '僵局观察期': { bg: '#F0EBFA', color: '#6B3FB0' },
};

// ═══════════════════════════════════════════════════════════════════════
// 版本 1：柔和长页（方案 B 基底 + 品牌浅紫渐变顶部）
// 仪式感来自"大号分数 + 状态胶囊"，ACR 雷达居中，锁住预览用模糊遮罩
// 付费 CTA 做成底部悬浮按钮
// ═══════════════════════════════════════════════════════════════════════
function Report_V1_SoftLong({ onPay, onBack }) {
  const D = window.buildDiagnosis();
  const stateStyle = STATE_STYLES[D.state.badge] || { bg: '#FFE6E6', color: '#C00' };

  return (
    <Frame bg="#FAFAFE">
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 240, background: 'linear-gradient(180deg,#F6EDFF 0%,#FAFAFE 100%)', zIndex: 0 }}/>

      {/* 顶部 */}
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10 }}>
        <button onClick={onBack} style={iconBtn36R}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
        <Eyebrow>诊断报告 · DIAGNOSIS</Eyebrow>
        <div style={{ width: 36 }}/>
      </div>

      <div style={{ position: 'absolute', top: 96, bottom: 90, left: 0, right: 0, overflowY: 'auto', padding: '10px 21px 40px', zIndex: 2 }}>
        {/* 状态胶囊 + 标题 */}
        <div style={{ textAlign: 'center', paddingTop: 8 }}>
          <span style={{ padding: '8px 18px', borderRadius: 999, background: stateStyle.bg, color: stateStyle.color, fontSize: 14, fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: stateStyle.color }}/>{D.state.badge}
          </span>
          <div style={{ marginTop: 14, fontSize: 24, fontWeight: 700, lineHeight: 1.4, color: '#1a1a1a', letterSpacing: -0.3 }}>
            你和 TA 现在处于<br/>「需要立刻介入」的阶段
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>基于 5 维健康度诊断 · 2,847 样本建模</div>
        </div>

        {/* ACR 雷达卡 */}
        <div style={{ marginTop: 22, background: '#fff', borderRadius: 18, padding: 18, boxShadow: '0 10px 30px rgba(105,124,255,.08)', border: '0.5px solid #E5E0F5' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>5 维关系健康度</div>
            <Eyebrow color="#999">5D MODEL</Eyebrow>
          </div>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <ACRRadar data={D.acr}/>
          </div>
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {Object.entries(D.acr).map(([k, v]) => (
              <div key={k} style={{ padding: '8px 10px', background: '#FAFAFC', borderRadius: 10, display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <span style={{ fontFamily: 'DM Sans', fontSize: 15, fontWeight: 700, color: v.score < 40 ? '#C00' : v.score < 60 ? '#E88F00' : '#8A4BFF', width: 30 }}>{v.score}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#333' }}>{k}</div>
                  <div style={{ fontSize: 11, color: '#666', marginTop: 2, lineHeight: 1.55 }}>{v.note}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 核心问题 */}
        <div style={{ marginTop: 22, display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>🔍 核心问题 · {D.problems.length} 条</div>
        </div>
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {D.problems.map((p, i) => <ProblemRow key={i} {...p} idx={i + 1}/>)}
        </div>

        {/* 趋势预判 */}
        <div style={{ marginTop: 18, padding: 14, background: 'linear-gradient(135deg,#FFE6E6,#FFF0F0)', borderRadius: 14, borderLeft: '3px solid #C00' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#C00', letterSpacing: 1, marginBottom: 6 }}>⚠ 趋势预判 · TREND</div>
          <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.65, color: '#1a1a1a' }}>{D.state.trend}。</div>
        </div>

        {/* 锁住内容预览 */}
        <div style={{ marginTop: 22, display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>🔒 解锁后你会拿到</div>
          <span style={{ fontSize: 11, color: '#999' }}>3 大能力 · 9 个子项</span>
        </div>
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <LockedSection title="完整局势分析" icon="📊" items={['对方心理画像', '关系走势预测', '核心阻力深度拆解']}/>
          <LockedSection title="专属行动规划" icon="🧭" items={['Phase 1（第 1-2 周）', 'Phase 2（第 3-4 周）', '关键里程碑清单']}/>
          <LockedSection title="即时行动指南" icon="🎯" items={['下一条消息怎么发', '本周朋友圈建设方案', '下次见面策略推演']}/>
        </div>

        {/* 信任背书 */}
        <div style={{ marginTop: 22, padding: 14, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#333' }}>💙 已帮助 2,847 人推进关系</span>
            <Tag tone="greenish" size="xs">最近 30 天</Tag>
          </div>
          <ReviewRow name="L 先生 · 29" text="报告看完我才发现是自己节奏出了问题，按方案调整 3 周后她主动约我了。"/>
          <div style={{ height: 1, background: '#F0EEF5', margin: '10px 0' }}/>
          <ReviewRow name="Y 女士 · 25" text="之前以为 TA 对我没感觉，诊断说我误读了——证据引用的很具体，说服我了。"/>
        </div>

        {/* 付费卡 */}
        <div style={{ marginTop: 20, background: 'linear-gradient(140deg,#3A1A6A 0%,#8A4BFF 60%,#FF65C2 120%)', borderRadius: 18, padding: 20, color: '#fff', position: 'relative', overflow: 'hidden', boxShadow: '0 20px 40px rgba(138,75,255,.3)' }}>
          <div style={{ position: 'absolute', right: -30, top: -30, width: 160, height: 160, borderRadius: '50%', background: 'rgba(255,255,255,.1)' }}/>
          <div style={{ position: 'relative', zIndex: 2 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 2, opacity: .8 }}>UNLOCK · 完整服务</div>
            <div style={{ fontSize: 18, fontWeight: 700, marginTop: 6, lineHeight: 1.35 }}>
              根据你的情况，窗口期约 2-3 周<br/>越早介入，扭转成本越低
            </div>
            <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13 }}>
              <Feat>完整局势深度分析 · ACR 每周刷新</Feat>
              <Feat>个性化行动规划 · 分阶段里程碑</Feat>
              <Feat>实时聊天指导 & 朋友圈策略</Feat>
              <Feat>7×24 小话军师陪跑</Feat>
            </div>
            <div style={{ marginTop: 18, display: 'flex', gap: 10 }}>
              <PriceChip title="包周" price="9.9" sub="体验版"/>
              <PriceChip title="包一个 Crush" price="99" sub="全程陪跑" featured/>
            </div>
          </div>
        </div>
      </div>

      {/* 底部悬浮 CTA */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '12px 21px 26px', background: 'linear-gradient(180deg,rgba(250,250,254,0) 0%,rgba(250,250,254,.95) 30%,#FAFAFE 100%)', zIndex: 10 }}>
        <PrimaryBtn onClick={onPay}>
          立即解锁 · ¥99 拿到完整方案
        </PrimaryBtn>
        <div style={{ fontSize: 11, color: '#999', textAlign: 'center', marginTop: 6 }}>💙 7 天无理由退款 · 内测专享价</div>
      </div>
    </Frame>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 版本 2：Dark Hero 报告（严肃 · 专业 · 数据驱动）
// 顶部深色 band + 白字大号数据；下方白底 ACR + 问题；锁住内容用编号 + 模糊
// CTA 做成白底醒目按钮在底部
// ═══════════════════════════════════════════════════════════════════════
function Report_V2_DarkHero({ onPay, onBack }) {
  const D = window.buildDiagnosis();
  const stateStyle = STATE_STYLES[D.state.badge];

  return (
    <Frame bg="#F7F7FA">
      {/* 顶部深色 band —— 延长至 360，覆盖 hero card 更稳 */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 360, background: 'linear-gradient(180deg,#1a1a2e 0%,#2d1b5e 100%)', zIndex: 0 }}/>

      {/* Sticky 顶部条：始终保留深色衬底 —— 解决"白字滚出深色区"的可读性问题 */}
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 20, color: '#fff', background: 'rgba(26,26,46,.75)', backdropFilter: 'blur(18px)', borderBottom: '0.5px solid rgba(255,255,255,.08)' }}>
        <button onClick={onBack} style={{ ...iconBtn36R, background: 'rgba(255,255,255,.1)', borderColor: 'rgba(255,255,255,.2)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg>
        </button>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 2, opacity: 0.8 }}>DIAGNOSTIC REPORT</div>
        <div style={{ fontSize: 10, opacity: 0.6 }}>ID · CR-428103</div>
      </div>

      <div style={{ position: 'absolute', top: 88, bottom: 0, left: 0, right: 0, overflowY: 'auto', padding: '10px 16px 30px', zIndex: 2 }}>
        {/* Hero card */}
        <div style={{ background: 'linear-gradient(160deg,rgba(255,255,255,.12),rgba(255,255,255,.05))', border: '0.5px solid rgba(255,255,255,.15)', borderRadius: 20, padding: 22, color: '#fff', backdropFilter: 'blur(20px)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ padding: '6px 14px', borderRadius: 999, background: stateStyle.bg, color: stateStyle.color, fontSize: 12, fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: stateStyle.color }}/>{D.state.badge}
            </span>
          </div>
          <div style={{ marginTop: 14, fontSize: 22, fontWeight: 700, lineHeight: 1.4, letterSpacing: -0.2 }}>
            你处于「需要立刻介入」的阶段
          </div>
          <div style={{ marginTop: 10, fontSize: 13, lineHeight: 1.7, opacity: 0.85 }}>
            {D.state.trend}。
          </div>

          {/* 5 维健康度 mini preview */}
          <div style={{ marginTop: 18, padding: 14, background: 'rgba(255,255,255,.08)', borderRadius: 14, border: '0.5px solid rgba(255,255,255,.12)' }}>
            <div style={{ fontSize: 10, letterSpacing: 1.5, opacity: 0.7, marginBottom: 10 }}>5 维健康度 · 吸引 / 舒适 / 张力 / 信任 / 回应</div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <ACRRadar data={D.acr} size={140} color="#FFB4E6" darkMode/>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {Object.entries(D.acr).map(([k, v]) => (
                  <div key={k}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10 }}>
                      <span style={{ opacity: 0.85 }}>{k}</span>
                      <span style={{ fontFamily: 'DM Sans', fontWeight: 700, color: v.score < 40 ? '#FF65C2' : v.score < 60 ? '#FFB4E6' : '#fff' }}>{v.score}</span>
                    </div>
                    <div style={{ marginTop: 3, height: 3, background: 'rgba(255,255,255,.12)', borderRadius: 2, overflow: 'hidden' }}>
                      <div style={{ width: `${v.score}%`, height: '100%', background: v.score < 40 ? '#FF65C2' : '#FFB4E6' }}/>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* 核心问题（白底） */}
        <div style={{ marginTop: 20, padding: '0 4px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>识别出的关键问题</div>
            <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>按严重程度降序</div>
          </div>
          <Tag tone="red" size="sm">{D.problems.length} 项</Tag>
        </div>
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
          {D.problems.map((p, i) => <ProblemRowFlat key={i} {...p} idx={i + 1}/>)}
        </div>

        {/* 锁住内容：用编号+模糊块 */}
        <div style={{ marginTop: 22, padding: '0 4px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 16, fontWeight: 700 }}>🔒 完整方案 · 3 大能力</div>
        </div>
        <div style={{ marginTop: 12, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5', padding: 4 }}>
          <LockedTableRow no="01" title="完整局势分析" items={['对方心理画像', '关系走势预测', '核心阻力深度拆解']}/>
          <LockedTableRow no="02" title="专属行动规划" items={['Phase 1 · 节奏重置', 'Phase 2 · 张力建立', '关键里程碑清单']}/>
          <LockedTableRow no="03" title="即时行动指南" items={['下一条消息怎么发', '本周朋友圈建设方案', '下次见面策略推演']} last/>
        </div>

        {/* 背书 */}
        <div style={{ marginTop: 18, padding: '12px 14px', background: '#fff', borderRadius: 12, fontSize: 12, color: '#666', display: 'flex', alignItems: 'center', gap: 8, border: '0.5px solid #E5E0F5' }}>
          <div style={{ display: 'flex' }}>
            {['#FF65C2','#8A4BFF','#BDA3FF'].map((c, i) =>
              <div key={i} style={{ width: 22, height: 22, borderRadius: '50%', background: c, border: '2px solid #fff', marginLeft: i > 0 ? -6 : 0 }}/>
            )}
          </div>
          已有 <b style={{ color: '#8A4BFF' }}>2,847</b> 人用此方案推进关系
        </div>

        {/* 底部渐变过渡带：白底 → 浅紫 → 深紫，让页面收尾柔和并与付费卡呼应 */}
        <div style={{ height: 80, margin: '0 -16px', background: 'linear-gradient(180deg, rgba(247,247,250,0) 0%, #F0EBFA 50%, #2d1b5e 100%)' }}/>

        {/* 付费卡：紧贴渐变带底端，视觉上与渐变"无缝衔接" */}
        <div style={{ margin: '0 -16px -30px', padding: '0 16px 30px', background: 'linear-gradient(180deg, #2d1b5e 0%, #1a1a2e 40%, #1a1a2e 100%)' }}>
          <div style={{ background: 'linear-gradient(160deg, #3A1A6A 0%, #1a1a2e 100%)', borderRadius: 20, padding: 22, color: '#fff', border: '0.5px solid rgba(255,255,255,.08)' }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 2, color: '#FF65C2' }}>UNLOCK</div>
            <div style={{ fontSize: 20, fontWeight: 700, marginTop: 6, lineHeight: 1.35 }}>
              窗口期约 2-3 周<br/>越早介入，扭转成本越低
            </div>
            <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13, opacity: 0.92 }}>
              <FeatDark>完整诊断 · PDF 导出</FeatDark>
              <FeatDark>3 阶段推进方案 · 里程碑可追踪</FeatDark>
              <FeatDark>每次关键对话前实时建议</FeatDark>
              <FeatDark>7 天 1 对 1 小话老师陪跑</FeatDark>
            </div>
            <div style={{ marginTop: 18, display: 'flex', gap: 10 }}>
              <PriceChipDark title="包周" price="9.9" sub="体验版"/>
              <PriceChipDark title="包一个 Crush" price="99" sub="推荐" featured/>
            </div>
            <button onClick={onPay} style={{
              width: '100%', height: 52, marginTop: 16, borderRadius: 14,
              background: '#fff', color: '#1a1a2e', border: 'none',
              fontWeight: 700, fontSize: 16, cursor: 'pointer', fontFamily: 'inherit',
              boxShadow: '0 10px 30px rgba(0,0,0,.3)'
            }}>立即解锁 · ¥99</button>
            <div style={{ fontSize: 11, opacity: 0.7, textAlign: 'center', marginTop: 10 }}>💙 7 天无理由退款</div>
          </div>
        </div>
      </div>
    </Frame>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 版本 3：分步式报告（Tab 切换：诊断 / 方案 / 付费）
// 报告很长 —— 用顶部 Tab 把报告/方案预览/付费切成 3 段；最后一 tab 才露价格
// 这样诊断页更专注；但 CTA 在每个 Tab 底部都放一个
// ═══════════════════════════════════════════════════════════════════════
function Report_V3_TabbedFocus({ onPay, onBack }) {
  const D = window.buildDiagnosis();
  const stateStyle = STATE_STYLES[D.state.badge];
  const [tab, setTab] = React.useState('diagnosis');

  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px 10px', zIndex: 10, background: '#F7F7FA' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <button onClick={onBack} style={iconBtn36R}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
          <Eyebrow>诊断报告</Eyebrow>
          <div style={{ width: 36 }}/>
        </div>
        {/* Tab */}
        <div style={{ marginTop: 12, padding: 4, background: '#fff', borderRadius: 999, border: '0.5px solid #E5E0F5', display: 'flex' }}>
          {[
            { k: 'diagnosis', t: '① 诊断' },
            { k: 'preview', t: '② 方案预览' },
            { k: 'pay', t: '③ 解锁' },
          ].map(x => (
            <button key={x.k} onClick={() => setTab(x.k)} style={{
              flex: 1, padding: '8px 0', border: 'none', borderRadius: 999,
              background: tab === x.k ? '#8A4BFF' : 'transparent',
              color: tab === x.k ? '#fff' : '#666',
              fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
            }}>{x.t}</button>
          ))}
        </div>
      </div>

      <div style={{ position: 'absolute', top: 136, bottom: 90, left: 0, right: 0, overflowY: 'auto', padding: '14px 21px 30px', zIndex: 2 }}>
        {tab === 'diagnosis' && (
          <>
            {/* 状态胶囊 */}
            <div style={{ textAlign: 'center' }}>
              <span style={{ padding: '7px 16px', borderRadius: 999, background: stateStyle.bg, color: stateStyle.color, fontSize: 13, fontWeight: 700, display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: stateStyle.color }}/>{D.state.badge}
              </span>
              <div style={{ marginTop: 12, fontSize: 20, fontWeight: 700, lineHeight: 1.45, letterSpacing: -0.2 }}>
                你处于「需要立刻介入」的阶段
              </div>
            </div>
            {/* ACR */}
            <div style={{ marginTop: 18, background: '#fff', borderRadius: 16, padding: 18, border: '0.5px solid #E5E0F5' }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>5 维关系健康度</div>
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <ACRRadar data={D.acr} size={200}/>
              </div>
              <div style={{ marginTop: 8 }}>
                {Object.entries(D.acr).map(([k, v], i) => (
                  <div key={k} style={{ padding: '8px 0', borderTop: i > 0 ? '0.5px solid #F0EEF5' : 'none', display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                    <span style={{ fontFamily: 'DM Sans', fontSize: 14, fontWeight: 700, color: v.score < 40 ? '#C00' : v.score < 60 ? '#E88F00' : '#8A4BFF', width: 28 }}>{v.score}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>{k}</div>
                      <div style={{ fontSize: 11, color: '#666', lineHeight: 1.55, marginTop: 2 }}>{v.note}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {/* 问题 */}
            <div style={{ marginTop: 18, fontSize: 14, fontWeight: 700 }}>🔍 核心问题 · {D.problems.length}</div>
            <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {D.problems.map((p, i) => <ProblemRow key={i} {...p} idx={i + 1}/>)}
            </div>
            {/* 趋势 */}
            <div style={{ marginTop: 18, padding: 14, background: 'linear-gradient(135deg,#FFE6E6,#FFF0F0)', borderRadius: 12, borderLeft: '3px solid #C00' }}>
              <Eyebrow color="#C00">⚠ 趋势预判</Eyebrow>
              <div style={{ marginTop: 6, fontSize: 14, fontWeight: 600, lineHeight: 1.65, color: '#1a1a1a' }}>{D.state.trend}。</div>
            </div>
            {/* CTA: 切到预览 */}
            <div style={{ marginTop: 20 }}>
              <button onClick={() => setTab('preview')} style={{
                width: '100%', height: 48, borderRadius: 12, background: '#fff', color: '#8A4BFF',
                border: '1.5px solid #8A4BFF', fontWeight: 700, fontSize: 14, cursor: 'pointer', fontFamily: 'inherit'
              }}>看完方案预览 →</button>
            </div>
          </>
        )}

        {tab === 'preview' && (
          <>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>🔒 付费解锁后你会看到</div>
            <div style={{ fontSize: 12, color: '#666', marginBottom: 14 }}>我们先让你看个开头——内容非常具体，不是模糊的"加油鸡汤"</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <PreviewTeaser icon="📊" title="局势分析 · 对方心理画像" teaser="她目前对你处于「混合信号」阶段——行为上保留距离（邀约拒绝、回复延迟），但未做出明确关系定性……"/>
              <PreviewTeaser icon="🧭" title="行动规划 · Phase 1（第 1-2 周）" teaser="Week 1：主动联系降到现在的 40%。不主动追问状态，不发长段文字。你的任务是……"/>
              <PreviewTeaser icon="💬" title="聊天指导 · 下一条消息" teaser="当她再次用「嗯嗯」敷衍回复时，不要追问、不要解释、直接……"/>
            </div>
            <div style={{ marginTop: 20 }}>
              <button onClick={() => setTab('pay')} style={{
                width: '100%', height: 48, borderRadius: 12, background: '#8A4BFF', color: '#fff',
                border: 'none', fontWeight: 700, fontSize: 14, cursor: 'pointer', fontFamily: 'inherit',
                boxShadow: '0 8px 24px rgba(138,75,255,.3)'
              }}>查看解锁方式 →</button>
            </div>
          </>
        )}

        {tab === 'pay' && (
          <>
            <div style={{ padding: 16, background: 'linear-gradient(135deg,#FFE6E6,#FFF0F0)', borderRadius: 14, borderLeft: '3px solid #C00' }}>
              <Eyebrow color="#C00">⚠ 窗口期仅 2-3 周</Eyebrow>
              <div style={{ marginTop: 6, fontSize: 14, fontWeight: 700, lineHeight: 1.5, color: '#1a1a1a' }}>越早介入，扭转成本越低</div>
              <div style={{ marginTop: 6, fontSize: 12, color: '#666', lineHeight: 1.6 }}>像你这种情况，每多等一周，「备胎」的心理定位就会被 TA 再强化一次。</div>
            </div>

            <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <PlanOption title="包周" price="9.9" sub="7 天完整报告访问权" selected={false}/>
              <PlanOption title="包一个 Crush" price="99" sub="完整方案 + 7 天 1对1 手把手指导" selected badge="90% 用户首选"/>
            </div>

            <div style={{ marginTop: 18, padding: 16, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#8A4BFF', marginBottom: 10 }}>「包一个 Crush」包含</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: 13, color: '#333' }}>
                <FeatLight>15 页完整诊断报告 · PDF 导出</FeatLight>
                <FeatLight>3 阶段推进方案 · 每日任务</FeatLight>
                <FeatLight>100+ 实战话术模板</FeatLight>
                <FeatLight>7 天 1 对 1 小话老师陪跑</FeatLight>
              </div>
            </div>

            <div style={{ marginTop: 16, padding: '12px 14px', background: '#F7F7FA', borderRadius: 10, fontSize: 11, color: '#666', textAlign: 'center' }}>
              💙 7 天无理由退款 · 已有 <b style={{ color: '#8A4BFF' }}>2,847</b> 人推进关系
            </div>
          </>
        )}
      </div>

      {/* 底部 CTA（在 pay tab 时突出） */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '12px 21px 26px', background: '#F7F7FA', borderTop: '0.5px solid #EEE', zIndex: 10 }}>
        <PrimaryBtn onClick={onPay}>
          {tab === 'pay' ? '立即解锁 · ¥99' : tab === 'preview' ? '查看解锁方式 →' : '生成专属方案 →'}
        </PrimaryBtn>
      </div>
    </Frame>
  );
}

// ─── sub components ───

function ProblemRow({ tag, title, evidence, severity, idx }) {
  const color = severity === 'high' ? '#C00' : severity === 'mid' ? '#E88F00' : '#0B5EFE';
  const bg    = severity === 'high' ? '#FFE6E6' : severity === 'mid' ? '#FFF4E0' : '#E8F1FF';
  return (
    <div style={{ background: '#fff', borderRadius: 14, padding: 14, border: '0.5px solid #E5E0F5' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontFamily: 'DM Sans', fontSize: 11, fontWeight: 700, color: '#999' }}>#{String(idx).padStart(2, '0')}</span>
        <span style={{ padding: '3px 8px', borderRadius: 6, background: bg, color, fontSize: 10, fontWeight: 700 }}>{tag}</span>
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, lineHeight: 1.4, color: '#1a1a1a' }}>{title}</div>
      <div style={{ fontSize: 12, color: '#666', marginTop: 6, lineHeight: 1.7 }}>{evidence}</div>
    </div>
  );
}
function ProblemRowFlat(props) {
  // Dark hero 配套的平底款
  return <ProblemRow {...props}/>;
}

function LockedSection({ title, icon, items }) {
  return (
    <div style={{ background: '#fff', borderRadius: 14, padding: 14, border: '0.5px solid #E5E0F5' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <span style={{ fontSize: 14, fontWeight: 700 }}>{title}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map((t, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', background: '#FAFAFC', borderRadius: 8 }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="#8A4BFF"><path d="M12 2a5 5 0 00-5 5v3H6a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2v-8a2 2 0 00-2-2h-1V7a5 5 0 00-5-5zm-3 8V7a3 3 0 016 0v3H9z"/></svg>
            <span style={{ fontSize: 12, color: '#666' }}>{t}</span>
            <span style={{ flex: 1, height: 6, margin: '0 6px', background: 'repeating-linear-gradient(90deg,#F0EEF5 0 8px,#FAFAFC 8px 16px)', borderRadius: 3 }}/>
          </div>
        ))}
      </div>
    </div>
  );
}

function LockedTableRow({ no, title, items, last }) {
  return (
    <div style={{ padding: 12, borderBottom: last ? 'none' : '0.5px solid #F0EEF5' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <span style={{ fontFamily: 'DM Sans', fontSize: 11, fontWeight: 700, color: '#8A4BFF' }}>{no}</span>
        <span style={{ fontSize: 14, fontWeight: 700 }}>{title}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#8A4BFF" style={{ marginLeft: 'auto' }}><path d="M12 2a5 5 0 00-5 5v3H6a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2v-8a2 2 0 00-2-2h-1V7a5 5 0 00-5-5zm-3 8V7a3 3 0 016 0v3H9z"/></svg>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, paddingLeft: 22 }}>
        {items.map((t, i) => (
          <div key={i} style={{ fontSize: 11, color: '#666', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>·</span>
            <span>{t}</span>
            <span style={{ flex: 1, height: 4, margin: '0 6px', background: 'repeating-linear-gradient(90deg,#F0EEF5 0 6px,#FAFAFC 6px 12px)', borderRadius: 2 }}/>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReviewRow({ name, text }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
      <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'linear-gradient(135deg,#F8EDFF,#FFF0F9)', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>🧑</div>
      <div>
        <div style={{ fontSize: 11, color: '#999', fontWeight: 600 }}>{name}</div>
        <div style={{ fontSize: 12, color: '#333', lineHeight: 1.6, marginTop: 2 }}>"{text}"</div>
      </div>
    </div>
  );
}

function Feat({ children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round"><path d="M20 6L9 17l-5-5"/></svg>
      <span>{children}</span>
    </div>
  );
}
function FeatDark({ children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FFB4E6" strokeWidth="2.5" strokeLinecap="round"><path d="M20 6L9 17l-5-5"/></svg>
      <span>{children}</span>
    </div>
  );
}
function FeatLight({ children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 18, height: 18, borderRadius: '50%', background: '#F8EDFF', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#8A4BFF" strokeWidth="3" strokeLinecap="round"><path d="M20 6L9 17l-5-5"/></svg>
      </div>
      <span>{children}</span>
    </div>
  );
}

function PriceChip({ title, price, sub, featured }) {
  return (
    <div style={{ flex: 1, padding: 14, borderRadius: 12,
      background: featured ? '#fff' : 'rgba(255,255,255,.14)',
      color: featured ? '#8A4BFF' : '#fff',
      position: 'relative' }}>
      {featured && <div style={{ position: 'absolute', right: -4, top: -8, padding: '3px 8px', borderRadius: 6, background: '#FF65C2', color: '#fff', fontSize: 10, fontWeight: 700 }}>推荐</div>}
      <div style={{ fontSize: 11, fontWeight: 600, opacity: featured ? 1 : 0.9 }}>{title}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 2, marginTop: 4 }}>
        <span style={{ fontSize: 11, fontWeight: 700 }}>¥</span>
        <span style={{ fontFamily: 'DM Sans', fontSize: 22, fontWeight: 700, lineHeight: 1 }}>{price}</span>
      </div>
      <div style={{ fontSize: 10, marginTop: 2, opacity: 0.75 }}>{sub}</div>
    </div>
  );
}
function PriceChipDark({ title, price, sub, featured }) {
  return (
    <div style={{ flex: 1, padding: 14, borderRadius: 12,
      background: featured ? 'linear-gradient(135deg,#FF65C2,#8A4BFF)' : 'rgba(255,255,255,.1)',
      color: '#fff', border: featured ? 'none' : '0.5px solid rgba(255,255,255,.2)',
      position: 'relative' }}>
      {featured && <div style={{ position: 'absolute', right: -4, top: -8, padding: '3px 8px', borderRadius: 6, background: '#FFE5A0', color: '#8A4BFF', fontSize: 10, fontWeight: 700 }}>推荐</div>}
      <div style={{ fontSize: 11, opacity: 0.85, fontWeight: 600 }}>{title}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 2, marginTop: 4 }}>
        <span style={{ fontSize: 11, fontWeight: 700 }}>¥</span>
        <span style={{ fontFamily: 'DM Sans', fontSize: 22, fontWeight: 700, lineHeight: 1 }}>{price}</span>
      </div>
      <div style={{ fontSize: 10, marginTop: 2, opacity: 0.75 }}>{sub}</div>
    </div>
  );
}

function PreviewTeaser({ icon, title, teaser }) {
  return (
    <div style={{ background: '#fff', borderRadius: 14, padding: 14, border: '0.5px solid #E5E0F5' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <span style={{ fontSize: 13, fontWeight: 700 }}>{title}</span>
      </div>
      <div style={{ fontSize: 12, color: '#333', lineHeight: 1.7 }}>{teaser}</div>
      <div style={{ marginTop: 8, padding: 8, background: '#FAFAFC', borderRadius: 8, fontSize: 11, color: '#999', display: 'flex', alignItems: 'center', gap: 6 }}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="#8A4BFF"><path d="M12 2a5 5 0 00-5 5v3H6a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2v-8a2 2 0 00-2-2h-1V7a5 5 0 00-5-5zm-3 8V7a3 3 0 016 0v3H9z"/></svg>
        解锁后查看完整内容
      </div>
    </div>
  );
}

function PlanOption({ title, price, sub, selected, badge }) {
  return (
    <div style={{ padding: 16, borderRadius: 14,
      background: selected ? 'linear-gradient(135deg,#F8EDFF,#FFF0F9)' : '#fff',
      border: selected ? '2px solid #8A4BFF' : '0.5px solid #E5E0F5',
      position: 'relative' }}>
      {badge && <div style={{ position: 'absolute', right: 12, top: -8, padding: '3px 10px', borderRadius: 6, background: '#FF65C2', color: '#fff', fontSize: 10, fontWeight: 700 }}>{badge}</div>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 22, height: 22, borderRadius: '50%', border: '2px solid ' + (selected ? '#8A4BFF' : '#CCC'), display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          {selected && <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#8A4BFF' }}/>}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 14, fontWeight: 700 }}>{title}</span>
            <span style={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: selected ? '#8A4BFF' : '#333' }}>¥</span>
              <span style={{ fontFamily: 'DM Sans', fontSize: 20, fontWeight: 700, color: selected ? '#8A4BFF' : '#333' }}>{price}</span>
            </span>
          </div>
          <div style={{ fontSize: 11, color: '#666', marginTop: 4 }}>{sub}</div>
        </div>
      </div>
    </div>
  );
}

const iconBtn36R = {
  width: 36, height: 36, borderRadius: 10,
  background: '#fff', border: '0.5px solid #E5E0F5',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer',
};

Object.assign(window, {
  Report_V1_SoftLong, Report_V2_DarkHero, Report_V3_TabbedFocus,
});
