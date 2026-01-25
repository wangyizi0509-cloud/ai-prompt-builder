# Layer 1 静态情报区规范（v2.0）

> 目的：定义 Layer 1 的数据结构与输出格式。Layer 1 是“长期画像与事实档案”，用来让模型稳定理解用户、Crush 与双方关系。

代码对应：
- 类型：`agent_impl/graph/context_types.py`（`AtomicMemory`, `UserContext`, `Layer1Memory`）
- 输出：`agent_impl/graph/context_builder.py`（`extract_layer1()`）

---

## 1. Layer 1 定位

Layer 1 存储 **长期有效** 的信息（半年后依然有用），主要是：
- 用户画像（身份、性格、偏好、边界、行为模式）
- Crush 画像（同上）
- 双方关系背景（认识方式、里程碑事件、互动模式、关键态度）

不适合放在 Layer 1 的内容（通常放到 Layer 2 报告/规划中）：
- 当前关系阶段、ACR 分析、当下核心问题（这些会随任务推进频繁变化）

---

## 2. 信息分类：3×3 情报矩阵

| 归属 ↓ \\ 来源 → | 用户提供 `user_provide` | 客观事实 `fact` | AI 分析 `ai_provide` |
|:---|:---|:---|:---|
| 用户 `user_info` | 用户自述属性/感受 | 可观察证据（截图/行为） | 基于证据的推断结论 |
| Crush `crush_info` | 用户描述/转述 | 聊天截图/客观行为 | 基于证据的推断结论 |
| 双方 `both_info` | 用户描述关系 | 互动记录/约定 | 关系动态推断 |

---

## 3. 信任优先级（冲突处理）

当信息冲突时，优先级为：

```text
事实（fact） > AI 分析（ai_provide） > 用户提供（user_provide）
```

原因：
- `fact`：直接证据或可观察行为，最不易失真
- `ai_provide`：推断结论，可能随新证据修正
- `user_provide`：主观口述，最容易夹杂误读或滤镜

---

## 4. 数据结构：AtomicMemory（原子记忆）

Layer 1 以“原子记忆”存储，不做字符串拼接。

字段（代码定义）：
- `id`: `str`（短 ID，如 `uuid[:8]`）
- `content`: `str`（最小语义单元）
- `created_at`: `str`（ISO 格式到小时：`YYYY-MM-DDTHH`，例如 `2026-01-13T14`）
- `source_type`: `"onboarding" | "conversation" | "report"`
- `confidence`: `float`（AI 分析必填，0.0–1.0）
- `confidence_reason`: `str`（AI 分析必填）

> 注：输出到模型时，`confidence/confidence_reason` 不直接出现在 Layer 1 列表里（Layer 1 输出强调“事实/AI/用户”的来源标签与时间戳）；置信度更常用于动态情报（Layer 2）。

---

## 5. 输出格式（对齐测试契约）

### 5.1 顶部固定头（必须存在）

```markdown
## 情报概览
> 信息可靠性：事实 > AI分析 > 用户提供。当信息冲突时，以高可靠性信息为准。
```

### 5.2 分区（按主体）

输出最多包含 3 个主体分区：
- `### 用户`
- `### Crush（{crush_name}）`（如果有 `crush_name`）
- `### 双方关系`

### 5.3 原子记忆行格式（紧凑列表）

每条原子记忆一行，格式如下：

```text
- [MM-DD HH:mm/事实] ...
- [MM-DD HH:mm/AI] ...
- [MM-DD HH:mm/用户] ...
```

时间戳规则：
- 存储时间为 ISO（到小时），展示时格式化为 `MM-DD HH:mm`
- 若跨年，则展示为 `YYYY-MM-DD HH:mm`

排序规则（代码实现）：
- 按时间倒序（新 → 旧）
- 同一时间按来源优先级（事实 → AI → 用户）

### 5.4 空内容处理（允许，但不要破坏结构）

当 Layer 1 缺少足够信息时，允许只输出固定头，或输出一句提示文本（例如“暂无详细信息，需要进一步了解。”）。

---

## 6. 常见坑

1. **`created_at` 格式不规范**：必须是 ISO `YYYY-MM-DDTHH`，否则展示时间可能为空。
2. **Crush 名称缺失**：如果已知 Crush 昵称，应放在 `crush_info.crush_name`，输出标题会变为 `### Crush（昵称）`。
3. **把低价值噪音写进 Layer 1**：长期记忆一旦被噪音污染，会持续消耗 Token 并干扰判断；价值过滤见 `../03_Strategies/Extraction_Strategy/value_filter_spec_v2.0.md`。

