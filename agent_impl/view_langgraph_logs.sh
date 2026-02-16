#!/bin/bash
# 查看 LangGraph dev 日志的便捷脚本

cd "$(dirname "$0")"
LOG_FILE="logs/langgraph_dev.log"

if [ ! -f "$LOG_FILE" ]; then
  echo "❌ 日志文件不存在: $LOG_FILE"
  echo "💡 请先启动服务: python3 .trae/skills/service-manager/scripts/start_services.py --mode dev"
  exit 1
fi

echo "📝 LangGraph Dev 日志文件: $LOG_FILE"
echo "=" 
echo ""

# 如果提供了参数，使用 tail -f 实时查看
if [ "$1" == "-f" ] || [ "$1" == "--follow" ]; then
  echo "🔄 实时查看日志 (按 Ctrl+C 退出)..."
  echo ""
  tail -f "$LOG_FILE"
else
  # 默认显示最后 50 行
  echo "📄 最后 50 行日志:"
  echo ""
  tail -n 50 "$LOG_FILE"
  echo ""
  echo "💡 使用 '$0 -f' 或 '$0 --follow' 实时查看日志"
fi
