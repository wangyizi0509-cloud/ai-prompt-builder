#!/bin/bash
# 本地直接运行模式 - 不需要 Docker / langgraph dev
# 直接在进程内运行 LangGraph workflow

cd "$(dirname "$0")"

echo "=============================================="
echo "🚀 本地直接运行模式"
echo "   不需要 Docker / langgraph dev"
echo "=============================================="
echo ""

# 激活虚拟环境 (优先使用 .venv，因为依赖更完整)
if [ -d "../.venv" ]; then
    source ../.venv/bin/activate
    echo "✅ 使用虚拟环境: .venv (Python 3.13)"
elif [ -d "../.venv312" ]; then
    source ../.venv312/bin/activate
    echo "✅ 使用虚拟环境: .venv312 (Python 3.12)"
fi

# 运行本地服务器
echo ""
echo "📍 服务启动中..."
echo "   - 前端界面: http://localhost:8000"
echo "   - API 文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python server_local.py
