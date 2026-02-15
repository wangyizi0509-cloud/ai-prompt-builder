#!/bin/sh
set -eu

echo "[boot] starting FastAPI container"
echo "[boot] pwd=$(pwd)"
echo "[boot] PORT=${PORT:-8000}"
echo "[boot] DEBUG_MODE=${DEBUG_MODE:-unset}"
echo "[boot] python=$(command -v python || true)"
echo "[boot] uvicorn=$(command -v uvicorn || true)"

exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}" --log-level info
