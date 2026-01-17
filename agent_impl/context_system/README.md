# Context System 文档入口

> 目标：让新来的产品经理或研发 10-15 分钟内理解上下文工程全貌。

---

## 从这里开始

| 顺序 | 文档 | 内容 | 阅读时间 |
|:-----|:----|:----|:--------|
| **1** | `01_Overview/Quick_Start.md` | 入门科普：这个系统解决什么问题 | 5 分钟 |
| **2** | `01_Overview/System_Overview.md` | 全景图：信息怎么流转、各模块怎么协作 | 10 分钟 |

读完这两篇，你就能理解整个上下文工程的逻辑了。

---

## 深入阅读

### 权威规范（各层详细定义）

| 文档 | 内容 |
|:----|:----|
| `02_Specs/layer1_spec_v1.0.md` | Layer 1 静态情报：3×3 矩阵、原子记忆、写入规则 |
| `02_Specs/layer2_spec_v1.0.md` | Layer 2 工作上下文：报告、规划、指南、动态情报 |
| `02_Specs/layer3_spec_v1.0.md` | Layer 3 对话历史：消息处理、压缩、摘要 |
| `02_Specs/task_system_spec.md` | 任务系统：任务状态机、BoundContext |
| `02_Specs/context_assembly_spec.md` | 上下文组装：组装顺序、KV Cache 优化 |

### 策略文档（讲"怎么做"）

| 文档 | 内容 |
|:----|:----|
| `03_Strategies/Storage_Strategy/storage_strategy_v1.0.md` | 存储策略：信息写入哪一层 |
| `03_Strategies/Extraction_Strategy/extraction_strategy_v1.0.md` | 提取策略：从各层取什么 |
| `03_Strategies/Refining_Strategy/refining_strategy_v1.0.md` | 提纯策略：如何提取高价值信息 |
| `03_Strategies/Storage_Strategy/storage_schema_v1.0.md` | 数据结构：JSON Schema 定义 |

### 其他

| 文档 | 内容 |
|:----|:----|
| `04_Prompts/organize_agent_prompts.md` | Organize Agent 的 Prompt 模板 |
| `05_Discussion/Discussion_Archive.md` | 历史讨论与设计决策记录 |
| `99_Deprecated/` | 过时文档（仅供考古） |

---

## 按角色推荐阅读顺序

### 产品经理

1. `01_Overview/Quick_Start.md` — 入门
2. `01_Overview/System_Overview.md` — 全景
3. `02_Specs/layer2_spec_v1.0.md` — 重点看报告和指南
4. `02_Specs/task_system_spec.md` — 了解任务概念

### 研发

1. `01_Overview/Quick_Start.md` — 入门
2. `01_Overview/System_Overview.md` — 全景
3. `02_Specs/layer1_spec_v1.0.md` → `layer2_spec_v1.0.md` → `layer3_spec_v1.0.md` — 各层规范
4. `02_Specs/context_assembly_spec.md` — 组装逻辑
5. `03_Strategies/Storage_Strategy/storage_schema_v1.0.md` — 数据结构

---

*最后更新：2026-01-15*
