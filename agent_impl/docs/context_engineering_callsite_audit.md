# 上下文工程调用链审计（v3.1）

> 目标：把“策略文档里承诺的触发点”与“代码真实调用点”逐条对齐，标出缺口与风险，并给出修复落点。\n+> 适用：`agent_impl/context_system/context_architecture.md`（v3.1）对应实现。

## 1) 总览：四条链路

| 链路 | 策略预期 | 关键代码模块 | 当前结论 |
| --- | --- | --- | --- |
| **存储（Sync Store）** | 每轮把交互流追加到 `layer3_memory.all_messages`（全量存储） | `graph/state.py::sync_new_messages_to_fullstore` | **缺口：函数存在但无调用点**（导致全量存储事实上没有建立） |
| **提取（Extraction）** | 各 Agent 通过提取策略从 L1/L2/L3 组装上下文 | `graph/context_builder.py` + `graph/extraction_strategy.py` | **OK：主/子 Agent 均使用 `build_context_dict`**（显式走 `ExtractionPipeline`） |
| **归档（Archiving）** | 对话压缩、旧报告/旧指南的摘要降级与历史维护 | `graph/archive_manager.py` | **部分 OK，部分缺口**：对话压缩在 server 路径会触发；reasoning 压缩/报告替换归档未接线或只写旧字段 |
| **提纯（Refining）** | Organize Agent 提取 L1 静态画像 + L2 动态情报 | `graph/nodes/organize_agent.py` | **重大缺口**：Onboarding 完成提纯入口存在但未被调用 |

## 2) 逐项审计：策略触发点 vs 实际调用点

### A. 交互信息流（用户消息 / AI 回复 / Tool 输出）

| 场景 | 策略预期触发点 | 应调用 | 应落字段（真源） | 当前实现 | 风险 |
| --- | --- | --- | --- | --- | --- |
| 每轮新增消息入库 | 回合结束（任何节点结束都应触发） | `sync_new_messages_to_fullstore(state)` | `layer3_memory.all_messages` | **未调用**；主要依赖 `state.messages`（还会被 router 修剪） | **高**：全量记忆缺失；压缩触发判断失真；Onboarding 提纯素材不全 |

### B. Onboarding 初始流程结束

| 场景 | 策略预期触发点 | 应调用 | 应落字段（真源） | 当前实现 | 风险 |
| --- | --- | --- | --- | --- | --- |
| Onboarding 完成提纯 | `onboarding_completed=True` 当轮结束 | `archive_manager.refine_on_onboarding_complete(state)` | `layer1_memory`、`layer2_memory.dynamic_intels`、可选 `layer3_memory.conversation_summaries` | **入口存在但完全未调用** | **高**：新用户画像不沉淀，后续 Agent “失忆” |

### C. 对话压缩（Layer3 Compression）

| 场景 | 策略预期触发点 | 应调用 | 应落字段（真源） | 当前实现 | 风险 |
| --- | --- | --- | --- | --- | --- |
| 对话超限压缩 | 达到阈值（按用户轮次） | `archive_manager.compress_layer3(state)` | `layer3_memory.conversation_summaries` + `layer1_memory` + `layer2_memory.dynamic_intels` | server 路径通过 `context_builder.check_and_compress_if_needed` 触发 | **中-高**：由于“全量存储未建立”，阈值与压缩范围可能偏离策略 |

### D. 任务思考过程压缩（Rolling Scratchpad）

| 场景 | 策略预期触发点 | 应调用 | 应落字段（真源） | 当前实现 | 风险 |
| --- | --- | --- | --- | --- | --- |
| reasoning 超限压缩 | 回合结束检查 | `archive_manager.process_archiving_if_needed(state)` 或 `compress_task_reasoning` | `layer3_memory.task_registry` | **缺口：主流程只调用了 `check_and_compress_if_needed`（仅对话压缩）** | **中**：长会话会膨胀；任务推理越来越重 |

### E. 报告（Status Report）生成与替换归档

| 场景 | 策略预期触发点 | 应调用 | 应落字段（真源） | 当前实现 | 风险 |
| --- | --- | --- | --- | --- | --- |
| 新报告写入 | Status Agent 产出报告当轮 | **写入 Layer2**（新增版本） | `layer2_memory.all_status_reports`（current 唯一） | 目前主要写旧字段 `status_report`（Markdown） | **高**：L2 真源缺失，历史/摘要机制无法闭环 |
| 旧报告归档摘要 | 生成新报告后立即 | `archive_manager.archive_status_to_layer2(old_report, state)`（摘要+提纯） | 更新旧 report 的 `summary/one_liner`，并更新 `layer1_memory` | **缺口：未找到触发点** | **高**：历史报告摘要缺失；L1 不会吸收“阶段判定”等结论 |

### F. 行动规划（Action Plan）生成与替换归档

| 场景 | 策略预期触发点 | 应调用 | 应落字段（真源） | 当前实现 | 风险 |
| --- | --- | --- | --- | --- | --- |
| 新规划写入 | Plan Agent 产出规划当轮 | **写入 Layer2**（新增版本） | `layer2_memory.all_action_plans`（current 唯一） | 目前主要写旧字段 `action_plan`（Markdown） | **高**：L2 真源缺失，后续提取策略对齐失败 |
| 旧规划归档摘要 | 生成新规划后立即 | （需要新增）`archive_plan_to_layer2(old_plan, state)` | 更新旧 plan 的 `summary/one_liner`，并更新 `layer1_memory` | **缺口：未实现/未接线** | **中-高**：历史规划不可用；提取策略无法做历史降级 |

### G. 行动指南（Action Guide）生成与完成归档

| 场景 | 策略预期触发点 | 应调用 | 应落字段（真源） | 当前实现 | 风险 |
| --- | --- | --- | --- | --- | --- |
| 新指南写入 | Guide Agent 产出指南当轮 | **写入 Layer2**（Append pending） | `layer2_memory.all_action_guides` | 目前写旧字段 `action_guides` 列表（dict），未同步进 Layer2 真源 | **中-高**：提取策略“未完成指南必选”无法完全对齐 |
| 指南完成归档/提纯 | 用户点击完成 / 主 Agent 检测完成 | `archive_manager.archive_guide_to_layer2(guide, state)` | `layer2_memory` + `layer1_memory` + `dynamic_intels` | 目前多走 `archive_guide_on_completion`，但上层合并只写 `history_archive/user_context`，**layer1/layer2 更新丢失** | **高**：你“以为归档了”，其实分层 memory 没更新 |

## 3) 结论：当前最关键的 3 个断点

1. **全量存储断点**：`sync_new_messages_to_fullstore` 无调用点（会让后续一切“基于全量消息”的策略失效）。\n+2. **Onboarding 提纯断点**：`refine_on_onboarding_complete` 未接线（直接复现你遇到的问题）。\n+3. **Layer2 真源断点**：Status/Plan/Guide 的产出与归档没有稳定写入 `layer2_memory`（历史/摘要/提取策略无法闭环）。

## 4) 修复原则（执行口径）

- **异步 best-effort**：LLM-heavy 的归档/提纯不阻塞用户回复，通过“回合结束入队 + 后台消费 + 写回 checkpointer”。\n+- **v3.1 memory 为真源**：`layer1_memory/layer2_memory/layer3_memory` 是真实存储；旧字段仅用于兼容展示。\n+- **必经 Finalizer**：任何回合结束都必须经过一个非 LLM 的 Finalizer，确保“全量落库 + 维护任务入队”不会漏。\n+

