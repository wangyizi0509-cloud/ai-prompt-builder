# Layer 3 对话历史规范（v2.0）

> 目的：定义 Layer 3 的“短期工作记忆”结构与输出格式，保证对话连贯性，同时控制无限增长。

代码对应：
- 类型：`agent_impl/graph/context_types.py`（`Layer3Memory`, `ConversationSummary`, Reasoning Notes/Task）
- 输出：`agent_impl/graph/context_builder.py`（`extract_layer3()` / `_format_interleaved_history()`）
- 模型调用时 History：`agent_impl/graph/message_builder.py`（`build_conversation_history()`）

---

## 1. Layer 3 包含 3 类内容

| 内容 | 作用 | 默认上限（代码默认） |
|:---|:---|---:|
| **历史摘要（Conversation Summaries）** | 压缩后的“远古对话”，保留关键语境与结论 | 5 条 |
| **任务笔记（Reasoning Notes）** | 当前任务的关键推理结论（结论导向） | 8 条 |
| **最近对话（Recent Turns）** | 最近 N 轮对话，用于连贯性 | 25 轮（按用户轮次计） |

---

## 2. 输出结构（对齐 `extract_layer3`）

`extract_layer3()` 输出为 Markdown，按如下结构组织：

1. `## 历史摘要`（可选，有摘要才出现）
2. `## 任务笔记「{任务标题或摘要}」`（可选，有活跃任务且有笔记/摘要才出现）
3. `## 对话`（必有；无近期对话则输出占位）

---

## 3. 历史摘要（Conversation Summary）

### 3.1 数据结构（核心字段）

- `summary`: str（摘要文本）
- `topics`: str（逗号分隔的标签，自由文本）
- `created_at`: ISO 时间

### 3.2 输出格式

```markdown
## 历史摘要
- [MM-DD HH:mm/话题1,话题2] 摘要文本
```

---

## 4. 任务笔记（Reasoning Notes）

任务笔记是“结论导向”的推理结果，不记录每轮的思维过程（避免 token 线性增长）。

### 4.1 触发写入的典型场景（经验规则）

- 做出关键判断（例如“对方态度偏冷淡，可能因工作压力”）
- 排除关键假设（例如“无证据支持第三者假设”）
- 策略切换（例如“从推进转为降压”）
- 阶段推进（例如“从暧昧期进入约会推进阶段”）

### 4.2 输出格式

```markdown
## 任务笔记「{title}」
- [MM-DD HH:mm] 结论
- [MM-DD HH:mm] 结论
```

---

## 5. 最近对话（Recent Turns）

### 5.1 输出格式（不标注 U/A，仅以时间戳 + 内容）

每条消息格式：

```text
[MM-DD HH:mm] 内容
```

### 5.2 过滤规则（对齐代码）

在 Layer 3 的“文本化历史”中：
- **跳过 ToolMessage**（role == tool）
- 只保留 `user / assistant(ai) / system` 等可读消息
- 对 assistant 消息做“降噪提取”（见下一节）

### 5.3 assistant 消息降噪（关键）

当 assistant 内容是 JSON（或包含 ```json 代码块）时：
- 只保留 `response`（或兼容字段 `assistant_response`）
- 若包含提问卡片 `inquiry_card.questions`，以“【提问】Q1/Q2…”形式追加

目的是让历史对话更接近“真实对话语境”，而不是把结构化输出的冗余字段带入语境。

---

## 6. 时间戳规则

输出展示时间由 ISO 时间格式化得到：
- 同一年：`MM-DD HH:mm`
- 跨年：`YYYY-MM-DD HH:mm`

若某条消息缺少时间字段，系统会以“当前时间”兜底生成展示时间，避免格式断裂。

