// page2-freedesc.jsx — 自由描述 + 截图上传页（路径 A，必填）
// 所有版本都要求：至少 1 张截图 + 文字描述，"提交"按钮在两者都满足后点亮
// 诊所报告风：白底、圆角、细线分隔、主色 #8A4BFF

// ───────────────────────────────────────────────
// 版本 1：经典表单式（单卡片一体化）
// 重点：所有元素堆在一张白卡里，信息密度高，一屏完成
// ───────────────────────────────────────────────
function FreeDesc_V1_Compact({ onNext, onBack }) {
  const [text, setText] = React.useState(window.DEMO_USER_INPUT);
  const [imgs, setImgs] = React.useState([{ n: 'chat_0421.jpg' }, { n: 'chat_0422.jpg' }]);
  const canSubmit = text.trim().length >= 10 && imgs.length >= 1;

  return (
    <Frame bg="#F7F7FA">
      {/* header */}
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10, background: '#F7F7FA' }}>
        <button onClick={onBack} style={iconBtnStyle}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
        <Eyebrow>情感评估 · 开场</Eyebrow>
        <div style={{ width: 36 }}/>
      </div>

      {/* 进度条（自由描述是 step 0，共 6 步） */}
      <div style={{ position: 'absolute', top: 94, left: 21, right: 21, display: 'flex', gap: 4, zIndex: 10 }}>
        <ProgressBar current={0} total={6}/>
      </div>

      <div style={{ position: 'absolute', top: 110, bottom: 0, left: 0, right: 0, overflowY: 'auto', padding: '18px 21px 30px', zIndex: 2 }}>
        <div style={{ fontSize: 22, fontWeight: 700, lineHeight: 1.4, letterSpacing: -0.2 }}>
          最近是发生了什么，<br/>让你想来找军师帮忙？
        </div>
        <div style={{ fontSize: 12, color: '#999', marginTop: 8 }}>描述越具体，诊断越精准 · 我们会基于你的描述生成首条判断</div>

        {/* 白卡：文字 + 截图上传 */}
        <div style={{ marginTop: 20, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5', padding: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#666', letterSpacing: 1, marginBottom: 8 }}>① 用你的话简单说说</div>
          <textarea
            value={text} onChange={e => setText(e.target.value)}
            placeholder="可以说：你们怎么认识的、最近发生了什么让你纠结、你已经做过哪些尝试……"
            style={{
              width: '100%', minHeight: 108, padding: 10, borderRadius: 10,
              border: '0.5px solid #E5E0F5', background: '#FAFAFC',
              fontSize: 13, fontFamily: 'inherit', resize: 'none', lineHeight: 1.6, color: '#333',
              outline: 'none',
            }}
          />
          <div style={{ marginTop: 4, fontSize: 10, color: '#BBB', textAlign: 'right' }}>{text.length} 字</div>

          <div style={{ height: 1, background: '#F0EEF5', margin: '12px 0' }}/>

          <div style={{ fontSize: 11, fontWeight: 700, color: '#666', letterSpacing: 1, marginBottom: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>② 上传聊天截图 <span style={{ color: '#C00' }}>*</span></span>
            <span style={{ color: '#999', fontWeight: 500 }}>已上传 {imgs.length} 张 · 建议 2-4 张</span>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {imgs.map((img, i) => (
              <UploadThumb key={i} name={img.n} onRemove={() => setImgs(imgs.filter((_, j) => j !== i))}/>
            ))}
            {imgs.length < 6 && <UploadSlot onClick={() => setImgs([...imgs, { n: `shot_${imgs.length}.jpg` }])}/>}
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: '#999', lineHeight: 1.6, display: 'flex', gap: 6, alignItems: 'flex-start' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#999" strokeWidth="2" style={{ flexShrink: 0, marginTop: 2 }}><circle cx="12" cy="12" r="10"/><path d="M12 8v5M12 16h.01"/></svg>
            <span>最近 1-2 周的聊天记录最有价值。头像、对方昵称会自动马赛克处理。</span>
          </div>
        </div>
      </div>

      {/* 底部 CTA */}
      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        <PrimaryBtn onClick={onNext} disabled={!canSubmit}>
          {canSubmit ? '提交 · 开始诊断' : (text.trim().length < 10 ? '请先简单描述一下情况' : '请至少上传 1 张截图')}
        </PrimaryBtn>
      </div>
    </Frame>
  );
}

// ───────────────────────────────────────────────
// 版本 2：双步卡片式（上下两张独立卡）
// 重点：把"讲情况"和"传截图"拆成两张独立卡，视觉更清爽
// ───────────────────────────────────────────────
function FreeDesc_V2_Stacked({ onNext, onBack }) {
  const [text, setText] = React.useState(window.DEMO_USER_INPUT);
  const [imgs, setImgs] = React.useState([{ n: 'chat_0421.jpg' }, { n: 'chat_0422.jpg' }]);
  const canSubmit = text.trim().length >= 10 && imgs.length >= 1;

  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10, background: '#F7F7FA' }}>
        <button onClick={onBack} style={iconBtnStyle}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
        <Eyebrow>情感评估 · 开场</Eyebrow>
        <div style={{ width: 36 }}/>
      </div>
      <div style={{ position: 'absolute', top: 94, left: 21, right: 21, display: 'flex', gap: 4, zIndex: 10 }}>
        <ProgressBar current={0} total={6}/>
      </div>

      <div style={{ position: 'absolute', top: 110, bottom: 110, left: 0, right: 0, overflowY: 'auto', padding: '14px 21px', zIndex: 2 }}>
        <div style={{ fontSize: 22, fontWeight: 700, lineHeight: 1.4, letterSpacing: -0.2 }}>
          最近是发生了什么，让你想来找军师帮忙？
        </div>
        <div style={{ fontSize: 12, color: '#999', marginTop: 6 }}>我们会基于你的描述生成首条判断</div>

        {/* 卡片 1 · 文字 */}
        <StepCard idx="①" title="用你的话简单说说" required hint="建议 50 字以上" done={text.trim().length >= 10}>
          <textarea
            value={text} onChange={e => setText(e.target.value)}
            placeholder="怎么认识的、最近发生了什么让你纠结、已经做过哪些尝试……"
            style={{
              width: '100%', minHeight: 90, padding: 10, borderRadius: 10,
              border: '0.5px solid #E5E0F5', background: '#FAFAFC',
              fontSize: 13, fontFamily: 'inherit', resize: 'none', lineHeight: 1.6, color: '#333', outline: 'none',
            }}
          />
          <div style={{ marginTop: 4, fontSize: 10, color: '#BBB', textAlign: 'right' }}>{text.length} 字</div>
        </StepCard>

        {/* 卡片 2 · 截图 */}
        <StepCard idx="②" title="上传聊天截图" required hint={`已上传 ${imgs.length} 张`} done={imgs.length >= 1}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {imgs.map((img, i) => (
              <UploadThumb key={i} name={img.n} onRemove={() => setImgs(imgs.filter((_, j) => j !== i))}/>
            ))}
            {imgs.length < 6 && <UploadSlot onClick={() => setImgs([...imgs, { n: `shot_${imgs.length}.jpg` }])}/>}
          </div>
          <div style={{ marginTop: 10, padding: 10, background: '#F8EDFF', borderRadius: 8, fontSize: 11, color: '#6B3FB0', lineHeight: 1.6 }}>
            💡 建议上传最近 1-2 周的聊天记录。头像、昵称会自动马赛克处理。
          </div>
        </StepCard>
      </div>

      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        <PrimaryBtn onClick={onNext} disabled={!canSubmit}>
          {canSubmit ? '提交 · 开始诊断' : '完成两步后才能提交'}
        </PrimaryBtn>
      </div>
    </Frame>
  );
}

// ───────────────────────────────────────────────
// 版本 3：引导气泡式（小话老师 + 独立输入框）
// 重点：保留诊所风但加一点"AI 在陪你"的温度——顶部气泡提示，下方两个输入区块
// ───────────────────────────────────────────────
function FreeDesc_V3_Guided({ onNext, onBack }) {
  const [text, setText] = React.useState(window.DEMO_USER_INPUT);
  const [imgs, setImgs] = React.useState([{ n: 'chat_0421.jpg' }, { n: 'chat_0422.jpg' }]);
  const canSubmit = text.trim().length >= 10 && imgs.length >= 1;

  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10, background: '#F7F7FA' }}>
        <button onClick={onBack} style={iconBtnStyle}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
        <Eyebrow>情感评估 · 开场</Eyebrow>
        <div style={{ width: 36 }}/>
      </div>
      <div style={{ position: 'absolute', top: 94, left: 21, right: 21, display: 'flex', gap: 4, zIndex: 10 }}>
        <ProgressBar current={0} total={6}/>
      </div>

      <div style={{ position: 'absolute', top: 115, bottom: 110, left: 0, right: 0, overflowY: 'auto', padding: '10px 21px', zIndex: 2 }}>
        {/* 小话老师引导气泡 */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 18 }}>
          <div style={{ width: 38, height: 38, borderRadius: '50%', background: '#fff', border: '0.5px solid #E5E0F5', overflow: 'hidden', flexShrink: 0, display: 'flex', alignItems: 'flex-end', justifyContent: 'center' }}>
            <img src="assets/teacher-avatar.png" style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt=""/>
          </div>
          <div style={{ flex: 1, background: '#fff', borderRadius: '4px 14px 14px 14px', padding: '12px 14px', border: '0.5px solid #E5E0F5' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#8A4BFF', marginBottom: 4 }}>小话老师</div>
            <div style={{ fontSize: 13, lineHeight: 1.7, color: '#222' }}>
              最近是发生了什么，<b>让你想来找军师帮忙</b>？<br/>
              你简单说说、再传几张聊天截图，我就能给你第一个判断。
            </div>
          </div>
        </div>

        {/* 文字输入 */}
        <div style={{ background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5', padding: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <div style={{ width: 18, height: 18, borderRadius: '50%', background: '#8A4BFF', color: '#fff', fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>1</div>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#333' }}>用你的话说说情况</span>
            <Tag tone="red" size="xs">必填</Tag>
          </div>
          <textarea
            value={text} onChange={e => setText(e.target.value)}
            placeholder="你们怎么认识的、最近发生了什么让你纠结、已经做过哪些尝试……"
            style={{
              width: '100%', minHeight: 96, padding: 0, border: 'none', background: 'transparent',
              fontSize: 13, fontFamily: 'inherit', resize: 'none', lineHeight: 1.6, color: '#333', outline: 'none',
            }}
          />
          <div style={{ borderTop: '0.5px solid #F0EEF5', paddingTop: 8, marginTop: 6, fontSize: 10, color: '#BBB', display: 'flex', justifyContent: 'space-between' }}>
            <span>{text.length >= 10 ? '✓ 描述已足够' : `再写 ${Math.max(0, 10 - text.length)} 字`}</span>
            <span>{text.length} 字</span>
          </div>
        </div>

        {/* 截图上传 */}
        <div style={{ marginTop: 12, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5', padding: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
            <div style={{ width: 18, height: 18, borderRadius: '50%', background: '#8A4BFF', color: '#fff', fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>2</div>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#333' }}>上传聊天截图</span>
            <Tag tone="red" size="xs">必填</Tag>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: '#999' }}>{imgs.length}/6</span>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {imgs.map((img, i) => (
              <UploadThumb key={i} name={img.n} onRemove={() => setImgs(imgs.filter((_, j) => j !== i))}/>
            ))}
            {imgs.length < 6 && <UploadSlot onClick={() => setImgs([...imgs, { n: `shot_${imgs.length}.jpg` }])}/>}
          </div>
          <div style={{ marginTop: 10, padding: '8px 10px', background: '#E8F1FF', borderRadius: 8, fontSize: 11, color: '#0B5EFE', lineHeight: 1.6, display: 'flex', gap: 6, alignItems: 'flex-start' }}>
            <span style={{ marginTop: 1 }}>🔒</span>
            <span>截图只用于本次诊断。头像、昵称会自动马赛克，不会被存储到模型训练数据。</span>
          </div>
        </div>
      </div>

      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        <PrimaryBtn onClick={onNext} disabled={!canSubmit}>
          {canSubmit ? '提交 · 开始诊断' : '两项都填好之后才能提交'}
        </PrimaryBtn>
      </div>
    </Frame>
  );
}

// ───────────────────────────────────────────────
// 版本 4：聊天输入式（复用产品主对话形态）
// 重点：把自由描述做成一个"给小话老师发第一条消息"的聊天场景
// ───────────────────────────────────────────────
function FreeDesc_V4_ChatInput({ onNext, onBack }) {
  const [text, setText] = React.useState(window.DEMO_USER_INPUT);
  const [imgs, setImgs] = React.useState([{ n: 'chat_0421.jpg' }, { n: 'chat_0422.jpg' }]);
  const canSubmit = text.trim().length >= 10 && imgs.length >= 1;

  return (
    <Frame bg="#F7F7FA">
      {/* 顶部 */}
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '10px 21px 12px', zIndex: 10, background: 'rgba(247,247,250,.95)', backdropFilter: 'blur(20px)', borderBottom: '0.5px solid #EEE' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <button onClick={onBack} style={iconBtnStyle}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#fff', border: '0.5px solid #E5E0F5', overflow: 'hidden' }}>
              <img src="assets/teacher-avatar.png" style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt=""/>
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700 }}>小话老师</div>
              <div style={{ fontSize: 10, color: '#4CAF50', display: 'flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#4CAF50' }}/>在线 · 可随时发起诊断
              </div>
            </div>
          </div>
          <div style={{ width: 36 }}/>
        </div>
      </div>

      {/* 聊天区 */}
      <div style={{ position: 'absolute', top: 110, bottom: 180, left: 0, right: 0, overflowY: 'auto', padding: '20px 21px', zIndex: 2 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <div style={{ width: 32, height: 32, borderRadius: '50%', background: '#fff', border: '0.5px solid #E5E0F5', overflow: 'hidden', flexShrink: 0 }}>
            <img src="assets/teacher-avatar.png" style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt=""/>
          </div>
          <div style={{ background: '#fff', borderRadius: '4px 16px 16px 16px', padding: '12px 14px', border: '0.5px solid #E5E0F5', maxWidth: 280 }}>
            <div style={{ fontSize: 13, lineHeight: 1.7, color: '#222' }}>
              最近是发生了什么，让你想来找军师帮忙？
            </div>
            <div style={{ fontSize: 11, color: '#999', marginTop: 8, lineHeight: 1.6 }}>
              简单说说+传几张聊天截图就行。我会基于你的描述给你第一个判断。
            </div>
          </div>
        </div>

        {/* 小提示 */}
        <div style={{ textAlign: 'center', marginTop: 24, fontSize: 11, color: '#BBB' }}>
          你可以在下方输入 + 传截图 → 点发送
        </div>
      </div>

      {/* 底部输入条（模仿主产品聊天框） */}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: '14px 21px 26px', background: '#fff', borderTop: '0.5px solid #EEE', zIndex: 5 }}>
        {imgs.length > 0 && (
          <div style={{ display: 'flex', gap: 8, marginBottom: 10, overflowX: 'auto' }}>
            {imgs.map((img, i) => (
              <UploadThumb key={i} name={img.n} onRemove={() => setImgs(imgs.filter((_, j) => j !== i))} compact/>
            ))}
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, padding: 10, borderRadius: 14, border: '1px solid #BDA3FF', background: '#FAFAFC' }}>
          <button onClick={() => setImgs([...imgs, { n: `shot_${imgs.length}.jpg` }])} style={{
            width: 32, height: 32, borderRadius: 8, background: '#fff', border: '0.5px solid #E5E0F5',
            display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', flexShrink: 0
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#8A4BFF" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/></svg>
          </button>
          <textarea
            value={text} onChange={e => setText(e.target.value)}
            placeholder="说说你的情况……"
            style={{
              flex: 1, minHeight: 36, maxHeight: 120, padding: '8px 0',
              border: 'none', background: 'transparent', resize: 'none', outline: 'none',
              fontSize: 14, fontFamily: 'inherit', lineHeight: 1.5, color: '#333'
            }}
          />
          <button onClick={onNext} disabled={!canSubmit} style={{
            width: 36, height: 36, borderRadius: '50%',
            background: canSubmit ? '#8A4BFF' : '#E5E0F5', color: '#fff',
            border: 'none', cursor: canSubmit ? 'pointer' : 'not-allowed', flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: canSubmit ? '0 6px 18px rgba(138,75,255,.3)' : 'none'
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="#fff"><path d="M3 11l18-8-8 18-2-8z"/></svg>
          </button>
        </div>
        <div style={{ marginTop: 8, fontSize: 10, color: '#AAA', textAlign: 'center' }}>
          {canSubmit ? '✓ 可以提交了' : `至少 10 字 + 1 张截图（当前 ${text.length} 字 / ${imgs.length} 张）`}
        </div>
      </div>
    </Frame>
  );
}

// ─── sub components ───

function ProgressBar({ current, total }) {
  return Array.from({ length: total }).map((_, i) => (
    <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= current ? '#8A4BFF' : '#E5E0F5' }}/>
  ));
}

function StepCard({ idx, title, required, hint, done, children }) {
  return (
    <div style={{ marginTop: 14, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5', padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <div style={{ width: 22, height: 22, borderRadius: '50%',
          background: done ? '#8A4BFF' : '#F0EEF5',
          color: done ? '#fff' : '#666',
          fontSize: 11, fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }}>{done ? '✓' : idx}</div>
        <span style={{ fontSize: 13, fontWeight: 700 }}>{title}</span>
        {required && <Tag tone="red" size="xs">必填</Tag>}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: '#999' }}>{hint}</span>
      </div>
      {children}
    </div>
  );
}

function UploadThumb({ name, onRemove, compact }) {
  return (
    <div style={{
      width: compact ? 52 : 64, height: compact ? 52 : 64, borderRadius: 10,
      background: 'linear-gradient(135deg,#F8EDFF,#FFF0F9)',
      border: '0.5px solid #E5E0F5', position: 'relative',
      overflow: 'hidden', flexShrink: 0
    }}>
      {/* 伪聊天截图缩略 */}
      <div style={{ padding: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {[0.7, 0.5, 0.8, 0.4, 0.6].map((w, i) => (
          <div key={i} style={{
            height: 3, borderRadius: 2,
            background: i % 2 === 0 ? '#DFC9FF' : '#FFD3EE',
            width: `${w * 100}%`, marginLeft: i % 2 === 0 ? 0 : 'auto'
          }}/>
        ))}
      </div>
      <button onClick={onRemove} style={{
        position: 'absolute', right: -4, top: -4, width: 18, height: 18, borderRadius: '50%',
        background: '#1a1a1a', color: '#fff', border: '2px solid #fff', cursor: 'pointer',
        fontSize: 10, lineHeight: 1, display: 'flex', alignItems: 'center', justifyContent: 'center'
      }}>×</button>
    </div>
  );
}

function UploadSlot({ onClick }) {
  return (
    <button onClick={onClick} style={{
      width: 64, height: 64, borderRadius: 10,
      background: '#FAFAFC', border: '1.5px dashed #D5CFE8',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 2, cursor: 'pointer', fontFamily: 'inherit',
    }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8A4BFF" strokeWidth="2"><path d="M12 5v14M5 12h14"/></svg>
      <span style={{ fontSize: 9, color: '#8A4BFF', fontWeight: 600 }}>添加</span>
    </button>
  );
}

const iconBtnStyle = {
  width: 36, height: 36, borderRadius: 10,
  background: '#fff', border: '0.5px solid #E5E0F5',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer',
};

Object.assign(window, {
  FreeDesc_V1_Compact, FreeDesc_V2_Stacked, FreeDesc_V3_Guided, FreeDesc_V4_ChatInput,
});
