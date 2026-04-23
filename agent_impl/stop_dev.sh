#!/bin/bash
# Onboarding v2 · 开发模式停服务脚本
#
# 背景：start_dev.sh 改为 nohup 后台模式后，Ctrl+C 无法停服务，
# 所以单独提供一个 stop 脚本。粗粒度方式：按进程名 pkill。
#
# 用法：
#   bash agent_impl/stop_dev.sh
#
# 或者（更精确）：如果 PID 记录还能找回，可手工 kill：
#   ps aux | grep -E "langgraph dev|server.py" | grep -v grep
#   kill <PID>

set -u  # 未定义变量即报错；不开 -e 以便 pkill 没找到目标时也继续

echo "🛑 正在停止 Crushe 开发服务（LangGraph + FastAPI）..."

# 1) LangGraph CLI
LANGGRAPH_COUNT=$(pgrep -f "langgraph dev" | wc -l | tr -d ' ')
if [ "${LANGGRAPH_COUNT}" -gt 0 ]; then
  echo "  • 找到 ${LANGGRAPH_COUNT} 个 langgraph dev 进程，发送 SIGTERM"
  pkill -f "langgraph dev" || true
else
  echo "  • 未找到运行中的 langgraph dev 进程"
fi

# 2) FastAPI uvicorn（server.py）
FASTAPI_COUNT=$(pgrep -f "python.*server\.py" | wc -l | tr -d ' ')
if [ "${FASTAPI_COUNT}" -gt 0 ]; then
  echo "  • 找到 ${FASTAPI_COUNT} 个 server.py 进程，发送 SIGTERM"
  pkill -f "python.*server\.py" || true
else
  echo "  • 未找到运行中的 server.py 进程"
fi

# 等待 2 秒让进程正常退出
sleep 2

# 3) 强制清理残留（如果 SIGTERM 没杀干净）
REMAIN_LANGGRAPH=$(pgrep -f "langgraph dev" | wc -l | tr -d ' ')
REMAIN_FASTAPI=$(pgrep -f "python.*server\.py" | wc -l | tr -d ' ')

if [ "${REMAIN_LANGGRAPH}" -gt 0 ] || [ "${REMAIN_FASTAPI}" -gt 0 ]; then
  echo "  • 仍有残留进程（langgraph=${REMAIN_LANGGRAPH}, fastapi=${REMAIN_FASTAPI}），SIGKILL 收尾"
  pkill -9 -f "langgraph dev" || true
  pkill -9 -f "python.*server\.py" || true
fi

echo "✅ 清理完成"
echo ""
echo "💡 提示："
echo "   - 如需查看日志：tail -f logs/langgraph_dev.log logs/fastapi_dev.log"
echo "   - 如需重启服务：bash start_dev.sh"
