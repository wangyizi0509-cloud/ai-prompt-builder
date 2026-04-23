"""每日漏斗推送 · 飞书群机器人

从 Supabase 的 events 表聚合"昨天（北京时间）"的销售漏斗 + LLM 健康，
组装成飞书交互卡片 POST 到群机器人 webhook。

环境变量：
  - SUPABASE_URL                 （必需）
  - SUPABASE_SERVICE_ROLE_KEY    （必需）
  - FEISHU_WEBHOOK_URL           （必需）飞书群机器人 webhook
  - FEISHU_SIGN_SECRET           （必需）飞书签名校验密钥
  - DASHBOARD_URL                （可选）仪表盘公网地址，用于卡片"查看完整数据"按钮；
                                       未配置时按钮会隐藏

用法：
  python scripts/funnel_daily_report.py                  # 推送昨日数据到飞书
  python scripts/funnel_daily_report.py --date 2026-04-21  # 推送指定日期
  python scripts/funnel_daily_report.py --dry-run        # 只打印不推送
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from supabase import Client, create_client

# 本地跑时自动读 agent_impl/.env（CI 会走 env 覆盖所以不影响）
try:
    from dotenv import load_dotenv as _load_dotenv
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _load_dotenv(os.path.join(_repo_root, "agent_impl", ".env"))
    _load_dotenv(os.path.join(_repo_root, ".env"), override=False)
except ImportError:
    pass  # CI 环境没装 dotenv 也行，env 会直接从 secrets 来

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("funnel_daily_report")


# ============================================================
# 常量 & 配置
# ============================================================

FUNNEL_STEPS: list[tuple[Any, str]] = [
    ("splash_view", "Splash 曝光"),
    ("description_submit", "提交描述+截图"),
    ({"event": "question_answer", "question_id": "A1"}, "回答 A1（怎么认识）"),
    ({"event": "question_answer", "question_id": "A2"}, "回答 A2（认识多久）"),
    ({"event": "question_answer", "question_id": "A3"}, "回答 A3（做过什么）"),
    ({"event": "question_answer", "question_id": "A4"}, "回答 A4（遇到什么）"),
    ({"event": "question_answer", "question_id": "A5"}, "回答 A5（想解决什么）"),
    ("onboarding_complete", "完成题库"),
    ("report_view", "看到报告"),
    ("pay_success", "付费成功"),
    ("first_message_send", "发首条消息"),
]

LLM_EVENTS = [
    "analyze_success",
    "analyze_fallback",
    "report_success",
    "report_failure",
]


def _event_names_for_funnel() -> list[str]:
    names: set[str] = set()
    for spec, _ in FUNNEL_STEPS:
        if isinstance(spec, str):
            names.add(spec)
        elif isinstance(spec, dict):
            names.add(spec["event"])
    return list(names)


def _row_matches(row: dict[str, Any], spec: Any) -> bool:
    if isinstance(spec, str):
        return row.get("event_name") == spec
    if isinstance(spec, dict):
        if row.get("event_name") != spec.get("event"):
            return False
        props = row.get("props") or {}
        for key, val in spec.items():
            if key == "event":
                continue
            if props.get(key) != val:
                return False
        return True
    return False


# ============================================================
# 时间工具
# ============================================================


def beijing_day_range(day_str: str | None = None) -> tuple[datetime, datetime, str]:
    """给定 YYYY-MM-DD（北京）返回对应那一天的 UTC 起止时间 + 标签。
    day_str=None 表示"昨天（北京时间）"。
    """
    if day_str is None:
        now_bj = datetime.now(timezone.utc) + timedelta(hours=8)
        day_bj = now_bj.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    else:
        try:
            day_bj = datetime.strptime(day_str, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        except ValueError:
            raise SystemExit(f"invalid --date: {day_str}, expect YYYY-MM-DD")

    start_utc = (day_bj - timedelta(hours=8)).replace(tzinfo=timezone.utc)
    end_utc = start_utc + timedelta(days=1)
    label = day_bj.strftime("%Y-%m-%d")
    return start_utc, end_utc, label


# ============================================================
# Supabase 拉事件
# ============================================================


def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def fetch_events(
    sb: Client,
    start_utc: datetime,
    end_utc: datetime,
    event_names: list[str],
) -> list[dict[str, Any]]:
    """分页拉指定事件名在时间段内的全部数据。"""
    page_size = 1000
    offset = 0
    all_rows: list[dict[str, Any]] = []

    while True:
        resp = (
            sb.table("events")
            .select("event_name, anonymous_id, props, created_at")
            .gte("created_at", start_utc.isoformat())
            .lt("created_at", end_utc.isoformat())
            .in_("event_name", event_names)
            .order("created_at", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
        if offset > 50000:
            break

    return all_rows


# ============================================================
# 聚合
# ============================================================


def build_funnel(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """以 anonymous_id 去重算每步人数，支持按 props 字段细化匹配。"""
    step_users: list[set[str]] = [set() for _ in FUNNEL_STEPS]
    for r in rows:
        anon = r.get("anonymous_id")
        if not anon:
            continue
        for i, (spec, _) in enumerate(FUNNEL_STEPS):
            if _row_matches(r, spec):
                step_users[i].add(anon)

    out: list[dict[str, Any]] = []
    first_count: int | None = None
    prev_count: int | None = None
    for i, (spec, label) in enumerate(FUNNEL_STEPS):
        c = len(step_users[i])
        conv_prev = (c / prev_count * 100) if prev_count else None
        conv_first = (c / first_count * 100) if first_count else None
        out.append({
            "label": label, "users": c,
            "conv_prev": conv_prev, "conv_first": conv_first,
        })
        if first_count is None:
            first_count = c
        prev_count = c
    return out


def build_llm_health(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets = {"analyze": {"success": 0, "fail": 0, "durs": []},
               "report": {"success": 0, "fail": 0, "durs": []}}
    for r in rows:
        n = r["event_name"]
        props = r.get("props") or {}
        dur = props.get("duration_ms")
        if n == "analyze_success":
            buckets["analyze"]["success"] += 1
            if isinstance(dur, (int, float)): buckets["analyze"]["durs"].append(dur)
        elif n == "analyze_fallback":
            buckets["analyze"]["fail"] += 1
            if isinstance(dur, (int, float)): buckets["analyze"]["durs"].append(dur)
        elif n == "report_success":
            buckets["report"]["success"] += 1
            if isinstance(dur, (int, float)): buckets["report"]["durs"].append(dur)
        elif n == "report_failure":
            buckets["report"]["fail"] += 1

    def summarize(b):
        total = b["success"] + b["fail"]
        rate = round(b["success"] / total * 100, 1) if total else None
        avg_ms = round(sum(b["durs"]) / len(b["durs"])) if b["durs"] else None
        return {"total": total, "success_rate_pct": rate, "avg_duration_ms": avg_ms}

    return {"analyze": summarize(buckets["analyze"]), "report": summarize(buckets["report"])}


def diff_pct(today: int, yesterday: int) -> str:
    """返回涨跌箭头 + 百分比。"""
    if yesterday == 0 and today == 0:
        return ""
    if yesterday == 0:
        return " (新增)"
    delta = (today - yesterday) / yesterday * 100
    if abs(delta) < 0.5:
        return ""
    arrow = "↑" if delta > 0 else "↓"
    return f" ({arrow}{abs(delta):.0f}%)"


# ============================================================
# 飞书卡片
# ============================================================


def gen_feishu_sign(secret: str, timestamp: int) -> str:
    """飞书签名校验（open.feishu.cn/document/client-docs/bot-v3/add-custom-bot）"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _fmt_users(n: int) -> str:
    if n >= 10000:
        return f"{n / 10000:.1f}w"
    return str(n)


def build_feishu_card(
    *,
    label: str,
    today_funnel: list[dict[str, Any]],
    yesterday_funnel: list[dict[str, Any]] | None,
    llm_health: dict[str, dict[str, Any]],
    dashboard_url: str | None,
) -> dict[str, Any]:
    """组装飞书交互卡片。

    飞书卡片 v1 协议：https://open.feishu.cn/document/common-capabilities/message-card/
    """
    # 漏斗主体：每步一行
    funnel_lines: list[str] = []
    prev_today = today_funnel[0]["users"] if today_funnel else 0
    for idx, step in enumerate(today_funnel):
        users_str = _fmt_users(step["users"])
        # 与昨天同步对比
        yday_users = (
            yesterday_funnel[idx]["users"]
            if yesterday_funnel and idx < len(yesterday_funnel)
            else 0
        )
        dod = diff_pct(step["users"], yday_users)
        # 转化率
        if idx == 0:
            conv_str = "— 起点"
        elif step["conv_prev"] is not None:
            conv_str = f"转化 **{step['conv_prev']:.1f}%**"
        else:
            conv_str = "转化 —"

        funnel_lines.append(
            f"**{step['label']}**：{users_str}{dod}\n<font color='grey'>↳ {conv_str}</font>"
        )

    funnel_md = "\n\n".join(funnel_lines)

    # 整体漏斗转化（第一步 → 最后一步）
    first_u = today_funnel[0]["users"] if today_funnel else 0
    last_u = today_funnel[-1]["users"] if today_funnel else 0
    overall = f"{first_u} → {last_u}"
    overall_pct = (
        f"（整体 {last_u / first_u * 100:.1f}%）" if first_u > 0 else ""
    )

    # LLM
    a = llm_health["analyze"]
    r = llm_health["report"]
    def rate_str(b):
        if b["total"] == 0:
            return "无调用"
        rate = b["success_rate_pct"]
        ms = b["avg_duration_ms"]
        ms_str = f"{ms / 1000:.1f}s" if ms and ms >= 1000 else f"{ms}ms" if ms else "—"
        return f"{rate}% · {b['total']} 次 · avg {ms_str}"

    llm_md = (
        f"**analyze**：{rate_str(a)}\n"
        f"**report**：{rate_str(r)}"
    )

    elements = [
        {"tag": "div", "text": {"tag": "lark_md", "content": funnel_md}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**整体漏斗**: {overall} {overall_pct}"}},
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**LLM 健康**\n{llm_md}"}},
    ]

    if dashboard_url:
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📊 打开完整仪表盘"},
                "type": "primary",
                "url": dashboard_url,
            }],
        })

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "purple",
            "title": {"tag": "plain_text", "content": f"📊 Crushe 漏斗日报 · {label}"},
        },
        "elements": elements,
    }
    return card


def post_feishu(webhook: str, sign_secret: str, card: dict[str, Any]) -> dict[str, Any]:
    ts = int(time.time())
    sign = gen_feishu_sign(sign_secret, ts)
    payload = {
        "timestamp": str(ts),
        "sign": sign,
        "msg_type": "interactive",
        "card": card,
    }
    r = requests.post(webhook, json=payload, timeout=15)
    try:
        return {"status": r.status_code, "body": r.json()}
    except Exception:
        return {"status": r.status_code, "body": r.text}


# ============================================================
# main
# ============================================================


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="YYYY-MM-DD (北京) 默认=昨天", default=None)
    p.add_argument("--dry-run", action="store_true", help="只打印卡片 JSON，不推送")
    args = p.parse_args()

    sb = get_supabase_client()

    # 今日（= 指定 date）
    start_today, end_today, label = beijing_day_range(args.date)
    logger.info("querying %s UTC %s ~ %s", label, start_today.isoformat(), end_today.isoformat())

    # 昨日（用于对比）
    start_yday = start_today - timedelta(days=1)
    end_yday = start_today

    funnel_event_names = _event_names_for_funnel()

    today_rows = fetch_events(sb, start_today, end_today, funnel_event_names)
    yday_rows = fetch_events(sb, start_yday, end_yday, funnel_event_names)
    llm_rows = fetch_events(sb, start_today, end_today, LLM_EVENTS)

    today_funnel = build_funnel(today_rows)
    yday_funnel = build_funnel(yday_rows)
    llm_health = build_llm_health(llm_rows)

    logger.info("today funnel: %s", [(s["label"], s["users"]) for s in today_funnel])
    logger.info("yday funnel:  %s", [(s["label"], s["users"]) for s in yday_funnel])
    logger.info("llm analyze: %s | report: %s", llm_health["analyze"], llm_health["report"])

    dashboard_url = os.getenv("DASHBOARD_URL") or None
    card = build_feishu_card(
        label=label,
        today_funnel=today_funnel,
        yesterday_funnel=yday_funnel,
        llm_health=llm_health,
        dashboard_url=dashboard_url,
    )

    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return 0

    webhook = os.getenv("FEISHU_WEBHOOK_URL")
    secret = os.getenv("FEISHU_SIGN_SECRET")
    if not webhook or not secret:
        logger.error("missing FEISHU_WEBHOOK_URL or FEISHU_SIGN_SECRET")
        return 2

    result = post_feishu(webhook, secret, card)
    logger.info("feishu response: %s", result)
    if result.get("status") != 200:
        return 3
    body = result.get("body")
    if isinstance(body, dict) and body.get("code") not in (0, None):
        logger.error("feishu returned error: %s", body)
        return 4
    logger.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
