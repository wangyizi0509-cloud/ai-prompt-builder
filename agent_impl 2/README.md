# Crushe AI Agent 实现

基于 LangGraph 的 AI 恋爱军师 Agent 架构实现。

> **v1.4 更新**：Skills 加载改用 LangChain Tool-Use 机制，LLM 自主决定何时加载完整指令。

## 目录结构

```
agent_impl/
├── main.py                    # 入口文件，提供交互式对话
├── config.py                  # LLM 配置（支持 DeepSeek/OpenAI/Claude）
├── requirements.txt           # 依赖包
├── env.example                # 环境变量示例
│
├── graph/
│   ├── state.py              # AgentState 状态定义
│   ├── workflow.py           # LangGraph 工作流编排（含 ToolNode）
│   └── nodes/
│       ├── router.py         # 前置路由节点
│       ├── main_agent.py     # 主 Agent 节点
│       ├── status_agent.py   # 现状分析 Agent 节点
│       ├── plan_agent.py     # 行动规划 Agent 节点
│       └── guide_agent.py    # 行动指南 Agent 节点
│
├── skills/
│   ├── __init__.py           # Skills 模块导出
│   ├── base.py               # Skill 基类
│   ├── inquiry.py            # 提问 Skill
│   ├── consult.py            # 咨询 Skill
│   └── tool.py               # load_skill_instructions 工具定义
│
├── prompts/                   # Prompt 独立维护
│   ├── main_agent.md
│   ├── status_agent.md
│   ├── plan_agent.md
│   ├── guide_agent.md
│   ├── inquiry_skill.md
│   ├── consult_answer_skill.md
│   └── emotion_support_skill.md
│
└── utils/
    └── prompt_loader.py      # Prompt 加载工具
```

## 快速开始

### 1. 安装依赖

```bash
cd agent_impl
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制示例配置
cp env.example .env

# 编辑 .env 文件，填入你的 API Key
```

支持的 LLM Provider：
- `deepseek`（默认）
- `openai`
- `claude`

### 3. 运行

```bash
python main.py
```

## 架构说明

> 详细架构设计请参考 `agent_architecture.md`

### Agent 层次（符合 agent_architecture.md）

```
[用户输入] 
     │
     ▼
[Router] ─── 风控/闲聊 ───→ [END]
     │
     ├── 有 current_agent ───→ [恢复对应子 Agent]
     │
     │ 无 current_agent（新对话）
     ▼
[Main Agent] ─── end_turn ───→ [END]
     │
     ├── call_status ──→ [Status Agent] ──┐
     ├── call_plan ────→ [Plan Agent] ───┼──→ [需要提问?]
     └── call_guide ───→ [Guide Agent] ──┘        │
                                                  ├── 是 → [Wait User Input] → [END]
                                                  │         (下轮从 Router 恢复)
                                                  └── 否 → [Main Agent] (再决策)
```

### 核心设计：子 Agent 恢复执行

当子 Agent 需要向用户提问时：

1. **暂停**: 子 Agent 设置 `current_agent` 和 `agent_resume_point`
2. **等待**: 工作流进入 `wait_user_input` 节点，本轮结束
3. **恢复**: 用户回答后，Router 检测到 `current_agent`，直接路由到对应子 Agent
4. **继续**: 子 Agent 从 `resume_point` 继续执行

**关键状态字段**:
- `current_agent`: 当前暂停的 Agent (`status_agent`/`plan_agent`/`guide_agent`)
- `agent_resume_point`: 恢复点标识
- `question_count`: 已提问次数（最多 3 次，防止过度提问）

### 状态流转

1. **onboarding_free**: 用户首次进入，自由表达
2. **onboarding_gathering**: 引导补充信息
3. **status_pending/confirming**: 生成/确认现状分析
4. **plan_pending/confirming**: 生成/确认行动规划
5. **guide_pending/executing**: 生成行动指南，用户执行中

### Skills（v1.4 Tool-Use 机制）

Skills 是共享能力模块，通过 LangChain Tool-Use 机制按需加载：

```python
# skills/tool.py
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

**LLM 绑定工具**：

```python
from skills.tool import load_skill_instructions

# Agent 节点中绑定工具
llm = get_llm().bind_tools([load_skill_instructions])

# LLM 自主决定是否调用工具
response = llm.invoke(prompt)

# 如果有 tool_calls，LangGraph ToolNode 自动处理
```

**工作流程**：
1. Prompt 只包含 Skills 元数据（简要描述）
2. LLM 判断需要某个 Skill 时，调用 `load_skill_instructions(skill_id)`
3. ToolNode 执行工具，返回完整 Skill prompt
4. LLM 根据完整指令生成结果

**Skill vs Agent 的区别**:
- **Agent**: 独立的执行单元，有明确的输入输出，可以接管对话流程
- **Skill**: 可复用的能力模块，被 Agent 通过 tool_call 加载，不改变控制流

## Prompt 维护

所有 Prompt 存放在 `prompts/` 目录下，使用 Markdown 格式。

修改 Prompt 后无需重启，会自动加载最新内容。

## 调试

设置环境变量 `DEBUG=1` 可以看到详细错误信息：

```bash
DEBUG=1 python main.py
```

## 扩展

### 添加新的 Skill

1. 在 `prompts/` 下添加 `{skill_name}.md` Prompt 文件
2. 在 `skills/tool.py` 的 `load_skill_instructions` 文档中添加新 skill_id
3. 在各 Agent 的 Prompt 元数据部分添加新 Skill 描述
4. （可选）在 `skills/` 下创建 Skill 类用于元数据管理

### 添加新的 Agent

1. 在 `graph/nodes/` 下创建新文件
2. 实现 Agent 节点函数，使用 `bind_tools([load_skill_instructions])`
3. 在 `graph/workflow.py` 中添加节点和边
4. 在 `prompts/` 下添加对应的 Prompt 文件

## 相关文档

- `agent_architecture.md` - 详细架构设计
- `SKILL_PROGRESSIVE_DISCLOSURE_DEMO.md` - Skill 渐进式披露机制演示
- `CONTEXT_ENGINEERING.md` - 上下文工程策略

