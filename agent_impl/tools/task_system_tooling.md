## 任务系统工具：`task_manager`

任务系统的目标是：**在多轮对话里，把“用户的一个目标/问题”当作一个可持续推进的任务容器**。这样系统可以：

- 在用户跳话题时切换任务，避免上下文串味
- 在同一任务内保留必要的推理笔记（reasoning_notes）
- 把需要跨轮次复用的上下文绑定到任务（bound_contexts）

本系统的任务数据主要存放在：

- `state.layer3_memory.task_registry[agent_name]`（最新版主路径）

工具实现见 `agent_impl/graph/tools/task_tools.py`。

---

## 1. 任务数据结构（TaskState）

任务对象由 `agent_impl/graph/context_types.py:create_new_task()` 创建，核心字段如下：

- **task_id**：任务唯一标识（建议语义化，例如“判断crush是否喜欢用户”）
- **title**：展示标题（默认等于 task_id）
- **summary**：短摘要（默认 `任务: <task_id前20字>`）
- **status**：`active | pending | completed`
- **started_at**：开始时间（ISO）
- **completed_at**：完成时间（ISO，可为空）
- **completion_summary**：完成总结（字符串，可为空）
- **reasoning_notes**：推理笔记列表（每条由 `create_reasoning_note(content, task_id)` 生成）
- **bound_contexts**：绑定上下文列表（每条由 `create_bound_context(...)` 生成）

补充说明：

- `task_tools.py` 内部同时维护了 `is_active` 兼容字段，但主语义以 `status` 为准。
- 推理笔记默认仅保留最新 8 条（见 `append_task_note_impl`）。

---

## 2. `task_manager` 工具：统一入口

`task_manager` 是任务系统对模型暴露的唯一主入口，支持四类 action：

- `create`：创建新任务并设为 active
- `switch`：切换到已存在任务并设为 active
- `complete`：完成任务（写入 completion_summary）
- `append_note`：追加推理笔记（reasoning_notes）

它的 Pydantic schema 定义在 `agent_impl/graph/tools/schemas.py:TaskManagerInput`。

---

## 3. action 语义与输入要求

### 3.1 `create`

- **何时用**：用户开启全新话题/目标，与现有任务都不匹配
- **必填**：
  - `task_id`（新 ID；若重复会被拒绝）
  - `title`（可选；为空时使用 task_id）
  - `summary`（可选；建议一句话描述任务）

系统行为：

- 将当前 active 任务置为 pending
- 新建任务并设为 active
- 返回最新任务索引与当前任务 payload

### 3.2 `switch`

- **何时用**：用户回到之前聊过的话题（应当复用同一任务）
- **必填**：
  - `task_id`（必须存在）

系统行为：

- 目标任务置为 active，其它任务置为 pending

### 3.3 `complete`

- **何时用**：任务已自然结束，需要归档结论
- **必填**：
  - `summary`（这里语义是 completion_summary）
- **可选**：
  - `task_id`（为空则默认当前 active）

系统行为：

- 目标任务置为 completed，并写入 `completed_at` 与 `completion_summary`

### 3.4 `append_note`

- **何时用**：记录“报告/规划/指南里看不到、也无法从字面推断”的关键推断
- **必填**：
  - `note`
- **可选**：
  - `task_id`（为空则默认当前 active）

系统行为：

- 向目标任务追加一条结构化 note（并裁剪到最多 8 条）

---

## 4. 工具输出（返回值）结构

`task_manager` 返回的是 JSON 字符串（`json.dumps(result)`），核心字段包括：

- **success**：布尔
- **action**：`create|switch|complete|append_note`
- **message**：给开发/日志看的描述
- **task_index**：结构化任务索引（列表，每项含 task_id/title/status/summary）
- **current_task**：当前 active 任务的结构化 payload：
  - `task_id/title/summary`
  - `reasoning_notes`（列表）
  - `bound_contexts`（列表）

失败时会返回统一错误结构（来自 `tool_error_response`），通常带：

- `hint`（下一步建议）
- `task_index`（便于模型选择正确的 task_id）

---

## 5. 与 `context_loader` 的关系：任务绑定上下文（Bound Contexts）

任务系统与上下文绑定是强耦合的：

- 任务提供“容器”（active task）
- `context_loader(action="bind")` 把某条上下文绑定到 active task 的 `bound_contexts`
- 后续轮次的 prompt 组装会把 bound_contexts 注入到 dossier，保证模型持续可见

绑定上下文的类型上限由 `agent_impl/graph/context_types.py:BOUND_CONTEXT_LIMITS` 控制（例如 `action_guide` 默认最多 3 条）。

更细节见 [`context_loader.md`](context_loader.md)。

