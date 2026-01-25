# 存储层数据结构（Storage Schema v2.0）

> 目的：提供“分层长期记忆”的**人类可读结构总览**，帮助研发快速理解 AgentState/各层 Memory/关键字段的关系。  
> 说明：此文档是概览型 Schema；更细的输出格式请以 `02_Specs/` 为准。

代码对应：
- `agent_impl/graph/state.py`（`AgentState`）
- `agent_impl/graph/context_types.py`（Layer1/2/3 类型）

---

## 1. AgentState 顶层结构（核心字段）

`AgentState` 是工作流的统一状态容器，核心字段可以按三类理解：

1) **用户输入与路由控制**
- `user_message`
- `current_message_id`
- `intent_type`
- `next_action`
- `route_to`
- `should_continue`

2) **分层长期记忆（长期存储与提取以这三块为准）**
- `layer1_memory`
- `layer2_memory`
- `layer3_memory`

3) **消息流（LangGraph messages，用于模型调用历史）**
- `messages`（会持续 append；模型调用时会做过滤与滑窗）

此外存在少量“向后兼容字段”（旧格式），例如 `user_profile/status_report/action_plan/action_guide/history_archive/task_registry` 等；新实现以 `layer*_memory` 为权威来源。

---

## 2. Layer 1：静态画像（Layer1Memory）

核心结构：
- `full_data`: `UserContext`（3×3 情报矩阵）
- `extraction_config`: 提取配置（如 mode/max_tokens）
- `processing_status`: 并发处理状态（压缩/提取/归档时的降级快照）
- `last_updated` / `update_count` / `version`: 元数据

`UserContext`（3×3）：
- `user_info`: `InfoSource`
- `crush_info`: `CrushInfo`（额外含 `crush_name`）
- `both_info`: `InfoSource`

`InfoSource` 三列：
- `user_provide`: `AtomicMemory[]`
- `fact`: `AtomicMemory[]`
- `ai_provide`: `AtomicMemory[]`

---

## 3. Layer 2：工作上下文（Layer2Memory）

核心字段：
- `current_status_report`: `StatusReportItem`
- `status_report_history`: `StatusReportItem[]`（历史摘要/降级）
- `current_action_plan`: `ActionPlanItem`
- `action_plan_history`: `ActionPlanItem[]`
- `action_guides`: `ActionGuideItem[]`（含状态机）
- `dynamic_intels`: `DynamicIntelItem[]`（短期情报）
- `extraction_config` / `processing_status` / `last_updated` / `version`

> 注：历史列表通常只保留摘要字段（`summary`/`one_liner`），全文在 current 内或由工具按需加载。

---

## 4. Layer 3：对话历史与任务（Layer3Memory）

核心字段：
- `all_messages`: Message[]（长期对话消息流，可与 `state.messages` 互相兼容）
- `conversation_summaries`: `ConversationSummary[]`
- `task_registry`: `{ agent_name: TaskState[] }`
- `extraction_config` / `processing_status` / `last_updated` / `total_turns` / `version`

`TaskState`（任务）：
- `task_id` / `title` / `summary`
- `status`: `pending | active | completed`
- `reasoning_notes`: list（结论导向，默认最多 8 条用于注入）
- `bound_contexts`: `BoundContext[]`
- `started_at` / `completed_at` / `completion_summary`

---

## 5. 并发处理状态（ProcessingStatus）

当系统在后台做压缩/提取/归档时，为避免并发写入冲突，会在对应 Memory 上打标：
- `is_processing`
- `processing_type`: `compression | extraction | archiving`
- `started_at`
- `snapshot_version`
- `fallback_data`（降级快照）

这使得系统在“正在处理”期间可以选择降级策略，而不是读到半成品状态。

