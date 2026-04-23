// shared.jsx — 最终版共享组件 + 题库 + 钩子文案
// 全部沿用方案 B（情感诊所 / Clinical Report）视觉语气：
// · 背景 #F7F7FA、白卡圆角 14、细线分隔 0.5px #E5E0F5
// · 主色 #8A4BFF，dark hero band #1a1a2e → #2d1b5e
// · 字体 DM Sans 用于数字/编号，Noto Sans SC 用于正文
// · 所有数据都可被各页面按需注入 / 覆写

// ─── iOS 375×812 设备外框（与现有交付包完全一致） ───
function Frame({ children, bg = '#F7F7FA', dark = false, style }) {
  const tint = dark ? '#fff' : '#000';
  return (
    <div style={{
      position: 'relative', width: 375, height: 812,
      background: bg, overflow: 'hidden', borderRadius: 44,
      boxShadow: '0 30px 80px rgba(105,124,255,.18), 0 0 0 10px #1a1a1a, 0 0 0 11px #333',
      fontFamily: '"Noto Sans SC","PingFang SC","Inter",sans-serif',
      color: tint, ...style
    }}>
      {/* status bar */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, height: 44, zIndex: 60,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 26px 0 32px', fontSize: 15, fontWeight: 600, color: tint
      }}>
        <span>9:41</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <svg width="16" height="10" viewBox="0 0 16 10">
            <rect x="0" y="6" width="3" height="4" rx="1" fill={tint}/>
            <rect x="4" y="4" width="3" height="6" rx="1" fill={tint}/>
            <rect x="8" y="2" width="3" height="8" rx="1" fill={tint}/>
            <rect x="12" y="0" width="3" height="10" rx="1" fill={tint}/>
          </svg>
          <svg width="14" height="10" viewBox="0 0 14 10">
            <path d="M7 2c2 0 4 .7 5.5 2l-1 1c-1.2-1-2.8-1.6-4.5-1.6s-3.3.6-4.5 1.6l-1-1C3 2.7 5 2 7 2zm0 3c1.3 0 2.5.4 3.5 1.2l-1 1c-.7-.6-1.6-.9-2.5-.9s-1.8.3-2.5.9l-1-1C4.5 5.4 5.7 5 7 5zm0 3c.8 0 1.4.6 1.4 1.4S7.8 9.8 7 9.8 5.6 9.2 5.6 8.4 6.2 7 7 7z" fill={tint}/>
          </svg>
          <svg width="26" height="12" viewBox="0 0 26 12">
            <rect x="0" y="1" width="22" height="10" rx="2.5" fill="none" stroke={tint} strokeOpacity=".4"/>
            <rect x="2" y="3" width="18" height="6" rx="1" fill={tint}/>
            <rect x="23" y="4" width="1.5" height="4" rx=".5" fill={tint} fillOpacity=".4"/>
          </svg>
        </span>
      </div>
      {children}
      <div style={{
        position: 'absolute', bottom: 8, left: '50%', transform: 'translateX(-50%)',
        width: 135, height: 5, borderRadius: 3, background: dark ? '#fff' : '#000', opacity: .85, zIndex: 60
      }}/>
    </div>
  );
}

// ─── 共用小组件 ───

function PrimaryBtn({ children, onClick, disabled, variant, style }) {
  const styles = {
    solid:   { bg: disabled ? '#BDA3FF' : '#8A4BFF', color: '#fff', shadow: '0 8px 24px rgba(138,75,255,.32)' },
    dark:    { bg: '#111', color: '#fff', shadow: '0 10px 30px rgba(0,0,0,.25)' },
    ghost:   { bg: '#fff', color: '#8A4BFF', shadow: '0 4px 14px rgba(105,124,255,.12)', border: '1px solid #E5E0F5' },
    outline: { bg: 'transparent', color: '#8A4BFF', shadow: 'none', border: '1.5px solid #8A4BFF' },
  };
  const s = styles[variant] || styles.solid;
  return (
    <button onClick={onClick} disabled={disabled} style={{
      width: '100%', height: 52, borderRadius: 14,
      background: s.bg, color: s.color, border: s.border || 'none',
      fontWeight: 600, fontSize: 16, cursor: disabled ? 'not-allowed' : 'pointer',
      fontFamily: 'inherit', boxShadow: disabled ? 'none' : s.shadow,
      transition: 'all .18s ease-out', ...style
    }}>{children}</button>
  );
}

function Tag({ children, tone = 'violet', size = 'sm' }) {
  const tones = {
    violet: { bg: '#F8EDFF', fg: '#8A4BFF' },
    blue:   { bg: '#E8F1FF', fg: '#0B5EFE' },
    red:    { bg: '#FFE6E6', fg: '#C00' },
    amber:  { bg: '#FFF4E0', fg: '#E88F00' },
    gray:   { bg: '#F0EEF5', fg: '#666' },
    greenish: { bg: '#E6F7F0', fg: '#0A8049' },
  };
  const t = tones[tone] || tones.violet;
  const pad = size === 'xs' ? '2px 6px' : size === 'md' ? '5px 12px' : '3px 8px';
  const fs  = size === 'xs' ? 9 : size === 'md' ? 12 : 10;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: pad, borderRadius: 6,
      background: t.bg, color: t.fg,
      fontSize: fs, fontWeight: 700, letterSpacing: 0.5
    }}>{children}</span>
  );
}

function Eyebrow({ children, color = '#8A4BFF' }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, letterSpacing: 2, color,
      textTransform: 'uppercase'
    }}>{children}</div>
  );
}

function ClinicalHeader({ qIdx, total, onBack }) {
  return (
    <div style={{ position: 'absolute', top: 44, left: 0, right: 0, padding: '18px 21px 14px', zIndex: 10, background: '#F7F7FA' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <button onClick={onBack} style={{ width: 36, height: 36, borderRadius: 10, background: '#fff', border: '0.5px solid #E5E0F5', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#333' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 6l-6 6 6 6"/></svg>
        </button>
        <div style={{ fontSize: 11, color: '#999', fontWeight: 600, letterSpacing: 1 }}>
          情感评估 · Q{qIdx + 1} / {total}
        </div>
        <div style={{ width: 36 }}/>
      </div>
      <div style={{ display: 'flex', gap: 4 }}>
        {Array.from({length: total}).map((_, i) => (
          <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= qIdx ? '#8A4BFF' : '#E5E0F5', transition: 'background .3s' }}/>
        ))}
      </div>
    </div>
  );
}

// ─── 题库（路径 A：有截图）===================================
// 与 onboarding_design_brief.md 3.3 一致：5 道题
const QUESTIONS = [
  {
    id: 'A1_rel',
    q: '你们是怎么认识的？',
    sub: '认识方式决定了后续策略的边界',
    type: 'single',
    opts: [
      { t: '同事（同公司 / 同团队）', key: 'colleague' },
      { t: '同学（同校 / 同班 / 同社团）', key: 'classmate' },
      { t: '网友（社交软件 / 游戏 / 社群）', key: 'online' },
      { t: '朋友介绍 / 相亲', key: 'intro' },
      { t: '线下偶遇（健身房 / 咖啡店 / 活动）', key: 'offline' },
      { t: '其他（补充一下）', key: 'other', withInput: true },
    ],
  },
  {
    id: 'A2_dur',
    q: '你们认识多久了？',
    sub: '时间窗口决定策略的紧迫度',
    type: 'single',
    opts: [
      { t: '不到 1 个月', key: 'lt1m' },
      { t: '1 – 3 个月',   key: '1to3m' },
      { t: '3 – 6 个月',   key: '3to6m' },
      { t: '半年到 1 年',   key: '6mto1y' },
      { t: '1 年以上',     key: 'gt1y' },
    ],
  },
  {
    id: 'A3_act',
    q: '到目前为止，你有没有做过下面这些事？',
    sub: '可多选 · 行动历史决定当前你的"明牌"程度',
    type: 'multi',
    exclusive: 'none',  // 选中 "以上都没有" 时互斥其余
    hookPriority: ['confess', 'rejected', 'expensive', 'public', 'chatting', 'asked', 'none'],
    opts: [
      { t: '主动表白 / 说过喜欢 TA',                 key: 'confess' },
      { t: '送过比较贵重的礼物',                      key: 'expensive' },
      { t: '频繁主动找 TA 聊天（每天主动开话题）',   key: 'chatting' },
      { t: '约过 TA 单独出来（成功）',               key: 'asked' },
      { t: '约过 TA 单独出来（被拒绝 / 被放鸽子）', key: 'rejected' },
      { t: '在社交场合对 TA 表现出明显不同',         key: 'public' },
      { t: '以上都没有，一直没敢有明显动作',         key: 'none', exclusive: true },
      { t: '其他（补充一下）',                        key: 'other', withInput: true },
    ],
  },
  {
    id: 'A4_neg',
    q: '下面这些情况，有发生在你身上的吗？',
    sub: '可多选 · TA 的负面信号强度分级',
    type: 'multi',
    exclusive: 'none2',
    hookPriority: ['friendzoned', 'toolman', 'refused', 'others_warm', 'cold_reply', 'slow_reply', 'none2'],
    opts: [
      { t: 'TA 回消息越来越慢 / 经常不回',          key: 'slow_reply' },
      { t: 'TA 聊天时很敷衍（嗯、哦、哈哈）',       key: 'cold_reply' },
      { t: 'TA 拒绝过单独见面',                     key: 'refused' },
      { t: 'TA 提过「我们就是朋友」/「你是好人」', key: 'friendzoned' },
      { t: 'TA 跟别人互动明显比跟你热情',           key: 'others_warm' },
      { t: 'TA 会主动找你，但只在需要帮忙的时候', key: 'toolman' },
      { t: '以上都没有，TA 对我还行',               key: 'none2', exclusive: true },
      { t: '其他（补充一下）',                       key: 'other', withInput: true },
    ],
  },
  {
    id: 'A5_goal',
    q: '你现在最想解决的是什么？',
    sub: '锁定目标后我们就能给你匹配最近的策略',
    type: 'single',
    opts: [
      { t: '想确认关系 / 在一起',                    key: 'commit' },
      { t: '想先拉近距离 / 让 TA 对我更有好感',     key: 'closer' },
      { t: '想知道 TA 到底什么态度 / 有没有机会',   key: 'probe' },
      { t: '关系倒退了，想挽回 / 修复',              key: 'recover' },
      { t: '不确定该不该继续追 / 想听听专业判断',   key: 'decide' },
    ],
  },
];

// ─── 每题选完后的钩子文案（独立页用）=======================================
// hint: 钩子短版（可做小卡一句话展示）
// hookBody: 独立页主文（来自 brief 文档原文）
// feature: 对应的产品功能配图 key（或 null）
const HOOKS_A1 = {
  colleague: { short: '同事关系有天然优势，也有十倍放大的尴尬。', body: '同事关系有个天然优势：日常接触机会多。但也有个隐藏风险——如果策略不对，尴尬会被放大十倍，因为你们天天见面。', feature: null, tag: '情境特征' },
  classmate: { short: '同学之间最容易掉进"好哥们 / 好闺蜜"陷阱。', body: '同学之间最容易掉进「好哥们／好闺蜜」的陷阱。舒适感有了，但张力起不来——这是我见过最多的卡点。', feature: null, tag: '情境特征' },
  online:    { short: '最关键的变量是：有没有建立线下锚点。', body: '线上认识的情况，最关键的变量是：你们有没有建立线下的锚点。纯线上聊天很容易变成「赛博笔友」。', feature: null, tag: '情境特征' },
  intro:     { short: '经人介绍，对方会过度解读你的每一步。', body: '经人介绍的关系有个特殊性——双方一开始就知道这是「相亲性质」，所以对方对你的每一步动作都会过度解读。这是把双刃剑。', feature: null, tag: '情境特征' },
  offline:   { short: '线下偶遇的机会窗口很快会关闭。', body: '线下偶遇的最大问题是联系窗口不稳定。如果没有建立固定的互动渠道，机会窗口会很快关闭。', feature: null, tag: '情境特征' },
  other:     null,
};
const HOOKS_A2 = {
  lt1m:   { short: '早期策略空间最大，别犯不可逆错误。', body: '还在早期，好消息是对方对你的印象还没固化，策略空间很大。关键是别在这个阶段犯一些不可逆的错误。', feature: null, tag: '时间诊断' },
  '1to3m':{ short: '黄金窗口——对方已经在形成印象了。', body: '这个阶段很关键——对方已经对你形成初步印象了。如果现在还没有明确的升温信号，说明有些东西需要调整。', feature: null, tag: '时间诊断' },
  '3to6m':{ short: '某个环节卡住了，现在调整还不算晚。', body: '认识快半年了，如果关系还没有实质性进展，大概率是某个环节卡住了。好在现在调整还不算晚。', feature: null, tag: '时间诊断' },
  '6mto1y':{ short: '你很可能已经被归类了——但可以打破。', body: '半年以上还停在这个阶段，有一个你可能不想听的事实：你很可能已经被归类了。但归类不是终局，是可以打破的。', feature: null, tag: '时间诊断' },
  gt1y:   { short: '定位已固化，逆转案例我见过很多。', body: '认识超过一年了……说实话，时间越长，对方的心理定位越固化。不过我见过很多逆转案例，关键是策略要对。', feature: null, tag: '时间诊断' },
};
// A3/A4 多选钩子 —— 由 pickHook() 按优先级选择
const HOOKS_A3 = {
  confess:   { short: '你现在在"明牌"状态下互动。', body: '已经表白过了……这意味着对方现在是在「明牌」状态下跟你互动的。接下来每一步都会被对方用"他喜欢我"这个滤镜来解读。不过别慌——我们可以帮你做一个动态的局势分析，追踪对方态度的变化趋势，找到重新打开局面的窗口期。', feature: '局势分析', highlight: '动态的局势分析', tag: '高暴露预警' },
  expensive: { short: '高低位可能已经失衡，需要系统修复。', body: '送过贵重礼物这件事，如果对方收了但关系没进展，你的高低位可能已经失衡了。这种情况需要一个系统性的行动规划来扭转对方的心理定位——不是一两句话能解决的，但有章法可循。', feature: '行动规划', highlight: '行动规划', tag: '高低位失衡' },
  chatting:  { short: '聊天模式需要调整，节奏是关键。', body: '每天主动找聊，对方回应跟不上你的投入……这说明你们的聊天模式需要调整。好消息是，我们可以提供逐条聊天指导——不是教你话术模板，而是根据你们的实际对话，实时告诉你下一句怎么接、什么时候该停。', feature: '聊天指导', highlight: '逐条聊天指导', tag: '投入失衡' },
  asked:     { short: '基础好，关键是下一次见面怎么设计。', body: '约出来过而且成功了，这说明对方至少不排斥跟你独处。这是一个很好的基础——关键是下一次见面怎么设计才能推进关系，而不是停在"普通朋友一起玩"。', feature: null, tag: '基础良好' },
  rejected:  { short: '要分清是真拒绝还是你约的方式不对。', body: '被拒绝过邀约……这个需要分析是「真拒绝」还是「你约的方式不对」。我们可以帮你做见面前的策略推演——什么时机约、用什么理由约、怎么让对方很难拒绝，这些都有讲究。', feature: '行动指南', highlight: '见面前的策略推演', tag: '邀约受阻' },
  public:    { short: '等于在公开场合半表白，压力给到 TA。', body: '在社交场合对 TA 表现不同，如果周围人都看出来了，那对方大概率也感受到了。这等于在「公开场合半表白」——压力给到了对方。后续策略需要把这个变量考虑进去。', feature: null, tag: '信号暴露' },
  none:      { short: '还有机会设计更好的切入路径。', body: '一直没有明显动作，说明对方可能根本不知道你的意图。这其实有利——你还有机会设计一个更好的切入路径。我们可以帮你制定一个分步行动规划，从朋友圈展示到话题制造，一步步把关系推进。', feature: '行动规划', highlight: '分步行动规划', tag: '未暴露' },

  // 组合钩子
  combo_confess_high: { short: '完全明牌状态下，需要整体策略重置。', body: '表白过，还送过礼物／天天聊／当众照顾……对方现在对你的意图已经零悬念了。在这种"完全明牌"的状态下，传统的"再加大投入"只会让对方压力更大。你现在需要的是整体策略重置——我们可以帮你评估当前位置，设计一条新的推进路线。', feature: '行动规划', highlight: '整体策略重置', tag: '组合诊断' },
  combo_confess_rej:  { short: '表白+被拒，需要动态局势分析。', body: '表白过，又被拒绝过邀约……这两个信号叠在一起，说明对方在表白后选择了拉开距离。但注意——这不一定是"对你没感觉"，也可能是"你的节奏让 TA 不舒服"。我们的动态局势分析能帮你区分这两种情况，然后制定对应的恢复策略。', feature: '局势分析', highlight: '动态局势分析', tag: '组合诊断' },
  combo_rej_chat:     { short: 'TA 在"享受关注"和"不推进"之间平衡。', body: '天天主动聊+邀约被拒——对方可能在"享受你的关注"和"不想推进关系"之间找了一个舒适点。你现在需要打破这个平衡，但方式不能是"更用力"。我们的聊天指导+行动规划能帮你用最小的动作制造最大的变化。', feature: '聊天指导', highlight: '聊天指导+行动规划', tag: '组合诊断' },
  combo_fallback:     { short: '先做一次全面现状评估，再设计下一步。', body: '你做了不少尝试——这些行动加在一起，对方对你的意图应该已经很清楚了。接下来的关键不是"做更多"，而是"做对的事"。我们会先帮你做一个全面的现状评估，看清你现在的真实位置，然后再设计下一步。', feature: '局势分析', highlight: '全面的现状评估', tag: '组合诊断' },
};
const HOOKS_A4 = {
  slow_reply:   { short: '不是没兴趣，是聊天模式让 TA 有压力。', body: '回复变慢／变敷衍，很多时候不是对你没兴趣，而是你们的聊天模式让对方觉得"有压力"。这种情况我们可以做实时聊天指导——根据对方的回复风格和节奏，告诉你这条该怎么接、多久后再发下一条，把对话氛围调回来。', feature: '聊天指导', highlight: '实时聊天指导', tag: '回应降级' },
  cold_reply:   { short: '不是没兴趣，是聊天模式让 TA 有压力。', body: '回复变慢／变敷衍，很多时候不是对你没兴趣，而是你们的聊天模式让对方觉得"有压力"。这种情况我们可以做实时聊天指导——根据对方的回复风格和节奏，告诉你这条该怎么接、多久后再发下一条，把对话氛围调回来。', feature: '聊天指导', highlight: '实时聊天指导', tag: '回应降级' },
  refused:      { short: '"最近忙"和"不方便"含义完全不同。', body: '拒绝见面要看具体措辞——"最近忙"和"不太方便"含义完全不同。我们可以帮你做动态局势跟踪，在每次互动后实时更新对方的态度评估，找到再次邀约的最佳窗口。', feature: '局势分析', highlight: '动态局势跟踪', tag: '邀约受阻' },
  friendzoned:  { short: '好人卡不是判决，是策略反馈。', body: '先别急着绝望——"我们是朋友"很多时候不是最终判决，而是对方在"你目前这个打法"下的反应。我们可以给你出一套系统性的策略规划，从根本上改变对方对你的心理定位。', feature: '行动规划', highlight: '系统性的策略规划', tag: '心理定位' },
  others_warm:  { short: '选择性保持距离——问题可以精准定位。', body: '对方选择性地对你保持距离，说明问题是可以定位的。我们的现状分析能帮你精确找到是哪个环节出了问题——是吸引力不够、还是互动模式不对、还是时机选错了。', feature: '局势分析', highlight: '现状分析', tag: '定向冷淡' },
  toolman:      { short: '"工具人化"高危信号，但可逆。', body: '这是"工具人化"的高危信号，但不是不可逆的。关键是要重新定义你在对方心中的角色——从"有用的人"变成"有趣的人"。我们会在行动指南里给你具体的朋友圈展示策略+话题转换技巧，一步步建立新的互动模式。', feature: '朋友圈指导', highlight: '朋友圈展示策略+话题转换技巧', tag: '角色固化' },
  none2:        { short: '没负面信号很好，你的卡点是推进。', body: '没有明显负面信号是好事。你的卡点可能是"不知道怎么往前推"——这反而是最容易解决的。我们可以给你做一个分阶段行动规划，把"从现在到在一起"拆成具体的步骤和里程碑。', feature: '行动规划', highlight: '分阶段行动规划', tag: '无负面信号' },

  combo_friend_any: { short: '好人卡 + 冷淡叠加——需要策略重置。', body: '对方已经口头划了界限，而且还有其他冷淡信号在叠加……说实话，这个局势确实比较紧张。但"好人卡"不是死刑——它只是对方在你当前策略下的反应。换一套打法，对方的态度是会变的。我们可以帮你做一套完整的策略重置规划，从对方的心理定位开始重建。', feature: '行动规划', highlight: '完整的策略重置规划', tag: '组合诊断' },
  combo_tool_cold:  { short: '"有用但不心动"——问题定位已很清楚。', body: '几个信号叠在一起看：对方在需要你的时候出现，不需要的时候消失，回复还冷淡……你现在大概率已经被归到"有用但不心动"的分类里了。听起来很扎心，但这恰恰是最明确的诊断——问题定位清楚了，解法反而不复杂。我们的现状分析+行动规划就是专门处理这类情况的。', feature: '局势分析', highlight: '现状分析+行动规划', tag: '组合诊断' },
  combo_cold_refuse:{ short: '线上冷淡+线下回避=系统性拉开距离。', body: '线上冷淡加上线下回避，这两个信号指向同一个问题：对方在系统性地拉开距离。但关键是——这是对你"这个人"的拒绝，还是对你"这种互动方式"的拒绝？两者的解法完全不同。我们的动态局势分析能帮你区分这个，然后给出针对性的策略。', feature: '局势分析', highlight: '动态局势分析', tag: '组合诊断' },
  combo_cold_other: { short: '选择性距离感——问题出在互动模式。', body: '对你冷淡但对别人热情——这说明不是"性格就这样"，而是选择性的距离感。好消息是：既然问题出在你们之间的互动模式上，那就是可以调整的。我们可以通过聊天指导+朋友圈策略，帮你在对方面前建立一个新的形象认知。', feature: '聊天指导', highlight: '聊天指导+朋友圈策略', tag: '组合诊断' },
  combo_fallback:   { short: '系统性问题，适合系统性方法。', body: '你选了好几个负面信号……这些叠在一起看，说明问题不是某一个点，而是整体互动模式需要调整。好在——越是系统性的问题，越适合用系统性的方法来解决。我们会先帮你做一个全面的局势评估，把每个问题的优先级排出来，然后一步步处理。', feature: '局势分析', highlight: '全面的局势评估', tag: '组合诊断' },
};

// 选中后从哪里挑钩子
function pickHookA3(selected = []) {
  if (selected.length === 0) return null;
  if (selected.length === 1) return HOOKS_A3[selected[0]] || null;
  const has = k => selected.includes(k);
  if (has('confess') && (has('expensive') || has('chatting') || has('public'))) return HOOKS_A3.combo_confess_high;
  if (has('confess') && has('rejected'))  return HOOKS_A3.combo_confess_rej;
  if (has('rejected') && has('chatting')) return HOOKS_A3.combo_rej_chat;
  return HOOKS_A3.combo_fallback;
}
function pickHookA4(selected = []) {
  if (selected.length === 0) return null;
  if (selected.length === 1) return HOOKS_A4[selected[0]] || null;
  const has = k => selected.includes(k);
  if (has('friendzoned')) return HOOKS_A4.combo_friend_any;
  if (has('toolman') && (has('slow_reply') || has('cold_reply') || has('others_warm'))) return HOOKS_A4.combo_tool_cold;
  if ((has('slow_reply') || has('cold_reply')) && has('refused')) return HOOKS_A4.combo_cold_refuse;
  if ((has('slow_reply') || has('cold_reply')) && has('others_warm')) return HOOKS_A4.combo_cold_other;
  return HOOKS_A4.combo_fallback;
}

// ─── 假用户自由描述输入（方便在各 hook 页复用） ───
const DEMO_USER_INPUT = `她是我同事，认识快 3 个月了。最开始聊得挺好，一周能聊 4-5 次，前两周我们还一起吃过一次午饭。
但最近一周她回复明显慢了，以前几分钟内回，现在经常半天才回一句"嗯嗯"。上周五我约她下班一起喝咖啡被拒了，说"最近很忙"。
我有点怕是不是我前几天的一些玩笑话让她不舒服了，但又不敢直接问。`;

// ─── 路径 A 首次 AI 钩子（基于自由描述生成） ───
const OPENING_HOOK = {
  tag: '首发诊断',
  title: '你的情况我之前见过很多——问题不在"她突然变了"，而在"节奏"。',
  body: '你 3 个月内推进到一起吃午饭，这个节奏其实挺正常。但"回复变慢 + 面对面邀约被拒 + 你开始自我怀疑"这三件事一起发生，是典型的信号过载。她大概率不是对你没感觉，而是你这两周的推进密度让她感到了压力。',
  highlights: ['回复变慢', '邀约被拒', '自我怀疑'],
  evidences: [
    '你提到「聊得挺好，一周 4-5 次」——基线建立得不错',
    '你提到「上周五约她被拒，理由是最近很忙」——要看具体措辞',
    '你提到「怕是玩笑话让她不舒服」——这是过度自我归因的典型信号',
  ],
};

// ─── 诊断报告（最终页 数据） ───
// 5 维扩展模型：ACR（brief 原生）+ Trust 信任度（Gottman）+ Reciprocity 回应度（依恋理论）
// 扩成 5 维是因为：① 5 维闭合成接近正五边形，比三维三角"专业感"强很多；
//                   ② 行业里 Gottman / Sternberg 都用 5-6 维作为完整模型；
//                   ③ 避免用户"只看到一个三角，以为还没做完"的错觉
function buildDiagnosis(answers = {}) {
  const state = {
    badge: '高危滑坡期',
    badgeColor: '#C00',
    badgeBg: '#FFE6E6',
    trend: '不介入的话，预计 2-3 周内 TA 会把你重新归档为"普通同事"',
    trendTone: 'warn',
  };
  // 5 维健康度模型（原 ACR 三维保留 + 信任 + 回应度）
  const acr = {
    '吸引力 A':   { score: 52, note: '基线还在，但"需求感过度"正在侵蚀你的吸引力' },
    '舒适感 C':   { score: 68, note: '舒适度不错，但这反而让你被固化成"好说话的那个"' },
    '张力 R':     { score: 18, note: '几乎没有暧昧的火花——这是你最薄弱的一环' },
    '信任度 T':   { score: 64, note: '基础信任在，但可预期性正被你的"忽冷忽热"稀释' },
    '回应度 E':   { score: 31, note: '你的投入远大于对方回应——这是严重的单边指标' },
  };
  const problems = [
    { tag: '推进节奏失衡', title: '你这两周的密度超过了她的舒适线', evidence: '你提到"一周 4-5 次"变成"每天主动"，密度上涨 2.3 倍，她的回复速度反向下降 47%。', severity: 'high' },
    { tag: '单边投入模式', title: '所有对话都是你发起的——她在坐等', evidence: '从你的描述看，最近两周没有一次是她先发消息。这是典型的"消耗型互动"。', severity: 'high' },
    { tag: '自我审查升级', title: '"怕说错话"正在让你变得无趣', evidence: '你提到"不敢直接问"——过度谨慎本身就是需求感的信号，她会感知到。', severity: 'mid' },
  ];
  return { state, acr, problems };
}

Object.assign(window, {
  Frame, PrimaryBtn, Tag, Eyebrow, ClinicalHeader,
  QUESTIONS, HOOKS_A1, HOOKS_A2, HOOKS_A3, HOOKS_A4,
  pickHookA3, pickHookA4,
  DEMO_USER_INPUT, OPENING_HOOK, buildDiagnosis,
});
