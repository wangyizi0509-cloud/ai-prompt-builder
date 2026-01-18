#!/bin/bash
cd "$(dirname "$0")"

# 生产级验证模式端口
PORT=${LANGGRAPH_PORT:-8123}

echo "🚀 启动 LangGraph 服务 (Docker Stack)..."
# 使用 langgraph up 启动生产级环境
export PATH="$PATH:$(python3 -m site --user-base)/bin"
langgraph up --port $PORT --wait &
LANGGRAPH_PID=$!

echo "⏳ 等待 LangGraph 服务启动 (可能需要拉取镜像)..."
sleep 15

echo "🚀 启动 FastAPI 服务 (连接到 http://localhost:$PORT)..."
# 强制环境变量以确保连接到正确的端口
export LANGGRAPH_LOCAL_URL="http://127.0.0.1:$PORT"
python3 server.py &
FASTAPI_PID=$!

echo "✅ 服务已启动"
echo "LangGraph PID: $LANGGRAPH_PID"
echo "FastAPI PID: $FASTAPI_PID"
echo "访问地址: http://localhost:8000"
echo "LangSmith Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:$PORT"

trap "kill $LANGGRAPH_PID $FASTAPI_PID 2>/dev/null" EXIT

wait
