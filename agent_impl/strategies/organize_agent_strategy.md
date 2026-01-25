# 整理 Agent (Organize Agent) 策略定义文档

> **文档状态**：Draft v1.0
> **最后更新**：2026-01-19
> **适用范围**：Crushe 产品产研团队
> **文档目的**：明确定义系统后台处理模块 Organize Agent 的定位、分类规则与执行逻辑。

---

## 1. 核心定位 (Core Identity)

### 1.1 后台整理员 (The Archivist)

Organize Agent 是系统的**后台信息整理员**，负责在信息从"热"变"冷"的关键时刻进行处理。
它不直接与用户对话，而是**静默运行**，将高价值信息沉淀到长期记忆，将短期信息归档到动态情报板。

**关键认知**：Agent 的记忆质量 = 信息的正确分类 × 信息的及时沉淀。
*   如果信息分类错误（把用户说的当成 AI 分析的），会导致后续决策偏差。
*   如果信息没有及时沉淀，随着对话压缩，宝贵的用户画像就会丢失。

### 1.2 两大职责

| 职责 | 说明 | 输出目标 |
|:----|:----|:--------|
| **提取沉淀** | 从内容中提取高价值信息，写入长期记忆 | Layer 1（3×3 矩阵） |
| **压缩归档** | 将过期内容生成摘要，释放上下文空间 | Layer 2（历史摘要）、Layer 3（对话摘要） |

### 1.3 与业务 Agent 的分工

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          业务 Agent（前台）                              │
│        Main / Status / Plan / Guide / Onboarding                        │
│                                                                         │
│   职责：与用户对话、做出决策、生成报告/指南                               │
│   写入：Layer 2 主体内容（报告、规划、指南）                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
                         （触发归档/压缩时）
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                       Organize Agent（后台）                             │
│                                                                         │
│   职责：从已完成的内容中提取信息、生成摘要                                │
│   写入：Layer 1（长期记忆）、Layer 2 动态情报板、历史摘要                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 触发时机 (Trigger Points)

Organize Agent 不是持续运行的，而是在特定事件触发时被调用。

| 触发事件 | 输入内容 | 处理逻辑 | 输出 |
|:--------|:--------|:--------|:----|
| **对话压缩** | 被压缩的消息列表 | 提取长期信息 + 动态情报 + 生成摘要 | Layer 1 更新、Layer 2 动态情报、Layer 3 对话摘要 |
| **现状报告归档** | 被替换的旧报告 | 提取长期信息 + 动态情报 + 生成摘要 | Layer 1 更新、Layer 2 动态情报、历史摘要 |
| **行动规划归档** | 被替换的旧规划 | 提取长期信息 + 生成摘要 | Layer 1 更新、历史摘要 |
| **行动指南完成** | 已完成的指南 | 提取长期信息 + 生成摘要 | Layer 1 更新、历史摘要 |
| **Onboarding 完成** | Onboarding 对话 | 提取用户/Crush 画像 | Layer 1 初始化 |

---

## 3. 信息分类模型：3×3 矩阵 (Classification Model)

### 3.1 双维度分类

Organize Agent 的核心任务是将信息正确分类到 **3×3 矩阵** 中：

```
             ┌─────────────┬─────────────┬─────────────┐
             │ user_provide│    fact     │ ai_provide  │
             │  (用户说的)  │ (有证据的)  │ (AI分析的)  │
┌────────────┼─────────────┼─────────────┼─────────────┤
│ user_info  │ 用户自述的  │ 用户的客观  │ AI 对用户   │
│ (关于用户) │ 个人信息    │ 行为证据    │ 的分析推断  │
├────────────┼─────────────┼─────────────┼─────────────┤
│ crush_info │ 用户描述的  │ Crush 在聊  │ AI 对 Crush │
│ (关于Crush)│ Crush       │ 天中说的话  │ 的分析推断  │
├────────────┼─────────────┼─────────────┼─────────────┤
│ both_info  │ 用户描述的  │ 互动的客观  │ AI 对关系   │
│ (关于关系) │ 两人关系    │ 证据        │ 的分析推断  │
└────────────┴─────────────┴─────────────┴─────────────┘
```

### 3.2 归属维度：关于谁？

| 维度 | 包含内容 |
|:----|:--------|
| **user_info** | 基本身份（姓名、年龄、职业）、性格特点、情感历史、兴趣爱好、核心问题模式 |
| **crush_info** | 基本身份、性格特点、兴趣爱好、关系状态、沟通风格、态度表现 |
| **both_info** | 认识背景、时间跨度、互动模式、里程碑事件、当前阻力 |

### 3.3 来源维度：谁说的/怎么来的？

| 来源 | 判断关键 | 信任度 |
|:----|:--------|:------|
| **user_provide** | 说话主体是**用户**，用户直接陈述/回答的 | 🥉 最低（用户可能美化或误读） |
| **fact** | 有**直接证据**支撑，聊天记录中 Crush 说的话、可观察的行为 | 🥇 最高（直接证据） |
| **ai_provide** | 说话主体是 **AI（小话）**，AI 的分析判断和推断 | 🥈 中等（基于证据推断） |

---

## 4. 来源判断规则 (Source Classification Rules)

### 4.1 user_provide — 用户说的

**判断关键**：说话的主体是**用户**。

| 场景 | 示例 | 分类 |
|:----|:----|:----|
| 用户介绍自己 | "我叫小明，26岁，程序员" | user_info.user_provide |
| 用户描述 Crush | "她25岁，是设计师" | crush_info.user_provide |
| 用户说 Crush 喜欢什么 | "她喜欢喝咖啡" | crush_info.user_provide |
| 用户描述互动情况 | "我们上周一起吃了饭" | both_info.user_provide |
| 用户说自己的感受 | "我觉得她对我冷淡了" | both_info.user_provide |
| 用户说自己的问题 | "我太容易紧张" | user_info.user_provide |

**⚠️ 注意**：用户说的不一定是事实！
*   用户说"她喜欢我" → 这是用户的**判断**，不是客观事实
*   用户说"她喜欢咖啡" → 这是用户观察到的，但不是 Crush 亲口说的

### 4.2 fact — 有证据的

**判断关键**：有**直接证据**支撑，主要来自聊天记录、截图。

| 场景 | 示例 | 分类 |
|:----|:----|:----|
| Crush 在聊天中说的话 | 聊天记录显示 Crush 说"我周末要加班" | crush_info.fact |
| Crush 透露的个人信息 | Crush 在聊天中说"我有男朋友" | crush_info.fact |
| Crush 表达的态度 | Crush 回复说"你挺好的，但我们不合适" | both_info.fact |
| 可观察的回复行为 | 用户发了消息，Crush 已读不回24小时 | both_info.fact |
| 互动的客观数据 | 用户主动发了10条，Crush 只回了3条 | both_info.fact |

**📝 书写规则**：fact 必须注明来源！
*   ✅ 正确："Crush 在聊天中表示自己有男朋友"
*   ✅ 正确："Crush 说周末要加班"
*   ❌ 错误："Crush 有男朋友"（缺少来源说明）

**为什么？** 因为"Crush 说的"≠"一定是真的"。保留来源信息，让后续决策能正确判断。

### 4.3 ai_provide — AI 分析的

**判断关键**：说话主体是 **AI（小话）**。

| 场景 | 示例 | 分类 |
|:----|:----|:----|
| AI 的性格分析 | "你属于焦虑型依恋" | user_info.ai_provide |
| AI 对 Crush 的推断 | "Crush 可能是回避型依恋" | crush_info.ai_provide |
| AI 对行为的分析 | "你的需求感过强" | user_info.ai_provide |
| AI 对态度的分析 | "Crush 对你态度偏冷淡" | crush_info.ai_provide |
| AI 的风格分析 | "Crush 沟通风格偏直接" | crush_info.ai_provide |

---

## 5. 长短期分流 (Long-term vs Short-term)

### 5.1 分流逻辑

不是所有信息都应该写入 Layer 1。Organize Agent 需要判断信息是长期有效还是短期有效：

```
信息输入
    │
    ├── 长期有效？
    │   ├── ✅ 是 → 写入 Layer 1（3×3 矩阵）
    │   │         例：身份、性格、背景、稳定特征
    │   │
    │   └── ❌ 否 → 写入 Layer 2（动态情报板）
    │             例：日程、情绪、临时状态、意向
```

### 5.2 长期信息 → Layer 1

| 类型 | 示例 | 存储位置 |
|:----|:----|:--------|
| 身份信息 | "她是设计师"、"他26岁" | Layer 1 对应格子 |
| 性格特点 | "性格内向"、"沟通风格直接" | Layer 1 对应格子 |
| 稳定偏好 | "喜欢喝咖啡"、"爱看综艺" | Layer 1 对应格子 |
| 关系背景 | "同事关系"、"认识两个月" | Layer 1 both_info |
| AI 分析结论 | "焦虑型依恋"、"需求感过强" | Layer 1 对应格子 |

### 5.3 短期信息 → Layer 2 动态情报板

| 类型 | category | 默认有效期 | 示例 |
|:----|:---------|:---------|:----|
| 日程安排 | schedule | 2天（事件结束后） | "下周三要去上海出差" |
| 情绪状态 | mood | 3天 | "最近心情不太好" |
| 临时状态 | status | 7天 | "这两天在加班" |
| 意向想法 | intent | 14天 | "想约她看电影" |

### 5.4 不写入 Layer 1 的信息

| 类型 | 原因 |
|:----|:----|
| 关系阶段（L1-L4/T1-T3） | 在 Layer 2 现状报告中常驻 |
| ACR 三维分析 | 在 Layer 2 现状报告中常驻 |
| 核心问题/风险点 | 在 Layer 2 现状报告中常驻 |

---

## 6. 判断流程 (Decision Flow)

### 6.1 完整判断流程

```
收到一条信息
    │
    ├── Step 1: 谁说的？
    │   ├── 用户说的 ─────────────────→ 可能是 user_provide
    │   ├── Crush 在聊天记录中说的 ──→ fact
    │   └── AI（小话）说的 ──────────→ ai_provide
    │
    ├── Step 2: 关于谁？
    │   ├── 关于用户自己 ─────────────→ user_info
    │   ├── 关于 Crush ───────────────→ crush_info
    │   └── 关于两人关系 ─────────────→ both_info
    │
    └── Step 3: 是否长期有效？
        ├── ✅ 长期有效 ──────────────→ 写入 Layer 1
        └── ❌ 短期有效 ──────────────→ 写入 Layer 2 动态情报板
```

### 6.2 示例

| 原始信息 | Step 1 | Step 2 | Step 3 | 最终归属 |
|:--------|:-------|:-------|:-------|:--------|
| 用户说"我是程序员" | 用户说的 | 关于用户 | 长期 | user_info.user_provide |
| 用户说"她喜欢咖啡" | 用户说的 | 关于 Crush | 长期 | crush_info.user_provide |
| Crush 在聊天中说"我有男朋友" | Crush 说的 | 关于 Crush | 长期 | crush_info.fact |
| AI 分析"你需求感过强" | AI 说的 | 关于用户 | 长期 | user_info.ai_provide |
| 用户说"她下周要出差" | 用户说的 | 关于 Crush | **短期** | Layer 2 (schedule, crush) |
| 用户说"她最近心情不好" | 用户说的 | 关于 Crush | **短期** | Layer 2 (mood, crush) |

---

## 7. 输出格式规范 (Output Format)

### 7.1 Layer 1 写入格式：AtomicMemory

每条信息以**原子记忆**形式存储：

```python
AtomicMemory = {
    "id": "a1b2c3d4",              # 唯一标识
    "content": "职业：程序员",      # 内容（最小语义单元）
    "created_at": "2026-01-19T14",  # 创建时间
    "source_type": "conversation",  # 来源类型
    "confidence": 0.8,              # 置信度（ai_provide 必填）
    "confidence_reason": "...",     # 置信度原因（ai_provide 必填）
}
```

### 7.2 动态情报写入格式：DynamicIntelItem

```python
DynamicIntelItem = {
    "id": "e5f6g7h8",
    "content": "下周三要去上海见 Crush",
    "created_at": "2026-01-19T14",
    "expire_at": "2026-01-22T00",   # 过期时间
    "subject": "user",              # 归属：user/crush
    "category": "schedule",         # 类型
    "confidence": 0.95,
    "confidence_reason": "用户明确表述",
}
```

---

## 8. 核心边界 (Boundaries)

### ✅ 应该做的

*   ✅ **正确分类**：根据"谁说的"和"关于谁"准确分类到 3×3 矩阵
*   ✅ **注明来源**：fact 类信息必须注明来源（如"Crush 在聊天中说..."）
*   ✅ **长短分流**：将短期信息写入 Layer 2 动态情报板，不要污染 Layer 1
*   ✅ **原子化存储**：一个属性/事实/结论一条，不要合并多条信息

### ❌ 不应该做的

*   ❌ **不要把用户说的当成事实**：用户说"她喜欢我"是用户的判断，不是 fact
*   ❌ **不要把 AI 分析当成用户说的**：AI 诊断"焦虑型依恋"是 ai_provide，不是 user_provide
*   ❌ **不要写入已常驻的信息**：关系阶段、ACR 分析、核心问题已在报告中常驻，不要重复写入 Layer 1
*   ❌ **不要丢失来源信息**：写 fact 时必须保留"Crush 说的"这个关键上下文

---

## 9. 代码入口 (Code Entry Points)

| 函数 | 位置 | 说明 |
|:----|:----|:----|
| `organize_and_archive()` | `graph/nodes/organize_agent.py` | 主入口，根据 content_type 分发 |
| `merge_extracted_info_to_context()` | `graph/nodes/organize_agent.py` | 合并提取的信息到 Layer 1 |
| `extract_dynamic_intel_from_text()` | `graph/nodes/organize_agent.py` | 提取动态情报到 Layer 2 |
| `archive_conversation_batch()` | `graph/nodes/organize_agent.py` | 对话压缩入口 |
| `archive_replaced_status_report()` | `graph/nodes/organize_agent.py` | 现状报告归档入口 |
| `archive_completed_guide()` | `graph/nodes/organize_agent.py` | 行动指南归档入口 |

---

## 10. Prompt 模板 (Prompt Templates)

所有 Prompt 模板统一存放在 `context_system/04_Prompts/organize_agent_prompts.md`。

| 模板名 | 用途 |
|:------|:----|
| `conversation` | 对话压缩：生成摘要 + 提取 Layer 1 信息 |
| `status_report` | 现状报告归档：生成摘要 + 提取 Layer 1 信息 |
| `action_plan` | 行动规划归档：生成摘要 + 提取 Layer 1 信息 |
| `action_guide` | 行动指南归档：生成摘要 + 提取 Layer 1 信息 |
| `dynamic_intel` | 动态情报提取：提取短期信息到 Layer 2 |
| `task_reasoning` | 任务思考压缩：生成任务摘要 |

---

## 附录：信息分类速查表

| 信息示例 | 归属 | 来源 | 去向 |
|:--------|:----|:----|:----|
| "我叫小明" | user_info | user_provide | Layer 1 |
| "我是程序员" | user_info | user_provide | Layer 1 |
| "我比较内向" | user_info | user_provide | Layer 1 |
| "她25岁" | crush_info | user_provide | Layer 1 |
| "她喜欢咖啡" | crush_info | user_provide | Layer 1 |
| "我们认识两个月了" | both_info | user_provide | Layer 1 |
| Crush 在聊天中说"我有男朋友" | crush_info | fact | Layer 1 |
| Crush 在聊天中说"周末要加班" | crush_info | fact | Layer 1 |
| 用户消息已读不回24小时 | both_info | fact | Layer 1 |
| AI 判断"你属于焦虑型依恋" | user_info | ai_provide | Layer 1 |
| AI 判断"Crush 回避型依恋" | crush_info | ai_provide | Layer 1 |
| AI 判断"你需求感过强" | user_info | ai_provide | Layer 1 |
| "她下周要出差" | — | — | **Layer 2** (schedule, crush) |
| "她最近心情不好" | — | — | **Layer 2** (mood, crush) |
| "我打算周六约她看电影" | — | — | **Layer 2** (intent, user) |
| "他这几天在加班" | — | — | **Layer 2** (status, crush) |
