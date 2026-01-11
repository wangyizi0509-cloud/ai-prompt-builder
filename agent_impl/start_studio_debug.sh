#!/bin/bash
# 启动 Studio 并显示详细输出

cd "$(dirname "$0")"

echo "🚀 启动 LangSmith Studio 服务器..."
echo "📁 工作目录: $(pwd)"
echo ""

# 检查配置文件
if [ ! -f "langgraph.json" ]; then
    echo "❌ 未找到 langgraph.json"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "❌ 未找到 .env 文件"
    exit 1
fi

echo "✅ 配置文件检查通过"
echo ""

# 启动服务器
echo "正在启动服务器..."
echo "---"
echo ""

npx @langchain/langgraph-cli dev







