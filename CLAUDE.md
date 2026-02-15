# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供在此代码库中工作的指导。

## 项目概述

Crushe AI Agent 实现 - 基于 LangGraph v1.0.5 的 Python 情感咨询 AI 智能体系统。系统采用编排器-工作器架构，具备人机协作能力和跨会话状态持久化功能。

**核心技术栈:** LangGraph, LangChain, FastAPI, PostgreSQL, Supabase, Docker

## 开发命令

### 启动服务

```bash
# 开发模式（快速启动，本地持久化，无需 Docker）
python3 .trae/skills/service-manager/scripts/start_services.py --mode dev
# API 访问: http://localhost:8000
# LangSmith Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024

# 生产验证模式（Docker，PostgreSQL）
python3 .trae/skills/service-manager/scripts/start_services.py --mode up
# API 访问: http://localhost:8000
# LangSmith Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:8123

# 停止所有服务
python3 .trae/skills/service-manager/scripts/stop_services.py
```

### 运行模式说明（重要）

为了避免把“本地调试”和“LangGraph 本地服务”混在一起，这里把运行方式明确分成 3 种：

1. **推荐 Dev/Up 模式（日常开发/生产验证）**：通过 `start_services.py` 启动  
   - Dev：`langgraph dev` + `agent_impl/server.py`  
   - Up：`langgraph up` + `agent_impl/server.py`  
   - 特点：**对话状态（thread）与持久化由 LangGraph CLI/平台管理**（见下方“状态持久化”）

2. **LangGraph Cloud（线上/云端）**：`agent_impl/server.py` 连接云端 LangGraph  
   - 特点：持久化同样由 LangGraph 平台管理

3. **单进程 Local Mode（仅用于快速本机调试）**：`agent_impl/server_local.py`  
   - 特点：使用 `MemorySaver()`，**进程退出即丢失**，不建议当作“持久化开发模式”

### 新增依赖（重要）

本项目在不同运行/部署模式下，依赖的读取来源不同。新增 Python 依赖时需要**同步在三处添加**，否则很容易出现“本地可跑、部署/容器启动失败”的情况：

- `agent_impl/requirements.txt`：本地开发（`langgraph dev` / `--mode dev`）常用安装入口（依赖由本机虚拟环境决定）
- `agent_impl/pyproject.toml` → `[project].dependencies`：本地 `langgraph up` 构建镜像时安装依赖的来源（镜像内 `pip/uv install -e .`）
- 仓库根目录 `pyproject.toml` → `[project].dependencies`：LangChain Cloud 部署构建时安装依赖的来源

典型症状速查：

- **缺 `agent_impl/requirements.txt`**：本地 dev 模式运行时报 `ModuleNotFoundError`
- **缺 `agent_impl/pyproject.toml`**：本地 `langgraph up` 的 `langgraph-api` 容器启动时报 `ModuleNotFoundError`
- **缺根目录 `pyproject.toml`**：LangChain Cloud 启动时加载 graph 失败并报 `ModuleNotFoundError`（例如缺 `langchain-deepseek`）

### 测试

```bash
# 运行所有测试
pytest tests/

# 运行特定类别的测试
pytest tests/ -m "api_test"              # 仅运行 API 测试
pytest tests/ -m "not api_test"          # 跳过 API 测试

# 运行单个测试文件
pytest tests/test_specific_file.py
```

## 架构设计

### LangChain Supervisor + Subgraphs 子 Agent 架构

系统采用 **LangChain Supervisor 模式**，主智能体（Main Agent）作为中央协调器，通过工具调用协调专业子智能体（plan/status/guide）。为了解决子 agent 在 interrupt/resume 场景下的“私有过程态持久化”问题，子 agent 以 **LangGraph Subgraph** 形式实现（不同 schema + 私有 history），由主 agent 在 tool 内 invoke 子图并透传 config，共享同一 thread 的 checkpointer。

#### 主智能体（Supervisor）

- **Main Agent**: LangChain Agent，负责意图识别、选择是否调用子 agent、汇总结果并更新 state
- 位于 `graph/nodes/main_agent.py`，内部使用工具循环执行所有工具调用，并在每次调用时通过 `runtime_config` 模块清洗并透传配置（含 `thread_id`），确保 Checkpointer 在子图中的正确传递与安全性。

#### 子智能体（Subagents）

子 agent 以 **Subgraph** 形式实现，并作为 **tool** 被主 agent 调用：

- `call_status_agent(...)`: 分析当前情感状况
- `call_plan_agent(...)`: 创建可执行计划
- `call_guide_agent(...)`: 提供分步指导

实现位于 `graph/subgraphs/`：
- `graph/subgraphs/status.py`
- `graph/subgraphs/plan.py`
- `graph/subgraphs/guide.py`

子图状态模型要点：
- `private_messages`: 子 agent 私有对话/工具痕迹，仅用于 interrupt/resume 与调试，子图结束后清理
- `state_patch`: 子图最终产出的对 ParentState 的增量更新，主 agent 只 merge 该 patch，不回传过程态

### LangGraph 工作流

位于 `agent_impl/graph/` 目录：
- `workflow.py`: 主 StateGraph 编排，编译入口支持 `checkpointer` 参数
- `state.py`: TypedDict 状态定义
- `runtime_config.py`: 运行时配置安全处理（Checkpointer 提取与清洗）
- `nodes/`: 节点实现
  - `router.py`: 输入路由、风控、闲聊处理、消息归一化
  - `main_agent.py`: LangChain Supervisor（内置工具循环）
  - `finalizer.py`: 对话轮次最终化和响应准备
- `subgraphs/`: 子 agent 子图实现（status/plan/guide）
- `onboarding/`: Onboarding 子图（独立 StateGraph）

**主图节点**：`router` → `onboarding`（可选） → `main_agent` → `post_turn_finalize`

### 人机协作系统（interrupt/resume）

系统使用 LangGraph 原生的 `interrupt()` 机制：

1. 需要用户输入时，工具（如 `ask_human`）调用 `interrupt(inquiry_card)`
2. Graph 暂停，`__interrupt__` 作为结果返回
3. 下一次请求用 `Command(resume=...)` 恢复执行

位于 `agents/tooling/interrupts.py` 和 `graph/tools/ask_human.py`。

子图中断恢复要点：
- 子图内部通过工具（如 `ask_human`）触发中断，checkpoint 会写入同一 `thread_id`
- 主 agent 的 `call_*_agent` 工具会把子图的 `__interrupt__` payload 透传为外层 `interrupt(payload)`，并在 resume 后用 `Command(resume=...)` 继续 invoke 子图

### 统一工具返回契约（ToolResult）

所有会修改 state 的工具统一返回 `ToolResult`：

```python
class ToolResult(TypedDict):
    ok: bool
    output: str          # 给模型看的 observation
    state_patch: dict    # 对 AgentState 的增量更新
```

工具执行后，`state_patch` 由 agent wrapper 合并到 state。位于 `agents/tooling/patch.py`。

### 技能系统

技能位于 `agent_impl/skills/` 目录：
- `base.py`: BaseSkill 基类
- `tool.py`: `load_skill(skill_id)` 工具实现

**渐进式披露**：默认只在 prompt 中注入技能元数据；模型需要时调用 `load_skill` 获取完整指令。

### 上下文架构

系统采用 **3 层上下文架构**：

- **Layer 0-2**: 静态系统提示词和角色定义
- **Layer 3**: 动态上下文（用户数据、对话历史）
- **Layer 4**: 渐进式技能加载和工具输出

上下文工程详见 `agent_impl/docs/context_engineering.md`

### 状态持久化

- **Dev/Up/Cloud（推荐路径）**：当通过 `langgraph dev` / `langgraph up` / LangGraph Cloud 运行时，**对话状态与持久化由 LangGraph CLI/平台负责**。
- **Local Mode（仅调试）**：`agent_impl/server_local.py` 显式使用 `MemorySaver()`，只在内存中保存状态；本地模式会把 `checkpointer` 放入 invoke 的 `config`，以便主 agent 在调用子图时复用同一个 checkpointer。
- **编译入口**：`compile_workflow(checkpointer=...)` 支持传入 checkpointer 以启用 interrupt/resume。

生产模式下状态可在服务器重启后保留，实现真正的跨会话对话。

## 配置说明

### 环境变量

`.env` 中的关键变量：
- `LLM_PROVIDER`: deepseek, openai, claude, doubao（以及 mock 用于纯逻辑测试）
- `DEBUG_MODE`: `1` 使用本地 LangGraph（由 `LANGGRAPH_LOCAL_URL` 指定），`0` 使用 LangGraph Cloud
- `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` / `LANGSMITH_TRACING`: LangSmith 追踪/调试
- `LANGGRAPH_LOCAL_URL`: 本地 LangGraph 地址（dev/up 模式由启动脚本注入）
- `LANGGRAPH_CLOUD_URL` / `LANGGRAPH_CLOUD_API_KEY` / `LANGGRAPH_CLOUD_ASSISTANT_ID`: 云端 LangGraph 配置
- `DATABASE_URL`: Checkpointer 数据库连接（通常由 langgraph up / 云端环境消费）
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`: Supabase 配置（认证与用户线程绑定）

### LLM 提供商切换

系统通过 `agent_impl/config.py` 支持多个 LLM 提供商。默认使用 DeepSeek。通过设置 `LLM_PROVIDER` 环境变量切换。

## 分支策略

- `main`: 生产分支，启用 CD
- `develop`: 集成分支
- `feature/*`: 功能开发分支

PR 工作流: feature → develop → main

详见 `CONTRIBUTING.md` 中的分支管理指南。

## 生产部署

### 部署架构

| 服务 | 部署平台 | 配置文件 | 说明 |
|------|----------|----------|------|
| **FastAPI** | Zeabur | `Dockerfile` | API 服务器，处理 HTTP 请求 |
| **LangGraph** | LangChain Cloud | `langgraph.json` | 智能体工作流引擎 |

### 部署流程

部署前必须完成以下验证步骤：

```bash
# 1. 同步远端 develop 分支最新代码
git fetch origin develop
git merge origin/develop

# 2. 本地生产验证模式（up mode）
python3 .trae/skills/service-manager/scripts/start_services.py --mode up

# 3. 验证功能正常后，提交并推送
git push origin feature/your-feature

# 4. 创建 GitHub PR 到 develop 分支
# PR 合并后自动触发部署
```

### 自动部署

- **触发条件**: GitHub `develop` 分支有新的 push
- **部署流程**:
  1. Zeabur 监听 `develop` 分支，通过 `Dockerfile` 自动重建 FastAPI 服务
  2. LangChain Cloud 监听 `develop` 分支，通过 `langgraph.json` 自动重新部署 LangGraph 应用

## 入口文件

- `agent_impl/server.py`: FastAPI 服务器（生产）
- `agent_impl/server_local.py`: 本地开发服务器（MemorySaver）
- `agent_impl/graph/workflow.py`: LangGraph 工作流定义，`compile_workflow()` 为编译入口

## Agents 子系统

- `agent_impl/agents/`: LangChain Agents 实现
  - `tooling/`: 工具基础设施（patch 合并、context 构建、interrupt）
  - `tools/all_tools.py`: 按角色组装工具集合

## 测试用户

测试时可使用 `TEST_USERS.md` 中的账号（邮箱: `test01@example.com` 至 `test10@example.com`, 密码: `password123`）

或通过 `http://localhost:8000/auth.html` 创建新用户

## 核心文档

- `README.md`: 项目概述和快速入门
- `STARTUP_GUIDE.md`: 详细服务启动说明
- `agent_impl/docs/architecture.md`: v2.1 架构设计细节
- `agent_impl/docs/skill_demo.md`: 技能系统演示
- `agent_impl/docs/debug_guide.md`: 调试流程
- `agent_impl/docs/multi_ai_collaboration_sop.md`: AI 协作指南
- `agent_impl/docs/langchain_agent_refactor_plan.md`: LangChain Agents 重构方案
- `agent_impl/docs/langchain_agent_refactor_tasks_breakdown.md`: 重构任务拆解与测试清单

## 技能框架

`.trae/skills/` 目录包含用于开发自动化的技能框架：
- `service-manager/`: 服务启动/停止脚本
- `langgraph-local-dev/`: LangGraph 开发工具
- `skill-creator/`: 技能创建工具
- `mcp-builder/`: MCP 服务器构建工具
- `changelog-creator/`: 变更日志生成

这些是开发工具，不属于核心智能体系统。

## 常见问题

### 端口冲突
- LangGraph 开发模式: 端口 2024
- LangGraph 生产模式: 端口 8123
- FastAPI: 端口 8000

检查命令: `lsof -i :PORT` 或 `ps aux | grep langgraph`

### 重构后变化

**主图节点**：从原来的 `router/main_agent/status_agent/plan_agent/guide_agent/skill_tools/finalizer` 简化为 `router/onboarding/main_agent/post_turn_finalize`。

**Onboarding 流程**：迁移至 Tool Calling (`submit_onboarding`) 模式，不再依赖 JSON 解析。API 层新增 `synthetic_resume` 支持非挂起式状态恢复。

**配置安全**：引入 `runtime_config` 模块（`sanitize_runtime_config`），在主子 Agent 间传递配置时自动过滤 Checkpointer 等不可序列化对象，防止 `OSError`。

**状态字段**：删除了 `current_agent/agent_resume_point/ask_mode/consult_mode/emotion_mode` 等旧控制字段，改用 `runtime/tool_patch_log`。

**人机交互**：从 Router-Resume 模式迁移到 LangGraph 原生 `interrupt()`，API 层支持 `Command(resume=...)` 恢复执行。

**工具契约**：所有工具统一返回 `ToolResult`（含 `state_patch`），不再依赖 `skill_tools` 节点集中写回。

## 测试账号生成（Supabase）

目标：生成一批真实测试账号写入 Supabase，并把账号清单保存为 Markdown，同时可选更新 `TEST_USERS.md`。

### 前置条件

- 已配置 Supabase 环境变量（通常在 `.env` 中）：
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`

### 生成并写入 Supabase（同时导出 Markdown + 更新 TEST_USERS.md）

```bash
python scripts/generate_test_accounts_excel.py \
  --mode supabase \
  --count 20 \
  --start 11 \
  --md-output generated/test_accounts_real.md \
  --update-test-users-md TEST_USERS.md
```
