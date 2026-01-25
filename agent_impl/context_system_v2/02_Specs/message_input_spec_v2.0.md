# Context Injection 输入规范（`<dossier>` XML v2.0）

> 目的：定义 **Context Injection**（HumanMessage 内的 `<dossier>`）结构、字段含义、最小输入规则，确保上下文“可解析、可追溯、可缓存”。

实现位置：`agent_impl/graph/message_builder.py` → `build_context_xml()`

---

## 1. 最外层结构

`<dossier>` 是单个闭合 XML 根节点，带 `agent` 属性标识目标 Agent。

```xml
<dossier agent="main_agent">
  ...
</dossier>

请阅读以上档案，准备开始咨询。
```

> 末尾追加一行自然语言提示，帮助模型进入“阅读档案”语境。

---

## 2. 字段清单（按实际注入顺序）

> 顺序即稳定性优先级：越稳定越靠前。

### 2.1 Layer 1：用户画像

```xml
<user_context source="layer1">
  ...（Markdown 文本，已 XML escape）
</user_context>
```

- **source**：固定为 `layer1`
- **内容**：见 `02_Specs/layer1_spec_v2.0.md`

---

### 2.2 Layer 2.a：稳定工作上下文（现状报告 + 行动规划）

```xml
<status_report source="layer2">
  ...（Markdown 文本，已 XML escape）
</status_report>

<action_plan source="layer2">
  ...（Markdown 文本，已 XML escape）
</action_plan>
```

- **内容格式**：必须包含 `> 更新时间: ... | 版本: ...`，正文用 `"""` 包裹（见 Layer2 规范）。

---

### 2.3 Layer 2.b：动态工作上下文（行动指南 + 动态情报 + 历史摘要）

```xml
<action_guides source="layer2">
  ...（Markdown 文本，已 XML escape）
</action_guides>
```

```xml
<dynamic_intel source="layer2">
  ...（可选，Markdown 文本，已 XML escape）
</dynamic_intel>
```

```xml
<history_summaries source="layer2">
  ...（可选，Markdown 文本，已 XML escape）
</history_summaries>
```

- `dynamic_intel`、`history_summaries` 只有在内容非空时才注入。
- “行动指南”采用渐进式披露：少量进行中指南展开，其他只给表格索引与摘要（见 Layer2 规范）。

---

### 2.4 任务系统：Task Index + Active Task

```xml
<task_context>
  <task_index>...（Markdown 文本，已 XML escape）</task_index>
  <active_task>...（JSON 字符串，已 XML escape）</active_task>
</task_context>
```

- `task_index`：给模型看的任务列表（可读 Markdown）
- `active_task`：结构化 JSON（字符串形式），便于模型精确读取任务字段

> 任务系统详细规范见 `02_Specs/task_system_spec_v2.0.md`。

---

### 2.5 任务绑定上下文（Bound Contexts，可选）

```xml
<bound_contexts>
  ...（Markdown 文本，已 XML escape）
</bound_contexts>
```

仅当存在绑定上下文时注入。

---

### 2.6 Main Agent → 专家指令（可选）

```xml
<instruction source="main_agent">
  ...（文本，已 XML escape）
</instruction>
```

仅当 `state.instruction` 非空时注入。

---

## 3. 内容编码与安全约束

### 3.1 XML escape（必须）

`<dossier>` 内的文本内容必须对以下字符做 escape：
- `&` → `&amp;`
- `<` → `&lt;`
- `>` → `&gt;`
- `"` → `&quot;`
- `'` → `&apos;`

原因：
- 防止内容破坏 XML 结构
- 降低提示注入风险（把“背景资料”和“指令”边界固定在结构层）

---

## 4. 最小输入规则（允许为空，但结构要对）

为了保证模型在信息不足时也能稳定工作：
- `<user_context>` / `<status_report>` / `<action_plan>` / `<action_guides>` 允许内容为“暂无/空”，但标签必须存在（由 `build_context_xml` 负责）。
- `dynamic_intel`、`history_summaries`、`bound_contexts`、`instruction` 允许整体缺省（不输出标签）。

