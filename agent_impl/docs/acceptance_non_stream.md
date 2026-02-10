# 非流式验收（One-Click）

本页定义一套“无需流式 SSE”的最小验收流程，用于团队在本地快速验证：
- FastAPI 服务可启动
- LangGraph（dev/up）可连接
- interrupt / resume（非流式）协议可用

## 使用方式

在仓库根目录执行：

```bash
./agent_impl/verify_non_stream.sh dev
```

可选：验收 Docker/生产栈（8123）：

```bash
./agent_impl/verify_non_stream.sh up
```

## 环境变量

脚本支持通过环境变量覆盖默认值：

- `LLM_PROVIDER`
  - 默认：`mock`（推荐用于“确定性验收”，不依赖真实 LLM）
  - 可选：`deepseek` / `claude` / `openai` / `doubao`（用于回归，但结果可能不稳定）
- `DEBUG_MODE`
  - 默认：`1`（连接本地 LangGraph dev）
- `UVICORN_RELOAD`
  - 默认：`0`（避免 watchfiles 热重载导致连接 reset、验收不稳定）

示例：

```bash
LLM_PROVIDER=mock DEBUG_MODE=1 UVICORN_RELOAD=0 ./agent_impl/verify_non_stream.sh dev
```

## 覆盖范围（本验收包含什么）

脚本顺序执行：

1. 启停服务（依赖 service-manager）
   - 启动 LangGraph（dev: 2024 / up: 8123）
   - 启动 FastAPI（8000）
   - 等待 `http://127.0.0.1:8000/openapi.json` 可访问
2. 单元/集成测试（不含 api_test）
   - `pytest tests/ -m "not api_test"`
3. 非流式 API 验收（仅 interrupt/resume）
   - `pytest -m api_test tests/test_interrupt_http_api.py`

## 明确不包含（为什么不测）

- 流式 SSE（`/api/chat/stream`）相关验收与测试：
  - 本页目标是“先保证非流式链路可用”，流式验收在单独的验收文档中定义。

## 验收标准（Pass/Fail）

### 必须满足（Fail fast）

- 脚本执行退出码为 0
- FastAPI 在 30 秒内启动成功（openapi.json 返回 200）
- `pytest tests/ -m "not api_test"` 全绿
- `pytest -m api_test tests/test_interrupt_http_api.py` 全绿（包含 interrupt 与 resume 两条用例）

### 允许的波动（不作为 Fail）

- 第三方依赖的告警日志（例如 pydantic deprecation warnings）
- 使用真实 LLM 时的输出内容波动（但不应导致 500、结构崩溃）

## 常见问题

### 1) 端口被占用

脚本会在开始与结束时调用 stop_services 清理 2024/8123/8000 端口进程。
如果仍冲突，通常是其他程序占用端口。

### 2) 为什么默认 LLM_PROVIDER=mock？

为了把“协议验收”与“模型能力回归”解耦：
- 验收阶段优先验证接口/状态机/interrupt-resume 链路稳定。
- 能力回归可以单独在真实 LLM 下做，不影响最小验收结论。

