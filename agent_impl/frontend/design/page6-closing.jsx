// page6-closing.jsx — 总结钩子 + 生成报告过渡（loading）
// 这一页比较轻，2 版足够：一个"紧凑总结一句话"，一个"双阶段过渡"

// ═══════════════════════════════════════════════════════════════════════
// 版本 1：总结钩子（静态短页） + 大按钮进入报告
// ═══════════════════════════════════════════════════════════════════════
function Closing_V1_Summary({ onNext, onBack }) {
  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '14px 21px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', zIndex: 10, background: '#F7F7FA' }}>
        <button onClick={onBack} style={iconBtn36Closing}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#333" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg></button>
        <Eyebrow>诊断完成 · WRAP UP</Eyebrow>
        <div style={{ width: 36 }}/>
      </div>
      {/* 进度条满 */}
      <div style={{ position: 'absolute', top: 94, left: 21, right: 21, display: 'flex', gap: 4, zIndex: 10 }}>
        {Array.from({length: 5}).map((_, i) => (
          <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: '#8A4BFF' }}/>
        ))}
      </div>

      <div style={{ position: 'absolute', top: 114, bottom: 100, left: 0, right: 0, padding: '20px 21px', zIndex: 2, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 44, height: 44, borderRadius: '50%', background: '#fff', border: '0.5px solid #E5E0F5', overflow: 'hidden' }}>
            <img src="assets/teacher-avatar.png" style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt=""/>
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700 }}>小话老师</div>
            <div style={{ fontSize: 11, color: '#4CAF50' }}>诊断已完成 · 准备生成报告</div>
          </div>
        </div>

        <div style={{ marginTop: 28, fontSize: 20, fontWeight: 700, lineHeight: 1.5, letterSpacing: -0.2 }}>
          好，你的情况我基本了解了。
        </div>
        <div style={{ marginTop: 12, fontSize: 15, lineHeight: 1.85, color: '#444' }}>
          老实说，你的情况我之前见过很多类似的——<b style={{ color: '#8A4BFF' }}>表白过+高投入但对方在拉距离</b>，这在早期关系里属于"明牌后的回撤"。这类情况成功扭转的关键不是加大投入，而是<b style={{ color: '#8A4BFF' }}>重置节奏</b>。
        </div>
        <div style={{ marginTop: 14, fontSize: 14, lineHeight: 1.7, color: '#555' }}>
          接下来我会给你生成一份完整诊断，把问题的根源、你现在的位置、以及下一步的推进路径说清楚。
        </div>

        {/* 小统计条 */}
        <div style={{ marginTop: 'auto', padding: 14, background: '#fff', borderRadius: 14, border: '0.5px solid #E5E0F5' }}>
          <div style={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center' }}>
            <div>
              <div style={{ fontFamily: 'DM Sans', fontSize: 20, fontWeight: 700, color: '#8A4BFF' }}>3</div>
              <div style={{ fontSize: 10, color: '#999', marginTop: 2 }}>关键问题</div>
            </div>
            <div style={{ width: 1, background: '#E5E0F5' }}/>
            <div>
              <div style={{ fontFamily: 'DM Sans', fontSize: 20, fontWeight: 700, color: '#8A4BFF' }}>ACR</div>
              <div style={{ fontSize: 10, color: '#999', marginTop: 2 }}>三维诊断</div>
            </div>
            <div style={{ width: 1, background: '#E5E0F5' }}/>
            <div>
              <div style={{ fontFamily: 'DM Sans', fontSize: 20, fontWeight: 700, color: '#8A4BFF' }}>15</div>
              <div style={{ fontSize: 10, color: '#999', marginTop: 2 }}>页报告</div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
        <PrimaryBtn onClick={onNext}>生成完整诊断报告 →</PrimaryBtn>
      </div>
    </Frame>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// 版本 2：loading 过渡页
// 动效方案：Aurora Halo（极光光晕）—— conic-gradient 旋转 + 光晕呼吸 + 吉祥物轻浮
// 没有"转圈"的土味 · AI 感 + 治愈感
// ═══════════════════════════════════════════════════════════════════════
function Closing_V2_Loading({ onNext }) {
  React.useEffect(() => {
    const t = setTimeout(() => onNext?.(), 9999); // 演示不自动跳
    return () => clearTimeout(t);
  }, [onNext]);
  return (
    <Frame bg="#F7F7FA">
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 40, zIndex: 2 }}>
        {/* Aurora Halo 动效容器 */}
        <div className="aurora-wrap">
          <div className="aurora-ring"/>
          <div className="aurora-glow"/>
          <img src="assets/mascot-new.png" className="aurora-mascot" alt=""/>
        </div>

        <div style={{ marginTop: 32, fontSize: 18, fontWeight: 700, textAlign: 'center', color: '#1a1a1a' }}>正在生成你的专属诊断…</div>
        <div style={{ marginTop: 16, fontSize: 12, color: '#666', textAlign: 'center', lineHeight: 1.9 }}>
          ✓ 比对 <b style={{ color: '#8A4BFF' }}>2,847</b> 个相似案例<br/>
          ✓ 分析 5 维关系健康数据<br/>
          ⋯ 识别你的隐藏隐患<br/>
          ⋯ 构建推进路线图
        </div>
        <div style={{ marginTop: 28, width: 200, height: 4, background: '#E5E0F5', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ width: '100%', height: '100%', background: 'linear-gradient(90deg,#8A4BFF,#FF65C2)', transformOrigin: 'left', animation: 'grow 2.4s ease-out' }}/>
        </div>
      </div>
      <style>{`
        .aurora-wrap{
          position:relative;
          width:180px;height:180px;
          display:grid;place-items:center;
          border-radius:50%;
          overflow:hidden;
        }
        .aurora-ring{
          position:absolute;inset:-18%;
          border-radius:50%;
          background:conic-gradient(from 0deg, #8A4BFF, #FF65C2, rgba(138,75,255,0) 40%, #8A4BFF);
          filter:blur(18px);
          animation:aurora-spin 2.4s linear infinite;
          opacity:.78;
        }
        .aurora-glow{
          position:absolute;inset:14%;
          border-radius:50%;
          background:radial-gradient(circle, #ffffff 0%, rgba(255,255,255,0) 68%);
          animation:aurora-breathe 2.4s ease-in-out infinite;
        }
        .aurora-mascot{
          position:relative;z-index:2;
          width:150px;height:150px;
          object-fit:contain;
          animation:aurora-float 2.4s ease-in-out infinite;
          filter:drop-shadow(0 10px 20px rgba(138,75,255,.25));
        }
        @keyframes aurora-spin{to{transform:rotate(360deg)}}
        @keyframes aurora-breathe{0%,100%{opacity:.4;transform:scale(.9)}50%{opacity:.9;transform:scale(1.05)}}
        @keyframes aurora-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}
        @keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
      `}</style>
    </Frame>
  );
}

const iconBtn36Closing = {
  width: 36, height: 36, borderRadius: 10,
  background: '#fff', border: '0.5px solid #E5E0F5',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  cursor: 'pointer',
};

Object.assign(window, { Closing_V1_Summary, Closing_V2_Loading });
