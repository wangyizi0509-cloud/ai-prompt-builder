#!/usr/bin/env python3
"""Judge chat screenshot eval packets with an OpenAI vision model."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

try:
    from scripts.chat_screenshot_eval_common import (
        compute_critical_fail,
        compute_weighted_score,
        load_jsonl,
        now_iso,
        write_jsonl,
    )
except ImportError:
    from chat_screenshot_eval_common import (  # type: ignore[no-redef]
        compute_critical_fail,
        compute_weighted_score,
        load_jsonl,
        now_iso,
        write_jsonl,
    )



def default_model_candidates() -> list[str]:
    candidates = ["gpt-5.4", os.getenv("OPENAI_MODEL", "gpt-4o")]
    deduped: list[str] = []
    for item in candidates:
        value = str(item or "").strip()
        if value and value not in deduped:
            deduped.append(value)
    return deduped
ALLOWED_ISSUE_TAGS = [
    "sender_flip",
    "speaker_swap_major",
    "message_missing",
    "time_separator_as_message",
    "massive_hallucination",
    "fabricated_content",
    "ui_noise",
    "ui_noise_as_message",
    "system_line_fabricated",
    "minor_text_noise",
    "image_semantics_overreach",
    "reply_bar_as_message",
    "quote_bar_as_message",
    "temporal_drift",
    "long_chat_drift",
]


def _image_data_url(image_path: Path) -> str:
    suffix = image_path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(suffix, "image/jpeg")
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```", 1)[1]
        raw = raw.split("```", 1)[0]
        raw = raw.lstrip("json").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        payload = json.loads(raw[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("judge output must be a JSON object")
    return payload


def _normalize_result(image_id: str, result: dict[str, Any]) -> dict[str, Any]:
    scores = result.get("scores") or {}
    weighted_score = round(float(result.get("weighted_score") or compute_weighted_score(scores)), 3)
    issue_tags = [str(item).strip() for item in (result.get("issue_tags") or []) if str(item).strip()]
    critical_fail = result.get("critical_fail")
    critical_fail_reasons = result.get("critical_fail_reasons")
    expected_fail, expected_reasons = compute_critical_fail(scores, issue_tags)
    if critical_fail is None:
        critical_fail = expected_fail
    if critical_fail_reasons is None:
        critical_fail_reasons = expected_reasons
    confidence = round(float(result.get("confidence") or 0.5), 3)
    evidence = [str(item).strip() for item in (result.get("evidence") or []) if str(item).strip()]
    return {
        "image_id": image_id,
        "scores": scores,
        "weighted_score": weighted_score,
        "critical_fail": bool(critical_fail),
        "critical_fail_reasons": [str(item).strip() for item in critical_fail_reasons if str(item).strip()],
        "issue_tags": issue_tags,
        "judge_summary": str(result.get("judge_summary") or "").strip() or "未提供评审摘要",
        "evidence": evidence,
        "confidence": confidence,
    }


def _build_prompt(packet: dict[str, Any]) -> str:
    rubric = packet["scoring_dimensions"]
    api_result = packet["api_result"]
    prompt = {
        "task": packet["judge_task"],
        "rubric": rubric,
        "critical_fail_rules": packet["critical_fail_rules"],
        "allowed_issue_tags": ALLOWED_ISSUE_TAGS,
        "image_id": packet["image_id"],
        "image_meta": packet["image_meta"],
        "api_output": {
            "success": api_result["success"],
            "detected_screenshot_type": api_result["detected_screenshot_type"],
            "final_screenshot_type": api_result["final_screenshot_type"],
            "ocr_text": api_result["ocr_text"],
            "error": api_result["error"],
            "latency_ms": api_result["latency_ms"],
        },
        "instructions": [
            "先看原图，再看 OCR 输出。",
            "严格按 1-5 分评分。",
            "speaker attribution 错误要重点惩罚；左右气泡翻转通常应 <=2。",
            "把时间分隔线、回复条、引用条、界面按钮误写成消息时，要下调 hallucination_control，并视情况打 forbidden issue tag。",
            "如果存在严重错误，critical_fail 必须为 true。",
            "issue_tags 只保留高价值标签，数量控制在 1-4 个。",
            "只返回 JSON，不要输出解释文字。",
        ],
        "output_schema": {
            "image_id": "str",
            "scores": {
                "speaker_attribution": "int 1-5",
                "message_recall": "int 1-5",
                "temporal_order": "int 1-5",
                "hallucination_control": "int 1-5",
                "text_accuracy": "int 1-5",
                "image_semantics": "int 1-5",
                "format_stability": "int 1-5",
            },
            "weighted_score": "float",
            "critical_fail": "bool",
            "critical_fail_reasons": ["str"],
            "issue_tags": ["str"],
            "judge_summary": "str",
            "evidence": ["str"],
            "confidence": "float 0-1",
        },
    }
    return json.dumps(prompt, ensure_ascii=False, indent=2)


def _call_model(client: OpenAI, model: str, packet: dict[str, Any]) -> dict[str, Any]:
    image_path = Path(packet["image_path"])
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "你是严谨的聊天截图 OCR 评审员，只能输出 JSON。",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_prompt(packet)},
                    {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                ],
            },
        ],
    )
    content = response.choices[0].message.content or ""
    parsed = _extract_json(content)
    normalized = _normalize_result(packet["image_id"], parsed)
    normalized["_judge_model"] = model
    return normalized


def judge_packets(
    *,
    packets_path: Path,
    output_path: Path,
    model_candidates: list[str],
    limit: int | None = None,
    retry_count: int = 2,
) -> dict[str, Any]:
    rows = load_jsonl(packets_path)
    if limit is not None:
        rows = rows[: max(0, limit)]

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL") or None)
    results: list[dict[str, Any]] = []
    used_model: str | None = None

    for idx, packet in enumerate(rows, start=1):
        last_error: str | None = None
        chosen_model: str | None = None
        for model in model_candidates:
            if not model:
                continue
            for attempt in range(1, retry_count + 2):
                try:
                    judged = _call_model(client, model, packet)
                    chosen_model = model
                    used_model = used_model or model
                    results.append(judged)
                    print(
                        json.dumps(
                            {
                                "index": idx,
                                "image_id": packet["image_id"],
                                "model": model,
                                "attempt": attempt,
                                "ok": True,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                    break
                except Exception as exc:  # pragma: no cover - exercised in real runs
                    last_error = f"{type(exc).__name__}: {exc}"
                    if attempt <= retry_count:
                        time.sleep(1.0 * attempt)
                        continue
            if chosen_model:
                break
        if not chosen_model:
            raise RuntimeError(f"judge failed for {packet['image_id']}: {last_error}")

    write_jsonl(output_path, results)
    return {
        "generated_at": now_iso(),
        "packet_count": len(rows),
        "judge_count": len(results),
        "model_candidates": model_candidates,
        "used_model": used_model,
        "output_path": str(output_path.resolve()),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--packets-jsonl", default="")
    parser.add_argument("--output-jsonl", default="")
    parser.add_argument("--judge-model", action="append", default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--retry-count", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    args = parse_args(argv or sys.argv[1:])
    run_dir = Path(args.run_dir).resolve()
    packets_path = Path(args.packets_jsonl).resolve() if args.packets_jsonl else run_dir / "judge_packets.jsonl"
    output_path = Path(args.output_jsonl).resolve() if args.output_jsonl else run_dir / "judge_results.jsonl"
    model_candidates = [item for item in (args.judge_model or []) if item] or default_model_candidates()
    summary = judge_packets(
        packets_path=packets_path,
        output_path=output_path,
        model_candidates=model_candidates,
        limit=args.limit,
        retry_count=max(0, args.retry_count),
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
