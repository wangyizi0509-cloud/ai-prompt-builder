# 上下文工程输入信息全量审计文档 v1.0

> **创建时间**: 2026-01-13  
> **目的**: 全面梳理当前上下文工程的所有输入信息，为精简优化提供依据  
> **目标**: 每一次模型的输入都是最重要且精简的信息

---

## 〇、全量输入信息速查表（核心表格）

### Layer 1 - 静态情报区

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入 Prompt 逻辑 |
|:-----|:---------|:---------|:-------------|:-----------------|
| Layer 1 | 用户信息 - 用户提供 | `user_info.user_provide` | `"姓名：小明\n年龄：26\n职业：程序员"` | **位置**: `{user_context}` → `#### 用户信息` → `##### 由用户提供的信息`<br>**输入逻辑**: 全量输出，无压缩，作为 Markdown 文本直接拼接 |
| Layer 1 | 用户信息 - 客观事实 | `user_info.fact` | `"用户朋友圈发了健身照（2026-01-10）"` | **位置**: `{user_context}` → `##### 客观事实`<br>**输入逻辑**: 全量输出，信任优先级最高（fact > user_provide > ai_provide） |
| Layer 1 | 用户信息 - AI分析 | `user_info.ai_provide` | `"依恋类型：焦虑型\n核心优势：稳定工作"` | **位置**: `{user_context}` → `##### AI分析`<br>**输入逻辑**: 全量输出，信任优先级最低 |
| Layer 1 | Crush信息 - 用户提供 | `crush_info.user_provide` | `"姓名：小红\n年龄：25\n爱好：画画"` | **位置**: `{user_context}` → `#### Crush信息` → `##### 由用户提供的信息`<br>**输入逻辑**: 全量输出 |
| Layer 1 | Crush信息 - 客观事实 | `crush_info.fact` | `"Crush 说周末要加班（2026-01-12 聊天记录）"` | **位置**: `{user_context}` → `##### 客观事实`<br>**输入逻辑**: 全量输出，从聊天截图抽取 |
| Layer 1 | Crush信息 - AI分析 | `crush_info.ai_provide` | `"沟通风格：直接型\n兴趣点：艺术、咖啡"` | **位置**: `{user_context}` → `##### AI分析`<br>**输入逻辑**: 全量输出 |
| Layer 1 | 双方信息 - 用户提供 | `both_info.user_provide` | `"认识方式：朋友介绍\n认识时间：2个月"` | **位置**: `{user_context}` → `#### 双方关系` → `##### 由用户提供的信息`<br>**输入逻辑**: 全量输出 |
| Layer 1 | 双方信息 - 客观事实 | `both_info.fact` | `"上周一起吃了晚饭"` | **位置**: `{user_context}` → `##### 客观事实`<br>**输入逻辑**: 全量输出 |
| Layer 1 | 双方信息 - AI分析 | `both_info.ai_provide` | `"关系阶段：暧昧期\n亲密度：中等"` | **位置**: `{user_context}` → `##### AI分析`<br>**输入逻辑**: 全量输出 |

### Layer 2 - 动态策略区

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入 Prompt 逻辑 |
|:-----|:---------|:---------|:-------------|:-----------------|
| Layer 2 | 战略规划 | `strategy_plan` | `"## 阶段目标\n从好感期推进到暧昧期\n\n## 核心策略\n1. 增加线下接触\n2. 创造共同话题"` | **位置**: `{strategy_section}` → `### 战略规划`<br>**输入逻辑**: Plan Agent 生成后存入 State，Main/Guide Agent 引用；覆盖式更新（新规划替换旧规划） |
| Layer 2 | 现状分析 | `latest_status_summary` | `"**关系阶段**: 好感期（3/5）\n**最近动态**: 聊天频率下降\n**风险点**: 用户过度追问"` | **位置**: `{strategy_section}` → `### 现状分析`<br>**输入逻辑**: Status Agent 每次分析后覆盖更新；仅保留最新一份 |
| Layer 2 | 行动方案 | `action_plan` | `"**行动类型**: 破冰话题\n**具体建议**: 分享有趣视频\n**预期效果**: 重启对话"` | **位置**: `{strategy_section}` → `### 行动方案`<br>**输入逻辑**: Guide Agent 生成，单次使用后可选保留或清除 |
| Layer 2 | 行动上下文 | `action_context` | `"Crush 上周提到喜欢综艺，用户可以从这个点切入"` | **位置**: 与 `action_plan` 合并输出<br>**输入逻辑**: 为行动提供背景支撑，与 action_plan 一起生成 |

### Layer 3 - 对话上下文（用户消息）

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入 Prompt 逻辑 |
|:-----|:---------|:---------|:-------------|:-----------------|
| Layer 3 | 用户消息 - 纯文本 | `content` (str) | `"我应该怎么回复她？她说今天加班很累"` | **位置**: `{conversation_history}`<br>**格式**: `[用户]: 我应该怎么回复她？她说今天加班很累`<br>**输入逻辑**: 按时间顺序与所有消息排列在同一队列，human/ai 用标签区分 |
| Layer 3 | 用户消息 - 带图片 | `content` (list: image_url + text) | `[{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}, {"type": "text", "text": "帮我分析"}]` | **位置**: `{conversation_history}`<br>**格式**: `[用户]: [上传了聊天截图]\n---\n[Crush 聊天记录]:\n- [Crush 14:30]: xxx\n- [用户 14:35]: xxx\n---`<br>**输入逻辑**: 图片经 OCR 提取后结构化，聊天记录单独格式化展示 |
| Layer 3 | 用户消息 - 回答提问 | `content` (str) | `"朋友介绍的"` | **位置**: `{conversation_history}`<br>**格式**: `[用户]: 朋友介绍的`<br>**输入逻辑**: 与普通文本消息格式一致，不特殊标记是"回答" |

### Layer 3 - 对话上下文（AI 消息）

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入 Prompt 逻辑 |
|:-----|:---------|:---------|:-------------|:-----------------|
| Layer 3 | AI消息 - 普通回复 | `content` (str) | `"建议你先表达关心，可以这样回复：'辛苦了，今天一定很累吧...'"` | **位置**: `{conversation_history}`<br>**格式**: `[AI]: 建议你先表达关心，可以这样回复：...`<br>**输入逻辑**: 仅 content 进入对话历史，thinking 不进入 |
| Layer 3 | AI消息 - 普通回复（内部字段） | `response_metadata.thinking` | `"用户需要回复建议，Crush 表达了疲惫，应该先共情..."` | **位置**: ❌ 不进入 Prompt<br>**输入逻辑**: 仅用于内部调试/日志，不输入下一轮对话 |
| Layer 3 | AI消息 - 普通回复（内部字段） | `response_metadata.intent` | `"guide_reply"` | **位置**: ❌ 不进入 Prompt<br>**输入逻辑**: 仅用于路由判断 |
| Layer 3 | AI消息 - 普通回复（内部字段） | `response_metadata.agent` | `"main_agent"` | **位置**: ❌ 不进入 Prompt<br>**输入逻辑**: 仅用于追踪来源 |
| Layer 3 | AI消息 - 提问 | `content` / `question` | `"请问你们是怎么认识的？"` | **位置**: `{conversation_history}`<br>**格式**: `[AI]: 请问你们是怎么认识的？\n[选项卡片: 朋友介绍 \| 工作认识 \| 网络社交 \| 其他]`<br>**输入逻辑**: question 作为 content 进入，options 拼接为选项卡片格式 |
| Layer 3 | AI消息 - 提问（内部字段） | `response_metadata.reasoning` | `"需要了解关系背景才能给出准确建议"` | **位置**: ⚠️ **问题点**：当前可能进入对话历史<br>**应有逻辑**: 不应进入 Prompt，仅内部使用 |
| Layer 3 | AI消息 - 提问（内部字段） | `response_metadata.options` | `["朋友介绍", "工作认识", "网络社交", "其他"]` | **位置**: `{conversation_history}` 中作为选项卡片展示<br>**格式**: `[选项卡片: 朋友介绍 \| 工作认识 \| ...]`<br>**输入逻辑**: 转为管道符分隔的纯文本 |
| Layer 3 | AI消息 - 提问（内部字段） | `response_metadata.inquiry_card` | `{"card_type": "single_choice", "title": "认识方式", "options": [...], "allow_custom": true}` | **位置**: ❌ 不进入 Prompt<br>**输入逻辑**: 仅用于前端渲染卡片 UI |

### Layer 3 - 对话上下文（工具调用）

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入 Prompt 逻辑 |
|:-----|:---------|:---------|:-------------|:-----------------|
| Layer 3 | 工具调用消息 | `tool_calls` (list) | `[{"id": "call_xxx", "name": "save_action_plan", "args": {"plan_type": "破冰话题", "content": "..."}}]` | **位置**: ❌ 通常不进入 Prompt<br>**输入逻辑**: 工具调用是内部执行，不作为对话历史展示 |
| Layer 3 | 工具结果消息 | `role: "tool"`, `content`, `tool_call_id`, `name` | `{"role": "tool", "content": "{\"success\": true}", "tool_call_id": "call_xxx", "name": "save_action_plan"}` | **位置**: ❌ 通常不进入 Prompt<br>**输入逻辑**: 工具执行结果仅用于当前轮次判断，不进入对话历史 |

### Layer 3 - 对话上下文（Agent 间传递）

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入 Prompt 逻辑 |
|:-----|:---------|:---------|:-------------|:-----------------|
| Layer 3 | Agent 传递 - 通过 State | `current_intent` | `"status_analysis"` | **位置**: ❌ 不进入对话历史<br>**输入逻辑**: Main Agent 设置，Sub Agent 读取，用于路由 |
| Layer 3 | Agent 传递 - 通过 State | `collected_info` | `{"认识方式": "朋友介绍", "认识时间": "2个月"}` | **位置**: ✅ 进入 Prompt（`{collected_info}` 变量）<br>**格式**: `### 已收集信息\n- 认识方式: 朋友介绍\n- 认识时间: 2个月`<br>**输入逻辑**: Inquiry Skill 收集后传递给下游 Agent |
| Layer 3 | Agent 传递 - 通过 State | `pending_questions` | `[{"question": "你们多久聊一次？", "priority": 1, "category": "interaction"}]` | **位置**: ❌ 不进入对话历史<br>**输入逻辑**: 内部问题队列，Inquiry Skill 消费 |
| Layer 3 | Agent 传递 - 通过 State | `sub_agent_result` | `{"summary": "关系处于好感期...", "suggestions": ["增加接触", "创造话题"]}` | **位置**: ✅ 进入 Finalizer Prompt<br>**输入逻辑**: Sub Agent 分析结果，Finalizer 组装为最终输出 |
| Layer 3 | Agent 传递 - 通过消息 | `role: "system"` + `content` | `"[Agent Transfer] status_agent → guide_agent\n现状分析完成，关系处于好感期..."` | **位置**: ⚠️ **问题点**：当前会进入对话历史<br>**应有逻辑**: 不应进入用户可见的对话历史，浪费 Token |

### Layer 3 - 对话历史管理

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入 Prompt 逻辑 |
|:-----|:---------|:---------|:-------------|:-----------------|
| Layer 3 | 窗口配置 | `MAX_HISTORY_LENGTH` | `25` | **位置**: 代码常量，非 Prompt 内容<br>**输入逻辑**: 超过 25 条消息时，旧消息归档后删除 |
| Layer 3 | 归档摘要 | `archived_summary` | `"[历史摘要] 用户在1月10日讨论了约会计划..."` | **位置**: ⚠️ 当前未实现注入<br>**应有逻辑**: 应在对话历史开头注入，保留历史上下文 |

---

## 一、架构总览

### 1.1 分层长期记忆架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 0: 系统指令区                        │
│  - 角色人设（小话）、核心法则（ACR/L-T）、信任优先级            │
│  - 策略：只读常驻，永不压缩                                    │
│  - Token 预算：4,000                                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Layer 1: 静态情报区                        │
│  - 3×3 情报矩阵：                                             │
│    • user_info / crush_info / both_info                      │
│    • user_provide / fact / ai_provide                        │
│  - 策略：全量输出，信任优先级排序                              │
│  - Token 预算：3,000                                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Layer 2: 动态策略区                        │
│  - 战略规划 (strategy_plan)                                   │
│  - 现状分析 (latest_status_summary)                          │
│  - 行动方案 (action_plan + action_context)                   │
│  - 策略：按需注入，可覆盖更新                                  │
│  - Token 预算：2,000                                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Layer 3: 对话上下文                        │
│  - 用户消息、AI 回复、问答卡片、工具调用                       │
│  - 策略：滑动窗口 25 条，超出归档                             │
│  - Token 预算：动态                                           │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 信息流向与处理链路

```
用户输入 → Main Agent → Status/Plan/Guide Agent → Skill 技能 → Finalizer → 用户
    ↓           ↓              ↓                      ↓           ↓
    │      路由决策        深度分析/规划           执行技能      组装输出
    │           │              │                      │           │
    └───────────┴──────────────┴──────────────────────┴───────────┘
                              ↓
                    ArchiveManager 归档管理
                    （信息抽取 → 分类存储）
```

---

## 二、Layer 1: 静态情报区详细梳理

### 2.1 信息结构

| 信息分类 | 输入字段 | 字段含义 | 输入格式示例 | Prompt 位置与逻辑 |
|:---------|:---------|:---------|:-------------|:------------------|
| **用户信息 - 用户提供** | `user_info.user_provide` | 用户主动告知的个人信息 | `"姓名：小明\n年龄：26\n职业：程序员\n性格：内向"` | **位置**: `{user_context}` → `#### 用户信息` → `##### 由用户提供的信息`<br>**逻辑**: 全量输出，不压缩 |
| **用户信息 - 客观事实** | `user_info.fact` | AI 观察到的客观行为/事件 | `"用户朋友圈发了健身照（2026-01-10）"` | **位置**: `{user_context}` → `##### 客观事实`<br>**逻辑**: 全量输出，信任优先级最高 |
| **用户信息 - AI分析** | `user_info.ai_provide` | AI 推断的用户特质 | `"依恋类型：焦虑型\n核心优势：稳定工作、幽默感"` | **位置**: `{user_context}` → `##### AI分析`<br>**逻辑**: 全量输出，信任优先级最低 |
| **Crush信息 - 用户提供** | `crush_info.user_provide` | 用户描述的 Crush 信息 | `"姓名：小红\n年龄：25\n职业：设计师\n爱好：画画、旅行"` | **位置**: `{user_context}` → `#### Crush信息` → `##### 由用户提供的信息`<br>**逻辑**: 全量输出 |
| **Crush信息 - 客观事实** | `crush_info.fact` | 聊天记录中的客观信息 | `"Crush 提到周末要加班（2026-01-12）"` | **位置**: `{user_context}` → `##### 客观事实`<br>**逻辑**: 全量输出 |
| **Crush信息 - AI分析** | `crush_info.ai_provide` | AI 推断的 Crush 特质 | `"沟通风格：直接型\n兴趣点：艺术、咖啡"` | **位置**: `{user_context}` → `##### AI分析`<br>**逻辑**: 全量输出 |
| **双方信息 - 用户提供** | `both_info.user_provide` | 用户描述的关系信息 | `"认识方式：朋友介绍\n认识时间：2个月"` | **位置**: `{user_context}` → `#### 双方关系`<br>**逻辑**: 全量输出 |
| **双方信息 - 客观事实** | `both_info.fact` | 观察到的互动事实 | `"上周一起吃了晚饭"` | **位置**: 同上<br>**逻辑**: 全量输出 |
| **双方信息 - AI分析** | `both_info.ai_provide` | AI 推断的关系现状 | `"关系阶段：暧昧期\n亲密度：中等"` | **位置**: 同上<br>**逻辑**: 全量输出 |

### 2.2 信息来源与抽取逻辑

**抽取触发**: `ArchiveManager.extract_and_archive()` 在每次对话结束后执行

**抽取策略** (来自 `extraction_strategy.py`):
- **抽取规则**:
  - 优先抽取客观事实 (`fact`)
  - 用户明确陈述 → `user_provide`
  - AI 推断结论 → `ai_provide`
- **去重策略**: 语义相似度检测，避免重复存储
- **合并策略**: 新信息覆盖旧信息（如年龄更新）

---

## 三、Layer 2: 动态策略区详细梳理

### 3.1 信息结构

| 信息分类 | 输入字段 | 字段含义 | 输入格式示例 | Prompt 位置与逻辑 |
|:---------|:---------|:---------|:-------------|:------------------|
| **战略规划** | `strategy_plan` | 长期追求策略 | `"## 阶段目标\n从好感期推进到暧昧期\n\n## 核心策略\n1. 增加线下接触\n2. 创造共同话题"` | **位置**: `{strategy_section}` → `### 战略规划`<br>**逻辑**: 由 Plan Agent 生成，Main Agent 参考 |
| **现状分析** | `latest_status_summary` | 当前关系现状总结 | `"**关系阶段**: 好感期（3/5）\n**最近动态**: 聊天频率下降，Crush 回复变慢\n**风险点**: 用户过度追问引发压力"` | **位置**: `{strategy_section}` → `### 现状分析`<br>**逻辑**: 由 Status Agent 生成，每次现状分析后更新 |
| **行动方案** | `action_plan` | 具体行动指令 | `"**行动类型**: 破冰话题\n**具体建议**: 分享今天看到的有趣视频\n**预期效果**: 重启对话"` | **位置**: `{strategy_section}` → `### 行动方案`<br>**逻辑**: 由 Guide Agent 生成 |
| **行动上下文** | `action_context` | 行动背景信息 | `"Crush 上周提到喜欢看综艺，用户可以从这个点切入"` | **位置**: 与 `action_plan` 合并<br>**逻辑**: 为行动提供背景支撑 |

### 3.2 生成与更新逻辑

| 字段 | 生成者 | 触发条件 | 更新频率 |
|:-----|:-------|:---------|:---------|
| `strategy_plan` | Plan Agent | 用户请求制定计划 / 关系阶段变化 | 低频（阶段性） |
| `latest_status_summary` | Status Agent | 每次调用现状分析 | 中频（按需） |
| `action_plan` | Guide Agent | 用户请求行动建议 | 高频（每次请求） |

---

## 四、Layer 3: 对话上下文详细梳理

### 4.1 消息类型总览

| 消息类型 | 来源 | 包含字段 | 输入格式 | 在 Prompt 中的表现 |
|:---------|:-----|:---------|:---------|:-------------------|
| **用户文本消息** | 用户输入 | `content` | `"我想问一下..."` | `[用户]: 我想问一下...` |
| **用户图片消息** | 用户上传 | `content` (base64/URL) | `[图片数据]` | `[用户]: [图片: 聊天截图]` + 结构化提取内容 |
| **AI 普通回复** | Agent 输出 | `content`, `thinking` | 见下方详细 | `[AI]: 回复内容...` |
| **AI 提问消息** | Inquiry Skill | `question`, `reasoning`, `inquiry_card` | 见下方详细 | `[AI]: 提问内容` + 卡片渲染 |
| **工具调用消息** | Agent 调用 | `tool_calls`, `tool_results` | 见下方详细 | 通常不直接显示给用户 |

### 4.2 用户消息详细结构

#### 4.2.1 用户文本消息

```json
{
  "role": "human",
  "content": "我应该怎么回复她？她说她今天加班很累"
}
```

**Prompt 格式**:
```
[用户]: 我应该怎么回复她？她说她今天加班很累
```

#### 4.2.2 用户图片消息（聊天截图）

```json
{
  "role": "human",
  "content": [
    {
      "type": "image_url",
      "image_url": {"url": "data:image/png;base64,..."}
    },
    {
      "type": "text", 
      "text": "这是我们的聊天记录，帮我分析一下"
    }
  ]
}
```

**处理逻辑** (来自 `image_processor.py`):
1. 图片 OCR 提取文本
2. 结构化解析为 `crush_messages` 格式
3. 存入 `crush_chat_history`

**Prompt 格式**:
```
[用户]: [上传了聊天截图]
---
[Crush 聊天记录]:
- [Crush 14:30]: 今天加班好累啊
- [用户 14:35]: 辛苦了，注意休息
- [Crush 14:36]: 谢谢关心
---
```

### 4.3 AI 消息详细结构

#### 4.3.1 AI 普通回复

```json
{
  "role": "ai",
  "content": "建议你先表达关心，然后...",
  "response_metadata": {
    "thinking": "用户需要回复建议，Crush 表达了疲惫...",
    "intent": "guide_reply",
    "agent": "main_agent"
  }
}
```

**Prompt 格式** (对话历史中):
```
[AI]: 建议你先表达关心，然后...
```

**注意**: `thinking` 字段在对话历史中**不显示**，仅用于内部调试。

#### 4.3.2 AI 提问消息 (Inquiry Skill)

**完整数据结构**:
```json
{
  "role": "ai",
  "content": "请问你们是怎么认识的？",
  "response_metadata": {
    "question": "请问你们是怎么认识的？",
    "reasoning": "需要了解关系背景才能给出准确建议",
    "options": ["朋友介绍", "工作认识", "网络社交", "其他"],
    "inquiry_card": {
      "card_type": "single_choice",
      "title": "认识方式",
      "options": ["朋友介绍", "工作认识", "网络社交", "其他"],
      "allow_custom": true
    },
    "agent": "status_agent",
    "skill": "inquiry"
  }
}
```

**Prompt 格式** (对话历史中):
```
[AI]: 请问你们是怎么认识的？
[选项卡片: 朋友介绍 | 工作认识 | 网络社交 | 其他]
```

**字段说明**:
| 字段 | 用途 | 是否输入 Prompt |
|:-----|:-----|:----------------|
| `question` | 问题文本 | ✅ 作为 AI 消息内容 |
| `reasoning` | 提问原因 | ❌ 仅内部使用 |
| `options` | 选项列表 | ✅ 渲染为选项卡片 |
| `inquiry_card` | 卡片配置 | ❌ 仅前端渲染用 |

#### 4.3.3 AI 工具调用消息

```json
{
  "role": "ai",
  "content": "",
  "tool_calls": [
    {
      "id": "call_xxx",
      "name": "save_action_plan",
      "args": {
        "plan_type": "破冰话题",
        "content": "分享有趣视频",
        "context": "Crush 喜欢综艺"
      }
    }
  ]
}
```

**Prompt 格式**: 
- 工具调用消息**通常不进入对话历史**
- 仅在调试模式下可见

#### 4.3.4 工具调用结果消息

```json
{
  "role": "tool",
  "content": "{\"success\": true, \"message\": \"行动方案已保存\"}",
  "tool_call_id": "call_xxx",
  "name": "save_action_plan"
}
```

**Prompt 格式**: 
- 同上，通常不进入对话历史

### 4.4 Agent 间传递信息

#### 4.4.1 通过 State 传递

| 字段 | 传递路径 | 内容示例 | 是否进入 Prompt |
|:-----|:---------|:---------|:----------------|
| `current_intent` | Main → Sub Agents | `"status_analysis"` | ❌ 仅路由用 |
| `collected_info` | Inquiry → Next Agent | `{"认识方式": "朋友介绍"}` | ✅ 作为上下文 |
| `pending_questions` | Status → Inquiry | `[{"question": "...", "priority": 1}]` | ❌ 内部队列 |
| `sub_agent_result` | Sub Agent → Finalizer | `{"summary": "...", "suggestions": [...]}` | ✅ 作为输出素材 |

#### 4.4.2 通过消息传递

```json
{
  "role": "system",
  "content": "[Agent Transfer] status_agent → guide_agent\n现状分析完成，用户关系处于好感期..."
}
```

**注意**: 这类系统消息**会进入对话历史**，占用 Token。

### 4.5 对话历史管理

#### 4.5.1 滑动窗口机制

```python
# message_utils.py
MAX_HISTORY_LENGTH = 25  # 保留最近 25 条消息

def trim_messages(messages: list) -> list:
    if len(messages) > MAX_HISTORY_LENGTH:
        return messages[-MAX_HISTORY_LENGTH:]
    return messages
```

#### 4.5.2 归档机制

**触发条件**: 消息数超过 25 条

**归档流程**:
1. 提取超出窗口的旧消息
2. 调用 `ArchiveManager.extract_and_archive()` 
3. 抽取关键信息存入 Layer 1
4. 生成摘要存入归档存储
5. 从 State 中删除旧消息

#### 4.5.3 消息格式化逻辑

```python
# context_builder.py → build_conversation_history()
def format_message(msg):
    role = "用户" if msg.role == "human" else "AI"
    content = msg.content
    
    # 处理提问消息
    if hasattr(msg, 'inquiry_card') and msg.inquiry_card:
        content += f"\n[选项: {' | '.join(msg.inquiry_card.options)}]"
    
    return f"[{role}]: {content}"
```

---

## 五、各 Agent Prompt 模板结构对比

### 5.1 Main Agent (`main_agent.md`)

```markdown
# 角色设定
你是"小话"，一个专业的恋爱顾问...

# 核心法则
1. ACR 法则...
2. L-T 法则...

# 用户情报
{user_context}

# 策略规划
{strategy_section}

# 对话历史
{conversation_history}

# 当前用户消息
{current_message}

# 任务
分析用户意图，决定路由...
```

### 5.2 Status Agent (`status_agent.md`)

```markdown
# 角色设定
你是现状分析专家...

# 分析框架
1. 关系阶段判断...
2. 风险识别...

# 用户情报
{user_context}

# 历史分析
{previous_status_summary}

# 对话历史
{conversation_history}

# 当前任务
{current_task}

# 已收集信息
{collected_info}
```

### 5.3 对比分析

| Prompt 区块 | Main Agent | Status Agent | Plan Agent | Guide Agent |
|:------------|:-----------|:-------------|:-----------|:------------|
| 角色设定 | ✅ | ✅ | ✅ | ✅ |
| 核心法则 | ✅ | ✅ | ✅ | ✅ |
| 用户情报 (`user_context`) | ✅ | ✅ | ✅ | ✅ |
| 策略规划 (`strategy_section`) | ✅ | ❌ | ✅ | ✅ |
| 历史分析 | ❌ | ✅ | ❌ | ❌ |
| 对话历史 | ✅ | ✅ | ✅ | ✅ |
| 已收集信息 | ❌ | ✅ | ❌ | ❌ |

---

## 六、当前问题与优化建议

### 6.1 🚨 识别出的问题

#### 问题 1: Layer 1 信息无差异化输出
- **现状**: 所有 3×3 矩阵字段全量输出，无论是否与当前任务相关
- **影响**: Token 浪费，可能包含大量无关信息
- **示例**: 用户问"怎么回复这条消息"，不需要完整的用户性格分析

#### 问题 2: Layer 3 消息格式不一致
- **现状**: 
  - 普通消息: `[用户]: xxx`
  - 提问消息: 包含 `reasoning`、`inquiry_card` 等元数据
  - Agent 传递: `[Agent Transfer]` 系统消息
- **影响**: 模型需要解析多种格式，增加认知负担

#### 问题 3: 内部信息泄露到 Prompt
- **现状**: 
  - `reasoning` 字段有时进入对话历史
  - `thinking` 字段在某些路径下可见
- **影响**: 占用 Token，可能影响模型行为

#### 问题 4: Agent 间传递信息冗余
- **现状**: `[Agent Transfer]` 消息进入对话历史
- **影响**: 用户无需看到的内部协调信息占用窗口

#### 问题 5: Layer 2 策略信息堆叠
- **现状**: `strategy_plan` + `status_summary` + `action_plan` 同时输出
- **影响**: 信息可能重复或冲突

### 6.2 💡 优化建议

#### 建议 1: 实施 Layer 1 按需加载
```python
# 根据 intent 决定加载哪些情报
def get_relevant_context(intent: str) -> dict:
    if intent == "guide_reply":
        return {
            "crush_info": True,   # 需要 Crush 信息
            "user_info": False,   # 不需要用户信息
            "both_info": True     # 需要关系信息
        }
    elif intent == "status_analysis":
        return {"all": True}      # 全量加载
```

#### 建议 2: 统一 Layer 3 消息格式
```markdown
# 统一格式
[{timestamp}] [{角色}]: {内容}

# 示例
[14:30] [用户]: 她说加班很累，我怎么回？
[14:31] [AI]: 建议先表达关心...

# 隐藏字段
- reasoning → 不进入对话历史
- inquiry_card → 仅前端渲染
- tool_calls → 不进入对话历史
```

#### 建议 3: 分离内部通信与用户对话
```python
# State 中区分两个列表
messages: list[Message]           # 用户可见消息
internal_notes: list[InternalNote] # Agent 间通信

# 只有 messages 进入 Prompt
```

#### 建议 4: Layer 2 按需组装
```python
# 根据 Agent 类型决定注入哪些策略信息
AGENT_CONTEXT_MAP = {
    "main_agent": ["strategy_plan"],  # 只需大方向
    "status_agent": ["previous_status_summary"],  # 只需历史分析
    "guide_agent": ["action_context", "status_summary"],  # 需要行动背景
}
```

### 6.3 📊 Token 预算估算

| 层级 | 当前估算 | 优化后估算 | 节省比例 |
|:-----|:---------|:-----------|:---------|
| Layer 0 | 4,000 | 4,000 | 0% (不压缩) |
| Layer 1 | 3,000 | 1,500 | 50% |
| Layer 2 | 2,000 | 1,000 | 50% |
| Layer 3 | 动态 | 动态 (-20%) | 20% |
| **总计** | ~9,000+ | ~6,500 | ~28% |

---

## 七、下一步行动项

### 7.1 高优先级 (P0)
- [ ] 分离 `internal_notes` 与 `messages`
- [ ] 移除 `reasoning`、`thinking` 从对话历史
- [ ] 统一消息格式规范

### 7.2 中优先级 (P1)  
- [ ] 实现 Layer 1 按需加载机制
- [ ] 优化 Layer 2 按 Agent 类型组装

### 7.3 低优先级 (P2)
- [ ] 引入语义去重检测
- [ ] 评估 Prompt Caching 收益

---

## 附录 A: 关键文件索引

| 文件 | 职责 |
|:-----|:-----|
| `context_builder.py` | 构建各层上下文 |
| `context_types.py` | 上下文类型定义 |
| `archive_manager.py` | 归档管理与信息抽取 |
| `extraction_strategy.py` | 信息抽取策略 |
| `message_utils.py` | 消息处理工具 |
| `prompts/*.md` | 各 Agent Prompt 模板 |
| `state.py` | 全局状态定义 |

## 附录 B: 行业最佳实践参考

### B.1 LangGraph 官方记忆分层模型

| 上下文类型 | 可变性 | 生命周期 | 存储方式 | 对应本项目 |
|-----------|--------|----------|----------|------------|
| **Runtime Context** (静态运行时) | 不可变 | 单次调用 | `context` 参数 | Layer 0 |
| **State** (动态运行时/短期记忆) | 可变 | 单次会话 | LangGraph State | Layer 2 + 3 |
| **Store** (跨会话/长期记忆) | 可变 | 跨会话 | LangGraph Store | Layer 1 |

### B.2 Anthropic Context Engineering 建议

1. **Prompt 稳定前缀**: 将不变内容放在 Prompt 开头，利用 Prompt Caching
2. **按需加载**: 只注入当前任务需要的上下文
3. **分层信任**: 明确区分 System/User 内容的信任级别
4. **递进披露**: 复杂流程分步骤加载上下文

### B.3 mem0 记忆分类体系

| 记忆类型 | 定义 | 示例 |
|----------|------|------|
| **Semantic** | 静态事实 | 用户名字、职业 |
| **Episodic** | 事件记忆 | "上周你们吃了火锅" |
| **Procedural** | 偏好/习惯 | "用户喜欢简洁回复" |

---

*文档版本: v1.0 | 最后更新: 2026-01-13*
