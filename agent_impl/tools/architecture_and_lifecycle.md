## Tools 在工作流中的位置与生命周期

这篇文档回答一个新人最常问的问题：

> “模型调用了工具之后，到底发生了什么？为什么有些工具要先 `enable`，再继续第二阶段？”

我们从“系统怎样跑”出发，按真实调用链路解释。

---

## 1. 工具的挂载点：LLM 只能调用被 bind 的 tool

在本项目里，LLM 能调用哪些工具，取决于当前节点是否对 LLM 执行了 `bind_tools([...])`。

### 1.1 主 Agent 的工具集合（main_agent）

主 Agent 在 `agent_impl/graph/nodes/main_agent.py` 中构建 `tool_list`，典型包括：

- `load_skill`（skills 渐进式披露，main_agent 可用所有 skills）
- `delegate_to_status/plan/guide`（handoff）
- `ask`（两阶段：由 `ask_mode` 决定返回 enable-only 或 full-schema）
- `consult_answer`（两阶段：由 `consult_mode` 决定 enable-only 或 complete-only）
- `emotion_support`（两阶段：由 `emotion_mode` 决定 enable-only 或 complete-only）
- `context_loader`
- `task_manager`

主 Agent 的职责是“CEO 决策中枢”：要么直接回复、要么发起 tool_call（包括委派专家）。

### 1.2 子 Agent 的工具集合（status/plan/guide）

子 Agent 的工具挂载逻辑与主 Agent 类似，但 **skills 权限更少**（通常只有 `inquiry`），并且它们更倾向于：

- 先产出分析/规划/指南
- 信息不足时进入提问（走 `ask` 或 `load_skill("inquiry")` → 提问二阶段）

---

## 2. 工具的执行点：统一在 `skill_tools_node` 执行

无论 tool_call 是主 Agent 触发还是子 Agent 触发，执行都汇聚到：

- `agent_impl/graph/workflow.py` → `skill_tools_node`

### 2.1 为什么要“统一执行”？

因为工具执行不仅是“跑函数”，更关键的是：

- **把 tool 输出转译成 `AgentState` 的状态更新**
- **设置下一跳路由（例如 handoff 到子 agent，或 ask_user 后结束等待用户）**
- **为两阶段机制生成/替换 ToolMessage 内容（注入策略）**
- **缓存最新工具输出到 `state["_last_tool_outputs"]` 供后续 prompt 注入**

换句话说：工具本身返回的是一个 JSON 字符串/结构化 payload，但真正驱动系统前进的是 `skill_tools_node` 对它的“解释与落库”。

---

## 3. 两阶段（有状态）渐进式披露：系统的关键机制

本系统里，“渐进式披露”有两条常用路径：

- **A. skills 渐进式披露**：`load_skill(skill_id)` 按需把 skill 指令注入当前轮次上下文（主要靠 ToolMessage 注入）  
- **B. 状态驱动两阶段工具**：`ask/consult_answer/emotion_support` 通过 mode 状态控制“工具 schema 在不同阶段不同”，从而约束模型行为

你这次最需要掌握的是 **B**，因为它是“先 enable 再继续”的根源。

---

## 4. `ask`（提问工具）的两阶段机制（ask_mode）

### 4.1 设计目标

提问不是“随便问一句”，而是要输出结构化的 `inquiry_card`，且要遵守提问策略。为了做到：

- 平时不把长策略塞进 prompt（省 token）
- 需要提问时再把策略注入
- 注入后强制模型产出结构化问题卡片

系统把 `ask` 设计成 **两阶段 + 有状态**。

### 4.2 Phase 1：进入提问模式（enable-only）

当 `ask_mode=False` 时，`get_ask_tool(False)` 返回的 `ask` 工具只接受：

- `ask(action="enable")`

它的“工具返回”是一个动作 JSON（简化理解）：

- `{"action":"enable_ask_mode"}`

然后 `skill_tools_node` 会做关键状态更新：

- `state.ask_mode = True`
- `state.ask_mode_tool_message_id = <本次 phase1 的 ToolMessage id>`
- `state._pending_action = "ask"`（强制下一步进入提问生成）

并且会把原本 tool 的简短输出替换为 **包含完整策略的 ToolMessage**（这就是“渐进式披露”的策略注入点）。

### 4.3 Phase 2：生成问题卡片（full-schema）并结束模式

当下一次回到 `main_agent_node`（`from_tool_call=True` 且 `_pending_action=="ask"`）时，主 Agent 会 **强制** LLM 调用 `ask`（full schema 版本）：

- 只绑定 `ask_full_tool = get_ask_tool(True)`
- 并设置 tool_choice 强制 `name="ask"`

LLM 这时必须调用：

- `ask(questions=[...], intro=..., reasoning=...)`

随后 `skill_tools_node` 会完成“提问落地”：

- `state.ask_mode = False`（复位，结束提问模式）
- `state.inquiry_card = {questions,intro,reasoning}`
- `state.pending_questions = [...]`
- `state.current_agent = <发起提问的 agent>`
- `state.agent_resume_point = continue_decision/continue_analysis/...`

同时工作流会进入“等待用户输入”的结束态（下一轮从 Router 恢复）。

### 4.4 ToolMessage 的动态简化（避免历史膨胀）

Phase 1 注入的策略 ToolMessage 非常长。为了不污染后续多轮历史：

- `agent_impl/graph/message_builder.py` 在构建 history 时会检测：
  - 若 `ask_mode=False` 且存在 `ask_mode_tool_message_id`
  - 则把那条 Phase 1 ToolMessage 内容压缩为短句（`ASK_MODE_SIMPLE`）

这就是“用完即焚”：策略在**当前轮次**服务模型，之后变成简短痕迹。

---

## 5. `consult_answer`（情感疑惑解答）的两阶段机制（consult_mode）

`consult_answer` 的两阶段与 `ask` 类似，但它的 Phase 2 不产出卡片，而是保证“模式关闭闭环”。

### 5.1 Phase 1：进入解答模式（enable-only）

当 `consult_mode=False`：

- 调用 `consult_answer(action="enable")`  
  → `skill_tools_node` 设置 `consult_mode=True`，并注入解答策略 ToolMessage

### 5.2 Phase 2：输出内容后关闭模式（complete-only）

当 `consult_mode=True`：

- 模型输出回复内容，同时必须调用 `consult_answer(action="complete")`
- `skill_tools_node` 收到 complete 后将 `consult_mode=False`

### 5.3 兜底：模型忘记 complete

主 Agent 在 `agent_impl/graph/nodes/main_agent.py` 里有兜底逻辑：

- 若 `consult_mode=True` 且模型输出了 content 但没调用 complete  
  → 系统会重试并强制生成一个 complete tool_call，再把 tool_calls 合并回响应

这保证了解答模式不会“卡死在开启态”。

---

## 6. `emotion_support`（情绪陪伴）的两阶段机制（emotion_mode）

与 `consult_answer` 同构：

- Phase 1：`emotion_support(action="enable")` → `emotion_mode=True`，注入陪伴策略 ToolMessage
- Phase 2：输出陪伴回复后 `emotion_support(action="complete")` → `emotion_mode=False`
- 同样有“忘记 complete”的兜底强制闭环

---

## 7. skills 渐进式披露：`load_skill(skill_id)` 与“有状态工具”的关系

### 7.1 `load_skill` 做什么

- `load_skill(skill_id)` 返回 **某个 skill 的完整执行指令**（来自 `agent_impl/skills/definitions/<skill_id>/SKILL.md`）
- 主 prompt 只注入元数据（name+description），模型需要细节时再调用 `load_skill`

### 7.2 `load_skill("inquiry")` 与提问二阶段

在 `skill_tools_node` 中有一条特殊映射：

- 如果看到 `load_skill(skill_id="inquiry")`
  - 会设置 `state._pending_action="inquiry"`
  - 下一步在主/子 agent 里会强制调用 `ask_user`（这是**向后兼容路径**）

注意：这条路径仍然是“两阶段”的（先 load_skill 注入指令，再强制 ask_user 产出问题），只是它的“mode 状态”不叫 `ask_mode`，而是 `_pending_action="inquiry"`。

### 7.3 为什么 `ask/consult/emotion` 不依赖 `load_skill`

本系统同时存在两种机制的原因是：

- `load_skill` 更适合“加载一段指令，让模型按指令执行”（skill 自包含）
- `ask/consult/emotion` 更适合“通过 **schema 切换** 限制模型下一步必须调用工具/必须闭环”，对稳定性更强

因此，你会看到：

- `ask/consult/emotion` 自带策略常量（注入在 Phase1 的 ToolMessage）
- `load_skill` 仍用于其它需要自包含指令的 skill（尤其是 `inquiry` 的兼容流程）

---

## 8. 状态字段速查（与工具强相关）

这些字段定义在 `agent_impl/graph/state.py`，是理解工具生命周期的关键：

- **两阶段 mode**：
  - `ask_mode`, `ask_mode_tool_message_id`
  - `consult_mode`, `consult_mode_tool_message_id`
  - `emotion_mode`, `emotion_mode_tool_message_id`
- **两阶段驱动**：
  - `_pending_action`：例如 `"ask"` / `"inquiry"`
- **handoff 驱动**：
  - `_handoff_target`, `_handoff_instruction`
  - `instruction`（Main Agent 给专家的 brief，会被注入到 dossier）
- **工具输出缓存**：
  - `_last_tool_outputs`, `_last_tool_content`

---

## 9. 提问节流：连续提问轮次控制（question_streak）

为了避免模型陷入“连续多轮只会问问题”的坏体验，系统实现了提问节流字段（定义在 `agent_impl/graph/state.py`）：

- `question_streak_agent`：当前连续提问的 agent（main_agent/status_agent/plan_agent/guide_agent）
- `question_streak_count`：该 agent 已连续提问的轮次
- `max_question_streak`：允许的最大连续提问轮次（默认 3）

它的典型更新时机在 `skill_tools_node` 的“提问落地（ask_user_payload）”阶段：

- 每次成功生成 `inquiry_card`，就会：
  - 如果仍是同一个 agent 提问：`streak_count += 1`
  - 否则重置为 1
- 同时会写回 `question_count`（旧字段兼容）

你在调试“为什么某个子 agent 不再继续问/开始输出结论”时，这组字段非常关键。

