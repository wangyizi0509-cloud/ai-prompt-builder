#!/usr/bin/env python3
"""Compare two chat screenshot evaluation runs and emit JSON / Markdown reports."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.chat_screenshot_eval_common import (
        BANNED_ISSUES_FOR_PROMOTION,
        CRITICAL_FAIL_RULES,
        EVAL_SUBSETS,
        FAILURE_POOL_GATE,
        FULL_PROMOTION_GATE,
        LATENCY_BUDGET_MS,
        SCORING_DIMENSIONS,
        SMALL_CONTINUE_GATE,
        SMALL_PROMOTION_GATE,
        STRICT_BASELINE_RUN_DIR,
        load_json,
        now_iso,
        summarize_text,
        write_json,
    )
except ImportError:
    from chat_screenshot_eval_common import (  # type: ignore[no-redef]
        BANNED_ISSUES_FOR_PROMOTION,
        CRITICAL_FAIL_RULES,
        EVAL_SUBSETS,
        FAILURE_POOL_GATE,
        FULL_PROMOTION_GATE,
        LATENCY_BUDGET_MS,
        SCORING_DIMENSIONS,
        SMALL_CONTINUE_GATE,
        SMALL_PROMOTION_GATE,
        STRICT_BASELINE_RUN_DIR,
        load_json,
        now_iso,
        summarize_text,
        write_json,
    )


SMALL_GATE_IMAGE_IDS = list(EVAL_SUBSETS["small"])
FAILURE_POOL_GATE_IMAGE_IDS = list(EVAL_SUBSETS["failure_pool"])
FULL_GATE_IMAGE_IDS = list(EVAL_SUBSETS["full"])

GATE_CONFIG = {
    "small": {
        "expected_count": len(SMALL_GATE_IMAGE_IDS),
        "image_ids": SMALL_GATE_IMAGE_IDS,
        "speaker_delta_min": SMALL_CONTINUE_GATE["min_speaker_delta"],
        "critical_fail_delta_max": -SMALL_CONTINUE_GATE["min_critical_fail_reduction"],
        "latency_regression_max": SMALL_CONTINUE_GATE["max_total_latency_regression_ratio"] - 1.0,
    },
    "failure_pool": {
        "expected_count": len(FAILURE_POOL_GATE_IMAGE_IDS),
        "image_ids": FAILURE_POOL_GATE_IMAGE_IDS,
        "critical_fail_delta_max": FAILURE_POOL_GATE["max_critical_fail_increase"],
        "speaker_delta_min": FAILURE_POOL_GATE["min_speaker_delta"],
        "latency_regression_max": SMALL_CONTINUE_GATE["max_total_latency_regression_ratio"] - 1.0,
    },
    "full": {
        "expected_count": len(FULL_GATE_IMAGE_IDS),
        "image_ids": FULL_GATE_IMAGE_IDS,
        "critical_fail_count_max": FULL_PROMOTION_GATE["max_critical_fail_count"],
        "weighted_score_min": FULL_PROMOTION_GATE["min_weighted_score"],
        "latency_budget_ms": LATENCY_BUDGET_MS,
    },
}


def _resolve_run_dir(path: Path) -> Path:
    if path.is_file():
        return path.parent
    if (path / "final_report.json").exists() and (path / "api_results.json").exists():
        return path
    if path.name in {"final_report.json", "api_results.json"}:
        return path.parent
    return path


def _load_run_bundle(run_dir: Path) -> dict[str, Any]:
    final_report = load_json(run_dir / "final_report.json")
    api_results = load_json(run_dir / "api_results.json")
    if not isinstance(final_report, dict):
        raise ValueError(f"final_report.json must be an object: {run_dir}")
    if not isinstance(api_results, dict):
        raise ValueError(f"api_results.json must be an object: {run_dir}")

    per_image = final_report.get("per_image_results")
    api_rows = api_results.get("results")
    if not isinstance(per_image, list):
        raise ValueError(f"final_report.json missing per_image_results: {run_dir}")
    if not isinstance(api_rows, list):
        raise ValueError(f"api_results.json missing results: {run_dir}")

    per_image_map: dict[str, dict[str, Any]] = {}
    for item in per_image:
        if not isinstance(item, dict):
            continue
        image_id = str(item.get("image_id") or "").strip()
        if image_id:
            per_image_map[image_id] = item

    api_map: dict[str, dict[str, Any]] = {}
    for item in api_rows:
        if not isinstance(item, dict):
            continue
        image_id = str(item.get("image_id") or "").strip()
        if image_id:
            api_map[image_id] = item

    return {
        "run_dir": run_dir,
        "final_report": final_report,
        "api_results": api_results,
        "per_image_map": per_image_map,
        "api_map": api_map,
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if q < 0 or q > 1:
        raise ValueError(f"percentile q must be between 0 and 1: {q}")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    idx = (len(ordered) - 1) * q
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return round(ordered[int(idx)], 3)
    frac = idx - lo
    value = ordered[lo] + (ordered[hi] - ordered[lo]) * frac
    return round(value, 3)


def _latency_summary(api_map: dict[str, dict[str, Any]], image_ids: list[str]) -> dict[str, Any]:
    rows = [api_map[image_id] for image_id in image_ids if image_id in api_map]
    if not rows:
        return {
            "count": 0,
            "missing_image_ids": image_ids,
            "latency_ms": {"avg": None, "p50": None, "p95": None, "min": None, "max": None},
            "detect_latency_ms": {"avg": None, "p50": None, "p95": None, "min": None, "max": None},
            "upload_latency_ms": {"avg": None, "p50": None, "p95": None, "min": None, "max": None},
        }

    def collect(key: str) -> dict[str, Any]:
        vals = [float(row.get(key) or 0.0) for row in rows]
        ordered = sorted(vals)
        return {
            "avg": _mean(vals),
            "p50": _percentile(vals, 0.5),
            "p95": _percentile(vals, 0.95),
            "min": round(min(ordered), 3),
            "max": round(max(ordered), 3),
        }

    return {
        "count": len(rows),
        "missing_image_ids": [image_id for image_id in image_ids if image_id not in api_map],
        "latency_ms": collect("latency_ms"),
        "detect_latency_ms": collect("detect_latency_ms"),
        "upload_latency_ms": collect("upload_latency_ms"),
    }


def _subset_summary(run_bundle: dict[str, Any], image_ids: list[str]) -> dict[str, Any]:
    per_image_map = run_bundle["per_image_map"]
    api_map = run_bundle["api_map"]

    selected_rows: list[dict[str, Any]] = []
    missing_image_ids: list[str] = []
    for image_id in image_ids:
        row = per_image_map.get(image_id)
        if row is None:
            missing_image_ids.append(image_id)
            continue
        selected_rows.append(row)

    scores = [float(item["judge"]["weighted_score"]) for item in selected_rows]
    speaker_scores = [
        float(item["judge"]["scores"]["speaker_attribution"])
        for item in selected_rows
        if isinstance(item.get("judge"), dict)
    ]
    critical_fail_count = sum(1 for item in selected_rows if item["judge"]["critical_fail"])
    issue_counts = Counter()
    for item in selected_rows:
        issue_counts.update(str(tag) for tag in item["judge"].get("issue_tags", []) if str(tag).strip())
    long_chat_critical_fail_ids = [
        item["image_id"]
        for item in selected_rows
        if item["image_meta"].get("is_long_chat_candidate") and item["judge"]["critical_fail"]
    ]

    latency = _latency_summary(api_map, image_ids)

    return {
        "image_ids": image_ids,
        "selected_count": len(selected_rows),
        "missing_image_ids": missing_image_ids,
        "weighted_score": _mean(scores),
        "speaker_attribution": _mean(speaker_scores),
        "critical_fail_count": critical_fail_count,
        "critical_fail_rate": round(critical_fail_count / max(len(selected_rows), 1), 3),
        "issue_tag_counts": dict(issue_counts.most_common()),
        "long_chat_critical_fail_ids": long_chat_critical_fail_ids,
        "latency": latency,
    }


def _select_image_ids(gate: str, baseline_report: dict[str, Any]) -> list[str]:
    if gate == "small":
        return list(SMALL_GATE_IMAGE_IDS)
    if gate == "failure_pool":
        return list(FAILURE_POOL_GATE_IMAGE_IDS)
    if gate == "full":
        return list(FULL_GATE_IMAGE_IDS)
    raise ValueError(f"unknown gate: {gate}")


def _absolute_latency_checks(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, expected: str, actual: str) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "expected": expected,
                "actual": actual,
                "details": None,
            }
        )

    for stage_key in ("total", "upload"):
        source_key = "latency_ms" if stage_key == "total" else "upload_latency_ms"
        budgets = LATENCY_BUDGET_MS[stage_key]
        p50 = _select_latency_value(candidate, source_key, "p50")
        p95 = _select_latency_value(candidate, source_key, "p95")
        add_check(
            f"{stage_key}_p50_budget",
            p50 is not None and p50 <= budgets["p50"],
            f"<= {budgets['p50']}",
            _format_value(p50, 1),
        )
        add_check(
            f"{stage_key}_p95_budget",
            p95 is not None and p95 <= budgets["p95"],
            f"<= {budgets['p95']}",
            _format_value(p95, 1),
        )
    return checks


def _delta_value(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return round(candidate - baseline, 3)


def _regression_ratio(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    if baseline == 0:
        return None if candidate == 0 else float("inf")
    return round((candidate - baseline) / baseline, 4)


def _format_signed(value: float | None, precision: int = 3) -> str:
    if value is None:
        return "-"
    return f"{value:+.{precision}f}"


def _format_value(value: Any, precision: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{precision}f}"
    return str(value)


def _build_issue_tag_deltas(
    baseline_counts: dict[str, int],
    candidate_counts: dict[str, int],
) -> list[dict[str, Any]]:
    tags = set(baseline_counts) | set(candidate_counts)
    rows = []
    for tag in tags:
        base = int(baseline_counts.get(tag, 0))
        cand = int(candidate_counts.get(tag, 0))
        rows.append(
            {
                "tag": tag,
                "baseline": base,
                "candidate": cand,
                "delta": cand - base,
            }
        )
    rows.sort(key=lambda item: (-abs(int(item["delta"])), item["tag"]))
    return rows


def _select_latency_value(summary: dict[str, Any], key: str, stat: str) -> float | None:
    latency = summary.get("latency") or {}
    return ((latency.get(key) or {}).get(stat))


def _gate_checks(
    gate: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    config = GATE_CONFIG[gate]
    checks: list[dict[str, Any]] = []

    baseline_weighted = baseline.get("weighted_score")
    candidate_weighted = candidate.get("weighted_score")
    baseline_speaker = baseline.get("speaker_attribution")
    candidate_speaker = candidate.get("speaker_attribution")
    baseline_critical = int(baseline.get("critical_fail_count") or 0)
    candidate_critical = int(candidate.get("critical_fail_count") or 0)

    total_p50_base = _select_latency_value(baseline, "latency_ms", "p50")
    total_p50_cand = _select_latency_value(candidate, "latency_ms", "p50")
    total_p95_base = _select_latency_value(baseline, "latency_ms", "p95")
    total_p95_cand = _select_latency_value(candidate, "latency_ms", "p95")

    reg_p50 = _regression_ratio(total_p50_cand, total_p50_base)
    reg_p95 = _regression_ratio(total_p95_cand, total_p95_base)
    max_regression = config.get("latency_regression_max")

    forbidden_hits = sorted(
        tag for tag in candidate.get("issue_tag_counts", {}) if tag in BANNED_ISSUES_FOR_PROMOTION
    )

    def add_check(name: str, passed: bool, expected: str, actual: str, details: str | None = None) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "expected": expected,
                "actual": actual,
                "details": details,
            }
        )

    add_check(
        "selected_count",
        candidate.get("selected_count") == config["expected_count"],
        str(config["expected_count"]),
        str(candidate.get("selected_count")),
    )

    add_check(
        "candidate_coverage",
        not candidate.get("missing_image_ids"),
        "no missing image ids",
        ", ".join(candidate.get("missing_image_ids") or []) or "ok",
    )

    if gate == "small":
        add_check(
            "speaker_attribution_delta",
            (candidate_speaker is not None and baseline_speaker is not None and candidate_speaker - baseline_speaker >= config["speaker_delta_min"]),
            f">= +{config['speaker_delta_min']}",
            _format_signed(_delta_value(candidate_speaker, baseline_speaker)),
        )
        add_check(
            "critical_fail_delta",
            (candidate_critical - baseline_critical) <= config["critical_fail_delta_max"],
            f"<= {config['critical_fail_delta_max']}",
            _format_signed(_delta_value(float(candidate_critical), float(baseline_critical)), 0),
        )
        add_check(
            "latency_p50_regression",
            reg_p50 is not None and max_regression is not None and reg_p50 <= max_regression,
            f"<= +{int((max_regression or 0.0) * 100)}%",
            f"{reg_p50 * 100:+.1f}%" if reg_p50 is not None else "-",
        )
        add_check(
            "latency_p95_regression",
            reg_p95 is not None and max_regression is not None and reg_p95 <= max_regression,
            f"<= +{int((max_regression or 0.0) * 100)}%",
            f"{reg_p95 * 100:+.1f}%" if reg_p95 is not None else "-",
        )
        add_check(
            "small_stage_promotion_issues_cleared",
            True,
            "reported separately in promotion_readiness",
            "see promotion_readiness",
        )
    elif gate == "failure_pool":
        add_check(
            "speaker_attribution_delta",
            (candidate_speaker is not None and baseline_speaker is not None and candidate_speaker - baseline_speaker >= config["speaker_delta_min"]),
            f">= +{config['speaker_delta_min']}",
            _format_signed(_delta_value(candidate_speaker, baseline_speaker)),
        )
        add_check(
            "critical_fail_delta",
            (candidate_critical - baseline_critical) <= config["critical_fail_delta_max"],
            f"<= {config['critical_fail_delta_max']}",
            _format_signed(_delta_value(float(candidate_critical), float(baseline_critical)), 0),
        )
        add_check(
            "latency_p50_regression",
            reg_p50 is not None and max_regression is not None and reg_p50 <= max_regression,
            f"<= +{int((max_regression or 0.0) * 100)}%",
            f"{reg_p50 * 100:+.1f}%" if reg_p50 is not None else "-",
        )
        add_check(
            "latency_p95_regression",
            reg_p95 is not None and max_regression is not None and reg_p95 <= max_regression,
            f"<= +{int((max_regression or 0.0) * 100)}%",
            f"{reg_p95 * 100:+.1f}%" if reg_p95 is not None else "-",
        )
        add_check(
            "forbidden_issue_tags",
            not forbidden_hits,
            f"exclude {', '.join(sorted(BANNED_ISSUES_FOR_PROMOTION))}",
            ", ".join(forbidden_hits) or "ok",
        )
    elif gate == "full":
        add_check(
            "weighted_score",
            candidate_weighted is not None and candidate_weighted >= config["weighted_score_min"],
            f">= {config['weighted_score_min']}",
            f"{candidate_weighted:.3f}" if candidate_weighted is not None else "-",
        )
        add_check(
            "speaker_attribution",
            candidate_speaker is not None and candidate_speaker >= SMALL_PROMOTION_GATE["min_speaker_attribution"],
            f">= {SMALL_PROMOTION_GATE['min_speaker_attribution']}",
            f"{candidate_speaker:.3f}" if candidate_speaker is not None else "-",
        )
        add_check(
            "critical_fail_count",
            candidate_critical <= config["critical_fail_count_max"],
            f"<= {config['critical_fail_count_max']}",
            str(candidate_critical),
        )
        add_check(
            "long_chat_critical_fail_count",
            not candidate.get("long_chat_critical_fail_ids"),
            "no long-chat critical fail ids",
            ", ".join(candidate.get("long_chat_critical_fail_ids") or []) or "ok",
        )
        checks.extend(_absolute_latency_checks(candidate))
    else:
        raise ValueError(f"unknown gate: {gate}")

    passed = all(check["passed"] for check in checks)
    reasons = [check["name"] for check in checks if not check["passed"]]
    result = {
        "passed": passed,
        "reasons": reasons,
        "checks": checks,
    }
    if gate == "small":
        promotion_checks = [
            {
                "name": "speaker_attribution",
                "passed": candidate_speaker is not None and candidate_speaker >= SMALL_PROMOTION_GATE["min_speaker_attribution"],
                "expected": f">= {SMALL_PROMOTION_GATE['min_speaker_attribution']}",
                "actual": f"{candidate_speaker:.3f}" if candidate_speaker is not None else "-",
                "details": None,
            },
            {
                "name": "critical_fail_count",
                "passed": candidate_critical <= SMALL_PROMOTION_GATE["max_critical_fail_count"],
                "expected": f"<= {SMALL_PROMOTION_GATE['max_critical_fail_count']}",
                "actual": str(candidate_critical),
                "details": None,
            },
            {
                "name": "forbidden_issue_tags",
                "passed": not forbidden_hits,
                "expected": f"exclude {', '.join(sorted(BANNED_ISSUES_FOR_PROMOTION))}",
                "actual": ", ".join(forbidden_hits) or "ok",
                "details": None,
            },
        ] + _absolute_latency_checks(candidate)
        result["promotion_readiness"] = {
            "passed": all(check["passed"] for check in promotion_checks),
            "reasons": [check["name"] for check in promotion_checks if not check["passed"]],
            "checks": promotion_checks,
        }
    return result


def compare_runs(baseline_run_dir: Path, candidate_run_dir: Path, gate: str) -> dict[str, Any]:
    if gate not in GATE_CONFIG:
        raise ValueError(f"unsupported gate: {gate}")

    baseline_bundle = _load_run_bundle(_resolve_run_dir(baseline_run_dir))
    candidate_bundle = _load_run_bundle(_resolve_run_dir(candidate_run_dir))

    baseline_report = baseline_bundle["final_report"]
    candidate_report = candidate_bundle["final_report"]

    selected_image_ids = _select_image_ids(gate, baseline_report)
    baseline_summary = _subset_summary(baseline_bundle, selected_image_ids)
    candidate_summary = _subset_summary(candidate_bundle, selected_image_ids)

    baseline_issue_counts = baseline_summary["issue_tag_counts"]
    candidate_issue_counts = candidate_summary["issue_tag_counts"]
    issue_tag_deltas = _build_issue_tag_deltas(baseline_issue_counts, candidate_issue_counts)

    weighted_delta = _delta_value(candidate_summary["weighted_score"], baseline_summary["weighted_score"])
    speaker_delta = _delta_value(candidate_summary["speaker_attribution"], baseline_summary["speaker_attribution"])
    critical_fail_delta = _delta_value(
        float(candidate_summary["critical_fail_count"]),
        float(baseline_summary["critical_fail_count"]),
    )

    comparison = {
        "gate": gate,
        "selected_image_ids": selected_image_ids,
        "selected_count": len(selected_image_ids),
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "delta": {
            "weighted_score": weighted_delta,
            "speaker_attribution": speaker_delta,
            "critical_fail_count": critical_fail_delta,
            "critical_fail_rate": _delta_value(
                candidate_summary["critical_fail_rate"],
                baseline_summary["critical_fail_rate"],
            ),
            "latency": {
                "latency_ms": {
                    "avg": _delta_value(
                        candidate_summary["latency"]["latency_ms"]["avg"],
                        baseline_summary["latency"]["latency_ms"]["avg"],
                    ),
                    "p50": _delta_value(
                        candidate_summary["latency"]["latency_ms"]["p50"],
                        baseline_summary["latency"]["latency_ms"]["p50"],
                    ),
                    "p95": _delta_value(
                        candidate_summary["latency"]["latency_ms"]["p95"],
                        baseline_summary["latency"]["latency_ms"]["p95"],
                    ),
                },
                "detect_latency_ms": {
                    "avg": _delta_value(
                        candidate_summary["latency"]["detect_latency_ms"]["avg"],
                        baseline_summary["latency"]["detect_latency_ms"]["avg"],
                    ),
                    "p50": _delta_value(
                        candidate_summary["latency"]["detect_latency_ms"]["p50"],
                        baseline_summary["latency"]["detect_latency_ms"]["p50"],
                    ),
                    "p95": _delta_value(
                        candidate_summary["latency"]["detect_latency_ms"]["p95"],
                        baseline_summary["latency"]["detect_latency_ms"]["p95"],
                    ),
                },
                "upload_latency_ms": {
                    "avg": _delta_value(
                        candidate_summary["latency"]["upload_latency_ms"]["avg"],
                        baseline_summary["latency"]["upload_latency_ms"]["avg"],
                    ),
                    "p50": _delta_value(
                        candidate_summary["latency"]["upload_latency_ms"]["p50"],
                        baseline_summary["latency"]["upload_latency_ms"]["p50"],
                    ),
                    "p95": _delta_value(
                        candidate_summary["latency"]["upload_latency_ms"]["p95"],
                        baseline_summary["latency"]["upload_latency_ms"]["p95"],
                    ),
                },
            },
        },
        "issue_tag_deltas": issue_tag_deltas,
    }

    gate_result = _gate_checks(gate, baseline_summary, candidate_summary)

    report = {
        "generated_at": now_iso(),
        "gate": {
            "name": gate,
            "config": GATE_CONFIG[gate],
        },
        "baseline": {
            "run_dir": str(_resolve_run_dir(baseline_run_dir).resolve()),
            "summary": baseline_report.get("summary", {}),
            "selected_summary": baseline_summary,
        },
        "candidate": {
            "run_dir": str(_resolve_run_dir(candidate_run_dir).resolve()),
            "summary": candidate_report.get("summary", {}),
            "selected_summary": candidate_summary,
        },
        "comparison": comparison,
        "gate_result": gate_result,
        "critical_fail_rules": CRITICAL_FAIL_RULES,
        "scoring_dimensions": SCORING_DIMENSIONS,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    gate = report["gate"]["name"]
    baseline = report["baseline"]["selected_summary"]
    candidate = report["candidate"]["selected_summary"]
    delta = report["comparison"]["delta"]
    gate_result = report["gate_result"]

    lines = [
        "# 聊天截图候选对比报告",
        "",
        "## 概览",
        "",
        f"- Gate: `{gate}`",
        f"- Generated At: `{report['generated_at']}`",
        f"- Passed: `{gate_result['passed']}`",
        f"- Selected Images: `{report['comparison']['selected_count']}`",
        f"- Baseline Run: `{report['baseline']['run_dir']}`",
        f"- Candidate Run: `{report['candidate']['run_dir']}`",
        "",
        "## 指标对比",
        "",
        "| Metric | Baseline | Candidate | Delta |",
        "| --- | ---: | ---: | ---: |",
        f"| weighted_score | {_format_value(baseline['weighted_score'])} | {_format_value(candidate['weighted_score'])} | {_format_signed(delta['weighted_score'])} |",
        f"| speaker_attribution | {_format_value(baseline['speaker_attribution'])} | {_format_value(candidate['speaker_attribution'])} | {_format_signed(delta['speaker_attribution'])} |",
        f"| critical_fail_count | {baseline['critical_fail_count']} | {candidate['critical_fail_count']} | {_format_signed(delta['critical_fail_count'], 0)} |",
        f"| critical_fail_rate | {_format_value(baseline['critical_fail_rate'])} | {_format_value(candidate['critical_fail_rate'])} | {_format_signed(delta['critical_fail_rate'])} |",
        "",
        "### Latency",
        "",
        "| Metric | Baseline p50 | Candidate p50 | Delta | Baseline p95 | Candidate p95 | Delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for key in ["latency_ms", "detect_latency_ms", "upload_latency_ms"]:
        base = baseline["latency"][key]
        cand = candidate["latency"][key]
        delta_row = delta["latency"][key]
        lines.append(
            f"| {key} | {_format_value(base['p50'])} | "
            f"{_format_value(cand['p50'])} | {_format_signed(delta_row['p50'])} | "
            f"{_format_value(base['p95'])} | {_format_value(cand['p95'])} | "
            f"{_format_signed(delta_row['p95'])} |"
        )

    lines += [
        "",
        "## Issue Tags",
        "",
        "| Tag | Baseline | Candidate | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in report["comparison"]["issue_tag_deltas"][:12]:
        lines.append(
            f"| {row['tag']} | {row['baseline']} | {row['candidate']} | {_format_signed(float(row['delta']), 0)} |"
        )

    lines += [
        "",
        "## Gate Checks",
        "",
        "| Check | Passed | Expected | Actual |",
        "| --- | --- | --- | --- |",
    ]
    for check in gate_result["checks"]:
        lines.append(
            f"| {check['name']} | {check['passed']} | {summarize_text(str(check['expected']), 80)} | "
            f"{summarize_text(str(check['actual']), 80)} |"
        )

    if gate_result["reasons"]:
        lines += [
            "",
            "## Failed Checks",
            "",
            ", ".join(f"`{reason}`" for reason in gate_result["reasons"]),
            "",
        ]

    promotion = gate_result.get("promotion_readiness")
    if promotion:
        lines += [
            "## Small Promotion Readiness",
            "",
            f"- Passed: `{promotion['passed']}`",
            "",
            "| Check | Passed | Expected | Actual |",
            "| --- | --- | --- | --- |",
        ]
        for check in promotion["checks"]:
            lines.append(
                f"| {check['name']} | {check['passed']} | {summarize_text(str(check['expected']), 80)} | "
                f"{summarize_text(str(check['actual']), 80)} |"
            )
        if promotion["reasons"]:
            lines += [
                "",
                "Failed readiness checks:",
                ", ".join(f"`{reason}`" for reason in promotion["reasons"]),
                "",
            ]

    return "\n".join(lines)


def write_outputs(report: dict[str, Any], output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_json, report)
    output_md.write_text(render_markdown(report), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run-dir", default=str(STRICT_BASELINE_RUN_DIR))
    parser.add_argument("--candidate-run-dir", required=True)
    parser.add_argument("--gate", choices=sorted(GATE_CONFIG.keys()), required=True)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    baseline_run_dir = _resolve_run_dir(Path(args.baseline_run_dir))
    candidate_run_dir = _resolve_run_dir(Path(args.candidate_run_dir))
    report = compare_runs(baseline_run_dir, candidate_run_dir, args.gate)

    json_path = Path(args.output_json) if args.output_json else candidate_run_dir / f"chat_screenshot_compare_{args.gate}.json"
    md_path = Path(args.output_md) if args.output_md else candidate_run_dir / f"chat_screenshot_compare_{args.gate}.md"
    write_outputs(report, json_path, md_path)

    print(
        json.dumps(
            {
                "ok": True,
                "gate": args.gate,
                "passed": report["gate_result"]["passed"],
                "json": str(json_path.resolve()),
                "markdown": str(md_path.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
