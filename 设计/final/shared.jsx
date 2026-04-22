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
// A0 性别题（不计入 5 题进度，不显示进度条，答完直接进 A1）
// A1-A5 共 5 道题
const QUESTIONS = [
  {
    id: 'A0_gender',
    q: '先问你一个小问题 — 你是？',
    sub: '这样我和你说话的时候可以更自然 😊',
    type: 'single',
    noProgress: true,  // 不显示进度条
    opts: [
      { t: '男生', key: 'male' },
      { t: '女生', key: 'female' },
      { t: '不想说', key: 'other' },
    ],
  },
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
// short/body: 中性兜底版（A0 选"不想说"或未选时使用）
// short_m/body_m: 男生版（A0 选 male）
// short_f/body_f: 女生版（A0 选 female）
// feature: 对应的产品功能配图 key（或 null）
const HOOKS_A1 = {
  colleague: {
    short:   '同事关系天然优势是见面多，但搞砸了尴尬会放大十倍。',
    short_m: '兄弟，同事关系好在天天碰面 😏',
    short_f: '姐妹，同事关系赢在接触机会多 😏',
    body:    '同事关系天然优势是见面多，但搞砸了尴尬会放大十倍。',
    body_m:  '但搞砸了也得天天对视，每一步都得有章法。',
    body_f:  '但搞砸了尴尬也翻倍，得比平时更讲策略。',
    feature: null, tag: '情境特征',
  },
  classmate: {
    short:   '同学之间最容易掉进「好哥们 / 好闺蜜」的陷阱。舒适感有了，但那种「心动感」反而起不来。',
    short_m: '兄弟，同学关系最怕的就是越熟越变成「哥们」。',
    short_f: '姐妹，同学关系女生特别容易掉进「好闺蜜」的坑——',
    body:    '同学之间最容易掉进「好哥们 / 好闺蜜」的陷阱。舒适感有了，但那种「心动感」反而起不来。',
    body_m:  '舒适感有了，心动感反而没了。',
    body_f:  '聊得越顺越像朋友，TA 反而不会往别的方向想你。',
    feature: null, tag: '情境特征',
  },
  online: {
    short:   '线上认识最关键的变量是有没有线下连接，纯聊下去很容易变赛博笔友。',
    short_m: '兄弟，没见过面你就只是个头像 😏',
    short_f: '姐妹，线上聊得再好也只是个头像。',
    body:    '线上认识最关键的变量是有没有线下连接，纯聊下去很容易变赛博笔友。',
    body_m:  '线下连接是第一优先级，别光在聊天里打转。',
    body_f:  '线下见面这件事得优先推进，别等感觉淡了。',
    feature: null, tag: '情境特征',
  },
  intro: {
    short:   '朋友介绍最大的坑是双方都在「筛选模式」，端着聊很难出真实感觉。',
    short_m: '兄弟，朋友介绍的坑是双方都端着——',
    short_f: '姐妹，朋友介绍最怕的就是两个人都在端着——',
    body:    '朋友介绍最大的坑是双方都在「筛选模式」，端着聊很难出真实感觉。',
    body_m:  '都在「筛选模式」里，反而聊不出真实感觉来。',
    body_f:  '互相筛选的状态很难产生真正的心动。',
    feature: null, tag: '情境特征',
  },
  offline: {
    short:   '偶遇的窗口期很短，没有稳定联系渠道的话机会很快消失。',
    short_m: '兄弟，偶遇的窗口期很短 ⚡',
    short_f: '姐妹，偶遇认识的热度散得很快 ⚡',
    body:    '偶遇的窗口期很短，没有稳定联系渠道的话机会很快消失。',
    body_m:  '没锁定联系方式，再见面就只能靠缘分了。',
    body_f:  '先把联系方式搞定，这是当务之急。',
    feature: null, tag: '情境特征',
  },
  other: null,
};
const HOOKS_A2 = {
  lt1m: {
    short:   '不到一个月，印象还没固化，可塑空间最大。别犯低级错误就行。',
    short_m: '兄弟，现在还早，可塑空间很大 👍',
    short_f: '姐妹，才认识不久，印象还没定型 👍',
    body:    '不到一个月，印象还没固化，可塑空间最大。别犯低级错误就行。',
    body_m:  '别犯低级错误就行，这阶段主动权完全在你手上。',
    body_f:  'TA 怎么看你还有很大空间，稳住别急就好。',
    feature: null, tag: '时间诊断',
  },
  '1to3m': {
    short:   '1-3 个月，TA 对你的初步印象已经成型了。没有升温信号就得找找卡在哪了。',
    short_m: '兄弟，1-3 个月，TA 对你的印象基本定了。',
    short_f: '姐妹，这个阶段 TA 心里已经给你「贴标签」了。',
    body:    '1-3 个月，TA 对你的初步印象已经成型了。没有升温信号就得找找卡在哪了。',
    body_m:  '没感觉到升温的话，说明有个环节卡住了，得找出来。',
    body_f:  '没有升温信号的话，早发现卡点比等着好。',
    feature: null, tag: '时间诊断',
  },
  '3to6m': {
    short:   '3-6 个月还没实质进展，某个环节大概率卡住了。现在调还来得及。',
    short_m: '兄弟，认识几个月了关系还没动——',
    short_f: '姐妹，几个月了还没实质进展——',
    body:    '3-6 个月还没实质进展，某个环节大概率卡住了。现在调还来得及。',
    body_m:  '说明某个环节卡住了，好消息是现在调整完全来得及。',
    body_f:  '不是没机会，是需要找到那个卡点，现在调还来得及。',
    feature: null, tag: '时间诊断',
  },
  '6mto1y': {
    short:   '半年到一年，你大概率已经被归类了。但归类是可以打破的，需要主动出手。',
    short_m: '兄弟，超过半年还停着，TA 心里大概率已经给你贴好标签了 😶',
    short_f: '姐妹，半年以上，TA 心里对你的位置基本定了 😶',
    body:    '半年到一年，你大概率已经被归类了。但归类是可以打破的，需要主动出手。',
    body_m:  '被归类不是死局，但要打破它得主动出手。',
    body_f:  '打破这个判断需要一个有策略的动作，不能靠等。',
    feature: null, tag: '时间诊断',
  },
  gt1y: {
    short:   '超过一年，定位确实固化了。但我见过不少逆转案例，关键是打法对不对。',
    short_m: '兄弟，超过一年，定位固化是真的。',
    short_f: '姐妹，一年以上印象确实很稳固了。',
    body:    '超过一年，定位确实固化了。但我见过不少逆转案例，关键是打法对不对。',
    body_m:  '但逆转的案例不少——不是时间问题，是打法问题。',
    body_f:  '但「稳固」不代表改不了，关键是用对方法。',
    feature: null, tag: '时间诊断',
  },
};
// A3/A4 多选钩子 —— 由 pickHook() 按优先级选择
const HOOKS_A3 = {
  confess: {
    short:   '表白过了，意味着 TA 现在是带着「TA 喜欢我」的滤镜跟你互动的。之后每一步都会被放大解读。',
    short_m: '兄弟，表白过了，牌已经打出去了。',
    short_f: '姐妹，表白了之后，TA 对你就不再是「普通相处」了。',
    body:    '表白过了，意味着 TA 现在是带着「TA 喜欢我」的滤镜跟你互动的。之后每一步都会被放大解读。',
    body_m:  '现在 TA 用「他喜欢我」的滤镜看你的每个动作。\n表白之后你的反应，决定了 TA 怎么看你。',
    body_f:  'TA 现在看你每个举动都会多想一层。\n这个局面反而有机会——关键是接下来怎么打。',
    feature: '局势分析', highlight: '局势分析', tag: '高暴露预警',
  },
  expensive: {
    short:   '送过贵重礼物，如果关系没有进展，说明高低位可能已经失衡了。这需要系统性调整，不是一两句话能解决的。',
    short_m: '兄弟，送过贵重礼物……',
    short_f: '姐妹，送过比较贵的礼物，如果 TA 收了但没什么反馈——',
    body:    '送过贵重礼物，如果关系没有进展，说明高低位可能已经失衡了。这需要系统性调整，不是一两句话能解决的。',
    body_m:  '如果收了但关系没进展，那说明 TA 在你们之间感觉不到平等——你一直在「付出位」。\n这种位置失衡不是加更多投入能解决的，需要换一套逻辑。',
    body_f:  '说明在 TA 心里你的「投入」和「你的价值」脱节了。\n解法不是送更多，而是先调整你们之间的位置关系。',
    feature: '行动规划', highlight: '行动规划', tag: '高低位失衡',
  },
  chatting: {
    short:   '每天主动聊，对方的回应跟不上——聊天节奏失衡了。不是教话术，是要根据实际对话调整你的回复方式和频率。',
    short_m: '兄弟，每天主动开话题，但 TA 回应越来越少？',
    short_f: '姐妹，每天都是你先主动，TA 回来的质量越来越低？',
    body:    '每天主动聊，对方的回应跟不上——聊天节奏失衡了。不是教话术，是要根据实际对话调整你的回复方式和频率。',
    body_m:  '这不是「聊天内容」的问题，是节奏失衡了——你太主动，TA 反而没了主动找你的动力。\n得学会「踩刹车」，不是「踩油门」。',
    body_f:  '说白了：你把对话全包了，TA 就没有「想主动找你」的感觉了。\n要做的是适当停下来，让 TA 来找你。',
    feature: '聊天指导', highlight: '聊天指导', tag: '投入失衡',
  },
  asked: {
    short:   '约出来过而且成功了，说明 TA 不排斥跟你独处。这是很好的基础。关键是下一次见面怎么设计，能推进而不是原地打转。',
    short_m: '兄弟，约出来过且成功了，这是真的好信号 ✅',
    short_f: '姐妹，约出来成功了，说明 TA 不排斥和你独处 ✅',
    body:    '约出来过而且成功了，说明 TA 不排斥跟你独处。这是很好的基础。关键是下一次见面怎么设计，能推进而不是原地打转。',
    body_m:  'TA 愿意跟你单独待着，说明基础不差。\n现在要想的是：下一次见面怎么设计，让它变成「那次见面」，而不只是「又一次出去玩」。',
    body_f:  '这是很好的基础。\n现在要思考的是怎么让下次见面有一点「不一样的感觉」，而不是继续当朋友模式。',
    feature: null, tag: '基础良好',
  },
  rejected: {
    short:   '被拒绝过邀约，要先分清楚是「真拒绝」还是「约法不对」——两种情况完全不同的解法。',
    short_m: '兄弟，被拒邀约之前先别沮丧。',
    short_f: '姐妹，被拒了不代表没希望——',
    body:    '被拒绝过邀约，要先分清楚是「真拒绝」还是「约法不对」——两种情况完全不同的解法。',
    body_m:  '「最近忙」和「不方便」和「不想去」，含义完全不同。\n是真拒绝，还是你约的方式让 TA 有压力？这两个问题搞清楚了，解法就不一样了。',
    body_f:  '关键是搞清楚 TA 拒绝的原因。\n是 TA 真的不想去，还是你约的时机和方式让 TA 下不了台？后者是完全可以修的。',
    feature: '行动指南', highlight: '行动指南', tag: '邀约受阻',
  },
  public: {
    short:   '在社交场合对 TA 特别照顾，周围人看出来了，TA 大概率也感受到了。等于公开半表白——压力已经给过去了。',
    short_m: '兄弟，当众对 TA 特别照顾，周围人都看出来了——',
    short_f: '姐妹，当众对 TA 不一样这件事，TA 心里是有数的。',
    body:    '在社交场合对 TA 特别照顾，周围人看出来了，TA 大概率也感受到了。等于公开半表白——压力已经给过去了。',
    body_m:  'TA 肯定也感受到了，甚至可能比你想的更明显。\n这等于在众目睽睽下打了一张牌，TA 已经在想怎么回应了。\n后续策略要把这个变量考虑进去。',
    body_f:  '这相当于一种「压力性暗示」——TA 现在需要想清楚怎么对待你。\n你接下来的动作要稳，别继续加码。',
    feature: null, tag: '信号暴露',
  },
  none: {
    short:   '一直没动作，多半是怕搞砸。但一直不出手，TA 永远不知道你的意图——你还有机会设计一个好的切入。',
    short_m: '兄弟，一直没出手，是不是怕一动就搞砸？',
    short_f: '姐妹，还没动作，是不是怕一步走错就没机会了？',
    body:    '一直没动作，多半是怕搞砸。但一直不出手，TA 永远不知道你的意图——你还有机会设计一个好的切入。',
    body_m:  '但不动的话，TA 永远不知道你的意图——你在 TA 眼里还是一张白纸。\n白纸反而是优势：你可以设计一个有质量的切入，而不是仓促出手。',
    body_f:  '但一直不出手，TA 就永远没法往那个方向想你。\n好消息是你现在还没明牌，完全可以主动设计怎么开始。',
    feature: '行动规划', highlight: '行动规划', tag: '未暴露',
  },

  // 组合钩子
  combo_confess_high: {
    short:   '表白过，还叠加了送礼 / 天天聊 / 当众照顾——TA 对你的意图已经零悬念。在「完全明牌」的状态下，再加大投入只会让 TA 压力更大。你现在需要的是整体策略重置。',
    short_m: '兄弟，说句实话 😮‍💨',
    short_f: '姐妹，我得跟你说实话 😮‍💨',
    body:    '表白过，还叠加了送礼 / 天天聊 / 当众照顾——TA 对你的意图已经零悬念。在「完全明牌」的状态下，再加大投入只会让 TA 压力更大。你现在需要的是整体策略重置。',
    body_m:  '你表白完还天天主动——\n你以为是坚持，TA 感觉是「这哥们儿跑不掉了」。\n越努力，越掉价。不是你的问题，是打法在帮倒忙。\n现在要做的是完全换一套策略，而不是继续加码。',
    body_f:  '表白了还天天主动——\nTA 感觉是「她跑不掉的」，已经不需要珍惜了。\n这不是你的错，是策略错了，能救。\n但要救，就得先停下来，换一个方向。',
    feature: '行动规划', highlight: '整体策略重置', tag: '组合诊断',
  },
  combo_confess_rej: {
    short:   '表白过，又被拒过邀约——两个信号叠在一起，说明对方在表白后选择了拉开距离。但这不一定是「对你没感觉」，也可能是「你的节奏让 TA 不舒服」。',
    short_m: '兄弟，表白过、又被拒过约 😶',
    short_f: '姐妹，表白了、约了、都没成功——',
    body:    '表白过，又被拒过邀约——两个信号叠在一起，说明对方在表白后选择了拉开距离。但这不一定是「对你没感觉」，也可能是「你的节奏让 TA 不舒服」。',
    body_m:  '这两件事叠在一起挺难受的，但还没到绝望的程度。\n「TA 对你没感觉」和「TA 被你的节奏吓到了」，这两种情况解法完全不同。\n先搞清楚是哪种，再决定怎么走。',
    body_f:  '不代表没希望，但说明 TA 现在需要一点距离感。\n继续推反而会加速关系冷却；退一步、制造一点空间，反而可能让 TA 重新想起你。',
    feature: '局势分析', highlight: '局势分析', tag: '组合诊断',
  },
  combo_rej_chat: {
    short:   '天天主动聊 + 邀约被拒——TA 在「享受你的关注」和「不想推进关系」之间找到了舒适点。你需要打破这个平衡，但不能靠「更用力」。',
    short_m: '兄弟，你现在的处境是：',
    short_f: '姐妹，你现在成了 TA 的「随时可以聊的人」——',
    body:    '天天主动聊 + 邀约被拒——TA 在「享受你的关注」和「不想推进关系」之间找到了舒适点。你需要打破这个平衡，但不能靠「更用力」。',
    body_m:  'TA 乐意跟你聊天，但不想往前走——TA 找到了一个舒服的位置，你来陪着就行。\n「再主动一点」只会强化这个模式。\n要打破它，反而要主动退一步，让 TA 感觉「你不是随叫随到的」。',
    body_f:  '但不是「TA 想约出来的人」。\n这个角色定位卡在那里很难受，而且越主动越稳固。\n破局的方式是反向操作：先降低你的可预期性。',
    feature: '聊天指导', highlight: '聊天指导', tag: '组合诊断',
  },
  combo_fallback: {
    short:   '你做了不少尝试，对方对你的意图应该很清楚了。关键现在不是「做更多」，而是「做对的事」。先全面评估一下现在真实的位置，再设计下一步。',
    short_m: '兄弟，你已经出了不少牌了。',
    short_f: '姐妹，你做了不少尝试——不是不努力，是方向可能没对。',
    body:    '你做了不少尝试，对方对你的意图应该很清楚了。关键现在不是「做更多」，而是「做对的事」。先全面评估一下现在真实的位置，再设计下一步。',
    body_m:  'TA 心里对你是什么感觉，其实 TA 自己是清楚的。\n现在不是「再努力一点」的问题——是要先搞清楚「你现在真实处于什么位置」，然后针对性地出手。',
    body_f:  '现在不需要再加动作，需要先停下来看清局面。\n知道自己在哪，才能知道下一步该往哪走。',
    feature: '局势分析', highlight: '全面的现状评估', tag: '组合诊断',
  },
};
const HOOKS_A4 = {
  slow_reply: {
    short:   '回复越来越慢，多数时候不是对你没兴趣，而是你发消息的频率和密度让 TA 有压力了。',
    short_m: '兄弟，回复变慢不一定是凉了。',
    short_f: '姐妹，回复慢了……先别乱想。',
    body:    '回复越来越慢，多数时候不是对你没兴趣，而是你发消息的频率和密度让 TA 有压力了。',
    body_m:  '更大的可能是你发消息太频繁，TA 觉得「每次都要及时回」有压力。\n降低频率，给 TA 一点「想你」的空间，比换话题有用十倍。',
    body_f:  '很多时候是你发消息的频率让 TA 喘不过气，不是不喜欢你。\n降低密度，给 TA 一点主动找你的空间。',
    feature: '聊天指导', highlight: '聊天指导', tag: '回应降级',
  },
  cold_reply: {
    short:   '聊天越来越敷衍，多半不是对你没感觉，而是你的聊天方式让 TA 接不住话。调内容比调频率管用。',
    short_m: '兄弟，「嗯嗯哦哦」不一定是不喜欢你。',
    short_f: '姐妹，敷衍的回复背后，可能不是「没感觉」。',
    body:    '聊天越来越敷衍，多半不是对你没感觉，而是你的聊天方式让 TA 接不住话。调内容比调频率管用。',
    body_m:  '更多时候是 TA 不知道怎么接你的话——你的话题让 TA 没有发挥空间。\n换一种聊法，让 TA 更容易有话说，比追着发消息管用。',
    body_f:  '更可能是你聊的内容让 TA 觉得「不知道怎么接」。\n让聊天变得 TA 能接住、想接住，比发更多消息有效。',
    feature: '聊天指导', highlight: '聊天指导', tag: '回应降级',
  },
  refused: {
    short:   '拒绝见面要看措辞——「最近忙」和「不方便」含义完全不同。拒绝的原因搞清楚之前，不要贸然再约。',
    short_m: '兄弟，被拒了别急着解读成「不喜欢」。',
    short_f: '姐妹，TA 拒绝见面，先不要下结论。',
    body:    '拒绝见面要看措辞——「最近忙」和「不方便」含义完全不同。拒绝的原因搞清楚之前，不要贸然再约。',
    body_m:  '「最近忙」「不太方便」「改天吧」，含义差很远。\n先搞清楚 TA 拒绝的真实原因，再决定下一步怎么约、用什么方式约。',
    body_f:  '有时候是真的有事，有时候是你约的方式让 TA 有压力。\n搞清楚是哪种情况，解法才不一样。',
    feature: '局势分析', highlight: '局势分析', tag: '邀约受阻',
  },
  friendzoned: {
    short:   '「好人卡」不是最终判决，是 TA 在你当前打法下的反应。打法变了，TA 的反应也会变。',
    short_m: '兄弟，「好人」这两个字是真的难听 😶',
    short_f: '姐妹，「你真的很好」是一种礼貌性的拒绝 😶',
    body:    '「好人卡」不是最终判决，是 TA 在你当前打法下的反应。打法变了，TA 的反应也会变。',
    body_m:  '但更难的是：你之后越主动，TA 越笃定了自己的判断没错。\n现在要做的不是证明自己多好，是让 TA 重新觉得「你不一定在」。',
    body_f:  '你之后越努力，TA 越确认自己的判断对。\n要打破这个，需要让 TA 开始怀疑「她还会等我吗」，而不是继续给 TA 稳定的预期。',
    feature: '行动规划', highlight: '行动规划', tag: '心理定位',
  },
  others_warm: {
    short:   '对你冷淡、但对别人热情——这是选择性距离。不是 TA 性格如此，而是你们之间的互动没触发 TA 的热情开关。找到那个开关就能调过来。',
    short_m: '兄弟，TA 对别人热情、对你冷淡——',
    short_f: '姐妹，TA 对别人都挺热情，偏偏对你冷一点——',
    body:    '对你冷淡、但对别人热情——这是选择性距离。不是 TA 性格如此，而是你们之间的互动没触发 TA 的热情开关。找到那个开关就能调过来。',
    body_m:  '扎心，但其实是个好消息：说明 TA 不是冷漠的人，是你们之间的互动方式触发不了 TA 的热情开关。\n找到那个开关比讨好有用十倍。',
    body_f:  '不是你不够好，是你们之间的相处方式没触发 TA 对你的兴趣。\n找到那个触发点比一味讨好有用得多。',
    feature: '局势分析', highlight: '局势分析', tag: '定向冷淡',
  },
  toolman: {
    short:   '工具人信号是高危，但不是不可逆。关键是让 TA 重新定义你的角色——从「有用的人」变成「有趣的人」。',
    short_m: '兄弟，TA 找你只在需要帮忙的时候……',
    short_f: '姐妹，TA 需要你才来找你，用完又消失——',
    body:    '工具人信号是高危，但不是不可逆。关键是让 TA 重新定义你的角色——从「有用的人」变成「有趣的人」。',
    body_m:  '这个「工具人」的标签已经粘上了。\n但它不是撕不掉的——关键是要让 TA 看见「你不一样的那一面」。\n不是刻意表现，是有策略地展示你的另一个维度。',
    body_f:  '这个模式让人很受伤，但它是可以打破的。\n你需要的不是拒绝帮 TA，而是让 TA 开始好奇「她除了能帮我，还是个什么样的人」。',
    feature: '朋友圈指导', highlight: '朋友圈指导', tag: '角色固化',
  },
  none2: {
    short:   '没有负面信号是好事。你的卡点可能是「不知道怎么往前推」——这反而是最容易解决的问题。',
    short_m: '兄弟，没有负面信号，那其实挺好的 👍',
    short_f: '姐妹，没有明显的负面信号，这是好事 👍',
    body:    '没有负面信号是好事。你的卡点可能是「不知道怎么往前推」——这反而是最容易解决的问题。',
    body_m:  '说明 TA 对你没有排斥，只是关系还没推进到位。\n这是最好处理的情况——卡点不是「TA 不喜欢你」，而是「关系推进节奏需要设计」。',
    body_f:  'TA 对你的态度还行，说明基础在。\n现在需要的是找到一个好的方式「往前走一步」——不是靠等，而是靠设计。',
    feature: '行动规划', highlight: '行动规划', tag: '无负面信号',
  },

  combo_friend_any: {
    short:   '好人卡已经够难受了，偏偏还叠了其他冷淡信号——这说明不是 TA 一时嘴快，是 TA 在用行动确认那个判断了。越主动只会越坐实，现在唯一的活路是让 TA 感觉「你可能不在了」。',
    short_m: '兄弟，好人卡已经够难受了，偏偏还叠了其他冷淡信号 😶',
    short_f: '姐妹，好人卡加上其他冷淡信号一起来了 😶',
    body:    '好人卡已经够难受了，偏偏还叠了其他冷淡信号——这说明不是 TA 一时嘴快，是 TA 在用行动确认那个判断了。越主动只会越坐实，现在唯一的活路是让 TA 感觉「你可能不在了」。',
    body_m:  '这说明不是 TA 一时嘴快——是 TA 已经在用行动确认那个判断了。\n越主动只会越坐实「这哥们跑不掉」的印象。\n现在唯一的活路是让 TA 感觉「你可能不在了」。',
    body_f:  '这不是 TA 客气一下——是 TA 已经在用行动确认自己的判断了。\n你越努力，TA 越觉得「她果然跑不掉」。\n唯一的转机是让 TA 感觉到「你可能真的要走了」。',
    feature: '行动规划', highlight: '完整的策略重置规划', tag: '组合诊断',
  },
  combo_tool_cold: {
    short:   '工具人 + 冷淡叠加——你现在被归到了「有用但不心动」那一类。听起来很扎心，但这是最明确的诊断——问题定位清楚了，解法反而不复杂。',
    short_m: '兄弟，几个信号加在一起：',
    short_f: '姐妹，TA 需要你才找你，回复还冷淡——',
    body:    '工具人 + 冷淡叠加——你现在被归到了「有用但不心动」那一类。听起来很扎心，但这是最明确的诊断——问题定位清楚了，解法反而不复杂。',
    body_m:  'TA 用到你的时候出现，不用的时候消失，回复还是敷衍。\n你现在大概率已经被归类成「有用的人」——但不是「让 TA 心动的人」。\n这不是不能逆转，但需要换个出现方式，不是加大投入。',
    body_f:  '你现在的角色是「方便的朋友」而不是「她喜欢的人」。\n扎心但是可以改的。\n关键是让 TA 看见你「不只是有用」这一面。',
    feature: '局势分析', highlight: '现状分析+行动规划', tag: '组合诊断',
  },
  combo_cold_refuse: {
    short:   '线上冷淡 + 拒绝见面，两个信号指向同一个方向：TA 在主动拉开距离。但问题是「对你这个人」的距离，还是「对你这种相处方式」的距离？两者解法完全不同。',
    short_m: '兄弟，线上不怎么回、线下也不愿见——',
    short_f: '姐妹，线上敷衍、线下回避——',
    body:    '线上冷淡 + 拒绝见面，两个信号指向同一个方向：TA 在主动拉开距离。但问题是「对你这个人」的距离，还是「对你这种相处方式」的距离？两者解法完全不同。',
    body_m:  '这两个加在一起，说明 TA 在主动保持距离。\n但这是「对你这个人」有距离，还是「你的互动方式让 TA 有压力」？\n搞清楚这个，解法才不一样。',
    body_f:  'TA 确实在拉开距离，这个事实得先认。\n但「拉开距离」是对你这个人，还是对你们的相处方式？\n搞清楚这个，才知道还有没有救、怎么救。',
    feature: '局势分析', highlight: '动态局势分析', tag: '组合诊断',
  },
  combo_cold_other: {
    short:   '对你冷淡 + 对别人热情——这是选择性的距离，说明不是 TA 性格如此。你们之间的互动方式没有触发 TA 的热情开关，找到那个开关就能翻盘。',
    short_m: '兄弟，TA 对别人热情、单独对你冷——',
    short_f: '姐妹，TA 对别人都挺好，偏偏对你有点疏远——',
    body:    '对你冷淡 + 对别人热情——这是选择性的距离，说明不是 TA 性格如此。你们之间的互动方式没有触发 TA 的热情开关，找到那个开关就能翻盘。',
    body_m:  '扎心，但这恰恰说明 TA 不是冷漠的人。\n是你们之间的互动方式没有触发 TA 的热情开关。\n找到那个开关，比一味讨好管用十倍。',
    body_f:  '不是你不够好，是你们之间的互动方式没触发 TA 对你的兴趣。\n找到那个触发点，才能真正扭转局面。',
    feature: '聊天指导', highlight: '聊天指导+朋友圈策略', tag: '组合诊断',
  },
  combo_fallback: {
    short:   '好几个负面信号叠在一起——问题不在某一个点，是你们之间的互动游戏规则本身需要重写。规则搞对了，局面会快速翻转。',
    short_m: '兄弟，好几个负面信号叠在一起——',
    short_f: '姐妹，多个负面信号叠在一起，确实不好受。',
    body:    '好几个负面信号叠在一起——问题不在某一个点，是你们之间的互动游戏规则本身需要重写。规则搞对了，局面会快速翻转。',
    body_m:  '说明不是某一件事的问题，是你们之间的互动游戏规则本身出了问题。\n好消息是：规则搞对了，这些信号会快速翻转。\n先把现在的规则看清楚，再重新设计。',
    body_f:  '但这恰恰说明问题不在某一个点——是你们之间的互动模式整体跑偏了。\n模式调对了，这些信号会很快改善。先把局面看清楚。',
    feature: '局势分析', highlight: '全面的局势评估', tag: '组合诊断',
  },
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
