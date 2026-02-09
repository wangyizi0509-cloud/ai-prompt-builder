#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-dev}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEARCH_DIR="$SCRIPT_DIR"
REPO_ROOT=""
while [[ "$SEARCH_DIR" != "/" ]]; do
  if [[ -d "$SEARCH_DIR/.trae" ]]; then
    REPO_ROOT="$SEARCH_DIR"
    break
  fi
  SEARCH_DIR="$(dirname "$SEARCH_DIR")"
done

if [[ -z "$REPO_ROOT" ]]; then
  echo "ERROR: could not locate repo root (missing .trae directory)." >&2
  exit 1
fi

SERVICE_MANAGER_DIR="$REPO_ROOT/.trae/skills/service-manager/scripts"
START_SERVICES="$SERVICE_MANAGER_DIR/start_services.py"
STOP_SERVICES="$SERVICE_MANAGER_DIR/stop_services.py"

if [[ ! -f "$START_SERVICES" || ! -f "$STOP_SERVICES" ]]; then
  echo "ERROR: service-manager scripts not found under $SERVICE_MANAGER_DIR" >&2
  exit 1
fi

if [[ "$MODE" != "dev" && "$MODE" != "up" ]]; then
  echo "Usage: $0 [dev|up]" >&2
  exit 2
fi

export DEBUG_MODE="${DEBUG_MODE:-1}"
export UVICORN_RELOAD="${UVICORN_RELOAD:-0}"
export LLM_PROVIDER="${LLM_PROVIDER:-mock}"
export PATH="$PATH:$(python3 -m site --user-base)/bin"

cleanup() {
  python3 "$STOP_SERVICES" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "== Crushe 非流式验收 =="
echo "- mode: $MODE"
echo "- DEBUG_MODE: $DEBUG_MODE"
echo "- UVICORN_RELOAD: $UVICORN_RELOAD"
echo "- LLM_PROVIDER: $LLM_PROVIDER"

python3 "$STOP_SERVICES" >/dev/null 2>&1 || true
python3 "$START_SERVICES" --mode "$MODE"

python3 - <<'PY'
import time
import urllib.request

url = "http://127.0.0.1:8000/openapi.json"
deadline = time.time() + 30
last_err = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if resp.status == 200:
                print("✅ FastAPI is up:", url)
                raise SystemExit(0)
    except Exception as e:
        last_err = e
        time.sleep(0.25)
print("❌ FastAPI failed to start:", last_err)
raise SystemExit(1)
PY

cd "$REPO_ROOT/agent_impl"

echo
echo "== 1) 单元/集成（不含 api_test）=="
python3 -m pytest -q tests/ -m "not api_test"

echo
echo "== 2) 非流式 API 验收（仅 interrupt/resume）=="
python3 -m pytest -q -m api_test tests/test_interrupt_http_api.py -rA

echo
echo "✅ 验收通过（非流式）"
