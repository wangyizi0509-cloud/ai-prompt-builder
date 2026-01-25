# 上下文组装规范（Context Assembly Spec v2.0）

> 目的：定义“每次模型调用前如何组装上下文”的顺序、预算与裁剪原则，使其稳定、可缓存、可控。

实现位置：`agent_impl/graph/context_builder.py`（预算与提取）+ `agent_impl/graph/message_builder.py`（消息栈组装）

---

## 1. 设计目标

### 1.1 KV Cache 命中率

**原则**：越稳定越靠前。

稳定性排序（高 → 低）：

```text
Layer 0（规则） > Layer 1（画像） > Layer 2（工作上下文） > History（滑窗对话） > Current Input
```

### 1.2 指令遵循

- SystemMessage 放最前：规则与输出格式最稳定、最关键
- 档案（`<dossier>`）在 History 前：让模型先“掌握背景”，再“进入语境”
- 当前输入最后：保证回复针对本轮问题

---

## 2. 默认 Token 预算（以代码常量为准）

当前默认预算定义在 `agent_impl/graph/context_builder.py`：

| 模块 | 默认预算 | 说明 |
|:---|---:|:---|
| total | 62,000 | 总预算（安全边际） |
| output_reserve | 8,000 | 预留给模型输出 |
| layer0_system | 4,000 | 系统指令区（SystemMessage） |
| layer1_static | 15,000 | Layer 1 静态画像（3×3） |
| layer2_working | 20,000 | Layer 2 工作上下文（报告/规划/指南/动态情报/历史摘要） |
| layer3_conversation | 15,000 | 对话历史（长期抽取的 Layer 3 文本，用于特定场景；模型调用的 History 窗口另计） |

> 说明：模型调用时的 History（滑动窗口）由 `message_builder.py` 单独控制（默认 10 轮），不在 `<dossier>` 内。

---

## 3. 组装顺序（消息栈层面）

一次模型调用的“最终结构”见 `02_Specs/message_stack_spec_v2.0.md`。这里强调各区域顺序背后的稳定性逻辑：

1. **SystemMessage（Layer 0）**：规则与输出格式
2. **HumanMessage（`<dossier>`）**：稳定背景（L1/L2/Task）
3. **AIMessage（Virtual Ack）**：固定隔离句
4. **History（滑动窗口）**：最近对话与工具消息
5. **Current Input**：用户本轮输入

---

## 4. `<dossier>` 内部顺序（字段层面）

`<dossier>` 的内部顺序以“稳定性与决策优先级”为主，实际注入顺序如下：

1. `user_context`（Layer 1）
2. `status_report`（Layer 2.a）
3. `action_plan`（Layer 2.a）
4. `action_guides`（Layer 2.b）
5. `dynamic_intel`（Layer 2.b，可选）
6. `history_summaries`（Layer 2.b，可选）
7. `task_context`（Task Index + Active Task）
8. `bound_contexts`（可选）
9. `instruction`（可选）

详细 XML 结构见 `02_Specs/message_input_spec_v2.0.md`。

---

## 5. 裁剪与降级原则（当内容过长时怎么办）

系统的裁剪思路是“保决策关键，砍低价值冗余”：

- **Layer 1**：以紧凑列表输出；信息粒度以 AtomicMemory 为单位（便于去重与排序）。
- **Layer 2**：
  - 报告/规划：保留“当前版本完整正文”，历史以 summary/one_liner 递减（见 Layer2 规范）。
  - 指南：渐进式披露（只展开少量进行中指南，其它只注入表格索引与摘要）。
  - 动态情报：过滤过期，仅取 Top-N（默认 20）。
- **History**：滑动窗口（默认 10 个用户轮次），并过滤掉 Context Injection 与 Virtual Ack。

