// page5-card-hook.jsx — 卡片题选完后的「钩子独立页」4 版
// ★ 这是你最关注的页面 —— 根据用户的选择给一段诊断+关联产品能力预览
// 所有版本都保持方案 B 风：白底 / 细线 / 主色 #8A4BFF
// 4 版的差异 = 信息结构 + 交互 + 布局
//
// 以【第 3 题 · 行动历史】选择了 {confess, chatting}（=组合钩子 combo_confess_high）为例
// 每版都要覆盖：判断标题 / 正文 / 产品功能示例 / 下一步 CTA

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

// 一个小的"功能预览卡"——5 种功能用不同的微型 UI 来"示意截图"
// 这是为了对齐 brief 3.3 里说的"附带产品功能示例截图"
function FeaturePreview({ feature, variant = 'default' }) {
  if (!feature) return null;
  const frames = {
    '局势分析': <SituationFrame variant={variant}/>,
    '行动规划': <PlanFrame variant={variant}/>,
    '聊天指导': <ChatGuideFrame variant={variant}/>,
    '行动指南': <ActionGuideFrame variant={variant}/>,
    '朋友圈指导': <MomentsFrame variant={variant}/>,
  };
  return frames[feature] || null;
}

function SituationFrame({ variant }) {
  return (
    <div style={{ padding: 14, background: '#fff', borderRadius: 12, border: '0.5px solid #E5E0F5' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700 }}>📊 局势分析 · 现状快照</span>
        <Tag tone="amber" size="xs">T+3 天</Tag>
      </div>
      {/* ACR 条 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
        {[['吸引力 A', 52, '#8A4BFF'], ['舒适感 C', 68, '#8A4BFF'], ['张力 R', 18, '#C00']].map(([k, v, c], i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 58, fontSize: 10, color: '#666' }}>{k}</span>
            <div style={{ flex: 1, height: 5, background: '#F0EBFA', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ width: `${v}%`, height: '100%', background: c }}/>
            </div>
            <span style={{ fontFamily: 'DM Sans', fontSize: 11, fontWeight: 700, color: c, width: 22, textAlign: 'right' }}>{v}</span>
          </div>
        ))}
      </div>
      {/* 趋势线 */}
      <div style={{ padding: 8, background: '#FAFAFC', borderRadius: 8, fontSize: 10, color: '#666', display: 'flex', alignItems: 'center', gap: 6 }}>
        <svg width="40" height="12" viewBox="0 0 40 12">
          <polyline points="0,4 8,3 16,5 24,7 32,9 40,10" fill="none" stroke="#C00" strokeWidth="1.5"/>
        </svg>
        <span>张力持续下滑，预计 2 周内触底</span>
      </div>
    </div>
  );
}
function PlanFrame({ variant }) {
  return (
    <div style={{ padding: 14, background: '#fff', borderRadius: 12, border: '0.5px solid #E5E0F5' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 11, fontWeight: 700 }}>🧭 行动规划 · 3 阶段</span>
        <Tag tone="violet" size="xs">4 周</Tag>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {[
          { stage: 'Phase 1', week: 'W1-2', text: '回撤密度 · 重置节奏' },
          { stage: 'Phase 2', week: 'W3',   text: '制造稀缺 · 建立张力' },
          { stage: 'Phase 3', week: 'W4',   text: '精准邀约 · 推进关系' },
        ].map((p, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', background: i === 0 ? '#F8EDFF' : '#FAFAFC', borderRadius: 8 }}>
            <span style={{ fontFamily: 'DM Sans', fontSize: 10, fontWeight: 700, color: '#8A4BFF', width: 44 }}>{p.stage}</span>
            <span style={{ fontSize: 10, color: '#999', width: 32 }}>{p.week}</span>
            <span style={{ fontSize: 11, color: '#333', flex: 1 }}>{p.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
function ChatGuideFrame({ variant }) {
  return (
    <div style={{ padding: 14, background: '#fff', borderRadius: 12, border: '0.5px solid #E5E0F5' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 11, fontWeight: 700 }}>💬 聊天指导 · 逐条批注</span>
        <Tag tone="greenish" size="xs">实时</Tag>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ alignSelf: 'flex-start', maxWidth: '80%', padding: '6px 10px', background: '#F0EEF5', borderRadius: '10px 10px 10px 2px', fontSize: 11, color: '#333' }}>
          最近你都没主动找我玩了 😃
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', paddingLeft: 12 }}>
          <div style={{ padding: '2px 6px', background: '#FFF4E0', borderRadius: 4, fontSize: 9, fontWeight: 700, color: '#E88F00' }}>⚠ 试探</div>
          <span style={{ fontSize: 10, color: '#666' }}>建议：不解释 · 反问回去</span>
        </div>
        <div style={{ alignSelf: 'flex-end', maxWidth: '80%', padding: '6px 10px', background: '#8A4BFF', color: '#fff', borderRadius: '10px 10px 2px 10px', fontSize: 11, fontWeight: 500 }}>
          是你先不理我的吧？
        </div>
      </div>
    </div>
  );
}
function ActionGuideFrame({ variant }) {
  return (
    <div style={{ padding: 14, background: '#fff', borderRadius: 12, border: '0.5px solid #E5E0F5' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 700 }}>🎯 行动指南 · 邀约推演</span>
      </div>
      <div style={{ padding: 10, background: '#FAFAFC', borderRadius: 8, fontSize: 11, color: '#444', lineHeight: 1.6 }}>
        <div><b>时机：</b>周三晚 · 对方刚下班</div>
        <div style={{ marginTop: 4 }}><b>理由：</b>你偶然聊过的那部电影首映</div>
        <div style={{ marginTop: 4 }}><b>话术：</b>"…你不是想看这个吗，周六有场..."</div>
      </div>
      <div style={{ marginTop: 8, fontSize: 10, color: '#8A4BFF', display: 'flex', justifyContent: 'space-between' }}>
        <span>成功率预估 72%</span>
        <span>↗ vs 上周 +18%</span>
      </div>
    </div>
  );
}
function MomentsFrame({ variant }) {
  return (
    <div style={{ padding: 14, background: '#fff', borderRadius: 12, border: '0.5px solid #E5E0F5' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 11, fontWeight: 700 }}>📷 朋友圈指导 · 本周建设</span>
        <Tag tone="violet" size="xs">3 条</Tag>
      </div>
      <div style={{ display: 'flex', gap: 4 }}>
        {['📸 周二 · 晒风景', '🍳 周五 · 生活感', '🎧 周日 · 品味感'].map((t, i) => (
          <div key={i} style={{ flex: 1, padding: 6, background: 'linear-gradient(135deg,#FFF0F9,#F6F0FF)', borderRadius: 6, fontSize: 9, color: '#6B3FB0', textAlign: 'center', lineHeight: 1.4 }}>{t}</div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 版本 1：经典报告页（判断标题 · 正文 · 能力预览 · CTA）
// 结构最稳重，类似方案 B 的诊断卡——推荐作为默认
// ═══════════════════════════════════════════════════════════════════════
function CardHook_V1_Report({ onNext, onBack, hookKey = 'A3', hookData }) {
  const H = hookData || getDemoHook(hookKey);
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
        <div style={{ marginTop: 14, fontSize: 22, fontWeight: 700, lineHeight: 1.45, color: '#1a1a1a', letterSpacing: -0.2 }}>
          {H.short}
        </div>

        {/* 正文卡 */}
        <div style={{ marginTop: 14, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5', padding: 14 }}>
          <div style={{ fontSize: 14, lineHeight: 1.85, color: '#333' }}>
            {highlightBody(H.body, H.highlight)}
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
            <div style={{ marginTop: 8, fontSize: 11, color: '#999', lineHeight: 1.6 }}>
              👆 这是诊断完成后你会拿到的具体能力演示
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
