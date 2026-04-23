"""埋点事件上报端点 + 服务端打点 helper。

职责：
  - `POST /api/track` 接收前端批量事件，写入 Supabase `events` 表
  - `log_event_server(...)` 供后端其他模块（onboarding_analyze/report, chat）直接打点
  - Supabase 不可用时 fallback 写 `local_data/events.jsonl`

与 `supabase_service/client.py` 的模式对齐（execute_supabase 重试 + local 降级）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from supabase_service.client import (
    execute_supabase,
    is_supabase_configured,
    supabase,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/track", tags=["analytics"])


_LOCAL_FALLBACK_PATH = (
    Path(__file__).resolve().parents[1] / "local_data" / "events.jsonl"
)


# ---------- Pydantic schemas ----------


class _TrackEventItem(BaseModel):
    """单条事件。客户端时间戳仅作保留字段，入库时间以服务端 now() 为准。"""

    model_config = ConfigDict(extra="ignore")

    event_name: str = Field(..., min_length=1, max_length=80)
    session_id: str = Field(..., min_length=1, max_length=120)
    props: dict[str, Any] = Field(default_factory=dict)
    ts_client: str | None = None


class TrackRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    anonymous_id: str = Field(..., min_length=1, max_length=120)
    user_id: str | None = None
    events: list[_TrackEventItem] = Field(..., min_length=1, max_length=50)


class TrackResponse(BaseModel):
    ok: bool
    received: int
    stored: int
    source: str  # "supabase" | "local"


# ---------- helpers ----------


def _build_row(
    *,
    anonymous_id: str,
    user_id: str | None,
    event_name: str,
    props: dict[str, Any],
    session_id: str,
    ua: str | None,
    referrer: str | None,
    source: str,
) -> dict[str, Any]:
    return {
        "anonymous_id": anonymous_id,
        "user_id": user_id,
        "session_id": session_id,
        "event_name": event_name,
        "props": props or {},
        "ua": (ua or "")[:500] or None,
        "referrer": (referrer or "")[:500] or None,
        "source": source,
    }


def _write_local_fallback(rows: list[dict[str, Any]]) -> int:
    """Supabase 不可用时的兜底：追加写 JSONL。"""
    _LOCAL_FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    wrote = 0
    with _LOCAL_FALLBACK_PATH.open("a", encoding="utf-8") as f:
        for row in rows:
            # 补个本地时间戳；入 Supabase 时由 default now() 处理
            row_out = dict(row)
            row_out.setdefault(
                "created_at", datetime.now(timezone.utc).isoformat()
            )
            f.write(json.dumps(row_out, ensure_ascii=False) + "\n")
            wrote += 1
    return wrote


def _insert_rows(rows: list[dict[str, Any]]) -> tuple[int, str]:
    """尝试写 Supabase；失败或未配置则写本地 JSONL。

    返回 (stored_count, source)。
    """
    if not rows:
        return 0, "noop"

    if is_supabase_configured():
        try:
            response = execute_supabase(
                lambda: supabase.table("events").insert(rows).execute(),
                op_name="log_events",
            )
            data = getattr(response, "data", None) or []
            return len(data) or len(rows), "supabase"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "events insert to Supabase failed, falling back to local: %s",
                exc,
            )
            wrote = _write_local_fallback(rows)
            return wrote, "local"

    wrote = _write_local_fallback(rows)
    return wrote, "local"


# ---------- public API (server-side helper) ----------


def log_event_server(
    *,
    anonymous_id: str | None,
    session_id: str | None = None,
    event_name: str,
    props: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> None:
    """服务端任意模块直接打点。

    设计为 best-effort：打点失败不抛、不阻断主流程。
    anonymous_id 缺失时用 "server" 占位，session_id 缺失时用 "server".
    """
    try:
        row = _build_row(
            anonymous_id=anonymous_id or "server",
            user_id=user_id,
            event_name=event_name,
            props=props or {},
            session_id=session_id or "server",
            ua=None,
            referrer=None,
            source="backend",
        )
        _insert_rows([row])
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "log_event_server best-effort failure event=%s err=%s",
            event_name,
            exc,
        )


# ---------- REST endpoint ----------


@router.post("", response_model=TrackResponse)
async def track_endpoint(
    request: Request,
    body: TrackRequest,
    user_agent: str | None = Header(default=None, alias="User-Agent"),
    referer: str | None = Header(default=None, alias="Referer"),
) -> TrackResponse:
    """前端批量上报入口。

    - 不需要登录态（本期 onboarding v2 无登录）
    - 失败降级为本地 JSONL，确保事件不丢
    - 永远返回 200（除非 body 不合法，Pydantic 会自动抛 422）
    """
    rows = [
        _build_row(
            anonymous_id=body.anonymous_id,
            user_id=body.user_id,
            event_name=ev.event_name,
            props=ev.props,
            session_id=ev.session_id,
            ua=user_agent,
            referrer=referer,
            source="frontend",
        )
        for ev in body.events
    ]

    stored, source = _insert_rows(rows)
    logger.info(
        "track received anon=%s events=%d stored=%d via=%s",
        body.anonymous_id[:12],
        len(rows),
        stored,
        source,
    )
    return TrackResponse(
        ok=True,
        received=len(rows),
        stored=stored,
        source=source,
    )
