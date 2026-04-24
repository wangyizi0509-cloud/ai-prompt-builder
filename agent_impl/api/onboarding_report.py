"""
Onboarding v2 · `/api/onboarding/report` REST 路由(极简转发层)。

挂载归属:Agent D 在 `server.py` 中 `include_router(router)`。
本文件只做"把请求 → 调度 run_report → 返回"的薄壳,核心逻辑在
`onboarding_v2/nodes/report.py`。

降级/错误处理:
- 正常成功 → 200 + DiagnosisReport JSON
- run_report 抛 HTTPException(500, REPORT_GENERATION_FAILED) → 原样透传
- 其他异常 → 由 FastAPI 默认异常处理器兜底为 500
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException

from api.track import log_event_server
from onboarding_v2.nodes.report import run_report
from onboarding_v2.schemas import DiagnosisReport, ReportRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.post("/report", response_model=DiagnosisReport)
async def report_endpoint(req: ReportRequest) -> DiagnosisReport:
    """生成免费诊断报告(LLM 节点③入口)。"""
    t0 = time.monotonic()
    try:
        report = await run_report(
            req,
            langsmith_extra={"metadata": {"session_id": req.session_id or "", "device_id": req.device_id or ""}},
        )
        log_event_server(
            anonymous_id=req.session_id,
            session_id=req.session_id,
            event_name="report_success",
            props={
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "answer_count": len(req.answers or {}),
                "state_label": report.state_label.name,
                "severity": report.state_label.severity,
                "score_A": report.scores_5d.A.score,
                "score_C": report.scores_5d.C.score,
                "score_R": report.scores_5d.R.score,
                "score_T": report.scores_5d.T.score,
                "score_E": report.scores_5d.E.score,
            },
        )
        return report
    except HTTPException as exc:
        log_event_server(
            anonymous_id=req.session_id,
            session_id=req.session_id,
            event_name="report_failure",
            props={
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "status_code": exc.status_code,
                "detail": str(exc.detail)[:200],
            },
        )
        raise
    except Exception as exc:  # noqa: BLE001
        log_event_server(
            anonymous_id=req.session_id,
            session_id=req.session_id,
            event_name="report_failure",
            props={
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "error": str(exc)[:200],
            },
        )
        raise
