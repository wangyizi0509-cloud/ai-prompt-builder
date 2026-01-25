# 章节覆盖映射（1.0 → 2.0）

> 目的：保证 **2.0 不遗漏 1.0 的任何“有效主题”**，并把每个主题与**当前代码实现**与**测试契约**对齐，方便维护者定位。

说明：
- 2.0 文档面向新人阅读；本页面向维护者自检。
- `99_Deprecated/` 为历史材料：2.0 **不收录**，避免干扰新人；其有效内容应已被 1.0 的 Overview/Specs/Strategies 吸收，本表不再逐条覆盖。

---

## 总体入口

| 1.0 路径 | 2.0 路径 | 代码对应 | 测试/校验 |
|:---|:---|:---|:---|
| `context_system/README.md` | `context_system_v2/README.md` | - | - |

---

## 01_Overview

| 1.0 路径 | 2.0 路径 | 代码对应（理解用） | 测试/校验（契约用） |
|:---|:---|:---|:---|
| `01_Overview/Quick_Start.md` | `01_Overview/Quick_Start.md` | `graph/context_builder.py`, `graph/message_builder.py` | `tests/test_context_spec_validation.py` |
| `01_Overview/System_Overview.md` | `01_Overview/System_Overview.md` | `graph/context_builder.py`, `graph/message_builder.py`, `graph/nodes/organize_agent.py` | `tests/test_context_spec_validation.py` |

---

## 02_Specs（权威规范）

| 1.0 路径 | 2.0 路径 | 代码对应（权威） | 测试/校验（硬契约） |
|:---|:---|:---|:---|
| `02_Specs/context_assembly_spec.md` | `02_Specs/context_assembly_spec_v2.0.md` | `graph/context_builder.py`（`TOKEN_BUDGET`、`build_context_dict`） | `tests/test_context_spec_validation.py`, `tests/test_output_format_integration.py` |
| `02_Specs/message_input_spec_v1.0.md` | `02_Specs/message_input_spec_v2.0.md` | `graph/message_builder.py`（`build_context_xml`） | `tests/test_output_format_integration.py`（字段存在与类型） |
| （散落于 1.0 与 `agent_impl/docs/plan_消息结构标准化.md`） | `02_Specs/message_stack_spec_v2.0.md` | `graph/message_builder.py`（消息栈、过滤规则） | `tests/test_output_format_integration.py`（整体流程一致性） |
| `02_Specs/layer1_spec_v1.0.md` | `02_Specs/layer1_spec_v2.0.md` | `graph/context_types.py`（`AtomicMemory`, `UserContext`, `Layer1Memory`）+ `graph/context_builder.py:extract_layer1` | `tests/test_context_spec_validation.py`（格式头、时间戳、Crush 名称等） |
| `02_Specs/layer2_spec_v1.0.md` | `02_Specs/layer2_spec_v2.0.md` | `graph/context_types.py`（Layer2 类型）+ `graph/context_builder.py:extract_layer2` + `graph/tools/context_loader.py` | `tests/test_context_spec_validation.py`（三引号、渐进式披露、过滤过期等） |
| `02_Specs/layer3_spec_v1.0.md` | `02_Specs/layer3_spec_v2.0.md` | `graph/context_types.py`（Layer3 类型）+ `graph/context_builder.py:extract_layer3` + `graph/message_builder.py:build_conversation_history` | `tests/test_context_spec_validation.py`（历史摘要/任务笔记/对话结构） |
| `02_Specs/task_system_spec.md` | `02_Specs/task_system_spec_v2.0.md` | `graph/tools/task_tools.py`（Task Index/Active Task）+ `graph/tools/context_loader.py`（Bound Context 绑定） | `tests/test_task_system.py`, `tests/test_task_bound_action_guides.py` |

---

## 03_Strategies（策略）

| 1.0 路径 | 2.0 路径 | 代码对应（权威） | 说明 |
|:---|:---|:---|:---|
| `03_Strategies/Storage_Strategy/storage_strategy_v1.0.md` | `03_Strategies/Storage_Strategy/storage_strategy_v2.0.md` | `graph/storage_strategy.py`, `graph/nodes/organize_agent.py` | 以“同步落库 + 异步提纯”叙事解释全链路 |
| `03_Strategies/Storage_Strategy/storage_schema_v1.0.md` | `03_Strategies/Storage_Strategy/storage_schema_v2.0.md` | `graph/context_types.py`, `graph/state.py` | 2.0 提供“人类可读 Schema 总览”，用于理解 AgentState/各层 Memory 的关系；更细输出格式仍以 `02_Specs/` 为准 |
| `03_Strategies/Extraction_Strategy/extraction_strategy_v1.0.md` | `03_Strategies/Extraction_Strategy/extraction_strategy_v2.0.md` | `graph/extraction_strategy.py`, `graph/context_builder.py` | 以 Pipeline + 默认配置解释“每次回复前取什么” |
| `03_Strategies/Extraction_Strategy/source_rules_spec.md` | `03_Strategies/Extraction_Strategy/source_rules_spec_v2.0.md` | `graph/context_types.py`（信任层级/字段）+ `graph/nodes/organize_agent.py`（抽取写入） | 对齐 Organize Prompt 的来源边界 |
| `03_Strategies/Extraction_Strategy/value_filter_spec.md` | `03_Strategies/Extraction_Strategy/value_filter_spec_v2.0.md` | `graph/nodes/organize_agent.py` + `context_system/04_Prompts/organize_agent_prompts.md`（运行时模板） | 明确“半年后仍有用吗”的过滤原则 |
| `03_Strategies/Refining_Strategy/refining_strategy_v1.0.md` | `03_Strategies/Refining_Strategy/refining_strategy_v2.0.md` | `graph/nodes/organize_agent.py` | 抽取（L1/L2）+ 归档（L2 history/L3 summary）的完整流程 |
| `03_Strategies/Compression_Strategy/compression_strategy_v1.0.md` | `03_Strategies/Compression_Strategy/compression_strategy_v2.0.md` | `graph/archive_manager.py`, `graph/nodes/organize_agent.py` | 压缩触发矩阵与摘要规范 |
| `03_Strategies/Compression_Strategy/summary_checklist_spec.md` | `03_Strategies/Compression_Strategy/summary_checklist_spec_v2.0.md` | `graph/nodes/organize_agent.py`（模板输出 JSON） | 摘要质量一致性 |
| `03_Strategies/Compression_Strategy/organize_agent_prompts.md` | `04_Prompts/organize_agent_prompts.md` | `graph/nodes/organize_agent.py`（读取模板块） | 2.0 将 Prompt 放回 Prompts 模块统一维护 |

---

## 04_Prompts

| 1.0 路径 | 2.0 路径 | 代码对应 | 说明 |
|:---|:---|:---|:---|
| `04_Prompts/organize_agent_prompts.md` | `04_Prompts/organize_agent_prompts.md` | `graph/nodes/organize_agent.py`（从文件读取 `<!-- TEMPLATE: xxx -->` 块） | 2.0 供新人理解；运行时读取路径以代码为准 |

---

## 05_Discussion

| 1.0 路径 | 2.0 路径 | 说明 |
|:---|:---|:---|
| `05_Discussion/Discussion_Archive.md` | `05_Discussion/Discussion_Archive.md` | 2.0 将其改写为“新人友好解释”，只保留仍然成立的设计取舍与误区澄清 |

