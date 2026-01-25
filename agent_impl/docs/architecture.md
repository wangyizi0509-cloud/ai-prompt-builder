# Crushe AI Agent 架构设计文档

> **版本**：v2.1  
> **更新日期**：2024-12  
> **技术栈**：LangGraph (0.2+)
> 
> **v2.1 更新 (LangGraph Best Practices)**：
> - **Human-in-the-Loop 升级**：使用官方 `interrupt()` 函数替代手动的 `wait_user_input` 节点，状态管理更原生
> - **持久化 (Persistence)**：引入 Checkpointer (MemorySaver/PostgresSaver)，支持跨会话记忆
> - **循环控制**：工作流层面统一的 `_iteration_count` 循环限制，防止无限递归
> - **ToolNode 优化**：简化工具节点实现，保持 pure function 风格
> - **State 优化**：使用 `add_messages` reducer，自动处理消息合并
> 
> **v2.0 更新**：
> - **Context Engineering**：引入 3x3 静态情报矩阵，分层上下文架构 (Layer 0-4)
> - **Skill Tool-Use**：LLM 原生工具调用加载 Skill 指令

---

## 一、架构总览

Crushe 采用「主 Agent + 子 Agent + 通用 Skills」的 **Orchestrator-Worker** 架构，以主 Agent 作为决策中枢，协调多个专业子 Agent 完成用户的情感咨询全流程。所有 Agent 共享一套通用 Skills（如提问、信息收集等），实现能力复用。

### 1.1 系统架构图

```mermaid
graph TD
    User([用户输入]) --> Router[Router 节点]
    
    subgraph "Core Agents"
        Main[Main Agent<br/>决策中枢]
        Status[Status Agent<br/>现状分析]
        Plan[Plan Agent<br/>行动规划]
        Guide[Guide Agent<br/>行动指南]
    end
    
    subgraph "Capabilities"
        Tools[Skill Tools<br/>(ToolNode)]
    end

    Router -->|新会话| Main
    Router -->|恢复执行| Status
    Router -->|恢复执行| Plan
    Router -->|恢复执行| Guide
    Router -->|恢复执行| Main

    Main -->|call_status| Status
    Main -->|call_plan| Plan
    Main -->|call_guide| Guide
    Main -->|ask_user| End([END])
    Main -->|tool_call| Tools
    Main -->|end_turn| End

    Status -->|完成| Main
    Status -->|tool_call| Tools
    Status -->|ask_user| End

    Plan -->|完成| Main
    Plan -->|tool_call| Tools
    Plan -->|ask_user| End

    Guide -->|完成| Main
    Guide -->|tool_call| Tools
    Guide -->|ask_user| End

    Tools -->|返回结果| Main
    Tools -->|返回结果| Status
    Tools -->|返回结果| Plan
    Tools -->|返回结果| Guide
```

### 1.2 核心机制：Router 状态恢复 (State-Based Recovery)

v2.1 采用 **Router 状态恢复** 模式来实现 Human-in-the-Loop，而非 LangGraph 原生的 Interrupt。这种方式对无状态的 HTTP 服务更友好，支持长时间的会话中断。

1.  **暂停**：当 Agent 需要提问时，将状态设置为 `next_action="ask_user"`，并写入 `current_agent` 和 `agent_resume_point` 标记。然后工作流流转至 `END`，结束本次运行。
2.  **持久化**：所有状态被 Checkpointer 保存到持久化存储（如 Redis/Postgres）。
3.  **恢复**：用户输入新消息后，Router 节点检测到 state 中存在 `current_agent`，将流量直接导回对应的 Agent，从 `agent_resume_point` 逻辑继续执行。

这种机制确保了系统的容灾性和跨会话能力。

---

## 二、各层职责定义

### 2.1 主 Agent（决策中枢）

主 Agent 是整个系统的核心，负责：
1.  **决策调度**：判断下一步调用哪个子 Agent。
2.  **可选回复**：根据上下文判断是否需要说话（过渡语、总结语）。
3.  **咨询回答**：融合咨询能力，直接回答用户追问。
4.  **使用 Skills**：在需要时直接调用通用 Skill（如提问）。
5.  **循环控制**：检测子 Agent 反复调用，强制介入。

#### 决策逻辑伪代码

```python
def main_agent_node(state):
    # 1. 绑定工具
    llm = get_llm().bind_tools([create_all_skills_loader()])
    
    # 2. 调用 LLM
    response = llm.invoke(prompt)
    
    # 3. 处理工具调用
    if response.tool_calls:
        return {"messages": [response], "current_agent": "main_agent"}
        
    # 4. 解析结果
    result = parse_response(response.content)
    
    # 5. 处理提问 (Interrupt)
    if result["next_action"] == "ask_user":
        # 暂停执行，等待用户输入
        user_answer = interrupt({
            "type": "inquiry",
            "inquiry_card": result["inquiry_card"]
        })
        # 恢复后继续...
    
    return result
```

### 2.2 子 Agent 层

子 Agent 负责特定领域的任务执行：
-   **现状分析 Agent**：诊断 ACR 阶段、L/T 线定位
-   **行动规划 Agent**：制定宏观战略
-   **行动指南 Agent**：生成具体 SOP

#### 子 Agent 通用行为
1.  **独立交互**：可以直接向用户提问（通过设置 next_action="ask_user"）。
2.  **工具使用**：自主决定加载哪些 Skill。
3.  **完成信号**：任务完成后返回主 Agent，附带 `completion_status`。

### 2.3 Skills 层 (Tool-Use)

Skills 是通用能力模块，v1.4 起采用 **LLM 原生 Tool-Use** 机制。

**核心流程**：
1.  **Progressive Disclosure**：Prompt 中只包含 Skill 元数据。
2.  **Tool Call**：LLM 自主决定调用 `load_skill(skill_id)`。
3.  **Tool Exec**：ToolNode 返回完整指令。
4.  **Generation**：LLM 根据完整指令生成最终内容（如 inquiry_card）。

---

## 三、状态管理 (AgentState)

`AgentState` 是工作流中传递的核心数据结构。

```python
class AgentState(TypedDict):
    # === 基础消息 ===
    user_message: str
    # v2.1: 使用 add_messages reducer 自动合并消息
    messages: Annotated[list, add_messages]
    
    # === Layer 1: 静态情报 (3x3 Matrix) ===
    user_context: UserContext
    
    # === Layer 2: 工作上下文 ===
    status_report: Optional[StatusReport]
    action_plan: Optional[ActionPlan]
    action_guides: list[ActionGuideItem]
    
    # === 流程控制 ===
    intent_type: str
    next_action: str
    
    # === 恢复执行状态 (用于 Router) ===
    current_agent: Optional[str]     # 暂停在哪个 Agent
    agent_resume_point: Optional[str] # 恢复标识
    question_count: int              # 提问计数
    
    # === 循环控制 (v2.1) ===
    _iteration_count: int            # 防止无限循环
    
    # ... 其他字段
```

### 持久化 (Persistence)

通过 LangGraph 的 Checkpointer 机制实现跨会话记忆：

-   **开发环境**：`MemorySaver` (内存存储)
-   **生产环境**：`PostgresSaver` / `RedisSaver` (数据库存储)

```python
# workflow.py
workflow.compile(checkpointer=checkpointer)
```

---

## 四、业务流程示例

### 场景：首次进入，信息不足

1.  **用户**："我喜欢一个女生。"
2.  **Router**：新会话 -> **Main Agent**
3.  **Main Agent**：
    -   调用 `load_skill("inquiry")`
    -   **ToolNode** 返回指令
    -   生成 `inquiry_card`
    -   设置 `next_action="ask_user"`，结束本轮
4.  **System**：保存状态，向用户展示问题
5.  **用户**："她是我的同事..."
6.  **Router**：检测到 `current_agent="main_agent"` -> **Main Agent**
7.  **Main Agent**：
    -   恢复执行
    -   信息足够 -> `call_status`
8.  **Status Agent**：
    -   执行分析
    -   完成 -> 返回 Main Agent
9.  **Main Agent**：
    -   展示分析结果
    -   结束本轮

---

## 五、关键设计决策

### 5.1 为什么放弃 wait_user_input 节点？

旧方案使用显式的 `wait_user_input` 节点作为暂停点，容易产生悬空边。

新方案使用 **Router 状态恢复**：
-   代码逻辑依然保持线性（处理完 -> 结束）。
-   状态恢复逻辑集中在 Router，职责清晰。
-   对无状态服务极其友好。

### 5.2 为什么使用 ToolNode 而非手动执行？

-   **解耦**：将工具执行逻辑从 Agent 中剥离
-   **标准**：利用 LangGraph 预置的 `ToolNode`，减少样板代码
-   **兼容**：未来更容易扩展到多 Agent 协作模式

### 5.3 统一循环限制

在 State 中引入 `_iteration_count`，并在 Router 层统一检查：
-   防止 Agent 之间无限踢皮球
-   防止工具调用死循环
-   提供系统的兜底保护

---

## 六、待优化项

- [ ] **异步 Tool 优化**：支持并发执行多个工具
- [ ] **Structured Output**：使用 `.with_structured_output()` 替代 JSON 字符串解析
- [ ] **测试覆盖率**：增加针对 interrupt 恢复场景的集成测试
