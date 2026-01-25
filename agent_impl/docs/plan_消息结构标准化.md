# 消息结构标准化：结构化状态注入模式

## 核心架构

采用业界最佳实践的 **结构化状态注入模式 (Structured State Injection Pattern)**，适配 DeepSeek V3 / Claude 3.5 / GPT-4o。

### 消息栈结构 (The Message Stack)

```
+-------------------------------------------------------------+
| [1] SystemMessage                                           |
|     角色人设 + 输出格式 (JSON) + 核心规则                     |
|     格式：Markdown | 全场唯一，固定不变                       |
+-------------------------------------------------------------+
| [2] HumanMessage (Context Injection)                        |
|     用户档案 + 现状报告 + 行动规划 + 行动指南                  |
|     格式：XML 包裹 | 支持 source 属性标注来源                 |
+-------------------------------------------------------------+
| [3] AIMessage (Virtual Ack)                                 |
|     "收到，已阅档案。请问有什么需要帮助的？"                   |
|     作用：语义隔离"阅读资料"和"开始对话"                      |
+-------------------------------------------------------------+
| [4~N] HumanMessage / AIMessage / ToolMessage                |
|     真实对话历史（滑动窗口，最近 N 轮）                        |
|     格式：纯文本 / 标准 tool_calls / AIMessage.name 标注来源  |
+-------------------------------------------------------------+
| [End] HumanMessage                                          |
|     用户当前输入                                             |
+-------------------------------------------------------------+
```

### 格式规范

| 位置 | 格式 | 理由 |
|------|------|------|
| System | Markdown | 指令层级清晰，便于维护 |
| Context | XML | DeepSeek/Claude 解析力强；闭合标签防注入；支持属性标注 |
| History | 纯文本 | 还原真实聊天语境 |

### 信任层级放置原则

- **规则说明**（"遇到冲突怎么处理"）-> 放在 **System Prompt**
- **来源标注**（如 `source="user"` / `source="ai_analysis"`）-> 放在 **Context XML** 的属性里

具体信任层级规则沿用现有方案，本次改造不重新定义。

---

## 改造范围

### 1. 新增：消息构建器

**文件**：`agent_impl/graph/message_builder.py`（新建）

```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

def build_messages_for_model(
    state: AgentState,
    agent_name: str,
    current_input: str,
) -> list:
    """
    构建标准消息列表
    
    Returns:
        [SystemMessage, HumanMessage(context), AIMessage(ack), ...history, HumanMessage(current)]
    """
    messages = []
    
    # [1] System: 人设 + 规则（无数据）
    system_prompt = load_system_prompt(agent_name)
    messages.append(SystemMessage(content=system_prompt))
    
    # [2] Context Injection: XML 包裹的档案
    context_xml = build_context_xml(state, agent_name)
    messages.append(HumanMessage(content=context_xml))
    
    # [3] Virtual Ack: AI 确认收到
    messages.append(AIMessage(content="收到，已阅档案。请问有什么需要帮助的？"))
    
    # [4~N] History: 真实对话（滑动窗口）
    history = build_conversation_history(state, max_turns=10)
    messages.extend(history)
    
    # [End] Current Input
    messages.append(HumanMessage(content=current_input))
    
    return messages


def build_context_xml(state: AgentState, agent_name: str) -> str:
    """
    构建 XML 格式的上下文档案
    来源标注（source 属性）沿用现有信任层级规则
    """
    context_dict = build_context_dict(state, target_agent=agent_name)
    
    xml = f"""<dossier agent="{agent_name}">
  <user_context source="layer1">
{context_dict.get("user_context", "暂无")}
  </user_context>
  
  <status_report source="layer2">
{context_dict.get("status_report", "暂无")}
  </status_report>
  
  <action_plan source="layer2">
{context_dict.get("action_plan", "暂无")}
  </action_plan>
  
  <action_guides source="layer2">
{context_dict.get("action_guides", "暂无")}
  </action_guides>
  
  <task_context>
    <task_index>{context_dict.get("task_index", "暂无")}</task_index>
    <active_task>{context_dict.get("active_task_payload", "{}")}</active_task>
  </task_context>
</dossier>

请阅读以上档案，准备开始咨询。"""
    
    return xml


def build_conversation_history(state: AgentState, max_turns: int = 10) -> list:
    """
    构建标准消息历史（纯文本，保留 tool_calls）
    """
    messages = state.get("messages", [])
    # 取最近 N 轮，跳过 context injection 和 ack
    # ...实现细节
```

### 2. 拆分 Prompt 模板

**改造文件**：

- `agent_impl/prompts/main_agent.md`
- `agent_impl/prompts/status_agent.md`
- `agent_impl/prompts/plan_agent.md`
- `agent_impl/prompts/guide_agent.md`

**改动**：

- 移除所有 `{user_context}`、`{status_report}`、`{conversation_history}` 等动态变量
- 只保留：角色定义 + 决策模型 + 输出格式 + 规则
- 信任层级规则沿用现有方案（已在 prompt 中定义）

**示例（main_agent.md 改造后结构）**：

```markdown
# 主 Agent System Prompt

你是**小话**，用户的**专属恋爱军师**。

## 角色定义
...（保留现有内容）

## 决策模型：OODA 循环
...（保留现有内容，但移除动态上下文占位符）

## 输出格式
（JSON 格式定义）

## 核心规则
（保留现有信任层级规则等）

## 可用 Skills
{skills_prompt}
```

### 3. 改造 Context Builder

**文件**：`agent_impl/graph/context_builder.py`

**改动**：

- 保留 `build_context_dict` 供 XML 构建使用
- 移除 `_format_interleaved_history` 的 Markdown 拼接逻辑
- 新增 `extract_layer1_for_xml` / `extract_layer2_for_xml` 等函数

### 4. 改造 Agent 节点

**文件**：4 个 agent 节点

**改动**：

```python
# 改造前
prompt = prompt_template.format(**format_kwargs)
response = base_llm.invoke(prompt)

# 改造后
from graph.message_builder import build_messages_for_model

messages = build_messages_for_model(
    state=state,
    agent_name="main_agent",
    current_input=state.get("user_message", ""),
)
response = base_llm.invoke(messages)
```

### 5. 改造工具调用链路

**文件**：`agent_impl/graph/workflow.py`

**改动**：

- 工具调用后，标准写入 `AIMessage(tool_calls=[...])` + `ToolMessage(tool_call_id=...)`
- 移除"工具输出拼到 prompt 文本"的逻辑
- Agent 二阶段直接从 messages 读取 ToolMessage

### 6. 清理旧代码

**文件**：`agent_impl/utils/message_utils.py`

**改动**：

- 移除 L34-L48 的工具调用转文本逻辑
- 简化 `get_msg_role_and_content`，只做 role 标准化

---

## 改造后的数据流

```
                    build_messages_for_model
                              |
        +---------------------+---------------------+
        v                     v                     v
+---------------+   +-----------------+   +-----------------+
| load_system   |   | build_context   |   | state.messages  |
| _prompt()     |   | _xml()          |   | (标准 msg list) |
+-------+-------+   +--------+--------+   +--------+--------+
        |                    |                     |
        v                    v                     v
   SystemMessage       HumanMessage           HumanMessage
   (Markdown)          (XML档案)              AIMessage
                            |                 ToolMessage
                            v                 ...
                       AIMessage              HumanMessage
                       (Virtual Ack)          (当前输入)
```

---

## 预期收益

1. **KV Cache 命中**：System + Context 头部固定，DeepSeek V3 长对话 Token 成本大幅下降
2. **抗注入**：XML 闭合标签划清"背景"和"指令"边界
3. **自我修正**：信任层级允许用户随时纠正 AI 错误判断
4. **调试友好**：消息栈结构清晰，问题定位更简单

---

## AI 分工方案

本次改造拆分为 5 个可解耦的开发任务，分配给不同的零上下文 AI 执行，最后由 AI-5 做端到端整合验收。

### 依赖关系图

```
AI-1 (消息构建器) ──┬──> AI-3 (Agent节点改造) ──┐
                   │                           │
AI-2 (Prompt改造) ─┴──────────────────────────>├──> AI-5 (整合验收)
                                               │
AI-4 (工具调用链路) ───────────────────────────┘
```

### AI-1: 消息构建器模块

| 属性 | 说明 |
|------|------|
| **任务** | 新建 `agent_impl/graph/message_builder.py` |
| **独立性** | 完全独立，可最先开始 |
| **必读文件** | 本 plan 文档、`context_builder.py`、`state.py` |
| **输出** | `message_builder.py` 文件 |
| **验收标准** | 导入不报错；`build_messages_for_model` 返回标准 message list；AIMessage 保留 `name` 字段 |

### AI-2: Prompt 模板改造

| 属性 | 说明 |
|------|------|
| **任务** | 改造 4 个 prompt 文件，移除动态变量，只保留 System Prompt 内容 |
| **独立性** | 完全独立，可与 AI-1 并行 |
| **必读文件** | 本 plan 文档、4 个 `prompts/*.md` 文件 |
| **输出** | 改造后的 4 个 prompt 文件 |
| **验收标准** | 无 `{user_context}`、`{status_report}`、`{conversation_history}` 等变量；保留 `{skills_prompt}` |

### AI-3: Agent 节点改造

| 属性 | 说明 |
|------|------|
| **任务** | 改造 4 个 Agent 节点，使用 `build_messages_for_model` |
| **依赖** | AI-1 完成 |
| **必读文件** | 本 plan 文档、`message_builder.py`、4 个 `nodes/*.py` 文件 |
| **输出** | 改造后的 4 个 agent 节点文件 |
| **验收标准** | 调用 `base_llm.invoke(messages)` 而非 `invoke(prompt字符串)`；写入 assistant 消息时设置 `name` 为对应 agent |

### AI-4: 工具调用链路改造

| 属性 | 说明 |
|------|------|
| **任务** | 改造 `workflow.py` 和 `message_utils.py`，走标准 tool message 协议 |
| **独立性** | 可与 AI-1/2 并行，但建议在 AI-3 之后执行 |
| **必读文件** | 本 plan 文档、`workflow.py`、`message_utils.py` |
| **输出** | 改造后的 2 个文件 |
| **验收标准** | 工具调用写入 `AIMessage(tool_calls)` + `ToolMessage`；移除文本拼接逻辑；保留 `_last_tool_content/_last_tool_outputs` 兼容字段 |

补充说明：
- 不修改 `context_builder.py`（模型输入已改为 message_builder，历史不再依赖 `_format_interleaved_history`）
- 不删除 `workflow.py` 中的缓存字段，等 AI-3 完成后由 AI-5 统一清理

### AI-5: 端到端整合验收

| 属性 | 说明 |
|------|------|
| **任务** | 运行完整流程，验收所有改动，修复集成问题 |
| **依赖** | 所有上述任务完成 |
| **必读文件** | 本 plan 文档、所有改动后的文件、测试用例 |
| **输出** | 测试报告、集成问题修复 |
| **验收标准** | 完整对话流程正常运行；工具调用正常；4 个 Agent 都能正确响应 |

---

## 实施顺序

1. **Phase 1**：AI-1 + AI-2 并行执行
2. **Phase 2**：AI-3 执行（依赖 AI-1 完成）
3. **Phase 3**：AI-4 执行
4. **Phase 4**：AI-5 整合验收
