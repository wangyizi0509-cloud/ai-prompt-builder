# Layer 2 工作上下文规范（v2.0）

> 目的：定义 Layer 2 的数据结构、提取与输出格式。Layer 2 是“任务周期内的工作台”，承载报告、规划、指南与短期态势。

代码对应：
- 类型：`agent_impl/graph/context_types.py`（`Layer2Memory`、各类 Item）
- 输出：`agent_impl/graph/context_builder.py`（`extract_layer2()`）
- 按需加载：`agent_impl/graph/tools/context_loader.py`

---

## 1. Layer 2 包含 4 类内容

| 类型 | 说明 | 关键特性 |
|:---|:---|:---|
| **动态情报板（Dynamic Intel）** | 短期/时效性态势（日程、情绪、状态、意向） | 有 `expire_at`，提取时过滤过期 |
| **现状分析报告（Status Report）** | 关系诊断快照（当前版本） | 覆盖式更新，历史进入摘要区 |
| **行动规划（Action Plan）** | 阶段性战略框架（当前版本） | 低频更新，历史进入摘要区 |
| **行动指南（Action Guides）** | 可执行任务列表（战术层） | 状态机 + 渐进式披露 + 可按需加载 |

---

## 2. 输出结构（对齐代码）

`extract_layer2()` 的输出按固定顺序拼接：

1. `## 现状分析` → `### 当前报告` → 报告内容
2. `## 行动规划` → `### 当前规划` → 规划内容
3. `## 动态情报板`（可选，有有效情报才出现）
4. `## 行动指南`（可选，有指南且允许注入才出现）
5. `## 历史摘要`（可选，有历史项才出现）

---

## 3. 现状分析报告（Status Report）

### 3.1 数据结构（核心字段）

- `report_id`: str/int（编号）
- `version`: int（版本号）
- `created_at`: ISO 时间
- `report_content`: Markdown 正文（推荐使用）

### 3.2 输出格式（硬契约）

```markdown
## 现状分析
### 当前报告
> 更新时间: MM-DD HH:mm | 版本: n

"""
{report_content}
"""
```

> 要点：正文必须用 `"""` 包裹，避免正文中的 Markdown 标题干扰外层结构。

---

## 4. 行动规划（Action Plan）

### 4.1 数据结构（核心字段）

- `plan_id`: str/int
- `version`: int
- `created_at`: ISO 时间
- `plan_content`: Markdown 正文（推荐使用）

### 4.2 输出格式（硬契约）

```markdown
## 行动规划
### 当前规划
> 更新时间: MM-DD HH:mm | 版本: n

"""
{plan_content}
"""
```

---

## 5. 动态情报板（Dynamic Intel Board）

### 5.1 数据结构（单条情报）

- `id`: str
- `content`: str
- `created_at`: ISO 时间
- `expire_at`: ISO 时间（过期时间）
- `subject`: `"user" | "crush"`
- `category`: str（自由文本）
- `confidence`: float
- `confidence_reason`: str（必填）

### 5.2 提取规则（对齐代码）

- 只提取“未过期”条目（过滤 `expire_at < now`）
- 默认最多注入 **20** 条（`max_dynamic_intels`）
- 先按 `expire_at`（或 `created_at`）排序，再截断
- 按 `subject` 分组输出：用户 / Crush

### 5.3 输出格式

```markdown
## 动态情报板
> 以下是近期的时效性信息，请务必参考。置信度说明：越高越可信。

### 用户
- [MM-DD HH:mm] 内容 (置信度: 0.95 - 原因)

### Crush
- [MM-DD HH:mm] 内容 (置信度: 0.70 - 原因)
```

---

## 6. 行动指南（Action Guides）

### 6.1 状态机（6 种状态）

```text
pending | in_progress | paused | completed | cancelled | expired
```

### 6.2 渐进式披露（关键设计）

原因：指南可能很多，全部展开会打爆 Token；且大多数指南本轮不需要细节。

规则（对齐代码默认配置）：
- `in_progress`：最多展开 **2** 条（完整内容）
- `paused`：最多 2 条（表格索引）
- `pending`：最多 3 条（表格索引）
- `completed`：最多 5 条（表格索引；在历史摘要区会额外展示已完成详情摘要）
- `cancelled`：最多 2 条（表格索引）
- `expired`：最多 2 条（表格索引）

### 6.3 输出结构

行动指南区块以一个提示行开头（指导按需加载），随后分为两段：

1) **进行中：完整展开**

```markdown
## 行动指南
> 需要查看某条指南的完整内容时，调用 context_loader(action="load", context_type="action_guide", context_id="指南ID")

### 🔥 当前进行中 (n)
#### 【指南ID】标题
> 创建: MM-DD HH:mm | 预计过期: MM-DD

"""
{guide_content}
"""
```

2) **非进行中：表格索引 + 摘要**

```markdown
### 📋 其他指南
| id | title | status | summary |
|:---|:------|:-------|:--------|
| g2 | 深度话题储备 | paused | 准备了3个深度话题，暂时用不上。 |
```

---

## 7. 历史摘要（Layer 2 History Summaries）

Layer 2 的历史摘要用于在不注入“历史全文”的情况下保留演进脉络，主要包含：
- 历史报告摘要（近期少量用 `summary`，更早用 `one_liner`）
- 已完成指南摘要（展示执行摘要与用户反馈）

输出整体结构：

```markdown
## 历史摘要

### 近期报告
- **[MM-DD]** {summary}
- [MM-DD] {one_liner}

### 已完成
#### 【指南ID】标题
> 完成于: MM-DD
**执行摘要**: ...
**用户反馈**: ...
```

---

## 8. 常见坑

1. **忘记三引号包裹报告/规划正文**：会导致外层 Markdown 结构被正文标题“吞掉”。
2. **把过期情报注入模型**：会让模型误判当下态势；动态情报必须过滤过期。
3. **指南全量展开**：会直接导致 Token 爆炸；必须采用渐进式披露 + `context_loader` 按需加载。

