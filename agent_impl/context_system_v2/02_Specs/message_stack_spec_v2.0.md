# 标准消息栈规范（Message Stack Spec v2.0）

> 目的：定义一次模型调用时“消息列表”的**固定结构**与**历史过滤规则**，确保：稳定、可缓存、抗注入、可调试。

---

## 1. 固定消息栈顺序（必须遵守）

每次调用模型时，消息列表按以下顺序构造：

1. **SystemMessage**：规则层（Layer 0）
2. **HumanMessage（Context Injection）**：档案层（`<dossier>` XML）
3. **AIMessage（Virtual Ack）**：固定确认句
4. **History（滑动窗口）**：真实对话历史（含工具消息），用于连贯性
5. **HumanMessage（Current Input）**：用户本轮输入

> 原则：越稳定越靠前，越易变越靠后。

---

## 2. 各段职责与边界

### 2.1 SystemMessage（Layer 0）

**只做两件事**：
- 角色与行为约束（禁区、风格、优先级）
- 输出格式约束（例如 JSON 结构、必填字段）

**不做的事**：
- 不注入任何动态上下文（避免每轮变化破坏缓存）

实现位置：`agent_impl/graph/message_builder.py` → `load_system_prompt()`

---

### 2.2 Context Injection（`<dossier>`）

**只提供“背景资料”**：用户画像（L1）、工作上下文（L2）、任务信息（Task System）、以及可选的 Main Agent 指令。

**必须满足**：
- HumanMessage 内容以 `<dossier` 开头（用于后续过滤识别）
- XML 内容必须可解析（闭合标签 + 内容做 XML escape）

实现位置：`agent_impl/graph/message_builder.py` → `build_context_xml()`

---

### 2.3 Virtual Ack

固定内容（语义隔离“已阅读档案”和“开始对话”）：

```text
收到，已阅档案。请问有什么需要帮助的？
```

实现位置：`agent_impl/graph/message_builder.py` → `VIRTUAL_ACK_MESSAGE`

---

### 2.4 History（滑动窗口）

History 负责提供**连续对话语境**，但必须过滤掉“档案注入”和“Virtual Ack”，否则会污染语境并造成重复。

#### 2.4.1 过滤规则（硬规则）

从 `state["messages"]` 中提取历史时：
- 跳过 **Context Injection**：以 `<dossier` 开头的 HumanMessage
- 跳过 **Virtual Ack**：内容等于 Virtual Ack 固定句的 AIMessage
- 保留真实对话：HumanMessage / AIMessage / ToolMessage

实现位置：`agent_impl/graph/message_builder.py` → `build_conversation_history()`

#### 2.4.2 轮次窗口（默认策略）

- “轮次”按 **用户消息**计数
- 默认最多保留 **最近 10 个用户轮次**

> 注意：Layer 3 的“长期对话历史提取”（用于单独展示或其他用途）默认是 25 轮；但**模型调用时的 History 窗口默认是 10 轮**，以控制成本并保持对当前输入的聚焦。

---

## 3. 多 Agent 场景约定

当多个 Agent 产出消息时，AIMessage 的 `name` 字段用于标注来源（例如 `status_agent` / `plan_agent`）。

实现位置：`agent_impl/graph/message_builder.py` → `AIMessage(..., name=agent_name)`

---

## 4. 最小可用示例（结构示意）

```text
[1] SystemMessage
    - 角色设定/规则/输出格式

[2] HumanMessage: <dossier agent="main_agent">...</dossier>

[3] AIMessage: "收到，已阅档案。请问有什么需要帮助的？"

[4~N] 历史对话
    - HumanMessage / AIMessage / ToolMessage（已过滤注入与 ack）

[End] HumanMessage: 用户本轮输入
```

