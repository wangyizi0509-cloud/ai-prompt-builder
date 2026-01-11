# 数据处理与流转机制 (Data Processing & Flow)

## 1. 概述

本产品采用 **"分层长期记忆架构" (Layered Long-term Memory Architecture)**，将数据处理分为两个核心流向：
1.  **业务执行流 (Business Flow)**：实时处理用户意图，生成策略与指南，写入短期/中期记忆。
2.  **记忆整理流 (Archiving Flow)**：异步提取高价值信息，压缩历史记录，沉淀为长期记忆。

核心理念是：**让业务 Agent 专注于"当下"的决策，让整理 Agent 专注于"过去"的沉淀。**

---

## 2. 数据流入与业务处理 (Data Inflow)

当用户消息进入系统时，数据流经各业务 Agent，并产生新的结构化数据。我们采用 **"双重状态管理"** 机制来确保数据的实时性与可追溯性。

我们支持两种更新模式：
*   **全量重写 (Rewrite)**：当阶段发生根本性变化时（如 L2 -> L3）。
*   **增量微调 (Refine/Update)**：当仅需修正细节或推进状态时（如补充一个风险点、更新任务状态）。

### 2.1 现状分析数据流 (Status Analysis Flow)
- **触发**: `Status Agent` 执行分析任务。
- **产出动作**: 生成新的或更新 `StatusReportItem`。
- **写入机制 (Layer 2)**:
    - **New Version**: 生成全新报告，压入列表头部，标记 `is_current=True`。
    - **Refinement**: (未来支持) 在当前报告基础上进行字段级更新，不生成新版本，仅更新 `last_updated`。
    - **Retire**: 旧版本报告自动标记 `is_current=False`。
    - **归档触发**: 旧报告退役时，触发 `Archive Manager` 规则。

### 2.2 行动规划数据流 (Action Plan Flow)
- **触发**: `Plan Agent` 执行规划任务。
- **产出动作**: 生成新的或更新 `ActionPlanItem` 或更新现有规划。
- **写入机制 (Layer 2)**:
    - **Strategy Shift**: 战略方向改变时，生成新规划，标记 `is_current=True`。
    - **Update**: 仅调整某个阶段目标或补充原则时，在原对象上修改。
    - **Retire**: 旧规划失效后标记 `is_current=False` 并触发归档。

### 2.3 行动指南数据流 (Action Guide Flow)
- **触发**: `Guide Agent` 执行指南生成或状态更新任务。
- **产出动作**: 生成 `ActionGuideItem` 或修改其 `status` 字段。
- **写入机制 (Layer 2)**:
    - **Create**: 生成新指南，状态为 `Pending`或`In_Progress`。
    - **Status Update**: 更新现有指南状态 (`Pending` -> `In_Progress` -> `Completed`/`Cancelled` / `Paused`)。
    - **归档触发**: 当指南状态变为终态（Completed/Cancelled/Expired）时，触发 `Archive Manager` 规则。

### 2.4 对话数据流 (Conversation Flow)
- **触发**: 每一轮对话结束（Agent 生成回复）。
- **产出动作**: 新消息追加至 `messages` 列表。
- **写入机制 (Layer 3)**:
    - **Rolling Window**: 原始对话 (`messages`) 保留在 Layer 3 的 `all_messages` 中。
    - **Compression**: 当对话轮次超过阈值（如 30 轮），触发 `archive_manager` 进行压缩。
    - **Task Reasoning**: 任务思考过程 (`Rolling Scratchpad`) 随任务状态更新，任务结束后归档为摘要。

---

## 3. 上下文构建机制 (Context Building)

为了解决 LLM 上下文窗口限制，我们引入了 `ContextBuilder` 模块，负责按需组装 Context。

### 3.1 组装策略
`ContextBuilder` 不会无脑加载所有数据，而是根据目标 Agent 的需求进行 **"分层加载"**：

| 层级 | 数据内容 | 加载策略 | 目的 |
| :--- | :--- | :--- | :--- |
| **Layer 1** | **静态情报** (User/Crush/Both) | **全量/压缩** | 提供底层认知 (3x3矩阵) |
| **Layer 2** | **工作上下文** (Report/Plan/Guide) | **混合模式** | 提供当前工作台 |
| **Layer 3** | **对话历史** (Messages/Thought) | **滚动窗口** | 提供近期交互记忆 |

### 3.2 智能加载细节
- **现状/规划**: 仅加载 `is_current=True` 的最新版本。历史版本仅加载摘要。
- **行动指南**: 
    - **详情加载**: 仅 `In_Progress` (进行中) 的指南。
    - **元数据加载**: `Pending`(待执行)、`Paused`(暂停) 以及所有历史终态指南，仅加载列表 (ID/Title/Status/Summary) 以节省 Token。
- **对话历史**: 
    - 最近 N 轮 (e.g. 25轮) 完整加载。
    - 更早的历史以 `ConversationSummary` (摘要) 形式加载。
    - 任务思考过程 (`Thought`) 仅加载当前活跃任务的记录，避免上下文污染。

---

## 4. 记忆整理与归档 (Archiving & Insight Extraction)

这是系统的**后台处理机制**，由 `Organize Agent` 和 `Archive Manager` 协同完成。

### 4.1 归档流程
当业务数据（Report/Guide/Conversation）进入"历史"状态时：
1.  **触发**: `Archive Manager` 捕捉到状态变更（如 Report 被替换、Guide 完成、对话超长）。
2.  **分发**: 将原始数据发送给 `Organize Agent`。
3.  **处理**: 
    - **摘要生成**: 生成一句话摘要 (`one_liner`) 和中等摘要 (`summary`)。
    - **洞察提取**: 从历史数据中挖掘高价值信息（如"用户其实很自卑"、"Crush喜欢猫"）。
3.  **回写**:
    - **Update Layer 2**: **保留原文** (`full_content` 字段保持不变)，仅在记录中**新增/更新** `summary` 和 `one_liner` 字段。
    - **Update Layer 1**: 将提取的洞察追加到 `UserContext` 的 3x3 矩阵中（`ai_provide` 字段）。

### 4.3 价值反哺
通过这个机制，系统实现了**"越用越聪明"**：
- 每一份过期的报告、每一个完成的任务，都会转化为 Layer 1 的**静态情报**。
- 下一次生成策略时，Agent 就能利用这些沉淀下来的情报，做出更精准的判断。

---

## 5. 数据流转图示 (Data Flow Diagram)

```mermaid
graph TD
    User[用户输入] --> Router{Main Agent 路由}
    
    %% 业务执行流 (Business Flow)
    Router -->|分发| StatusAgent[Status Agent]
    Router -->|分发| PlanAgent[Plan Agent]
    Router -->|分发| GuideAgent[Guide Agent]
    
    %% 上下文加载 (Context Loading)
    L1[Layer 1] -.-> ContextBuilder
    L2[Layer 2] -.-> ContextBuilder
    L3[Layer 3] -.-> ContextBuilder
    ContextBuilder -->|注入上下文| StatusAgent
    ContextBuilder -->|注入上下文| PlanAgent
    ContextBuilder -->|注入上下文| GuideAgent

    %% 执行与写入 (Execution & Write)
    StatusAgent -->|生成/更新| L2_Report[L2: Status Report]
    PlanAgent -->|生成/更新| L2_Plan[L2: Action Plan]
    GuideAgent -->|更新状态/新建| L2_Guide[L2: Action Guide]
    
    %% 记忆整理流 (Archiving Flow)
    L2_Report --"旧版本退役\n(规则触发)"--> ArchiveManager[Archive Manager]
    L2_Plan --"旧版本退役\n(规则触发)"--> ArchiveManager
    L2_Guide --"任务终态\n(规则触发)"--> ArchiveManager
    
    ArchiveManager --> OrganizeAgent[Organize Agent\n(智能处理)]
    
    OrganizeAgent -->|提取洞察| L1
    OrganizeAgent -->|生成摘要| L2
    OrganizeAgent -->|生成摘要| L3
```

## 6. 关键数据结构映射

| 概念 | 对应代码结构 | 存储位置 |
| :--- | :--- | :--- |
| **静态情报** | `UserContext` (3x3 Dict) | `state["layer1_memory"]["full_data"]` |
| **现状报告** | `StatusReportItem` | `state["layer2_memory"]["all_status_reports"]` |
| **行动规划** | `ActionPlanItem` | `state["layer2_memory"]["all_action_plans"]` |
| **行动指南** | `ActionGuideItem` | `state["layer2_memory"]["all_action_guides"]` |
| **对话历史** | `List[Message]` | `state["layer3_memory"]["all_messages"]` |
| **动态情报** | `DynamicIntelItem` | `state["layer2_memory"]["dynamic_intels"]` |
