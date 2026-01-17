# AI 军师 Agent 上下文策略 v3.1（代码同步版）

> 目标：与当前实现保持一致，确保上下文高信噪比与可追溯性。  
> 适用日期：2025-12-30，依据 `graph/context_builder.py`、`graph/archive_manager.py` 等最新代码。

---

## 1. 架构与分层总览

仅保留 Layer 0-3，历史摘要已内嵌到各层，旧版 `history_archive` 仅做兼容。  
- 架构总览（获取 → 存储策略 → 存储 → 提取策略 → 消费）见 `agent_impl/docs/context_architecture.md`

| 层级 | 作用 | 提取/压缩策略（现状） | 关键参数 |
| --- | --- | --- | --- |
| Layer 0 系统指令 | 只读常驻，含人设/ACR/信任优先级 | 始终全量 | — |
| Layer 1 静态情报 | 3×3 用户/Crush/双方矩阵 | 默认 `mode=full`；压缩模式 TODO | `max_tokens=15000` |
| Layer 2 工作上下文 | 现状报告 + 行动规划 + 行动指南 | 当前版本全量；历史摘要分级（最近2条中等摘要，之后一句话） | `recent_summary_count=2` `max_one_liner=10` |
| Layer 3 对话历史 | `state.messages` 最近对话 + 摘要 | 构建上下文：最近 25 条消息 + 最多 5 条摘要；压缩触发按用户轮次 | 提取：`max_recent_turns=25` 摘要数 5；压缩：阈值 4 轮，  批量 2 轮 |

---

## 2. Layer 策略细则

### 2.1 Layer 0 系统指令
- 内容：人设、ACR/LT 模型、工具与安全边界、信任优先级说明。  
- 放在 Prompt 模板，`build_context` 仅在 `include_layer0=True` 时拼入。

### 2.2 Layer 1 静态情报（3×3）
- 结构：`Layer1Memory.full_data` = `user_info` / `crush_info` / `both_info`，每项含 `user_provide / fact / ai_provide`。带版本号、更新时间、`processing_status`（并发降级用）。  
- 提取：当前仅 `full` 模式输出完整矩阵；压缩模式占位待实现。  
- 信任优先级：fact > ai_provide > user_provide。  
- 更新来源：整理 Agent 在归档时通过 `merge_extracted_info_to_context` 追加到 `ai_provide`。

### 2.3 Layer 2 工作上下文
- 结构：`all_status_reports`、`all_action_plans`、`all_action_guides` + `extraction_config` + `processing_status` + 版本。  
- 提取规则：  
  - 当前现状报告、当前行动规划：全量。  
  - 未完成指南（pending/in_progress）：全量且不可压缩。  
  - 历史摘要：仅现状报告 + 已完成指南参与分级（最近2条中等摘要，其余一句话）；行动规划历史尚未接入归档。  
- 摘要降级：StorageProcessor 内置降级规则（最近2条中等摘要，其余只留 `one_liner`，最多 2+10 条）。  
- 编号：`report_id / plan_id / guide_id` 作为展示前缀。

### 2.4 Layer 3 对话历史
- 存储：`layer3_memory.all_messages` 全量留存；`conversation_summaries` 存压缩摘要；`task_registry` 存 Rolling Scratchpad。  
- 提取到 Prompt：使用 `state.messages`（工作区消息）末尾 `max_recent_turns=25` 条 + `conversation_summaries` 前 5 条。`all_messages` 不直接用于拼上下文。  
- 摘要格式：`#### 历史对话摘要` + `#### 最近对话`，assistant 消息支持 JSON 提取 `response` 和 `inquiry_card` 文本。  
- Rolling Scratchpad：`task_registry` 中活跃任务的 reasoning 仅取最近 10 条拼入 `task_reasoning` 段。  
- 压缩触发（实际代码）：按“用户轮次”计算，阈值 4 轮，超出每 2 轮触发；保留最近 4 轮用户消息，其余调用整理 Agent 生成摘要存 `conversation_summaries`（最多 10 条），并把被压缩消息从 `state.messages` 中删除（`layer3_memory.all_messages` 仍保留）。  
- 说明：提取配置（25 条）与压缩阈值（4 轮）存在不一致，当前以代码真实行为为准。

### 2.5 Crush 聊天记录（独立于 Layer 1-3）
- 管理器：`CrushChatManager`（L1 元数据、L2 结构化摘要、L3 关键片段，L4 语义检索待实现）。  
- 参数：最近消息 20 条，重要消息 10 条，每新增 10 条自动刷新摘要，摘要基于最近 30 条生成关键事件/情感转折/话题。  
- 上下文使用：常驻可拼 L1+L2 摘要，按需调用 L3 片段。

---

## 3. 归档与压缩流水线（archive_manager 驱动）

### 3.1 对话压缩
- 检查：`check_layer3_compression_needed` 按用户轮次 >4 且超出部分是 2 的倍数触发。  
- 压缩：`compress_layer3`
  1) 设置 `processing_status`、保存 fallback。  
  2) 取需压缩消息，调用整理 Agent `archive_conversation_batch` 生成摘要 + 新的 Layer1 情报。  
  3) 通过 StorageRouter 路由 conversation_summary → Layer3，StorageProcessor 追加摘要（限 10），Layer1 计数+版本递增。  
  4) 通过 `RemoveMessage` 把已压缩消息从 `state.messages` 删除，`layer3_memory.all_messages` 不裁剪。  
- 失败：超时/异常会清理处理状态，保留原数据。

### 3.2 任务思考过程压缩
- 触发：任意活跃任务 reasoning 长度 > `reasoning_limit=10`。  
- 行为：保留最近 2 条，其余批量摘要（LLM `summarize_task_reasoning`），摘要写回 `summary` 字段，reasoning 仅留尾部，Layer3 版本+时间更新。

### 3.3 行动指南归档
- 调用：`archive_guide_to_layer2`（或兼容入口 `archive_guide_on_completion`）。  
- 流程：整理 Agent 生成 `summary/one_liner`，标记指南为 completed，降级旧摘要，Layer2/Layer1 更新时间与计数递增。  
- 历史分级：仍按最近2条中等摘要、其余一句话。

### 3.4 现状分析归档
- 调用：`archive_status_to_layer2`（或兼容入口 `archive_status_on_replacement`）。  
- 流程：整理 Agent 生成摘要，旧报告标记 `is_current=False`，降级旧摘要后重排列表；Layer1 同步更新。  
- 仅现状报告接入归档；行动规划尚未接入归档链路。

### 3.5 统一入口
- `process_archiving_if_needed`：每轮结束检查对话压缩与任务思考压缩；指南/报告归档通常由业务节点显式调用。  
- `check_and_compress_if_needed`：供工作流直接调用，仅处理对话压缩。

---

## 4. 上下文组装（context_builder）

- 入口：`build_context(state, target_agent, include_layer0=False)` 返回拼好的 Markdown；`build_context_dict` 输出可插值字典。底层通过 ExtractionPipeline 统一调度各层提取。  
- Layer 1：`extract_layer1` 使用 `layer1_memory.full_data`，默认全量输出；压缩模式 TODO。  
- Layer 2：`extract_layer2` 输出当前报告/规划/活跃指南 + 历史摘要（仅现状+已完成指南）。无数据返回空。  
- Layer 3：`extract_layer3` 先拼摘要（最多 5 条），再拼 `state.messages` 末尾最多 25 条（按角色过滤，assistant 支持 JSON 解析 `response` + `inquiry_card`）。  
- 任务思考：`_build_task_reasoning` 从 `task_registry` 取活跃任务最近 10 条 reasoning 拼成隐藏段。  
- Token 估算：`estimate_tokens=len(text)/2`；`TOKEN_BUDGET` 总 70k，预留输出 8k，层级预算：L1 15k / L2 20k / L3 15k；压缩阈值常量 55k 仅用于估算，真实压缩由对话轮次触发。

---

## 5. 兼容性与已知缺口

- `history_archive` 仍在 DrawerTools 等处用于兼容；新链路主要写入 Layer1/2/3。  
- 行动规划未进入归档/降级链路，历史摘要依旧缺失。  
- Layer1 压缩模式占位未实现。  
- Layer3 提取（25 条）与压缩阈值（4 用户轮）不一致，易出现“刚压缩就又提取过长”或摘要过密；需后续统一策略。  
- `layer3_memory.all_messages` 不裁剪，可能持续膨胀；当前仅删除工作区 `messages` 中的已压缩部分。  
- DrawerTools 抽屉工具未迁移到 Layer2/Layer3 新结构，仍读兼容字段。

---

## 6. 版本记录

- v3.1（2025-12-30）：同步最新代码，调整对话压缩阈值、任务思考压缩、归档链路与兼容性说明。  
- v3.0（2024-12-22）：移除统一 Layer4，分层长期记忆。  
- v2.x 及以前：旧版统一存档、无任务思考压缩。
