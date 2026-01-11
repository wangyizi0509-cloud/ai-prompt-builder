#!/bin/bash
# 启动 LangSmith Studio 的脚本

cd "$(dirname "$0")"

echo "🎨 启动 LangSmith Studio..."
echo ""

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
    echo ""
    echo "或者使用 npm："
    echo "  npx @langchain/langgraph-cli dev"
    echo ""
    echo "如果安装失败，可以尝试："
    echo "  pip3 install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org langgraph-cli"
    exit 1
fi

