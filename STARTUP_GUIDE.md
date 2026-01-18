# Crushe AI Agent 启动指南

本指南介绍了如何启动和管理 Crushe AI Agent 的后端及 LangGraph 服务。

## 🚀 快速启动 (推荐)

我们提供了封装好的 Skill 脚本，可以一键管理所有服务。

### 1. 开发模式 (Dev Mode) - **推荐日常开发使用**
特点：启动快，轻量级，不需要 Docker。状态持久化到本地目录。
```bash
python3 .trae/skills/service-manager/scripts/start_services.py --mode dev
```
- **API 地址**: http://localhost:8000
- **Studio 地址**: [点击打开](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024)

### 2. 生产验证模式 (Up Mode)
特点：模拟生产环境，使用 Docker 运行完整的 Postgres 和 Redis 技术栈。
```bash
python3 .trae/skills/service-manager/scripts/start_services.py --mode up
```
- **API 地址**: http://localhost:8000
- **Studio 地址**: [点击打开](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:8123)

---

## 🛑 停止服务

无论使用哪种模式启动，都可以通过以下命令停止所有相关进程（包括 Docker 容器）：
```bash
python3 .trae/skills/service-manager/scripts/stop_services.py
```

---

## 🔄 重启服务

清理旧进程并按之前的模式重新启动：
```bash
python3 .trae/skills/service-manager/scripts/restart_services.py
```

---

## 📝 模式对比

| 特性 | 开发模式 (Dev) | 生产验证模式 (Up) |
| :--- | :--- | :--- |
| **启动速度** | 极快 (< 5s) | 较慢 (15s+, 需冷启动 Docker) |
| **依赖** | 仅 Python | Docker Desktop |
| **持久化** | 本地文件 (.langgraph) | **PostgreSQL (Docker 卷)** |
| **端口 (LangGraph)** | 2024 | 8123 |
| **适用场景** | 逻辑开发、Prompt 调试 | 持久化测试、多用户并发模拟 |

---

## 🔍 日志查看

- **后端日志**: [agent_impl/logs/backend.log](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/logs/backend.log)
- **实时监控**: `tail -f agent_impl/logs/backend.log`

## 🛠️ 故障排查

1. **端口占用**: 如果看到 `Address already in use`，请运行停止服务脚本后再试。
2. **Docker 错误**: 确保 Docker Desktop 已启动并处于运行状态。
3. **环境变量**: 确保根目录的 `.env` 文件配置正确。
