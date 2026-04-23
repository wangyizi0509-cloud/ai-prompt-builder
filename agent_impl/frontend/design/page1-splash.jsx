// page1-splash.jsx — 开屏页 3 版对比（全部沿用方案 B 诊所报告风）
// 共同要素：CRUSHE 品牌锚定 · "开始诊断"主 CTA · 可选的案例/好评
// 差异点：布局节奏、信任背书位置、主视觉（是否有 mascot / 是否用数据条 / 是否用报告封面感）

// ───────────────────────────────────────────────
// 版本 1：诊所 · 报告封面感（现有方案 B 的基础版微调）
// 重点：用"倾斜的报告卡片"作为主视觉，传达专业感
// ───────────────────────────────────────────────
function Splash_V1_ReportCover({ onNext }) {
  return (
    <Frame bg="#F7F7FA">
      {/* 顶部品牌条 */}
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '16px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10 }}>
        <Eyebrow>CRUSHE · 情感评估中心</Eyebrow>
        <span style={{ fontSize: 11, color: '#999' }}>v 2.4</span>
      </div>

      <div style={{ position: 'absolute', inset: 0, padding: '100px 24px 32px', display: 'flex', flexDirection: 'column', zIndex: 2 }}>
        {/* 报告封面视觉 */}
        <div style={{ margin: '0 auto', width: 170, height: 210, background: '#fff', borderRadius: 10,
          boxShadow: '0 20px 50px rgba(105,124,255,.15), 0 2px 6px rgba(0,0,0,.06)',
          padding: 18, position: 'relative', transform: 'rotate(-3deg)', border: '0.5px solid #E5E0F5' }}>
          <Eyebrow>DIAGNOSTIC REPORT</Eyebrow>
          <div style={{ marginTop: 6, fontSize: 11, color: '#222', fontWeight: 700 }}>个人情感评估</div>
          <div style={{ marginTop: 8, height: 2, background: 'linear-gradient(90deg,#8A4BFF,#FF65C2)', width: '40%' }}/>
          {/* 伪雷达 */}
          <svg width="134" height="90" viewBox="0 0 134 90" style={{ marginTop: 16 }}>
            {[0.35, 0.65, 1].map((k, i) =>
              <polygon key={i}
                points={[[67,8+(34-8)*(1-k)],[67+40*k,30+(60-30)*(1-k)*0+0],[67+25*k,68+(90-68)*(1-k)*0+0],[67-25*k,68+(90-68)*(1-k)*0+0],[67-40*k,30]].map(p=>p.join(',')).join(' ')}
                fill="none" stroke="#E5E0F5" strokeWidth="0.8"/>
            )}
            <polygon points="67,10 103,32 88,68 48,72 32,32" fill="#8A4BFF" fillOpacity=".28" stroke="#8A4BFF" strokeWidth="1.4"/>
          </svg>
          <div style={{ position: 'absolute', bottom: 14, left: 18, right: 18, height: 2, background: '#F0EBFA' }}>
            <div style={{ width: '68%', height: '100%', background: '#8A4BFF' }}/>
          </div>
          <div style={{ position: 'absolute', top: 12, right: 12, width: 30, height: 30, borderRadius: 6, background: '#FFE6E6', color: '#C00', fontSize: 8, fontWeight: 700, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', transform: 'rotate(15deg)', lineHeight: 1.1 }}>⚠<br/>预警</div>
        </div>

        <div style={{ marginTop: 34, textAlign: 'center' }}>
          <div style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.35, letterSpacing: -0.3 }}>
            3 分钟情感诊断<br/>找到 TA 态度变化的真实原因
          </div>
          <div style={{ marginTop: 12, fontSize: 13, color: '#666', lineHeight: 1.7 }}>
            基于 <b style={{ color: '#8A4BFF' }}>2,847</b> 个真实案例建模<br/>生成 3 维度 · 可量化 · 可追踪的诊断报告
          </div>
        </div>

        {/* 数据条 */}
        <div style={{ marginTop: 22, background: '#fff', borderRadius: 12, padding: 14, display: 'flex', justifyContent: 'space-around', boxShadow: '0 2px 10px rgba(0,0,0,.04)', border: '0.5px solid #E5E0F5' }}>
          <StatCell num="ACR" label="三维诊断"/>
          <DividerV/>
          <StatCell num="2,847" label="样本库"/>
          <DividerV/>
          <StatCell num="83%" label="识别准确率"/>
        </div>

        <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 11, color: '#999', textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#999" strokeWidth="2"><path d="M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6z"/></svg>
            匿名诊断 · 无需注册 · 本地处理
          </div>
          <PrimaryBtn onClick={onNext}>开始诊断 · 约 3 分钟</PrimaryBtn>
        </div>
      </div>
    </Frame>
  );
}

// ───────────────────────────────────────────────
// 版本 2：诊所 · 大字标题 + 短好评
// 重点：去掉封面视觉，用"一段判断性文案+好评墙"作为主视觉
// ───────────────────────────────────────────────
function Splash_V2_HeadlineReviews({ onNext }) {
  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '16px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10 }}>
        <Eyebrow>CRUSHE · 情感评估中心</Eyebrow>
        <Tag tone="violet" size="xs">BETA</Tag>
      </div>

      <div style={{ position: 'absolute', inset: 0, padding: '92px 24px 32px', display: 'flex', flexDirection: 'column', zIndex: 2 }}>
        {/* Logo 小图 */}
        <div style={{ width: 64, height: 64, borderRadius: 16, background: '#fff',
          boxShadow: '0 10px 30px rgba(105,124,255,.12)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: '0.5px solid #E5E0F5' }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="#8A4BFF">
            <path d="M12 2c.6 2.5 1.5 5 3 6.5s4 2.4 6.5 3c-2.5.6-5 1.5-6.5 3S12.6 18.5 12 21c-.6-2.5-1.5-5-3-6.5S5 12.1 2.5 11.5c2.5-.6 5-1.5 6.5-3S11.4 4.5 12 2z"/>
          </svg>
        </div>

        <div style={{ marginTop: 28, fontSize: 34, fontWeight: 700, lineHeight: 1.2, letterSpacing: -0.5 }}>
          帮你看清<br/>
          <span style={{ color: '#8A4BFF' }}>TA 对你到底是</span><br/>
          <span style={{ color: '#8A4BFF' }}>什么态度</span>
        </div>
        <div style={{ marginTop: 14, fontSize: 14, color: '#666', lineHeight: 1.7 }}>
          上传聊天截图 + 3 分钟诊断，拿到一份<b style={{ color: '#333' }}>你的专属情感局势报告</b>——我们会告诉你现在卡在哪里、下一步该怎么做。
        </div>

        {/* 好评墙（3 条短评 flex wrap） */}
        <div style={{ marginTop: 28, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <ReviewChip avatar="🧑🏻" name="L 先生 · 28" text="诊断完才发现是我自己把节奏搞砸了……"/>
          <ReviewChip avatar="👩🏻" name="Y 女士 · 25" text="之前以为他没感觉，报告说我完全错解了。"/>
          <ReviewChip avatar="🧑🏼" name="K 先生 · 30" text="比咨询朋友有用，是真的能给出下一步。"/>
        </div>

        <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <PrimaryBtn onClick={onNext}>开始诊断 · 约 3 分钟</PrimaryBtn>
          <div style={{ fontSize: 11, color: '#999', textAlign: 'center' }}>匿名 · 无需注册 · 已有 <b style={{ color: '#8A4BFF' }}>2,847</b> 人完成</div>
        </div>
      </div>
    </Frame>
  );
}

// ───────────────────────────────────────────────
// 版本 3：诊所 · 极简居中（医院导诊台类比）
// 重点：页面几乎只有品牌+CTA，把所有复杂元素挪到次页
// ───────────────────────────────────────────────
function Splash_V3_MinimalCenter({ onNext }) {
  return (
    <Frame bg="#fff">
      {/* 顶部细线 */}
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10, borderBottom: '0.5px solid #EEE' }}>
        <Eyebrow color="#8A4BFF">CRUSHE</Eyebrow>
        <span style={{ fontSize: 11, color: '#999' }}>情感评估中心</span>
      </div>

      <div style={{ position: 'absolute', inset: 0, padding: '120px 28px 40px', display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: 2 }}>
        {/* 大号 logomark + 柔雾 */}
        <div style={{ position: 'relative', marginTop: 40 }}>
          <div style={{ position: 'absolute', inset: -40, borderRadius: '50%',
            background: 'radial-gradient(circle,rgba(138,75,255,.14) 0%,transparent 70%)' }}/>
          <div style={{ width: 112, height: 112, borderRadius: 30, background: 'linear-gradient(180deg,#FFF0F9,#F6F0FF)', border: '4px solid #fff', boxShadow: '0 20px 50px rgba(105,124,255,.18)', overflow: 'hidden', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', position: 'relative' }}>
            <img src="assets/mascot-girl.png" style={{ width: '95%', objectFit: 'cover', objectPosition: 'top' }} alt=""/>
          </div>
        </div>

        <div style={{ marginTop: 28, fontFamily: 'DM Sans', fontSize: 38, fontWeight: 700, letterSpacing: -0.5, color: '#111' }}>CRUSHE</div>
        <div style={{ marginTop: 6, fontSize: 11, color: '#888', letterSpacing: 3 }}>让 语 言 更 加 触 动 人 心</div>

        <div style={{ marginTop: 40, textAlign: 'center', maxWidth: 300 }}>
          <div style={{ fontSize: 20, fontWeight: 700, lineHeight: 1.45, color: '#1a1a1a' }}>
            看清 TA 对你的真实态度<br/>知道下一步到底该怎么走
          </div>
          <div style={{ marginTop: 10, fontSize: 13, color: '#999', lineHeight: 1.7 }}>
            基于 2,847 案例建模的情感诊断 · 3 分钟生成
          </div>
        </div>

        <div style={{ marginTop: 'auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <PrimaryBtn onClick={onNext}>开始诊断</PrimaryBtn>
          <div style={{ fontSize: 11, color: '#AAA', textAlign: 'center' }}>匿名 · 免费 · 3 分钟</div>
        </div>
      </div>
    </Frame>
  );
}

// ───────────────────────────────────────────────
// 版本 4：诊所 · 三功能锚定（显性价值主张）
// 重点：把"诊断 / 规划 / 指导"三个核心能力用数字锚点展开
// ───────────────────────────────────────────────
function Splash_V4_ThreeAnchors({ onNext }) {
  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '16px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 22, height: 22, borderRadius: 6, background: '#8A4BFF', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="#fff"><path d="M12 2c.6 2.5 1.5 5 3 6.5s4 2.4 6.5 3c-2.5.6-5 1.5-6.5 3S12.6 18.5 12 21c-.6-2.5-1.5-5-3-6.5S5 12.1 2.5 11.5c2.5-.6 5-1.5 6.5-3S11.4 4.5 12 2z"/></svg>
          </div>
          <Eyebrow>CRUSHE</Eyebrow>
        </div>
        <span style={{ fontSize: 11, color: '#999' }}>情感评估中心</span>
      </div>

      <div style={{ position: 'absolute', inset: 0, padding: '88px 22px 28px', display: 'flex', flexDirection: 'column', zIndex: 2 }}>
        <div style={{ fontSize: 28, fontWeight: 700, lineHeight: 1.3, letterSpacing: -0.3 }}>
          三步，看清你和 TA<br/>到底卡在哪里
        </div>
        <div style={{ marginTop: 10, fontSize: 13, color: '#666', lineHeight: 1.7 }}>
          Crushe 是一个帮你"看清现状 → 制定方案 → 手把手执行"的 AI 军师
        </div>

        {/* 三功能锚点 */}
        <div style={{ marginTop: 28, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <AnchorRow idx="01" title="局势诊断" sub="3 维度量化 TA 对你的真实态度" tag="ACR 模型"/>
          <AnchorRow idx="02" title="行动规划" sub="分阶段、有里程碑的推进路线图" tag="分步可执行"/>
          <AnchorRow idx="03" title="实时指导" sub="关键对话前实时告诉你该怎么说" tag="7×24 陪跑"/>
        </div>

        {/* 案例缩略图墙（方案 B 风：不用大图，用小色块提示） */}
        <div style={{ marginTop: 20, padding: 14, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: '#333' }}>最近的诊断案例</span>
            <span style={{ fontSize: 11, color: '#999' }}>今日 +{147}</span>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {['同事 · 3 月', '网友 · 6 月', '同学 · 1 年', '偶遇 · 1 月', '相亲 · 2 月'].map((t, i) =>
              <div key={i} style={{
                padding: '4px 10px', borderRadius: 999, background: '#F7F7FA',
                fontSize: 11, color: '#666', border: '0.5px solid #E5E0F5'
              }}>{t}</div>
            )}
          </div>
        </div>

        <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <PrimaryBtn onClick={onNext}>开始诊断 · 约 3 分钟</PrimaryBtn>
          <div style={{ fontSize: 11, color: '#999', textAlign: 'center' }}>匿名 · 已有 <b style={{ color: '#8A4BFF' }}>2,847</b> 人完成诊断</div>
        </div>
      </div>
    </Frame>
  );
}

// ─── sub components ───
function StatCell({ num, label }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontFamily: 'DM Sans', fontSize: 18, fontWeight: 700, color: '#8A4BFF' }}>{num}</div>
      <div style={{ fontSize: 10, color: '#999', marginTop: 2 }}>{label}</div>
    </div>
  );
}
function DividerV() { return <div style={{ width: 1, background: '#E5E0F5' }}/>; }

function ReviewChip({ avatar, name, text }) {
  return (
    <div style={{ background: '#fff', borderRadius: 12, padding: '10px 12px', border: '0.5px solid #E5E0F5', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
      <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#F7F7FA', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>{avatar}</div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 11, color: '#999', fontWeight: 600 }}>{name}</div>
        <div style={{ fontSize: 12, color: '#333', lineHeight: 1.6, marginTop: 2 }}>"{text}"</div>
      </div>
    </div>
  );
}

function AnchorRow({ idx, title, sub, tag }) {
  return (
    <div style={{ background: '#fff', borderRadius: 14, padding: '14px 14px 14px 16px', border: '0.5px solid #E5E0F5', display: 'flex', gap: 14, alignItems: 'center' }}>
      <div style={{ fontFamily: 'DM Sans', fontSize: 20, fontWeight: 700, color: '#8A4BFF', lineHeight: 1, width: 30 }}>{idx}</div>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 700 }}>{title}</span>
          <Tag tone="violet" size="xs">{tag}</Tag>
        </div>
        <div style={{ fontSize: 11, color: '#888', marginTop: 2, lineHeight: 1.5 }}>{sub}</div>
      </div>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#CCC" strokeWidth="2"><path d="M9 6l6 6-6 6"/></svg>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// 【PM 最终版】融合方案：V3 极简居中骨架 + V2 用户真实发言 + 新吉祥物
// ═════════════════════════════════════════════════════════════
function Splash_FINAL({ onNext }) {
  return (
    <Frame bg="#fff">
      {/* 顶部细线 */}
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10, borderBottom: '0.5px solid #EEE' }}>
        <Eyebrow color="#8A4BFF">CRUSHE</Eyebrow>
        <span style={{ fontSize: 11, color: '#999' }}>情感评估中心</span>
      </div>

      <div style={{ position: 'absolute', inset: 0, padding: '82px 28px 26px', display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: 2 }}>
        {/* 新吉祥物 + 柔雾（无白色卡片框，保留透明 PNG） */}
        <div style={{ position: 'relative', marginTop: 10 }}>
          <div style={{ position: 'absolute', inset: -50, borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(255,101,194,.25) 0%, rgba(138,75,255,.18) 45%, transparent 72%)',
            filter: 'blur(8px)' }}/>
          <img src="assets/mascot-new.png" style={{ width: 180, height: 180, objectFit: 'contain', position: 'relative', zIndex: 2, filter: 'drop-shadow(0 16px 30px rgba(138,75,255,.25))' }} alt=""/>
        </div>

        <div style={{ marginTop: 14, fontFamily: 'DM Sans', fontSize: 36, fontWeight: 700, letterSpacing: -0.5, color: '#111' }}>CRUSHE</div>
        <div style={{ marginTop: 6, fontSize: 11, color: '#888', letterSpacing: 3 }}>让 语 言 更 加 触 动 人 心</div>

        <div style={{ marginTop: 22, textAlign: 'center', maxWidth: 310 }}>
          <div style={{ fontSize: 20, fontWeight: 700, lineHeight: 1.5, color: '#1a1a1a' }}>
            看清 TA 对你的真实态度<br/>知道下一步到底该怎么走
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: '#999', lineHeight: 1.7 }}>
            基于 2,847 案例建模 · 3 分钟生成诊断
          </div>
        </div>

        {/* 用户真实发言（V2 好评墙缩略版，3 条变 2 条以保持极简） */}
        <div style={{ marginTop: 'auto', width: '100%' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
            <ReviewChipFinal avatar="🧑🏻" name="L 先生 · 28" text="诊断完才发现是我自己把节奏搞砸了……"/>
            <ReviewChipFinal avatar="👩🏻" name="Y 女士 · 25" text="以为他没感觉，报告说我完全错解了。"/>
          </div>
          <PrimaryBtn onClick={onNext}>开始诊断</PrimaryBtn>
          <div style={{ fontSize: 11, color: '#AAA', textAlign: 'center', marginTop: 8 }}>匿名 · 免费 · 3 分钟</div>
        </div>
      </div>
    </Frame>
  );
}

function ReviewChipFinal({ avatar, name, text }) {
  return (
    <div style={{ background: '#FAFAFC', borderRadius: 10, padding: '8px 11px', border: '0.5px solid #EEE', display: 'flex', gap: 8, alignItems: 'center' }}>
      <div style={{ width: 22, height: 22, borderRadius: '50%', background: '#fff', border: '0.5px solid #E5E0F5', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, flexShrink: 0 }}>{avatar}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 10, color: '#999', fontWeight: 600 }}>{name}</div>
        <div style={{ fontSize: 11, color: '#333', lineHeight: 1.5, marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>"{text}"</div>
      </div>
    </div>
  );
}

Object.assign(window, {
  Splash_V1_ReportCover, Splash_V2_HeadlineReviews, Splash_V3_MinimalCenter, Splash_V4_ThreeAnchors,
  Splash_FINAL,
});
