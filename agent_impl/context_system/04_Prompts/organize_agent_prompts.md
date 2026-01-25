# Organize Agent Prompts（提纯/归档/压缩）v3

> 说明：本文件用于 **上下文工程** 的"提纯/归档"LLM Prompt 模板。  
> 使用方式：代码读取 `<!-- TEMPLATE: xxx -->` 到 `<!-- END_TEMPLATE -->` 之间的内容。

占位符约定：
- 行动指南：`__GUIDE_CURRENT_TASK__`、`__GUIDE_FULL_CONTENT__`
- 现状报告：`__STATUS_STAGE__`、`__STATUS_SUMMARY_TEXT__`、`__STATUS_REPORT_CONTENT__`
- 行动规划：`__PLAN_GOAL__`、`__PLAN_STRATEGY__`、`__PLAN_CONTENT__`
- 对话压缩：`__CONVERSATION_TEXT__`
- 任务思考压缩：`__CURRENT_SUMMARY__`、`__REASONING_TEXT__`

---

<!-- TEMPLATE: action_guide -->
## 你的任务

从已完成的行动指南中提取信息并生成摘要。

## 价值过滤标准

### ✅ 必须提取（写入 Layer 1）
- 身份信息：姓名、年龄、职业、学历、家庭情况
- 性格与风格：性格特点、沟通风格、依恋类型、行为模式
- 长期偏好：兴趣爱好、生活习惯、价值观、择偶标准
- 关系背景：认识方式、认识时长、共同社交圈
- 重要事件：关系里程碑、关键冲突、重大态度表达

### 🚫 禁止记录（直接跳过）
- 纯语气词："哈哈哈"、"唉"、"..."、"？？？"
- 口头禅/废话："你怕不是xxx"、"就那样"、"算了不说了"
- 简单应答："好的"、"行"、"知道了"、"对对对"
- 无实质提问："真的吗"、"然后呢"、"那怎么办"
- 无关话题：天气、新闻、娱乐八卦
- AI 说的话：AI 的建议、分析、安慰（不需要记录回 Layer 1）
- 已在 Layer 2 常驻：关系阶段、ACR 分析、核心问题

## 来源判断规则

| 来源 | 定义 | 置信度 |
|:----|:----|:------|
| user_provide | 用户直接陈述的信息 | 0.3-0.8 |
| fact | 有直接证据（聊天截图、可观察行为） | 0.85-0.95 |
| ai_provide | AI 基于证据分析得出的结论 | 0.5-0.85 |

**边界情况速查**：
| 场景 | 来源 | 置信度 |
|:----|:----|:------|
| 用户转述 Crush 的话 | user_provide | 0.70 |
| 用户描述可观察行为（如"已读不回3天"） | fact | 0.85 |
| 用户的主观推测（如"我感觉她喜欢我"） | user_provide | 0.35 |
| 截图中 Crush 直接说的话 | fact | 0.95 |

## 摘要质量检查清单

生成已完成指南摘要时，确保包含：
- [ ] 任务概述：这个任务要做什么？
- [ ] 执行情况：用户做了吗？怎么做的？
- [ ] 用户反馈：用户说了什么？（保留原话关键词！）
- [ ] Crush 反应：对方有什么反应？
- [ ] 关键收获：从这次行动中学到/发现了什么？

## 输入

任务：__GUIDE_CURRENT_TASK__
完整内容：
__GUIDE_FULL_CONTENT__

## 输出格式

```json
{
  "summary": "中等摘要（100-200字）：任务目标、执行情况、用户反馈、Crush反应、收获",
  "one_liner": "一句话摘要（20-30字）",
  "extracted_info": {
    "user_info": { "user_provide": [], "fact": [], "ai_provide": [] },
    "crush_info": { "user_provide": [], "fact": [], "ai_provide": [] },
    "both_info": { "user_provide": [], "fact": [], "ai_provide": [] }
  }
}
```

**示例**：
```json
{
  "summary": "【任务】发布展示生活的朋友圈。【执行】用户周六下午发布咖啡店照片。【用户反馈】'发了！她点赞了，发完10分钟内'。【Crush反应】10分钟内点赞无评论。【收获】Crush 关注着用户朋友圈，态度未完全冷却。",
  "one_liner": "用户发朋友圈展示生活，Crush 10分钟内点赞",
  "extracted_info": {
    "user_info": { "user_provide": [], "fact": [], "ai_provide": [] },
    "crush_info": { "user_provide": [], "fact": [], "ai_provide": ["Crush 关注用户朋友圈动态"] },
    "both_info": { "user_provide": [], "fact": ["Crush 在用户发朋友圈10分钟内点赞"], "ai_provide": [] }
  }
}
```
<!-- END_TEMPLATE -->

---

<!-- TEMPLATE: status_report -->
## 你的任务

从现状分析报告中提取信息并生成摘要。

## 价值过滤标准

### ✅ 必须提取（写入 Layer 1）
- 身份信息：姓名、年龄、职业、学历、家庭情况
- 性格与风格：性格特点、沟通风格、依恋类型、行为模式
- 长期偏好：兴趣爱好、生活习惯、价值观、择偶标准
- 关系背景：认识方式、认识时长、共同社交圈
- 重要事件：关系里程碑、关键冲突、重大态度表达

### 🚫 禁止记录
- 纯语气词、口头禅、简单应答
- 已在 Layer 2 常驻的信息：
  - 关系阶段判断（L1-L4/T1-T3）
  - ACR 三维分析
  - 核心问题/风险点

## 来源判断规则

| 来源 | 定义 | 置信度 |
|:----|:----|:------|
| user_provide | 用户直接陈述的信息 | 0.3-0.8 |
| fact | 有直接证据（聊天截图、可观察行为） | 0.85-0.95 |
| ai_provide | AI 基于证据分析得出的结论 | 0.5-0.85 |

**边界情况速查**：
| 场景 | 来源 | 置信度 |
|:----|:----|:------|
| 用户转述 Crush 的话 | user_provide | 0.70 |
| 用户描述可观察行为 | fact | 0.85 |
| AI 的性格/依恋类型分析 | ai_provide | 0.80 |
| 截图中 Crush 直接说的话 | fact | 0.95 |

## 摘要质量检查清单

生成报告摘要时，确保包含：
- [ ] 关系阶段：当时处于什么阶段？（L1-L4 / T1-T3）
- [ ] 核心问题：主要障碍/风险是什么？
- [ ] 关键发现：这份报告最重要的洞察是什么？
- [ ] 态势判断：Crush 对用户的态度如何？
- [ ] 建议方向：报告建议的应对方向（1句话）

## 输入

关系阶段：__STATUS_STAGE__
原始总结：__STATUS_SUMMARY_TEXT__
完整报告：
__STATUS_REPORT_CONTENT__

## 输出格式

```json
{
  "summary": "中等摘要（100-200字）：【阶段】【核心问题】【态势】【关键发现】【方向】",
  "one_liner": "一句话摘要（20-30字）",
  "extracted_info": {
    "user_info": { "user_provide": [], "fact": [], "ai_provide": [] },
    "crush_info": { "user_provide": [], "fact": [], "ai_provide": [] },
    "both_info": { "user_provide": [], "fact": [], "ai_provide": [] }
  }
}
```

**示例**：
```json
{
  "summary": "【阶段】L2好感期初期，有T1备胎风险。【核心问题】用户需求感过强，消息频率过高。【态势】Crush态度从热情降温至平淡，回复变短。【关键发现】Crush出现'再说吧''最近忙'等推脱话术。【方向】建议7天冷冻期，降低主动频率。",
  "one_liner": "L2阶段有T1风险，用户需求感过强导致Crush态度降温",
  "extracted_info": {
    "user_info": { "user_provide": [], "fact": [], "ai_provide": ["依恋类型：焦虑型", "需求感过强，主动频率过高"] },
    "crush_info": { "user_provide": [], "fact": ["Crush说'再说吧''最近忙'"], "ai_provide": [] },
    "both_info": { "user_provide": [], "fact": [], "ai_provide": ["用户主动多，Crush被动回应"] }
  }
}
```
<!-- END_TEMPLATE -->

---

<!-- TEMPLATE: action_plan -->
## 你的任务

从行动规划中提取信息并生成摘要。

## 价值过滤标准

### ✅ 必须提取（写入 Layer 1）
- 身份信息：姓名、年龄、职业、学历、家庭情况
- 性格与风格：性格特点、沟通风格、依恋类型、行为模式
- 长期偏好：兴趣爱好、生活习惯、价值观、择偶标准
- 关系背景：认识方式、认识时长、共同社交圈
- AI 分析的用户问题模式（如"需求感过强"）

### 🚫 禁止记录
- 纯语气词、口头禅、简单应答
- 具体的每日任务安排（太细节）
- 详细话术/模板（行动指南负责）

## 来源判断规则

| 来源 | 定义 | 置信度 |
|:----|:----|:------|
| user_provide | 用户直接陈述的信息 | 0.3-0.8 |
| fact | 有直接证据（聊天截图、可观察行为） | 0.85-0.95 |
| ai_provide | AI 基于证据分析得出的结论 | 0.5-0.85 |

**边界情况速查**：
| 场景 | 来源 | 置信度 |
|:----|:----|:------|
| 用户表达的目标/意向 | user_provide | 0.80 |
| AI 对用户问题的诊断 | ai_provide | 0.80 |
| AI 制定的策略建议 | ai_provide | 0.75 |

## 摘要质量检查清单

生成规划摘要时，确保包含：
- [ ] 阶段性目标：这个规划想达成什么？
- [ ] 核心策略：采用什么策略/打法？（1句话）
- [ ] 阶段划分：分几个阶段？每阶段关键词是什么？
- [ ] 里程碑：什么信号表示可以进入下一阶段？
- [ ] 关键原则：执行时的红线/禁忌（如果有）

## 输入

阶段性目标：__PLAN_GOAL__
核心策略：__PLAN_STRATEGY__
完整规划：
__PLAN_CONTENT__

## 输出格式

```json
{
  "summary": "中等摘要（100-200字）：【目标】【核心策略】【阶段划分】【里程碑】【红线】",
  "one_liner": "一句话摘要（20-30字）",
  "extracted_info": {
    "user_info": { "user_provide": [], "fact": [], "ai_provide": [] },
    "crush_info": { "user_provide": [], "fact": [], "ai_provide": [] },
    "both_info": { "user_provide": [], "fact": [], "ai_provide": [] }
  }
}
```

**示例**：
```json
{
  "summary": "【目标】从T1备胎边缘恢复到L2稳定状态。【核心策略】撤退→建设→重启三阶段打法。【阶段划分】Phase1冷冻期7天只回不发，Phase2建设期14天朋友圈展示价值，Phase3重启期用自然契机开启对话。【里程碑】Crush主动发起非工作话题=可进入Phase3。【红线】禁止追问'你怎么不理我'。",
  "one_liner": "三阶段打法从T1恢复L2：冷冻→建设→重启",
  "extracted_info": {
    "user_info": { "user_provide": [], "fact": [], "ai_provide": ["需求感过强是核心问题"] },
    "crush_info": { "user_provide": [], "fact": [], "ai_provide": [] },
    "both_info": { "user_provide": [], "fact": [], "ai_provide": ["用户主动频率过高，需要调整互动模式"] }
  }
}
```
<!-- END_TEMPLATE -->

---

<!-- TEMPLATE: conversation -->
## 你的任务

从对话记录中提取信息，输出对话摘要 + Layer 1 长期信息 + Layer 2 动态情报。

---

## ⚠️ 信息分类流程（按顺序执行，不可跳步）

对每条提取的信息，**必须按以下顺序判断**：

### Step 1: 时效性判断（最高优先级！）

**先判断这条信息是短期有效还是长期有效：**

| 关键词 | 时效性 | 去向 |
|:------|:------|:----|
| "这周"、"最近"、"今天"、"明天"、"下周"、"这几天" | 短期 | **只进 dynamic_intel，禁止进 layer1_info** |
| "一直"、"从来"、"总是"、"性格"、"习惯"、无时间限定 | 长期 | 进 layer1_info |

**短期信息示例（只进 dynamic_intel）**：
- "Crush这周要加班" → dynamic_intel (schedule) ✅，layer1_info ❌
- "Crush最近心情不好" → dynamic_intel (mood) ✅，layer1_info ❌
- "Crush今天已读不回" → dynamic_intel (event) ✅，layer1_info ❌

**长期信息示例（只进 layer1_info）**：
- "Crush性格内向" → layer1_info ✅
- "Crush说她有男朋友" → layer1_info ✅（关系状态=长期）
- "Crush已读不回超过3天了" → layer1_info ✅（持续行为模式=长期）

⚠️ **如果判定为短期，直接进 dynamic_intel，不要继续后面的步骤！**

---

### Step 2: 价值判断（只对长期信息执行）

**判断这条长期信息是否值得记录：**

✅ **高价值（记录）**：
- 身份信息：姓名、年龄、职业、学历、家庭
- 性格特点：内向/外向、敏感/大条、沟通风格
- 长期偏好：兴趣爱好、生活习惯、价值观、择偶标准
- 关系背景：认识方式、认识时长、关系定性
- 里程碑事件：第一次约会、表白、吵架

🚫 **低价值（不记录）**：
- 纯语气词："哈哈哈"、"唉"
- 废话/口头禅："你怕不是xxx"、"就那样"
- 简单应答："好的"、"知道了"
- 过于泛化："通过微信联系"、"经常聊天"
- AI 说的话

---

### Step 3: 归属判断（信息关于谁？）

| 信息关于谁？ | 归属 |
|:-----------|:----|
| 关于**用户自己** | user_info |
| 关于**Crush 的特征或态度** | crush_info |
| 关于**双方的关系或互动** | both_info |

**关键规则**：判断标准是**信息描述的对象**，不是**信息来源**。

| 信息 | 归属 | 解释 |
|:----|:----|:----|
| "我是程序员" | user_info | 描述用户 |
| "Crush是设计师" | crush_info | 描述Crush |
| "用户感觉：Crush对自己有好感" | **crush_info** | 描述的是**Crush的态度**，虽然是用户的感觉 |
| "我们认识3个月了" | both_info | 描述双方关系 |

---

### Step 4: 来源判断

| 来源 | 定义 | 置信度 |
|:----|:----|:------|
| fact | 截图原话、可观察行为（如"已读不回3天"） | 0.85-0.95 |
| user_provide | 用户陈述（包括转述、推测） | 0.30-0.80 |
| ai_provide | AI 的分析结论 | 0.50-0.85 |

**书写规范**：
- 截图原话："Crush在聊天中说：'...'"
- 用户转述："用户转述：Crush表示..."
- 用户推测："用户感觉：..."
- 可观察行为："用户反馈：Crush已读不回3天"

---

## 输入

__CONVERSATION_TEXT__

## 输出格式

```json
{
  "summary": "对话摘要（50-100字）",
  "key_topics": ["话题1", "话题2"],
  "layer1_info": {
    "user_info": { "user_provide": [], "fact": [], "ai_provide": [] },
    "crush_info": { "user_provide": [], "fact": [], "ai_provide": [] },
    "both_info": { "user_provide": [], "fact": [], "ai_provide": [] }
  },
  "dynamic_intel": [
    {
      "content": "情报内容",
      "category": "schedule|mood|status|intent|event",
      "subject": "user|crush",
      "confidence": 0.8,
      "confidence_reason": "原因"
    }
  ]
}
```

**示例**：
```json
{
  "summary": "【话题】Crush态度问题。【情况】用户反馈Crush已读不回超过3天，担心关系变化。【结论】AI分析需求感过强，建议冷静期。",
  "key_topics": ["已读不回", "需求感管理"],
  "layer1_info": {
    "user_info": { 
      "user_provide": [], 
      "fact": [], 
      "ai_provide": ["依恋类型：焦虑型"] 
    },
    "crush_info": { 
      "user_provide": ["Crush性格偏被动", "用户转述：Crush表示自己有男朋友", "用户感觉：Crush对自己有好感"], 
      "fact": ["Crush在聊天中说：'我有男朋友了'"], 
      "ai_provide": [] 
    },
    "both_info": { 
      "user_provide": [], 
      "fact": ["用户反馈：Crush已读不回超过3天"], 
      "ai_provide": [] 
    }
  },
  "dynamic_intel": [
    {
      "content": "Crush这周要加班",
      "category": "schedule",
      "subject": "crush",
      "confidence": 0.70,
      "confidence_reason": "用户转述"
    }
  ]
}
```

**注意示例中**：
- "Crush这周要加班" 只在 dynamic_intel，不在 layer1_info（因为"这周"=短期）
- "用户感觉：Crush对自己有好感" 在 crush_info（因为描述的是 Crush 的态度）
- "Crush表示自己有男朋友" 在 layer1_info（因为关系状态=长期）
<!-- END_TEMPLATE -->

---

<!-- TEMPLATE: task_reasoning -->
## 你的任务

根据任务思考记录，生成或更新任务摘要。

## 当前摘要

__CURRENT_SUMMARY__

## 新的思考记录

__REASONING_TEXT__

## 输出要求

生成简练的任务执行摘要（50字以内），概括主要进展和关键判断。
如果已有摘要，将新信息融合进去。

直接输出摘要文本，不要包含其他内容。
<!-- END_TEMPLATE -->
