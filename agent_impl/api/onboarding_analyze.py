"""Onboarding v2 · `/api/onboarding/analyze` 路由

极简包装：请求体 Pydantic 校验 → 调 `run_analyze` → 返回响应。

- 本模块**只负责**路由声明，挂到 FastAPI app 的责任在 Agent D（`server.py`）
- 所有异常兜底都在 `run_analyze` 内部实现（契约要求返回 200 + 降级 payload）
- 如果请求体不合法（例如 `free_text < 5`），由 FastAPI/Pydantic 直接抛 422，
  符合契约 §2「降级行为」里 `free_text < 5 字 → HTTP 422」的约定
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter

from api.track import log_event_server
from onboarding_v2.nodes.analyze import run_analyze
from onboarding_v2.schemas import AnalyzeRequest, AnalyzeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(req: AnalyzeRequest) -> AnalyzeResponse:
    """合一分析端点：筛题 + 第一个钩子。

    参见 `onboarding_v2/API_CONTRACT.md §2` 与 `onboarding_v2/nodes/analyze.py` 的
    降级策略：任何 LLM/解析错误都会返回「全不跳 + 兜底钩子」而非 5xx。
    """
    logger.info(
        "[onboarding_v2.analyze] POST /api/onboarding/analyze session=%s "
        "text_len=%d images=%d",
        req.session_id,
        len(req.free_text or ""),
        len(req.image_urls or []),
    )
    t0 = time.monotonic()
    success = False
    skip_count = 0
    try:
        resp = await run_analyze(
            req,
            langsmith_extra={"metadata": {"session_id": req.session_id or "", "device_id": req.device_id or ""}},
        )
        # 判断是否走了降级：降级态下 5 题 skip 全 False、verdict_tag 为「先补信息」
        is_fallback = (
            resp.first_hook.verdict_tag == "先补信息"
            and not any(r.skip for r in resp.skip_rules.values())
        )
        success = not is_fallback
        skip_count = sum(1 for r in resp.skip_rules.values() if r.skip)
        return resp
    finally:
        log_event_server(
            anonymous_id=req.session_id,
            session_id=req.session_id,
            event_name="analyze_success" if success else "analyze_fallback",
            props={
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "text_len": len(req.free_text or ""),
                "image_count": len(req.image_urls or []),
                "ocr_count": len(req.ocr_texts or []),
                "skip_count": skip_count,
            },
        )
