# 存储层数据结构定义 (Storage Schema) v1.0

> **适用版本**：v1.0 (2025-12-30)
> **代码对应**：`graph/context_types.py`, `graph/state_storage.py`

本文档定义了上下文工程中各层长期记忆的**完整数据结构**，包括字段定义、类型规范和示例数据。

---

## 目录

1. [整体架构](#1-整体架构)
2. [Layer 1: 静态情报 (Static Intelligence)](#2-layer-1-静态情报)
3. [Layer 2: 工作上下文 (Working Context)](#3-layer-2-工作上下文)
4. [Layer 3: 对话历史 (Conversation History)](#4-layer-3-对话历史)
5. [辅助结构](#5-辅助结构)
6. [持久化存储格式](#6-持久化存储格式)

---

## 1. 整体架构

### 1.1 AgentState 顶层结构

```json
{
  "user_message": "string",
  
  "layer1_memory": { /* Layer1Memory */ },
  "layer2_memory": { /* Layer2Memory */ },
  "layer3_memory": { /* Layer3Memory */ },
  
  "messages": [ /* Message[] */ ],
  "crush_chat_storage": { /* CrushChatStorage */ },
  "report_counter": { /* ReportCounter */ },
  
  "intent_type": "consult_only | emotion_vent | action_trigger | info_update | off_topic",
  "next_action": "ask_user | call_status | call_plan | call_guide | end_turn",
  
  "should_continue": true,
  "route_to": "string"
}
```

---

## 2. Layer 1: 静态情报

### 2.1 Layer1Memory 结构

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `full_data` | `UserContext` | ✅ | 3×3 情报矩阵全量数据 |
| `extraction_config` | `Layer1ExtractionConfig` | ✅ | 提取策略配置 |
| `processing_status` | `ProcessingStatus` | ❌ | 并发处理状态（处理中时有值） |
| `last_updated` | `string (ISO 8601)` | ✅ | 最后更新时间 |
| `update_count` | `int` | ✅ | 累计更新次数 |
| `version` | `int` | ✅ | 数据版本号（每次更新递增） |

### 2.2 UserContext (3×3 情报矩阵)

```json
{
  "user_info": {
    "user_provide": "用户口述的自我描述（如：我比较内向，不太会聊天）",
    "fact": "客观事实（如：朋友圈显示喜欢健身，有一只猫）",
    "ai_provide": "AI分析结论（如：依恋类型偏焦虑，执行力中等）"
  },
  "crush_info": {
    "crush_name": "小雅",
    "user_provide": "用户描述的Crush（如：她是我同事，性格比较安静）",
    "fact": "聊天记录/截图提取（如：回复速度快，喜欢用表情包）",
    "ai_provide": "AI推断（如：性格类型INFJ，回避型依恋倾向）"
  },
  "both_info": {
    "user_provide": "用户描述的相处情况（如：认识3个月，经常一起吃午饭）",
    "fact": "互动记录/证据（如：上周末一起看了电影）",
    "ai_provide": "AI推断（如：当前关系阶段L2，互动频率中等偏高）"
  }
}
```

### 2.3 InfoSource 字段

| 字段 | 类型 | 必填 | 说明 | 信任优先级 |
|------|------|------|------|-----------|
| `user_provide` | `string` | ❌ | 用户口述信息 | 🟡 最低 |
| `fact` | `string` | ❌ | 客观事实（截图/记录） | 🟢 最高 |
| `ai_provide` | `string` | ❌ | AI分析结论 | 🔵 中等 |

### 2.4 Layer1ExtractionConfig

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `mode` | `"full" \| "compressed"` | ❌ | `"full"` | 提取模式 |
| `max_tokens` | `int` | ❌ | `15000` | 压缩模式下的 token 上限 |

### 2.5 完整 Layer1Memory 示例

```json
{
  "full_data": {
    "user_info": {
      "user_provide": "28岁，程序员，平时比较内向",
      "fact": "朋友圈显示喜欢打篮球和弹吉他",
      "ai_provide": "依恋类型：安全型偏焦虑；执行力：中等"
    },
    "crush_info": {
      "crush_name": "小雅",
      "user_provide": "同公司产品经理，比我小2岁",
      "fact": "聊天记录显示她回复速度快，喜欢分享日常",
      "ai_provide": "性格外向，回避型依恋倾向不明显"
    },
    "both_info": {
      "user_provide": "认识3个月，经常一起吃午饭",
      "fact": "上周一起看了电影，她主动分享了家人的事",
      "ai_provide": "当前阶段：L2（有好感）；互动频率：高"
    }
  },
  "extraction_config": {
    "mode": "full",
    "max_tokens": 15000
  },
  "processing_status": null,
  "last_updated": "2025-12-30T10:30:00.000Z",
  "update_count": 15,
  "version": 5
}
```

---

## 3. Layer 2: 工作上下文

### 3.1 Layer2Memory 结构

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `all_status_reports` | `StatusReportItem[]` | ✅ | 所有现状分析报告（含历史） |
| `all_action_plans` | `ActionPlanItem[]` | ✅ | 所有行动规划（含历史） |
| `all_action_guides` | `ActionGuideItem[]` | ✅ | 所有行动指南（含已完成） |
| `dynamic_intels` | `DynamicIntelItem[]` | ✅ | 动态情报板（时效性信息）⚠️ **待实现** |
| `extraction_config` | `Layer2ExtractionConfig` | ✅ | 提取策略配置 |
| `processing_status` | `ProcessingStatus` | ❌ | 并发处理状态 |
| `last_updated` | `string (ISO 8601)` | ✅ | 最后更新时间 |
| `version` | `int` | ✅ | 数据版本号 |

### 3.2 StatusReportItem (现状分析报告)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识（8位UUID） |
| `report_id` | `int` | ✅ | 报告编号（用于显示【报告N】） |
| `is_current` | `bool` | ✅ | 是否为当前版本 |
| `stage` | `string` | ❌ | 关系阶段（L1-L4 或 T1-T3） |
| `stage_description` | `string` | ❌ | 阶段描述 |
| `acr_analysis` | `object` | ❌ | A/C/R 三维分析结果 |
| `key_issues` | `string[]` | ❌ | 核心问题列表 |
| `risk_points` | `string[]` | ❌ | 风险点列表 |
| `report_content` | `string` | ✅ | Markdown 格式的完整报告 |
| `created_at` | `string (ISO 8601)` | ✅ | 创建时间 |
| `summary` | `string` | ❌ | 中等摘要（100-200字）⚠️ 仅历史报告 |
| `one_liner` | `string` | ❌ | 一句话摘要（20-30字）⚠️ 仅历史报告 |

```json
{
  "id": "a1b2c3d4",
  "report_id": 3,
  "is_current": true,
  "stage": "L2",
  "stage_description": "有好感阶段 - 双方有明确的互动意愿",
  "acr_analysis": {
    "attraction": { "score": 7, "description": "她主动分享日常，回复积极" },
    "comfort": { "score": 6, "description": "相处自然，但还未涉及深层话题" },
    "rapport": { "score": 5, "description": "有共同话题，但默契还需培养" }
  },
  "key_issues": [
    "缺乏单独约会机会",
    "对方的真实意图尚不明确"
  ],
  "risk_points": [
    "推进太快可能吓到对方",
    "工作场合限制了互动方式"
  ],
  "report_content": "## 现状分析报告 #3\n\n### 一、关系阶段判定\n...",
  "created_at": "2025-12-30T10:30:00.000Z",
  "summary": null,
  "one_liner": null
}
```

### 3.3 ActionPlanItem (行动规划)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识 |
| `plan_id` | `int` | ✅ | 规划编号 |
| `is_current` | `bool` | ✅ | 是否为当前版本 |
| `goal` | `string` | ❌ | 阶段性目标 |
| `strategy` | `string` | ❌ | 核心策略方向 |
| `phases` | `Phase[]` | ❌ | 分阶段计划 |
| `key_principles` | `string[]` | ❌ | 关键原则 |
| `plan_content` | `string` | ✅ | Markdown 格式的完整规划 |
| `created_at` | `string (ISO 8601)` | ✅ | 创建时间 |
| `summary` | `string` | ❌ | 中等摘要（仅历史版本） |
| `one_liner` | `string` | ❌ | 一句话摘要（仅历史版本） |

```json
{
  "id": "e5f6g7h8",
  "plan_id": 2,
  "is_current": true,
  "goal": "两周内完成从L2到L3的推进，建立更深层的情感连接",
  "strategy": "通过共同活动创造独处机会，逐步试探对方态度",
  "phases": [
    {
      "phase_name": "第一周：强化日常互动",
      "actions": ["增加工作外话题", "寻找共同兴趣点"],
      "milestone": "至少一次非工作场合的交流"
    },
    {
      "phase_name": "第二周：创造独处机会",
      "actions": ["邀请一起吃晚饭", "分享个人故事"],
      "milestone": "完成一次单独约会"
    }
  ],
  "key_principles": [
    "保持自然，不刻意",
    "观察反馈，及时调整",
    "尊重对方节奏"
  ],
  "plan_content": "## 行动规划 #2\n\n### 阶段目标\n...",
  "created_at": "2025-12-30T11:00:00.000Z",
  "summary": null,
  "one_liner": null
}
```

### 3.4 ActionGuideItem (行动指南)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识 |
| `guide_id` | `int` | ✅ | 指南编号 |
| `status` | `"pending" \| "in_progress" \| "completed"` | ✅ | 执行状态 |
| `guide` | `ActionGuideContent` | ✅ | 指南内容 |
| `created_at` | `string (ISO 8601)` | ✅ | 创建时间 |
| `completed_at` | `string (ISO 8601)` | ❌ | 完成时间（completed时填充） |
| `summary` | `string` | ❌ | 执行摘要（completed时填充） |
| `one_liner` | `string` | ❌ | 一句话摘要（completed时填充） |

### 3.5 ActionGuideContent (指南内容)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `current_task` | `string` | ✅ | 当前任务描述 |
| `steps` | `string[]` | ❌ | 具体步骤 |
| `talking_points` | `string[]` | ❌ | 话术要点 |
| `dos` | `string[]` | ❌ | 该做的事 |
| `donts` | `string[]` | ❌ | 不该做的事 |
| `next_milestone` | `string` | ❌ | 下一个里程碑 |
| `guide_content` | `string` | ✅ | Markdown 格式的完整指南 |

```json
{
  "id": "i9j0k1l2",
  "guide_id": 5,
  "status": "pending",
  "guide": {
    "current_task": "邀请小雅周末一起看展览",
    "steps": [
      "先聊最近看到的有趣展览信息",
      "观察她的反应和兴趣程度",
      "自然地提出一起去的邀请",
      "如果她犹豫，给她时间考虑"
    ],
    "talking_points": [
      "「最近看到XX展览挺有意思的，你平时喜欢看展吗？」",
      "「我打算周末去看看，你要是有空可以一起？」"
    ],
    "dos": [
      "保持轻松自然的语气",
      "给对方留有余地",
      "观察她的肢体语言"
    ],
    "donts": [
      "不要表现得太急切",
      "不要反复追问",
      "如果被拒绝不要追问原因"
    ],
    "next_milestone": "获得明确回复（同意/拒绝/改期）",
    "guide_content": "## 行动指南 #5\n\n### 任务目标\n..."
  },
  "created_at": "2025-12-30T14:00:00.000Z",
  "completed_at": null,
  "summary": null,
  "one_liner": null
}
```

### 3.6 DynamicIntelItem (动态情报)

> ⚠️ **待实现 (To Be Implemented)**：此结构在 `context_types.py` 中尚未定义，需要开发人员根据本规格添加。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识 |
| `content` | `string` | ✅ | 情报内容（如"下周三要去上海"） |
| `category` | `"schedule" \| "mood" \| "status" \| "intent"` | ✅ | 情报类别 |
| `valid_from` | `string (ISO 8601)` | ✅ | 生效时间 |
| `expire_at` | `string (ISO 8601)` | ❌ | 过期时间（空则默认 7 天） |
| `source_msg_id` | `string` | ❌ | 来源消息 ID (用于溯源) |
| `confidence` | `float` | ❌ | 置信度 (0.0-1.0) |

```json
{
  "id": "d1i2n3t4",
  "content": "Crush 下周三(1月5日)要去上海参加展会，这几天会很忙",
  "category": "schedule",
  "valid_from": "2025-12-30T10:00:00.000Z",
  "expire_at": "2025-01-06T00:00:00.000Z",
  "source_msg_id": "msg_12345678",
  "confidence": 0.95
}
```

### 3.7 Layer2ExtractionConfig

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `recent_summary_count` | `int` | ❌ | `2` | 最近 N 份保留中等摘要 |
| `max_one_liner_count` | `int` | ❌ | `10` | 最多保留 N 条一句话摘要 |
| `include_active_guides` | `bool` | ❌ | `true` | 是否包含所有未执行指南 |

---

## 4. Layer 3: 对话历史

### 4.1 Layer3Memory 结构

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `all_messages` | `Message[]` | ✅ | 完整对话记录（只增不减） |
| `conversation_summaries` | `ConversationSummary[]` | ✅ | 压缩后的对话摘要 |
| `task_registry` | `AgentTaskRegistry` | ✅ | 任务级思考过程 |
| `extraction_config` | `Layer3ExtractionConfig` | ✅ | 提取策略配置 |
| `processing_status` | `ProcessingStatus` | ❌ | 并发处理状态 |
| `last_updated` | `string (ISO 8601)` | ✅ | 最后更新时间 |
| `total_turns` | `int` | ✅ | 累计对话轮次 |
| `version` | `int` | ✅ | 数据版本号 |

### 4.2 Message (消息)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识（UUID） |
| `role` | `"user" \| "assistant" \| "system"` | ✅ | 角色 |
| `content` | `string` | ✅ | 消息内容 |
| `source_type` | `"text" \| "ocr"` | ❌ | 来源类型（默认text） |

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "role": "user",
  "content": "她今天主动问我周末有什么安排",
  "source_type": "text"
}
```

### 4.3 ConversationSummary (对话摘要)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识 |
| `summary` | `string` | ✅ | 压缩摘要 |
| `start_time` | `string (ISO 8601)` | ✅ | 对话开始时间 |
| `end_time` | `string (ISO 8601)` | ✅ | 对话结束时间 |
| `turn_count` | `int` | ✅ | 对话轮次 |
| `key_topics` | `string[]` | ❌ | 关键话题 |
| `extracted_info` | `object` | ❌ | 提取的高价值信息 |

```json
{
  "id": "m3n4o5p6",
  "summary": "用户分享了和Crush一起吃午饭的经历，Crush主动问起用户的周末计划。AI建议用户可以趁机邀请Crush周末一起活动。",
  "start_time": "2025-12-30T09:00:00.000Z",
  "end_time": "2025-12-30T09:30:00.000Z",
  "turn_count": 8,
  "key_topics": ["午饭互动", "周末计划", "邀约时机"],
  "extracted_info": {
    "to_layer1": {
      "crush_info.fact": "Crush主动询问用户周末安排"
    }
  }
}
```

### 4.4 AgentTaskRegistry (任务注册表)

用于实现 **Rolling Scratchpad** 模式，管理各 Agent 的思考过程。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `main_agent` | `TaskState[]` | ❌ | 主 Agent 的任务列表 |
| `status_agent` | `TaskState[]` | ❌ | 现状分析 Agent 的任务列表 |
| `plan_agent` | `TaskState[]` | ❌ | 行动规划 Agent 的任务列表 |
| `guide_agent` | `TaskState[]` | ❌ | 行动指南 Agent 的任务列表 |

### 4.5 TaskState (任务状态)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | `string` | ✅ | 任务标识 |
| `reasoning` | `string[]` | ✅ | 思考过程记录 |
| `summary` | `string` | ❌ | 思考过程摘要（超长任务时填充） |
| `started_at` | `string (ISO 8601)` | ✅ | 任务开始时间 |
| `is_active` | `bool` | ✅ | 是否为当前活跃任务 |

```json
{
  "task_id": "判断Crush是否对用户有好感",
  "reasoning": [
    "根据聊天记录，Crush回复速度快，平均5分钟内回复",
    "Crush主动分享日常生活细节，这是好感信号",
    "但还需要观察是否有更明确的互动意愿"
  ],
  "summary": null,
  "started_at": "2025-12-30T10:00:00.000Z",
  "is_active": true
}
```

### 4.6 Layer3ExtractionConfig

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `max_recent_turns` | `int` | ❌ | `25` | 完整保留的最近轮次 |
| `include_summaries` | `bool` | ❌ | `true` | 是否包含历史摘要 |
| `max_summary_count` | `int` | ❌ | `5` | 最多包含的摘要条数 |
| `reasoning_limit` | `int` | ❌ | `10` | 任务思考过程保留条数 |

---

## 5. 辅助结构

### 5.1 ProcessingStatus (并发控制)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `is_processing` | `bool` | ✅ | 是否正在处理中 |
| `processing_type` | `"compression" \| "extraction" \| "archiving"` | ✅ | 处理类型 |
| `started_at` | `string (ISO 8601)` | ✅ | 处理开始时间 |
| `snapshot_version` | `int` | ✅ | 处理前的数据版本号 |
| `fallback_data` | `object` | ❌ | 降级时使用的数据快照 |

### 5.2 ReportCounter (报告计数器)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `status_report` | `int` | ❌ | `0` | 现状分析报告编号 |
| `action_plan` | `int` | ❌ | `0` | 行动规划编号 |
| `action_guide` | `int` | ❌ | `0` | 行动指南编号 |

### 5.3 CrushChatStorage (Crush 聊天记录)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `metadata` | `CrushChatMetadata` | ❌ | L1: 元数据（常驻） |
| `summary` | `CrushChatSummary` | ❌ | L2: 结构化摘要（常驻） |

#### CrushChatMetadata

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_messages` | `int` | 总消息数 |
| `chat_frequency` | `string` | 聊天频率描述 |
| `time_span` | `string` | 时间跨度 |
| `last_chat_time` | `string` | 最后聊天时间 |

#### CrushChatSummary

| 字段 | 类型 | 说明 |
|------|------|------|
| `key_events` | `string[]` | 关键事件 |
| `emotional_turns` | `string[]` | 情感转折点 |
| `main_topics` | `string[]` | 主要话题 |

---

## 6. 持久化存储格式

### 6.1 文件位置

```
agent_impl/data/users/{user_id}.json
```

### 6.2 完整存储格式

```json
{
  "user_id": "user_001",
  "updated_at": "2025-12-30T15:00:00.000Z",
  "version": "3.0",
  "state": {
    "user_message": "...",
    "layer1_memory": { /* Layer1Memory */ },
    "layer2_memory": { /* Layer2Memory */ },
    "layer3_memory": { /* Layer3Memory */ },
    "messages": [ /* Message[] */ ],
    "crush_chat_storage": null,
    "report_counter": {
      "status_report": 3,
      "action_plan": 2,
      "action_guide": 5
    },
    "intent_type": "action_trigger",
    "next_action": "end_turn",
    "should_continue": true,
    "route_to": "main_agent"
  }
}
```

### 6.3 版本迁移

| 版本 | 说明 |
|------|------|
| `1.0` | 旧版扁平化结构 |
| `2.0` | 引入 3×3 矩阵，但未分层 |
| `3.0` | 分层长期记忆架构（当前） |

从旧版本加载时，`state_storage.py` 会自动调用 `_migrate_to_layered_memory()` 进行迁移。

---

## 附录：快速参考

### 字段命名约定

| 前缀/后缀 | 含义 |
|----------|------|
| `all_*` | 全量数据（含历史） |
| `*_config` | 配置对象 |
| `*_at` | 时间戳 (ISO 8601) |
| `is_*` | 布尔标志 |
| `*_count` | 计数器 |
| `*_id` | 唯一标识 |

### 状态流转

```
ActionGuide 状态流转:
  pending → in_progress → completed
                 ↑
             (用户操作)

报告版本管理:
  新报告生成 → is_current=true
  旧报告     → is_current=false, summary 填充
```

### 默认值汇总

| 配置项 | 默认值 |
|--------|--------|
| `Layer1.max_tokens` | 15000 |
| `Layer2.recent_summary_count` | 2 |
| `Layer2.max_one_liner_count` | 10 |
| `Layer3.max_recent_turns` | 25 |
| `Layer3.max_summary_count` | 5 |
| `Layer3.reasoning_limit` | 10 |

