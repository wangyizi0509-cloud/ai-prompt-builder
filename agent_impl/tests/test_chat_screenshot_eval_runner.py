from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_chat_screenshot_real_api_eval as runner
from scripts.chat_screenshot_eval_common import FULL_PRIVATE_CHAT_IMAGE_IDS, SMALL_EVAL_IMAGE_IDS


def _make_image(path: Path, size: tuple[int, int]) -> None:
    img = Image.new("RGB", size, color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    path.write_bytes(buf.getvalue())


def test_run_dataset_writes_required_artifacts(monkeypatch, tmp_path: Path):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    _make_image(dataset_dir / "001.png", (1080, 2400))
    _make_image(dataset_dir / "002.png", (1080, 6000))

    monkeypatch.setattr(runner, "check_health", lambda *args, **kwargs: (True, "healthy"))
    monkeypatch.setattr(
        runner,
        "detect_screenshot_type",
        lambda *args, **kwargs: {"screenshot_type": "private_chat_screenshot", "_latency_ms": 12.0},
    )

    def _fake_upload(*args, **kwargs):
        image_path = Path(kwargs["image_path"] if "image_path" in kwargs else args[2])
        return {
            "success": True,
            "text": f"ocr for {image_path.stem}",
            "screenshot_type": "private_chat_screenshot",
            "error": None,
            "_latency_ms": 34.0,
        }

    monkeypatch.setattr(runner, "upload_screenshot", _fake_upload)

    run_dir = runner.run_dataset(
        dataset_dir=dataset_dir,
        output_root=tmp_path / "out",
        base_url="http://127.0.0.1:8000",
        timeout_seconds=30,
        worker_count=4,
        request_concurrency=2,
        limit=None,
        skip_health_check=False,
        eval_mode=True,
    )

    assert (run_dir / "api_results.json").exists()
    assert (run_dir / "api_results.md").exists()
    assert (run_dir / "judge_packets.jsonl").exists()
    assert (run_dir / "manifest.json").exists()

    api_results = json.loads((run_dir / "api_results.json").read_text(encoding="utf-8"))
    assert api_results["image_count"] == 2
    assert api_results["success_count"] == 2
    assert api_results["failure_count"] == 0
    assert api_results["selection"]["subset_name"] == "full"
    assert api_results["runtime_snapshot"]["prompt_hash"]
    assert api_results["results"][1]["image_meta"]["is_long_chat_candidate"] is True

    judge_packets = [json.loads(line) for line in (run_dir / "judge_packets.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(judge_packets) == 2
    assert judge_packets[0]["rubric_version"] == "chat_screenshot_eval_v1"
    assert "scoring_dimensions" in judge_packets[0]
    assert "critical_fail_rules" in judge_packets[0]

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["worker_shards"]) == 4
    assert manifest["request_concurrency"] == 2
    assert manifest["eval_mode"] is True
    assert manifest["latency_summary_ms"]["total"]["p50"] >= 0.0
    shard_item_total = sum(int(item["item_count"]) for item in manifest["worker_shards"])
    assert shard_item_total == 2


def test_run_dataset_supports_subset_name_and_image_id_filter(monkeypatch, tmp_path: Path):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    image_ids = list(SMALL_EVAL_IMAGE_IDS) + ["z_custom_extra"]
    for image_id in image_ids:
        _make_image(dataset_dir / f"{image_id}.png", (1080, 2400))

    monkeypatch.setattr(runner, "check_health", lambda *args, **kwargs: (True, "healthy"))
    monkeypatch.setattr(
        runner,
        "detect_screenshot_type",
        lambda *args, **kwargs: {"screenshot_type": "private_chat_screenshot", "_latency_ms": 10.0},
    )
    monkeypatch.setattr(
        runner,
        "upload_screenshot",
        lambda *args, **kwargs: {
            "success": True,
            "text": "ocr",
            "screenshot_type": "private_chat_screenshot",
            "error": None,
            "_latency_ms": 20.0,
        },
    )

    run_dir = runner.run_dataset(
        dataset_dir=dataset_dir,
        output_root=tmp_path / "out",
        base_url="http://127.0.0.1:8000",
        timeout_seconds=30,
        worker_count=2,
        request_concurrency=1,
        subset_name="small",
        image_ids=["z_custom_extra"],
        skip_health_check=False,
        prompt_version="prompt-v2",
        eval_mode=True,
    )

    api_results = json.loads((run_dir / "api_results.json").read_text(encoding="utf-8"))
    assert api_results["selection"]["subset_name"] == "small"
    assert api_results["selection"]["selected_image_ids"] == list(SMALL_EVAL_IMAGE_IDS) + ["z_custom_extra"]
    assert api_results["runtime_snapshot"]["prompt_version"] == "prompt-v2"


def test_run_dataset_full_subset_uses_private_chat_gate_ids(monkeypatch, tmp_path: Path):
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    image_ids = list(FULL_PRIVATE_CHAT_IMAGE_IDS) + ["group_noise_sample"]
    for image_id in image_ids:
        _make_image(dataset_dir / f"{image_id}.png", (1080, 2400))

    monkeypatch.setattr(runner, "check_health", lambda *args, **kwargs: (True, "healthy"))
    monkeypatch.setattr(
        runner,
        "detect_screenshot_type",
        lambda *args, **kwargs: {"screenshot_type": "private_chat_screenshot", "_latency_ms": 10.0},
    )
    monkeypatch.setattr(
        runner,
        "upload_screenshot",
        lambda *args, **kwargs: {
            "success": True,
            "text": "ocr",
            "screenshot_type": "private_chat_screenshot",
            "error": None,
            "_latency_ms": 20.0,
        },
    )

    run_dir = runner.run_dataset(
        dataset_dir=dataset_dir,
        output_root=tmp_path / "out",
        base_url="http://127.0.0.1:8000",
        timeout_seconds=30,
        worker_count=2,
        request_concurrency=1,
        subset_name="full",
        skip_health_check=False,
        eval_mode=True,
    )

    api_results = json.loads((run_dir / "api_results.json").read_text(encoding="utf-8"))
    assert api_results["selection"]["subset_name"] == "full"
    assert api_results["selection"]["selected_image_ids"] == list(FULL_PRIVATE_CHAT_IMAGE_IDS)
    assert "group_noise_sample" not in api_results["selection"]["selected_image_ids"]
