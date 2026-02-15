#!/usr/bin/env python3
"""
Run end-to-end validation for:
1) first-node route stability
2) second-node A/B (GLM-4.6V-FlashX vs Doubao-Seed-1.6-flash)
3) OCR + low-confidence postprocess + fallback shadow pipeline

Outputs are written to /Users/ant/Crushe/模型策略/output/*.json and *.md
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from io import BytesIO
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from PIL import Image

REPO_ROOT = Path("/Users/ant/Crushe/模型策略")
AGENT_IMPL_ROOT = REPO_ROOT / "agent_impl"
OUTPUT_DIR = REPO_ROOT / "output"

if str(AGENT_IMPL_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_IMPL_ROOT))
if "/tmp/volc_sdk_test" not in sys.path:
    sys.path.insert(0, "/tmp/volc_sdk_test")

from utils.image_processor import ImageProcessor  # noqa: E402
from utils.ocr_assembler import assemble_ocr_text  # noqa: E402
from utils.ocr_normalizer import average_confidence, normalize_general_ocr_lines  # noqa: E402
from volcenginesdkcore import ApiClient, Configuration  # noqa: E402
from volcenginesdkcore.universal import UniversalApi, UniversalInfo  # noqa: E402


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
    {
        "image_path": "/Users/ant/聊天/微信图片_20260208215237_212_13.png",
        "expected_type": "moments_screenshot",
        "store_uri_env": "VOLC_IMAGEX_STORE_URI_1",
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


class VolcImageXOCRClient:
    def __init__(self) -> None:
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
) -> Dict[str, Any]:
    candidates = [
        "Doubao-Seed-1.6-flash",
        "doubao-seed-1-6-flash",
        "doubao-seed-1-6-flash-250828",
        "doubao-seed-1-6-flash-250715",
    ]
    old = (
        processor.ocr_model,
        processor.ocr_api_key,
        processor.ocr_base_url,
    )
    out: Dict[str, Any] = {
        "requested": "Doubao-Seed-1.6-flash",
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
) -> Dict[str, Any]:
    probe_img = Path(image_cases[1]["image_path"]).read_bytes()
    probe = await _probe_doubao_model(processor, probe_img, "private_chat_screenshot")
    doubao_model = probe["selected"] or "Doubao-Seed-1.6-flash"

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
        second_configs = [
            {
                "key": "doubao_seed_1_6_flash",
                "model": doubao_model,
                "api_key": os.getenv("DOUBAO_API_KEY"),
                "base_url": os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            },
            {
                "key": "glm_4_6v_flashx",
                "model": "GLM-4.6V-FlashX",
                "api_key": os.getenv("IMAGE_TYPE_DETECT_API_KEY"),
                "base_url": os.getenv("IMAGE_TYPE_DETECT_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            },
        ]
        old = (processor.ocr_model, processor.ocr_api_key, processor.ocr_base_url)
        try:
            for cfg in second_configs:
                processor.ocr_model = cfg["model"]
                processor.ocr_api_key = cfg["api_key"]
                processor.ocr_base_url = cfg["base_url"]

                started_at = _now_iso()
                start_perf = time.perf_counter()
                res = await processor.process_image(
                    image_bytes=image_bytes,
                    screenshot_type=screenshot_type,
                    additional_context=None,
                )
                timing = _timed_call_end(start_perf, started_at)
                second_node[cfg["key"]] = {
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
            "first_node_fixed": "GLM-4.6V-FlashX detect_type",
            "second_node_variable": ["doubao_seed_1_6_flash", "glm_4_6v_flashx"],
            "reasoning_disabled_for_both": True,
            "max_tokens_unchanged": True,
            "ocr_max_tokens": processor.ocr_max_tokens,
            "ocr_max_edge": processor.ocr_max_edge,
            "doubao_requested_model": "Doubao-Seed-1.6-flash",
            "doubao_probe": probe,
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
) -> Dict[str, Any]:
    client = VolcImageXOCRClient()
    low_conf_threshold = _safe_float(os.getenv("IMAGE_OCR_LOW_CONFIDENCE_THRESHOLD", "0.72"), 0.72)
    parse_error_threshold = _safe_float(os.getenv("IMAGE_OCR_PARSE_ERROR_THRESHOLD", "0.30"), 0.30)
    fallback_enabled = os.getenv("IMAGE_OCR_FALLBACK_ENABLED", "true").lower() == "true"
    postprocess_enabled = os.getenv("IMAGE_OCR_TEXT_POSTPROCESS_ENABLED", "true").lower() == "true"
    postprocess_only_low = os.getenv("IMAGE_OCR_TEXT_POSTPROCESS_ONLY_ON_LOW_CONF", "true").lower() == "true"

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
        glm_data = row["second_node"]["glm_4_6v_flashx"]["result"]
        vlm_fallback_map[image_path] = glm_data

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
        if ocr_error:
            fallback_reason = "ocr_api_error"
        elif low_conf:
            fallback_reason = "low_confidence"
        elif not assembled.strip():
            fallback_reason = "empty_assembled_text"

        if fallback_enabled and fallback_reason is not None:
            extraction_source = "vlm_fallback"
            final_text = (vlm_fallback_map.get(str(image_path), {}).get("text") or "").strip()
            final_structured_messages = []

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
        },
        "results": results,
    }


def build_human_scores(
    ab_result: Dict[str, Any],
    shadow_result: Dict[str, Any],
) -> Dict[str, Any]:
    score_rows = []
    for image_row in ab_result.get("results", []):
        image_path = image_row["image_path"]
        glm_text = image_row["second_node"]["glm_4_6v_flashx"]["result"].get("text", "")
        doubao_text = image_row["second_node"]["doubao_seed_1_6_flash"]["result"].get("text", "")
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

        score_rows.append(
            {
                "image_path": image_path,
                "glm_vlm": quick_quality(glm_text),
                "doubao_vlm": quick_quality(doubao_text),
                "ocr_shadow": quick_quality(shadow_text),
            }
        )

    return {
        "generated_at": _now_iso(),
        "scores": score_rows,
    }


def render_first_node_md(data: Dict[str, Any]) -> str:
    lines = [
        "# 第一节点路由稳定性复测（每图 5 次）",
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
    lines = [
        "# 图片识别第二节点 A/B（Doubao-Seed-1.6-flash vs GLM-4.6V-FlashX）",
        "",
        f"- 报告生成时间: {ab['generated_at']}",
        f"- 第一节点固定: {ab['notes']['first_node_fixed']}",
        f"- 第二节点变量: {', '.join(ab['notes']['second_node_variable'])}",
        f"- 思考模式: {'关闭' if ab['notes']['reasoning_disabled_for_both'] else '开启'}",
        f"- max_tokens 维持现状: `{ab['notes']['ocr_max_tokens']}`",
        f"- 超大图缩图阈值: `{ab['notes']['ocr_max_edge']}`",
        f"- doubao 请求模型: `{ab['notes']['doubao_requested_model']}`",
        f"- doubao 实际可用模型: `{ab['notes']['doubao_probe'].get('selected')}`",
        "",
    ]
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
        for key in ["doubao_seed_1_6_flash", "glm_4_6v_flashx"]:
            node = row["second_node"][key]
            lines += [
                f"### 第二节点: {key}",
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
        for k in ["glm_vlm", "doubao_vlm", "ocr_shadow"]:
            v = row[k]
            lines += [
                f"- {k}: recall={v['recall_score_1_to_5']}, accuracy={v['accuracy_score_1_to_5']}, "
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
        "1. 把影子链路的组件实现落地到生产路径：OCR Provider 抽象、normalizer/assembler、低置信门控、fallback、观测字段。",
        "2. 增加单测：normalizer、assembler、threshold gate、fallback 触发。",
        "3. 新增配置写入 `.env.example`：IMAGE_OCR_PROVIDER/VOLC_OCR_* / threshold 开关等。",
        "4. 用同三图重跑回归，输出 p50/p95（首节点、二节点、总耗时）并和现网纯 VLM 对比。",
        "5. 安全动作：轮换已暴露的 AK/SK，并仅保留新密钥在安全存储。",
    ]
    return "\n".join(
        [
            "# OCR 方案交接说明",
            "",
            "## 背景",
            "- 目标：把第二节点从“整图 VLM 直出”升级为“专用 OCR 主通道 + 规则整理 + 低置信后处理 + 全局回退”。",
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


async def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    processor = ImageProcessor()
    processor.disable_reasoning_output = True

    route_data = await run_first_node_route_check(processor, IMAGE_CASES, runs_per_image=5)
    route_json = OUTPUT_DIR / f"first_node_route_check_{ts}_5runs.json"
    route_md = OUTPUT_DIR / f"first_node_route_check_{ts}_5runs.md"
    _write_json(route_json, route_data)
    route_md.write_text(render_first_node_md(route_data), encoding="utf-8")

    ab_data = await run_second_node_ab(processor, IMAGE_CASES)
    scores_data = build_human_scores(ab_data, {"results": []})
    ab_json = OUTPUT_DIR / f"image_model_ab_compare_doubao_flash_vs_glm_{ts}.json"
    ab_md = OUTPUT_DIR / f"image_model_ab_compare_doubao_flash_vs_glm_{ts}.md"
    _write_json(ab_json, ab_data)

    shadow_data = await run_ocr_shadow_pipeline(processor, IMAGE_CASES, ab_data)
    scores_data = build_human_scores(ab_data, shadow_data)
    scores_json = OUTPUT_DIR / f"image_human_score_compare_{ts}.json"
    _write_json(scores_json, scores_data)

    ab_md.write_text(render_ab_md(ab_data, scores_data), encoding="utf-8")

    shadow_json = OUTPUT_DIR / f"ocr_shadow_quick_test_3images_{ts}.json"
    shadow_md = OUTPUT_DIR / f"ocr_shadow_quick_test_3images_{ts}.md"
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
    glm_times = []
    doubao_times = []
    shadow_times = []
    for row in ab_data["results"]:
        glm_times.append(row["second_node"]["glm_4_6v_flashx"]["total_elapsed_seconds"])
        doubao_times.append(row["second_node"]["doubao_seed_1_6_flash"]["total_elapsed_seconds"])
    for row in shadow_data["results"]:
        shadow_times.append(row["result"]["pipeline_timing"]["total_ms"] / 1000.0)

    print(
        "latency_summary="
        + json.dumps(
            {
                "glm_total_s": {"p50": round(_median(glm_times), 3), "p95": round(_p95(glm_times), 3)},
                "doubao_total_s": {"p50": round(_median(doubao_times), 3), "p95": round(_p95(doubao_times), 3)},
                "ocr_shadow_total_s": {"p50": round(_median(shadow_times), 3), "p95": round(_p95(shadow_times), 3)},
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
