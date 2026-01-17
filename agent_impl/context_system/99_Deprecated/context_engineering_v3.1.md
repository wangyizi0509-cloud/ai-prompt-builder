# AI 军师 Agent 上下文工程技术实现 v3.1

> ⚠️ **DEPRECATED - 已废弃**
> 
> 本文档已被以下规范文档取代，请参阅：
> - `Layer_Specs/layer1_spec_v1.0.md` - Layer 1 静态情报规范
> - `Layer_Specs/layer2_spec_v1.0.md` - Layer 2 工作上下文规范
> - `Layer_Specs/layer3_spec_v1.0.md` - Layer 3 对话历史规范
> - `Task_System/task_system_spec.md` - 任务系统规范
> - `Context_Assembly/context_assembly_spec.md` - 上下文组装规范
>
> 以下内容仅供历史参考，不再维护。

---

> **原适用版本**：v3.1 (2025-12-30)
> **代码对应**：`graph/context_builder.py`, `graph/archive_manager.py`, `graph/context_types.py`

本文档详细说明了 AI 军师 Agent 的上下文管理技术实现。核心目标是实现**分层长期记忆 (Layered Long-term Memory)**，确保 Token 消耗可控且信息不丢失。

---

## 1. 核心数据结构 (Data Structures)

所有状态定义在 `graph/state.py` 的 `AgentState` 中，具体类型定义在 `graph/context_types.py`。

### 1.1 AgentState 顶层结构

状态对象不再包含扁平化的字段，而是按层级组织：

```python
class AgentState(TypedDict):
    # === Layer 1: 静态情报 ===
    layer1_memory: Layer1Memory
    # 兼容字段: user_context (指向 layer1_memory.full_data)

    # === Layer 2: 工作上下文 ===
    layer2_memory: Layer2Memory
    # 兼容字段: status_report, action_plan, action_guides

    # === Layer 3: 对话历史与推理 ===
    layer3_memory: Layer3Memory
    messages: Annotated[list, add_messages]  # LangGraph 工作区消息

    # === 辅助 ===
    crush_chat_storage: Optional[CrushChatStorage] # 独立存储
    report_counter: ReportCounter                  # 报告编号生成器
```

### 1.2 各层 Memory 结构

每一层都包含 `full_data` (全量数据)、`extraction_config` (提取配置) 和 `processing_status` (并发锁)。

#### Layer 1 (Static Intel)
```python
class Layer1Memory(TypedDict):
    full_data: UserContext  # 3x3 矩阵 (user/crush/both x user/fact/ai)
    extraction_config: Layer1ExtractionConfig  # mode="full"|"compressed"
```

#### Layer 2 (Working Context)
```python
class Layer2Memory(TypedDict):
    all_status_reports: list[StatusReportItem]  # 所有历史报告
    all_action_plans: list[ActionPlanItem]      # 所有历史规划
    all_action_guides: list[ActionGuideItem]    # 所有指南(含已完成)
    
    # 提取配置：控制历史摘要的数量 (最近2个中等摘要，其余一句话)
    extraction_config: Layer2ExtractionConfig 
```

#### Layer 3 (Conversation)
```python
class Layer3Memory(TypedDict):
    all_messages: list[dict]                    # 全量消息存档 (不随压缩删除)
    conversation_summaries: list[ConversationSummary] # 压缩后的对话摘要
    task_registry: AgentTaskRegistry            # Rolling Scratchpad (任务思考)
```

---

## 2. 上下文组装流水线 (Context Pipeline)

代码位置：`graph/context_builder.py` -> `build_context()`

当 Agent 需要调用 LLM 时，我们会实时组装 Context。组装过程是**只读**的，不会修改 State。

### 2.1 组装逻辑

1.  **Layer 0 (System)**: 
    *   直接读取 Prompt 模板中的系统指令。
2.  **Layer 1 (Static)**: 
    *   调用 `extract_layer1()`。
    *   目前逻辑：完整输出 3x3 矩阵内容。
3.  **Layer 2 (Working)**: 
    *   调用 `extract_layer2()`。
    *   **当前内容**：最新的报告、规划、未完成的指南 -> **全量输出**。
    *   **历史内容**：已完成指南、旧报告 -> 根据配置 (默认最近2个) 输出摘要。
4.  **Layer 3 (History)**: 
    *   调用 `extract_layer3()`。
    *   **摘要区**：输出 `conversation_summaries` (默认最近 5 条)。
    *   **对话区**：输出 `state.messages` 中的最近 `max_recent_turns` (默认 25) 条消息。
    *   *注*：这里读取的是 `state.messages` (工作区)，而不是 `layer3_memory.all_messages` (存档区)。

---

## 3. 归档与压缩流水线 (Archiving Pipeline)

代码位置：`graph/archive_manager.py`

这是系统的"垃圾回收"机制，负责将动态信息转为静态摘要。

### 3.1 触发机制

我们采用**被动触发**机制，在每轮对话结束或特定事件发生时检查：

1.  **对话压缩 (Conversation Compression)**:
    *   触发器：`check_layer3_compression_needed()`
    *   逻辑：基于**用户轮次 (User Turns)**。
    *   阈值：默认保留最近 4 轮。每超出 2 轮触发一次压缩。
    *   *注意*：虽然提取时看 25 条，但压缩阈值设得较低 (4 轮) 是为了给整理 Agent 留出缓冲，防止 Token 突然爆炸。

2.  **任务思考压缩 (Reasoning Compression)**:
    *   触发器：`check_task_reasoning_compression_needed()`
    *   逻辑：当活跃任务的 `reasoning` 条目 > 10 条。
    *   动作：保留最近 2 条，将旧的 8+ 条压缩为 summary。

3.  **业务归档 (Explicit Archiving)**:
    *   **指南完成**：`archive_guide_to_layer2()`。指南状态变为 `completed`，生成摘要，移入历史区。
    *   **报告更新**：`archive_status_to_layer2()`。旧报告标记 `is_current=False`，生成摘要。

### 3.2 整理 Agent (Organize Agent)

代码位置：`graph/nodes/organize_agent.py`

归档不是简单的截断，而是调用 LLM (整理 Agent) 进行智能处理：

1.  **输入**：待归档的原始数据 (如 5 轮对话、1 个完成的任务)。
2.  **LLM 处理**：
    *   生成 **Summary** (用于 Layer 2/3)。
    *   提取 **Insights** (用于更新 Layer 1)。
3.  **输出**：结构化数据，写回对应的 Memory。

### 3.3 并发控制 (Concurrency)

为了防止在 LLM 整理归档期间用户发来新消息导致数据不一致，我们实现了简单的乐观锁机制：

*   `processing_status`：标记该层正在处理中。
*   `fallback_data`：保存处理前的快照。
*   如果整理期间需要读取，优先读快照。整理完成后，合并更新。

---

## 4. 特殊模块实现

### 4.1 Crush 聊天记录
代码位置：`graph/crush_chat_storage.py`

独立于 Layer 1-3 的存储模块。
*   **CrushChatManager**：单例管理类。
*   **存储**：目前全量存内存 (List)，生产环境应接向量数据库。
*   **L2 摘要更新**：每新增 10 条消息，自动触发一次 LLM 总结，更新 `summary` 字段。

### 4.2 抽屉工具 (Drawer Tools)
代码位置：`graph/tools/drawer_tools.py`

允许 Agent 主动查阅"被压缩掉"的历史详情。
*   **原理**：直接读取 `layerX_memory` 中的全量数据列表 (如 `all_action_guides`)。
*   **接口**：`get_full_history(type, index)`。

---

## 5. 开发注意事项

1.  **消息同步**：
    *   LangGraph 的 `state.messages` 是工作区，会被裁剪。
    *   `layer3_memory.all_messages` 是永久存档，**只增不减**。
    *   `sync_new_messages_to_fullstore` 负责在每轮结束时将新消息同步到存档。

2.  **Token 估算**：
    *   使用简单的 `len(text) // 2` 进行估算，非精确 Tokenizer，仅用于阈值判断。

3.  **配置调整**：
    *   所有阈值配置在 `graph/archive_manager.py` 的 `LAYER3_ARCHIVE_CONFIG` 等常量中。
    *   调整 `max_recent_turns` 和 `compression_threshold` 时需保持平衡，避免频繁触发压缩导致 LLM 成本上升。
