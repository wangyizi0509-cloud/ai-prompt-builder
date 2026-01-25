## 专家委派（handoff）工具：`delegate_to_*`

主 Agent 的核心能力之一是：**把复杂问题交给更专业的子 Agent（Status/Plan/Guide）完成**，而不是自己“兼职专家”。

在系统实现上，委派通过 tool_call 完成，工具名有三个：

- `delegate_to_status`
- `delegate_to_plan`
- `delegate_to_guide`

工具定义见 `agent_impl/graph/tools/delegate_tools.py`。

---

## 1. 什么时候用哪个委派工具

你可以把它理解成三种“专家脑区”：

- **Status Agent（现状分析）**：诊断关系阶段、核心矛盾、局势机会与风险  
- **Plan Agent（行动规划）**：制定宏观推进蓝图、阶段目标、里程碑  
- **Guide Agent（行动指南）**：把规划落成 SOP：具体步骤、话术要点、执行节奏  

主 Agent prompt（`agent_impl/prompts/main_agent.md`）里也强调了这条分工边界：

- 不确定局势 → 找 Status
- 不确定方向 → 找 Plan
- 不确定怎么做 → 找 Guide

---

## 2. 工具调用协议

三个工具的输入与输出结构一致，区别只是 target 不同。

### 2.1 输入（参数）

- `instruction: str`  
  给专家的 **宏观 brief**：告诉专家“背景是什么、这轮要重点分析什么、希望产出什么”。

建议写法：

- 1-3 句即可，不需要复述全部上下文（专家会在 dossier 里看到完整档案）
- 写“关注点/侧重点”而不是“具体结论”

### 2.2 输出（工具返回）

工具返回 JSON 字符串（示意）：

```json
{
  "action": "handoff",
  "target": "status_agent",
  "instruction": "..."
}
```

`target` 取值为：

- `status_agent` / `plan_agent` / `guide_agent`

---

## 3. 工作流如何消费 handoff

执行点在 `agent_impl/graph/workflow.py:skill_tools_node`：

- 当检测到 tool_call 名称属于 `delegate_to_status/plan/guide` 时：
  - 写入 `state._handoff_target`
  - 写入 `state._handoff_instruction`
  - 同步写入 `state.instruction`（用于 dossier 注入）

随后路由逻辑会根据 `_handoff_target` 跳转到对应子 Agent 节点执行。

---

## 4. `instruction` 如何进入子 Agent 的上下文

子 Agent 在生成消息时，会由 `message_builder`/context 注入层把 `state.instruction` 放进 dossier：

- 这能确保专家明确“这轮要做什么”，避免它在海量上下文里跑偏。

新人理解上只要记住：

- **handoff 工具决定“切到谁”**
- **instruction 决定“让他重点干啥”**

---

## 5. 常见误用与红线

### 5.1 不要帮专家提前套话

如果你委派 Status/Plan/Guide 的目的是为了让专家分析，而你又觉得信息不足：

- 正确做法：**直接委派**，让专家自己决定是否需要进入提问工具（`ask` 两阶段）
- 错误做法：主 Agent 先问一堆细节（这会让主 Agent prompt 变成“秘书”，并且浪费轮次）

### 5.2 instruction 不要写成“模板话”

坏例子：

- “请分析一下。”（没有侧重点）

好例子：

- “用户刚发了新的聊天截图，重点判断对方是在回避推进还是只是忙；如果仍不明朗，先走提问模式收集关键信息。”

---

## 6. 你可能会关心的问题

### 6.1 handoff 后是否一定要回主 Agent？

通常会回到主 Agent 做“收口与下一步决策”，但子 Agent 在信息不足时也可能触发提问并暂停等待用户输入。

### 6.2 委派是否可以用于“更新/修正”？

可以。`delegate_to_*` 不仅用于首次生成报告/规划/指南，也可以用于 **更新/修正已有结论**（主 prompt 也强调了这一点）。

