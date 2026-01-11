# 🎨 LangSmith Studio 配置完成

## ✅ 已完成的配置

1. **环境变量已配置**
   - `LANGSMITH_API_KEY` 已添加到 `.env`
   - `LANGSMITH_PROJECT=crushe-agent-debug`
   - `LANGSMITH_TRACING=true`

2. **配置文件已创建**
   - `langgraph.json` 已配置

## 🚀 启动方式

### 方式 1: 使用启动脚本（推荐）

```bash
cd agent_impl
./start_studio.sh
```

### 方式 2: 使用 npx（如果脚本不工作）

```bash
cd agent_impl
npx @langchain/langgraph-cli dev
```

### 方式 3: 使用 Python CLI（如果已安装）

```bash
cd agent_impl
langgraph dev
```

## 📍 访问 Studio

启动后，你会看到类似输出：

```
Ready!

* API: http://localhost:2024
* Docs: http://localhost:2024/docs
* LangGraph Studio Web Interface: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

**打开浏览器访问：**
```
https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

## 🔧 如果遇到问题

### 问题 1: 端口被占用

```bash
# 查看占用端口的进程
lsof -ti:2024

# 或者使用其他端口
npx @langchain/langgraph-cli dev -p 3000
# 然后访问: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:3000
```

### 问题 2: Safari 连接失败

使用 `--tunnel` 参数：

```bash
npx @langchain/langgraph-cli dev --tunnel
```

### 问题 3: 安装 Python CLI

如果 npm 版本不兼容，尝试安装 Python 版本：

```bash
pip3 install langgraph-cli
```

如果安装失败，可能是网络问题，可以尝试：

```bash
pip3 install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org langgraph-cli
```

## 📝 使用 Studio

1. **选择 Graph**: 在左侧选择 `crushe_agent`
2. **输入测试消息**: 在输入框中输入用户消息
3. **查看执行过程**:
   - 左侧面板显示执行流程
   - 右侧面板显示每个节点的详细信息
   - 可以看到 prompts、工具调用、返回值等

## 🎯 下一步

- 在 Studio 中测试你的 Agent
- 查看执行轨迹和调试信息
- 优化 Agent 的行为

---

**配置完成！现在可以启动 Studio 了！** 🎉

