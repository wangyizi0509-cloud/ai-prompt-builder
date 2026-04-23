"""分析/仪表盘端点：查 Supabase events 表做聚合。

- GET /api/analytics/funnel?range=today|yesterday|7d
- GET /api/analytics/events/recent?limit=100
- GET /api/analytics/llm_health?range=yesterday|7d

职责：聚合逻辑放后端，前端只渲染。不做鉴权（本期 onboarding v2 无登录）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from supabase_service.client import (
    execute_supabase,
    is_supabase_configured,
    supabase,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# 漏斗定义（匹配规则 + 展示标签，顺序 = 步骤顺序）
# 每一步是 (match_spec, label)
#   match_spec 可以是 str（匹配 event_name）
#   也可以是 dict{"event": "question_answer", "question_id": "A1"}
#     表示匹配 event_name=question_answer 且 props.question_id=A1
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


def _event_names_for_funnel() -> list[str]:
    """从 FUNNEL_STEPS 抽取涉及的所有 event_name（用于 Supabase in_ 过滤）。"""
    names: set[str] = set()
    for spec, _ in FUNNEL_STEPS:
        if isinstance(spec, str):
            names.add(spec)
        elif isinstance(spec, dict):
            names.add(spec["event"])
    return list(names)


def _row_matches(row: dict[str, Any], spec: Any) -> bool:
    """判断一行事件是否匹配某步的 match_spec。"""
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


def _beijing_now() -> datetime:
    """北京时间（UTC+8）。"""
    return datetime.now(timezone.utc) + timedelta(hours=8)


def _range_to_utc(range_key: str) -> tuple[datetime, datetime, str]:
    """把 range 字符串解析成 UTC 起止时间 + 人类可读标签。

    - today:     北京今天 00:00 → now
    - yesterday: 北京昨天 00:00 → 00:00 次日
    - 7d:        近 7 天（含今天）
    """
    bj = _beijing_now()
    bj_midnight = bj.replace(hour=0, minute=0, second=0, microsecond=0)

    if range_key == "today":
        start_bj = bj_midnight
        end_bj = bj
        label = "今日"
    elif range_key == "yesterday":
        start_bj = bj_midnight - timedelta(days=1)
        end_bj = bj_midnight
        label = "昨日"
    elif range_key == "7d":
        start_bj = bj_midnight - timedelta(days=6)
        end_bj = bj
        label = "近 7 天"
    else:
        raise HTTPException(400, detail=f"invalid range: {range_key}")

    # 北京时间转 UTC
    start_utc = (start_bj - timedelta(hours=8)).replace(tzinfo=timezone.utc)
    end_utc = (end_bj - timedelta(hours=8)).replace(tzinfo=timezone.utc)
    return start_utc, end_utc, label


def _fetch_events(
    start_utc: datetime,
    end_utc: datetime,
    event_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """拉回指定时间段 + 事件名过滤的全部事件（Supabase 分页拉）。"""
    if not is_supabase_configured():
        return []

    all_rows: list[dict[str, Any]] = []
    page_size = 1000
    offset = 0

    while True:
        def query(offset_val: int = offset):
            q = (
                supabase.table("events")
                .select("event_name, anonymous_id, session_id, props, created_at")
                .gte("created_at", start_utc.isoformat())
                .lt("created_at", end_utc.isoformat())
                .order("created_at", desc=False)
                .range(offset_val, offset_val + page_size - 1)
            )
            if event_names:
                q = q.in_("event_name", event_names)
            return q.execute()

        resp = execute_supabase(query, op_name="analytics_fetch_events")
        rows = resp.data or []
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
        if offset > 50000:  # 防呆上限
            logger.warning("analytics fetch truncated at 50k rows")
            break

    return all_rows


def _build_funnel(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """以 anonymous_id 去重，按预定义步骤算人数和转化率。

    支持按 props 字段精细匹配（如 question_answer + question_id=A1）。
    """
    # 预先为每一步建一个 user set
    step_users: list[set[str]] = [set() for _ in FUNNEL_STEPS]

    for r in rows:
        anon = r.get("anonymous_id")
        if not anon:
            continue
        for i, (spec, _) in enumerate(FUNNEL_STEPS):
            if _row_matches(r, spec):
                step_users[i].add(anon)

    steps_out: list[dict[str, Any]] = []
    first_count: int | None = None
    prev_count: int | None = None

    for idx, (spec, label) in enumerate(FUNNEL_STEPS):
        count = len(step_users[idx])
        # 为前端展示稳定 id：事件名，或 event:question_id 形式
        step_id = spec if isinstance(spec, str) else f"{spec['event']}:{spec.get('question_id', '')}"
        step = {
            "step_id": step_id,
            "label": label,
            "users": count,
            "conv_from_prev": None,
            "conv_from_first": None,
        }
        if prev_count is not None and prev_count > 0:
            step["conv_from_prev"] = round(count / prev_count * 100, 1)
        if first_count is not None and first_count > 0:
            step["conv_from_first"] = round(count / first_count * 100, 1)
        if first_count is None:
            first_count = count
        prev_count = count
        steps_out.append(step)

    return steps_out


# ---------- endpoints ----------


@router.get("/funnel")
def funnel(
    range: str = Query("today", description="today | yesterday | 7d"),
) -> dict[str, Any]:
    """销售漏斗统计（以 anonymous_id 去重）。"""
    start, end, label = _range_to_utc(range)
    rows = _fetch_events(
        start, end, event_names=_event_names_for_funnel()
    )
    steps = _build_funnel(rows)

    return {
        "range": range,
        "label": label,
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "total_events": len(rows),
        "steps": steps,
    }


@router.get("/events/recent")
def recent_events(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    """最近 N 条事件明细（调试/排查用）。"""
    if not is_supabase_configured():
        return {"events": [], "note": "supabase not configured"}

    resp = execute_supabase(
        lambda: supabase.table("events")
        .select("event_name, anonymous_id, session_id, source, props, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute(),
        op_name="analytics_recent",
    )
    return {"events": resp.data or [], "limit": limit}


@router.get("/llm_health")
def llm_health(
    range: str = Query("yesterday", description="yesterday | 7d | today"),
) -> dict[str, Any]:
    """LLM 端点成功率 + 平均耗时。"""
    start, end, label = _range_to_utc(range)
    rows = _fetch_events(
        start,
        end,
        event_names=[
            "analyze_success",
            "analyze_fallback",
            "report_success",
            "report_failure",
        ],
    )

    buckets: dict[str, dict[str, Any]] = {
        "analyze": {"success": 0, "fail": 0, "durations": []},
        "report": {"success": 0, "fail": 0, "durations": []},
    }
    for r in rows:
        n = r.get("event_name", "")
        props = r.get("props") or {}
        dur = props.get("duration_ms")
        if n == "analyze_success":
            buckets["analyze"]["success"] += 1
            if isinstance(dur, (int, float)):
                buckets["analyze"]["durations"].append(dur)
        elif n == "analyze_fallback":
            buckets["analyze"]["fail"] += 1
            if isinstance(dur, (int, float)):
                buckets["analyze"]["durations"].append(dur)
        elif n == "report_success":
            buckets["report"]["success"] += 1
            if isinstance(dur, (int, float)):
                buckets["report"]["durations"].append(dur)
        elif n == "report_failure":
            buckets["report"]["fail"] += 1

    def summarize(b: dict[str, Any]) -> dict[str, Any]:
        total = b["success"] + b["fail"]
        success_rate = round(b["success"] / total * 100, 1) if total else None
        durs = b["durations"]
        avg_ms = round(sum(durs) / len(durs)) if durs else None
        return {
            "total": total,
            "success": b["success"],
            "fail": b["fail"],
            "success_rate_pct": success_rate,
            "avg_duration_ms": avg_ms,
        }

    return {
        "range": range,
        "label": label,
        "analyze": summarize(buckets["analyze"]),
        "report": summarize(buckets["report"]),
    }
