# 提纯策略（Refining Strategy v2.0）

> 目的：把非结构化对话/报告/指南中的“高价值信息”提取出来，沉淀为结构化长期记忆（Layer 1/2），并生成摘要以控制无限增长。

代码对应：
- 整理 Agent：`agent_impl/graph/nodes/organize_agent.py`
- 归档管理器：`agent_impl/graph/archive_manager.py`

---

## 1. 提纯不是“总结”，而是“信息分流”

提纯回路要做三件事：

1. **抽取长期画像（Layer 1）**：3×3 情报矩阵（身份/性格/偏好/关系事实）
2. **抽取短期态势（Layer 2 Dynamic Intel）**：日程/情绪/状态/意向（带过期）
3. **生成摘要归档（Layer 2 history / Layer 3 summaries）**：控制无限增长

---

## 2. 触发时机（什么时候会提纯）

提纯通常由“归档/压缩事件”触发：

- **对话压缩**：当 Layer 3 对话超过阈值，需要把旧对话批量压缩  
  输入：即将被压缩的一段对话消息  
  产出：Layer 3 对话摘要 + Layer 1/2 抽取信息

- **报告被替换**：生成新版本现状报告时，旧报告进入历史  
  输入：旧报告正文  
  产出：旧报告 summary/one_liner + 可沉淀到 Layer 1 的稳定洞察

- **规划被替换**：生成新版本行动规划时，旧规划进入历史  
  输入：旧规划正文  
  产出：旧规划 summary/one_liner（通常不沉淀到 Layer 1，除非出现稳定画像信息）

- **指南进入终态**：completed/cancelled/expired  
  输入：指南正文 + 用户反馈（如有）  
  产出：指南 summary/one_liner + 可沉淀到 Layer 1 的事实/画像 + 可形成短期态势

---

## 3. 分流规则（写到哪里）

### 3.1 写入 Layer 1（长期画像）

满足“半年后仍有用”的信息（见 `value_filter_spec_v2.0.md`），写入：
- `user_info` / `crush_info` / `both_info`
并按来源归类：
- `fact` / `ai_provide` / `user_provide`

来源判断见：`../Extraction_Strategy/source_rules_spec_v2.0.md`

### 3.2 写入 Layer 2 Dynamic Intel（短期态势）

满足“短期决策关键，但会过期”的信息，写入动态情报：
- 必须给出 `expire_at`
- 必须给出 `confidence` 与 `confidence_reason`

### 3.3 写入摘要归档

摘要归档是“控制增长”的关键：
- Layer 3 对话摘要：topics + summary
- Layer 2 历史摘要：status_report_history / action_plan_history / 已完成指南摘要

摘要质量要求见：`../Compression_Strategy/summary_checklist_spec_v2.0.md`

---

## 4. 两个关键约束（决定系统是否会“越用越聪明”）

1. **价值过滤优先**：宁可少写，也不要把噪音写进 Layer 1。
2. **证据与结论拆分**：截图原话是 `fact`；推断是 `ai_provide`。不拆分会导致长期记忆不可追溯、不可纠错。

