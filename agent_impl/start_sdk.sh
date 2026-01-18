#!/bin/bash
cd "$(dirname "$0")"

echo "🚀 启动 LangGraph 服务..."
export PATH="/Users/wuyu/Library/Python/3.11/bin:$PATH"
langgraph dev --port 2024 --no-browser &
LANGGRAPH_PID=$!

echo "⏳ 等待服务启动..."
sleep 5

echo "🚀 启动 FastAPI 服务 (SDK 版本)..."
python server_sdk.py &
FASTAPI_PID=$!

echo "✅ 服务已启动"
echo "LangGraph PID: $LANGGRAPH_PID"
echo "FastAPI PID: $FASTAPI_PID"
echo "访问地址: http://localhost:8000"
echo "LangSmith Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024"

trap "kill $LANGGRAPH_PID $FASTAPI_PID 2>/dev/null" EXIT

wait
