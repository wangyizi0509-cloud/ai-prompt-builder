# 统一 Message 输入规则草案 v1.0

> 创建时间：2026-01-23  
> 状态：草案  
> 目标：最精简、最干净、最高效的消息栈输入规范（在不改 SystemMessage 的前提下）

---

## 1. 消息栈顺序（固定）
```
[1] SystemMessage (Markdown)  # 不修改
[2] HumanMessage (Context Injection, XML)
[3] AIMessage (Virtual Ack)
[4~N] HumanMessage / AIMessage / ToolMessage  # 历史对话
[End] HumanMessage  # 当前用户输入
```

---

## 2. Context Injection XML Schema（草案）
> 仅定义结构与字段归属，具体内容格式见第 3 章。

```xml
<context version="1.0">
  <layer1>...</layer1>
  <layer2>
    <status_report>...</status_report>
    <action_plan>...</action_plan>
    <output_schema>...</output_schema>
    <dynamic_intel>...</dynamic_intel>
    <action_guides>...</action_guides>
    <history_summaries>...</history_summaries>
  </layer2>
  <task_system>
    <task_list>...</task_list>
    <bound_contexts>...</bound_contexts>
  </task_system>
</context>
```

---

## 3. 各区块最小输入规则

### 3.1 SystemMessage（Layer 0）
- **保持原样**：不修改、不裁剪。

---

### 3.2 Layer 1 静态情报（保留解释性文本）
**必留**
- 情报说明行（解释性文本需保留）
- 三个主体分区（用户 / Crush / 双方）
- 原子记忆：时间 + 来源 + 内容

**可删**
- 重复说明、装饰性文本

**格式**
```
## 情报概览
> 信息可靠性：事实 > AI分析 > 用户提供。当信息冲突时，以高可靠性信息为准。

### 用户
- [MM-DD HH:mm/事实] ...
- [MM-DD HH:mm/AI] ...
- [MM-DD HH:mm/用户] ...

### Crush
...

### 双方关系
...
```

---

### 3.3 Layer 2.a 现状报告 + 行动规划
**必留**
- 当前版本完整正文（report/plan）
- 更新时间 + 版本号

**可删**
- 额外解释性段落

**格式**
```
## 现状分析
### 当前报告
> 更新时间: MM-DD HH:mm | 版本: n
"""
{report_content}
"""

## 行动规划
### 当前规划
> 更新时间: MM-DD HH:mm | 版本: n
"""
{plan_content}
"""
```

---

### 3.4 输出格式规范（字段说明需简洁但清楚）
**必留**
- JSON schema 本体
- 必填字段的简洁说明

**可删**
- 过长字段解释
- 多余示例

**格式**
```
## 输出格式 (JSON)
{ ...schema... }

### 字段说明
- task_id: ...
- response: ...
```

---

### 3.5 Layer 2.b 动态情报 + 行动指南 + 历史摘要
#### 动态情报板
**必留**
- 基础解释行
- 时间 + 内容 + 置信度 + 原因
- 分组（用户/Crush）

**格式**
```
## 动态情报板
> 以下是近期的时效性信息，请务必参考。置信度越高越可信。

### 用户
- [MM-DD HH:mm] 内容 (置信度: X.XX - 原因)

### Crush
- [MM-DD HH:mm] 内容 (置信度: X.XX - 原因)
```

#### 行动指南
**必留**
- in_progress：完整正文（<=2条）
- 其他状态：简要摘要（summary/one_liner）

**格式**
```
## 行动指南
### 🔥 当前进行中
#### 【id】标题
"""
{guide_content}
"""

### 📋 其他指南
| ID | 状态 | 摘要 |
|----|------|------|
...
```

#### 历史摘要（报告/规划/指南）
**必留**
- 近期少量摘要（简短）

---

### 3.6 任务系统（保持原规则）
**必留**
- 当前任务 + 摘要
- 非 completed 最近 5 条
- completed 最近 3 条（completion_summary）
- 任务绑定上下文（按 type 分组）

**格式**
```
## 任务列表
### 当前任务
- **标题** [active]
  摘要：...

### 其他任务
| title | status | summary |
...

### 已完成任务
| title | completion_summary |
...

## 任务绑定上下文
### 类型A (n)
- [MM-DD HH:mm] 标题
...
```

---

## 4. Layer 3 历史对话（标准 message list）
### 4.1 历史摘要（ConversationSummary）
**必留**
- 时间 + 话题 + 一句话摘要

**格式**
```
## 历史摘要
- [MM-DD/话题1,话题2] 一句话摘要
```

### 4.2 任务笔记（Reasoning Notes）
**必留**
- 结论型 notes（<=8条）
- 时间戳

**格式**
```
## 任务笔记「任务名」
- [MM-DD HH:mm] 结论
```

### 4.3 最近对话（RecentTurns）
**规则**
- 采用标准 message list（role 已提供）
- 内容只保留 **时间戳 + 文本**，不再写 U/A/S

**格式**
```
[MM-DD HH:mm] 内容
```

### 4.4 系统通知
**规则**
- 作为 AIMessage 注入（可用 name="system_notice" 标注）
- 内容格式同上（仅时间戳 + 通知内容）

---

## 5. 提问卡片与回答（最省 token）
### 5.1 AI 提问卡片
**格式**
```
【提问】
Q1: 问题1
Q2: 问题2
```

### 5.2 用户选择选项（自动注入为用户输入）
**规则**
- 选项选择转换为“选项文本”写入
- 按题号对齐

**格式**
```
Q1: 选项文本
Q2: 选项文本
---
补充：...
```

---

## 6. Virtual Ack
**规则**
- 用一条空 AIMessage 进行语义隔离
- 不需要任何正文

---

## 7. Onboarding 特殊规则
- `preliminary_assessment` 仅用于前端展示，不进入后续模型输入。
