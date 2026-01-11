#!/bin/bash
# 启动调试服务器的脚本

cd "$(dirname "$0")"

echo "🚀 启动 Agent 调试服务器..."
echo ""
echo "📋 可用功能："
echo "  1. Streaming API: http://localhost:8000/api/chat/stream"
echo "  2. 普通 API: http://localhost:8000/api/chat"
echo "  3. 前端界面: http://localhost:8000"
echo ""
echo "💡 测试 Streaming:"
echo "  python3 test_streaming.py '你的消息'"
echo ""
echo "按 Ctrl+C 停止服务器"
echo ""

python3 server.py

