# Organize Agent Prompts（提纯/归档/压缩）v1

> 说明：本文件用于 **上下文工程** 的“提纯/归档”LLM Prompt 模板。  
> 使用方式：代码读取本文件的指定模板块，然后用字符串替换写入变量（使用 `__PLACEHOLDER__` 形式，避免与 JSON 花括号冲突）。

占位符约定：
- 行动指南：`__GUIDE_CURRENT_TASK__`、`__GUIDE_FULL_CONTENT__`
- 现状报告：`__STATUS_STAGE__`、`__STATUS_SUMMARY_TEXT__`、`__STATUS_REPORT_CONTENT__`
- 行动规划：`__PLAN_GOAL__`、`__PLAN_STRATEGY__`、`__PLAN_CONTENT__`
- 对话压缩：`__CONVERSATION_TEXT__`
- 任务思考压缩：`__CURRENT_SUMMARY__`、`__REASONING_TEXT__`

---

<!-- TEMPLATE: action_guide -->
你是信息整理专家。请从以下已完成的行动指南中提取信息并生成摘要。

## 行动指南内容
任务：__GUIDE_CURRENT_TASK__
完整内容：
__GUIDE_FULL_CONTENT__

## 任务
1. 生成**中等摘要**（100-200字）：概括任务目标、核心策略、预期效果
2. 生成**一句话摘要**（20-30字）：一句话概括这个任务
3. 提取**高价值信息**：从中识别出对理解用户/Crush/双方关系有帮助的信息

## 输出格式（JSON）
```json
{
  "summary": "中等摘要内容",
  "one_liner": "一句话摘要",
  "extracted_info": {
    "user_info": "关于用户的新发现（如性格、行为模式），没有则为空",
    "crush_info": "关于Crush的新发现，没有则为空",
    "both_info": "关于双方关系的新发现，没有则为空"
  }
}
```
<!-- END_TEMPLATE -->

---

<!-- TEMPLATE: status_report -->
你是信息整理专家。请从以下现状分析报告中提取信息并生成摘要。

## 现状分析报告
关系阶段：__STATUS_STAGE__
原始总结：__STATUS_SUMMARY_TEXT__
完整报告：
__STATUS_REPORT_CONTENT__

## 任务
1. 生成**中等摘要**（100-200字）：概括关系阶段、核心问题、关键风险
2. 生成**一句话摘要**（20-30字）：一句话概括当前关系状态
3. 提取**高价值信息**：从诊断中识别出的关键洞察

## 输出格式（JSON）
```json
{
  "summary": "中等摘要内容",
  "one_liner": "一句话摘要",
  "extracted_info": {
    "user_info": "关于用户的分析结论（如依恋类型、沟通模式），没有则为空",
    "crush_info": "关于Crush的分析结论（如性格特征、态度倾向），没有则为空",
    "both_info": "关于双方关系的分析结论（如互动模式、问题根源），没有则为空"
  }
}
```
<!-- END_TEMPLATE -->

---

<!-- TEMPLATE: action_plan -->
你是信息整理专家。请从以下行动规划中提取信息并生成摘要。

## 行动规划
阶段性目标：__PLAN_GOAL__
核心策略：__PLAN_STRATEGY__
完整规划：
__PLAN_CONTENT__

## 任务
1. 生成**中等摘要**（100-200字）：概括目标、策略、关键阶段与原则
2. 生成**一句话摘要**（20-30字）：一句话概括这份规划
3. 提取**高价值信息**：从规划中识别出对理解用户/Crush/双方关系有帮助的信息

## 输出格式（JSON）
```json
{
  "summary": "中等摘要内容",
  "one_liner": "一句话摘要",
  "extracted_info": {
    "user_info": "关于用户的新发现/判断，没有则为空",
    "crush_info": "关于Crush的新发现/判断，没有则为空",
    "both_info": "关于双方关系的新发现/判断，没有则为空"
  }
}
```
<!-- END_TEMPLATE -->

---

<!-- TEMPLATE: conversation -->
你是信息整理专家。请从以下对话记录中提取信息并生成摘要。

## 对话记录
__CONVERSATION_TEXT__

## 任务
1. 生成**对话摘要**（50-100字）：概括对话的核心话题和关键结论
2. 提取**关键话题**：用 2-5 个词标签概括
3. 提取**高价值信息**：用户透露的新事实、情感状态变化等

## 输出格式（JSON）
```json
{
  "summary": "对话摘要内容",
  "key_topics": ["话题1", "话题2", "话题3"],
  "extracted_info": {
    "user_info": "用户透露的关于自己的信息，没有则为空",
    "crush_info": "用户提到的关于Crush的信息，没有则为空",
    "both_info": "用户提到的关于双方关系的信息，没有则为空"
  }
}
```
<!-- END_TEMPLATE -->

---

<!-- TEMPLATE: task_reasoning -->
你是信息整理专家。请根据以下任务思考记录，生成或更新任务摘要。

## 当前摘要
__CURRENT_SUMMARY__

## 新的思考记录
__REASONING_TEXT__

## 任务
生成一个新的、简练的任务执行摘要（50字以内），概括这个任务的主要进展和关键判断。
如果已有摘要，请将新信息融合进去。

## 输出
直接输出摘要文本，不要包含其他内容。
<!-- END_TEMPLATE -->

