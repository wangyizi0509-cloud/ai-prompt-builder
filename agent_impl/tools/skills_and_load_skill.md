## Skills 渐进式披露：`load_skill` 与“有状态两阶段工具”

本项目里，“渐进式披露（Progressive Disclosure）”不是一句口号，而是两套互补机制：

1. **Skills 渐进式披露（load_skill）**：只在需要时加载某个 skill 的完整指令，避免 system prompt 过长  
2. **有状态两阶段工具（ask/consult/emotion）**：通过 mode 状态切换 + schema 切换，强约束模型完成关键闭环

新人常见误解是把它们混为一谈。本文把两者区分清楚，并说明它们如何协作。

---

## 1. Skills 渐进式披露解决什么问题

传统做法是把所有技能的完整指令塞进系统提示词，这会导致：

- token 浪费（大多数 skill 本轮用不上）
- 扩展困难（新增/修改 skill 需要动很多地方）
- 上下文污染（模型被无关指令干扰）

因此我们采用两层结构：

- **Metadata Level（元数据）**：只放每个 skill 的 name + description（用于“选不选用”）
- **Instruction Level（完整指令）**：需要时调用 `load_skill(skill_id)` 才加载

---

## 2. skills 的目录结构与注册方式

目录在 `agent_impl/skills/`：

- `registry.py`：扫描 `definitions/` 自动发现 skills
- `tool.py`：提供 `load_skill` 工具工厂
- `definitions/<skill_id>/SKILL.md`：每个 skill 的定义文件（含 frontmatter）

`registry.py` 会读取每个 `SKILL.md` 的 frontmatter：

- `name`
- `description`

并生成元数据列表（`generate_metadata_prompt()`）。

---

## 3. `load_skill` 工具：按需加载完整指令

### 3.1 工具如何创建（权限在挂载层控制）

`agent_impl/skills/tool.py:create_skill_loader(allowed_skills)` 会创建一个 `StructuredTool`：

- tool 名称固定为 `load_skill`
- 但 description 会列出“允许的 skill_id 列表”

重要细节：

- **权限仅在工具挂载层控制，不在工具内部校验**  
  也就是说：谁把哪些 skill_id 绑定给模型，谁就决定模型能加载哪些指令。

预置工厂：

- `create_inquiry_only_loader()`：子 agent 常用（只允许 inquiry）
- `create_all_skills_loader()`：主 agent 常用（允许 inquiry/consult_answer/emotion_support）

### 3.2 工具输入与输出

- **输入**：`skill_id: str`
- **输出**：该 skill 的完整指令（Markdown 文本，去除 frontmatter）

这段指令会以 ToolMessage 形式进入当前轮次上下文，供模型“照着执行”。

---

## 4. 元数据是怎么进入 prompt 的

主 Agent 会在 prompt 中注入元数据（供模型选择是否 load）：

- `agent_impl/graph/nodes/main_agent.py:_get_skills_metadata_prompt()`
  - 调用 `get_skill_registry().generate_metadata_prompt()`
  - 生成“可用 skills 列表 + 调用规则说明”

因此在不 load_skill 的情况下，模型只能看到“每个 skill 的简介”，看不到执行细则。

---

## 5. ToolMessage 的“用完即焚”：load_skill 的输出会被压缩

`agent_impl/graph/message_builder.py` 在构建对话历史时有一条动态简化规则：

- 对 `load_skill` 的 ToolMessage：除当前轮次外，会压缩成短句（例如 `[已加载 inquiry skill]`）

目的：

- 避免每次加载的大段指令被永久带进历史，导致 token 膨胀

这意味着：**skill 指令只在“当下执行窗口”里完整可见**。

---

## 6. “有状态两阶段工具”与 load_skill 的关系

你在代码里会同时看到：

- `load_skill("inquiry")`（skills 渐进式披露）
- `ask(action="enable")` → `ask(questions=[...])`（有状态两阶段）

它们的区别与协作如下。

### 6.1 `ask/consult/emotion` 是“状态驱动的渐进式披露”

这三类工具不依赖 `load_skill` 来注入策略，而是：

- Phase 1（enable-only）：进入 mode，并把策略全文写入 ToolMessage（渐进式披露）
- Phase 2（full/complete-only）：强制模型执行关键动作并结束 mode

其详细机制见 [`architecture_and_lifecycle.md`](architecture_and_lifecycle.md)。

### 6.2 `load_skill("inquiry")` 仍然存在（兼容路径）

在 `agent_impl/graph/workflow.py:skill_tools_node` 中：

- 如果识别到 `load_skill(skill_id="inquiry")`
  - 会设置 `_pending_action="inquiry"`
  - 下一步强制模型调用 `ask_user`（旧接口）来产出 `inquiry_card`

因此它仍然是“两阶段”的：

- 第一阶段：load_skill 注入指令
- 第二阶段：强制 ask_user 生成结构化问题

只是这条路径不使用 `ask_mode`，而使用 `_pending_action="inquiry"` 作为驱动信号。

### 6.3 实战建议：什么时候用哪条

从“系统稳定性与一致性”出发：

- **优先使用 `ask` 两阶段**（ask_mode 机制更直接、更可控，且策略由系统注入）
- `load_skill("inquiry")` 主要用于：
  - 某些 prompt/策略仍沿用“先加载 inquiry skill 再 ask_user”的流程
  - 向后兼容测试与旧调用链

---

## 7. 新增/维护一个 skill 的工作流（给开发者）

新增 skill 的最小步骤是：

- 在 `agent_impl/skills/definitions/<new_skill_id>/SKILL.md` 新建文件
- 写 frontmatter：`name`、`description`
- 正文写完整执行指令（确保自包含）

是否能被模型调用，取决于：

- 你是否在某个 agent 的工具挂载列表里把它加入 `create_skill_loader([...])` 的允许列表

