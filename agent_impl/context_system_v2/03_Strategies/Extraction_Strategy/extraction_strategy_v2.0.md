# 上下文提取策略（Extraction Strategy v2.0）

> 目的：定义每次模型调用前“从各层取什么、按什么顺序取、默认限制是什么”，让输入在有限 Token 预算内保持高信噪比。

代码对应：
- 提取流水线封装：`agent_impl/graph/extraction_strategy.py`（`ExtractionPipeline`）
- 具体提取实现：`agent_impl/graph/context_builder.py`（`extract_layer1/2/3` + 默认配置）

---

## 1. 核心理念：动态组装，信噪比最大化

系统不追求“全量记忆注入”，而是追求“当前最有用”：
- 越稳定、越关键的背景放在前面，几乎每轮都注入
- 越时效、越细节的内容按需、限量注入
- 低价值噪音永远不应进入长期注入区域

---

## 2. 提取流水线（ExtractionPipeline）

Pipeline 负责“组装流程与顺序”，具体每层怎么提取由回调函数注入：

- `extract_layer1(state)`：静态画像（3×3）
- `extract_layer2(state)`：工作上下文（报告/规划/指南/动态情报/历史摘要）
- `extract_layer3(state)`：文本化的 Layer 3 历史（摘要/任务笔记/最近对话）

> 模型调用时的 History（消息列表滑窗）由 Message Builder 负责，不在 Pipeline 的 `<dossier>` 中。

---

## 3. 默认提取配置（对齐代码常量）

### 3.1 Layer 1 默认配置

- `mode`: `"full"`（当前等价于全量输出）
- `max_tokens`: 15000（压缩模式预留，当前未启用真实裁剪）

### 3.2 Layer 2 默认配置（关键上限）

- `recent_summary_count`: 2（历史报告摘要的“中等摘要”数量）
- `max_one_liner_count`: 10（历史报告摘要的“一句话摘要”数量）
- `max_dynamic_intels`: 20（动态情报最大注入条数）
- 行动指南各状态上限：
  - `in_progress`: 2
  - `paused`: 2
  - `pending`: 3
  - `completed`: 5
  - `cancelled`: 2
  - `expired`: 2

### 3.3 Layer 3 默认配置（文本化历史）

- `max_recent_turns`: 25（按用户轮次计）
- `max_summary_count`: 5（历史摘要条数）
- `reasoning_limit`: 8（任务笔记条数）

---

## 4. 通用提取顺序（稳定性优先）

一次模型调用的整体顺序（与组装规范一致）：

1. Layer 0（SystemMessage）
2. Layer 1（画像）
3. Layer 2（报告/规划 → 动态情报 → 指南 → 历史摘要 → 任务）
4. History（滑窗对话）
5. Current Input

---

## 5. 价值过滤与按需加载

两条关键原则：

1) **长期注入区（Layer 1/2）必须高信噪比**  
价值过滤见：`value_filter_spec_v2.0.md`

2) **细节通过工具按需加载**  
例如行动指南正文：只展开少量进行中条目，其他条目通过 `context_loader` 拉取并绑定到任务上下文。

