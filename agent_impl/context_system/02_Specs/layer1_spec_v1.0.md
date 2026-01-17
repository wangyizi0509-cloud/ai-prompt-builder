# Layer 1 静态情报区 — 规范文档 v1.0

> **创建时间**: 2026-01-14  
> **状态**: 设计中  
> **目的**: 定义 Layer 1 的存储结构、写入逻辑、提取逻辑、输出格式

---

## 一、Layer 1 定位

**Layer 1 是 Agent 的「大脑长期记忆」**，存储关于用户、Crush、双方关系的静态情报。

### 1.1 信息分类：3×3 情报矩阵

| 归属 ↓ \ 来源 → | 用户提供 (user_provide) | 客观事实 (fact) | AI分析 (ai_provide) |
|:---------------|:----------------------|:---------------|:-------------------|
| **用户信息** (user_info) | 用户自述的个人信息 | 用户朋友圈、照片等 | AI推断的依恋类型等 |
| **Crush信息** (crush_info) | 用户描述的Crush | 聊天记录截图 | AI推断的性格特征 |
| **双方信息** (both_info) | 用户描述的相处情况 | 互动记录 | AI推断的关系阶段 |

### 1.2 信任优先级

当信息冲突时，按以下优先级判断：

```
🥇 最高可信 — 客观事实 (fact)
   聊天记录、截图内容、时间戳等直接证据。这是真理。

🥈 中等可信 — AI分析 (ai_provide)  
   基于证据的推断。如无新证据反驳，保持沿用。

🥉 最低可信 — 用户提供 (user_provide)
   用户可能美化自己或误读对方。需用客观事实修正。
```

---

## 二、存储结构

### 2.1 原子记忆 (AtomicMemory)

每条信息以「原子记忆」形式存储，不做字符串拼接。

```python
AtomicMemory = TypedDict("AtomicMemory", {
    "id": str,                    # 唯一标识 (uuid[:8])
    "content": str,               # 内容（最小语义单元）
    "created_at": str,            # ISO 格式时间（精确到小时）: "2026-01-13T14"
    "source_type": Literal[       # 来源类型
        "onboarding",             # Onboarding 阶段收集
        "conversation",           # 日常对话中提取
        "report",                 # 报告生成时提取
    ],
    "confidence": float,          # 置信度 (0.0-1.0)，AI分析必填，其他可选
    "confidence_reason": str,     # 置信度原因，AI分析必填
}, total=False)
```

### 2.2 原子记忆粒度规则

不同来源类型使用不同的粒度策略：

| 来源类型 | 粒度策略 | 示例（每条独立存储） |
|:--------|:--------|:-------------------|
| **用户提供** | 按属性拆分（一个属性一条） | `"姓名：小明"` `"年龄：26"` `"职业：程序员"` |
| **客观事实** | 按事件拆分（一个事件/证据一条） | `"Crush 说周末要加班"` `"上周一起吃了晚饭"` |
| **AI分析** | 按结论拆分（一个推断一条） | `"依恋类型：焦虑型"` `"关系阶段：暧昧期"` |

### 2.3 完整存储结构

```python
# 信息来源（v2.0）
InfoSourceV2 = TypedDict("InfoSourceV2", {
    "user_provide": list[AtomicMemory],  # 用户提供的原子记忆列表
    "fact": list[AtomicMemory],          # 客观事实列表
    "ai_provide": list[AtomicMemory],    # AI分析列表
})

# Crush 信息（额外有 crush_name）
CrushInfoV2 = TypedDict("CrushInfoV2", {
    "crush_name": str,                   # Crush 名称或昵称
    "user_provide": list[AtomicMemory],
    "fact": list[AtomicMemory],
    "ai_provide": list[AtomicMemory],
})

# 3×3 矩阵（v2.0）
UserContextV2 = TypedDict("UserContextV2", {
    "user_info": InfoSourceV2,
    "crush_info": CrushInfoV2,
    "both_info": InfoSourceV2,
})

# Layer 1 Memory（v2.0）
Layer1MemoryV2 = TypedDict("Layer1MemoryV2", {
    "full_data": UserContextV2,
    "extraction_config": Layer1ExtractionConfig,
    "processing_status": Optional[ProcessingStatus],
    "last_updated": str,
    "update_count": int,
    "version": int,
})
```

### 2.4 存储示例（JSON）

```json
{
  "full_data": {
    "user_info": {
      "user_provide": [
        {"id": "a1b2c3", "content": "姓名：小明", "created_at": "2026-01-10T10", "source_type": "onboarding"},
        {"id": "d4e5f6", "content": "年龄：26", "created_at": "2026-01-10T10", "source_type": "onboarding"},
        {"id": "g7h8i9", "content": "职业：程序员", "created_at": "2026-01-10T10", "source_type": "onboarding"},
        {"id": "h1i2j3", "content": "性格：内向", "created_at": "2026-01-10T10", "source_type": "onboarding"}
      ],
      "fact": [
        {"id": "j1k2l3", "content": "朋友圈发了健身照", "created_at": "2026-01-10T14", "source_type": "conversation"}
      ],
      "ai_provide": [
        {"id": "m4n5o6", "content": "依恋类型：焦虑型", "created_at": "2026-01-12T09", "source_type": "report", "confidence": 0.85, "confidence_reason": "基于用户描述的追问行为和焦虑表现推断"}
      ]
    },
    "crush_info": {
      "crush_name": "小红",
      "user_provide": [
        {"id": "p1q2r3", "content": "年龄：25", "created_at": "2026-01-10T10", "source_type": "onboarding"},
        {"id": "s4t5u6", "content": "职业：设计师", "created_at": "2026-01-10T10", "source_type": "onboarding"}
      ],
      "fact": [
        {"id": "v7w8x9", "content": "说周末要加班", "created_at": "2026-01-12T15", "source_type": "conversation"}
      ],
      "ai_provide": [
        {"id": "y1z2a3", "content": "沟通风格：直接型", "created_at": "2026-01-12T09", "source_type": "report", "confidence": 0.80, "confidence_reason": "基于聊天记录中 Crush 的表达方式分析"}
      ]
    },
    "both_info": {
      "user_provide": [
        {"id": "b4c5d6", "content": "认识方式：朋友介绍", "created_at": "2026-01-10T10", "source_type": "onboarding"},
        {"id": "e7f8g9", "content": "认识时间：2个月", "created_at": "2026-01-10T10", "source_type": "onboarding"}
      ],
      "fact": [
        {"id": "h1i2j3", "content": "上周一起吃了晚饭", "created_at": "2026-01-12T20", "source_type": "conversation"}
      ],
      "ai_provide": [
        {"id": "k4l5m6", "content": "关系阶段：暧昧期", "created_at": "2026-01-12T09", "source_type": "report", "confidence": 0.90, "confidence_reason": "基于双方互动频率和内容深度判断"}
      ]
    }
  },
  "extraction_config": {
    "mode": "full",
    "max_tokens": 15000
  },
  "last_updated": "2026-01-13T14:30:00",
  "update_count": 5,
  "version": 3
}
```

---

## 三、写入逻辑

### 3.1 写入触发点

| 触发时机 | 触发函数 | 说明 |
|:--------|:---------|:----|
| Onboarding 完成时 | `refine_on_onboarding_complete()` | 从 Onboarding 对话中提取用户/Crush 基本信息 |
| 对话压缩时 | `compress_layer3()` | 从被压缩的对话中提取高价值信息 |
| 报告被摘要时 | `archive_status_to_layer2()` 等 | 从报告中提取新的分析结论 |

### 3.2 写入规则（核心）

#### 3.2.1 去重规则：LLM 语义判断

写入前，调用 LLM 判断新信息是否与已有信息语义重复：

```
Prompt 示例:
---
判断以下两条信息是否表达相同的含义：
- 已有信息：「职业：程序员」
- 新信息：「用户是一名软件工程师」

如果语义相同，返回 "duplicate"；否则返回 "new"。
---
```

- 返回 `duplicate` → 不写入
- 返回 `new` → 执行写入

#### 3.2.2 用户提供 (user_provide)：覆盖

当用户提供的**同一属性**有新值时，**直接覆盖**旧值：

```
示例：
- 旧：「年龄：26」
- 新：「年龄：28」
- 结果：删除旧的，写入新的
```

**"同一属性"的判断**：由 LLM 判断两条信息是否描述同一属性。

#### 3.2.3 客观事实 (fact)：全量追加 + 长短期分流

客观事实**不覆盖，全量追加**。

⚠️ **关键设计：长短期分流**

写入时需要 LLM 判断这条事实是**长期事实**还是**短期/动态事实**：

| 类型 | 定义 | 示例 | 写入目标 |
|:----|:----|:----|:--------|
| **长期事实** | 长时间有效的客观信息 | `"Crush 是独生女"` `"用户有健身习惯"` | **Layer 1** |
| **短期事实** | 近期发生的、有时效性的信息 | `"下周三要去上海"` `"最近在加班"` | **Layer 2 动态情报板** |

```
LLM Prompt 示例:
---
判断以下信息是「长期事实」还是「短期事实」：

信息：「Crush 说下周要出差」

- 长期事实：长时间有效，不会很快过期（如性格、习惯、背景）
- 短期事实：近期发生的、有时效性的（如近期计划、当前状态）

返回 "long_term" 或 "short_term"。
---
```

- 返回 `long_term` → 写入 Layer 1 的 `fact`
- 返回 `short_term` → 写入 Layer 2 的 `dynamic_intels`

#### 3.2.4 AI 分析 (ai_provide)：同类覆盖

当 AI 产生新的分析结论时，**覆盖同一分析维度**的旧结论：

```
示例：
- 旧：「依恋类型：焦虑型」
- 新：「依恋类型：安全型」
- 结果：删除旧的，写入新的（同属"依恋类型"维度）
```

**"同一分析维度"的判断**：由 LLM 判断两条分析是否属于同一维度。

⚠️ **不应写入 Layer 1 的 AI 分析**

以下分析维度**不写入 Layer 1**（因为会在 Layer 2 现状报告中常驻，避免重复）：

| 不写入的维度 | 原因 |
|:-----------|:----|
| 关系阶段（L1-L4/T1-T3） | 在现状报告中常驻 |
| ACR 三维分析 | 在现状报告中常驻 |
| 核心问题/风险点 | 在现状报告中常驻 |

**应该写入 Layer 1 的 AI 分析**：

| 写入的维度 | 示例 |
|:---------|:----|
| 依恋类型 | `依恋类型：焦虑型` |
| 性格特征 | `性格：内向、敏感` |
| 沟通风格 | `沟通风格：直接型` |
| 兴趣偏好 | `兴趣：喜欢看综艺、咖啡` |

### 3.3 写入流程图

```
新信息输入
    │
    ▼
┌─────────────────────────────────────┐
│  Step 1: LLM 判断信息类型            │
│  → user_provide / fact / ai_provide │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Step 2: LLM 去重检查                │
│  → 与已有信息语义对比                │
│  → 重复则跳过                        │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Step 3: 按类型执行写入策略          │
│                                      │
│  user_provide → 覆盖同属性           │
│  fact → 长短期分流                   │
│  ai_provide → 覆盖同维度 + 排除列表  │
└─────────────────────────────────────┘
    │
    ▼
写入完成
```

### 3.4 写入入口

```python
# 统一写入接口
async def save_atomic_memory(
    layer1_memory: Layer1MemoryV2,
    layer2_memory: Layer2MemoryV2,  # 用于短期事实分流
    target: Literal["user_info", "crush_info", "both_info"],
    source: Literal["user_provide", "fact", "ai_provide"],
    content: str,
    source_type: str,
    confidence: float = None,
) -> tuple[Layer1MemoryV2, Layer2MemoryV2]:
    """
    写入一条原子记忆
    
    1. LLM 去重检查
    2. 按类型执行写入策略
    3. 返回更新后的 Layer1 和 Layer2
    """
    ...
```

---

## 四、提取逻辑

### 4.1 提取入口

```python
def extract_layer1(state: AgentState) -> str:
    """从 Layer 1 长期记忆中提取静态情报，组装为 Prompt 文本"""
    ...
```

### 4.2 提取策略

| 模式 | 说明 | 状态 |
|:----|:----|:----|
| `full` | 全量输出所有原子记忆 | ✅ 当前使用 |
| `compressed` | 按相关性筛选 Top-K | ⏳ 未来规划 |

### 4.3 排序规则

1. **按时间倒序**：最新的信息在上面
2. **同时间按来源优先级**：事实 > AI > 用户

---

## 五、输出格式

### 5.1 格式规范

采用**紧凑列表格式**，每条原子记忆独立一行，不做合并。

```
[日期时间/来源标记] 内容
```

### 5.2 时间显示规则

- **存储精度**：年-月-日-时（如 `2026-01-13T14`）
- **输出精度**：
  - 默认省略年份：`01-13 14:00`
  - 跨年数据显示年份：`2025-12-30 10:00`

### 5.3 来源标记

| 来源类型 | 标记 | 可靠性说明 |
|:--------|:----|:---------|
| 用户提供 | `用户` | 可靠性最低，用户可能美化或误读 |
| 客观事实 | `事实` | 可靠性最高，直接证据 |
| AI分析 | `AI` | 可靠性中等，基于证据推断 |

### 5.4 输出模板

```markdown
## 情报概览
> 信息可靠性：事实 > AI分析 > 用户提供。当信息冲突时，以高可靠性信息为准。

### 用户
- [01-12 09:00/AI] 依恋类型：焦虑型
- [01-10 14:00/事实] 朋友圈发了健身照
- [01-10 10:00/用户] 姓名：小明
- [01-10 10:00/用户] 年龄：26
- [01-10 10:00/用户] 职业：程序员
- [01-10 10:00/用户] 性格：内向

### Crush（小红）
- [01-12 15:00/事实] 说周末要加班
- [01-12 09:00/AI] 沟通风格：直接型
- [01-10 10:00/用户] 年龄：25
- [01-10 10:00/用户] 职业：设计师

### 双方关系
- [01-12 20:00/事实] 上周一起吃了晚饭
- [01-12 09:00/AI] 关系阶段：暧昧期
- [01-10 10:00/用户] 认识方式：朋友介绍
- [01-10 10:00/用户] 认识时间：2个月
```

### 5.5 Token 预算

- **当前估算**：典型用户 ~200-400 tokens
- **上限**：15,000 tokens（与 extraction_config.max_tokens 对齐）

---

## 六、待实现功能

### 6.1 高优先级 (P0)
- [ ] 实现 `AtomicMemory` 数据结构
- [ ] 实现 `save_atomic_memory()` 写入函数
- [ ] 实现新的 `_build_layer1_static_intel_v2()` 输出函数
- [ ] 迁移现有数据到新结构

### 6.2 中优先级 (P1)
- [ ] 实现 LLM 语义去重判断
- [ ] 实现 LLM 同属性/同维度判断
- [ ] 实现 LLM 长短期事实分流判断
- [ ] 定义 AI 分析排除列表（不写入 Layer 1 的维度）

### 6.3 低优先级 (P2)
- [ ] 实现 `compressed` 模式（按相关性召回 Top-K）
- [ ] 引入向量检索支持

---

## 七、变更记录

| 版本 | 日期 | 变更内容 |
|:----|:----|:--------|
| v1.0 | 2026-01-14 | 初始版本，定义存储结构、写入逻辑、输出格式 |

---

*文档维护者: AI 产品经理 & AI 助手*

