## 上下文加载/绑定工具：`context_loader`

`context_loader` 的目标是解决一个实际问题：

> 模型在当前轮次里“看到了某段上下文”，但我们不希望把所有细节永久塞进对话历史；同时，有些上下文又必须跨轮次持续可见。

因此 `context_loader` 设计了两条路径：

- **load**：只看一眼（一次性使用），不绑定，不影响后续轮次
- **bind**：绑定到当前 active task，后续多轮自动注入（跨轮次复用）

工具实现见 `agent_impl/graph/tools/context_loader.py`，输入 schema 见 `agent_impl/graph/tools/schemas.py:ContextLoaderInput`。

---

## 1. 什么时候用 load，什么时候用 bind

### 用 `load`（一次性）

- 你只需要“把某条内容读出来”辅助当前轮次决策
- 这段内容不会在后续多轮反复引用
- 你不希望任务上下文膨胀

### 用 `bind`（跨轮次）

- 你需要在后续多轮持续引用同一段内容（例如行动指南步骤、关键历史片段）
- 你希望系统在每轮 prompt 里自动注入这段内容
- 你明确它属于当前任务推进的一部分

**强规则**：只看一眼用 `load`，跨轮次复用才 `bind`。

---

## 2. 输入字段（ContextLoaderInput）

`context_loader` 主要字段：

- **action**：`"load" | "bind" | "unbind" | "refresh"`
- **context_type**：
  - `"action_guide"`
  - `"status_report"`
  - `"action_plan"`
  - `"crush_chat"`
  - `"history_snippet"`
  - `"custom"`（当前实现里不支持直接 load/bind 自定义内容；更多是占位）
- **context_id**：上下文 ID（不同类型含义不同，见下文）
- **expire_at**：ISO 字符串（bind/refresh 可选，用于设置/续期）

---

## 3. 各 context_type 的数据源与 context_id 规则

### 3.1 `action_guide`

数据源（按优先级）：

- `state.layer2_memory.action_guides`
- 兼容：`state.action_guides`

`context_id` 规则：

- 传指南的 `id`（或旧字段 `guide_id`）

返回内容：

- 优先返回 `guide_content`（完整 Markdown）
- 否则拼装 `steps` / `talking_points`

### 3.2 `status_report`

数据源：

- `state.layer2_memory.current_status_report`
- `state.layer2_memory.status_report_history`

`context_id` 规则：

- `"current"` 或空：读取 current_status_report
- 或传某条报告的 `id` / `report_id`

返回内容：

- `report_content`（通常是 Markdown/长文本）

### 3.3 `action_plan`

数据源：

- `state.layer2_memory.current_action_plan`
- `state.layer2_memory.action_plan_history`

`context_id` 规则：

- `"current"` 或空：读取 current_action_plan
- 或传某条规划的 `id` / `plan_id`

返回内容：

- `plan_content`

### 3.4 `history_snippet`

数据源：

- `state.layer3_memory.conversation_summaries`

`context_id` 规则：

- 若是数字字符串（例如 `"0"`）：按索引读取（0 表示最早还是最近，取决于 summaries 的存储顺序；当前实现是直接按列表索引）  
- 或传 summary 的 `id`

返回内容：

- `summary`

### 3.5 `crush_chat`

数据源：

- `state.crush_chat_storage`（通常是 dict）

`context_id` 规则：

- 目前更多是占位，返回时会把 `context_id` 或 `"crush_chat"` 当作 meta 的 id/ref_id

返回内容：

- 优先取 `summary`，否则取 `metadata`
- 若是 dict，会 `json.dumps` 成字符串

### 3.6 `custom`

当前 `_load_context` 对 `custom` 直接返回 None（即工具返回“未找到对应上下文”）。如果未来要支持自定义内容，需要扩展实现与 schema。

---

## 4. 工具输出结构

### 4.1 `action="load"` 的输出

成功时（示意）：

- `success: true`
- `action: "load"`
- `context: {id,title,type,ref_id}`
- `content_md: "<Markdown/文本>"`

### 4.2 `action="bind"` 的输出

除了 `load` 的内容，还会包含：

- `bound_to_task: <task_id>`（绑定到哪个 active task）
- `updated: bool`（是否为“更新已绑定项”）
- `bound_contexts_index: [...]`（绑定列表索引）
- 可能包含 `evicted: {...}`（超限淘汰信息）

### 4.3 `action="unbind"/"refresh"` 的输出

成功时会返回：

- `bound_contexts_index: [...]`（最新绑定列表）

失败时会返回统一错误 JSON（`tool_error_response`），并可能附带 `available_ids` 提示。

---

## 5. 绑定策略：去重、限额与淘汰

### 5.1 去重/更新（updated=True）

当你 `bind` 时，如果满足：

- 同一个 `context_type`
- 且 `ref_id` 相同

则会认为是同一条上下文的“刷新/更新绑定”，会覆盖原项，而不是新增（返回 `updated=True`）。

### 5.2 类型限额（BOUND_CONTEXT_LIMITS）

绑定上下文按 `context_type` 有数量上限（见 `agent_impl/graph/context_types.py:BOUND_CONTEXT_LIMITS`），例如：

- `action_guide`: 3
- `status_report`: 1
- `action_plan`: 1
- `crush_chat`: 3
- `history_snippet`: 3
- `custom`: 3
- `default`: 3

### 5.3 淘汰策略（evicted）

当某一类型绑定数超过上限，系统会淘汰“最早绑定”的一条（按 `bound_at` 排序）：

- 优先在同类型中选择带 `expire_at` 的项作为淘汰候选
- 否则在同类型全部项中选最早绑定的

淘汰信息会以 `evicted` 字段返回，帮助模型理解“为什么少了一条”。

---

## 6. 状态写回：绑定信息存在哪

`context_loader(action="bind"/"unbind"/"refresh")` 会写回到：

- `state.layer3_memory.task_registry[current_agent]` 的 active task
  - `active_task.bound_contexts = [...]`

因此它与任务系统强相关：**没有 active task 就无法 bind**（会报错“当前没有活跃任务”）。

任务系统详见 [`task_system_tooling.md`](task_system_tooling.md)。

