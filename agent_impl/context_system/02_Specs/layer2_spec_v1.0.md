# Layer 2 工作上下文 — 规范文档 v1.0

> **创建时间**: 2026-01-14  
> **状态**: 设计中  
> **目的**: 定义 Layer 2 的存储结构、写入逻辑、提取逻辑、输出格式

---

## 一、Layer 2 定位

**Layer 2 是 Agent 的「案头工作区」**，存放当前的"作战地图"和任务周期内的工作信息。

### 1.1 包含 4 类内容

| 类型 | 英文名 | 说明 | 特点 |
|:----|:------|:----|:----|
| 动态情报板 | DynamicIntel | 短期/时效性事实 | 有过期时间，永不删除 |
| 现状报告 | StatusReport | 关系诊断快照 | 覆盖式更新，归档历史 |
| 行动规划 | ActionPlan | 阶段性战略目标 | 低频更新，归档历史 |
| 行动指南 | ActionGuide | 具体行动任务 | 有状态机，渐进披露 |

### 1.2 Token 预算

- **总预算**: ~20,000 tokens
- 动态情报板: ~2,000 tokens
- 现状报告: ~5,000 tokens
- 行动规划: ~3,000 tokens
- 行动指南: ~10,000 tokens

---

## 二、动态情报板 (DynamicIntel)

### 2.1 定位

存放「短期/时效性事实」，是 Layer 1 长短期分流的下游。

### 2.2 存储结构

```python
DynamicIntelItem = TypedDict("DynamicIntelItem", {
    "id": str,                    # 唯一标识 (uuid[:8])
    "content": str,               # 情报内容
    "created_at": str,            # ISO 格式时间: "2026-01-13T14"
    "expire_at": str,             # ISO 格式过期时间: "2026-01-20T00"
    "subject": Literal["user", "crush"],  # 归属
    "category": str,              # 类型（不限制，LLM 自定义）
    "confidence": float,          # 置信度 (0.0-1.0)
    "confidence_reason": str,     # 置信度原因（必填）
    "source_type": Literal["conversation"],  # 来源类型
})
```

### 2.3 存储示例

```json
{
  "dynamic_intels": [
    {
      "id": "a1b2c3d4",
      "content": "下周三要去上海见 Crush",
      "created_at": "2026-01-14T10",
      "expire_at": "2026-01-22T00",
      "subject": "user",
      "category": "日程",
      "confidence": 0.95,
      "confidence_reason": "用户明确表述，非玩笑语境",
      "source_type": "conversation"
    },
    {
      "id": "e5f6g7h8",
      "content": "Crush 最近工作压力大，心情不太好",
      "created_at": "2026-01-13T15",
      "expire_at": "2026-01-20T00",
      "subject": "crush",
      "category": "情绪状态",
      "confidence": 0.70,
      "confidence_reason": "用户转述 Crush 的话，非直接证据",
      "source_type": "conversation"
    }
  ]
}
```

### 2.4 写入逻辑

#### 2.4.1 数据来源

只从「对话提取」环节写入，与 Layer 1 共享分流节点：
- **长期事实** → 写入 Layer 1
- **短期事实** → 写入 Layer 2 动态情报板

#### 2.4.2 去重/覆盖规则

- LLM 判断新情报与已有情报是否语义相同
- 语义相同 → 覆盖（更新 content、expire_at、confidence 等）
- 语义不同 → 新增

#### 2.4.3 过期时间规则（给整理 Agent）

```markdown
## 过期时间判断标准

### 日程类 (schedule)
- 有明确时间的事件 → 事件结束后 2 天
- 示例："下周三去上海" → expire_at = 下周五

### 情绪类 (mood)
- 一般情绪状态 → 3 天后
- 示例："Crush 最近心情不好" → expire_at = 3 天后

### 意向类 (intent)
- 模糊的想法/计划 → 30 天后
- 示例："Crush 说想学滑雪" → expire_at = 30 天后

### 临时状态类 (status)
- 当前状态描述 → 7 天后
- 示例："Crush 最近在加班" → expire_at = 7 天后

### 其他
- 根据内容判断，默认 14 天后
```

#### 2.4.4 置信度判断标准（给整理 Agent）

```markdown
## 置信度判断标准

### 高置信度 (0.8-1.0)
- 用户明确、认真地表述
- 有具体时间/地点/事件
- 非玩笑/调侃语境

### 中置信度 (0.5-0.8)
- 用户转述他人的话
- 用户的推测或猜想
- 语境不够明确

### 低置信度 (0.3-0.5)
- 在开玩笑/调侃的语境中说的
- 用户自己也不确定
- 可能是情绪化的表达

### 不记录 (< 0.3)
- 明显是玩笑话
- 与之前信息严重矛盾
- 用户明确表示"我瞎说的"

⚠️ 必须在 confidence_reason 中说明判断依据！
```

### 2.5 提取逻辑

```python
def get_active_dynamic_intels(
    dynamic_intels: list[DynamicIntelItem],
    max_count: int = 20,
) -> list[DynamicIntelItem]:
    """
    提取有效的动态情报
    
    1. 过滤：只取未过期的（expire_at > now）
    2. 排序：按过期时间升序（即将过期的在前）
    3. 截断：取 Top-N（N=20）
    """
    now = datetime.now()
    valid = [i for i in dynamic_intels if parse(i["expire_at"]) > now]
    valid.sort(key=lambda x: x["expire_at"])
    return valid[:max_count]
```

**注意**：存储永不删除，只在提取时过滤。

### 2.6 输出格式

```markdown
## 动态情报板
> 以下是近期的时效性信息，请务必参考。置信度说明：越高越可信。

### 用户
- [01-14 10:00] 下周三要去上海见 Crush (置信度: 0.95 - 用户明确表述)
- [01-12 20:00] 最近在准备年终总结 (置信度: 0.80 - 用户提及)

### Crush
- [01-13 15:00] 最近工作压力大，心情不太好 (置信度: 0.70 - 用户转述)
- [01-12 20:00] 说想学滑雪 (置信度: 0.50 - 聊天中随口提到)
```

**格式规则**：
- `[创建时间]` + `内容` + `(置信度: X.XX - 原因)`
- 按 `subject` 分组（用户/Crush）
- 组内按过期时间排序（即将过期的在前）
- 不显示过期时间

---

## 三、现状报告 (StatusReport)

### 3.1 定位

当前关系状态的分析快照，是 Agent 决策的核心依据。

### 3.2 存储结构

```python
StatusReportItem = TypedDict("StatusReportItem", {
    # 核心字段
    "report_id": str,              # 报告 ID (uuid[:8])
    "report_content": str,         # 报告正文（Markdown）
    "created_at": str,             # 创建时间 "2026-01-14T10"
    "version": int,                # 版本号（修改时+1）
    
    # 归档字段（由 Organize Agent 生成）
    "summary": Optional[str],      # 中等摘要（~100-200 字）
    "one_liner": Optional[str],    # 一句话摘要（~30 字）
    "archived_at": Optional[str],  # 归档时间
})

# Layer 2 Memory 中的存储
Layer2Memory = TypedDict("Layer2Memory", {
    "current_status_report": StatusReportItem,        # 当前报告
    "status_report_history": list[StatusReportItem],  # 历史报告（全量保留）
    # ...
})
```

### 3.3 写入逻辑

```
新报告生成
    │
    ▼
┌─────────────────────────────────────┐
│  Step 1: 判断是「修改」还是「新建」   │
│  → 修改：更新 content + version++   │
│  → 新建：进入 Step 2                │
└─────────────────────────────────────┘
    │ (新建)
    ▼
┌─────────────────────────────────────┐
│  Step 2: 归档旧报告                  │
│  → 将 current 移入 history          │
│  → 触发 Organize Agent 生成摘要     │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Step 3: 写入新报告                  │
│  → 设置新的 current_status_report   │
└─────────────────────────────────────┘
```

### 3.4 提取逻辑

```python
def extract_status_reports(layer2_memory: Layer2Memory) -> dict:
    """
    提取现状报告用于注入 Prompt
    
    返回：
    - current: 当前报告完整内容
    - history_summaries: 最近 2 份的 summary
    - history_one_liners: 再往前 3 份的 one_liner
    """
    current = layer2_memory["current_status_report"]
    history = layer2_memory["status_report_history"]
    
    history_sorted = sorted(history, key=lambda x: x["created_at"], reverse=True)
    
    recent_with_summary = [h for h in history_sorted[:2] if h.get("summary")]
    older_with_one_liner = [h for h in history_sorted[2:5] if h.get("one_liner")]
    
    return {
        "current": current,
        "history_summaries": recent_with_summary,
        "history_one_liners": older_with_one_liner,
    }
```

### 3.5 输出格式

```markdown
## 现状分析

### 当前报告
> 更新时间: 01-14 10:00 | 版本: 3

"""
{report_content}
"""

---

### 历史分析摘要

#### 近期报告
- **[01-12]** 用户与 Crush 关系处于好感期初期，双方互动频率稳定但缺乏深度话题。主要问题：用户追问过多导致 Crush 有压力感。建议放慢节奏，等待 Crush 主动。
- **[01-08]** 刚完成破冰阶段，Crush 对用户有基础好感。用户表现积极但略显急躁，需要建立更多共同话题。

#### 更早记录
- [01-05] 首次现状分析，关系处于认识初期
- [01-02] Onboarding 阶段信息收集
- [12-28] 初始报告生成
```

**注意**：报告正文用 `"""` 包围，避免内部 Markdown 层级与外层冲突。

---

## 四、行动规划 (ActionPlan)

### 4.1 定位

阶段性的战略规划，是 Guide Agent 生成具体指南的依据。

### 4.2 存储结构

```python
ActionPlanItem = TypedDict("ActionPlanItem", {
    # 核心字段
    "plan_id": str,                # 规划 ID (uuid[:8])
    "plan_content": str,           # 规划正文（Markdown）
    "created_at": str,             # 创建时间 "2026-01-14T10"
    "version": int,                # 版本号（修改时+1）
    
    # 归档字段（由 Organize Agent 生成）
    "summary": Optional[str],      # 中等摘要
    "one_liner": Optional[str],    # 一句话摘要
    "archived_at": Optional[str],  # 归档时间
})

# Layer 2 Memory 中的存储
Layer2Memory = TypedDict("Layer2Memory", {
    # ...
    "current_action_plan": ActionPlanItem,          # 当前规划
    "action_plan_history": list[ActionPlanItem],    # 历史规划（全量保留）
    # ...
})
```

### 4.3 写入逻辑

与现状报告一致：
- 修改不归档（更新 content + version++）
- 新建则归档（旧规划移入 history，触发 Organize Agent 生成摘要）

### 4.4 提取逻辑

与现状报告一致：
- 当前规划完整输出
- 最近 2 份历史的 summary
- 再往前 3 份的 one_liner

### 4.5 输出格式

```markdown
## 行动规划

### 当前规划
> 更新时间: 01-14 10:00 | 版本: 2

"""
{plan_content}
"""

---

### 历史规划摘要

#### 近期规划
- **[01-10]** 第一阶段目标：建立稳定聊天节奏，每周 3-4 次主动联系...
- **[01-05]** 初始规划：从破冰到建立好感...

#### 更早记录
- [01-02] 初始规划生成
```

---

## 五、行动指南 (ActionGuide)

### 5.1 定位

具体的行动任务，是 Agent 给用户的「可执行指令」。

### 5.2 状态机

```
Guide Agent 创建指南
         │
         ▼
  ┌─────────────┐
  │ in_progress │ ← 默认状态
  └──────┬──────┘
         │
    ┌────┴────┬──────────┬──────────┐
    │         │          │          │
 新指南进来  用户暂停   用户完成   超过expire_at
 需要搁置      │          │          │
    │         │          │          │
    ▼         ▼          ▼          ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ pending │ │ paused  │ │completed│ │ expired │
└────┬────┘ └────┬────┘ └─────────┘ └─────────┘
     │           │
     └─────┬─────┘
           │ Agent 判断可以继续
           ▼
    ┌─────────────┐
    │ in_progress │
    └─────────────┘
           │
           │ Agent 判断不再适用
           ▼
    ┌─────────────┐
    │  cancelled  │
    └─────────────┘
```

**状态说明**：

| 状态 | 说明 | 触发场景 |
|:----|:----|:--------|
| `in_progress` | **默认状态**，执行中 | 创建时 / 从 pending/paused 恢复 |
| `pending` | 搁置中，等待执行 | 新指南进来需要优先处理 / 时间调整 |
| `paused` | 用户主动暂停 | 用户说"先放一放" |
| `completed` | 已完成 | 用户反馈完成 |
| `cancelled` | 已取消 | Agent 判断不再适用 |
| `expired` | 已过期 | 系统自动（超过 expire_at） |

### 5.3 存储结构

```python
ActionGuideItem = TypedDict("ActionGuideItem", {
    # 核心字段
    "guide_id": str,               # 指南 ID (uuid[:8])
    "title": str,                  # 标题
    "status": Literal["pending", "in_progress", "paused", 
                      "completed", "cancelled", "expired"],
    "guide_content": str,          # 指南正文（Markdown）
    "created_at": str,             # 创建时间
    
    # 时间管理
    "expected_start_at": Optional[str],  # 预计开始时间（Agent 生成）
    "expire_at": Optional[str],          # 过期时间（Agent 生成）
    "completed_at": Optional[str],       # 完成时间（用户操作时记录）
    
    # 用户反馈（completed 时记录）
    "user_feedback": Optional[str],      # 用户的完成反馈
    
    # 归档字段（Organize Agent 生成）
    "summary": Optional[str],            # 中等摘要
    "one_liner": Optional[str],          # 一句话摘要
})

# Layer 2 Memory 中的存储
Layer2Memory = TypedDict("Layer2Memory", {
    # ...
    "action_guides": list[ActionGuideItem],  # 所有指南（全量保留）
})
```

### 5.4 状态管理规则（给 Guide Agent 的 Prompt）

```markdown
## 行动指南状态管理规则

### 创建指南时
- 默认 status = in_progress
- 设置 expire_at（根据任务类型，一般 7-14 天）
- 同时 in_progress 最多 2 个

### 何时改为 pending（搁置）
- 有新的更紧急指南需要优先执行
- 当前指南的时机不对，需要推迟
- 同时 in_progress 超过 2 个时，优先级较低的改为 pending
- 需要告知用户："这个指南我们先放一放，等 xxx 再继续"

### 何时改为 paused（暂停）
- 用户明确表示想暂停，如：
  - "这个先不做了"
  - "等等再说"
  - "最近没时间"
- 需要确认用户意图："好的，这个指南我们先暂停，等你准备好了告诉我"

### 何时改为 cancelled（取消）
- 指南不再适用的情况：
  - 情况发生变化，原计划已无意义
  - 用户明确表示不想做了
  - 关系阶段变化，策略需要调整
- 需要向用户解释原因："这个指南我们取消吧，因为 xxx"

### 何时改为 completed（完成）
- 用户反馈执行结果，如：
  - "我做了，她回复了..."
  - "约到了！"
  - "聊完了，感觉还不错"
- 需要记录用户反馈到 user_feedback 字段
- 触发 Organize Agent 生成摘要并提取 Layer 1 信息

### 从 pending/paused 恢复为 in_progress
- 根据与用户的交互判断时机合适
- 用户主动提起相关话题
- 之前的阻碍因素已消除

### 自动过期 (expired)
- 系统检测到 in_progress 指南超过 expire_at
- 自动设置 status = expired
- 在对话中告知用户："之前的 xxx 指南已经过期了，要不要重新制定？"

### ⚠️ 关键原则
1. 状态转换基于与用户的实际交互判断
2. 每次状态变更都要在对话中告知用户
3. 不要让指南长期停留在某个状态不处理
4. 主动在对话中询问进度、确认状态
5. pending 最多 3 个，超过需要取消优先级最低的
```

### 5.5 写入逻辑

#### 5.5.1 创建新指南

```
Guide Agent 创建指南
    │
    ▼
设置初始状态 = in_progress
设置 expire_at（过期时间）
    │
    ▼
写入 action_guides 列表
```

#### 5.5.2 用户完成指南（重要流程）

```
用户标记完成
    │
    ▼
┌─────────────────────────────────────┐
│  Step 1: 记录完成信息                │
│  → status = completed               │
│  → completed_at = now               │
│  → user_feedback = 用户的反馈内容    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Step 2: 触发 Organize Agent        │
│  → 生成 summary（重点包含用户反馈）  │
│  → 提取用户反馈中的高价值信息        │
│  → 分流写入 Layer 1 / 动态情报板    │
└─────────────────────────────────────┘
```

### 5.6 提取逻辑

**注入 Prompt 时的限制**：

| 状态 | 注入数量 | 展示详细程度 |
|:----|:--------|:-----------|
| `in_progress` | 最多 2 个 | 完整展开 `guide_content` |
| `paused` | 最多 2 个 | 展示 `summary` |
| `pending` | 最多 3 个 | 展示 `summary` |
| `completed` | 最多 5 个 | 展示 `summary`（重点：用户反馈） |
| `cancelled` | 最多 2 个 | 展示 `one_liner` |
| `expired` | 最多 2 个 | 展示 `one_liner` |

**后端存储**：全量保留，不删除。

```python
def extract_action_guides(layer2_memory: Layer2Memory) -> dict:
    """提取行动指南用于注入 Prompt"""
    guides = layer2_memory["action_guides"]
    
    by_status = {
        "in_progress": [], "paused": [], "pending": [],
        "completed": [], "cancelled": [], "expired": [],
    }
    
    for g in guides:
        by_status[g["status"]].append(g)
    
    return {
        "in_progress": sorted(by_status["in_progress"], 
                              key=lambda x: x["created_at"], reverse=True)[:2],
        "paused": sorted(by_status["paused"], 
                         key=lambda x: x["created_at"], reverse=True)[:2],
        "pending": sorted(by_status["pending"], 
                          key=lambda x: x.get("expected_start_at", ""))[:3],
        "completed": sorted(by_status["completed"], 
                            key=lambda x: x.get("completed_at", ""), reverse=True)[:5],
        "cancelled": sorted(by_status["cancelled"], 
                            key=lambda x: x["created_at"], reverse=True)[:2],
        "expired": sorted(by_status["expired"], 
                          key=lambda x: x.get("expire_at", ""), reverse=True)[:2],
    }
```

### 5.7 输出格式

```markdown
## 行动指南

### 🔥 进行中 (2)

#### 【abc123】破冰话题准备
> 创建: 01-14 10:00 | 预计过期: 01-21

"""
{guide_content}
"""

---

#### 【def456】约饭计划制定
> 创建: 01-13 15:00 | 预计过期: 01-20

"""
{guide_content}
"""

---

### ⏸️ 已暂停 (1)

#### 【ghi789】深度话题储备
> 创建: 01-12 10:00

**摘要**: 准备了 3 个深度话题（童年回忆、未来规划、价值观），用户反馈暂时用不上，先暂停。

---

### 📋 待执行 (2)

#### 【jkl012】周末邀约
> 预计开始: 01-16

**摘要**: 计划在周四邀请 Crush 周末一起看电影，需要先铺垫...

#### 【mno345】朋友圈互动
> 预计开始: 01-17

**摘要**: 关注 Crush 朋友圈动态，适时点赞评论...

---

### ✅ 已完成 (3)

#### 【pqr678】首次破冰对话
> 完成于: 01-13 20:00

**执行摘要**: 用户按照建议发送了破冰消息，Crush 回复积极。
**用户反馈**: "她回复了！说周末有空，感觉有戏"
**关键收获**: Crush 对约会持开放态度，周末可能有空。

#### 【stu901】了解兴趣爱好
> 完成于: 01-11 15:00

**执行摘要**: 通过聊天了解到 Crush 喜欢看综艺、喝咖啡。
**用户反馈**: "聊得挺开心的，她说最近在追《花儿与少年》"
**关键收获**: Crush 喜欢综艺节目，可以作为话题切入点。

#### 【vwx234】建立聊天节奏
> 完成于: 01-09 18:00

**执行摘要**: 建立了每天 1-2 次的聊天频率。
**用户反馈**: "感觉频率刚好，她也会主动找我聊"
**关键收获**: 当前聊天频率合适，Crush 会主动发起对话。

---

### 📁 其他记录

| 状态 | 标题 | 简述 |
|:----|:----|:----|
| ❌ 已取消 | 送礼物计划 | 时机不成熟，暂缓 |
| ⏰ 已过期 | 节日祝福 | 错过了元旦时机 |
```

### 5.8 归档摘要生成（给 Organize Agent）

```markdown
## 任务：为已完成指南生成摘要

请为以下行动指南生成摘要：

### 原指南内容
{guide_content}

### 用户反馈
{user_feedback}

### 要求

#### summary（中等摘要）
必须包含三个部分：
1. **执行摘要**: 用户做了什么，结果如何（1-2句）
2. **用户反馈**: 用户的原话或关键反馈（1句）
3. **关键收获**: 从这次行动中得到的重要信息（1句）

#### one_liner（一句话摘要）
- 格式："{核心结果}"

#### layer1_extractions（提取到 Layer 1 的信息）
从用户反馈中提取可以写入 Layer 1 的高价值信息，如：
- Crush 的新特征/偏好
- 关系进展的客观事实
- 用户的新发现

### 输出格式
{
  "summary": "**执行摘要**: ... **用户反馈**: ... **关键收获**: ...",
  "one_liner": "...",
  "layer1_extractions": [
    {"target": "crush_info", "source": "fact", "content": "..."},
    {"target": "both_info", "source": "fact", "content": "..."}
  ]
}
```

---

## 六、Layer 2 完整存储结构

```python
Layer2Memory = TypedDict("Layer2Memory", {
    # 动态情报板
    "dynamic_intels": list[DynamicIntelItem],
    
    # 现状报告
    "current_status_report": Optional[StatusReportItem],
    "status_report_history": list[StatusReportItem],
    
    # 行动规划
    "current_action_plan": Optional[ActionPlanItem],
    "action_plan_history": list[ActionPlanItem],
    
    # 行动指南
    "action_guides": list[ActionGuideItem],
    
    # 元信息
    "last_updated": str,
    "version": int,
})
```

---

## 七、待实现功能

### 7.1 高优先级 (P0)
- [ ] 实现 `DynamicIntelItem` 数据结构
- [ ] 实现动态情报板的写入/提取逻辑
- [ ] 实现行动指南的状态机管理
- [ ] 实现 `"""` 包围的报告输出格式

### 7.2 中优先级 (P1)
- [ ] 实现 Organize Agent 的归档摘要生成
- [ ] 实现用户完成指南时的 Layer 1 信息提取
- [ ] 实现自动过期检测（expire_at）

### 7.3 低优先级 (P2)
- [ ] 历史报告/规划的 summary 压缩优化
- [ ] 动态情报板的任务相关性过滤

---

## 八、变更记录

| 版本 | 日期 | 变更内容 |
|:----|:----|:--------|
| v1.0 | 2026-01-14 | 初始版本，定义 4 类内容的存储/写入/提取/输出规范 |

---

*文档维护者: AI 产品经理 & AI 助手*

