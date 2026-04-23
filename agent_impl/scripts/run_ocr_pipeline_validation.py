#!/usr/bin/env python3
"""
Run end-to-end validation for:
1) first-node route stability
2) second-node reference vs GLM candidate sequence
3) OCR + low-confidence postprocess + fallback shadow pipeline

Outputs are written to /Users/ant/Crushe/模型策略/output/*.json and *.md
"""

from __future__ import annotations

import asyncio
import argparse
import base64
import json
import os
import re
import statistics
import sys
import time
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import httpx
from PIL import Image

REPO_ROOT = Path("/Users/ant/Crushe/模型策略")
AGENT_IMPL_ROOT = REPO_ROOT / "agent_impl"
OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_BIGMODEL_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_REFERENCE_PROVIDER = "glm"
DEFAULT_REFERENCE_MODEL = "GLM-4.6V-FlashX"
DEFAULT_DOUBAO_REFERENCE_MODEL = "Doubao-Seed-1.6-flash"
DEFAULT_GLM_CANDIDATE_MODELS = [
    "GLM-4.6V-FlashX",
    "GLM-OCR",
]

if str(AGENT_IMPL_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_IMPL_ROOT))
if "/tmp/volc_sdk_test" not in sys.path:
    sys.path.insert(0, "/tmp/volc_sdk_test")

from utils.image_processor import ImageProcessor  # noqa: E402
from utils.ocr_assembler import assemble_ocr_text  # noqa: E402
from utils.ocr_normalizer import average_confidence, normalize_general_ocr_lines  # noqa: E402
try:
    from volcenginesdkcore import ApiClient, Configuration  # noqa: E402
    from volcenginesdkcore.universal import UniversalApi, UniversalInfo  # noqa: E402
    VOLC_SDK_IMPORT_ERROR: Exception | None = None
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in unit tests via graceful fallback
    ApiClient = Configuration = UniversalApi = UniversalInfo = None  # type: ignore[assignment]
    VOLC_SDK_IMPORT_ERROR = exc


IMAGE_CASES = [
    {
        "image_path": "/Users/ant/13401615760079295.jpeg",
        "expected_type": "private_chat_screenshot",
        "store_uri_env": "VOLC_IMAGEX_STORE_URI_2",
    },
    {
        "image_path": "/Users/ant/Crushe/32abf758a163e13210f585c7d812a271.jpg",
        "expected_type": "private_chat_screenshot",
        "store_uri_env": "VOLC_IMAGEX_STORE_URI_3",
    },
]


@dataclass
class StageTiming:
    started_at: str
    ended_at: str
    elapsed_seconds: float


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _timed_call_end(start_perf: float, started_at: str) -> StageTiming:
    return StageTiming(
        started_at=started_at,
        ended_at=_now_iso(),
        elapsed_seconds=round(time.perf_counter() - start_perf, 3),
    )


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _median(nums: List[float]) -> float:
    if not nums:
        return 0.0
    return float(statistics.median(nums))


def _p95(nums: List[float]) -> float:
    if not nums:
        return 0.0
    arr = sorted(nums)
    idx = min(len(arr) - 1, max(0, int(round((len(arr) - 1) * 0.95))))
    return float(arr[idx])


def _model_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return normalized or "model"


def _provider_api_key(provider: str) -> str | None:
    if provider == "doubao":
        return os.getenv("DOUBAO_API_KEY")
    return os.getenv("IMAGE_OCR_API_KEY") or os.getenv("IMAGE_TYPE_DETECT_API_KEY")


def _provider_base_url(provider: str) -> str:
    if provider == "doubao":
        return os.getenv("DOUBAO_BASE_URL", DEFAULT_DOUBAO_BASE_URL)
    return os.getenv("IMAGE_OCR_BASE_URL") or os.getenv("IMAGE_TYPE_DETECT_BASE_URL", DEFAULT_BIGMODEL_BASE_URL)


def _is_glm_ocr_model(model_name: str) -> bool:
    normalized = (model_name or "").strip().lower().replace("_", "-")
    return normalized in {"glm-ocr", "glmocr"}


def _candidate_mode(provider: str, model_name: str) -> str:
    if provider == "glm" and _is_glm_ocr_model(model_name):
        return "layout_parsing"
    return "chat_completion"


def _normalize_layout_parsing_url(base_url: str) -> str:
    normalized = (base_url or DEFAULT_BIGMODEL_BASE_URL).rstrip("/")
    if normalized.endswith("/layout_parsing"):
        return normalized
    if normalized.endswith("/chat/completions"):
        return normalized[: -len("/chat/completions")] + "/layout_parsing"
    return normalized + "/layout_parsing"


def _image_data_url(image_path: Path) -> str:
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    suffix = image_path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(suffix, "image/jpeg")
    return f"data:{mime};base64,{encoded}"


def _build_second_node_configs(
    *,
    reference_provider: str,
    reference_model: str,
    candidate_models: List[str],
) -> List[Dict[str, Any]]:
    configs: List[Dict[str, Any]] = []
    seen_signatures: set[tuple[str, str, str]] = set()

    def add_config(*, role: str, provider: str, model: str, label: str, key: str | None = None) -> None:
        resolved_key = key or _model_key(model)
        base_url = _provider_base_url(provider)
        signature = (provider, _candidate_mode(provider, model), model.strip())
        if signature in seen_signatures:
            return
        seen_signatures.add(signature)
        configs.append(
            {
                "key": resolved_key,
                "label": label,
                "role": role,
                "provider": provider,
                "mode": _candidate_mode(provider, model),
                "model": model,
                "api_key": _provider_api_key(provider),
                "base_url": base_url,
            }
        )

    add_config(
        role="reference",
        provider=reference_provider,
        model=reference_model,
        label="reference_model",
        key=f"reference__{_model_key(reference_model)}",
    )
    for model in candidate_models:
        add_config(
            role="candidate",
            provider="glm",
            model=model,
            label=model,
        )
    return configs


def _build_glm_shadow_fallback_order(configs: List[Dict[str, Any]]) -> List[str]:
    return [str(cfg["key"]) for cfg in configs if cfg.get("provider") == "glm" and str(cfg.get("key") or "").strip()]


class VolcImageXOCRClient:
    def __init__(self) -> None:
        if VOLC_SDK_IMPORT_ERROR is not None:
            raise RuntimeError(
                "volcenginesdkcore is required to run OCR shadow validation. "
                "Install the Volcengine SDK before executing this script."
            ) from VOLC_SDK_IMPORT_ERROR
        self.service_id = os.getenv("VOLC_IMAGEX_SERVICE_ID") or os.getenv("VOLC_OCR_SERVICE_ID")
        ak = os.getenv("VOLCENGINE_ACCESS_KEY_ID") or os.getenv("VOLC_OCR_AK") or ""
        sk = os.getenv("VOLCENGINE_SECRET_ACCESS_KEY") or os.getenv("VOLC_OCR_SK") or ""
        self.scene = os.getenv("VOLC_OCR_SCENE", "general")

        cfg = Configuration()
        cfg.ak = ak
        cfg.sk = sk
        cfg.region = "cn-north-1"
        cfg.host = "open.volcengineapi.com"
        self.api = UniversalApi(ApiClient(cfg))

    def get_all_image_services(self) -> Dict[str, Any]:
        info = UniversalInfo(
            method="GET",
            service="imagex",
            version="2018-08-01",
            action="GetAllImageServices",
        )
        return self.api.do_call(info, body={})

    def get_image_ocr_v2(self, store_uri: str, scene: Optional[str] = None) -> Dict[str, Any]:
        info = UniversalInfo(
            method="POST",
            service="imagex",
            version="2018-08-01",
            action="GetImageOCRV2",
            content_type="application/json",
        )
        body = {
            "ServiceId": self.service_id,
            "StoreUri": store_uri,
            "Scene": scene or self.scene,
        }
        return self.api.do_call(info, body=body)


def _load_image_cases(cases_manifest: Optional[Path]) -> List[Dict[str, str]]:
    if not cases_manifest:
        return list(IMAGE_CASES)
    payload = json.loads(cases_manifest.read_text(encoding="utf-8"))
    rows = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("cases manifest must be a list or an object with `cases`")

    image_cases: List[Dict[str, str]] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"cases manifest row #{idx} must be an object")
        image_path = str(row.get("image_path") or "").strip()
        expected_type = str(row.get("expected_type") or "").strip()
        store_uri_env = str(row.get("store_uri_env") or "").strip()
        if not image_path:
            raise ValueError(f"cases manifest row #{idx} missing image_path")
        if not expected_type:
            raise ValueError(f"cases manifest row #{idx} missing expected_type")
        image_cases.append(
            {
                "image_path": image_path,
                "expected_type": expected_type,
                "store_uri_env": store_uri_env,
            }
        )
    return image_cases


async def _call_glm_layout_parsing(
    *,
    image_path: Path,
    screenshot_type: str,
    model: str,
    api_key: str | None,
    base_url: str,
    timeout_seconds: float,
) -> Dict[str, Any]:
    if not api_key:
        return {
            "success": False,
            "text": "",
            "error": "missing_bigmodel_api_key",
            "screenshot_type": screenshot_type,
            "structured_messages": [],
        }

    payload = {
        "model": model,
        "file": _image_data_url(image_path),
        "return_crop_images": False,
        "need_layout_visualization": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    endpoint = _normalize_layout_parsing_url(base_url)
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        return {
            "success": False,
            "text": "",
            "error": str(exc),
            "screenshot_type": screenshot_type,
            "structured_messages": [],
        }

    text = str(body.get("md_results") or "").strip()
    layout_details = body.get("layout_details") or []
    detail_count = 0
    for item in layout_details:
        if isinstance(item, list):
            detail_count += len(item)

    return {
        "success": bool(text),
        "text": text,
        "error": None if text else "glm_ocr_empty_md_results",
        "screenshot_type": screenshot_type,
        "structured_messages": [],
        "layout_details_count": detail_count,
        "usage": body.get("usage"),
        "request_id": body.get("request_id"),
    }


async def run_first_node_route_check(
    processor: ImageProcessor,
    image_cases: List[Dict[str, str]],
    runs_per_image: int = 5,
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for case in image_cases:
        image_path = Path(case["image_path"])
        image_bytes = image_path.read_bytes()
        expected = case["expected_type"]
        for run_idx in range(1, runs_per_image + 1):
            started_at = _now_iso()
            start_perf = time.perf_counter()
            result = await processor.detect_type(image_bytes)
            timing = _timed_call_end(start_perf, started_at)
            row = {
                "image": str(image_path),
                "run": run_idx,
                "elapsed_seconds": timing.elapsed_seconds,
                "success": bool(result.get("success")),
                "screenshot_type": result.get("screenshot_type"),
                "confidence": result.get("confidence"),
                "reason": result.get("reason"),
                "error": result.get("error"),
                "model": processor.type_detect_model,
                "base_url": processor.type_detect_base_url,
                "expected_type": expected,
                "route_correct": result.get("screenshot_type") == expected,
                "timestamp": timing.ended_at,
            }
            rows.append(row)

    route_errors = [r for r in rows if not r["route_correct"] or not r["success"]]
    return {
        "generated_at": _now_iso(),
        "runs_per_image": runs_per_image,
        "rows": rows,
        "summary": {
            "total_runs": len(rows),
            "error_count": len(route_errors),
            "all_correct": len(route_errors) == 0,
        },
    }


async def _probe_doubao_model(
    processor: ImageProcessor,
    probe_bytes: bytes,
    screenshot_type: str,
    requested_model: str = DEFAULT_REFERENCE_MODEL,
) -> Dict[str, Any]:
    candidates = []
    for candidate in [
        requested_model,
        "Doubao-Seed-1.6-flash",
        "doubao-seed-1-6-flash",
        "doubao-seed-1-6-flash-250828",
        "doubao-seed-1-6-flash-250715",
    ]:
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    old = (
        processor.ocr_model,
        processor.ocr_api_key,
        processor.ocr_base_url,
    )
    out: Dict[str, Any] = {
        "requested": requested_model,
        "selected": None,
        "probe_success": False,
        "probe_error": None,
        "candidates": candidates,
        "details": [],
    }
    try:
        processor.ocr_api_key = os.getenv("DOUBAO_API_KEY")
        processor.ocr_base_url = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        for m in candidates:
            processor.ocr_model = m
            started_at = _now_iso()
            start_perf = time.perf_counter()
            res = await processor.process_image(
                image_bytes=probe_bytes,
                screenshot_type=screenshot_type,
                additional_context="模型探测，忽略内容",
            )
            timing = _timed_call_end(start_perf, started_at)
            detail = {
                "model": m,
                "success": bool(res.get("success")),
                "error": res.get("error"),
                "elapsed_seconds": timing.elapsed_seconds,
            }
            out["details"].append(detail)
            if res.get("success"):
                out["selected"] = m
                out["probe_success"] = True
                break
        if not out["probe_success"]:
            out["probe_error"] = "no available doubao model candidate"
    finally:
        processor.ocr_model, processor.ocr_api_key, processor.ocr_base_url = old
    return out


async def run_second_node_ab(
    processor: ImageProcessor,
    image_cases: List[Dict[str, str]],
    *,
    reference_provider: str = DEFAULT_REFERENCE_PROVIDER,
    reference_model: str = DEFAULT_REFERENCE_MODEL,
    candidate_models: Optional[List[str]] = None,
) -> Dict[str, Any]:
    candidate_models = candidate_models or list(DEFAULT_GLM_CANDIDATE_MODELS)
    probe_case = image_cases[1] if len(image_cases) > 1 else image_cases[0]
    probe_img = Path(probe_case["image_path"]).read_bytes()
    if reference_provider == "doubao":
        probe = await _probe_doubao_model(
            processor,
            probe_img,
            "private_chat_screenshot",
            requested_model=reference_model,
        )
        resolved_reference_model = probe["selected"] or reference_model
    else:
        probe = {
            "requested": reference_model,
            "selected": reference_model,
            "probe_success": True,
            "probe_error": None,
            "candidates": [reference_model],
            "details": [],
        }
        resolved_reference_model = reference_model

    second_configs = _build_second_node_configs(
        reference_provider=reference_provider,
        reference_model=resolved_reference_model,
        candidate_models=candidate_models,
    )

    results: List[Dict[str, Any]] = []
    for case in image_cases:
        image_path = Path(case["image_path"])
        image_bytes = image_path.read_bytes()
        image_result: Dict[str, Any] = {
            "image_path": str(image_path),
            "file_size_bytes": image_path.stat().st_size,
        }

        detect_started = _now_iso()
        detect_start_perf = time.perf_counter()
        detect_result = await processor.detect_type(image_bytes)
        detect_timing = _timed_call_end(detect_start_perf, detect_started)
        screenshot_type = detect_result.get("screenshot_type") or "universal_screenshot_analysis"
        image_result["first_node"] = {
            "model": processor.type_detect_model,
            "base_url": processor.type_detect_base_url,
            "thinking_disabled": bool(processor.disable_reasoning_output),
            "result": detect_result,
            "timing": detect_timing.__dict__,
        }

        second_node = {}
        old = (processor.ocr_model, processor.ocr_api_key, processor.ocr_base_url)
        try:
            for cfg in second_configs:
                started_at = _now_iso()
                start_perf = time.perf_counter()
                if cfg["mode"] == "layout_parsing":
                    res = await _call_glm_layout_parsing(
                        image_path=image_path,
                        screenshot_type=screenshot_type,
                        model=cfg["model"],
                        api_key=cfg["api_key"],
                        base_url=cfg["base_url"],
                        timeout_seconds=processor.timeout_seconds,
                    )
                else:
                    processor.ocr_model = cfg["model"]
                    processor.ocr_api_key = cfg["api_key"]
                    processor.ocr_base_url = cfg["base_url"]
                    res = await processor.process_image(
                        image_bytes=image_bytes,
                        screenshot_type=screenshot_type,
                        additional_context=None,
                    )
                timing = _timed_call_end(start_perf, started_at)
                second_node[cfg["key"]] = {
                    "key": cfg["key"],
                    "label": cfg["label"],
                    "role": cfg["role"],
                    "provider": cfg["provider"],
                    "mode": cfg["mode"],
                    "model": cfg["model"],
                    "base_url": cfg["base_url"],
                    "thinking_disabled": bool(processor.disable_reasoning_output),
                    "result": res,
                    "timing": timing.__dict__,
                    "total_elapsed_seconds": round(
                        detect_timing.elapsed_seconds + timing.elapsed_seconds,
                        3,
                    ),
                    "final_timestamp": timing.ended_at,
                }
        finally:
            processor.ocr_model, processor.ocr_api_key, processor.ocr_base_url = old

        image_result["second_node"] = second_node
        results.append(image_result)

    return {
        "generated_at": _now_iso(),
        "notes": {
            "first_node_fixed": f"{processor.type_detect_model} detect_type",
            "reference_model_requested": reference_model,
            "reference_model_selected": resolved_reference_model,
            "reference_provider": reference_provider,
            "reference_key": second_configs[0]["key"],
            "second_node_variable": [cfg["key"] for cfg in second_configs],
            "second_node_configs": [
                {
                    "key": cfg["key"],
                    "label": cfg["label"],
                    "role": cfg["role"],
                    "provider": cfg["provider"],
                    "mode": cfg["mode"],
                    "model": cfg["model"],
                    "base_url": cfg["base_url"],
                }
                for cfg in second_configs
            ],
            "glm_candidate_sequence": [cfg["model"] for cfg in second_configs if cfg["role"] == "candidate"],
            "reasoning_disabled_for_both": True,
            "max_tokens_unchanged": True,
            "ocr_max_tokens": processor.ocr_max_tokens,
            "ocr_max_edge": processor.ocr_max_edge,
            "reference_probe": probe,
            "candidate_order": [cfg["key"] for cfg in second_configs if cfg["role"] == "candidate"],
            "glm_shadow_fallback_order": _build_glm_shadow_fallback_order(second_configs),
        },
        "results": results,
    }


async def _postprocess_with_small_model(
    processor: ImageProcessor,
    screenshot_type: str,
    lines: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not lines:
        return {"success": False, "text": "", "error": "empty_ocr_lines"}

    joined = "\n".join([f"- {x['content']}" for x in lines[:180]])
    prompt = (
        "你是OCR文本整理助手。请只做去噪和格式整理，不补充不存在信息，不推断意图。"
        "若是表情包/图片，仅保留客观描述。输出中文、简洁、可读。\n\n"
        f"截图类型: {screenshot_type}\n"
        "原始OCR行:\n"
        f"{joined}"
    )
    payload = {
        "model": os.getenv("IMAGE_TYPE_DETECT_MODEL", "GLM-4.6V-FlashX"),
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "max_tokens": min(1200, processor.ocr_max_tokens),
        "temperature": 0,
    }
    try:
        res = await processor._post_chat_completion(  # pylint: disable=protected-access
            processor._apply_generation_controls(payload),  # pylint: disable=protected-access
            api_key=os.getenv("IMAGE_TYPE_DETECT_API_KEY"),
            base_url=os.getenv("IMAGE_TYPE_DETECT_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        )
        choices = res.get("choices") or []
        text = ""
        if choices and isinstance(choices[0], dict):
            text = (choices[0].get("message") or {}).get("content") or ""
        if not isinstance(text, str):
            text = str(text)
        return {"success": True, "text": text.strip(), "error": None}
    except Exception as e:
        return {"success": False, "text": "", "error": str(e)}


async def run_ocr_shadow_pipeline(
    processor: ImageProcessor,
    image_cases: List[Dict[str, str]],
    ab_result: Dict[str, Any],
    *,
    fallback_candidate_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    client = VolcImageXOCRClient()
    low_conf_threshold = _safe_float(os.getenv("IMAGE_OCR_LOW_CONFIDENCE_THRESHOLD", "0.72"), 0.72)
    parse_error_threshold = _safe_float(os.getenv("IMAGE_OCR_PARSE_ERROR_THRESHOLD", "0.30"), 0.30)
    fallback_enabled = os.getenv("IMAGE_OCR_FALLBACK_ENABLED", "true").lower() == "true"
    postprocess_enabled = os.getenv("IMAGE_OCR_TEXT_POSTPROCESS_ENABLED", "true").lower() == "true"
    postprocess_only_low = os.getenv("IMAGE_OCR_TEXT_POSTPROCESS_ONLY_ON_LOW_CONF", "true").lower() == "true"
    second_node_configs = ab_result.get("notes", {}).get("second_node_configs", [])
    fallback_candidate_keys = fallback_candidate_keys or list(
        ab_result.get("notes", {}).get("glm_shadow_fallback_order") or []
    )

    service_check = {"success": False, "error": None, "services_count": 0}
    try:
        all_services = client.get_all_image_services()
        service_check["success"] = True
        service_check["services_count"] = len(all_services.get("Services") or [])
    except Exception as e:
        service_check["error"] = str(e)

    vlm_fallback_map: Dict[str, Dict[str, Any]] = {}
    for row in ab_result.get("results", []):
        image_path = row["image_path"]
        candidate_result_map: Dict[str, Dict[str, Any]] = {}
        for cfg in second_node_configs:
            key = str(cfg.get("key") or "").strip()
            if not key:
                continue
            candidate_result_map[key] = row["second_node"].get(key) or {}
        vlm_fallback_map[image_path] = candidate_result_map

    results = []
    for case in image_cases:
        image_path = Path(case["image_path"])
        image_bytes = image_path.read_bytes()
        store_uri = os.getenv(case["store_uri_env"], "")
        image_width, image_height = 0, 0
        try:
            with Image.open(BytesIO(image_bytes)) as im:
                image_width, image_height = im.size
        except Exception:
            image_width, image_height = 0, 0

        total_start = time.perf_counter()
        started_total_at = _now_iso()

        # detect
        t0 = time.perf_counter()
        detect = await processor.detect_type(image_bytes)
        detect_ms = round((time.perf_counter() - t0) * 1000, 1)
        screenshot_type = detect.get("screenshot_type") or "universal_screenshot_analysis"

        # ocr
        t1 = time.perf_counter()
        ocr_resp: Dict[str, Any] = {}
        ocr_error = None
        if store_uri:
            for attempt in range(1, 4):
                try:
                    ocr_resp = client.get_image_ocr_v2(store_uri=store_uri, scene="general")
                    ocr_error = None
                    break
                except Exception as e:
                    ocr_error = str(getattr(e, "reason", e))
                    if attempt < 3:
                        await asyncio.sleep(0.25 * attempt)
        else:
            ocr_error = "store_uri_missing"
        ocr_ms = round((time.perf_counter() - t1) * 1000, 1)

        # normalize + assemble
        t2 = time.perf_counter()
        normalized = normalize_general_ocr_lines(ocr_resp) if not ocr_error else {
            "lines": [],
            "raw_count": 0,
            "filtered_count": 0,
            "noise_count": 0,
            "parse_error_rate": 1.0,
        }
        lines = normalized["lines"]
        avg_conf = average_confidence(lines)
        parse_error_rate = float(normalized["parse_error_rate"])
        assembled_pack = assemble_ocr_text(
            screenshot_type=screenshot_type,
            lines=lines,
            image_width=image_width,
            image_height=image_height,
        )
        assembled = str(assembled_pack.get("text") or "")
        structured_messages = assembled_pack.get("structured_messages") or []
        assembled_item_count = int(assembled_pack.get("item_count") or 0)
        assemble_ms = round((time.perf_counter() - t2) * 1000, 1)

        # small model postprocess (low-confidence only by default)
        t3 = time.perf_counter()
        min_items = 4 if screenshot_type in ("private_chat_screenshot", "group_chat_screenshot") else 3
        low_conf = (
            avg_conf < low_conf_threshold
            or parse_error_rate > parse_error_threshold
            or assembled_item_count < min_items
        )
        postprocess_applied = False
        postprocess_res = {"success": False, "text": "", "error": None}
        if postprocess_enabled and (low_conf if postprocess_only_low else True):
            postprocess_applied = True
            postprocess_res = await _postprocess_with_small_model(
                processor=processor,
                screenshot_type=screenshot_type,
                lines=lines,
            )
            if postprocess_res.get("success") and postprocess_res.get("text"):
                assembled = postprocess_res["text"]
        post_ms = round((time.perf_counter() - t3) * 1000, 1)

        # fallback
        t4 = time.perf_counter()
        fallback_reason = None
        extraction_source = "ocr_pipeline"
        final_text = assembled
        final_structured_messages = structured_messages
        fallback_model_key = None
        fallback_model = None
        if ocr_error:
            fallback_reason = "ocr_api_error"
        elif low_conf:
            fallback_reason = "low_confidence"
        elif not assembled.strip():
            fallback_reason = "empty_assembled_text"

        if fallback_enabled and fallback_reason is not None:
            image_candidates = vlm_fallback_map.get(str(image_path), {})
            for key in fallback_candidate_keys:
                node = image_candidates.get(key) or {}
                result = node.get("result") or {}
                text = str(result.get("text") or "").strip()
                if text:
                    extraction_source = "vlm_fallback"
                    final_text = text
                    final_structured_messages = []
                    fallback_model_key = key
                    fallback_model = node.get("model")
                    break

        fallback_ms = round((time.perf_counter() - t4) * 1000, 1)
        total_ms = round((time.perf_counter() - total_start) * 1000, 1)

        results.append(
            {
                "image_path": str(image_path),
                "store_uri": store_uri,
                "first_node": detect,
                "ocr": {
                    "error": ocr_error,
                    "raw_line_count": normalized.get("raw_count", 0),
                    "line_count": len(lines),
                    "assembled_item_count": assembled_item_count,
                    "noise_count": normalized.get("noise_count", 0),
                    "ocr_confidence": avg_conf,
                    "parse_error_rate": parse_error_rate,
                },
                "postprocess": {
                    "applied": postprocess_applied,
                    "success": postprocess_res.get("success"),
                    "error": postprocess_res.get("error"),
                },
                "result": {
                    "success": True,
                    "text": final_text,
                    "screenshot_type": screenshot_type,
                    "error": None,
                    "extraction_source": extraction_source,
                    "fallback_reason": fallback_reason,
                    "fallback_model_key": fallback_model_key,
                    "fallback_model": fallback_model,
                    "ocr_confidence": avg_conf,
                    "structured_messages": final_structured_messages,
                    "pipeline_timing": {
                        "started_at": started_total_at,
                        "ended_at": _now_iso(),
                        "detect_ms": detect_ms,
                        "ocr_ms": ocr_ms,
                        "assemble_ms": assemble_ms,
                        "postprocess_ms": post_ms,
                        "fallback_ms": fallback_ms,
                        "total_ms": total_ms,
                    },
                },
            }
        )

    return {
        "generated_at": _now_iso(),
        "notes": {
            "ocr_provider": "volc_veImageX_GetImageOCRV2",
            "service_id": client.service_id,
            "service_check": service_check,
            "low_conf_threshold": low_conf_threshold,
            "parse_error_threshold": parse_error_threshold,
            "fallback_enabled": fallback_enabled,
            "postprocess_enabled": postprocess_enabled,
            "postprocess_only_low_conf": postprocess_only_low,
            "vlm_fallback_candidate_order": fallback_candidate_keys,
        },
        "results": results,
    }


def build_human_scores(
    ab_result: Dict[str, Any],
    shadow_result: Dict[str, Any],
) -> Dict[str, Any]:
    score_rows = []
    second_node_configs = ab_result.get("notes", {}).get("second_node_configs", [])
    for image_row in ab_result.get("results", []):
        image_path = image_row["image_path"]
        shadow_item = next((x for x in shadow_result.get("results", []) if x["image_path"] == image_path), None)
        shadow_text = ((shadow_item or {}).get("result", {}) or {}).get("text", "")

        def quick_quality(t: str) -> Dict[str, Any]:
            has_text = bool(t.strip())
            length = len(t.strip())
            recall = 5 if length > 700 else 4 if length > 250 else 3 if length > 80 else 2 if length > 10 else 1
            accuracy = 4 if has_text else 1
            missed = length < 120
            emoji_semantic_overreach = ("心疼" in t and "😂" in t) or ("推断" in t)
            return {
                "recall_score_1_to_5": recall,
                "accuracy_score_1_to_5": accuracy,
                "missed_text_risk": missed,
                "emoji_semantic_misread_risk": bool(emoji_semantic_overreach),
            }

        model_scores: Dict[str, Any] = {}
        for cfg in second_node_configs:
            key = str(cfg.get("key") or "").strip()
            if not key:
                continue
            text = str((image_row["second_node"].get(key) or {}).get("result", {}).get("text") or "")
            model_scores[key] = {
                "label": cfg.get("label") or key,
                "model": cfg.get("model") or key,
                "provider": cfg.get("provider"),
                **quick_quality(text),
            }
        model_scores["ocr_shadow"] = {
            "label": "ocr_shadow",
            "model": "ocr_shadow",
            "provider": "ocr",
            **quick_quality(shadow_text),
        }
        score_rows.append(
            {
                "image_path": image_path,
                "model_scores": model_scores,
            }
        )

    return {
        "generated_at": _now_iso(),
        "second_node_order": [cfg.get("key") for cfg in second_node_configs if cfg.get("key")] + ["ocr_shadow"],
        "scores": score_rows,
    }


def render_first_node_md(data: Dict[str, Any]) -> str:
    lines = [
        f"# 第一节点路由稳定性复测（每图 {data['runs_per_image']} 次）",
        "",
        f"- 生成时间: {data['generated_at']}",
        f"- 总运行: {data['summary']['total_runs']}",
        f"- 路由错误数: {data['summary']['error_count']}",
        f"- 结论: {'无路由错误' if data['summary']['all_correct'] else '存在路由错误'}",
        "",
    ]
    for row in data["rows"]:
        lines += [
            f"## {row['image']} / run={row['run']}",
            f"- expected: `{row['expected_type']}`",
            f"- got: `{row['screenshot_type']}`",
            f"- success: `{row['success']}`",
            f"- route_correct: `{row['route_correct']}`",
            f"- confidence: `{row['confidence']}`",
            f"- elapsed_seconds: `{row['elapsed_seconds']}`",
            f"- timestamp: `{row['timestamp']}`",
            "",
        ]
    return "\n".join(lines)


def render_ab_md(ab: Dict[str, Any], scores: Dict[str, Any]) -> str:
    second_node_configs = ab["notes"].get("second_node_configs", [])
    lines = [
        "# 图片识别第二节点候选矩阵（参考模型 + GLM 候选序列）",
        "",
        f"- 报告生成时间: {ab['generated_at']}",
        f"- 第一节点固定: {ab['notes']['first_node_fixed']}",
        f"- 参考模型: `{ab['notes']['reference_model_selected']}`",
        f"- 参考提供方: `{ab['notes']['reference_provider']}`",
        f"- GLM 候选顺序: {', '.join(ab['notes'].get('glm_candidate_sequence') or [])}",
        f"- 思考模式: {'关闭' if ab['notes']['reasoning_disabled_for_both'] else '开启'}",
        f"- max_tokens 维持现状: `{ab['notes']['ocr_max_tokens']}`",
        f"- 超大图缩图阈值: `{ab['notes']['ocr_max_edge']}`",
        "",
        "## 第二节点配置",
        "",
    ]
    if ab["notes"]["reference_provider"] == "doubao":
        lines += [
            f"- 参考探测请求模型: `{ab['notes']['reference_probe'].get('requested')}`",
            f"- 参考探测实际模型: `{ab['notes']['reference_probe'].get('selected')}`",
            "",
        ]
    for cfg in second_node_configs:
        lines.append(
            f"- `{cfg['key']}`: role=`{cfg['role']}`, provider=`{cfg['provider']}`, "
            f"mode=`{cfg.get('mode')}`, model=`{cfg['model']}`"
        )
    lines.append("")
    for idx, row in enumerate(ab["results"], start=1):
        lines += [
            f"## 图片 {idx}",
            f"- 路径: `{row['image_path']}`",
            f"- 大小: `{row['file_size_bytes']} bytes`",
            "### 第一节点",
            f"- 模型: `{row['first_node']['model']}`",
            f"- screenshot_type: `{row['first_node']['result'].get('screenshot_type')}`",
            f"- confidence: `{row['first_node']['result'].get('confidence')}`",
            f"- started_at: `{row['first_node']['timing']['started_at']}`",
            f"- ended_at: `{row['first_node']['timing']['ended_at']}`",
            f"- elapsed_seconds: `{row['first_node']['timing']['elapsed_seconds']}`",
            "",
        ]
        for cfg in second_node_configs:
            key = cfg["key"]
            node = row["second_node"].get(key)
            if not node:
                continue
            lines += [
                f"### 第二节点: {key}",
                f"- 角色: `{node['role']}`",
                f"- provider/mode: `{node['provider']}` / `{node.get('mode')}`",
                f"- 模型: `{node['model']}`",
                f"- success: `{node['result'].get('success')}`",
                f"- error: `{node['result'].get('error')}`",
                f"- started_at: `{node['timing']['started_at']}`",
                f"- ended_at: `{node['timing']['ended_at']}`",
                f"- elapsed_seconds: `{node['timing']['elapsed_seconds']}`",
                f"- total_elapsed_seconds(type+second): `{node['total_elapsed_seconds']}`",
                f"- final_timestamp: `{node['final_timestamp']}`",
                "- 原始输出:",
                "```text",
                str(node["result"].get("text") or ""),
                "```",
                "",
            ]

    lines += [
        "## 人工可读评分（快速）",
        "",
        "- 评分维度: 召回率、准确率、是否漏字、是否误识别表情包语义",
        "",
    ]
    for row in scores["scores"]:
        lines += [f"### `{row['image_path']}`"]
        for key in scores.get("second_node_order", []):
            v = (row.get("model_scores") or {}).get(key)
            if not v:
                continue
            lines += [
                f"- {v['label']}: recall={v['recall_score_1_to_5']}, accuracy={v['accuracy_score_1_to_5']}, "
                f"missed_text_risk={v['missed_text_risk']}, emoji_semantic_misread_risk={v['emoji_semantic_misread_risk']}",
            ]
        lines.append("")

    return "\n".join(lines)


def render_shadow_md(data: Dict[str, Any]) -> str:
    lines = [
        "# OCR + 小模型整理 快速影子实验（三图）",
        "",
        f"- 生成时间: {data['generated_at']}",
        f"- OCR Provider: {data['notes']['ocr_provider']}",
        f"- ServiceId: `{data['notes']['service_id']}`",
        f"- 服务检查: success=`{data['notes']['service_check']['success']}`, services_count=`{data['notes']['service_check']['services_count']}`",
        f"- 低置信阈值: `{data['notes']['low_conf_threshold']}`",
        f"- 解析错误阈值: `{data['notes']['parse_error_threshold']}`",
        f"- 回退开关: `{data['notes']['fallback_enabled']}`",
        f"- VLM 回退候选顺序: {', '.join(data['notes'].get('vlm_fallback_candidate_order') or [])}",
        "",
    ]
    for idx, row in enumerate(data["results"], start=1):
        result = row["result"]
        timing = result["pipeline_timing"]
        lines += [
            f"## 图片{idx}",
            f"- 路径: `{row['image_path']}`",
            f"- StoreUri: `{row['store_uri']}`",
            f"- 第一节点类型: `{row['first_node'].get('screenshot_type')}`",
            f"- OCR raw_line_count: `{row['ocr'].get('raw_line_count')}`",
            f"- OCR line_count: `{row['ocr']['line_count']}`",
            f"- assembled_item_count: `{row['ocr'].get('assembled_item_count')}`",
            f"- noise_count: `{row['ocr'].get('noise_count')}`",
            f"- ocr_confidence: `{row['ocr']['ocr_confidence']}`",
            f"- parse_error_rate: `{row['ocr']['parse_error_rate']}`",
            f"- 来源: `{result['extraction_source']}`",
            f"- 回退原因: `{result['fallback_reason']}`",
            f"- 回退模型: `{result.get('fallback_model_key')}` / `{result.get('fallback_model')}`",
            f"- structured_messages_count: `{len(result.get('structured_messages') or [])}`",
            f"- 后处理触发: `{row['postprocess']['applied']}` / success=`{row['postprocess']['success']}` / error=`{row['postprocess']['error']}`",
            f"- 耗时(ms): detect={timing['detect_ms']}, ocr={timing['ocr_ms']}, assemble={timing['assemble_ms']}, post={timing['postprocess_ms']}, fallback={timing['fallback_ms']}, total={timing['total_ms']}",
            "- 输出内容:",
            "```text",
            str(result["text"]),
            "```",
            "- structured_messages 预览:",
            "```json",
            json.dumps((result.get("structured_messages") or [])[:8], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    return "\n".join(lines)


def build_handoff_md(
    route_json: Path,
    route_md: Path,
    ab_json: Path,
    ab_md: Path,
    shadow_json: Path,
    shadow_md: Path,
    scores_json: Path,
    ocr_opened: bool,
) -> str:
    block_status = "已解除（GetImageOCRV2 可用）" if ocr_opened else "仍阻塞（组件未开通）"
    todo_lines = [
        "1. 先用 fixed small set 跑 prompt-first 候选，只让通过小集门槛的版本进入完整私聊严格评估。",
        "2. 若 prompt 两轮无显著提升，直接复用这份脚本验证 GLM 候选顺序：GLM-4.6V-FlashX -> GLM-OCR。",
        "3. 将通过时延预算且质量更优的候选接入真实 API shadow，保留 Markdown 输出契约不变。",
        "4. 增加更贴近聊天截图的 shadow 验证样本，并补充 fallback 触发与后处理相关单测。",
        "5. 安全动作：轮换已暴露的 AK/SK，并仅保留新密钥在安全存储。",
    ]
    return "\n".join(
        [
            "# 聊天截图 OCR / VLM 兜底交接说明",
            "",
            "## 背景",
            "- 目标：在 prompt-first 优化不足时，用固定顺序的 GLM 候选做第二节点兜底验证，同时保留 OCR 主通道 + 低置信回退。",
            "- 第一节点 detect_type 保持不变。",
            "",
            "## 当前状态",
            f"- veImageX OCR 阻塞状态：{block_status}",
            "- 已完成新一轮首节点复测、二节点 A/B、OCR+小模型整理影子实验，并落盘。",
            "",
            "## 已完成项（本轮）",
            f"- 第一节点复测 JSON: `{route_json}`",
            f"- 第一节点复测 MD: `{route_md}`",
            f"- 二节点 A/B JSON: `{ab_json}`",
            f"- 二节点 A/B MD: `{ab_md}`",
            f"- OCR 影子实验 JSON: `{shadow_json}`",
            f"- OCR 影子实验 MD: `{shadow_md}`",
            f"- 人工可读评分 JSON: `{scores_json}`",
            "",
            "## 阻塞项",
            "- 无 `611000` 组件阻塞（若后续账号切换再次出现，按附加组件开通流程处理）。",
            "",
            "## 下一步 TODO",
            *todo_lines,
            "",
            "## 最小复验命令（开通后）",
            "```bash",
            "python3 /Users/ant/Crushe/模型策略/agent_impl/scripts/run_ocr_pipeline_validation.py",
            "```",
        ]
    )


def _default_reference_model(provider: str) -> str:
    if provider == "doubao":
        return os.getenv("DOUBAO_ENDPOINT_ID") or DEFAULT_DOUBAO_REFERENCE_MODEL
    return os.getenv("IMAGE_OCR_MODEL") or os.getenv("IMAGE_TYPE_DETECT_MODEL") or DEFAULT_REFERENCE_MODEL


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-per-image", type=int, default=5)
    parser.add_argument(
        "--cases-manifest",
        default="",
        help="Optional JSON manifest with `cases` to override the built-in sample images.",
    )
    parser.add_argument(
        "--reference-provider",
        choices=["doubao", "glm"],
        default=os.getenv("IMAGE_VALIDATION_REFERENCE_PROVIDER", DEFAULT_REFERENCE_PROVIDER),
    )
    parser.add_argument(
        "--reference-model",
        default=os.getenv("IMAGE_VALIDATION_REFERENCE_MODEL", ""),
        help="Defaults to the currently configured OCR model for the chosen provider.",
    )
    parser.add_argument(
        "--candidate-model",
        action="append",
        dest="candidate_models",
        default=None,
        help="Repeatable. Defaults to GLM-4.6V-FlashX, GLM-OCR.",
    )
    parser.add_argument(
        "--shadow-fallback-key",
        action="append",
        dest="shadow_fallback_keys",
        default=None,
        help="Repeatable fallback key order. Defaults to the candidate order.",
    )
    parser.add_argument(
        "--output-tag",
        default="glm_fallback_validation",
        help="Tag appended to output filenames.",
    )
    return parser.parse_args(argv or sys.argv[1:])


async def main(args: argparse.Namespace) -> None:
    load_dotenv(REPO_ROOT / ".env")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate_models = args.candidate_models or list(DEFAULT_GLM_CANDIDATE_MODELS)
    image_cases = _load_image_cases(Path(args.cases_manifest)) if args.cases_manifest else list(IMAGE_CASES)
    reference_model = (args.reference_model or _default_reference_model(args.reference_provider)).strip()
    output_tag = _model_key(args.output_tag)

    processor = ImageProcessor()
    processor.disable_reasoning_output = True

    route_data = await run_first_node_route_check(processor, image_cases, runs_per_image=args.runs_per_image)
    route_json = OUTPUT_DIR / f"first_node_route_check_{ts}_{args.runs_per_image}runs.json"
    route_md = OUTPUT_DIR / f"first_node_route_check_{ts}_{args.runs_per_image}runs.md"
    _write_json(route_json, route_data)
    route_md.write_text(render_first_node_md(route_data), encoding="utf-8")

    ab_data = await run_second_node_ab(
        processor,
        image_cases,
        reference_provider=args.reference_provider,
        reference_model=reference_model,
        candidate_models=candidate_models,
    )
    ab_json = OUTPUT_DIR / f"image_model_ab_compare_{output_tag}_{ts}.json"
    ab_md = OUTPUT_DIR / f"image_model_ab_compare_{output_tag}_{ts}.md"
    _write_json(ab_json, ab_data)

    shadow_data = await run_ocr_shadow_pipeline(
        processor,
        image_cases,
        ab_data,
        fallback_candidate_keys=args.shadow_fallback_keys,
    )
    scores_data = build_human_scores(ab_data, shadow_data)
    scores_json = OUTPUT_DIR / f"image_human_score_compare_{ts}.json"
    _write_json(scores_json, scores_data)

    ab_md.write_text(render_ab_md(ab_data, scores_data), encoding="utf-8")

    shadow_json = OUTPUT_DIR / f"ocr_shadow_quick_test_{output_tag}_{ts}.json"
    shadow_md = OUTPUT_DIR / f"ocr_shadow_quick_test_{output_tag}_{ts}.md"
    _write_json(shadow_json, shadow_data)
    shadow_md.write_text(render_shadow_md(shadow_data), encoding="utf-8")

    ocr_opened = True
    for row in shadow_data.get("results", []):
        if row.get("ocr", {}).get("error"):
            ocr_opened = False
            break

    handoff_md = OUTPUT_DIR / f"handoff_ocr_pipeline_{ts}.md"
    handoff_md.write_text(
        build_handoff_md(
            route_json=route_json,
            route_md=route_md,
            ab_json=ab_json,
            ab_md=ab_md,
            shadow_json=shadow_json,
            shadow_md=shadow_md,
            scores_json=scores_json,
            ocr_opened=ocr_opened,
        ),
        encoding="utf-8",
    )

    print("DONE")
    print(f"route_json={route_json}")
    print(f"route_md={route_md}")
    print(f"ab_json={ab_json}")
    print(f"ab_md={ab_md}")
    print(f"shadow_json={shadow_json}")
    print(f"shadow_md={shadow_md}")
    print(f"scores_json={scores_json}")
    print(f"handoff_md={handoff_md}")

    # Quick latency summary for convenience
    second_node_latency_summary: Dict[str, Any] = {}
    shadow_times = []
    for cfg in ab_data["notes"].get("second_node_configs", []):
        key = cfg["key"]
        times = [
            row["second_node"][key]["total_elapsed_seconds"]
            for row in ab_data["results"]
            if key in row.get("second_node", {})
        ]
        second_node_latency_summary[key] = {
            "model": cfg["model"],
            "provider": cfg["provider"],
            "role": cfg["role"],
            "mode": cfg.get("mode"),
            "p50": round(_median(times), 3),
            "p95": round(_p95(times), 3),
        }
    for row in shadow_data["results"]:
        shadow_times.append(row["result"]["pipeline_timing"]["total_ms"] / 1000.0)
    second_node_latency_summary["ocr_shadow_pipeline"] = {
        "model": "ocr_shadow",
        "provider": "ocr",
        "role": "shadow",
        "p50": round(_median(shadow_times), 3),
        "p95": round(_p95(shadow_times), 3),
    }

    print(
        "latency_summary="
        + json.dumps(
            second_node_latency_summary,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
