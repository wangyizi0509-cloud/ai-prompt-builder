#!/bin/bash
echo "🛑 停止服务..."

lsof -ti :2024 | xargs kill -9 2>/dev/null
echo "✅ LangGraph 服务已停止"

lsof -ti :8000 | xargs kill -9 2>/dev/null
echo "✅ FastAPI 服务已停止"

echo "✅ 所有服务已停止"
