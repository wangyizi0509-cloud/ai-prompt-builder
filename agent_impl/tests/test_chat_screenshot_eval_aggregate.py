from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import aggregate_chat_screenshot_eval_report as aggregate


def test_aggregate_run_synthesizes_api_failure_and_conclusion(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    api_results = {
        "run_id": "chat_screenshot_eval_test",
        "generated_at": "2026-04-01T20:00:00+08:00",
        "base_url": "http://127.0.0.1:8000",
        "dataset_dir": "/tmp/dataset",
        "image_count": 2,
        "success_count": 1,
        "failure_count": 1,
        "results": [
            {
                "image_id": "ok_001",
                "image_path": "/tmp/dataset/ok_001.png",
                "image_meta": {"width": 1080, "height": 2400, "aspect_ratio": 2.2222, "is_long_chat_candidate": False},
                "success": True,
                "detected_screenshot_type": "private_chat_screenshot",
                "final_screenshot_type": "private_chat_screenshot",
                "ocr_text": "#### 记录1 ...",
                "ocr_text_len": 40,
                "latency_ms": 120.0,
                "error": None,
            },
            {
                "image_id": "fail_001",
                "image_path": "/tmp/dataset/fail_001.png",
                "image_meta": {"width": 1080, "height": 7000, "aspect_ratio": 6.4815, "is_long_chat_candidate": True},
                "success": False,
                "detected_screenshot_type": None,
                "final_screenshot_type": None,
                "ocr_text": "",
                "ocr_text_len": 0,
                "latency_ms": 500.0,
                "error": "RuntimeError: api down",
            },
        ],
    }
    manifest = {
        "run_id": "chat_screenshot_eval_test",
        "worker_shards": [],
    }
    judge_results = {
        "image_id": "ok_001",
        "scores": {
            "speaker_attribution": 5,
            "message_recall": 4,
            "temporal_order": 4,
            "hallucination_control": 5,
            "text_accuracy": 4,
            "image_semantics": 4,
            "format_stability": 5,
        },
        "weighted_score": 4.45,
        "critical_fail": False,
        "critical_fail_reasons": [],
        "issue_tags": ["minor_text_noise"],
        "judge_summary": "整体可用，但有轻微文本噪声。",
        "evidence": ["文本有少量 OCR 噪声"],
        "confidence": 0.82,
    }

    (run_dir / "api_results.json").write_text(json.dumps(api_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "judge_results.jsonl").write_text(json.dumps(judge_results, ensure_ascii=False) + "\n", encoding="utf-8")

    report = aggregate.aggregate_run(run_dir)
    assert report["summary"]["total_images"] == 2
    assert report["summary"]["api_failure_count"] == 1
    assert report["summary"]["critical_fail_count"] == 1
    assert report["summary"]["conclusion"] == "不建议作为默认链路"

    fail_row = next(item for item in report["per_image_results"] if item["image_id"] == "fail_001")
    assert fail_row["judge"]["critical_fail"] is True
    assert "api_failure" in fail_row["judge"]["critical_fail_reasons"]

    markdown = aggregate.to_markdown(report)
    assert "## 执行摘要" in markdown
    assert "## 逐图附录" in markdown
