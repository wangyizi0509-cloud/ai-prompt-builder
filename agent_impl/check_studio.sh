#!/bin/bash
# 检查 Studio 服务器状态

echo "🔍 检查 LangSmith Studio 服务器状态..."
echo ""

# 检查进程
PROCESSES=$(ps aux | grep -i "langgraph\|node.*langgraph" | grep -v grep | wc -l | tr -d ' ')
if [ "$PROCESSES" -gt 0 ]; then
    echo "✅ 找到 $PROCESSES 个相关进程"
    ps aux | grep -i "langgraph\|node.*langgraph" | grep -v grep | head -2
else
    echo "❌ 未找到运行中的进程"
fi

echo ""

# 检查端口
if lsof -ti:2024 > /dev/null 2>&1; then
    echo "✅ 端口 2024 正在监听"
    lsof -i:2024 | head -2
else
    echo "⚠️  端口 2024 未监听"
fi

echo ""

# 检查 API
echo "📡 测试 API 连接..."
if curl -s http://localhost:2024/api/assistants > /dev/null 2>&1; then
    echo "✅ API 可访问"
    echo ""
    echo "🌐 访问 Studio:"
    echo "   https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024"
elif curl -s http://localhost:2024/docs > /dev/null 2>&1; then
    echo "✅ 服务器运行中（API 可能还在初始化）"
    echo ""
    echo "🌐 访问 Studio:"
    echo "   https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024"
else
    echo "⏳ 服务器可能还在启动中，请稍候..."
    echo ""
    echo "💡 如果长时间无法访问，请检查："
    echo "   1. 查看终端输出是否有错误"
    echo "   2. 检查 .env 文件中的配置"
    echo "   3. 尝试重新启动: ./start_studio.sh"
fi







