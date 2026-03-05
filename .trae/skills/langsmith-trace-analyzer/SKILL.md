---
name: langsmith-trace-analyzer
description: 分析 LangSmith 上的对话 Trace 和 Thread，支持线上 (Crushe2-0) 和调试环境。当需要执行以下任务时使用此技能：(1) 列出最近的对话 Trace 或 Thread，(2) 根据 thread_id 查找关联的所有 runs，(3) 深度分析特定 run_id 的输入、输出、模型思考过程（Thinking）及子图调用逻辑。
---

# LangSmith Trace Analyzer

此技能允许你直接读取和分析存储在 LangSmith 云端的执行轨迹（Traces）。它封装了 LangSmith SDK，能够提取模型思考过程、工具调用参数、状态补丁（State Patches）以及子图的流转细节。

## 快速开始

当你需要分析某个线上的对话问题时，请遵循以下流程：

1. **确定项目范围**：
   - 线上项目：`Crushe2-0` (默认)
   - 本地调试项目：`crushe-agent-debug`

2. **获取 Trace/Thread 列表**：
   如果你没有具体的 ID，先列出最近的记录。
   ```bash
   # 列出最近 10 条 Trace (默认项目)
   python3 scripts/list_recent_traces.py
   
   # 指定项目列出
   python3 scripts/list_recent_traces.py Crushe2-0
   ```

3. **按 Thread ID 查找**：
   如果你有用户反馈的 `thread_id`：
   ```bash
   python3 scripts/inspect_by_thread.py <thread_id> [project_name]
   ```
   这将列出该 Thread 下所有的根 Run ID。

4. **深度分析特定 Run**：
   获取到具体的 `run_id` 后，进行深度拆解：
   ```bash
   python3 scripts/inspect_langsmith_run.py <run_id> [project_name]
   ```

## 核心分析任务

### 1. 模型思考过程 (Thinking)
在 `inspect_langsmith_run.py` 的输出中，关注 `ChatDeepSeekReasoning` 节点的输出。这包含了模型在调用工具前的推理逻辑，有助于理解为什么它选择了某个子 Agent。

### 2. 子图调用 (Subgraphs)
Trace 会展示 `call_guide_agent` -> `LangGraph` -> `run` 的嵌套结构。
- 检查 `inputs` 是否包含了正确的 `thread_id`。
- 检查子图结束后的 `outputs` 是否包含预期的 `state_patch`。

### 3. 状态流转分析
重点查看 `route_after_main_agent` 或子图内的 `_route_after_run` 节点，确认路由逻辑是否根据当前的 State 做了正确的跳转决定。

## 资源

### scripts/
- `list_recent_traces.py`: 列出指定项目最近的根 Run。
- `inspect_by_thread.py`: 根据 `thread_id` 过滤并列出相关的 Run。
- `inspect_langsmith_run.py`: 深度拆解单个 Run 的所有子节点、输入输出和元数据。

## 注意事项
- **API Key**: 确保 `.env` 中配置了有效的 `LANGSMITH_API_KEY`。
- **环境隔离**: 线上和测试环境使用不同的 `project_name`，调用脚本时请务必确认。
