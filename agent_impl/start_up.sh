#!/bin/bash
cd "$(dirname "$0")"

# Load .env for both LangGraph CLI and FastAPI (export vars)
if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

# Prefer micromamba env (Python>=3.11) if available
ROOT_DIR="$(cd .. && pwd)"
MAMBA_BIN="${ROOT_DIR}/.tools/micromamba"
export MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-${ROOT_DIR}/.mamba}"
RUN_PREFIX=""
if [ -x "${MAMBA_BIN}" ] && [ -d "${MAMBA_ROOT_PREFIX}/envs/agent" ]; then
  RUN_PREFIX="${MAMBA_BIN} run -n agent"
fi

# 生产级验证模式端口
PORT=${LANGGRAPH_PORT:-8123}
export DEBUG_MODE=1
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LANGGRAPH_LOG="$LOG_DIR/langgraph_up.log"
FASTAPI_LOG="$LOG_DIR/fastapi_up.log"

echo "🚀 启动 LangGraph 服务 (Docker Stack)..."
# 使用 langgraph up 启动生产级环境
export PATH="$PATH:$(python3 -m site --user-base)/bin"
LANGGRAPH_PID=""
if [ -n "$RUN_PREFIX" ] || command -v langgraph >/dev/null 2>&1; then
  if [ -n "$RUN_PREFIX" ]; then
    nohup $RUN_PREFIX langgraph up --port $PORT --wait >> "$LANGGRAPH_LOG" 2>&1 &
  else
    nohup langgraph up --port $PORT --wait >> "$LANGGRAPH_LOG" 2>&1 &
  fi
  LANGGRAPH_PID=$!
else
  echo "⚠️  未找到 langgraph CLI（请确认已安装 langgraph-cli，或已激活虚拟环境）"
  echo "   你仍然可以先预览前端，但聊天/工作流相关能力可能不可用。"
fi

echo "⏳ 等待 LangGraph 服务启动 (可能需要拉取镜像)..."
sleep 15

echo "🚀 启动 FastAPI 服务 (连接到 http://localhost:$PORT)..."
# 强制环境变量以确保连接到正确的端口
export LANGGRAPH_LOCAL_URL="http://127.0.0.1:$PORT"
if [ -n "$RUN_PREFIX" ]; then
  nohup $RUN_PREFIX python server.py >> "$FASTAPI_LOG" 2>&1 &
else
  nohup python3 server.py >> "$FASTAPI_LOG" 2>&1 &
fi
FASTAPI_PID=$!

echo "✅ 服务已启动"
if [ -n "$LANGGRAPH_PID" ]; then
  echo "LangGraph PID: $LANGGRAPH_PID"
fi
echo "FastAPI PID: $FASTAPI_PID"
echo "FastAPI 日志: $FASTAPI_LOG"
echo "访问地址: http://localhost:8000"
LAN_IP="$(python3 - <<'PY'
import socket

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(("8.8.8.8", 80))
    print(s.getsockname()[0])
except Exception:
    print("")
finally:
    s.close()
PY
)"
if [ -n "$LAN_IP" ]; then
  echo "iOS/真机访问: http://$LAN_IP:8000"
fi
echo "LangSmith Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:$PORT"
