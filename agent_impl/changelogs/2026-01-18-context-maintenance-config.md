# 上下文维护配置与同步提纯支持 - 2026-01-18

## 概述
引入 `STUDIO_SYNC_MAINTENANCE` 配置项，允许在本地开发或 Studio 模式下同步执行上下文提纯任务，确保调试时状态的一致性。

## 变更内容

### 配置项变更
- 修改 `.env` 和 `.env.example`
- 新增 `STUDIO_SYNC_MAINTENANCE` 变量：
    - `1`: 同步执行维护任务（阻塞响应，适用于调试）
    - `0`: 异步入队执行（非阻塞响应，适用于生产）

### 逻辑优化
- 系统现在会优先读取环境变量中的 `STUDIO_SYNC_MAINTENANCE` 来决定提纯任务的执行方式。

## 技术细节

### 实现要点
- 在 [finalizer.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/nodes/finalizer.py) 中，通过检测环境变量和运行时模块来判定是否启用同步消费模式。
- 同步模式下调用 `_consume_maintenance_queue_inline` 立即处理队列。

### 兼容性说明
- 向后兼容：默认值（或不设置时）在生产环境 API 中仍保持异步 BackgroundTasks 模式。

## 验证结果
- ✅ 环境变量正确读取。
- ✅ 配置文件已同步更新。

## 测试清单（必须）

### 变更关联用例文件
- 用例文档：[2026-01-18-context-maintenance-config.md](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/testcases/2026-01-18-context-maintenance-config.md)

### Checklist
- [x] 环境验证：检查 `.env` 中是否正确配置变量。
- [x] 逻辑验证：验证 `finalizer.py` 是否能正确识别该变量。
- [ ] 功能回归：验证在同步模式下，提纯任务是否能成功完成并更新 state。

## 影响范围
- 配置文件：`.env`, `.env.example`
- 核心逻辑：`agent_impl/graph/nodes/finalizer.py`
