# Agent 调试指南

本指南介绍如何使用 LangSmith Studio 和 Streaming 来调试你的 Agent。

## 📋 目录

1. [LangSmith Studio - 可视化调试](#langsmith-studio)
2. [Streaming - 实时查看执行过程](#streaming)
3. [快速开始](#快速开始)

---

## 🎨 LangSmith Studio

LangSmith Studio 是一个可视化的调试界面，可以实时查看 Agent 的每一步执行过程。

### 功能特点

- ✅ **可视化执行流程**：看到每个节点的执行顺序
- ✅ **查看详细状态**：每个步骤的 prompts、工具调用、返回值
- ✅ **时间旅行调试**：可以从任意步骤重新运行
- ✅ **热重载**：修改代码后立即反映
- ✅ **Token 和延迟统计**：查看性能指标

### 使用步骤

#### 1. 安装依赖

```bash
cd agent_impl
pip install -r requirements.txt
```

#### 2. 配置环境变量

编辑 `.env` 文件，添加 LangSmith 配置：

```bash
# LangSmith 配置
LANGSMITH_API_KEY=your_langsmith_api_key_here
LANGSMITH_PROJECT=crushe-agent-debug
LANGSMITH_TRACING=true
```

> 💡 **获取 API Key**：
> 1. 访问 https://smith.langchain.com/
> 2. 注册/登录账号
> 3. 在 Settings → API Keys 中创建 API Key

#### 3. 启动 LangGraph 开发服务器

```bash
cd agent_impl
langgraph dev
```

你会看到类似输出：

```
Starting LangGraph server...
Server running at http://127.0.0.1:2024
```

#### 4. 打开 Studio 界面

在浏览器中访问：

```
https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

> ⚠️ **注意**：如果使用 Safari，可能需要使用 `--tunnel` 参数：
> ```bash
> langgraph dev --tunnel
> ```

#### 5. 在 Studio 中调试

1. **选择 Graph**：在左侧选择 `crushe_agent`
2. **输入测试消息**：在输入框中输入用户消息
3. **查看执行过程**：
   - 左侧面板显示执行流程
   - 右侧面板显示每个节点的详细信息
   - 可以看到 prompts、工具调用、返回值等

### Studio 界面说明

- **Graph 视图**：显示工作流的节点和连接
- **Trace 视图**：显示执行轨迹，包括：
  - 每个节点的输入/输出
  - LLM 调用的 prompts 和响应
  - 工具调用的参数和结果
  - Token 使用和延迟
- **State 视图**：查看当前状态的所有字段
- **Messages 视图**：查看对话历史

---

## 📡 Streaming - 实时查看执行过程

Streaming 允许你实时查看 Agent 的执行过程，适合在代码中集成或通过 API 调用。

### API 端点

**POST** `/api/chat/stream`

### 请求格式

```json
{
  "message": "用户消息",
  "session_id": "session_123",
  "stream_mode": "updates"  // 可选: "values", "updates", "messages", "debug"
}
```

### 流模式说明

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `values` | 每个步骤后的完整状态 | 需要完整状态信息 |
| `updates` | 每个步骤的状态更新（推荐） | 实时查看执行进度 |
| `messages` | LLM tokens 和元数据 | 查看模型输出流 |
| `debug` | 最详细的调试信息 | 深度调试 |

### 使用示例

#### Python 客户端

```python
import requests
import json

def stream_chat(message, session_id="test_session"):
    url = "http://localhost:8000/api/chat/stream"
    data = {
        "message": message,
        "session_id": session_id,
        "stream_mode": "updates"
    }
    
    response = requests.post(url, json=data, stream=True)
    
    for line in response.iter_lines():
        if line:
            # SSE 格式: data: {...}
            if line.startswith(b"data: "):
                json_str = line[6:].decode("utf-8")
                chunk = json.loads(json_str)
                
                if chunk.get("type") == "chunk":
                    print(f"收到更新: {chunk.get('data')}")
                elif chunk.get("type") == "info":
                    print(f"ℹ️  {chunk.get('message')}")
                elif chunk.get("type") == "done":
                    print(f"✅ {chunk.get('message')}")
                elif chunk.get("type") == "error":
                    print(f"❌ 错误: {chunk.get('error')}")

# 使用
stream_chat("帮我分析一下我和 crush 的关系状态")
```

#### JavaScript/TypeScript 客户端

```javascript
async function streamChat(message, sessionId = "test_session") {
  const response = await fetch("http://localhost:8000/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message: message,
      session_id: sessionId,
      stream_mode: "updates"
    }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split("\n");

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const jsonStr = line.slice(6);
        const data = JSON.parse(jsonStr);

        if (data.type === "chunk") {
          console.log("收到更新:", data.data);
        } else if (data.type === "info") {
          console.log("ℹ️", data.message);
        } else if (data.type === "done") {
          console.log("✅", data.message);
        } else if (data.type === "error") {
          console.error("❌ 错误:", data.error);
        }
      }
    }
  }
}

// 使用
streamChat("帮我分析一下我和 crush 的关系状态");
```

#### cURL 测试

```bash
curl -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我分析一下我和 crush 的关系状态",
    "session_id": "test_session",
    "stream_mode": "updates"
  }' \
  --no-buffer
```

---

## 🚀 快速开始

### 方式 1: 使用 LangSmith Studio（推荐用于开发）

1. **配置环境变量**
   ```bash
   cp env.example .env
   # 编辑 .env，填入 LANGSMITH_API_KEY
   ```

2. **启动开发服务器**
   ```bash
   langgraph dev
   ```

3. **打开 Studio**
   ```
   https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
   ```

4. **开始调试**
   - 在 Studio 中输入测试消息
   - 查看执行流程和详细信息

### 方式 2: 使用 Streaming API

1. **启动服务器**
   ```bash
   python server.py
   # 或
   uvicorn server:app --reload
   ```

2. **调用 Streaming API**
   ```python
   # 使用上面的 Python 示例代码
   stream_chat("你的消息")
   ```

---

## 🔍 调试技巧

### 1. 查看特定节点的执行

在 Studio 中：
- 点击左侧的节点名称
- 查看右侧的详细信息面板
- 可以看到该节点的输入、输出、prompts 等

### 2. 查看工具调用

- 在 Trace 视图中找到 `skill_tools` 节点
- 查看工具调用的参数和返回值
- 检查工具是否正确执行

### 3. 分析决策路径

- 查看 `router` 节点的路由决策
- 查看 `main_agent` 的 `next_action` 决策
- 理解 Agent 为什么选择某个路径

### 4. 性能分析

- 查看每个节点的执行时间
- 查看 Token 使用情况
- 识别性能瓶颈

### 5. 状态调试

- 在 State 视图中查看完整状态
- 检查 `user_context`、`status_report` 等字段
- 验证状态是否正确传递

---

## 📝 常见问题

### Q: Studio 连接失败？

A: 检查：
1. `langgraph dev` 是否正在运行
2. 端口 2024 是否被占用
3. 防火墙是否阻止连接
4. 如果使用 Safari，尝试 `langgraph dev --tunnel`

### Q: Streaming 没有输出？

A: 检查：
1. 服务器是否正在运行
2. 请求格式是否正确
3. 查看服务器日志是否有错误

### Q: 如何查看历史 trace？

A: 在 LangSmith 网页界面：
1. 访问 https://smith.langchain.com/
2. 进入你的 Project
3. 查看 Traces 列表

### Q: 如何禁用 Tracing？

A: 在 `.env` 中设置：
```bash
LANGSMITH_TRACING=false
```

---

## 🎯 下一步

- 了解更多 LangSmith 功能：https://docs.langchain.com/langsmith/
- 查看 LangGraph 文档：https://langchain-ai.github.io/langgraph/
- 优化 Agent 性能：使用 Studio 分析瓶颈

---

**祝你调试愉快！** 🎉

