#!/bin/bash
cd "$(dirname "$0")"

# 默认使用开发模式端口
PORT=${LANGGRAPH_PORT:-2024}

echo "🚀 启动 LangGraph 服务 (Dev Mode)..."
export PATH="$PATH:$(python3 -m site --user-base)/bin"
langgraph dev --port $PORT --no-browser &
LANGGRAPH_PID=$!

echo "⏳ 等待服务启动..."
sleep 5

echo "🚀 启动 FastAPI 服务 (连接到 http://localhost:$PORT)..."
# 强制环境变量以确保连接到正确的端口
export DEBUG_MODE="${DEBUG_MODE:-1}"
export UVICORN_RELOAD="${UVICORN_RELOAD:-1}"
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
