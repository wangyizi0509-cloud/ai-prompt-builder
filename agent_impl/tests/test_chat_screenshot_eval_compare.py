from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import compare_chat_screenshot_eval_runs as compare


def _build_run_dir(
    base_dir: Path,
    name: str,
    image_ids: list[str],
    *,
    weighted_score: float,
    speaker_score: float,
    critical_fail_ids: set[str] | None = None,
    issue_tags_by_id: dict[str, list[str]] | None = None,
    latency_ms: float,
    detect_latency_ms: float,
    upload_latency_ms: float,
) -> Path:
    run_dir = base_dir / name
    run_dir.mkdir(parents=True, exist_ok=True)
    critical_fail_ids = critical_fail_ids or set()
    issue_tags_by_id = issue_tags_by_id or {}

    per_image_results = []
    api_results = []

    for idx, image_id in enumerate(image_ids, start=1):
        is_fail = image_id in critical_fail_ids
        per_image_results.append(
            {
                "image_id": image_id,
                "image_path": f"/tmp/{image_id}.png",
                "image_meta": {
                    "width": 1080,
                    "height": 2400,
                    "aspect_ratio": 2.2222,
                    "is_long_chat_candidate": False,
                },
                "api_result": {
                    "success": True,
                    "detected_screenshot_type": "private_chat_screenshot",
                    "final_screenshot_type": "private_chat_screenshot",
                    "ocr_text_len": 100,
                    "latency_ms": latency_ms,
                    "error": None,
                },
                "judge": {
                    "scores": {
                        "speaker_attribution": speaker_score,
                        "message_recall": 4,
                        "temporal_order": 4,
                        "hallucination_control": 4 if not is_fail else 2,
                        "text_accuracy": 4,
                        "image_semantics": 4,
                        "format_stability": 5,
                    },
                    "weighted_score": weighted_score,
                    "critical_fail": is_fail,
                    "critical_fail_reasons": ["speaker_attribution<=2"] if is_fail else [],
                    "issue_tags": issue_tags_by_id.get(image_id, []),
                    "judge_summary": "stub",
                    "evidence": ["stub"],
                    "confidence": 0.9,
                },
                "appendix_summary": "stub",
            }
        )
        api_results.append(
            {
                "index": idx,
                "image_id": image_id,
                "image_path": f"/tmp/{image_id}.png",
                "image_meta": {
                    "width": 1080,
                    "height": 2400,
                    "aspect_ratio": 2.2222,
                    "file_size_bytes": 12345,
                    "is_long_chat_candidate": False,
                },
                "success": True,
                "detected_screenshot_type": "private_chat_screenshot",
                "final_screenshot_type": "private_chat_screenshot",
                "ocr_text": f"text {image_id}",
                "ocr_text_len": 100,
                "latency_ms": latency_ms,
                "detect_latency_ms": detect_latency_ms,
                "upload_latency_ms": upload_latency_ms,
                "error": None,
                "run_started_at": "2026-04-01T10:00:00+08:00",
                "run_finished_at": "2026-04-01T10:00:01+08:00",
            }
        )

    final_report = {
        "run_id": f"{name}_run",
        "generated_at": "2026-04-01T10:00:00+08:00",
        "summary": {
            "total_images": len(image_ids),
            "api_success_count": len(image_ids),
            "api_failure_count": 0,
            "critical_fail_count": len(critical_fail_ids),
            "overall_weighted_score": weighted_score,
            "conclusion": "stub",
        },
        "risk_distribution": {
            "issue_tag_counts": {},
        },
        "long_chat_analysis": {
            "count": 0,
            "average_weighted_score": None,
            "critical_fail_count": 0,
            "image_ids": [],
        },
        "top_issue_examples": [],
        "per_image_results": per_image_results,
        "manifest": {
            "worker_count": 1,
        },
    }
    api_results_json = {
        "run_id": f"{name}_run",
        "generated_at": "2026-04-01T10:00:00+08:00",
        "base_url": "http://127.0.0.1:8000",
        "dataset_dir": "/tmp/dataset",
        "auth_mode": "bearer",
        "eval_mode": True,
        "request_concurrency": 1,
        "image_count": len(image_ids),
        "success_count": len(image_ids),
        "failure_count": 0,
        "results": api_results,
    }

    (run_dir / "final_report.json").write_text(json.dumps(final_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "api_results.json").write_text(json.dumps(api_results_json, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir


def test_compare_small_gate_generates_json_and_markdown(tmp_path: Path):
    ids = compare.SMALL_GATE_IMAGE_IDS
    baseline = _build_run_dir(
        tmp_path,
        "baseline_small",
        ids,
        weighted_score=3.50,
        speaker_score=2.60,
        critical_fail_ids={ids[0], ids[1], ids[2], ids[3], ids[4]},
        issue_tags_by_id={ids[0]: ["minor_text_noise"], ids[1]: ["speaker_swap_major"]},
        latency_ms=1000.0,
        detect_latency_ms=200.0,
        upload_latency_ms=800.0,
    )
    candidate = _build_run_dir(
        tmp_path,
        "candidate_small",
        ids,
        weighted_score=3.72,
        speaker_score=3.30,
        critical_fail_ids={ids[0], ids[1], ids[2]},
        issue_tags_by_id={ids[0]: ["minor_text_noise"]},
        latency_ms=1050.0,
        detect_latency_ms=210.0,
        upload_latency_ms=840.0,
    )

    report = compare.compare_runs(baseline, candidate, "small")

    assert report["gate_result"]["passed"] is True
    assert report["comparison"]["candidate"]["selected_count"] == len(ids)
    assert report["comparison"]["delta"]["speaker_attribution"] == 0.7
    assert report["comparison"]["delta"]["critical_fail_count"] == -2.0
    assert report["comparison"]["delta"]["latency"]["latency_ms"]["p50"] == 50.0

    out_json = tmp_path / "out" / "compare_small.json"
    out_md = tmp_path / "out" / "compare_small.md"
    compare.write_outputs(report, out_json, out_md)

    assert out_json.exists()
    assert out_md.exists()
    written = json.loads(out_json.read_text(encoding="utf-8"))
    assert written["gate"]["name"] == "small"
    assert "speaker_attribution" in out_md.read_text(encoding="utf-8")
    assert "Gate Checks" in out_md.read_text(encoding="utf-8")


def test_compare_failure_pool_gate_uses_fixed_private_chat_ids(tmp_path: Path):
    ids = compare.FAILURE_POOL_GATE_IMAGE_IDS
    baseline = _build_run_dir(
        tmp_path,
        "baseline_failure_pool",
        ids,
        weighted_score=3.20,
        speaker_score=2.40,
        critical_fail_ids=set(ids),
        issue_tags_by_id={ids[0]: ["speaker_swap_major"], ids[1]: ["time_separator_as_message"]},
        latency_ms=2000.0,
        detect_latency_ms=300.0,
        upload_latency_ms=1700.0,
    )
    candidate = _build_run_dir(
        tmp_path,
        "candidate_failure_pool",
        ids,
        weighted_score=3.55,
        speaker_score=2.95,
        critical_fail_ids={ids[0], ids[1]},
        issue_tags_by_id={ids[0]: ["minor_text_noise"]},
        latency_ms=2080.0,
        detect_latency_ms=320.0,
        upload_latency_ms=1760.0,
    )

    report = compare.compare_runs(baseline, candidate, "failure_pool")

    assert report["comparison"]["selected_count"] == len(ids)
    assert report["comparison"]["candidate"]["critical_fail_count"] == 2
    assert report["gate_result"]["passed"] is True
    assert report["gate_result"]["reasons"] == []


def test_compare_failure_pool_gate_blocks_sender_flip_tags(tmp_path: Path):
    ids = compare.FAILURE_POOL_GATE_IMAGE_IDS
    baseline = _build_run_dir(
        tmp_path,
        "baseline_failure_pool_sender_flip",
        ids,
        weighted_score=3.20,
        speaker_score=2.40,
        critical_fail_ids=set(ids),
        issue_tags_by_id={ids[0]: ["speaker_swap_major"]},
        latency_ms=2000.0,
        detect_latency_ms=300.0,
        upload_latency_ms=1700.0,
    )
    candidate = _build_run_dir(
        tmp_path,
        "candidate_failure_pool_sender_flip",
        ids,
        weighted_score=3.90,
        speaker_score=4.20,
        critical_fail_ids={ids[0]},
        issue_tags_by_id={ids[0]: ["sender_flip"]},
        latency_ms=2020.0,
        detect_latency_ms=310.0,
        upload_latency_ms=1710.0,
    )

    report = compare.compare_runs(baseline, candidate, "failure_pool")

    assert report["gate_result"]["passed"] is False
    assert "forbidden_issue_tags" in report["gate_result"]["reasons"]


def test_compare_full_gate_requires_quality_thresholds(tmp_path: Path):
    ids = compare.FULL_GATE_IMAGE_IDS
    baseline = _build_run_dir(
        tmp_path,
        "baseline_full",
        ids,
        weighted_score=3.78,
        speaker_score=2.95,
        critical_fail_ids={ids[0], ids[1], ids[2], ids[3], ids[4], ids[5]},
        issue_tags_by_id={ids[0]: ["speaker_swap_major"], ids[1]: ["massive_hallucination"]},
        latency_ms=3000.0,
        detect_latency_ms=400.0,
        upload_latency_ms=2600.0,
    )
    candidate = _build_run_dir(
        tmp_path,
        "candidate_full",
        ids,
        weighted_score=4.30,
        speaker_score=3.70,
        critical_fail_ids={ids[0], ids[1], ids[2]},
        issue_tags_by_id={ids[0]: ["minor_text_noise"]},
        latency_ms=3120.0,
        detect_latency_ms=420.0,
        upload_latency_ms=2700.0,
    )

    report = compare.compare_runs(baseline, candidate, "full")

    assert report["comparison"]["selected_count"] == len(ids)
    assert report["gate_result"]["passed"] is True
    assert report["comparison"]["delta"]["weighted_score"] == 0.52
    assert report["comparison"]["delta"]["critical_fail_count"] == -3.0
    assert report["comparison"]["candidate"]["weighted_score"] == 4.3
    assert report["comparison"]["candidate"]["speaker_attribution"] == 3.7
