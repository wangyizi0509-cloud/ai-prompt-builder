# 压缩与归档策略（Compression Strategy v2.0）

> 目的：在不丢失关键决策信息的前提下，把无限增长的数据压缩到可控规模，保证长期稳定运行。

代码对应：
- 归档管理器：`agent_impl/graph/archive_manager.py`
- 整理 Agent：`agent_impl/graph/nodes/organize_agent.py`
- Layer 3 文本化历史：`agent_impl/graph/context_builder.py`

---

## 1. 压缩系统总览

压缩与归档覆盖 4 类场景：

1. **对话压缩（Layer 3）**：旧对话 → 对话摘要 + 信息分流（写入 L1/L2）
2. **报告归档（Layer 2）**：旧报告 → summary/one_liner（并可沉淀画像信息到 L1）
3. **规划归档（Layer 2）**：旧规划 → summary/one_liner
4. **指南归档（Layer 2）**：指南进入终态 → summary/one_liner + 画像沉淀 + 可能的短期态势

---

## 2. 触发矩阵（什么时候压缩/归档）

### 2.1 对话压缩

触发逻辑由 `archive_manager.check_layer3_compression_needed()` 控制：
- 按 **用户轮次**计数
- 超过阈值后，按批量触发（避免每轮都压缩）

> 生产阈值通常会高一些（例如 25+）；测试环境可能更低（便于覆盖测试）。

### 2.2 报告/规划归档

当“新版本写入 current”且“旧版本进入 history”时触发：
- 归档对象是 **旧版本**
- 归档产物是 `summary` 与 `one_liner`（用于后续注入的降级）

### 2.3 指南归档

当指南进入终态时触发（对齐状态机）：
- `completed` / `cancelled` / `expired`：触发归档
- `pending` / `in_progress` / `paused`：不归档（仍在进行或可恢复）

---

## 3. 压缩的产物（写到哪里）

| 场景 | 主要产物 | 写入位置 |
|:---|:---|:---|
| 对话压缩 | `ConversationSummary`（topics + summary） | Layer 3 `conversation_summaries` |
| 对话压缩 | 抽取的长期画像信息 | Layer 1 3×3 矩阵 |
| 对话压缩 | 抽取的短期态势 | Layer 2 `dynamic_intels` |
| 报告/规划归档 | summary/one_liner | Layer 2 `*_history` |
| 指南归档 | summary/one_liner + 画像/事实 | Layer 2 `action_guides`（终态项）+ Layer 1/2 |

---

## 4. 摘要生成规范（质量要求）

摘要的共同目标：**高信息密度 + 可操作 + 可追溯**。

不同摘要侧重点：
- 对话摘要：互动质量、关系动态、关键事实/约定、待办
- 报告摘要：阶段判定、核心问题、态势、关键发现、建议方向
- 规划摘要：阶段目标、核心策略、关键里程碑
- 指南摘要：执行情况、用户反馈、对方反应、关键收获

质量检查清单见：`summary_checklist_spec_v2.0.md`

---

## 5. 并发与降级（为什么需要 processing_status）

压缩/归档属于“后台回路”，可能与用户新消息并发发生。系统通过：
- 在对应 Memory 上设置 `processing_status`
- 保存 `fallback_data`（快照）

来保证：
1) 不会重复触发同一个归档任务  
2) 在处理中仍然能用“快照”降级运行，而不是读到半成品

