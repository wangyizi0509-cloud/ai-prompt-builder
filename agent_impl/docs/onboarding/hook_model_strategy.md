# Onboarding 钩子（Hook）模型策略

> 目标：把"首发 opening hook + 逐题 card hook"从当前的"一句话兜底"升级为**能撑起原型饱满度、让用户觉得"被说中了"**的输出。
> 范围：路径 A（FreeDesc_V1_Compact 入口：自由文本 + 2-4 张聊天截图）。
> 约束：只改模型策略与数据契约，不改前端视觉骨架。

---

## 1. 诊断：钩子为什么这么薄？

结论先行：**input 在客观上够用，output 契约被写死成 1 句话字符串**——模型被"框架"砍成薄片，不是它不会写。

### 1.1 Opening hook：契约决定了它只能是一句话

证据链：

- `agent_impl/onboarding_v2/schemas.py:96-99`：`AnalyzeResponse.first_hook: str`（纯字符串，无 title / evidences / highlights）
- `agent_impl/onboarding_v2/prompts/analyze.md:35-39`：prompt **硬约束**「1-3 句话，不要多、不要少」「不用任何 markdown 加粗/列表/引用符号；纯一段自然语言」
- `agent_impl/onboarding_v2/nodes/analyze.py:50-52`：fallback 也只是一句话
- `agent_impl/frontend/scripts/onboarding_flow.js:636-672`：前端拿到 `first_hook` 之后，**用正则 `/^([^。]+。)\s*(.*)$/` 硬拆第一句当 title、其余当 body**；`chips` 来自 `**xxx**` 的反向抓取，但 prompt 明令禁止加粗 → 结果 `chipsEl` 几乎永远是 `display:none`；evidences 区在 HTML 里**根本没有对应元素**（原型的 `#opening-hook-chips` 容器只接 chips，没有 evidences 列表）

对比原型 `docs/onboarding/page3-opening-hook.jsx:20-55`，原型期望：`tag + title(大字判断) + body + highlights(3 个关键词) + evidences(至少 3 条 "我从你的描述里看到了" 引证)`。**后端只交付了 title+body 两段融合字符串；highlights 和 evidences 是设计稿里的"空壳"**。

> 所以你看到的钩子"巨少"不是模型偷懒，是 API 契约根本没有 evidences / highlights 字段让它写。

### 1.2 Card hook：压根没走模型

证据链：

- `agent_impl/frontend/onboarding.html:204`：整条 `qbank` `<script>` 里，5 题的 hooks 全部以**静态 JSON 硬编码**进 HTML（同义的 Python 源在 `agent_impl/onboarding_v2/hooks.py`）
- `agent_impl/frontend/scripts/onboarding_flow.js:152-178`：`resolveHook()` 完全按 **选项 key** 在 `bankData.hooks[qid]` 查表，没有任何 LLM 调用
- 设计稿 `page5-card-hook.jsx` 期待的字段 `{short, body, highlights, evidences, feature}` 里，只有 `body` 和 `feature/image` 被填充；`short`（大字判断标题）用正则从 `body` 劈出来（`onboarding_flow.js:862-866`）；`highlights` **几乎是空**（仅 `HOOKS_A3/A4` 的少量组合钩子里有）。

> 所以 card hook 完全**跟用户的自由文本 / 截图无关**——用户选了 A3=confess，无论截图里有没有"对方已读不回"，都会吐出同一段预写文案。"被说中"只能做到"选项命中"级别，而不是"截图细节级"。

### 1.3 输入端并不空

以 Benchmark 评估集 (`Benchmark/新版onboarding自由评估集.md`) 为样本，N（信息密度）是相当充足的：

| 信息源 | 字数 / token | 细节密度 |
|---|---|---|
| 自由文本 | 约 400 字 | 10+ 具体事件（扣球、手套、"处对象"话题、"相处对象"话术、圣诞帽头像、聊崩） |
| 聊天截图（OCR 后表格） | 25 条消息 | 包含时间戳、明显情绪转折（"拒绝回答"、"到此为止了"） |

这个密度足以让 opening hook 拿出 3 条独立 evidence、2-3 个 highlights、1 条 call_to_action 的趋势预演。**信息没有在输入端丢失**——analyze.py 把 OCR 文本 + 原图 URL 一起多模态送进 vision LLM（`analyze.py:124-172`），管道是对的。

### 1.4 数据流没有截断，但"容器不够大"

`first_hook` 从 `AnalyzeResponse` → API → localStorage → `renderOpeningHook` 全程是一个字符串，没有丢字段。问题不是"富内容被半路吃掉"，是"根本没给富内容开字段"。

---

## 2. 根因小结

| 症状 | 根因 | 类型 |
|---|---|---|
| Opening hook 没有 evidences / highlights | `AnalyzeResponse.first_hook` 是 `str`，prompt 还反向禁用加粗 | **契约缺陷** |
| Opening title 经常是半截句子 | 前端用正则硬劈「第一句当 title」 | 前端兜底对错契约的妥协 |
| Card hook 千人一面 | 纯静态模板按选项 key 查表 | **产品决策缺陷**（早期为了"秒出"放弃个性化） |
| Card hook 无 evidences | 数据结构只有 `text+image`，没预留 evidences 位 | 契约缺陷 |
| 有截图也感觉"没被看见" | Opening 阶段就一句话，后面 card 阶段又完全不引用截图 | 信息断流 |

---

## 3. 模型策略（目标方案）

### 3.1 扩 schema：给钩子开够容器

**新 `FirstHook`（替代 `first_hook: str`）**：

```jsonc
{
  "verdict_tag": "信号暴露",          // 3-6 字标签，前端 tag 位
  "verdict_color": "amber",           // violet | amber | red | green（映射 tone）
  "title": "你的\"圣诞帽玩笑\"是压垮节奏的最后一根稻草——但 TA 还没关门。",  // 18-32 字；允许用「」或 "" 标注重点短语（前端自动高亮）
  "body": "2-3 句 · 最多 120 字 · 一段自然语言；建立判断但留悬念",
  "highlights": ["话题踩雷", "关系定义期", "对方撤回"],  // 3 个 4-6 字关键词
  "evidences": [                       // 3 条，每条 20-50 字，直接引用原文/截图片段
    "你提到\"拒绝回答\"+\"到此为止\"——这是 TA 用最小代价按暂停键",
    "截图里 TA 前几条还在接「头套」的梗，10 分钟后突然切短句——情绪掉线点很清楚",
    "你自述「不处对象那种人，常拿帝总开玩笑」——这类玩笑本来是亲密标志，但此刻踩到了关系定义的雷区"
  ],
  "call_to_action": "接下来 5 道题，我帮你分清「TA 是气你这次玩笑」还是「借机划线」。"  // 1 句 · 30-50 字
}
```

> 前端原型字段一一对齐，不再靠正则劈句。

**新 `CardHook`（替代静态查表）**：

```jsonc
{
  "short": "你这次表白式玩笑把 TA 推到了选边位。",  // 大字 · 16-26 字
  "body": "2 句 · 含「问题 + 我们怎么办」·  60-100 字",
  "highlights": ["关系定义期", "撤回信号"],       // 1-3 个
  "evidences": [                                 // 1-2 条 · 每条 ≤40 字 · 必须来自 analyze 阶段的 OCR/原文
    "截图里 TA 说「看看」→「6」→「拒绝回答」，三步撤回"
  ],
  "feature": "局势分析",       // 五选一 · 对齐静态表
  "tag": "组合诊断"             // 复用现有 tag 语义
}
```

### 3.2 输入预处理（保证模型 See the full picture）

保留现状合理部分，**补两个信号提纯步骤**：

1. **OCR 前置摘要器（复用 analyze.py 的多模态调用，但新增一个前置 pass）**
   - 输入：原图 + OCR 表格
   - 输出：`signal_list`（JSON 数组）——每张截图抽 3-5 条"可引用事件"，形如 `{time: "17:53", sender: "crush", text: "拒绝回答", interpretation: "情绪撤回"}`。这个列表作为 analyze 阶段的第二条 user 消息，让模型**直接在 evidences 里 cite** 而不是自己在长 OCR 里"捞"。
   - 证据：当前 `_build_user_message_content:124-172` 直接把原始 OCR 表扔给模型，模型在高噪声下倾向"概括化"——evidences 质量下滑的主因。
   - 成本：+1 次 vision 调用（可复用已有 `image_processor` 的长聊天 OCR 模型，不加新依赖）。

2. **自由文本实体抽取（纯文本 LLM，≤0.5s）**
   - 抽 `entities: {user_persona, crush_persona, relation_channel, key_events[], emotional_turns[]}`
   - 作为 analyze 阶段的 Dossier 注入，既服务 hook，也能写进 `collected_info` 给 main_agent 复用。

### 3.3 Prompt 重构（analyze.md v2 要点）

保留"筛题（skip_rules）"任务，重写"钩子"任务部分：

- **角色**：依然"专业朋友小话"，但显式要求「像记者写 lede：一个判断 + 两条独立证据 + 一个悬念」
- **Few-shot**：加 2 组 good/bad 对照，覆盖（a）只有文本（b）文本 + 截图情绪撤回 两种密度。每组 good 必须 evidences 引用 **OCR 原话或自由文本原句**。
- **Output schema**：直接贴 `FirstHook` 的 JSON Schema（字段 + 字数区间），并强调「evidences 必须来自上面 signal_list 或自由描述原文，不允许自编」
- **反 hedging 条款**：禁用「大概率 / 可能 / 也许」开头；禁用「根据 XX 理论」；禁用一上来就免责
- **长度约束**（关键反薄片）：
  - title 18-32 字（过短= title 被正则误伤，过长= 前端挤到两行）
  - body 80-120 字（不是 `1-3 sentences` 的主观约束，给最小字数下限）
  - evidences ≥3 条且每条 ≥20 字

### 3.4 采样参数

| 场景 | temperature | top_p | 说明 |
|---|---|---|---|
| analyze（筛题+opening hook） | 0.4 | 0.9 | 原来 0.3 偏稳，但 hook 需要语感；关键结构由 schema 保证，提一点温度换表达 |
| card_hook（新增 LLM 路径） | 0.5 | 0.9 | 短文本、个性化，温度再高一点 |
| evidences 抽取子步骤 | 0.1 | 0.8 | 要的是忠实引用，不要发挥 |

- Provider：继续走 `LLM_PROVIDER` + vision 支持的模型（DeepSeek 目前不支持多模态，建议 analyze 阶段强制 `豆包 doubao-vision` 或 OpenAI gpt-4o；fallback 时保留纯文本降级）。
- 超时：`ONBOARDING_ANALYZE_TIMEOUT=18`（现状）够，evidences 抽取并行跑，不拉长端到端。

### 3.5 Card hook 策略（渐进式，不砍现有静态兜底）

两层：

- **L0（秒出，静态）**：保留现有 `hooks.py` 按 key 查表 → 用户点完选项后 **立即** 显示，保证无感延迟。
- **L1（2-4s 异步补强）**：后台 `/api/onboarding/card_hook` 根据 `qid + selected + free_text + ocr_signals` 出**个性化覆盖**，前端用淡入动画替换 L0 文案。失败就不替换。

> 好处：不牺牲现在「秒出」的体验；同时让 LLM 有机会"点名"截图里的细节（真正的"被说中了"瞬间发生在 card 阶段而不是仅 opening）。

### 3.6 兜底与降级

- 契约变了以后 fallback 也要扩字段。`_build_fallback_response` 需要吐出结构完整、evidences 为空列表、title/body 是通用文案的 `FirstHook`，保证前端渲染不崩。
- 前端 `onboarding_flow.js:renderOpeningHook` 的正则劈句逻辑**删掉**，改走 schema 的 title/body/highlights/evidences。
- 如果模型吐的 JSON schema 校验失败，按现有 try/except 走降级，但要打埋点（`first_hook_schema_fail_rate` 上线后监控）。

---

## 4. 评估集每 case 的预估饱满度

以 `Benchmark/新版onboarding自由评估集.md` 的 Case（排球/圣诞帽/聊崩）为基准预估，应用 3.1-3.4 后：

| 维度 | 当前（contract_str） | 新策略（contract_obj） |
|---|---|---|
| verdict_tag | — | 「信号暴露」/「关系定义期」 |
| title | 1 句 · 约 25 字 | 1 句大标题 · 约 28 字（含高亮短语） |
| body | 1-2 句融合 · 约 60 字 | 2-3 句 · 约 100-120 字（判断 + 悬念） |
| highlights | 几乎空 | 3 个 · 覆盖「话题踩雷 / 关系定义期 / 对方撤回」 |
| evidences | 0 | 3 条 · 每条 30-50 字 · 必引 OCR 原话（"拒绝回答"、"到此为止"、17:53 时间点） |
| call_to_action | 基本没有 | 30-50 字 · 平滑衔接到 5 道补充题 |
| 总字数 | 约 80 字 | 约 280-340 字（贴合原型滚动容器高度） |

用户侧的"被说中了"判定点：能否引出截图里那两个最刺激的原句（"拒绝回答"、"到此为止"）——**新策略强制在 evidences 里引用，就能稳定击中**。现状是 0 命中。

其他 case（需要完整跑 benchmark 才能逐一核对，此处先列预期）：**输入文本 < 100 字且只有 1 张图**的 case，evidences 会被降级到 2 条 + 引用折半；但 title/body/highlights 仍能撑起原型容器。

---

## 5. 落地步骤（按投入排序）

### 立刻可以做（≤半天，收益最大）

1. **扩 `AnalyzeResponse.first_hook` 契约**为 `FirstHook` object（schemas.py）
2. **重写 analyze.md v2**：加 few-shot、加 length 约束、加 evidences 必引规则
3. **重写前端 `renderOpeningHook`**：删正则劈句、按新 schema 渲染 evidences 区块（onboarding.html 需加 `#opening-hook-evidences` 容器）
4. **扩 fallback payload**：`_build_fallback_response` 返回完整 `FirstHook` 结构

### 中等投入（1-2 天，质的飞跃）

5. **OCR signal_list 前置抽取**：analyze.py 加一步多模态预抽取，产出 `signal_list` 作为第二条 user message
6. **Card hook L1 异步个性化**：加 `/api/onboarding/card_hook` 端点，前端淡入替换。需要一套新 prompt + schema（复用 FirstHook 的字段集）。
7. **Prompt few-shot 扩到 4 组**：覆盖（文本长+截图）/（文本长+无图）/（文本短+截图多）/（文本短+无图）四种组合

### 大改（如果未来想让 onboarding 整体"可成长"）

8. **引入 benchmark 驱动的 prompt 迭代闭环**：把评估集里每条 case 的预期 hook 打标（人工 30 分钟可完成），上 LangSmith 做 evaluator 跑分。
9. **`preliminary_assessment` 和 `FirstHook` 合流**：目前后端还保留旧 onboarding_agent 的 `preliminary_assessment`（`onboarding_agent.py:679-769`）——这是 v1 残余，v2 已经不在主链路。可以彻底删掉减少双轨困扰。

---

## 6. 风险与取舍

- **延迟**：+1 次 vision 调用 ≈ +3-6s。opening hook 本来就带 loading 动画，用户能接受；card hook L1 走异步覆盖，不阻塞。
- **成本**：`豆包 doubao-vision-pro` 图像单价约 ¥0.015/千 token，单次 analyze ≤¥0.05；量级不敏感。
- **风格一致性**：prompt 放宽后可能"发挥过度"。用 temperature=0.4 + 强 schema + length 约束 + 禁用术语清单组合压住。
- **前端字段缺失兼容**：新字段上线当天，若 Pydantic 校验通过但前端旧版仍在运行，需要保留 `first_hook` 字符串字段半灰度期（渲染优先读 object，缺则读字符串）。

---

## 7. 核心结论（给 PM 打包）

1. 钩子薄的**第一根因**是 `AnalyzeResponse.first_hook: str` + prompt 禁用结构化输出，**不是模型不会写**
2. Card hook **完全没走模型**，是按选项 key 查静态表；"被说中"只能到"选项级"精度，到不了"截图原句级"精度
3. 输入端（自由文本 + 截图 OCR + 原图多模态）管道**没有丢信号**；继续投资"让模型看得更好"不如先投资"让模型写得更多"
4. 最小干预方案：扩 schema + 重写 prompt + 前端按新字段渲染，半天量级，收益立刻肉眼可见
5. 进阶方案：OCR signal_list 前置抽取 + card hook L1 异步个性化，把"个性化被说中"从偶发变成稳定

---

_本文档作为 onboarding 钩子模型策略的单一事实来源。代码与此冲突时，以本策略为 spec，代码改动由主线 agent 执行。_
