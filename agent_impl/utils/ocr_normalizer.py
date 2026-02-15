from __future__ import annotations

import re
from typing import Any, Dict, List


CHAT_UI_NOISE_KEYWORDS = {
    "全部",
    "文件",
    "连接",
    "音乐与音",
    "图片与视频",
    "小红书",
    "我的小红书号",
    "取消",
}


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    # normalize full-width colon variants and punctuation spacing
    text = text.replace("： ", "：").replace(": ", ":")
    return text


def _bbox_from_location(location: Any) -> Dict[str, float]:
    if not isinstance(location, list) or not location:
        return {"x_min": 0.0, "y_min": 0.0, "x_max": 0.0, "y_max": 0.0}
    xs: List[float] = []
    ys: List[float] = []
    for p in location:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                xs.append(float(p[0]))
                ys.append(float(p[1]))
            except Exception:
                continue
    if not xs or not ys:
        return {"x_min": 0.0, "y_min": 0.0, "x_max": 0.0, "y_max": 0.0}
    return {
        "x_min": min(xs),
        "y_min": min(ys),
        "x_max": max(xs),
        "y_max": max(ys),
    }


def normalize_general_ocr_lines(ocr_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize veImageX GetImageOCRV2 response into sortable line items.
    """
    raw_lines = ocr_response.get("GeneralResult") or []
    normalized: List[Dict[str, Any]] = []
    noise_count = 0

    for item in raw_lines:
        content = _clean_text(str(item.get("Content", "")))
        if not content:
            continue

        bbox = _bbox_from_location(item.get("Location"))
        conf_raw = item.get("Confidence", 0.0)
        try:
            conf = float(conf_raw)
        except Exception:
            conf = 0.0

        is_noise = any(k in content for k in CHAT_UI_NOISE_KEYWORDS)
        # remove UI tabs/labels and one-char fragments early
        if is_noise:
            noise_count += 1
            continue
        if len(content) == 1:
            noise_count += 1
            continue

        cx = (bbox["x_min"] + bbox["x_max"]) / 2.0
        cy = (bbox["y_min"] + bbox["y_max"]) / 2.0
        normalized.append(
            {
                "content": content,
                "confidence": conf,
                "bbox": bbox,
                "cx": cx,
                "cy": cy,
            }
        )

    normalized.sort(key=lambda x: (x["bbox"]["y_min"], x["bbox"]["x_min"]))
    raw_count = len(raw_lines)
    filtered_count = len(normalized)
    parse_error_rate = 1.0 - (filtered_count / max(raw_count, 1))

    return {
        "lines": normalized,
        "raw_count": raw_count,
        "filtered_count": filtered_count,
        "noise_count": noise_count,
        "parse_error_rate": round(parse_error_rate, 4),
    }


def average_confidence(lines: List[Dict[str, Any]]) -> float:
    if not lines:
        return 0.0
    return round(sum(float(x.get("confidence", 0.0)) for x in lines) / len(lines), 4)
