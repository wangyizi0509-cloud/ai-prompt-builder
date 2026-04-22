// page4-question.jsx — 提问卡片页
// 按你的指示："风格用方案 B"——白底圆角 + 编号 + 细线 + Diagnostic Question 标签
// 但需求文档有单选/多选/自由输入/互斥逻辑，所以结构上比原方案 B 更完整
// 这里出 1 版（本组件风格确定），覆盖 3 种题型场景：单选 / 多选 / 多选+自由输入

// 核心组件：一道题 = 头部 + 题目 + 选项 + （多选时）确认按钮
function QuestionCard({ Q, qIdx, total, selected, onSelect, onConfirm, onBack, otherText, onOtherChange }) {
  const isMulti = Q.type === 'multi';
  const sel = isMulti ? (selected || []) : selected;
  const hasSelection = isMulti ? sel.length > 0 : sel != null;

  function toggle(key) {
    if (isMulti) {
      let next = [...sel];
      const opt = Q.opts.find(o => o.key === key);
      if (opt.exclusive) {
        // 选 "以上都没有" → 清空其他
        next = next.includes(key) ? [] : [key];
      } else {
        // 选其他 → 取消 exclusive 项
        const exKey = Q.opts.find(o => o.exclusive)?.key;
        next = next.filter(k => k !== exKey);
        if (next.includes(key)) next = next.filter(k => k !== key);
        else next.push(key);
      }
      onSelect(next);
    } else {
      onSelect(key);
    }
  }

  return (
    <Frame bg="#F7F7FA">
      <ClinicalHeader qIdx={qIdx} total={total} onBack={onBack}/>

      <div style={{ position: 'absolute', top: 120, bottom: isMulti ? 100 : 30, left: 0, right: 0, overflowY: 'auto', padding: '14px 21px 20px', zIndex: 2 }}>
        {/* Q编号 + 副标题 */}
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <div style={{ fontFamily: 'DM Sans', fontSize: 40, fontWeight: 700, lineHeight: 0.9, color: '#8A4BFF' }}>Q{qIdx + 1}</div>
          <div style={{ flex: 1, padding: '4px 0 0' }}>
            <Eyebrow>DIAGNOSTIC QUESTION</Eyebrow>
            <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>{Q.sub}</div>
          </div>
        </div>

        {/* 题目 */}
        <div style={{ fontSize: 22, fontWeight: 700, lineHeight: 1.4, letterSpacing: -0.2, color: '#1a1a1a', marginTop: 14, marginBottom: 8 }}>
          {Q.q}
        </div>
        {isMulti && (
          <div style={{ fontSize: 11, color: '#8A4BFF', fontWeight: 600, marginBottom: 18 }}>
            ✦ 可多选 · 选完后点底部「确认」提交
          </div>
        )}
        {!isMulti && <div style={{ height: 14 }}/>}

        {/* 选项 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {Q.opts.map((opt, i) => {
            const isSel = isMulti ? sel.includes(opt.key) : sel === opt.key;
            const isOther = opt.withInput;
            return (
              <React.Fragment key={opt.key}>
                <button onClick={() => toggle(opt.key)} style={{
                  padding: '14px 16px', borderRadius: 12,
                  border: isSel ? '1.5px solid #8A4BFF' : '0.5px solid #E5E0F5',
                  background: isSel ? '#F8EDFF' : '#fff',
                  display: 'flex', alignItems: 'center', gap: 12,
                  cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left',
                  transition: 'all .15s ease-out',
                  boxShadow: isSel ? '0 6px 18px rgba(138,75,255,.15)' : 'none'
                }}>
                  {/* check / radio */}
                  <div style={{
                    width: 22, height: 22, borderRadius: isMulti ? 6 : '50%',
                    border: isSel ? 'none' : '1.5px solid #CCC',
                    background: isSel ? '#8A4BFF' : 'transparent',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
                  }}>
                    {isSel && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round"><path d="M20 6L9 17l-5-5"/></svg>}
                  </div>
                  <div style={{ flex: 1, fontSize: 14, fontWeight: 600, color: isSel ? '#8A4BFF' : '#333' }}>{opt.t}</div>
                </button>
                {/* 自由输入（选中"其他"时展开） */}
                {isSel && isOther && (
                  <div style={{ marginLeft: 32, marginTop: -2, marginBottom: 4 }}>
                    <input
                      value={otherText || ''}
                      onChange={e => onOtherChange?.(e.target.value)}
                      placeholder="请补充一下..."
                      style={{
                        width: '100%', padding: '10px 12px', borderRadius: 10,
                        border: '1.5px solid #BDA3FF', background: '#FBF7FF',
                        fontSize: 13, fontFamily: 'inherit', outline: 'none', color: '#333'
                      }}
                    />
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* 单选时的提示 */}
        {!isMulti && hasSelection && (
          <div style={{ marginTop: 14, textAlign: 'center', fontSize: 11, color: '#999' }}>
            已选择 · 将自动生成反馈
          </div>
        )}
      </div>

      {/* 多选时的底部确认 */}
      {isMulti && (
        <div style={{ position: 'absolute', left: 21, right: 21, bottom: 26, zIndex: 5 }}>
          <PrimaryBtn
            onClick={() => onConfirm?.(sel)}
            disabled={!hasSelection}
          >
            {hasSelection ? `确认 · 已选 ${sel.length} 项` : '请至少选择 1 项'}
          </PrimaryBtn>
        </div>
      )}
    </Frame>
  );
}

// 演示用：单选题示例（第 1 题 A1_rel，index=1 因为 A0 在 index=0）
function Question_V1_SingleDemo({ onNext, onBack }) {
  const [sel, setSel] = React.useState('colleague');
  return (
    <QuestionCard
      Q={window.QUESTIONS[1]} qIdx={0} total={5}
      selected={sel}
      onSelect={(k) => { setSel(k); setTimeout(onNext, 600); }}
      onBack={onBack}
    />
  );
}

// 演示用：多选题示例（第 3 题 A3_act，index=3 因为 A0 在 index=0）
function Question_V1_MultiDemo({ onNext, onBack }) {
  const [sel, setSel] = React.useState(['confess', 'chatting']);
  return (
    <QuestionCard
      Q={window.QUESTIONS[3]} qIdx={2} total={5}
      selected={sel}
      onSelect={setSel}
      onConfirm={onNext}
      onBack={onBack}
    />
  );
}

// 演示用：多选题含自由输入选项示例（第 3 题勾选"其他"时展开输入框）
function Question_V1_MultiWithOtherDemo({ onNext, onBack }) {
  const [sel, setSel] = React.useState(['confess', 'other']);
  const [other, setOther] = React.useState('');
  return (
    <QuestionCard
      Q={window.QUESTIONS[3]} qIdx={2} total={5}
      selected={sel}
      onSelect={setSel}
      onConfirm={onNext}
      onBack={onBack}
      otherText={other}
      onOtherChange={setOther}
    />
  );
}

Object.assign(window, {
  QuestionCard,
  Question_V1_SingleDemo, Question_V1_MultiDemo, Question_V1_MultiWithOtherDemo,
});
