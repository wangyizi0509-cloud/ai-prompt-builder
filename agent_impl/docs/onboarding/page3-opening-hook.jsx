// page3-opening-hook.jsx — 自由描述提交后的「首发钩子」独立页（3 版）
// 这是 Phase 2：AI 基于自由描述生成的个性化判断性反馈
// 3 句话以内、引用用户具体细节、诊所报告风

// ───────────────────────────────────────────────
// 版本 1：诊所"快速读数"风（卡片式数据报告感）
// 重点：顶部大标题判断 + 分层证据引用 + 小数据点
// ───────────────────────────────────────────────
function OpeningHook_V1_QuickRead({ onNext, onBack, userInput = window.DEMO_USER_INPUT }) {
  const hook = window.OPENING_HOOK;
  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10, background: '#F7F7FA' }}>
        <button onClick={onBack} style={iconBtnSmall}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
        <Eyebrow>首发诊断 · FIRST READ</Eyebrow>
        <div style={{ width: 36 }}/>
      </div>

      <div style={{ position: 'absolute', top: 94, bottom: 100, left: 0, right: 0, overflowY: 'auto', padding: '10px 21px 20px', zIndex: 2 }}>
        {/* Tag + 大标题 */}
        <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Tag tone="violet" size="sm">{hook.tag}</Tag>
          <span style={{ fontSize: 11, color: '#999' }}>基于你的描述即时生成</span>
        </div>
        <div style={{ marginTop: 14, fontSize: 20, fontWeight: 700, lineHeight: 1.45, color: '#1a1a1a', letterSpacing: -0.2 }}>
          {hook.title.split(/(「[^」]+」|"[^"]+")/g).map((seg, i) =>
            /[「"]/.test(seg)
              ? <span key={i} style={{ background: 'linear-gradient(transparent 60%,#FFE58A 60%)', padding: '0 2px' }}>{seg.replace(/[「」"]/g, '')}</span>
              : <React.Fragment key={i}>{seg}</React.Fragment>
          )}
        </div>

        {/* 正文 */}
        <div style={{ marginTop: 14, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5', padding: 14 }}>
          <div style={{ fontSize: 14, lineHeight: 1.8, color: '#333' }}>{hook.body}</div>
          {/* 三个关键词 */}
          <div style={{ marginTop: 12, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {hook.highlights.map((h, i) =>
              <span key={i} style={{ padding: '4px 10px', borderRadius: 999, background: '#FFF4E0', color: '#E88F00', fontSize: 11, fontWeight: 700 }}>⚠ {h}</span>
            )}
          </div>
        </div>

        {/* 证据引用 */}
        <div style={{ marginTop: 16 }}>
          <Eyebrow color="#999">EVIDENCE · 我从你的描述里看到了这些</Eyebrow>
        </div>
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {hook.evidences.map((e, i) => (
            <div key={i} style={{ background: '#fff', borderRadius: 10, padding: '10px 12px', border: '0.5px solid #E5E0F5', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <div style={{ fontFamily: 'DM Sans', fontSize: 12, fontWeight: 700, color: '#8A4BFF', flexShrink: 0, marginTop: 1 }}>#{i + 1}</div>
              <div style={{ fontSize: 12, color: '#333', lineHeight: 1.65 }}>{e}</div>
            </div>
          ))}
        </div>

        {/* 下一步指示 */}
        <div style={{ marginTop: 20, padding: 14, background: 'linear-gradient(135deg,#F8EDFF,#FFF0F9)', borderRadius: 14, border: '0.5px solid rgba(138,75,255,.15)' }}>
          <div style={{ fontSize: 12, color: '#6B3FB0', fontWeight: 700, marginBottom: 4 }}>下一步</div>
          <div style={{ fontSize: 13, color: '#333', lineHeight: 1.65 }}>
            接下来我会问你 <b>5 道补充题</b>，每题都不超过 15 秒——帮我把你的诊断精度再提升一档。
          </div>
        </div>
      </div>

      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        <PrimaryBtn onClick={onNext}>开始补充题 · 5 道</PrimaryBtn>
      </div>
    </Frame>
  );
}

// ───────────────────────────────────────────────
// 版本 2：深色警示风（dark hero 判断，冲击力最大）
// 重点：用深色背景 + 白字大字把"老实说"的冲击感最大化
// ───────────────────────────────────────────────
function OpeningHook_V2_DarkAlert({ onNext, onBack }) {
  const hook = window.OPENING_HOOK;
  return (
    <Frame bg="#1a1a2e" dark>
      {/* 顶部 */}
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10 }}>
        <button onClick={onBack} style={{ ...iconBtnSmall, background: 'rgba(255,255,255,.08)', borderColor: 'rgba(255,255,255,.2)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg>
        </button>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 2, color: 'rgba(255,255,255,.7)' }}>FIRST READ · 即时判断</div>
        <div style={{ width: 36 }}/>
      </div>

      {/* 渐变球装饰 */}
      <div style={{ position: 'absolute', right: -60, top: 60, width: 200, height: 200, borderRadius: '50%', background: 'radial-gradient(circle,rgba(255,101,194,.3) 0%,transparent 70%)' }}/>
      <div style={{ position: 'absolute', left: -80, top: 300, width: 220, height: 220, borderRadius: '50%', background: 'radial-gradient(circle,rgba(138,75,255,.35) 0%,transparent 70%)' }}/>

      <div style={{ position: 'absolute', top: 88, bottom: 100, left: 0, right: 0, overflowY: 'auto', padding: '14px 21px 20px', zIndex: 2 }}>
        {/* Intro */}
        <div style={{ fontSize: 13, color: '#BDA3FF', fontWeight: 600, marginBottom: 10 }}>读完你的描述，我想直接跟你说……</div>

        {/* 大字判断 */}
        <div style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.4, color: '#fff', letterSpacing: -0.3 }}>
          {hook.title}
        </div>

        {/* 三个关键词 */}
        <div style={{ marginTop: 14, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {hook.highlights.map((h, i) =>
            <span key={i} style={{ padding: '5px 12px', borderRadius: 999, background: 'rgba(255,101,194,.15)', color: '#FFB4E6', fontSize: 11, fontWeight: 700, border: '0.5px solid rgba(255,101,194,.3)' }}>⚠ {h}</span>
          )}
        </div>

        {/* 正文 */}
        <div style={{ marginTop: 22, padding: 18, background: 'rgba(255,255,255,.06)', borderRadius: 16, border: '0.5px solid rgba(255,255,255,.1)', backdropFilter: 'blur(10px)' }}>
          <div style={{ fontSize: 14, lineHeight: 1.85, color: 'rgba(255,255,255,.92)' }}>{hook.body}</div>
        </div>

        {/* 证据 */}
        <div style={{ marginTop: 20, fontSize: 10, fontWeight: 700, letterSpacing: 2, color: 'rgba(255,255,255,.5)' }}>
          EVIDENCE · 我引用了你说过的：
        </div>
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {hook.evidences.map((e, i) => (
            <div key={i} style={{ padding: '10px 12px', background: 'rgba(255,255,255,.04)', borderRadius: 10, borderLeft: '2px solid #FF65C2', fontSize: 12, color: 'rgba(255,255,255,.85)', lineHeight: 1.65 }}>
              {e}
            </div>
          ))}
        </div>

        {/* 底部暗示 */}
        <div style={{ marginTop: 24, padding: 14, background: 'rgba(255,255,255,.08)', borderRadius: 14, fontSize: 12, color: 'rgba(255,255,255,.85)', lineHeight: 1.7, display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <span style={{ fontSize: 16 }}>👉</span>
          <span>接下来 5 道题，每题不超过 15 秒——答完就能拿到完整诊断。</span>
        </div>
      </div>

      {/* CTA */}
      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        <button onClick={onNext} style={{
          width: '100%', height: 52, borderRadius: 14,
          background: '#fff', color: '#1a1a2e', border: 'none',
          fontWeight: 700, fontSize: 16, cursor: 'pointer', fontFamily: 'inherit',
          boxShadow: '0 10px 30px rgba(0,0,0,.4)'
        }}>继续 · 开始 5 道补充题</button>
      </div>
    </Frame>
  );
}

// ───────────────────────────────────────────────
// 版本 3：对话气泡+引用卡（保留诊所骨架 + 陪伴温度）
// 重点：顶部小话老师 + 引用你发的"截图/文字" + 判断卡
// ───────────────────────────────────────────────
function OpeningHook_V3_Companion({ onNext, onBack, userInput = window.DEMO_USER_INPUT }) {
  const hook = window.OPENING_HOOK;
  const userSnippet = userInput.split('\n')[0].slice(0, 60) + '……';
  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '10px 21px 12px', zIndex: 10, background: '#F7F7FA', borderBottom: '0.5px solid #EEE' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <button onClick={onBack} style={iconBtnSmall}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 26, height: 26, borderRadius: '50%', background: '#fff', border: '0.5px solid #E5E0F5', overflow: 'hidden' }}>
              <img src="assets/teacher-avatar.png" style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt=""/>
            </div>
            <span style={{ fontSize: 13, fontWeight: 700 }}>小话老师</span>
          </div>
          <div style={{ width: 36 }}/>
        </div>
      </div>

      <div style={{ position: 'absolute', top: 96, bottom: 100, left: 0, right: 0, overflowY: 'auto', padding: '14px 21px 20px', zIndex: 2 }}>
        {/* 用户输入回显（引用气泡） */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
          <div style={{ maxWidth: 260, padding: 12, borderRadius: '16px 4px 16px 16px', background: '#8A4BFF', color: '#fff', fontSize: 12, lineHeight: 1.6 }}>
            <div style={{ fontSize: 10, opacity: .7, marginBottom: 4 }}>你刚刚说</div>
            "{userSnippet}"
            <div style={{ marginTop: 6, fontSize: 10, opacity: .7 }}>+ 2 张聊天截图</div>
          </div>
        </div>

        {/* 小话老师"正在阅读" */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 14 }}>
          <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#fff', border: '0.5px solid #E5E0F5', overflow: 'hidden', flexShrink: 0 }}>
            <img src="assets/teacher-avatar.png" style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt=""/>
          </div>
          <div style={{ flex: 1, padding: '10px 12px', background: '#F0EEF5', borderRadius: '4px 14px 14px 14px', fontSize: 12, color: '#666', lineHeight: 1.6 }}>
            读完了，我看出几件事…
          </div>
        </div>

        {/* 判断卡片 */}
        <div style={{ background: '#fff', borderRadius: 16, padding: 16, border: '0.5px solid #E5E0F5', boxShadow: '0 6px 20px rgba(105,124,255,.06)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Tag tone="violet" size="sm">{hook.tag}</Tag>
            <span style={{ fontSize: 10, color: '#999' }}>AI 实时生成</span>
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, lineHeight: 1.5, color: '#1a1a1a' }}>
            {hook.title}
          </div>
          <div style={{ marginTop: 10, fontSize: 13, lineHeight: 1.8, color: '#444' }}>
            {hook.body}
          </div>
        </div>

        {/* 证据小条 */}
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 11, color: '#999', fontWeight: 600, marginBottom: 8 }}>💡 我从你的描述里看到了这些信号</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {hook.evidences.map((e, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '8px 10px', background: '#fff', borderRadius: 10, border: '0.5px dashed #D5CFE8', fontSize: 12, color: '#666', lineHeight: 1.6 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8A4BFF" strokeWidth="2" style={{ flexShrink: 0, marginTop: 2 }}><path d="M9 11l3 3 8-8M20 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2h11"/></svg>
                <span>{e}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 接下来 */}
        <div style={{ marginTop: 18, padding: 12, background: '#F7F7FA', borderRadius: 12, fontSize: 12, color: '#666', lineHeight: 1.6, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <span style={{ fontSize: 14 }}>👉</span>
          <span>接下来我会问你 <b style={{ color: '#8A4BFF' }}>5 道补充题</b>，每题不超过 15 秒，让诊断更精准。</span>
        </div>
      </div>

      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        <PrimaryBtn onClick={onNext}>继续 · 开始补充题</PrimaryBtn>
      </div>
    </Frame>
  );
}

const iconBtnSmall = {
  width: 36, height: 36, borderRadius: 10,
  background: '#fff', border: '0.5px solid #E5E0F5',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer',
};

Object.assign(window, {
  OpeningHook_V1_QuickRead, OpeningHook_V2_DarkAlert, OpeningHook_V3_Companion,
});
