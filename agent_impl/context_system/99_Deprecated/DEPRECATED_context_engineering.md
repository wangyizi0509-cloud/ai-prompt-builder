# AI 军师 Agent 上下文工程技术实现 v3.1（代码同步版）

> 面向工程团队的实现说明，基于 2025-12-30 的最新代码（`graph/context_builder.py`、`graph/archive_manager.py`、`graph/nodes/organize_agent.py` 等）。

---

## 1. 核心文件与职责

- `graph/context_types.py`：Layer1/2/3 数据结构、处理状态、任务注册表、工厂函数。`
- `graph/state.py`：`AgentState` 定义，初始状态创建、迁移和消息同步工具。`state.messages` 供 LangGraph 流转，`layer3_memory.all_messages` 存全量。
- `graph/context_builder.py`：上下文拼装与 token 估算；默认提取配置；对话压缩检查入口（通过 ExtractionPipeline 调度）。
- `graph/archive_manager.py`：对话压缩、任务思考压缩、Layer2 归档降级，统一归档入口；调用 StorageRouter/StorageProcessor 写入。
- `graph/storage_strategy.py`：存储策略层，包含 StorageRouter（路由）与 StorageProcessor（统一写入/降级）。
- `graph/extraction_strategy.py`：提取策略层，ExtractionPipeline 封装多层提取与字典输出。
- `graph/nodes/organize_agent.py`：整理 Agent（LLM）归档对话/报告/指南并提取信息；压缩任务思考摘要。
- `graph/crush_chat_storage.py`：Crush 聊天分层存储（L1 元数据、L2 结构化摘要、L3 片段，L4 语义检索预留）。
- `graph/tools/drawer_tools.py`：抽屉工具（仍主要依赖兼容字段 `history_archive`）。

---

## 2. 状态与存储结构

### 2.1 AgentState 关键字段（新版）
- Layer 1：`layer1_memory`（含 full_data、extraction_config、processing_status、version）。`user_context` 为兼容字段。
- Layer 2：`layer2_memory`（all_status_reports/all_action_plans/all_action_guides + extraction_config + processing_status + version）。旧版 `status_report/action_plan/action_guides` 保留兼容。
- Layer 3：`layer3_memory`（all_messages、conversation_summaries、task_registry、extraction_config、processing_status、total_turns、version）。`messages` 用于工作区流转。
- 任务：`task_registry` 仍保留兼容，但主存放在 `layer3_memory.task_registry`。
- 报告编号：`report_counter`（status_report/action_plan/action_guide）。
- 历史兼容：`history_archive` 仍被抽屉工具使用。

### 2.2 消息存储与同步
- `sync_new_messages_to_fullstore`：将 `state.messages` 的新增消息去重后写入 `layer3_memory.all_messages`，不删除历史。
- `compress_layer3` 触发时使用 `RemoveMessage` 从 `state.messages` 删除已压缩消息，但不会裁剪 `layer3_memory.all_messages`。
- 消息键：优先 ID，其次 `role:content`，辅助去重。

### 2.3 任务思考（Rolling Scratchpad）
- 结构：`task_registry[agent_name] -> list[TaskState]`，每个任务含 `reasoning`、`summary`、`is_active` 等。
- 拼装：`build_context_dict` 仅取当前活跃任务最近 10 条 reasoning。

---

## 3. 上下文提取（context_builder）

- `build_context`：按 Layer0→1→2→3 顺序拼接 Markdown；`include_layer0` 可选；通过 ExtractionPipeline 统一调度。
- Layer1：`extract_layer1` 读取 `layer1_memory.full_data`，`mode=full` 输出 3×3，压缩模式待实现。
- Layer2：`extract_layer2` 输出当前现状报告/行动规划/未完成指南全量，历史摘要分级（最近2条 summary，其余 one_liner，来源仅现状报告与已完成指南）。
- Layer3：`extract_layer3` 先拼 `conversation_summaries`（最多 5 条），再拼 `state.messages` 末尾最多 25 条（assistant 支持 JSON 提取 `response` 与 `inquiry_card`）。
- 任务思考：`_build_task_reasoning` 从任务注册表取活跃任务最近 10 条。
- Token 估算：`estimate_tokens=len(text)//2`；`TOKEN_BUDGET` 总 70k，输出预留 8k，层级预算 L1 15k / L2 20k / L3 15k，压缩阈值常量 55k 仅用于估算。

---

## 4. 归档与压缩实现（archive_manager）

### 4.1 对话压缩
- 配置：`LAYER3_ARCHIVE_CONFIG` → `max_recent_turns=4`、`compression_threshold=4`、`compression_batch_size=2`、`max_summaries=10`、`reasoning_limit=10`、`reasoning_compression_batch=2`。
- 触发：`check_layer3_compression_needed` 基于“用户轮次”计数，>4 且超出部分为 2 的倍数时触发。
- 切分：`get_layer3_messages_to_compress` 以用户消息为界保留最近 4 轮，其余进入压缩批次。
- 执行：`compress_layer3`
  1) 设置 `processing_status` 并保存 fallback（all_messages、conversation_summaries、task_registry）。
  2) 调用整理 Agent `archive_conversation_batch` 生成摘要+提取信息。
  3) 新摘要写入 `conversation_summaries` 头部（限 10），Layer1 合并新情报，Layer1/Layer3 版本递增。
  4) 使用 `RemoveMessage` 从 `state.messages` 删除被压缩消息；`layer3_memory.all_messages` 不裁剪。
- 失败：清理处理状态，返回原数据。

### 4.2 任务思考压缩
- 检查：`check_task_reasoning_compression_needed` 活跃任务 reasoning >10 触发。
- 执行：`compress_task_reasoning` 保留最近 2 条，其余调用 `summarize_task_reasoning`（LLM）写入 `summary`，reasoning 仅留尾部；Layer3 版本+时间更新。

### 4.3 行动指南与现状报告归档
- 指南：`archive_guide_to_layer2`（兼容入口 `archive_guide_on_completion`）。整理 Agent 生成 `summary/one_liner`，指南标记 completed，经 StorageRouter 路由、StorageProcessor 降级写回 Layer2，同时更新 Layer1。
- 现状分析：`archive_status_to_layer2`（兼容入口 `archive_status_on_replacement`）。旧报告标记 `is_current=False`，经 StorageRouter/StorageProcessor 写回 Layer2 并更新 Layer1。
- 历史降级：StorageProcessor 内置规则，保留最近 2 条 summary，其余转 one_liner，超出 12 条丢弃。
- 行动规划：尚无归档链路，历史摘要缺失。

### 4.4 统一入口
- `process_archiving_if_needed`：每轮检查对话压缩和任务思考压缩并合并更新。指南/报告归档需业务节点显式调用。
- `check_and_compress_if_needed`：仅对话压缩快捷入口。

---

## 5. 整理 Agent 细节（organize_agent）

- 公共入口：`organize_and_archive(content, content_type, existing_user_context)`，按类型选择不同 Prompt，低温度 LLM。
- 行动指南 `_process_action_guide`：生成中等摘要+一句话+提取信息；返回 `HistorySummary`。
- 现状分析 `_process_status_report`：同上，关注阶段/问题/风险；返回 `HistorySummary`。
- 对话 `_process_conversation`：生成 50-100 字摘要、话题标签、提取信息；返回 `ConversationArchive`。
- 信息合并：`merge_extracted_info_to_context` 将提取结果追加到 3×3 的 `ai_provide`。
- 封装函数：`archive_completed_guide`、`archive_replaced_status_report`、`archive_conversation_batch`，均返回摘要和更新后的 Layer1 上下文。
- 任务思考压缩：`summarize_task_reasoning` 生成 ≤50 字的任务摘要，用于 Rolling Scratchpad。

---

## 6. Crush 聊天分层存储

- 管理器：`CrushChatManager`，全量消息保存在内存；可序列化/反序列化。
- 参数：`recent_messages_count=20`、`max_important_messages=10`、`summary_update_threshold=10`（每新增 10 条重算摘要）、摘要基于最近 30 条消息。
- 输出：
  - L1 元数据：总条数/频率/时间跨度/最后聊天时间。
  - L2 结构化摘要：关键事件、情感转折、主要话题（LLM 生成）。
  - L3 片段：最近 N 条、标记重要消息、关键词搜索（文本匹配）。
- 上下文：`build_context_l1_l2()` 供常驻，`build_context_l3()` 按需。

---

## 7. 抽屉工具（兼容实现）

- `DrawerTools` 仍主要读取 `history_archive`（status/guide/conversation），未迁移到 Layer2/Layer3 新结构。
- Crush 聊天抽屉：`get_recent/important/search` 依赖 `CrushChatManager`。
- LangChain 工具创建：`create_drawer_tools_for_langchain` 返回 Tool 列表。

---

## 8. 配置速查

- Token 预算（context_builder）：`total=70000`，`output_reserve=8000`，`layer1_static=15000`，`layer2_working=20000`，`layer3_conversation=15000`，`compression_threshold=55000`（估算用）。
- 提取默认：Layer1 `mode=full max_tokens=15000`；Layer2 `recent_summary_count=2 max_one_liner_count=10 include_active_guides=True`；Layer3 `max_recent_turns=25 include_summaries=True max_summary_count=5`。
- 压缩/归档（archive_manager）：见 4.1/4.2/4.3 配置，重点对话阈值 4 轮、批量 2 轮，摘要上限 10。
- 任务思考：`TASK_REASONING_CONFIG.max_reasoning_notes=10`（context_builder 展示）；压缩保留 2 条（archive_manager）。
- Crush 聊天：`recent_messages_count=20`、`max_important_messages=10`、`summary_update_threshold=10`。

---

## 9. 已知差异与风险

1) Layer3 提取使用 25 条消息，但压缩阈值仅 4 用户轮，节奏不一致，可能出现摘要过密或上下文仍偏长。  
2) 行动规划未接入归档链路，缺少历史摘要降级。  
3) Layer1 压缩模式仍未实现。  
4) `layer3_memory.all_messages` 不裁剪，长对话会在持久化中持续膨胀。  
5) 抽屉工具依赖兼容字段，未读取新 Layer2/Layer3 结构。  
6) 对话压缩以用户轮次计数，若助理回复很长但用户轮次少，仍不会触发；需评估是否改为 token 或总条数。  
7) 任务思考压缩保留 2 条固定值，若想要更长记忆需调整 `reasoning_compression_batch`。

---

## 10. 版本记录

- v3.1（2025-12-30）：同步代码，更新对话压缩阈值、任务思考压缩、归档链路与风险提示。
- v1.0（2024-12-19）：首版技术实现文档。
