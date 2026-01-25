#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "🚀 一键启动前端 + 后端 + LangGraph Studio"
echo "============================================"

# 可按需切换 Python
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

echo "使用 Python: $PYTHON_BIN"

# 启动 LangGraph Dev Server (2024)
echo "\n[1/2] 启动 LangGraph Dev Server (2024)"
$PYTHON_BIN -m langgraph_cli dev --port 2024 --no-browser &
LANGGRAPH_PID=$!

# 等待 LangGraph 启动
sleep 3

# 启动 FastAPI (8000)
# 注意: 这里使用 server.py，它会通过 SDK 连接 LangGraph
# 如果你要用本地模式，可以改为 server_local.py

echo "\n[2/2] 启动 FastAPI (8000)"
DEBUG_MODE=1 $PYTHON_BIN server.py &
FASTAPI_PID=$!

cat <<INFO
\n✅ 已启动
- LangGraph PID: $LANGGRAPH_PID
- FastAPI PID:  $FASTAPI_PID
\n访问地址:
- 前端: http://localhost:8000
- API:  http://localhost:8000/docs
- Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
\n按 Ctrl+C 停止服务
INFO

trap "kill $LANGGRAPH_PID $FASTAPI_PID 2>/dev/null" EXIT
wait
