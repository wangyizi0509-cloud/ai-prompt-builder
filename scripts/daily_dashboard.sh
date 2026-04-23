#!/bin/bash
# Crushe 数据仪表盘 · 一键工具
#
# 用法：
#   bash scripts/daily_dashboard.sh start    # 启服务（LangGraph + FastAPI）
#   bash scripts/daily_dashboard.sh stop     # 停服务
#   bash scripts/daily_dashboard.sh status   # 看服务状态
#   bash scripts/daily_dashboard.sh open     # 浏览器打开仪表盘
#   bash scripts/daily_dashboard.sh feishu   # 立刻推一条飞书（昨天数据）
#   bash scripts/daily_dashboard.sh feishu 2026-04-22  # 推指定日期
#   bash scripts/daily_dashboard.sh funnel   # 终端查今日漏斗
#   bash scripts/daily_dashboard.sh events   # 终端查最近 20 条事件
#   bash scripts/daily_dashboard.sh llm      # 终端查 LLM 健康

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$REPO_ROOT/.venv/bin/python3"
cd "$REPO_ROOT" || exit 1

# ────────── colors ──────────
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

say() { echo -e "${CYAN}→${NC} $*"; }
ok()  { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
err()  { echo -e "${RED}✗${NC} $*"; }

# ────────── commands ──────────

cmd_start() {
  say "启动 LangGraph + FastAPI…"
  "$VENV_PY" .trae/skills/service-manager/scripts/start_services.py --mode dev
  say "等服务就绪…"
  for i in 1 2 3 4 5 6 7 8 9 10; do
    code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null)
    if [ "$code" = "200" ]; then ok "服务就绪 (尝试 $i 次)"; break; fi
    sleep 2
  done
  echo
  ok "访问地址:"
  echo "  • 主产品:    http://localhost:8000/splash.html"
  echo "  • 数据仪表盘: http://localhost:8000/dashboard.html"
}

cmd_stop() {
  say "停止服务…"
  "$VENV_PY" .trae/skills/service-manager/scripts/stop_services.py
}

cmd_status() {
  local fast lang
  fast=$(lsof -ti :8000 2>/dev/null | head -1)
  lang=$(lsof -ti :2024 2>/dev/null | head -1)
  if [ -n "$fast" ]; then ok "FastAPI 在跑 (PID $fast, :8000)"; else err "FastAPI 未启动 (:8000)"; fi
  if [ -n "$lang" ]; then ok "LangGraph 在跑 (PID $lang, :2024)"; else err "LangGraph 未启动 (:2024)"; fi
}

cmd_open() {
  open http://localhost:8000/dashboard.html
}

cmd_feishu() {
  local date_arg="${1:-}"
  if [ -n "$date_arg" ]; then
    say "推送飞书（日期 = $date_arg）…"
    "$VENV_PY" scripts/funnel_daily_report.py --date "$date_arg"
  else
    say "推送飞书（默认=昨天）…"
    "$VENV_PY" scripts/funnel_daily_report.py
  fi
}

cmd_funnel() {
  local range="${1:-today}"
  say "查询漏斗 range=$range ..."
  if ! curl -s -o /dev/null -w "" "http://localhost:8000/health" 2>/dev/null; then
    err "FastAPI 未启动，先跑: bash scripts/daily_dashboard.sh start"
    exit 2
  fi
  curl -s "http://localhost:8000/api/analytics/funnel?range=$range" | \
    "$VENV_PY" -c "
import sys, json
d = json.loads(sys.stdin.read())
print(f\"\\n📊 {d['label']} 漏斗 · 区间事件 {d['total_events']} 条\\n\")
print(f\"  {'步骤':<25} {'人数':>6}  {'上一步':>10}  {'累计':>8}\")
print(f\"  {'-'*25} {'-'*6}  {'-'*10}  {'-'*8}\")
for s in d['steps']:
    prev = f\"{s['conv_from_prev']:.1f}%\" if s['conv_from_prev'] is not None else '—'
    first = f\"{s['conv_from_first']:.1f}%\" if s['conv_from_first'] is not None else '—'
    print(f\"  {s['label']:<25} {s['users']:>6}  {prev:>10}  {first:>8}\")
print()
"
}

cmd_events() {
  local limit="${1:-20}"
  say "最近 $limit 条事件 ..."
  if ! curl -s -o /dev/null -w "" "http://localhost:8000/health" 2>/dev/null; then
    err "FastAPI 未启动"
    exit 2
  fi
  curl -s "http://localhost:8000/api/analytics/events/recent?limit=$limit" | \
    "$VENV_PY" -c "
import sys, json
from datetime import datetime, timedelta, timezone
d = json.loads(sys.stdin.read())
events = d.get('events', [])
print(f\"\\n最近 {len(events)} 条\\n\")
for ev in events:
    ts = ev['created_at']
    try:
        dt = datetime.fromisoformat(ts.replace('Z','+00:00')) + timedelta(hours=8)
        ts_str = dt.strftime('%m-%d %H:%M:%S')
    except Exception:
        ts_str = ts[:19]
    props = ev.get('props') or {}
    qid = props.get('question_id', '')
    qid_str = f' [{qid}]' if qid else ''
    anon = (ev.get('anonymous_id') or '')[:8]
    print(f\"  {ts_str}  {ev['event_name']:<24}{qid_str:<8}  anon={anon}  src={ev.get('source','')}\")
print()
"
}

cmd_llm() {
  local range="${1:-7d}"
  say "LLM 健康 range=$range ..."
  if ! curl -s -o /dev/null -w "" "http://localhost:8000/health" 2>/dev/null; then
    err "FastAPI 未启动"
    exit 2
  fi
  curl -s "http://localhost:8000/api/analytics/llm_health?range=$range" | \
    "$VENV_PY" -c "
import sys, json
d = json.loads(sys.stdin.read())
print(f\"\\n🤖 LLM 健康 · {d['label']}\\n\")
for name in ['analyze', 'report']:
    b = d.get(name) or {}
    rate = b.get('success_rate_pct')
    ms = b.get('avg_duration_ms')
    rate_s = f\"{rate:.1f}%\" if rate is not None else '—'
    ms_s = f\"{ms/1000:.1f}s\" if ms and ms >= 1000 else (f\"{ms}ms\" if ms else '—')
    print(f\"  {name:<10}  总计 {b.get('total',0):>4} 次   成功率 {rate_s:>7}   平均耗时 {ms_s:>6}\")
print()
"
}

cmd_help() {
  cat <<EOF
Crushe 数据仪表盘 · 本地工具

服务管理:
  start           启动 LangGraph + FastAPI
  stop            停止服务
  status          查看服务状态
  open            浏览器打开仪表盘

查数据（要先 start）:
  funnel [range]  看漏斗 · range: today | yesterday | 7d（默认 today）
  events [N]      看最近 N 条事件明细（默认 20）
  llm [range]     看 LLM 健康 · range: today | yesterday | 7d（默认 7d）

推飞书:
  feishu          推昨天数据到飞书群
  feishu YYYY-MM-DD  推指定日期

示例:
  bash scripts/daily_dashboard.sh start
  bash scripts/daily_dashboard.sh funnel today
  bash scripts/daily_dashboard.sh events 50
  bash scripts/daily_dashboard.sh feishu
EOF
}

# ────────── dispatch ──────────

case "${1:-help}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  open) cmd_open ;;
  feishu) cmd_feishu "${2:-}" ;;
  funnel) cmd_funnel "${2:-today}" ;;
  events) cmd_events "${2:-20}" ;;
  llm) cmd_llm "${2:-7d}" ;;
  help|-h|--help) cmd_help ;;
  *)
    err "未知命令: $1"
    cmd_help
    exit 1
    ;;
esac
