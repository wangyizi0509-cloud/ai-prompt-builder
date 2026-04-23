#!/usr/bin/env python3
"""Shared helpers for chat screenshot real-API evaluation."""

from __future__ import annotations

import json
import hashlib
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DATASET_DIR = PROJECT_ROOT / "评估集" / "聊天截图"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "chat_screenshot_eval"
STRICT_BASELINE_RUN_ID = "chat_screenshot_eval_20260401_141415"
STRICT_BASELINE_RUN_DIR = DEFAULT_OUTPUT_ROOT / STRICT_BASELINE_RUN_ID
STRICT_BASELINE_FINAL_REPORT = STRICT_BASELINE_RUN_DIR / "final_report.json"
STRICT_BASELINE_API_RESULTS = STRICT_BASELINE_RUN_DIR / "api_results.json"
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
RUBRIC_VERSION = "chat_screenshot_eval_v1"
SCREENSHOT_PROMPT_TYPES = (
    "private_chat_screenshot",
    "group_chat_screenshot",
    "moments_screenshot",
    "other_social_media_screenshot",
    "universal_screenshot_analysis",
    "type_detection",
)
SMALL_EVAL_IMAGE_IDS = [
    "9354d39f7091f12e92f61955039317b8",
    "13401615760079295",
    "5055499a75d867a5bd4059db5caf009e",
    "b62c3f3ba60a0bf425e4656df896e13f",
    "456251df79ce2fe41297edeb115953ff",
    "aa8075409dc29359994bcc3e651331f9",
    "1295ab9230a45eaf8ef61ada41bb479b",
]
FAILURE_POOL_IMAGE_IDS = [
    "0923859fb43467198c8a301a24c284cd",
    "13401615760079295",
    "5055499a75d867a5bd4059db5caf009e",
    "6710ebfaed07bd1d9d63be9a0d2f2665",
    "9354d39f7091f12e92f61955039317b8",
    "a86d33b681fc3d6ad56e0e4e0e735ee2",
    "b62c3f3ba60a0bf425e4656df896e13f",
    "c814a17b460651030fdf2c907f257e50",
    "ccb0692709b04223534582eca2f86c55",
    "e33421e6c755bd986ed8fa91bfeae3b1",
    "eec1408930a9193ce1cdac57126fe8df",
]
FULL_PRIVATE_CHAT_IMAGE_IDS = [
    "0923859fb43467198c8a301a24c284cd",
    "09693a1fcf53b932e855e4b160354268",
    "1295ab9230a45eaf8ef61ada41bb479b",
    "13401615760079295",
    "2eb48fcab5133d434ecf26a6e60bddcc",
    "32abf758a163e13210f585c7d812a271",
    "456251df79ce2fe41297edeb115953ff",
    "5055499a75d867a5bd4059db5caf009e",
    "523f51ae9fb7bb6df5d6b8bfc641572c",
    "6710ebfaed07bd1d9d63be9a0d2f2665",
    "9354d39f7091f12e92f61955039317b8",
    "a86d33b681fc3d6ad56e0e4e0e735ee2",
    "aa8075409dc29359994bcc3e651331f9",
    "b62c3f3ba60a0bf425e4656df896e13f",
    "c814a17b460651030fdf2c907f257e50",
    "ccb0692709b04223534582eca2f86c55",
    "e33421e6c755bd986ed8fa91bfeae3b1",
    "ec002086bfbb35857c2e2ec51b0ba279",
    "eec1408930a9193ce1cdac57126fe8df",
]
EVAL_SUBSETS: dict[str, list[str]] = {
    "small": SMALL_EVAL_IMAGE_IDS,
    "failure_pool": FAILURE_POOL_IMAGE_IDS,
    "full": FULL_PRIVATE_CHAT_IMAGE_IDS,
}
SENDER_ATTRIBUTION_BLOCKING_ISSUES = {
    "sender_flip",
    "speaker_flip",
    "speaker_swap_major",
    "media_sender_misattributed",
    "voice_note_misattributed",
    "mid_late_chat_attribution_drift",
}
BANNED_ISSUES_FOR_PROMOTION = {
    "massive_hallucination",
    "time_separator_as_message",
    *SENDER_ATTRIBUTION_BLOCKING_ISSUES,
}
SMALL_CONTINUE_GATE = {
    "min_speaker_delta": 0.6,
    "min_critical_fail_reduction": 2,
    "max_total_latency_regression_ratio": 1.10,
}
FAILURE_POOL_GATE = {
    "min_speaker_delta": 0.0,
    "max_critical_fail_increase": 0,
}
SMALL_PROMOTION_GATE = {
    "min_speaker_attribution": 3.6,
    "max_critical_fail_count": 1,
    "banned_issues": sorted(BANNED_ISSUES_FOR_PROMOTION),
}
FULL_PROMOTION_GATE = {
    "min_weighted_score": 4.2,
    "max_critical_fail_count": 3,
}
LATENCY_BUDGET_MS = {
    "total": {"p50": 5961.6, "p95": 28802.4},
    "upload": {"p50": 4872.9, "p95": 28067.7},
}
SMALL_BASELINE_METRICS = {
    "weighted_score": 3.777,
    "speaker_attribution": 2.857,
    "critical_fail_count": 4,
    "image_count": 7,
}

SCORING_DIMENSIONS: dict[str, dict[str, Any]] = {
    "speaker_attribution": {
        "weight": 35,
        "description": "说话人左右归属是否稳定、是否把用户/Crush 对调。",
        "scale": "1-5",
    },
    "message_recall": {
        "weight": 25,
        "description": "可见消息是否完整召回，尤其是边界、图片消息、系统消息。",
        "scale": "1-5",
    },
    "temporal_order": {
        "weight": 15,
        "description": "消息顺序和时间分隔理解是否正确，是否出现倒序或跨段错位。",
        "scale": "1-5",
    },
    "hallucination_control": {
        "weight": 12,
        "description": "是否凭空补充不存在的消息、把时间分隔线或 UI 噪声写成消息。",
        "scale": "1-5",
    },
    "text_accuracy": {
        "weight": 8,
        "description": "已提取消息的文本内容、时间戳、系统提示是否基本准确。",
        "scale": "1-5",
    },
    "image_semantics": {
        "weight": 3,
        "description": "图片、表情包、GIF 的功能性描述是否基本成立。",
        "scale": "1-5",
    },
    "format_stability": {
        "weight": 2,
        "description": "输出格式是否稳定、是否便于下游继续消费。",
        "scale": "1-5",
    },
}

CRITICAL_FAIL_RULES: list[dict[str, str]] = [
    {
        "id": "speaker_attr_low",
        "condition": "speaker_attribution <= 2",
        "description": "说话人归属错误达到高风险级别。",
    },
    {
        "id": "message_recall_low",
        "condition": "message_recall <= 2",
        "description": "消息漏召回严重，无法支撑后续分析。",
    },
    {
        "id": "temporal_order_low",
        "condition": "temporal_order <= 2",
        "description": "时间顺序或视觉顺序严重错乱。",
    },
    {
        "id": "severe_hallucination",
        "condition": "issue_tags includes severe hallucination",
        "description": "存在明显捏造内容、把时间分隔线当消息等严重幻觉。",
    },
]

SEVERE_HALLUCINATION_TAGS = {
    "fabricated_content",
    "separator_leakage",
    "separator_leakage_severe",
    "ui_noise_as_message",
    "system_line_fabricated",
    "made_up_sender",
}

LONG_CHAT_MIN_HEIGHT = int(os.getenv("IMAGE_LONG_CHAT_MIN_HEIGHT", "5000"))
LONG_CHAT_MIN_ASPECT_RATIO = float(os.getenv("IMAGE_LONG_CHAT_MIN_ASPECT_RATIO", "2.6"))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def collect_image_meta(image_path: Path) -> dict[str, Any]:
    with Image.open(image_path) as img:
        width, height = img.size
    aspect_ratio = round((height / float(width)) if width else 0.0, 4)
    return {
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "file_size_bytes": image_path.stat().st_size,
        "is_long_chat_candidate": bool(
            width > 0 and height >= LONG_CHAT_MIN_HEIGHT and aspect_ratio >= LONG_CHAT_MIN_ASPECT_RATIO
        ),
    }


def normalize_image_id(value: str | Path) -> str:
    return Path(str(value)).stem


def dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def compute_percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    idx = (len(ordered) - 1) * quantile
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return round(ordered[int(idx)], 1)
    value = ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo)
    return round(value, 1)


def compute_latency_summary(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(row.get(key) or 0.0) for row in rows]
    if not values:
        return {"min": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0, "avg": 0.0}
    return {
        "min": round(min(values), 1),
        "p50": compute_percentile(values, 0.50),
        "p95": compute_percentile(values, 0.95),
        "max": round(max(values), 1),
        "avg": round(sum(values) / len(values), 1),
    }


def collect_prompt_metadata(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    prompt_root = project_root / "agent_impl" / "prompts" / "screenshots"
    prompt_files: dict[str, dict[str, Any]] = {}
    combined = hashlib.sha256()
    for prompt_type in SCREENSHOT_PROMPT_TYPES:
        prompt_path = prompt_root / f"{prompt_type}.md"
        if not prompt_path.exists():
            continue
        data = prompt_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        combined.update(prompt_type.encode("utf-8"))
        combined.update(b":")
        combined.update(digest.encode("utf-8"))
        prompt_files[prompt_type] = {
            "path": str(prompt_path.resolve()),
            "sha256": digest,
            "size_bytes": len(data),
        }
    return {
        "prompt_hash": combined.hexdigest(),
        "prompt_files": prompt_files,
    }


def collect_runtime_snapshot(prompt_version: str | None = None, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    prompt_meta = collect_prompt_metadata(project_root=project_root)
    return {
        "prompt_version": (prompt_version or os.getenv("IMAGE_PROMPT_VERSION") or "unspecified").strip() or "unspecified",
        "prompt_hash": prompt_meta["prompt_hash"],
        "prompt_files": prompt_meta["prompt_files"],
        "detect_model": os.getenv("IMAGE_TYPE_DETECT_MODEL", "GLM-4.6V-FlashX"),
        "detect_base_url": os.getenv("IMAGE_TYPE_DETECT_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        "ocr_model": os.getenv("IMAGE_OCR_MODEL") or os.getenv("IMAGE_TYPE_DETECT_MODEL", "GLM-4.6V-FlashX"),
        "ocr_base_url": os.getenv("IMAGE_OCR_BASE_URL") or os.getenv("IMAGE_TYPE_DETECT_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        "long_chat_ocr_model": os.getenv("IMAGE_LONG_CHAT_OCR_MODEL", "").strip() or None,
        "long_chat_ocr_base_url": os.getenv("IMAGE_LONG_CHAT_OCR_BASE_URL", "").strip() or None,
        "thinking_disabled": os.getenv("IMAGE_DISABLE_REASONING_OUTPUT", "true").lower() == "true",
        "ocr_max_tokens": int(os.getenv("IMAGE_OCR_MAX_TOKENS", "2000")),
        "ocr_max_edge": int(os.getenv("IMAGE_OCR_MAX_EDGE", "3000")),
        "type_detect_max_tokens": int(os.getenv("IMAGE_TYPE_DETECT_MAX_TOKENS", "80")),
        "type_detect_max_edge": int(os.getenv("IMAGE_TYPE_DETECT_MAX_EDGE", "1024")),
        "long_chat_min_height": int(os.getenv("IMAGE_LONG_CHAT_MIN_HEIGHT", "5000")),
        "long_chat_min_aspect_ratio": float(os.getenv("IMAGE_LONG_CHAT_MIN_ASPECT_RATIO", "2.6")),
    }


def load_image_ids_from_selection_file(path: Path) -> list[str]:
    payload = load_json(path)
    image_ids: list[str] = []
    if isinstance(payload, list):
        image_ids = [normalize_image_id(item) for item in payload]
    elif isinstance(payload, dict):
        if isinstance(payload.get("image_ids"), list):
            image_ids.extend(normalize_image_id(item) for item in payload["image_ids"])
        if isinstance(payload.get("selected_image_ids"), list):
            image_ids.extend(normalize_image_id(item) for item in payload["selected_image_ids"])
        if isinstance(payload.get("worker_shards"), list):
            for shard in payload["worker_shards"]:
                if isinstance(shard, dict) and isinstance(shard.get("image_ids"), list):
                    image_ids.extend(normalize_image_id(item) for item in shard["image_ids"])
        if isinstance(payload.get("results"), list):
            for row in payload["results"]:
                if isinstance(row, dict):
                    if row.get("image_id"):
                        image_ids.append(normalize_image_id(row["image_id"]))
                    elif row.get("image_path"):
                        image_ids.append(normalize_image_id(row["image_path"]))
        if isinstance(payload.get("per_image_results"), list):
            for row in payload["per_image_results"]:
                if isinstance(row, dict) and row.get("image_id"):
                    image_ids.append(normalize_image_id(row["image_id"]))
    return dedupe_keep_order(image_ids)


def build_subset_metrics(report: dict[str, Any], image_ids: list[str]) -> dict[str, Any]:
    normalized_ids = set(image_ids)
    rows = [
        item
        for item in report.get("per_image_results", [])
        if str(item.get("image_id") or "").strip() in normalized_ids
    ]
    if not rows:
        raise ValueError("subset metrics requested for empty image set")

    weighted_score = round(
        sum(float(item["judge"]["weighted_score"]) for item in rows) / len(rows),
        3,
    )
    dimension_averages = {
        dim: round(sum(float(item["judge"]["scores"][dim]) for item in rows) / len(rows), 3)
        for dim in SCORING_DIMENSIONS
    }
    critical_fail_count = sum(1 for item in rows if item["judge"]["critical_fail"])
    issue_tag_counts: dict[str, int] = {}
    for item in rows:
        for tag in item["judge"]["issue_tags"]:
            key = str(tag).strip()
            if not key:
                continue
            issue_tag_counts[key] = issue_tag_counts.get(key, 0) + 1
    return {
        "image_count": len(rows),
        "weighted_score": weighted_score,
        "dimension_averages": dimension_averages,
        "critical_fail_count": critical_fail_count,
        "issue_tag_counts": dict(sorted(issue_tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
    }


def summarize_text(text: str, limit: int = 240) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)] + "…"


def normalize_score(value: Any) -> int:
    try:
        score = int(value)
    except Exception as exc:
        raise ValueError(f"invalid score: {value!r}") from exc
    if score < 1 or score > 5:
        raise ValueError(f"score out of range 1-5: {score}")
    return score


def compute_weighted_score(scores: dict[str, Any]) -> float:
    total_weight = sum(int(meta["weight"]) for meta in SCORING_DIMENSIONS.values())
    weighted_sum = 0.0
    for dim, meta in SCORING_DIMENSIONS.items():
        weighted_sum += normalize_score(scores[dim]) * int(meta["weight"])
    return round(weighted_sum / max(total_weight, 1), 3)


def compute_critical_fail(scores: dict[str, Any], issue_tags: list[str]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    normalized_scores = {dim: normalize_score(scores[dim]) for dim in SCORING_DIMENSIONS}
    normalized_tags = {str(tag).strip() for tag in issue_tags if str(tag).strip()}

    if normalized_scores["speaker_attribution"] <= 2:
        reasons.append("speaker_attribution<=2")
    if normalized_scores["message_recall"] <= 2:
        reasons.append("message_recall<=2")
    if normalized_scores["temporal_order"] <= 2:
        reasons.append("temporal_order<=2")
    if normalized_tags & SEVERE_HALLUCINATION_TAGS:
        reasons.append("severe_hallucination")

    return (len(reasons) > 0, reasons)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError(f"jsonl row must be an object: {path}")
        rows.append(obj)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
