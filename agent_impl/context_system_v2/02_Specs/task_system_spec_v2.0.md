# 任务系统规范（Task System Spec v2.0）

> 目的：用“任务”作为额外上下文的生命周期边界，支持按需加载、绑定与卸载，避免无限注入导致 Token 爆炸。

代码对应：
- 任务工具：`agent_impl/graph/tools/task_tools.py`
- 按需上下文：`agent_impl/graph/tools/context_loader.py`
- 注入：`agent_impl/graph/context_builder.py`（Task Index / Active Task / Bound Contexts 格式化）

---

## 1. 核心概念

### 1.1 什么是任务？

**一个任务 = 一个用户意图的完整解决过程**。  
任务是“额外上下文”的生命周期边界：
- 任务进行中：绑定的上下文持续注入
- 任务切换：绑定上下文不再注入（但后台保留）
- 任务回切：绑定上下文恢复注入

### 1.2 任务归属

任务列表按 Agent 维度隔离，互不影响：
- `main_agent` / `status_agent` / `plan_agent` / `guide_agent`

存储位置：`layer3_memory.task_registry[agent_name]`

---

## 2. 任务列表（Task Index）

### 2.1 展示结构（对齐 `format_task_index`）

输出为可读 Markdown：

```markdown
## 任务列表

### 当前任务
- **标题** [active]
  摘要：...

### 其他任务
| title | status | summary |
|-------|--------|---------|
| ...   | ...    | ...     |

### 已完成任务
| title | completion_summary |
|-------|---------------------|
| ...   | ...                 |
```

### 2.2 数量限制（默认）

为控制 Token：
- 非 completed（不含当前 active）：最多 5 条
- completed：最多 3 条

---

## 3. 当前任务（Active Task Payload）

在 `<dossier>` 中，当前任务会以 **JSON 字符串**注入（便于模型稳定解析）。

结构（对齐 `format_active_task_payload`）：

```json
{
  "task_id": "",
  "title": "",
  "summary": "",
  "reasoning_notes": [],
  "bound_contexts": []
}
```

---

## 4. Bound Contexts（任务绑定上下文）

### 4.1 为什么需要绑定上下文？

有些信息很长、很具体、只在某个任务内有用（例如“某条指南的完整正文”“某段聊天记录片段”）。  
这类信息不应该常驻注入，而应该 **按需加载** 并绑定到当前任务。

### 4.2 绑定与解绑

由工具 `context_loader` 完成，典型能力包括：
- 从 Layer 2/Layer 3/外部片段中**定位**某条资源（例如某条指南）
- 把“资源详情”封装为 Markdown，并写入当前任务的 `bound_contexts`
- 达到上限时按策略淘汰最早绑定的上下文

### 4.3 type 与默认上限

系统为不同类型的绑定上下文设置了上限（避免无限堆积）。典型类型：
- `action_guide`
- `status_report`
- `action_plan`
- `crush_chat`
- `history_snippet`
- `dynamic_intel`
- `custom`
- 以及 `default`

具体上限以代码常量 `BOUND_CONTEXT_LIMITS` 为准。

### 4.4 Bound Contexts 注入格式（对齐 Context Builder）

注入为 Markdown，按 type 分组：

```markdown
## 任务绑定上下文

### 行动指南 (n)
- [MM-DD HH:mm] 标题

### Crush 聊天记录 (n)
- [MM-DD HH:mm] 标题
```

> 注意：这里默认只注入“索引与标题”，正文由工具按需加载并写入绑定内容（或在绑定内容中包含全文）。

---

## 5. 任务生命周期操作（工具层）

任务管理由 `task_manager` 工具提供，支持：
- `create`：创建新任务并设为 active
- `switch`：切换到已存在的任务
- `complete`：完成当前任务
- `append_note`：追加推理笔记（Reasoning Notes）

这些操作会更新 `layer3_memory.task_registry`，并影响后续 `<dossier>` 注入的 Task Index / Active Task / Bound Contexts。

