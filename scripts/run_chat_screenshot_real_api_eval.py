#!/usr/bin/env python3
"""Run real-API extraction against the selected chat screenshot evaluation set."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import mimetypes
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import requests

try:
    from scripts.chat_screenshot_eval_common import (
        CRITICAL_FAIL_RULES,
        DEFAULT_BASE_URL,
        DEFAULT_DATASET_DIR,
        DEFAULT_OUTPUT_ROOT,
        EVAL_SUBSETS,
        RUBRIC_VERSION,
        SCORING_DIMENSIONS,
        SUPPORTED_IMAGE_SUFFIXES,
        collect_image_meta,
        collect_runtime_snapshot,
        compute_latency_summary,
        dedupe_keep_order,
        load_image_ids_from_selection_file,
        normalize_image_id,
        now_iso,
        summarize_text,
        utc_stamp,
        write_json,
        write_jsonl,
    )
except ImportError:
    from chat_screenshot_eval_common import (
        CRITICAL_FAIL_RULES,
        DEFAULT_BASE_URL,
        DEFAULT_DATASET_DIR,
        DEFAULT_OUTPUT_ROOT,
        EVAL_SUBSETS,
        RUBRIC_VERSION,
        SCORING_DIMENSIONS,
        SUPPORTED_IMAGE_SUFFIXES,
        collect_image_meta,
        collect_runtime_snapshot,
        compute_latency_summary,
        dedupe_keep_order,
        load_image_ids_from_selection_file,
        normalize_image_id,
        now_iso,
        summarize_text,
        utc_stamp,
        write_json,
        write_jsonl,
    )


def _guess_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _as_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def check_health(base_url: str, timeout_seconds: int) -> tuple[bool, str]:
    url = base_url.rstrip("/") + "/openapi.json"
    try:
        resp = requests.get(url, timeout=timeout_seconds)
        if resp.status_code == 200:
            return True, "healthy"
        return False, f"status_{resp.status_code}"
    except Exception as exc:
        return False, _as_error(exc)


def build_auth_headers(auth_token: str | None) -> dict[str, str]:
    token = (auth_token or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def login_and_get_token(base_url: str, email: str, password: str, timeout_seconds: int) -> str:
    url = base_url.rstrip("/") + "/api/auth/login"
    resp = requests.post(url, json={"email": email, "password": password}, timeout=timeout_seconds)
    resp.raise_for_status()
    payload = resp.json() if resp.content else {}
    token = str(payload.get("token") or "").strip() if isinstance(payload, dict) else ""
    if not token:
        raise RuntimeError("login succeeded but token missing")
    return token


def create_local_eval_token() -> str | None:
    try:
        project_root = Path(__file__).resolve().parents[1]
        agent_root = project_root / "agent_impl"
        if str(agent_root) not in sys.path:
            sys.path.insert(0, str(agent_root))
        from auth_utils import create_jwt_token
    except Exception:
        return None

    user_id = str(uuid.uuid4())
    return create_jwt_token(
        user_id=user_id,
        email="chat-eval@local.test",
        username="chat-eval",
        expires_days=1,
    )


def detect_screenshot_type(base_url: str, image_path: Path, timeout_seconds: int, auth_token: str | None = None) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/upload/detect-type"
    started = time.perf_counter()
    with image_path.open("rb") as fh:
        resp = requests.post(
            url,
            files={"file": (image_path.name, fh, _guess_mime(image_path))},
            headers=build_auth_headers(auth_token),
            timeout=timeout_seconds,
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    resp.raise_for_status()
    payload = resp.json() if resp.content else {}
    if not isinstance(payload, dict):
        raise RuntimeError("detect-type response is not a JSON object")
    payload["_latency_ms"] = elapsed_ms
    return payload


def upload_screenshot(
    base_url: str,
    session_id: str,
    image_path: Path,
    screenshot_type: str,
    timeout_seconds: int,
    auth_token: str | None = None,
    eval_mode: bool = False,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/upload/upload-screenshot"
    started = time.perf_counter()
    with image_path.open("rb") as fh:
        resp = requests.post(
            url,
            files={"file": (image_path.name, fh, _guess_mime(image_path))},
            data={
                "screenshot_type": screenshot_type,
                "session_id": session_id,
                "eval_mode": "true" if eval_mode else "false",
            },
            headers=build_auth_headers(auth_token),
            timeout=timeout_seconds,
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    resp.raise_for_status()
    payload = resp.json() if resp.content else {}
    if not isinstance(payload, dict):
        raise RuntimeError("upload-screenshot response is not a JSON object")
    payload["_latency_ms"] = elapsed_ms
    return payload


def list_dataset_images(dataset_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(dataset_dir.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    ]


def _load_image_ids_file(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if path.suffix.lower() == ".json":
        return load_image_ids_from_selection_file(path)
    if path.suffix.lower() == ".jsonl":
        rows = []
        for line in raw.splitlines():
            text = line.strip()
            if not text:
                continue
            obj = json.loads(text)
            if isinstance(obj, dict):
                if obj.get("image_id"):
                    rows.append(normalize_image_id(obj["image_id"]))
                elif obj.get("image_path"):
                    rows.append(normalize_image_id(obj["image_path"]))
            else:
                rows.append(normalize_image_id(str(obj)))
        return dedupe_keep_order(rows)
    return dedupe_keep_order([normalize_image_id(line) for line in raw.splitlines() if line.strip()])


def resolve_selected_images(
    dataset_dir: Path,
    *,
    limit: int | None = None,
    image_ids: list[str] | None = None,
    image_ids_file: Path | None = None,
    selection_manifest: Path | None = None,
    subset_name: str | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    available_images = list_dataset_images(dataset_dir)
    available_by_id = {path.stem: path for path in available_images}

    requested_ids: list[str] = []
    selection_sources: list[str] = []
    if subset_name:
        if subset_name not in EVAL_SUBSETS:
            raise RuntimeError(f"Unknown subset_name: {subset_name}")
        requested_ids.extend(EVAL_SUBSETS[subset_name])
        selection_sources.append(f"subset:{subset_name}")
    if selection_manifest:
        requested_ids.extend(load_image_ids_from_selection_file(selection_manifest))
        selection_sources.append(f"manifest:{selection_manifest}")
    if image_ids_file:
        requested_ids.extend(_load_image_ids_file(image_ids_file))
        selection_sources.append(f"ids_file:{image_ids_file}")
    if image_ids:
        requested_ids.extend(normalize_image_id(item) for item in image_ids)
        selection_sources.append("cli:image_id")

    normalized_ids = dedupe_keep_order(requested_ids)
    if normalized_ids:
        missing = [image_id for image_id in normalized_ids if image_id not in available_by_id]
        if missing:
            raise RuntimeError(f"Requested image ids not found in dataset: {', '.join(missing)}")
        images = [available_by_id[image_id] for image_id in normalized_ids]
    else:
        images = available_images

    if limit is not None:
        images = images[: max(0, limit)]

    resolved_subset_name = subset_name or ("custom" if normalized_ids else "full")
    selection_meta = {
        "subset_name": resolved_subset_name,
        "selection_sources": selection_sources or ["dataset_scan"],
        "requested_image_ids": normalized_ids,
        "selected_image_ids": [path.stem for path in images],
        "selected_count": len(images),
    }
    return images, selection_meta


def build_judge_packet(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "image_id": row["image_id"],
        "image_path": row["image_path"],
        "image_meta": row["image_meta"],
        "api_result": {
            "success": row["success"],
            "detected_screenshot_type": row["detected_screenshot_type"],
            "final_screenshot_type": row["final_screenshot_type"],
            "ocr_text": row["ocr_text"],
            "ocr_text_len": row["ocr_text_len"],
            "error": row["error"],
            "latency_ms": row["latency_ms"],
            "detect_latency_ms": row["detect_latency_ms"],
            "upload_latency_ms": row["upload_latency_ms"],
        },
        "rubric_version": RUBRIC_VERSION,
        "scoring_dimensions": SCORING_DIMENSIONS,
        "critical_fail_rules": CRITICAL_FAIL_RULES,
        "judge_task": (
            "你是聊天截图提取评审员。请对比原图与真实 API 输出，按 scoring_dimensions 对每一维打 1-5 分。"
            " issue_tags 只保留高价值问题标签；如存在严重错误，critical_fail 必须为 true。"
        ),
        "output_contract": {
            "image_id": "str",
            "scores": {dim: "int(1-5)" for dim in SCORING_DIMENSIONS},
            "weighted_score": "float",
            "critical_fail": "bool",
            "critical_fail_reasons": "list[str]",
            "issue_tags": "list[str]",
            "judge_summary": "str",
            "evidence": "list[str]",
            "confidence": "float(0-1)",
        },
    }


def estimate_packet_weight(packet: dict[str, Any]) -> int:
    meta = packet["image_meta"]
    api = packet["api_result"]
    weight = 1
    if meta.get("is_long_chat_candidate"):
        weight += 4
    if int(meta.get("height") or 0) >= 3000:
        weight += 1
    if int(api.get("ocr_text_len") or 0) >= 3000:
        weight += 1
    if not api.get("success"):
        weight += 1
    return weight


def shard_packets(packets: list[dict[str, Any]], worker_count: int) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = [[] for _ in range(max(1, worker_count))]
    weights = [0 for _ in groups]
    ordered = sorted(
        packets,
        key=lambda item: (-estimate_packet_weight(item), item["image_path"]),
    )
    for packet in ordered:
        idx = min(range(len(groups)), key=lambda i: (weights[i], len(groups[i]), i))
        groups[idx].append(packet)
        weights[idx] += estimate_packet_weight(packet)
    return groups


def run_dataset(
    *,
    dataset_dir: Path,
    output_root: Path,
    base_url: str,
    timeout_seconds: int,
    worker_count: int,
    request_concurrency: int,
    limit: int | None = None,
    image_ids: list[str] | None = None,
    image_ids_file: Path | None = None,
    selection_manifest: Path | None = None,
    subset_name: str | None = None,
    prompt_version: str | None = None,
    skip_health_check: bool = False,
    auth_token: str | None = None,
    login_email: str | None = None,
    login_password: str | None = None,
    eval_mode: bool = True,
) -> Path:
    run_id = f"chat_screenshot_eval_{utc_stamp()}"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    shard_dir = run_dir / "judge_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)

    images, selection_meta = resolve_selected_images(
        dataset_dir,
        limit=limit,
        image_ids=image_ids,
        image_ids_file=image_ids_file,
        selection_manifest=selection_manifest,
        subset_name=subset_name,
    )
    if not images:
        raise RuntimeError(f"No images found in dataset dir: {dataset_dir}")

    if not skip_health_check:
        ok, reason = check_health(base_url, timeout_seconds=min(timeout_seconds, 6))
        if not ok:
            raise RuntimeError(f"Service unhealthy at {base_url}: {reason}")

    resolved_token = (auth_token or "").strip() or None
    if resolved_token is None and login_email and login_password:
        resolved_token = login_and_get_token(
            base_url=base_url,
            email=login_email,
            password=login_password,
            timeout_seconds=timeout_seconds,
        )
    if resolved_token is None:
        resolved_token = create_local_eval_token()

    rows: list[dict[str, Any]] = []
    packets: list[dict[str, Any]] = []

    def _process_one(index_and_path: tuple[int, Path]) -> dict[str, Any]:
        index, image_path = index_and_path
        image_meta = collect_image_meta(image_path)
        row = {
            "index": index,
            "image_id": image_path.stem,
            "image_path": str(image_path.resolve()),
            "image_meta": image_meta,
            "success": False,
            "detected_screenshot_type": None,
            "final_screenshot_type": None,
            "ocr_text": "",
            "ocr_text_len": 0,
            "latency_ms": 0.0,
            "detect_latency_ms": 0.0,
            "upload_latency_ms": 0.0,
            "error": None,
            "run_started_at": now_iso(),
            "run_finished_at": None,
        }
        started = time.perf_counter()
        session_id = f"{run_id}_{index:03d}"
        try:
            detect_result = detect_screenshot_type(base_url, image_path, timeout_seconds, auth_token=resolved_token)
            detected_type = str(detect_result.get("screenshot_type") or "universal_screenshot_analysis")
            upload_result = upload_screenshot(
                base_url,
                session_id,
                image_path,
                detected_type,
                timeout_seconds,
                auth_token=resolved_token,
                eval_mode=eval_mode,
            )
            ocr_text = str(upload_result.get("text") or "")

            row.update(
                {
                    "success": bool(upload_result.get("success")),
                    "detected_screenshot_type": detected_type,
                    "final_screenshot_type": str(upload_result.get("screenshot_type") or detected_type),
                    "ocr_text": ocr_text,
                    "ocr_text_len": len(ocr_text),
                    "detect_latency_ms": float(detect_result.get("_latency_ms") or 0.0),
                    "upload_latency_ms": float(upload_result.get("_latency_ms") or 0.0),
                    "error": upload_result.get("error"),
                }
            )
        except Exception as exc:
            row["error"] = _as_error(exc)
        finally:
            row["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
            row["run_finished_at"] = now_iso()
        return row

    items = list(enumerate(images, start=1))
    if request_concurrency <= 1:
        rows = [_process_one(item) for item in items]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=request_concurrency) as executor:
            rows = list(executor.map(_process_one, items))
    rows.sort(key=lambda item: item["index"])
    packets = [build_judge_packet(row) for row in rows]

    shards = shard_packets(packets, worker_count=worker_count)
    runtime_snapshot = collect_runtime_snapshot(prompt_version=prompt_version)
    latency_summary_ms = {
        "total": compute_latency_summary(rows, "latency_ms"),
        "detect": compute_latency_summary(rows, "detect_latency_ms"),
        "upload": compute_latency_summary(rows, "upload_latency_ms"),
    }

    api_results = {
        "run_id": run_id,
        "generated_at": now_iso(),
        "base_url": base_url,
        "dataset_dir": str(dataset_dir.resolve()),
        "auth_mode": "bearer" if resolved_token else "anonymous",
        "eval_mode": eval_mode,
        "request_concurrency": request_concurrency,
        "image_count": len(rows),
        "success_count": sum(1 for row in rows if row["success"]),
        "failure_count": sum(1 for row in rows if not row["success"]),
        "selection": selection_meta,
        "runtime_snapshot": runtime_snapshot,
        "latency_summary_ms": latency_summary_ms,
        "results": rows,
    }

    manifest = {
        "run_id": run_id,
        "generated_at": now_iso(),
        "base_url": base_url,
        "dataset_dir": str(dataset_dir.resolve()),
        "output_dir": str(run_dir.resolve()),
        "auth_mode": "bearer" if resolved_token else "anonymous",
        "eval_mode": eval_mode,
        "rubric_version": RUBRIC_VERSION,
        "image_count": len(rows),
        "success_count": api_results["success_count"],
        "failure_count": api_results["failure_count"],
        "worker_count": worker_count,
        "request_concurrency": request_concurrency,
        "selection": selection_meta,
        "runtime_snapshot": runtime_snapshot,
        "latency_summary_ms": latency_summary_ms,
        "files": {
            "api_results_json": str((run_dir / "api_results.json").resolve()),
            "api_results_md": str((run_dir / "api_results.md").resolve()),
            "judge_packets_jsonl": str((run_dir / "judge_packets.jsonl").resolve()),
            "manifest_json": str((run_dir / "manifest.json").resolve()),
        },
        "worker_shards": [],
    }

    for idx, shard in enumerate(shards, start=1):
        shard_path = shard_dir / f"worker_{idx:02d}.jsonl"
        write_jsonl(shard_path, shard)
        manifest["worker_shards"].append(
            {
                "worker_id": idx,
                "path": str(shard_path.resolve()),
                "item_count": len(shard),
                "estimated_weight": sum(estimate_packet_weight(packet) for packet in shard),
                "image_ids": [packet["image_id"] for packet in shard],
            }
        )

    write_json(run_dir / "api_results.json", api_results)
    write_jsonl(run_dir / "judge_packets.jsonl", packets)
    write_json(run_dir / "manifest.json", manifest)
    (run_dir / "api_results.md").write_text(to_markdown(api_results, manifest), encoding="utf-8")

    return run_dir


def to_markdown(api_results: dict[str, Any], manifest: dict[str, Any]) -> str:
    lines = [
        "# 聊天截图评估集真实 API 运行结果",
        "",
        f"- Run ID: `{api_results['run_id']}`",
        f"- Generated At: `{api_results['generated_at']}`",
        f"- Base URL: `{api_results['base_url']}`",
        f"- Dataset Dir: `{api_results['dataset_dir']}`",
        f"- Eval Mode: `{api_results.get('eval_mode', False)}`",
        f"- Request Concurrency: `{api_results.get('request_concurrency', 1)}`",
        f"- Subset Name: `{api_results.get('selection', {}).get('subset_name', 'full')}`",
        f"- Selected Images: `{api_results.get('selection', {}).get('selected_count', api_results['image_count'])}`",
        f"- Images: `{api_results['image_count']}`",
        f"- Success: `{api_results['success_count']}`",
        f"- Failure: `{api_results['failure_count']}`",
        f"- Prompt Version: `{api_results.get('runtime_snapshot', {}).get('prompt_version', 'unspecified')}`",
        f"- Prompt Hash: `{api_results.get('runtime_snapshot', {}).get('prompt_hash', '-')}`",
        f"- Detect Model: `{api_results.get('runtime_snapshot', {}).get('detect_model', '-')}`",
        f"- OCR Model: `{api_results.get('runtime_snapshot', {}).get('ocr_model', '-')}`",
        f"- Long Chat OCR Model: `{api_results.get('runtime_snapshot', {}).get('long_chat_ocr_model', '-')}`",
        f"- Thinking Disabled: `{api_results.get('runtime_snapshot', {}).get('thinking_disabled', True)}`",
        "",
        "## Latency Summary (ms)",
        "",
        "| Stage | Min | P50 | P95 | Max | Avg |",
        "| --- | --- | --- | --- | --- | --- |",
        (
            f"| total | {api_results['latency_summary_ms']['total']['min']} | "
            f"{api_results['latency_summary_ms']['total']['p50']} | "
            f"{api_results['latency_summary_ms']['total']['p95']} | "
            f"{api_results['latency_summary_ms']['total']['max']} | "
            f"{api_results['latency_summary_ms']['total']['avg']} |"
        ),
        (
            f"| detect | {api_results['latency_summary_ms']['detect']['min']} | "
            f"{api_results['latency_summary_ms']['detect']['p50']} | "
            f"{api_results['latency_summary_ms']['detect']['p95']} | "
            f"{api_results['latency_summary_ms']['detect']['max']} | "
            f"{api_results['latency_summary_ms']['detect']['avg']} |"
        ),
        (
            f"| upload | {api_results['latency_summary_ms']['upload']['min']} | "
            f"{api_results['latency_summary_ms']['upload']['p50']} | "
            f"{api_results['latency_summary_ms']['upload']['p95']} | "
            f"{api_results['latency_summary_ms']['upload']['max']} | "
            f"{api_results['latency_summary_ms']['upload']['avg']} |"
        ),
        "",
        "## Worker Shards",
        "",
        "| Worker | Count | Estimated Weight | Images |",
        "| --- | --- | --- | --- |",
    ]
    for shard in manifest["worker_shards"]:
        lines.append(
            f"| {shard['worker_id']} | {shard['item_count']} | {shard['estimated_weight']} | "
            + ", ".join(shard["image_ids"])
            + " |"
        )

    lines.extend(
        [
            "",
            "## Per Image",
            "",
            "| # | Image ID | Long Chat | Detected Type | Final Type | Success | Latency(ms) | OCR Len | Error |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in api_results["results"]:
        lines.append(
            f"| {row['index']} | {row['image_id']} | {row['image_meta']['is_long_chat_candidate']} | "
            f"{row['detected_screenshot_type'] or '-'} | {row['final_screenshot_type'] or '-'} | "
            f"{row['success']} | {row['latency_ms']} | {row['ocr_text_len']} | "
            f"{summarize_text(str(row['error'] or ''), 80) or '-'} |"
        )

    lines.append("")
    for row in api_results["results"]:
        lines.extend(
            [
                f"### {row['image_id']}",
                f"- Path: `{row['image_path']}`",
                f"- Size: `{row['image_meta']['width']}x{row['image_meta']['height']}`",
                f"- Long Chat Candidate: `{row['image_meta']['is_long_chat_candidate']}`",
                f"- Success: `{row['success']}`",
                f"- Detected Type: `{row['detected_screenshot_type']}`",
                f"- Final Type: `{row['final_screenshot_type']}`",
                f"- Latency(ms): total=`{row['latency_ms']}`, detect=`{row['detect_latency_ms']}`, upload=`{row['upload_latency_ms']}`",
                f"- OCR Preview: `{summarize_text(row['ocr_text'], 300)}`",
            ]
        )
        if row["error"]:
            lines.append(f"- Error: `{row['error']}`")
        lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--worker-count", type=int, default=4)
    parser.add_argument("--request-concurrency", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--image-id", action="append", default=[])
    parser.add_argument("--image-ids-file", default="")
    parser.add_argument("--selection-manifest", default="")
    parser.add_argument("--subset-name", choices=sorted(EVAL_SUBSETS.keys()), default=None)
    parser.add_argument("--prompt-version", default="")
    parser.add_argument("--skip-health-check", action="store_true")
    parser.add_argument("--auth-token", default="")
    parser.add_argument("--login-email", default="")
    parser.add_argument("--login-password", default="")
    parser.add_argument("--eval-mode", dest="eval_mode", action="store_true", default=True)
    parser.add_argument("--no-eval-mode", dest="eval_mode", action="store_false")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    run_dir = run_dataset(
        dataset_dir=Path(args.dataset_dir).resolve(),
        output_root=Path(args.output_root).resolve(),
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        worker_count=max(1, args.worker_count),
        request_concurrency=max(1, args.request_concurrency),
        limit=args.limit,
        image_ids=args.image_id or None,
        image_ids_file=Path(args.image_ids_file).resolve() if args.image_ids_file else None,
        selection_manifest=Path(args.selection_manifest).resolve() if args.selection_manifest else None,
        subset_name=args.subset_name,
        prompt_version=args.prompt_version or None,
        skip_health_check=bool(args.skip_health_check),
        auth_token=args.auth_token or None,
        login_email=args.login_email or None,
        login_password=args.login_password or None,
        eval_mode=bool(args.eval_mode),
    )
    print(json.dumps({"ok": True, "run_dir": str(run_dir.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
