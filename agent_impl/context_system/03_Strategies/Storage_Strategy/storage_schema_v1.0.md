# 存储层数据结构定义 (Storage Schema) v1.1

> **适用版本**：v1.1 (2026-01-15)  
> **代码对应**：`graph/context_types.py`, `graph/state_storage.py`  
> **规范依赖**：`02_Specs/layer1_spec_v1.0.md`, `02_Specs/layer2_spec_v1.0.md`, `02_Specs/layer3_spec_v1.0.md`, `02_Specs/task_system_spec.md`

本文档定义了上下文工程中各层长期记忆的**完整数据结构**。

---

## 目录

1. [整体架构](#1-整体架构)
2. [Layer 1: 静态情报 (AtomicMemory 结构)](#2-layer-1-静态情报)
3. [Layer 2: 工作上下文](#3-layer-2-工作上下文)
4. [Layer 3: 对话历史](#4-layer-3-对话历史)
5. [任务系统 (Task System)](#5-任务系统)
6. [辅助结构](#6-辅助结构)
7. [持久化存储格式](#7-持久化存储格式)

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

> **核心变更**：使用 **AtomicMemory 原子记忆结构**，每条信息独立存储为对象，不再使用字符串拼接。

### 2.1 Layer1Memory 结构

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `full_data` | `UserContext` | ✅ | 3×3 情报矩阵全量数据（原子记忆列表） |
| `extraction_config` | `Layer1ExtractionConfig` | ✅ | 提取策略配置 |
| `processing_status` | `ProcessingStatus` | ❌ | 并发处理状态 |
| `last_updated` | `string (ISO 8601)` | ✅ | 最后更新时间 |
| `update_count` | `int` | ✅ | 累计更新次数 |
| `version` | `int` | ✅ | 数据版本号 |

### 2.2 AtomicMemory（原子记忆）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识（uuid[:8]） |
| `content` | `string` | ✅ | 内容（最小语义单元） |
| `created_at` | `string` | ✅ | 时间（精确到小时）: "2026-01-13T14" |
| `source_type` | `"onboarding" \| "conversation" \| "report"` | ✅ | 来源类型 |
| `confidence` | `float` | ❌ | 置信度 (0.0-1.0)，AI分析必填 |
| `confidence_reason` | `string` | ❌ | 置信度原因，AI分析必填 |

```json
{
  "id": "a1b2c3d4",
  "content": "用户28岁，是程序员",
  "created_at": "2026-01-13T14",
  "source_type": "onboarding"
}
```

### 2.3 UserContext (3×3 情报矩阵)

```json
{
  "user_info": {
    "user_provide": [/* AtomicMemory[] */],
    "fact": [/* AtomicMemory[] */],
    "ai_provide": [/* AtomicMemory[] */]
  },
  "crush_info": {
    "crush_name": "小雅",
    "user_provide": [/* AtomicMemory[] */],
    "fact": [/* AtomicMemory[] */],
    "ai_provide": [/* AtomicMemory[] */]
  },
  "both_info": {
    "user_provide": [/* AtomicMemory[] */],
    "fact": [/* AtomicMemory[] */],
    "ai_provide": [/* AtomicMemory[] */]
  }
}
```

### 2.4 InfoSource 字段

| 字段 | 类型 | 必填 | 说明 | 信任优先级 |
|------|------|------|------|-----------|
| `user_provide` | `AtomicMemory[]` | ❌ | 用户口述信息 | 🟡 最低 |
| `fact` | `AtomicMemory[]` | ❌ | 客观事实（截图/记录） | 🟢 最高 |
| `ai_provide` | `AtomicMemory[]` | ❌ | AI分析结论 | 🔵 中等 |

### 2.5 完整 Layer1Memory 示例

```json
{
  "full_data": {
    "user_info": {
      "user_provide": [
        {"id": "a1b2c3d4", "content": "28岁，程序员", "created_at": "2026-01-13T10", "source_type": "onboarding"},
        {"id": "e5f6g7h8", "content": "平时比较内向", "created_at": "2026-01-13T10", "source_type": "onboarding"}
      ],
      "fact": [
        {"id": "i9j0k1l2", "content": "朋友圈显示喜欢打篮球和弹吉他", "created_at": "2026-01-13T14", "source_type": "conversation"}
      ],
      "ai_provide": [
        {"id": "m3n4o5p6", "content": "依恋类型：安全型偏焦虑", "created_at": "2026-01-14T09", "source_type": "report", "confidence": 0.75, "confidence_reason": "基于用户描述的恋爱史推断"}
      ]
    },
    "crush_info": {
      "crush_name": "小雅",
      "user_provide": [
        {"id": "q7r8s9t0", "content": "同公司产品经理，比我小2岁", "created_at": "2026-01-13T10", "source_type": "onboarding"}
      ],
      "fact": [
        {"id": "u1v2w3x4", "content": "聊天记录显示她回复速度快", "created_at": "2026-01-14T15", "source_type": "conversation"}
      ],
      "ai_provide": []
    },
    "both_info": {
      "user_provide": [
        {"id": "y5z6a7b8", "content": "认识3个月，经常一起吃午饭", "created_at": "2026-01-13T10", "source_type": "onboarding"}
      ],
      "fact": [],
      "ai_provide": [
        {"id": "c9d0e1f2", "content": "当前阶段：L2（有好感）", "created_at": "2026-01-14T09", "source_type": "report", "confidence": 0.8, "confidence_reason": "综合互动频率和主动性判断"}
      ]
    }
  },
  "extraction_config": {
    "mode": "full",
    "max_tokens": 15000
  },
  "processing_status": null,
  "last_updated": "2026-01-15T10:30:00.000Z",
  "update_count": 15,
  "version": 5
}
```

---

## 3. Layer 2: 工作上下文

> **核心变更**：使用 `current_xxx` + `xxx_history` 结构替代 `all_xxx` + `is_current`。

### 3.1 Layer2Memory 结构

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `dynamic_intels` | `DynamicIntelItem[]` | ✅ | 动态情报板（时效性信息） |
| `current_status_report` | `StatusReportItem \| null` | ✅ | 当前现状报告 |
| `status_report_history` | `StatusReportItem[]` | ✅ | 历史现状报告 |
| `current_action_plan` | `ActionPlanItem \| null` | ✅ | 当前行动规划 |
| `action_plan_history` | `ActionPlanItem[]` | ✅ | 历史行动规划 |
| `action_guides` | `ActionGuideItem[]` | ✅ | 所有行动指南（全量保留） |
| `extraction_config` | `Layer2ExtractionConfig` | ✅ | 提取策略配置 |
| `processing_status` | `ProcessingStatus` | ❌ | 并发处理状态 |
| `last_updated` | `string (ISO 8601)` | ✅ | 最后更新时间 |
| `version` | `int` | ✅ | 数据版本号 |

### 3.2 StatusReportItem (现状分析报告)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 报告 ID (uuid[:8]) |
| `report_id` | `int` | ✅ | 报告编号（用于显示【报告N】） |
| `report_content` | `string` | ✅ | 报告正文（Markdown） |
| `created_at` | `string (ISO 8601)` | ✅ | 创建时间 |
| `version` | `int` | ✅ | 版本号（修改时+1） |
| `stage` | `string` | ❌ | 关系阶段（L1-L4 或 T1-T3） |
| `stage_description` | `string` | ❌ | 阶段描述 |
| `acr_analysis` | `object` | ❌ | A/C/R 三维分析结果 |
| `key_issues` | `string[]` | ❌ | 核心问题列表 |
| `risk_points` | `string[]` | ❌ | 风险点列表 |
| `summary` | `string` | ❌ | 中等摘要（历史报告，由 Organize Agent 生成） |
| `one_liner` | `string` | ❌ | 一句话摘要（历史报告） |
| `archived_at` | `string (ISO 8601)` | ❌ | 归档时间 |

```json
{
  "id": "a1b2c3d4",
  "report_id": 3,
  "report_content": "## 现状分析报告 #3\n\n### 一、关系阶段判定\n...",
  "created_at": "2026-01-15T10:30:00.000Z",
  "version": 1,
  "stage": "L2",
  "stage_description": "有好感阶段 - 双方有明确的互动意愿",
  "summary": null,
  "one_liner": null,
  "archived_at": null
}
```

### 3.3 ActionPlanItem (行动规划)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 规划 ID (uuid[:8]) |
| `plan_id` | `int` | ✅ | 规划编号 |
| `plan_content` | `string` | ✅ | 规划正文（Markdown） |
| `created_at` | `string (ISO 8601)` | ✅ | 创建时间 |
| `version` | `int` | ✅ | 版本号 |
| `goal` | `string` | ❌ | 阶段性目标 |
| `strategy` | `string` | ❌ | 核心策略方向 |
| `phases` | `Phase[]` | ❌ | 分阶段计划 |
| `key_principles` | `string[]` | ❌ | 关键原则 |
| `summary` | `string` | ❌ | 中等摘要（历史规划） |
| `one_liner` | `string` | ❌ | 一句话摘要 |
| `archived_at` | `string (ISO 8601)` | ❌ | 归档时间 |

### 3.4 ActionGuideItem (行动指南)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识 (uuid[:8]) |
| `guide_id` | `int` | ✅ | 指南编号 |
| `title` | `string` | ✅ | 标题 |
| `status` | `Literal` | ✅ | 状态（见下方状态机） |
| `guide` | `ActionGuideContent` | ✅ | 指南内容 |
| `created_at` | `string (ISO 8601)` | ✅ | 创建时间 |
| `expected_start_at` | `string (ISO 8601)` | ❌ | 预计开始时间 |
| `expire_at` | `string (ISO 8601)` | ❌ | 过期时间 |
| `completed_at` | `string (ISO 8601)` | ❌ | 完成时间 |
| `user_feedback` | `string` | ❌ | 用户反馈（完成时记录） |
| `summary` | `string` | ❌ | 执行摘要（终态时填充） |
| `one_liner` | `string` | ❌ | 一句话摘要 |

**状态机（6 种状态）**：

```
in_progress（进行中，默认）
    ├─ → completed（已完成，终态）
    ├─ → paused（暂停）
    ├─ → cancelled（已取消，终态）
    └─ → pending（搁置）

pending（搁置）
    ├─ → in_progress
    ├─ → cancelled
    └─ → expired（已过期，终态）

paused（暂停）
    ├─ → in_progress
    └─ → cancelled
```

### 3.5 DynamicIntelItem (动态情报)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识 (uuid[:8]) |
| `content` | `string` | ✅ | 情报内容 |
| `created_at` | `string (ISO 8601)` | ✅ | 创建时间 |
| `expire_at` | `string (ISO 8601)` | ✅ | 过期时间 |
| `subject` | `"user" \| "crush"` | ✅ | 归属 |
| `category` | `string` | ✅ | 类型（LLM 自定义，如：日程、情绪、意向） |
| `confidence` | `float` | ✅ | 置信度 (0.0-1.0) |
| `confidence_reason` | `string` | ✅ | 置信度原因 |
| `source_type` | `"conversation"` | ✅ | 来源类型 |

```json
{
  "id": "d1i2n3t4",
  "content": "Crush 下周三要去上海参加展会",
  "created_at": "2026-01-15T10:00:00.000Z",
  "expire_at": "2026-01-22T00:00:00.000Z",
  "subject": "crush",
  "category": "日程",
  "confidence": 0.95,
  "confidence_reason": "Crush 明确告知用户",
  "source_type": "conversation"
}
```

---

## 4. Layer 3: 对话历史

> **核心变更**：ConversationSummary 使用新字段结构，reasoning 字段移除。

### 4.1 Layer3Memory 结构

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `all_messages` | `Message[]` | ✅ | 完整对话记录 |
| `conversation_summaries` | `ConversationSummary[]` | ✅ | 对话摘要（最多 5 条） |
| `task_registry` | `AgentTaskRegistry` | ✅ | 任务注册表 |
| `extraction_config` | `Layer3ExtractionConfig` | ✅ | 提取策略配置 |
| `processing_status` | `ProcessingStatus` | ❌ | 并发处理状态 |
| `last_updated` | `string (ISO 8601)` | ✅ | 最后更新时间 |
| `total_turns` | `int` | ✅ | 累计对话轮次 |
| `version` | `int` | ✅ | 数据版本号 |

### 4.2 ConversationSummary (对话摘要)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识 (uuid[:8]) |
| `summary` | `string` | ✅ | 摘要内容 |
| `topics` | `string` | ✅ | 关键话题（逗号分隔） |
| `created_at` | `string (ISO 8601)` | ✅ | 创建时间 |
| `turn_range` | `string` | ✅ | 覆盖的轮次范围: "1-25" |

```json
{
  "id": "m3n4o5p6",
  "summary": "用户分享了和Crush一起吃午饭的经历，Crush主动问起用户的周末计划。AI建议趁机邀请Crush周末一起活动。",
  "topics": "午饭互动,周末计划,邀约时机",
  "created_at": "2026-01-15T09:30:00.000Z",
  "turn_range": "1-25"
}
```

### 4.3 Layer3ExtractionConfig

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `max_recent_turns` | `int` | ❌ | `25` | 完整保留的最近轮次 |
| `include_summaries` | `bool` | ❌ | `true` | 是否包含历史摘要 |
| `max_summary_count` | `int` | ❌ | `5` | 最多包含的摘要条数 |
| `reasoning_limit` | `int` | ❌ | `8` | 推理笔记保留条数 |

---

## 5. 任务系统

> **核心变更**：使用 `status` 替代 `is_active`，使用 `BoundContext` 替代 `BoundActionGuide`。

### 5.1 AgentTaskRegistry

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `main_agent` | `TaskState[]` | ❌ | 主 Agent 的任务列表 |
| `status_agent` | `TaskState[]` | ❌ | 现状分析 Agent 的任务列表 |
| `plan_agent` | `TaskState[]` | ❌ | 行动规划 Agent 的任务列表 |
| `guide_agent` | `TaskState[]` | ❌ | 行动指南 Agent 的任务列表 |

### 5.2 TaskState (任务状态)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | `string` | ✅ | 任务唯一标识 (uuid[:8]) |
| `title` | `string` | ✅ | 语义化标题 |
| `summary` | `string` | ✅ | 摘要（20-30字） |
| `status` | `"pending" \| "active" \| "completed"` | ✅ | 任务状态 |
| `reasoning_notes` | `ReasoningNote[]` | ✅ | 推理笔记（最多 8 条） |
| `bound_contexts` | `BoundContext[]` | ✅ | 绑定的上下文 |
| `started_at` | `string (ISO 8601)` | ✅ | 开始时间 |
| `completed_at` | `string (ISO 8601)` | ❌ | 完成时间 |
| `completion_summary` | `string` | ❌ | 完成结论摘要（50-100字） |

```json
{
  "task_id": "a1b2c3d4",
  "title": "判断Crush是否对用户有好感",
  "summary": "分析Crush的互动信号，判断好感程度",
  "status": "active",
  "reasoning_notes": [
    {
      "id": "n1o2p3q4",
      "content": "Crush回复速度快，平均5分钟内回复，这是积极信号",
      "created_at": "2026-01-15T10:00:00.000Z",
      "task_id": "a1b2c3d4"
    }
  ],
  "bound_contexts": [],
  "started_at": "2026-01-15T10:00:00.000Z",
  "completed_at": null,
  "completion_summary": null
}
```

### 5.3 ReasoningNote (推理笔记)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识 (uuid[:8]) |
| `content` | `string` | ✅ | 笔记内容（结论导向） |
| `created_at` | `string (ISO 8601)` | ✅ | 创建时间 |
| `task_id` | `string` | ✅ | 所属任务 ID |

### 5.4 BoundContext (绑定上下文)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 绑定记录 ID (uuid[:8]) |
| `type` | `string` | ✅ | 上下文类型 |
| `ref_id` | `string` | ❌ | 引用的资源 ID（用于去重） |
| `title` | `string` | ✅ | 标题（20-30字） |
| `content_md` | `string` | ✅ | Markdown 内容 |
| `source` | `string` | ✅ | 来源标识 |
| `bound_at` | `string (ISO 8601)` | ✅ | 绑定时间 |
| `expire_at` | `string (ISO 8601)` | ❌ | 过期时间 |

**支持的 context_type 及上限**：

| type | 上限 | 说明 |
|------|------|------|
| `action_guide` | 3 | 行动指南详情 |
| `status_report` | 1 | 现状报告片段 |
| `action_plan` | 1 | 行动规划片段 |
| `crush_chat` | 3 | Crush 聊天记录片段 |
| `history_snippet` | 3 | 历史对话片段 |
| `dynamic_intel` | 5 | 动态情报 |
| `custom` | 3 | 自定义上下文 |

---

## 6. 辅助结构

### 6.1 ProcessingStatus (并发控制)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `is_processing` | `bool` | ✅ | 是否正在处理中 |
| `processing_type` | `"compression" \| "extraction" \| "archiving"` | ✅ | 处理类型 |
| `started_at` | `string (ISO 8601)` | ✅ | 处理开始时间 |
| `snapshot_version` | `int` | ✅ | 处理前的数据版本号 |
| `fallback_data` | `object` | ❌ | 降级时使用的数据快照 |

### 6.2 ReportCounter (报告计数器)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `status_report` | `int` | `0` | 现状分析报告编号 |
| `action_plan` | `int` | `0` | 行动规划编号 |
| `action_guide` | `int` | `0` | 行动指南编号 |

---

## 7. 持久化存储格式

### 7.1 文件位置

```
agent_impl/data/users/{user_id}.json
```

### 7.2 完整存储格式

```json
{
  "user_id": "user_001",
  "updated_at": "2026-01-15T15:00:00.000Z",
  "version": "3.1",
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
    }
  }
}
```

### 7.3 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| `1.0` | - | 旧版扁平化结构 |
| `2.0` | - | 引入 3×3 矩阵，但未分层 |
| `3.0` | - | 分层长期记忆架构 |
| `3.1` | 2026-01-15 | AtomicMemory、current_xxx 结构、任务系统 status |

---

## 附录：快速参考

### 默认值汇总

| 配置项 | 默认值 |
|--------|--------|
| `Layer1.max_tokens` | 15000 |
| `Layer2.recent_summary_count` | 2 |
| `Layer2.max_one_liner_count` | 10 |
| `Layer3.max_recent_turns` | 25 |
| `Layer3.max_summary_count` | 5 |
| `Layer3.reasoning_limit` | 8 |

### 状态流转

```
TaskState 状态流转:
  active（当前活跃，同一时刻只有一个）
      ├─ → pending（被其他任务切走）
      └─ → completed（任务完成）

  pending（待处理）
      └─ → active（切换回来）

ActionGuide 状态流转:
  in_progress（默认）
      ├─ → completed
      ├─ → paused
      ├─ → cancelled
      └─ → pending
```
