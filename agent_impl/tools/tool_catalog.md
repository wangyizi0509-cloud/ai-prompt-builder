## Tool Catalog（工具总目录）

这份文档是“查表入口”：当你想知道某个工具**做什么、怎么调用、会改哪些状态、会返回什么**，从这里开始。

工具实现主要在：

- `agent_impl/graph/tools/`（workflow/graph 工具）
- `agent_impl/skills/`（skills 渐进式披露工具：`load_skill`）

---

## 0. 统一约定：工具输出与系统如何消费

### 0.1 工具输出形态

多数工具的 Python 实现返回的是 **JSON 字符串**（`str`），例如：

- `{"action":"handoff","target":"status_agent","instruction":"..."}`
- `{"action":"ask_user","inquiry_card":{...}}`

重要：**工具返回的 JSON 不是最终用户回复**，它是给工作流消费的“动作协议”。

### 0.2 工作流如何消费工具输出

工具执行统一在 `agent_impl/graph/workflow.py` 的 `skill_tools_node` 完成，它会：

- 执行 tool 函数
- 解析 tool_call（name/args），并据此更新 `AgentState`
- 在必要时进入两阶段（`ask_mode/consult_mode/emotion_mode` 或 `_pending_action`）
- 缓存最新工具输出到 `state["_last_tool_outputs"]`，供下一阶段 prompt 注入

### 0.3 统一响应封装（success/message/data）

部分工具（尤其是 `task_manager`、`context_loader`）会使用统一的响应封装函数：

- 位置：`agent_impl/graph/tools/schemas.py`
  - `tool_response(success: bool, message: str, data?: Any) -> str`
  - `tool_error_response(message: str, data?: Any) -> str`

封装后的 JSON 形态通常是：

- 成功：
  - `{"success": true, "message": "...", "data": {...}}`
- 失败：
  - `{"success": false, "message": "...", "data": {...}}`

这类结构的重点是：**失败也可携带 data（例如 hint、available_ids、task_index）**，用于指导模型下一步自我修正。

---

## 1. 工具一览（按类别）

### 1.1 任务系统工具

- **`task_manager`**：任务创建/切换/完成/追加 reasoning note  
  详见 [`task_system_tooling.md`](task_system_tooling.md)

### 1.2 上下文加载与绑定工具

- **`context_loader`**：`load`（一次性查看）/ `bind`（跨轮次注入）/ `unbind` / `refresh`  
  详见 [`context_loader.md`](context_loader.md)

### 1.3 专家委派（handoff）工具

- **`delegate_to_status`** / **`delegate_to_plan`** / **`delegate_to_guide`**：触发工作流切换到对应子 agent  
  详见 [`handoff_delegate_tools.md`](handoff_delegate_tools.md)

### 1.4 两阶段（有状态）渐进式披露工具

- **`ask`**：提问（Phase1 enable → Phase2 生成 `inquiry_card`）  
- **`consult_answer`**：情感疑惑解答（enable → complete 闭环）  
- **`emotion_support`**：情绪陪伴（enable → complete 闭环）  
  两阶段机制详见 [`architecture_and_lifecycle.md`](architecture_and_lifecycle.md)

### 1.5 skills 渐进式披露工具

- **`load_skill`**：按需加载 skill 指令（用于 progressive disclosure）  
  详见 [`skills_and_load_skill.md`](skills_and_load_skill.md)

### 1.6 兼容/边缘工具

- **`ask_user`**：旧版“直接产出 inquiry_card”的工具接口。当前代码里仍保留，用于兼容 `_pending_action="inquiry"` 的路径。
- **`graph/tools/ask_user_tool.py`**：另一个旧版实现（`@tool` 装饰器风格）。当前主链路更倾向使用 `graph/tools/ask_tool.py` 里的 `ask_user` 别名/兼容接口。
- **`DrawerTools` / create_drawer_tools_for_langchain**：抽屉式历史/聊天拉取（偏兼容旧结构）。注意：它目前**不在** `skill_tools_node` 的 ToolNode 列表中，因此**不会被模型自动调用**。详见 [`drawer_tools.md`](drawer_tools.md)。

---

## 2. 逐个工具：如何调用（输入）与会返回什么（输出）

以下内容以“调用协议”方式描述（面向新人理解 tool_call），并指出关键 state 影响。

---

## 2.1 `load_skill`（skills 指令加载）

- **定义位置**：`agent_impl/skills/tool.py`（通过 `create_skill_loader` 生成工具）
- **何时用**：模型需要某个 skill 的完整执行指令（而不是只靠元数据）时
- **输入字段**：
  - `skill_id: str`（例如 `"inquiry"`, `"consult_answer"`, `"emotion_support"`）
- **输出**：Markdown 指令文本（ToolMessage），由模型读完后执行
- **关键状态影响**：
  - `skill_tools_node` 若识别到 `load_skill("inquiry")`，会设置 `state._pending_action="inquiry"`（下一步强制走提问工具）

---

## 2.2 `ask`（提问，两阶段：ask_mode）

- **定义位置**：`agent_impl/graph/tools/ask_tool.py`
- **何时用**：需要向用户收集关键信息，且希望输出结构化问题卡片

补充：当前工具链路里同时保留了 `ask_user`（旧接口）用于兼容，但新人应优先理解与使用 `ask` 的两阶段模式（enable → questions），因为它承载了 mode 状态与策略注入。

### Phase 1（ask_mode=False）：进入提问模式

- **调用**：`ask(action="enable")`
- **输出（工具返回）**：`{"action":"enable_ask_mode"}`
- **系统状态变化（由 `skill_tools_node` 完成）**：
  - `ask_mode=True`
  - `ask_mode_tool_message_id=<id>`（用于后续动态简化）
  - `_pending_action="ask"`（下一步强制生成问题）
  - ToolMessage 内容会被替换为“提问策略全文”（渐进式披露）

### Phase 2（ask_mode=True）：生成问题卡片并结束模式

- **调用**：`ask(questions=[...], intro=..., reasoning=...)`
- **输出（工具返回）**：
  - `{"action":"ask_user","inquiry_card":{"questions":[...],"intro":"...","reasoning":"..."}}`
- **系统状态变化**：
  - `ask_mode=False`（结束模式）
  - `inquiry_card` / `pending_questions` / `agent_resume_point` 等字段被写入，用于暂停等待用户输入并在下轮恢复

---

## 2.3 `consult_answer`（解答，两阶段：consult_mode）

- **定义位置**：`agent_impl/graph/tools/consult_answer_tool.py`

### Phase 1（consult_mode=False）：进入解答模式

- **调用**：`consult_answer(action="enable")`
- **输出**：`{"action":"enable_consult_mode"}`
- **系统状态变化**：
  - `consult_mode=True`
  - `consult_mode_tool_message_id=<id>`（策略 ToolMessage 的标识）
  - ToolMessage 被替换为“解答策略全文”（渐进式披露）

### Phase 2（consult_mode=True）：关闭解答模式

- **调用**：`consult_answer(action="complete")`
- **输出**：`{"action":"complete_consult_mode"}`
- **系统状态变化**：
  - `consult_mode=False`
  - ToolMessage 会被替换为“解答模式已关闭。”

---

## 2.4 `emotion_support`（陪伴，两阶段：emotion_mode）

- **定义位置**：`agent_impl/graph/tools/emotion_support_tool.py`
- **机制**：与 `consult_answer` 同构

---

## 2.5 `delegate_to_status / delegate_to_plan / delegate_to_guide`（handoff）

- **定义位置**：`agent_impl/graph/tools/delegate_tools.py`
- **何时用**：主 Agent 需要调度专家（Status/Plan/Guide）完成更专业的诊断/规划/执行指南
- **输入字段**：
  - `instruction: str`（给专家的宏观 brief）
- **输出**：
  - `{"action":"handoff","target":"status_agent|plan_agent|guide_agent","instruction":"..."}`
- **系统状态变化**：
  - `skill_tools_node` 会写入 `_handoff_target` 与 `instruction`，并将工作流路由到对应 agent

---

## 2.6 `context_loader`（上下文加载/绑定）

- **定义位置**：`agent_impl/graph/tools/context_loader.py`
- **何时用**：
  - `load`：只想临时查看某条上下文内容（一次性）
  - `bind`：希望某段上下文在后续多轮持续注入（跟随当前 active task）
- **输入字段**（核心）：
  - `action: "load" | "bind" | "unbind" | "refresh"`
  - `context_type: "action_guide" | "status_report" | "action_plan" | "crush_chat" | "history_snippet" | "custom"`
  - `context_id: str`
  - `expire_at?: str`
- **输出**：
  - 成功时包含 `content_md` 与 `context` meta（id/title/type/ref_id），失败时是统一错误 JSON
- **系统状态变化**：
  - `bind/unbind/refresh` 会更新 `layer3_memory.task_registry[*].bound_contexts`

---

## 2.7 `task_manager`（任务系统）

- **定义位置**：`agent_impl/graph/tools/task_tools.py`
- **输入字段**：
  - `action: "create" | "switch" | "complete" | "append_note"`
  - `task_id/title/summary/note`（随 action 不同而可选/必填）
- **输出**：
  - `task_index`（结构化索引）
  - `current_task`（活跃任务的结构化 payload，含 reasoning_notes 与 bound_contexts）
- **系统状态变化**：
  - 写入 `layer3_memory.task_registry[agent_name]`

