# LangGraph SDK 集成变更摘要

**日期**: 2026-01-17

## 概述

将 FastAPI 服务器改造为通过 langgraph-sdk 调用 LangGraph 服务，实现本地开发和云端部署的统一架构。

## 变更详情

### 1. 新增文件

| 文件 | 说明 |
|------|------|
| `agent.py` | LangGraph CLI 入口文件，导出编译后的 graph 对象 |
| `api/sdk_client.py` | LangGraph SDK 客户端工具库，提供统一的客户端获取、状态管理等函数 |
| `start.sh` | 启动脚本，同时启动 LangGraph 服务和 FastAPI 服务 |
| `stop_services.sh` | 停止脚本，清理所有运行的服务 |

### 2. 修改文件

| 文件 | 变更内容 |
|------|---------|
| `langgraph.json` | 更新 graph 路径从 `graph.workflow:get_workflow` 改为 `./agent.py:graph` |
| `requirements.txt` | 添加 `langgraph-cli>=0.4.0` 和 `langgraph-sdk>=0.2.0` |
| `api/chat.py` | 重构为使用 SDK 调用 LangGraph 服务，替换直接的 workflow.invoke |
| `api/stream.py` | 重构为使用 SDK 调用 LangGraph 服务，替换直接的 workflow.stream |
| `api/guide.py` | 重构为使用 SDK 的状态管理函数 |
| `api/debug.py` | 重构为使用 SDK 的状态查询函数 |
| `api/__init__.py` | 恢复 auth 路由（支持可选配置） |
| `.env` | 添加 JWT_SECRET、LANGGRAPH_URL、LANGGRAPH_API_KEY、LANGGRAPH_ASSISTANT_ID、SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY 配置 |
| `auth_utils.py` | 支持可选的 JWT_SECRET 配置，添加 `is_jwt_configured()` 检查 |
| `supabase_service/client.py` | 支持可选的 Supabase 配置，添加 `is_supabase_configured()` 检查 |

### 3. 删除文件

| 文件 | 原因 |
|------|------|
| `server_sdk.py` | 临时文件已删除，统一使用原始 server.py |

### 4. 备份文件

| 文件 | 说明 |
|------|------|
| `server_legacy.py` | 原始 server.py 备份（未使用 SDK 版本） |

## 技术细节

### SDK 客户端工具 (`api/sdk_client.py`)

提供以下核心功能：

```python
# 获取客户端
get_client()

# Session ID 到 UUID 转换
session_to_thread_id(session_id)

# 确保 Thread 存在
ensure_thread_exists(session_id)

# 状态管理
get_thread_state(thread_id)
update_thread_state(thread_id, updates)

# 运行 Assistant
run_assistant(thread_id, input_state, stream_mode)
```

### API 改造要点

1. **Chat API** (`api/chat.py`)
   - 使用 `run_assistant()` 执行工作流
   - 流式收集 chunks，获取最终状态
   - 后台任务改为使用 SDK 的状态管理

2. **Stream API** (`api/stream.py`)
   - 支持多种流模式：values, updates, messages, debug
   - 实时推送 Agent 执行过程
   - 使用 SSE (Server-Sent Events) 格式

3. **Guide API** (`api/guide.py`)
   - 使用 SDK 的状态查询和更新
   - 简化状态管理逻辑

4. **Debug API** (`api/debug.py`)
   - 使用 SDK 的状态查询
   - 提供分层上下文调试信息

5. **Auth API** (`api/auth.py`)
   - 支持可选的 Supabase 配置
   - 支持可选的 JWT 配置
   - 未配置时返回适当错误信息

### 可选配置支持

- **JWT**: 当 `JWT_SECRET` 未配置时，Auth 路由返回 503 错误
- **Supabase**: 当 `SUPABASE_URL` 和 `SUPABASE_SERVICE_ROLE_KEY` 未配置时，返回 "Supabase not configured" 错误

## 环境变量配置

```bash
# LangGraph 服务地址（本地开发）
LANGGRAPH_URL=http://127.0.0.1:2024

# LangGraph API Key（云端部署需要）
LANGGRAPH_API_KEY=

# Assistant ID
LANGGRAPH_ASSISTANT_ID=crushe_agent

# JWT 密钥（用于 API 认证）
JWT_SECRET=your-secret-key-change-this-in-production

# Supabase 配置（可选，用于用户认证）
SUPABASE_URL=your-supabase-url-here
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key-here
```

## 使用方法

### 启动服务

```bash
cd /Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl
./start.sh
```

### 停止服务

```bash
./stop_services.sh
```

### 访问地址

- **FastAPI**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **LangSmith Studio**: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
- **LangGraph API 文档**: http://127.0.0.1:2024/docs

## 架构优势

1. **统一性**: 本地和云端使用相同的代码逻辑
2. **可观测性**: 集成 LangSmith Studio 实时调试
3. **可扩展性**: 轻松切换本地/云端部署
4. **状态管理**: LangGraph API 自动处理 Checkpointer
5. **标准化**: 遵循 LangGraph 官方部署最佳实践
6. **可选依赖**: 支持 Supabase 和 JWT 的可选配置，便于本地开发

## 注意事项

1. ⚠️ Supabase 和 JWT 配置为可选，未配置时相关 API 返回错误信息
2. ⚠️ 本地 LangGraph 服务需要 Python 3.11 环境
3. ⚠️ LangGraph CLI 路径: `/Users/wuyu/Library/Python/3.11/bin/langgraph`
4. ⚠️ 确保环境变量正确配置

## 下一步

- [x] 恢复 Auth 路由，支持可选配置
- [ ] 配置 Supabase，启用完整用户认证
- [ ] 完善错误处理和日志
- [ ] 添加单元测试
- [ ] 配置云端部署环境
