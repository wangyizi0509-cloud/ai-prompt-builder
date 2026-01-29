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

### 编排器-工作器模式

系统使用中央 **主智能体（Main Agent）** 协调专业子智能体：

- **状态智能体 (Status Agent)**: 分析当前情感状况
- **计划智能体 (Plan Agent)**: 创建可执行计划
- **指导智能体 (Guide Agent)**: 提供分步指导
- **调度器 (Dispatcher)**: 将任务路由到合适的技能

### LangGraph 工作流

位于 `agent_impl/graph/` 目录：
- `workflow.py`: 主 StateGraph 编排和路由逻辑
- `state.py`: TypedDict 状态定义（消息、用户信息、上下文等）
- `nodes/`: 各个节点实现
  - `router.py`: 处理输入路由和状态恢复（HTTP 兼容）
  - `main_agent.py`: 中央决策枢纽
  - `status_agent.py`, `plan_agent.py`, `guide_agent.py`: 专业智能体
  - `finalizer.py`: 对话轮次最终化和响应准备

### 人机协作系统

系统使用 LangGraph 的 `interrupt()` 机制暂停执行并等待用户输入。但为了 HTTP API 兼容性，实现了**基于状态恢复的模式**：

1. 需要中断时，节点将意图保存到状态并返回特殊状态码
2. 路由节点检测到此状态并保存检查点
3. 下次用户消息时，路由节点检查待处理的中断
4. 如果发现中断，使用用户输入恢复被中断的节点

这使得系统在保持 HTTP 兼容性的同时，通过 Checkpointer 实现跨会话持久化。

### 技能系统

技能位于 `agent_impl/skills/` 目录，是动态加载的能力：
- `base.py`: 技能实现的 BaseSkill 基类
- `tool.py`: 由 LLM 调用的技能加载机制

技能通过 ToolNode 基于智能体决策渐进式加载，而非在初始化时静态定义。

### 上下文架构

系统采用 **3 层上下文架构**：

- **Layer 0-2**: 静态系统提示词和角色定义
- **Layer 3**: 动态上下文（用户数据、对话历史）
- **Layer 4**: 渐进式技能加载和工具输出

上下文工程详见 `agent_impl/docs/context_engineering.md`

### 状态持久化

- **开发环境**: 内存检查点（临时）
- **生产环境**: 通过 `langgraph-checkpoint-postgres` 使用 PostgreSQL
- **存储策略**: `graph/storage_strategy.py` 和 `graph/crush_chat_storage.py`

生产模式下状态可在服务器重启后保留，实现真正的跨会话对话。

## 配置说明

### 环境变量

`.env` 中的关键变量：
- `LLM_PROVIDER`: deepseek, openai, claude 或 doubao
- `DEBUG_MODE`: 启用自动重载和详细日志
- `LANGCHAIN_API_KEY`: LangSmith 用于追踪/调试
- `POSTGRES_*`: 检查点数据库连接
- `SUPABASE_URL`: 后端数据库和认证

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
- `agent_impl/server_local.py`: 本地开发服务器
- `agent_impl/agent.py`: LangGraph 智能体定义（CLI/Studio）
- `agent_impl/main.py`: 直接 CLI 接口

## 测试用户

测试时可使用 `TEST_USERS.md` 中的账号（邮箱: `test01@example.com` 至 `test10@example.com`, 密码: `password123`）

或通过 `http://localhost:8000/auth.html` 创建新用户

## 核心文档

- `README.md`: 项目概述和快速入门
- `STARTUP_GUIDE.md`: 详细服务启动说明
- `docs/architecture.md`: v2.1 架构设计细节
- `docs/skill_demo.md`: 技能系统演示
- `docs/debug_guide.md`: 调试流程
- `docs/multi_ai_collaboration_sop.md`: AI 协作指南

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
