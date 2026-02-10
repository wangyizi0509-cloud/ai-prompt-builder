# 🚀 快速开始调试

## 方式 0: 非流式验收（推荐团队自测）

一键跑“非流式 interrupt/resume + 单测回归”：

```bash
./agent_impl/verify_non_stream.sh dev
```

验收标准与覆盖范围见 docs/acceptance_non_stream.md。

## 方式 1: Streaming API（立即可用）

### 启动服务器

```bash
cd agent_impl
./start_debug.sh
```

或者：

```bash
python3 server.py
```

### 测试 Streaming

在另一个终端运行：

```bash
cd agent_impl
python3 test_streaming.py "帮我分析一下我和 crush 的关系状态"
```

### 或者用 curl 测试

```bash
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好",
    "session_id": "test",
    "stream_mode": "updates"
  }' \
  --no-buffer
```

---

## 方式 2: LangSmith Studio（需要配置）

### 1. 配置 LangSmith API Key

编辑 `.env` 文件，添加：

```bash
# LangSmith 配置
LANGSMITH_API_KEY=your_api_key_here
LANGSMITH_PROJECT=crushe-agent-debug
LANGSMITH_TRACING=true
```

获取 API Key：
1. 访问 https://smith.langchain.com/
2. 注册/登录
3. Settings → API Keys → Create API Key

### 2. 安装 langgraph-cli

```bash
pip3 install langgraph-cli
```

如果安装失败，可以尝试：
```bash
pip3 install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org langgraph-cli
```

### 3. 启动 Studio

```bash
cd agent_impl
langgraph dev
```

### 4. 打开 Studio

访问：https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024

---

## 📝 当前状态

✅ Streaming API 已配置，可以直接使用
⚠️  LangSmith Studio 需要配置 API Key
