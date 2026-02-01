# Crushe AI Agent Implementation

本项目是一个基于 LangGraph 的 AI 恋爱军师 Agent 架构实现。

## 项目结构

- `agent_impl/`: 核心代码库，包含 Agent 节点、工作流和 Skills。
- `scripts/`: 实用工具脚本。
- `supabase/`: 数据库迁移文件。
- `tests/`: 测试用例。

## 快速开始

请参考 [agent_impl/README.md](agent_impl/README.md) 获取详细的安装和运行指南。

## 贡献指南与分支管理

为了保持代码质量和稳定的 CD 流程，请在提交代码前阅读：
- [分支管理与贡献指南](CONTRIBUTING.md)

## 主要特性

- **Human-in-the-Loop**: 采用 Router 状态恢复模式（不使用 `interrupt()`）。
- **持久化**: 集成 Checkpointer 支持跨会话记忆。
- **分层上下文**: 优化状态结构，支持复杂的上下文组装。
