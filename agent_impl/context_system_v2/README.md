# Context System 2.0（权威文档）

> 目标：让第一次接触本项目的产品经理或研发在 10–15 分钟内建立“上下文系统”的完整心智模型，并能按需深入查阅规范与策略。

本目录文档以**当前代码实现与测试契约**为准，面向“第一次了解系统”的读者，采用从 0 解释的叙事方式。

---

## 从这里开始（推荐阅读顺序）

| 顺序 | 文档 | 你将学到什么 | 时间 |
|:---:|:---|:---|:---:|
| 1 | `01_Overview/Quick_Start.md` | 这个系统解决什么问题、四层结构、一个完整例子 | 5–10 分钟 |
| 2 | `01_Overview/System_Overview.md` | 信息生命周期、核心模块协作、端到端数据流 | 10–15 分钟 |

---

## 深入阅读（权威规范 Specs）

> 如果你要写代码或排查线上问题，优先读这一组。

| 文档 | 内容 |
|:---|:---|
| `02_Specs/message_stack_spec_v2.0.md` | 标准消息栈：SystemMessage → Context XML → Virtual Ack → History → Current Input |
| `02_Specs/message_input_spec_v2.0.md` | Context XML（`<dossier>`）结构、字段含义、最小输入规则 |
| `02_Specs/context_assembly_spec_v2.0.md` | 组装顺序、KV Cache 原理、Token 预算与裁剪原则 |
| `02_Specs/layer1_spec_v2.0.md` | Layer 1（3×3 情报矩阵、AtomicMemory、信任优先级、输出格式） |
| `02_Specs/layer2_spec_v2.0.md` | Layer 2（现状报告/行动规划/行动指南/动态情报，状态机与渐进式披露） |
| `02_Specs/layer3_spec_v2.0.md` | Layer 3（历史摘要/任务笔记/最近对话，窗口限制与格式） |
| `02_Specs/task_system_spec_v2.0.md` | 任务系统（Task Index/Active Task/Bound Contexts/context_loader） |

---

## 策略文档（讲“怎么运作”与“为什么这样设计”）

| 文档 | 内容 |
|:---|:---|
| `03_Strategies/Storage_Strategy/storage_strategy_v2.0.md` | 信息写入哪一层：同步落库与异步提纯 |
| `03_Strategies/Storage_Strategy/storage_schema_v2.0.md` | 数据结构总览：AgentState/各层 Memory 的人类可读 Schema |
| `03_Strategies/Extraction_Strategy/extraction_strategy_v2.0.md` | 每次回复前从各层取什么、默认配置与限制 |
| `03_Strategies/Refining_Strategy/refining_strategy_v2.0.md` | Organize Agent 如何提取高价值信息、如何沉淀到 L1/L2 |
| `03_Strategies/Compression_Strategy/compression_strategy_v2.0.md` | 对话/报告/规划/指南/推理的压缩与归档触发 |
| `03_Strategies/Extraction_Strategy/source_rules_spec_v2.0.md` | 来源判断：user_provide/fact/ai_provide 的边界与置信度建议 |
| `03_Strategies/Extraction_Strategy/value_filter_spec_v2.0.md` | 价值过滤：什么值得写入长期记忆、什么必须过滤 |
| `03_Strategies/Compression_Strategy/summary_checklist_spec_v2.0.md` | 各类摘要的质量标准与检查清单 |

---

## Prompts 与讨论材料

| 文档 | 内容 |
|:---|:---|
| `04_Prompts/organize_agent_prompts.md` | Organize Agent 的 Prompt 模板（人类可读与占位符说明） |
| `05_Discussion/Discussion_Archive.md` | 面向新人的“设计取舍解释”：为什么要分层、为什么要 Virtual Ack、为什么要渐进式披露等 |

---

## 维护者参考（不建议新人从这里开始）

| 文档 | 内容 |
|:---|:---|
| `06_Reference/code_mapping.md` | 1.0 → 2.0：章节覆盖映射、代码/测试对应表（用于防遗漏与后续维护） |

