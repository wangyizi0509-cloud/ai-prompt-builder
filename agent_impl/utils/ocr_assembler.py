from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List


TIME_LINE_PATTERN = re.compile(
    r"(昨天|今天|前天|上午|下午|晚上|凌晨|\d{1,2}:\d{2}|\d+月\d+日|\d{4}年)"
)


@dataclass
class Message:
    speaker: str
    text: str
    speaker_confidence: float
    ocr_confidence: float


def _is_time_or_system_line(text: str) -> bool:
    if not text:
        return True
    if TIME_LINE_PATTERN.search(text):
        return True
    # short separators or lone symbols
    if len(text) <= 2 and re.fullmatch(r"[\-\|·.。:：]+", text):
        return True
    return False


def _speaker_by_x(cx: float, image_width: int) -> tuple[str, float]:
    if image_width <= 0:
        return ("UNKNOWN", 0.3)
    ratio = cx / float(image_width)
    if ratio >= 0.58:
        # right bubble is usually current user
        confidence = min(0.98, 0.70 + max(0.0, ratio - 0.58) * 1.2)
        return ("USER", round(confidence, 3))
    if ratio <= 0.42:
        confidence = min(0.98, 0.70 + max(0.0, 0.42 - ratio) * 1.2)
        return ("CRUSH", round(confidence, 3))
    return ("UNKNOWN", 0.45)


def _resolve_unknown_speakers(messages: List[Message]) -> List[Message]:
    resolved = list(messages)
    for i, msg in enumerate(resolved):
        if msg.speaker != "UNKNOWN":
            continue
        prev_speaker = None
        next_speaker = None
        for j in range(i - 1, -1, -1):
            if resolved[j].speaker in ("USER", "CRUSH"):
                prev_speaker = resolved[j].speaker
                break
        for j in range(i + 1, len(resolved)):
            if resolved[j].speaker in ("USER", "CRUSH"):
                next_speaker = resolved[j].speaker
                break

        if prev_speaker and next_speaker and prev_speaker == next_speaker:
            resolved[i] = Message(
                speaker=prev_speaker,
                text=msg.text,
                speaker_confidence=min(0.62, msg.speaker_confidence + 0.12),
                ocr_confidence=msg.ocr_confidence,
            )
        elif prev_speaker:
            resolved[i] = Message(
                speaker=prev_speaker,
                text=msg.text,
                speaker_confidence=min(0.58, msg.speaker_confidence + 0.08),
                ocr_confidence=msg.ocr_confidence,
            )
        elif next_speaker:
            resolved[i] = Message(
                speaker=next_speaker,
                text=msg.text,
                speaker_confidence=min(0.58, msg.speaker_confidence + 0.08),
                ocr_confidence=msg.ocr_confidence,
            )
    return resolved


def _merge_chat_lines(
    lines: List[Dict[str, Any]],
    image_width: int,
    image_height: int,
) -> List[Message]:
    if not lines:
        return []

    max_gap = max(18.0, min(48.0, image_height * 0.018))
    merged: List[Message] = []
    current: Dict[str, Any] | None = None

    for item in lines:
        text = str(item.get("content", "")).strip()
        conf = float(item.get("confidence", 0.0))
        y_min = float(item.get("bbox", {}).get("y_min", 0.0))
        y_max = float(item.get("bbox", {}).get("y_max", y_min))
        cx = float(item.get("cx", 0.0))

        if _is_time_or_system_line(text):
            speaker, sp_conf = ("SYSTEM", 0.95)
        else:
            speaker, sp_conf = _speaker_by_x(cx, image_width)

        if current is None:
            current = {
                "speaker": speaker,
                "texts": [text],
                "speaker_conf": sp_conf,
                "ocr_confs": [conf],
                "y_max": y_max,
            }
            continue

        same_speaker = current["speaker"] == speaker
        close_enough = (y_min - current["y_max"]) <= max_gap
        if same_speaker and close_enough:
            current["texts"].append(text)
            current["ocr_confs"].append(conf)
            current["y_max"] = max(current["y_max"], y_max)
            # keep min confidence as conservative score
            current["speaker_conf"] = min(current["speaker_conf"], sp_conf)
        else:
            merged.append(
                Message(
                    speaker=current["speaker"],
                    text="\n".join([t for t in current["texts"] if t]),
                    speaker_confidence=round(float(current["speaker_conf"]), 3),
                    ocr_confidence=round(
                        sum(current["ocr_confs"]) / max(len(current["ocr_confs"]), 1),
                        4,
                    ),
                )
            )
            current = {
                "speaker": speaker,
                "texts": [text],
                "speaker_conf": sp_conf,
                "ocr_confs": [conf],
                "y_max": y_max,
            }

    if current is not None:
        merged.append(
            Message(
                speaker=current["speaker"],
                text="\n".join([t for t in current["texts"] if t]),
                speaker_confidence=round(float(current["speaker_conf"]), 3),
                ocr_confidence=round(
                    sum(current["ocr_confs"]) / max(len(current["ocr_confs"]), 1),
                    4,
                ),
            )
        )

    # drop empty or low-value system fragments
    cleaned: List[Message] = []
    for m in merged:
        t = m.text.strip()
        if not t:
            continue
        if m.speaker == "SYSTEM" and len(t) <= 2:
            continue
        cleaned.append(m)
    return _resolve_unknown_speakers(cleaned)


def _format_chat_text(messages: List[Message]) -> str:
    lines = ["### OCR 组装（聊天）", "", "| 序号 | 说话人 | 内容 |", "| --- | --- | --- |"]
    idx = 1
    for m in messages:
        role = {
            "USER": "用户",
            "CRUSH": "crush",
            "SYSTEM": "系统",
            "UNKNOWN": "未知",
        }.get(m.speaker, "未知")
        content = m.text.replace("\n", "<br>")
        lines.append(f"| {idx} | {role} | {content} |")
        idx += 1
    return "\n".join(lines)


def _format_moments_text(lines: List[Dict[str, Any]]) -> str:
    out = ["### OCR 组装（朋友圈候选）"]
    idx = 1
    for item in lines[:120]:
        out.append(f"{idx}. {item['content']}")
        idx += 1
    return "\n".join(out)


def assemble_ocr_text(
    screenshot_type: str,
    lines: List[Dict[str, Any]],
    image_width: int,
    image_height: int,
) -> Dict[str, Any]:
    if screenshot_type in ("private_chat_screenshot", "group_chat_screenshot"):
        messages = _merge_chat_lines(lines, image_width, image_height)
        return {
            "text": _format_chat_text(messages),
            "structured_messages": [
                {
                    "speaker": m.speaker,
                    "text": m.text,
                    "speaker_confidence": m.speaker_confidence,
                    "ocr_confidence": m.ocr_confidence,
                }
                for m in messages
            ],
            "item_count": len(messages),
        }

    # moments/other: currently keep line list; can evolve into entry parser later
    return {
        "text": _format_moments_text(lines),
        "structured_messages": [],
        "item_count": len(lines),
    }
