# Crushe AI Agent 架构设计文档

> **版本**：v1.3  
> **更新日期**：2024-12  
> **技术栈**：LangGraph
> 
> **v1.4 更新**：
> - **Skill 加载改为 LangChain Tool-Use 机制**：废弃两阶段 API 调用，改用 LLM 原生工具调用
> - **新增 `load_skill_instructions` 工具**：LLM 自主决定何时加载 Skill 完整指令
> - **简化 Agent 代码**：移除手动两阶段逻辑，由 LangGraph ToolNode 自动处理
> - **更符合 Claude 设计理念**：一次 API 调用内完成「判断 → 加载 → 执行」闭环
> 
> **v1.3 更新**：
> - **主 Agent 支持 ask_user**：主 Agent 可以像子 Agent 一样提问并暂停，用户回答后恢复执行
> - **移除固定流程**：再决策逻辑改为灵活判断，不再强制"现状→规划→指南"流程
> - **新增咨询 Skills**：解答情感疑惑 Skill、情感陪伴 Skill
> - **Skill 基于 Anthropic 设计**：渐进式披露（Progressive Disclosure），平时只加载元数据，需要时展开完整 prompt
> 
> **v1.2 更新**：
> - 优化回复机制：主 Agent 和子 Agent 都可回复，回复为可选项
> - 新增消息累积机制（pending_responses）
> - 新增子 Agent 完成信号（completion_status, result_summary）
> - 更新 LangGraph 实现建议，支持恢复执行

---

## 一、架构总览

Crushe 采用「主 Agent + 子 Agent + 通用 Skills」的 Agentic 架构，以主 Agent 作为决策中枢，协调多个专业子 Agent 完成用户的情感咨询全流程。所有 Agent 共享一套通用 Skills（如提问、信息收集等），实现能力复用。

```
┌─────────────────────────────────────────────────────────────────────┐
│                          用户输入层                                  │
│  [文字消息] [问题回复] [行动反馈] [聊天截图]                           │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     前置路由层（可选，小模型）                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                          │
│  │ 风控过滤  │  │ 闲聊分流  │  │ 业务识别  │                          │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                          │
│       │拦截         │小模型回复    │转发                              │
└───────┴─────────────┴─────────────┴─────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    决策中枢层（主 Agent）                             │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  1. 快速意图分类（智能降级）                                    │   │
│  │     → 纯咨询/情绪 → 轻量回复                                   │   │
│  │     → 可能触发行动 → 完整决策流程                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  2. 可选：过渡回复（如需调用子 Agent，可先说过渡语）            │   │
│  │     例："让我来更新一下你们的情感现状..."                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  3. 决策下一步行动                                             │   │
│  │     → 调用子 Agent / 使用 Skill / 结束本轮                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  4. 子 Agent 执行（可直接与用户交互：提问、展示结果）           │   │
│  │     → 完成后返回主 Agent，附带完成信号                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  5. 子 Agent 返回 → 主 Agent 再决策（循环或结束）              │   │
│  │     → 可选：后续回复（如"需要我帮你制定行动指南吗？"）          │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         子 Agent 层                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                          │
│  │现状分析   │  │行动规划   │  │行动指南   │                          │
│  │ Agent    │  │ Agent    │  │ Agent    │                          │
│  └──────────┘  └──────────┘  └──────────┘                          │
│       │               │               │                             │
│       └───────────────┼───────────────┘                             │
│                       ▼                                             │
│              ┌─────────────────┐                                    │
│              │  共享 Skills 层  │                                    │
│              │  ┌───────────┐  │                                    │
│              │  │ 提问 Skill │  │                                    │
│              │  └───────────┘  │                                    │
│              └─────────────────┘                                    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         共享上下文层                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ 用户情报  │  │ 现状报告  │  │ 行动规划  │  │ 行动指南  │            │
│  │ Profile  │  │ Status   │  │ Plan     │  │ Guide    │            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                    嘴替模块（独立于主架构）                            │
│                                                                     │
│  [用户聊天记录] ──┬──→ [嘴替 Agent] ──→ [话术建议]                   │
│                  │         ↑                                        │
│                  │    读取共享上下文                                  │
│                  │                                                  │
│                  └──→ [同步决策 Agent] ──→ 判断是否触发看板更新        │
│                              │                                      │
│                              └──→ [主 Agent] (如需更新)              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、核心设计理念：Agent + Skills

### 2.1 设计理念

借鉴 Claude 的 Skills 设计理念，将「提问」等通用能力抽象为 **Skill**，而非独立的 Agent。

**Agent vs Skill 的区别**：

| 维度 | Agent | Skill |
|:---|:---|:---|
| **定位** | 独立的执行单元，有明确的输入输出 | 可复用的能力模块，被 Agent 调用 |
| **控制权** | 可以接管对话流程 | 不改变控制流，只提供能力 |
| **上下文** | 有自己的专属上下文 | 共享调用者的上下文 |
| **示例** | 现状分析 Agent、行动规划 Agent | 提问 Skill、信息收集 Skill |

### 2.2 为什么不用「提问 Agent」？

原方案中，「提问 Agent」需要通过复杂的「委托模式」接管对话：

```
主Agent → 委托 → 提问Agent → 多轮对话 → 返回 → 主Agent再决策
```

**问题**：
1. 控制流复杂，增加工程实现难度
2. 上下文切换成本高
3. 每个需要提问的 Agent 都要走这个链路

**改进方案**：将「提问」作为 Skill，任何 Agent 都可以直接调用：

```
任意Agent执行任务
    │
    └── 发现信息不足 → 调用「提问 Skill」→ 输出问题 → 等待用户回答 → 继续执行
```

---

## 三、各层职责定义

### 3.1 前置路由层（可选）

| 职责 | 说明 | 优先级 |
|:---|:---|:---|
| 风控过滤 | 识别敏感词、违规内容，直接拦截 | P0 (后续实现) |
| 闲聊分流 | 纯情绪发泄或无关话题，小模型直接回复 | P2 (成本优化) |
| 业务识别 | 其余全部转发给主 Agent | 默认行为 |

**建议**：MVP 阶段可跳过，先让主 Agent 处理全部流量。

---

### 3.2 主 Agent（决策中枢）

主 Agent 是整个系统的核心，负责：
1. **决策调度**：判断下一步调用哪个子 Agent
2. **可选回复**：根据上下文判断是否需要说话
   - **过渡回复**：调用子 Agent 前的引导语（如"让我来分析一下..."）
   - **后续回复**：子 Agent 返回后的跟进（如"需要我帮你制定行动指南吗？"）
   - **直接回复**：不需要调用子 Agent 时的完整回答
3. **咨询回答**：融合咨询能力，直接回答用户追问
4. **使用 Skills**：在需要时直接调用通用 Skill（如提问）
5. **检测行动完成**：从对话中发现用户已完成行动指南，自动标记并触发归档

> **注意**：主 Agent **不再负责信息提取**，信息提取由整理 Agent 在归档时统一处理。

> **核心原则**：回复是可选的，主 Agent 需要根据上下文判断是否需要说话。避免"为了回复而回复"。

#### 3.2.1 智能降级机制

为避免主 Agent 任务过重，引入「快速意图分类」：

```
用户输入
    │
    ▼
┌─────────────────────────┐
│ 快速意图分类（轻量判断）   │
│                         │
│ 分类结果：               │
│ - CONSULT_ONLY: 纯咨询   │
│ - EMOTION_VENT: 情绪发泄 │
│ - ACTION_TRIGGER: 触发行动│
│ - INFO_UPDATE: 信息更新   │
└───────────┬─────────────┘
            │
    ┌───────┴───────┐
    │               │
    ▼               ▼
┌────────┐    ┌────────────┐
│轻量回复 │    │完整决策流程 │
│模块    │    │            │
└────────┘    └────────────┘
```

**关键设计**：
- 「快速意图分类」应使用较短的 Prompt，快速判断
- 判断准确性是核心指标，需要持续监控和优化
- 边界 case 宁可误判为「触发行动」，也不要漏掉重要信息

#### 3.2.2 主 Agent 输入

```json
{
  "user_message": "用户当前消息",
  "conversation_history": "对话历史摘要",
  "current_state": "当前业务阶段",
  "user_profile": "用户情报摘要",
  "status_report": "现状分析报告（如有）",
  "action_plan": "行动规划（如有）",
  "action_guide": "行动指南（如有）"
}
```

#### 3.2.3 主 Agent 输出

```json
{
  "user_response": "给用户的回复（可选，可为 null）",
  "next_action": {
    "type": "CALL_AGENT | USE_SKILL | END_TURN",
    "target": "STATUS | PLAN | GUIDE | ASK_QUESTION | null",
    "params": {}
  }
}
```

**回复策略**：
- `user_response` 可以为 `null`，表示本轮主 Agent 不需要说话
- 调用子 Agent 时：可选过渡语（如"让我帮你分析一下..."）
- 子 Agent 返回后再决策时：可选后续回复（如"需要我帮你制定行动指南吗？"）
- `END_TURN` 时：通常需要回复，但如果子 Agent 已经完整回复了，也可以不说

#### 3.2.4 决策逻辑伪代码

```python
def main_agent_decision(user_input, context, from_sub_agent=False):
    """
    主 Agent 决策逻辑
    
    Args:
        user_input: 用户输入
        context: 上下文
        from_sub_agent: 是否是子 Agent 返回后的再决策
    """
    # Step 1: 快速意图分类（仅首次处理用户输入时）
    if not from_sub_agent:
        intent = quick_classify(user_input)
        
        if intent in ["CONSULT_ONLY", "EMOTION_VENT"]:
            # 轻量回复，不触发子 Agent
            return {"response": light_response(user_input, context), "action": end_turn()}
    
    # Step 2: 判断是否需要回复
    # 回复是可选的，根据上下文决定
    response = None
    
    if should_respond_before_action(context):
        # 需要过渡语，如"让我帮你分析一下..."
        response = generate_transition_response(context)
    
    if from_sub_agent and should_respond_after_sub_agent(context):
        # 子 Agent 返回后的跟进回复，如"需要我帮你制定行动指南吗？"
        response = generate_followup_response(context)
    
    # Step 3: 决策下一步
    if need_more_info_for_decision(context):
        return {"response": response, "action": use_skill("ASK_QUESTION", goal="决策所需信息")}
    
    if need_status_analysis(context):
        return {"response": response, "action": call_agent("STATUS")}
    
    if need_plan_update(context):
        return {"response": response, "action": call_agent("PLAN")}
    
    if need_guide_update(context):
        return {"response": response, "action": call_agent("GUIDE")}
    
    # Step 4: 结束本轮
    if response is None:
        # 如果之前没回复，结束时需要回复
        response = generate_final_response(context)
    
    return {"response": response, "action": end_turn()}
```

**关键点**：
- `response` 可以为 `None`，表示本轮主 Agent 不说话
- 子 Agent 返回后，主 Agent 通过 `from_sub_agent=True` 进入再决策
- 主 Agent 需要判断：子 Agent 是否已经完整回复了？是否需要额外跟进？

---

### 3.3 子 Agent 层

子 Agent 不仅负责执行专业任务，还可以**直接与用户交互**。

#### 3.3.0 子 Agent 通用机制

**回复能力**：
- 子 Agent 可以直接给用户发消息（提问、展示结果、确认信息等）
- 回复内容由子 Agent 根据任务需要自行决定
- 子 Agent 的回复会直接展示给用户

**返回主 Agent**：
- 子 Agent 完成任务后，需要返回主 Agent 进行再决策
- 返回时附带「完成信号」，告知主 Agent 任务状态

```json
{
  "user_response": "给用户的回复（可选）",
  "completion_status": "COMPLETED | NEED_MORE_INFO | BLOCKED",
  "result_summary": "任务结果摘要（供主 Agent 决策用）",
  "updated_data": { ... }  // 更新的业务数据（如 status_report）
}
```

**示例对话**：
```
用户: "crush约我明天去约会！"
  │
  ▼
主 Agent: 
  - user_response: "哇，这太好了！看来你们的情感状态要更新了，让我来分析一下..."
  - next_action: call_agent("STATUS")
  │
  ▼
现状分析 Agent:
  - user_response: "在更新之前，我需要确认几个问题：crush是约你单独约会吗？为什么约你？"
  - [等待用户回答]
  │
  ▼
用户: "是单独的，她说想一起看电影"
  │
  ▼
现状分析 Agent:
  - user_response: "明白了！我已经帮你更新了情感现状～"
  - completion_status: "COMPLETED"
  - result_summary: "用户与 crush 关系升温，即将进行首次单独约会"
  - 返回主 Agent
  │
  ▼
主 Agent:
  - user_response: "恭喜你呀！你们要开始第一次约会了，需要我帮你制定一个约会行动指南吗？"
  - next_action: end_turn (等待用户回复)
```

#### 3.3.0.1 消息累积机制

当一轮交互中有多个 Agent 产生回复时，需要处理消息累积：

**规则**：
1. 每个 Agent 的 `user_response` 独立存储
2. 本轮结束时（`END_TURN`），将所有累积的消息**按顺序**发送给用户
3. 前端可以选择：合并显示 or 分条显示（推荐分条，更自然）

**示例**：
```
本轮执行顺序：
1. 主 Agent: "让我来分析一下..."
2. 现状分析 Agent: "在分析前需要确认几个问题..."

累积消息队列: [
  { from: "main_agent", content: "让我来分析一下..." },
  { from: "status_agent", content: "在分析前需要确认几个问题..." }
]

发送给用户时：按顺序依次展示（或合并为一条）
```

**状态字段**：
```python
# 在 AgentState 中添加
pending_responses: list[dict]  # 累积的待发送消息
# 格式: [{"from": "agent_id", "content": "消息内容"}, ...]
```

#### 3.3.1 现状分析 Agent

| 属性 | 说明 |
|:---|:---|
| **触发条件** | 首次进入 / 关键信息变更 / 主 Agent 判断需要重新诊断 |
| **输入** | 用户情报 + 聊天记录（如有） |
| **输出** | 用户问题诊断 + ACR 阶段判断 + L/T 线定位 |
| **可用 Skills** | 提问 Skill（发现信息不足时使用） |
| **对应模块** | `Strategy_Library/01_Modules/Status_Analysis/` |

**执行流程**：
```
现状分析Agent开始执行
    │
    ├── 检查信息是否足够
    │       │
    │       ├── 足够 → 直接生成分析报告
    │       │
    │       └── 不足 → 调用「提问 Skill」
    │                      │
    │                      ▼
    │               输出问题给用户
    │                      │
    │                      ▼
    │               等待用户回答
    │                      │
    │                      ▼
    │               继续分析（可能再次提问）
    │
    └── 生成分析报告 → 返回主 Agent
```

#### 3.3.2 行动规划 Agent

| 属性 | 说明 |
|:---|:---|
| **触发条件** | 现状分析完成后 / 关键情况变更需要调整战略 |
| **输入** | 现状分析报告 + 用户情报 |
| **输出** | 宏观战略规划（Campaign Plan） |
| **可用 Skills** | 提问 Skill（需要更多信息来制定规划时使用） |
| **粒度** | 战略层：阶段性目标、核心策略方向 |
| **示例** | 「通过线上保持联系，寒假见面时尝试升温」 |

#### 3.3.3 行动指南 Agent

| 属性 | 说明 |
|:---|:---|
| **触发条件** | 行动规划确认后 / 用户需要具体执行指导 |
| **输入** | 行动规划 + 当前阶段 + 用户情报 |
| **输出** | 具体 SOP 任务包 |
| **可用 Skills** | 提问 Skill（需要更多细节来生成指南时使用） |
| **对应模块** | `Strategy_Library/01_Modules/Action_Guide/` |
| **粒度** | 战术层：下一步做什么、怎么做、话术示例 |
| **示例** | 「今晚发一条朋友圈，内容建议...」 |

---

### 3.4 Skills 层

Skills 是所有 Agent 共享的通用能力模块。**v1.4 起采用 LangChain Tool-Use 机制**，LLM 通过工具调用自主加载 Skill 指令。

#### 3.4.0 Skill 加载机制（Tool-Use）

**核心设计**：LLM 自主决定是否需要某个 Skill，通过调用 `load_skill_instructions` 工具获取完整指令。

```
┌─────────────────────────────────────────────────────────────┐
│                    LLM 单次 API 调用                         │
│                                                             │
│  1. LLM 收到用户消息 + Skills 元数据                          │
│                    │                                        │
│                    ▼                                        │
│  2. LLM 判断：需要 inquiry_skill 的完整指令                   │
│                    │                                        │
│                    ▼                                        │
│  3. LLM 发起 tool_call: load_skill_instructions("inquiry")  │
│                    │                                        │
│                    ▼                                        │
│  4. ToolNode 执行工具，返回完整 Skill prompt                  │
│                    │                                        │
│                    ▼                                        │
│  5. LLM 根据完整指令生成 inquiry_card                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**`load_skill_instructions` 工具定义**：

```python
from langchain.tools import tool
from utils.prompt_loader import load_prompt

@tool
def load_skill_instructions(skill_id: str):
    """
    当识别到用户需要咨询、提问或陪伴时，调用此工具获取该技能的详细执行指令。
    参数 skill_id 必须是: inquiry_skill, consult_answer_skill, emotion_support_skill 之一。
    """
    return load_prompt(skill_id)
```

**LangGraph 工作流集成**：

```python
from langgraph.prebuilt import ToolNode
from skills.tool import load_skill_instructions

# 创建 ToolNode
skill_tools = ToolNode([load_skill_instructions])

# 在工作流中添加节点
workflow.add_node("skill_tools", skill_tools)

# 路由逻辑：检测 tool_calls
def route_after_agent(state):
    messages = state.get("messages", [])
    if messages and hasattr(messages[-1], "tool_calls") and messages[-1].tool_calls:
        return "skill_tools"
    # ... 其他路由逻辑
```

**vs 旧方案（两阶段 API 调用）对比**：

| 维度 | 旧方案（v1.3） | 新方案（v1.4） |
|------|---------------|---------------|
| **API 调用次数** | 2 次（判断 + 执行） | 1 次（闭环） |
| **Skill 加载方式** | 工程代码 if/else 判断 | LLM 自主 tool_call |
| **代码复杂度** | 高（两阶段逻辑） | 低（ToolNode 自动处理） |
| **灵活性** | 依赖硬编码判断 | LLM 动态决策 |
| **符合 Claude 理念** | 部分符合 | 完全符合 |

#### 3.4.1 提问 Skill (Ask Question)

| 属性 | 说明 |
|:---|:---|
| **定位** | 通用的引导式提问能力 |
| **调用者** | 主 Agent、现状分析 Agent、行动规划 Agent、行动指南 Agent |
| **加载方式** | LLM 调用 `load_skill_instructions("inquiry_skill")` |
| **输出** | 格式化的问题卡片（inquiry_card） |
| **特点** | 不改变控制流，只生成问题内容 |

**Skill 元数据（提供给 LLM 判断用）**：

```markdown
- **提问引导 (inquiry_skill)**：生成结构化的引导性问题，帮助收集用户信息
  （当需要向用户提问以收集更多信息时使用）
```

**LLM 调用示例**：

```python
# LLM 绑定工具
llm = get_llm().bind_tools([load_skill_instructions])

# LLM 在需要时自主调用
# response.tool_calls = [{"name": "load_skill_instructions", "args": {"skill_id": "inquiry_skill"}}]
```

#### 3.4.2 多轮提问的处理

当一个 Agent 需要多轮提问时，通过状态管理实现：

```
Agent 执行
    │
    ├── LLM 判断信息不足，调用 load_skill_instructions("inquiry_skill")
    │       │
    │       ▼
    │   ToolNode 返回完整 Skill 指令
    │       │
    │       ▼
    │   LLM 生成 inquiry_card，设置 resume_point
    │       │
    │       ▼
    │   工作流进入 wait_user_input，本轮结束
    │       │
    │       ▼
    │   用户回答后，Router 恢复对应 Agent
    │       │
    │       ├── 信息还是不足 → LLM 再次调用工具
    │       │
    │       └── 信息足够 → 继续执行任务
    │
    └── 任务完成，返回主 Agent
```

**兜底机制**：
- 最大提问轮次限制（如 3 轮）
- 超过后强制使用已有信息继续执行

---

### 3.5 嘴替模块（独立架构）

嘴替模块独立于主 Agent 架构运行，但共享上下文。

#### 3.5.1 设计原因

- 嘴替是**高频功能**，用户可能每天使用多次
- 如果每次都经过主 Agent 决策，会增加延迟和成本
- 但聊天记录可能包含重要信息，需要同步判断

#### 3.5.2 架构设计

```
用户输入聊天记录
        │
        ├────────────────────┐
        │                    │
        ▼                    ▼
┌──────────────┐    ┌──────────────────┐
│  嘴替 Agent   │    │  同步决策 Agent   │
│              │    │  (轻量判断器)     │
│  读取:       │    │                  │
│  - 用户情报   │    │  判断:           │
│  - 现状报告   │    │  - 是否有关键变更？│
│  - 行动规划   │    │  - 是否需要更新？  │
│              │    │                  │
└──────┬───────┘    └────────┬─────────┘
       │                     │
       ▼                     ▼
┌──────────────┐    ┌──────────────────┐
│  话术建议     │    │  触发主Agent更新  │
│  (返回用户)   │    │  (如需要)        │
└──────────────┘    └──────────────────┘
```

#### 3.5.3 同步决策 Agent

| 属性 | 说明 |
|:---|:---|
| **职责** | 判断聊天记录是否包含「关键信息变更」 |
| **输入** | 用户输入的聊天记录 + 当前现状/规划摘要 |
| **输出** | 是否触发更新 + 变更类型 |
| **特点** | 轻量、快速，不阻塞嘴替返回 |

---

## 四、业务流程映射

### 4.1 首次进入流程

| 业务步骤 | 架构执行者 | 说明 |
|:---|:---|:---|
| 用户自由表达 | 主 Agent | 接收、简短回应、判断信息是否足够 |
| 引导补充信息 | 主 Agent (使用提问 Skill) 或 现状分析 Agent (使用提问 Skill) | 任何需要信息的 Agent 都可以直接提问 |
| 产出问题/ACR 阶段 | 现状分析 Agent | 执行过程中可能使用提问 Skill |
| 用户确认现状 | 主 Agent | 接收反馈，决定是否调整 |
| 产出行动规划 | 行动规划 Agent | 执行过程中可能使用提问 Skill |
| 用户确认规划 | 主 Agent | 接收反馈 |
| 产出行动指南 | 行动指南 Agent | 执行过程中可能使用提问 Skill |
| 后续追问/调整 | 主 Agent → 对应子 Agent | 主 Agent 判断影响范围 |

### 4.2 日常使用流程

| 场景 | 架构执行者 | 说明 |
|:---|:---|:---|
| 用户使用嘴替 | 嘴替 Agent + 同步决策 Agent | 独立运行，可能触发看板更新 |
| 用户追问/调整 | 主 Agent | 智能降级判断是否需要触发子 Agent |
| 用户反馈执行结果 | 主 Agent → 对应子 Agent | 判断是否更新规划/指南 |
| 情况发生变化 | 主 Agent → 现状分析 Agent → ... | 重新诊断，可能级联更新 |

### 4.3 提问场景示例

**场景**：用户首次进入，信息不足

```
用户: 我喜欢一个女生，她好像对我有点意思

主Agent: 
  - 回应: "听起来是个不错的开始！为了帮你更好地分析情况..."
  - 决策: 调用现状分析 Agent

现状分析Agent:
  - 检查信息: 缺少关键信息（认识渠道、互动频率、具体表现）
  - 使用提问 Skill: "你们是怎么认识的？平时有什么互动？"

用户: 我们是同事，经常一起吃午饭

现状分析Agent:
  - 继续检查: 还缺少信息（她的具体表现）
  - 再次使用提问 Skill: "她有哪些表现让你觉得对你有意思？"

用户: 她会主动找我聊天，有时候会碰我手臂

现状分析Agent:
  - 信息足够，生成分析报告
  - 返回主 Agent

主Agent:
  - 展示分析报告给用户
  - 决策下一步...
```

---

## 五、状态管理

### 5.1 业务阶段定义

主 Agent 需要感知用户当前所处的「业务阶段」：

```python
class UserStage(Enum):
    # Onboarding 阶段
    ONBOARDING_FREE_EXPRESSION = "onboarding_free"      # 首次进入，自由表达
    ONBOARDING_INFO_GATHERING = "onboarding_gathering"  # 引导补充信息中
    
    # 诊断阶段
    STATUS_ANALYSIS_PENDING = "status_pending"          # 等待生成现状分析
    STATUS_ANALYSIS_CONFIRMING = "status_confirming"    # 用户确认现状中
    
    # 规划阶段
    PLAN_PENDING = "plan_pending"                       # 等待生成行动规划
    PLAN_CONFIRMING = "plan_confirming"                 # 用户确认规划中
    
    # 指南阶段
    GUIDE_PENDING = "guide_pending"                     # 等待生成行动指南
    GUIDE_EXECUTING = "guide_executing"                 # 用户执行指南中（主流程完成）
    
    # 开放阶段
    CONSULTING = "consulting"                           # 开放咨询模式
```

### 5.2 Agent 执行状态

当 Agent 使用提问 Skill 等待用户回答时，需要保存执行状态：

```python
class AgentExecutionState(TypedDict):
    # 恢复执行相关
    current_agent: Optional[str]     # 当前暂停的 Agent (status_agent/plan_agent/guide_agent)
    agent_resume_point: Optional[str]  # 恢复点标识
    collected_info: dict             # 已收集的信息
    question_count: int              # 已提问次数
    max_questions: int               # 最大提问次数（默认 3）
    
    # 消息累积
    pending_responses: list[dict]    # 累积的待发送消息
    # 格式: [{"from": "agent_id", "content": "消息内容"}, ...]
    
    # 子 Agent 完成信号（子 Agent 返回主 Agent 时设置）
    completion_status: Optional[str]  # COMPLETED / NEED_MORE_INFO / BLOCKED / None
    result_summary: Optional[str]     # 任务结果摘要（供主 Agent 决策用）
```

### 5.3 状态转换图

```
ONBOARDING_FREE_EXPRESSION
         │
         ▼ (信息不足)
ONBOARDING_INFO_GATHERING ◄──┐
         │                   │
         │ (信息足够)        │ (Agent 使用提问 Skill)
         ▼                   │
STATUS_ANALYSIS_PENDING ─────┘
         │
         ▼
STATUS_ANALYSIS_CONFIRMING
         │
         ├── (不满意) → 调整 → 返回
         │
         ▼ (满意)
PLAN_PENDING
         │
         ▼
PLAN_CONFIRMING
         │
         ├── (不满意) → 调整 → 返回
         │
         ▼ (满意)
GUIDE_PENDING
         │
         ▼
GUIDE_EXECUTING ◄───────────────┐
         │                      │
         ├── (追问) → CONSULTING │
         │                      │
         └── (执行反馈) → 判断 ──┘
                          │
                          └── (重大变化) → STATUS_ANALYSIS_PENDING
```

---

## 六、LangGraph 实现建议

### 6.1 Graph 结构

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Literal, Optional
from skills.tool import load_skill_instructions

# 定义状态
class AgentState(TypedDict):
    user_message: str
    messages: list                  # LangChain 消息历史（用于 Tool-Use）
    conversation_history: list
    user_profile: dict
    status_report: dict
    action_plan: dict
    action_guide: dict
    
    # Agent 执行状态（用于恢复执行）
    current_agent: Optional[str]    # 当前暂停的 Agent (status_agent/plan_agent/guide_agent/None)
    agent_resume_point: Optional[str]  # Agent 恢复点
    question_count: int             # 已提问次数
    max_questions: int              # 最大提问次数（默认 3）
    collected_info: dict            # 本轮收集的信息
    
    # 消息累积
    pending_responses: list[dict]   # 累积的待发送消息
    
    # 子 Agent 完成信号
    completion_status: Optional[str]  # COMPLETED / NEED_MORE_INFO / None
    result_summary: Optional[str]     # 任务结果摘要

# 构建 Graph
workflow = StateGraph(AgentState)

# 添加节点（包含 ToolNode）
workflow.add_node("router", router_node)
workflow.add_node("main_agent", main_agent_node)
workflow.add_node("status_agent", status_agent_node)
workflow.add_node("plan_agent", plan_agent_node)
workflow.add_node("guide_agent", guide_agent_node)
workflow.add_node("wait_user_input", wait_user_input_node)
workflow.add_node("skill_tools", ToolNode([load_skill_instructions]))  # v1.4 新增

# 设置入口点
workflow.set_entry_point("router")

# ========== Router 后的路由 ==========
# 关键：如果有 current_agent，说明需要恢复之前的 Agent
def route_after_router(state):
    if state.get("route_to") == "end":
        return "end"
    
    # 检查是否需要恢复之前的 Agent
    current_agent = state.get("current_agent")
    if current_agent and state.get("agent_resume_point"):
        return current_agent  # 恢复到对应的子 Agent
    
    return "main_agent"

workflow.add_conditional_edges(
    "router",
    route_after_router,
    {
        "main_agent": "main_agent",
        "status_agent": "status_agent",
        "plan_agent": "plan_agent",
        "guide_agent": "guide_agent",
        "end": END,
    }
)

# ========== 主 Agent 后的路由 ==========
def route_after_main_agent(state):
    next_action = state.get("next_action", "end_turn")
    if next_action == "call_status":
        return "status_agent"
    elif next_action == "call_plan":
        return "plan_agent"
    elif next_action == "call_guide":
        return "guide_agent"
    return "end"  # ask_user 和 end_turn 都结束本轮

workflow.add_conditional_edges(
    "main_agent",
    route_after_main_agent,
    {
        "status_agent": "status_agent",
        "plan_agent": "plan_agent",
        "guide_agent": "guide_agent",
        "end": END,
    }
)

# ========== 子 Agent 后的路由（v1.4 含 Tool-Use 支持）==========
def route_after_agent(state):
    """通用路由：检测 tool_calls 或提问状态"""
    messages = state.get("messages", [])
    
    # 如果有 tool_calls，先去 skill_tools
    if messages and hasattr(messages[-1], "tool_calls") and messages[-1].tool_calls:
        return "skill_tools"
    
    # 如果需要提问，等待用户输入
    if state.get("current_agent") and state.get("agent_resume_point"):
        return "wait_user_input"
    
    return "main_agent"  # 任务完成，回主 Agent 再决策

# 所有 Agent 共用统一路由逻辑
for agent in ["main_agent", "status_agent", "plan_agent", "guide_agent"]:
    workflow.add_conditional_edges(agent, route_after_agent,
        {"skill_tools": "skill_tools", "wait_user_input": "wait_user_input", "main_agent": "main_agent"})

# skill_tools 执行完后返回调用它的 Agent（通过 messages 追溯）
workflow.add_edge("skill_tools", "main_agent")  # 简化：统一返回 main_agent

# wait_user_input 直接结束本轮，下一轮从 router 开始
workflow.add_edge("wait_user_input", END)
```

**关键设计**：
- `wait_user_input` 节点结束本轮，用户回答后从 `router` 重新开始
- `router` 检查 `current_agent`，如果有则恢复到对应子 Agent
- 子 Agent 完成后回到 `main_agent` 进行再决策

### 6.2 Agent 节点实现示例（v1.4 Tool-Use 版本）

```python
from skills.tool import load_skill_instructions

def status_agent_node(state: AgentState) -> AgentState:
    """现状分析 Agent（v1.4 使用 Tool-Use）"""
    
    # 绑定 Skill 工具
    llm = get_llm().bind_tools([load_skill_instructions])
    
    # 如果是恢复执行，先合并用户的回答
    if state.get("agent_resume_point") == "status_continue":
        state["collected_info"].update(parse_user_answer(state["user_message"]))
    
    # 构建 Prompt（只包含 Skill 元数据）
    prompt = f"""
    {status_agent_prompt}
    
    ## 可用技能（如需要可调用 load_skill_instructions 获取完整指令）
    - inquiry_skill: 生成引导性问题，收集用户信息
    - consult_answer_skill: 回答情感咨询问题
    - emotion_support_skill: 提供情感陪伴
    
    当你判断需要某个技能时，调用 load_skill_instructions(skill_id) 获取完整指令。
    """
    
    # LLM 自主决定是否调用工具
    response = llm.invoke(prompt)
    
    # 如果有 tool_calls，LangGraph ToolNode 会自动处理
    # 工具返回后会再次进入此节点，此时 response 包含工具结果
    
    if response.tool_calls:
        # 返回状态，让 ToolNode 执行工具
        return {
            **state,
            "messages": state.get("messages", []) + [response],
        }
    
    # 解析最终结果
    result = parse_response(response.content)
    
    if result.get("inquiry_card"):
        # 需要提问，设置暂停状态
        return {
            **state,
            "current_agent": "status_agent",
            "agent_resume_point": "status_continue",
            "inquiry_card": result["inquiry_card"],
            "question_count": state.get("question_count", 0) + 1
        }
    
    # 生成分析报告
    return {
        **state,
        "status_report": result.get("status_report"),
        "current_agent": None,
        "agent_resume_point": None,
    }
```

**关键变化**：
1. LLM 通过 `bind_tools()` 绑定 `load_skill_instructions` 工具
2. LLM 自主判断何时需要调用工具（不再是工程代码 if/else）
3. ToolNode 自动执行工具调用并返回结果
4. 代码大幅简化，逻辑更清晰

---

## 七、关键设计要点

1. **Agent + Skills 分离**：Agent 负责业务逻辑，Skills 提供通用能力
2. **LLM 原生 Tool-Use（v1.4）**：通过 `bind_tools()` 让 LLM 自主决定何时加载 Skill
3. **状态驱动恢复**：Agent 使用 Skill 后暂停，用户回答后从 resume_point 继续
4. **智能降级**：通过快速意图分类，减轻主 Agent 负担，提升响应速度
5. **嘴替独立**：高频功能独立运行，但通过「同步决策 Agent」保持数据一致性
6. **提问兜底**：限制最大提问轮次，避免用户流失
7. **单次 API 闭环**：一次 API 调用内完成「判断 → 加载 → 执行」，符合 Claude 设计理念

---

## 八、待优化项

- [ ] **智能降级准确性**：需要建立评估机制，持续监控意图分类的准确率
- [ ] **提问 Skill 质量**：提问的自然度、针对性需要持续优化
- [ ] **多轮提问体验**：避免让用户感觉被"审问"，需要设计好提问节奏
- [ ] **同步决策延迟**：嘴替的同步决策是否需要异步执行，避免阻塞用户体验
- [ ] **并发处理**：用户同时使用嘴替和主流程时的状态一致性

---

## 九、与现有模块的关系

| 架构组件 | 对应现有模块 | 关系说明 |
|:---|:---|:---|
| 主 Agent | Decision Hub | 主 Agent 承担 Decision Hub 的核心决策职责 |
| 现状分析 Agent | Status_Analysis | 直接对应 |
| 行动规划 Agent | (新增) | 从 Action_Guide 中拆分出战略层 |
| 行动指南 Agent | Action_Guide | 直接对应，专注战术层 SOP |
| 提问 Skill | Pre_Question_Gen / Post_Question_Gen | 整合现有提问生成模块为通用 Skill |
| 嘴替 Agent | Chat_Analysis | 直接对应 |
| 同步决策 Agent | Decision Hub 的 Satellite 模块 | 轻量化的变更检测 |
