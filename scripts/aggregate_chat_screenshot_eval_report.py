#!/usr/bin/env python3
"""Aggregate judge outputs into a final chat screenshot evaluation report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.chat_screenshot_eval_common import (
        CRITICAL_FAIL_RULES,
        RUBRIC_VERSION,
        SCORING_DIMENSIONS,
        compute_critical_fail,
        compute_weighted_score,
        load_json,
        load_jsonl,
        now_iso,
        summarize_text,
        write_json,
    )
except ImportError:
    from chat_screenshot_eval_common import (
        CRITICAL_FAIL_RULES,
        RUBRIC_VERSION,
        SCORING_DIMENSIONS,
        compute_critical_fail,
        compute_weighted_score,
        load_json,
        load_jsonl,
        now_iso,
        summarize_text,
        write_json,
    )


def validate_judge_result(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("judge result row must be a JSON object")
    image_id = str(row.get("image_id") or "").strip()
    if not image_id:
        raise ValueError("judge result missing image_id")

    scores = row.get("scores")
    if not isinstance(scores, dict):
        raise ValueError(f"judge result missing scores: {image_id}")
    for dim in SCORING_DIMENSIONS:
        if dim not in scores:
            raise ValueError(f"judge result missing score dim={dim}: {image_id}")

    issue_tags = row.get("issue_tags")
    if not isinstance(issue_tags, list):
        raise ValueError(f"judge result issue_tags must be list: {image_id}")

    weighted_score = row.get("weighted_score")
    if weighted_score is None:
        weighted_score = compute_weighted_score(scores)
    else:
        weighted_score = round(float(weighted_score), 3)

    critical_fail = row.get("critical_fail")
    critical_fail_reasons = row.get("critical_fail_reasons")
    expected_fail, expected_reasons = compute_critical_fail(scores, issue_tags)
    if critical_fail is None:
        critical_fail = expected_fail
    if not isinstance(critical_fail, bool):
        raise ValueError(f"judge result critical_fail must be bool: {image_id}")
    if critical_fail_reasons is None:
        critical_fail_reasons = expected_reasons
    if not isinstance(critical_fail_reasons, list):
        raise ValueError(f"judge result critical_fail_reasons must be list: {image_id}")

    evidence = row.get("evidence")
    if evidence is None:
        evidence_list: list[str] = []
    elif isinstance(evidence, list):
        evidence_list = [str(item) for item in evidence]
    elif isinstance(evidence, dict):
        evidence_list = [f"{key}: {value}" for key, value in evidence.items()]
    else:
        evidence_list = [str(evidence)]

    confidence = row.get("confidence")
    if confidence is None:
        confidence = 0.5
    confidence = round(float(confidence), 3)

    judge_summary = str(row.get("judge_summary") or "").strip()
    if not judge_summary:
        judge_summary = "未提供评审摘要"

    return {
        "image_id": image_id,
        "scores": scores,
        "weighted_score": weighted_score,
        "critical_fail": critical_fail,
        "critical_fail_reasons": [str(item) for item in critical_fail_reasons],
        "issue_tags": [str(item) for item in issue_tags],
        "judge_summary": judge_summary,
        "evidence": evidence_list,
        "confidence": confidence,
    }


def synthesize_failure_judgement(api_row: dict[str, Any]) -> dict[str, Any]:
    scores = {dim: 1 for dim in SCORING_DIMENSIONS}
    return {
        "image_id": api_row["image_id"],
        "scores": scores,
        "weighted_score": compute_weighted_score(scores),
        "critical_fail": True,
        "critical_fail_reasons": ["api_failure"],
        "issue_tags": ["api_failure"],
        "judge_summary": "真实 API 运行失败，自动判定为关键失败样本。",
        "evidence": [str(api_row.get("error") or "unknown_api_error")],
        "confidence": 1.0,
    }


def load_judge_rows(run_dir: Path, judge_inputs: list[Path] | None = None) -> list[dict[str, Any]]:
    if judge_inputs:
        paths = judge_inputs
    else:
        direct_path = run_dir / "judge_results.jsonl"
        judge_dir = run_dir / "judge_results"
        paths = []
        if direct_path.exists():
            paths.append(direct_path)
        if judge_dir.exists():
            paths.extend(sorted(judge_dir.glob("*.jsonl")))

    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(load_jsonl(path))
    return rows


def build_conclusion(critical_fail_count: int, overall_score: float) -> str:
    if critical_fail_count == 0 and overall_score >= 4.0:
        return "推荐当前链路"
    if critical_fail_count >= 4 or overall_score < 3.2:
        return "不建议作为默认链路"
    return "有明显风险"


def aggregate_run(run_dir: Path, judge_inputs: list[Path] | None = None) -> dict[str, Any]:
    api_results = load_json(run_dir / "api_results.json")
    manifest = load_json(run_dir / "manifest.json")
    api_rows = api_results.get("results")
    if not isinstance(api_rows, list):
        raise ValueError("api_results.json missing results")

    raw_judges = load_judge_rows(run_dir, judge_inputs=judge_inputs)
    validated = [validate_judge_result(row) for row in raw_judges]
    judge_map = {row["image_id"]: row for row in validated}

    per_image: list[dict[str, Any]] = []
    for api_row in api_rows:
        image_id = str(api_row["image_id"])
        judge_row = judge_map.get(image_id)
        if judge_row is None:
            if api_row.get("success"):
                raise ValueError(f"missing judge result for successful image: {image_id}")
            judge_row = synthesize_failure_judgement(api_row)

        per_image.append(
            {
                "image_id": image_id,
                "image_path": api_row["image_path"],
                "image_meta": api_row["image_meta"],
                "api_result": {
                    "success": api_row["success"],
                    "detected_screenshot_type": api_row["detected_screenshot_type"],
                    "final_screenshot_type": api_row["final_screenshot_type"],
                    "ocr_text_len": api_row["ocr_text_len"],
                    "ocr_text_preview": summarize_text(api_row.get("ocr_text") or "", 300),
                    "latency_ms": api_row["latency_ms"],
                    "error": api_row["error"],
                },
                "judge": judge_row,
                "appendix_summary": (
                    judge_row["judge_summary"]
                    if judge_row["judge_summary"]
                    else "无"
                ),
            }
        )

    overall_score = round(
        sum(float(item["judge"]["weighted_score"]) for item in per_image) / max(len(per_image), 1),
        3,
    )
    critical_fail_count = sum(1 for item in per_image if item["judge"]["critical_fail"])
    conclusion = build_conclusion(critical_fail_count, overall_score)
    issue_counter = Counter(
        tag for item in per_image for tag in item["judge"]["issue_tags"] if tag
    )

    long_chat_items = [item for item in per_image if item["image_meta"].get("is_long_chat_candidate")]
    long_chat_summary = {
        "count": len(long_chat_items),
        "average_weighted_score": round(
            sum(float(item["judge"]["weighted_score"]) for item in long_chat_items) / max(len(long_chat_items), 1),
            3,
        )
        if long_chat_items
        else None,
        "critical_fail_count": sum(1 for item in long_chat_items if item["judge"]["critical_fail"]),
        "image_ids": [item["image_id"] for item in long_chat_items],
    }

    top_issue_examples = sorted(
        per_image,
        key=lambda item: (
            0 if item["judge"]["critical_fail"] else 1,
            float(item["judge"]["weighted_score"]),
            item["image_id"],
        ),
    )[:5]

    report = {
        "run_id": api_results["run_id"],
        "generated_at": now_iso(),
        "rubric_version": RUBRIC_VERSION,
        "critical_fail_rules": CRITICAL_FAIL_RULES,
        "summary": {
            "base_url": api_results["base_url"],
            "dataset_dir": api_results["dataset_dir"],
            "total_images": len(per_image),
            "api_success_count": sum(1 for item in per_image if item["api_result"]["success"]),
            "api_failure_count": sum(1 for item in per_image if not item["api_result"]["success"]),
            "critical_fail_count": critical_fail_count,
            "overall_weighted_score": overall_score,
            "conclusion": conclusion,
        },
        "selection": api_results.get("selection") or manifest.get("selection") or {},
        "runtime_snapshot": api_results.get("runtime_snapshot") or manifest.get("runtime_snapshot") or {},
        "latency_summary_ms": api_results.get("latency_summary_ms") or manifest.get("latency_summary_ms") or {},
        "risk_distribution": {
            "issue_tag_counts": dict(issue_counter.most_common()),
        },
        "long_chat_analysis": long_chat_summary,
        "top_issue_examples": top_issue_examples,
        "per_image_results": per_image,
        "manifest": manifest,
    }
    return report


def to_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 聊天截图评估集最终评估报告",
        "",
        "## 执行摘要",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Generated At: `{report['generated_at']}`",
        f"- Base URL: `{summary['base_url']}`",
        f"- Dataset Dir: `{summary['dataset_dir']}`",
        f"- Subset Name: `{report.get('selection', {}).get('subset_name', 'full')}`",
        f"- 总体结论: `{summary['conclusion']}`",
        f"- 总体加权均分: `{summary['overall_weighted_score']}`",
        f"- 关键失败图片数: `{summary['critical_fail_count']}` / `{summary['total_images']}`",
        "",
        "## 数据集概览",
        "",
        f"- 总图片数: `{summary['total_images']}`",
        f"- API 成功: `{summary['api_success_count']}`",
        f"- API 失败: `{summary['api_failure_count']}`",
        f"- Rubric Version: `{report['rubric_version']}`",
        "",
        "## 运行时快照",
        "",
        f"- Prompt Version: `{report.get('runtime_snapshot', {}).get('prompt_version', 'unspecified')}`",
        f"- Prompt Hash: `{report.get('runtime_snapshot', {}).get('prompt_hash', '-')}`",
        f"- Detect Model: `{report.get('runtime_snapshot', {}).get('detect_model', '-')}`",
        f"- OCR Model: `{report.get('runtime_snapshot', {}).get('ocr_model', '-')}`",
        f"- Thinking Disabled: `{report.get('runtime_snapshot', {}).get('thinking_disabled', True)}`",
        "",
        "## 总体评分与结论",
        "",
        f"- 评分分档规则: `推荐当前链路 / 有明显风险 / 不建议作为默认链路`",
        f"- 本次分档结果: `{summary['conclusion']}`",
        f"- 关键失败规则: `{', '.join(rule['condition'] for rule in report['critical_fail_rules'])}`",
        "",
        "## 时延统计",
        "",
        f"- total: p50=`{report.get('latency_summary_ms', {}).get('total', {}).get('p50', 0.0)}`, "
        f"p95=`{report.get('latency_summary_ms', {}).get('total', {}).get('p95', 0.0)}`",
        f"- detect: p50=`{report.get('latency_summary_ms', {}).get('detect', {}).get('p50', 0.0)}`, "
        f"p95=`{report.get('latency_summary_ms', {}).get('detect', {}).get('p95', 0.0)}`",
        f"- upload: p50=`{report.get('latency_summary_ms', {}).get('upload', {}).get('p50', 0.0)}`, "
        f"p95=`{report.get('latency_summary_ms', {}).get('upload', {}).get('p95', 0.0)}`",
        "",
        "## 高风险问题分布",
        "",
        "| Issue Tag | Count |",
        "| --- | --- |",
    ]
    issue_counts = report["risk_distribution"]["issue_tag_counts"]
    if issue_counts:
        for tag, count in issue_counts.items():
            lines.append(f"| {tag} | {count} |")
    else:
        lines.append("| (none) | 0 |")

    long_chat = report["long_chat_analysis"]
    lines.extend(
        [
            "",
            "## 长图专项分析",
            "",
            f"- 长图数量: `{long_chat['count']}`",
            f"- 长图平均加权分: `{long_chat['average_weighted_score']}`",
            f"- 长图关键失败数: `{long_chat['critical_fail_count']}`",
            f"- 长图样本: `{', '.join(long_chat['image_ids']) or '-'}`",
            "",
            "## Top 问题样例",
            "",
        ]
    )
    for item in report["top_issue_examples"]:
        judge = item["judge"]
        lines.extend(
            [
                f"### {item['image_id']}",
                f"- 路径: `{item['image_path']}`",
                f"- 加权分: `{judge['weighted_score']}`",
                f"- 关键失败: `{judge['critical_fail']}`",
                f"- 问题标签: `{', '.join(judge['issue_tags']) or '-'}`",
                f"- 结论: {judge['judge_summary']}",
                "",
            ]
        )

    lines.extend(
        [
            "## 逐图附录",
            "",
        ]
    )
    for item in report["per_image_results"]:
        judge = item["judge"]
        api = item["api_result"]
        score_text = ", ".join(f"{dim}={judge['scores'][dim]}" for dim in SCORING_DIMENSIONS)
        lines.extend(
            [
                f"### {item['image_id']}",
                f"- 图片路径: `{item['image_path']}`",
                f"- 真实 API 输出摘要: `{api['ocr_text_preview']}`",
                f"- 各维度分数: `{score_text}`",
                f"- 是否关键失败: `{judge['critical_fail']}`",
                f"- 主要问题标签: `{', '.join(judge['issue_tags']) or '-'}`",
                f"- 一句话结论: {judge['judge_summary']}",
                "",
            ]
        )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--judge-jsonl", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    run_dir = Path(args.run_dir).resolve()
    judge_inputs = [Path(item).resolve() for item in args.judge_jsonl]
    report = aggregate_run(run_dir, judge_inputs=judge_inputs or None)
    write_json(run_dir / "final_report.json", report)
    (run_dir / "final_report.md").write_text(to_markdown(report), encoding="utf-8")
    print(json.dumps({"ok": True, "run_dir": str(run_dir), "conclusion": report["summary"]["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
