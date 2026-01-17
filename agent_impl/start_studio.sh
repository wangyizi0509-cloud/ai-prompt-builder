#!/bin/bash
# 启动 LangSmith Studio 的脚本

cd "$(dirname "$0")"

echo "🎨 启动 LangSmith Studio..."
echo ""

# 激活项目虚拟环境
if [ -f "../.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "../.venv/bin/activate"
fi

# Studio 调试模式：同步消费维护队列（允许 LLM 归档）
export STUDIO_SYNC_MAINTENANCE=1

# 检查 langgraph CLI
if command -v langgraph &> /dev/null; then
    echo "✅ 找到 langgraph CLI"
    langgraph dev
elif command -v npx &> /dev/null; then
    echo "✅ 使用 npx 启动..."
    npx @langchain/langgraph-cli dev
else
    echo "❌ 未找到 langgraph CLI"
    echo ""
    echo "请先安装 langgraph-cli："
    echo "  pip3 install langgraph-cli"
    exit 1
fi
