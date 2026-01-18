# 测试用例：上下文维护配置与同步提纯 - 2026-01-18

## 概述
验证 `STUDIO_SYNC_MAINTENANCE` 环境变量对系统提纯逻辑的控制效果。

## 测试环境
- 开发环境
- LangGraph Studio 或本地 API

## 测试用例

### 用例 1：同步模式验证
**描述**：验证当 `STUDIO_SYNC_MAINTENANCE=1` 时，任务被同步消费。
**前置条件**：`.env` 中设置 `STUDIO_SYNC_MAINTENANCE=1`。
**步骤**：
1. 启动服务。
2. 发送多轮对话，触发对话压缩阈值。
3. 观察响应耗时。
4. 检查响应后的 `state`，确认 `layer3_memory` 已更新且消息已被压缩。
**预期结果**：响应时间略有增加，且返回的 `state` 中已经包含了压缩后的摘要，`maintenance_queue` 中对应任务状态为 `done`。

### 用例 2：异步模式验证（回归）
**描述**：验证当 `STUDIO_SYNC_MAINTENANCE=0` 时，任务进入异步处理。
**前置条件**：`.env` 中设置 `STUDIO_SYNC_MAINTENANCE=0`。
**步骤**：
1. 发送对话触发维护任务。
2. 观察 API 立即返回。
3. 检查返回的 `state`，此时消息可能尚未压缩。
4. 等待几秒后重新获取 `state`。
**预期结果**：API 快速响应，任务异步完成。

## 覆盖范围
- 模块：`finalizer.py`, `archive_manager.py`
- 接口：`POST /chat`, `POST /chat/stream`
