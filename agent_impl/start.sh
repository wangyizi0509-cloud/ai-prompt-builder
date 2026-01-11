#!/bin/bash
# 启动脚本 - Crushe AI Agent
# 使用方法：./start.sh

# 1. 确保在脚本所在目录
cd "$(dirname "$0")"

# 2. 清理旧进程 (Port 8000)
echo "🧹 清理端口 8000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true

# 3. 启动服务
echo "🚀 启动 Agent 服务 (Port 8000)..."
echo "👉 访问地址: http://localhost:8000"
echo "⚠️  注意: 如果浏览器白屏，请使用 Shift+F5 强制刷新"

python3 server.py

