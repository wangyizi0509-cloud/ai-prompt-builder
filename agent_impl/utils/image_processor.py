"""
图片转文本处理模块 (Image Processor)

根据截图类型路由到对应的 prompt，调用豆包多模态模型将图片转换为结构化文本。

支持的截图类型：
- private_chat_screenshot: 私聊截图
- group_chat_screenshot: 群聊截图
- moments_screenshot: 朋友圈截图
- other_social_media_screenshot: 其他社媒截图
"""

import os
import base64
import json
import asyncio
import httpx
import logging
import time
import re
from io import BytesIO
from typing import Literal, Optional
from dotenv import load_dotenv
from PIL import Image

load_dotenv()
logger = logging.getLogger(__name__)

# 截图类型定义
ScreenshotType = Literal[
    "private_chat_screenshot",
    "group_chat_screenshot", 
    "moments_screenshot",
    "other_social_media_screenshot",
    "universal_screenshot_analysis"  # 新增通用类型
]

def load_screenshot_prompt(screenshot_type: str) -> str:
    """从文件中加载对应的截图分析 prompt"""
    try:
        # 尝试从 prompts/screenshots 目录加载
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompt_path = os.path.join(base_dir, "prompts", "screenshots", f"{screenshot_type}.md")
        
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        
        # 兜底：如果找不到对应的，尝试使用通用版
        if screenshot_type != "universal_screenshot_analysis":
            return load_screenshot_prompt("universal_screenshot_analysis")
            
        return "请分析这张截图并提取关键信息。"
    except Exception as e:
        logger.exception("Error loading prompt for %s", screenshot_type)
        return "请分析这张截图并提取关键信息。"


class ImageProcessor:
    """
    图片处理器 - 调用豆包多模态模型
    
    豆包 Vision API 兼容 OpenAI 格式
    """
    
    def __init__(self):
        self.api_key = os.getenv("DOUBAO_API_KEY")
        self.base_url = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        self.model = os.getenv("DOUBAO_ENDPOINT_ID")
        self.timeout_seconds = float(os.getenv("DOUBAO_TIMEOUT_SECONDS", "60"))
        self.max_retries = int(os.getenv("DOUBAO_MAX_RETRIES", "2"))
        self.type_detect_max_tokens = int(os.getenv("IMAGE_TYPE_DETECT_MAX_TOKENS", "80"))
        self.type_detect_max_edge = int(os.getenv("IMAGE_TYPE_DETECT_MAX_EDGE", "1024"))
        self.ocr_max_edge = int(os.getenv("IMAGE_OCR_MAX_EDGE", "3000"))
        self.ocr_max_tokens = int(os.getenv("IMAGE_OCR_MAX_TOKENS", "2000"))
        self.long_chat_min_height = int(os.getenv("IMAGE_LONG_CHAT_MIN_HEIGHT", "5000"))
        self.long_chat_min_aspect_ratio = float(os.getenv("IMAGE_LONG_CHAT_MIN_ASPECT_RATIO", "2.6"))
        self.long_chat_probe_height = int(os.getenv("IMAGE_LONG_CHAT_PROBE_HEIGHT", "1400"))
        self.long_chat_segment_height = int(os.getenv("IMAGE_LONG_CHAT_SEGMENT_HEIGHT", "2600"))
        self.long_chat_overlap = int(os.getenv("IMAGE_LONG_CHAT_OVERLAP", "220"))
        self.long_chat_dedupe_window = int(os.getenv("IMAGE_LONG_CHAT_DEDUPE_WINDOW", "8"))
        self.long_chat_boundary_scan_width = int(os.getenv("IMAGE_LONG_CHAT_BOUNDARY_SCAN_WIDTH", "240"))
        self.long_chat_boundary_search_radius = int(os.getenv("IMAGE_LONG_CHAT_BOUNDARY_SEARCH_RADIUS", "220"))
        self.long_chat_boundary_min_gap = int(os.getenv("IMAGE_LONG_CHAT_BOUNDARY_MIN_GAP", "120"))
        self.long_chat_boundary_smooth_window = int(os.getenv("IMAGE_LONG_CHAT_BOUNDARY_SMOOTH_WINDOW", "9"))
        self.long_chat_boundary_diff_threshold = int(os.getenv("IMAGE_LONG_CHAT_BOUNDARY_DIFF_THRESHOLD", "12"))
        self.disable_reasoning_output = os.getenv("IMAGE_DISABLE_REASONING_OUTPUT", "true").lower() == "true"
        self._http_client: Optional[httpx.AsyncClient] = None

        # 图片类型识别（第一路由节点）可单独配置模型与鉴权
        self.type_detect_api_key = os.getenv("IMAGE_TYPE_DETECT_API_KEY")
        self.type_detect_base_url = os.getenv(
            "IMAGE_TYPE_DETECT_BASE_URL",
            "https://open.bigmodel.cn/api/paas/v4"
        )
        self.type_detect_model = os.getenv("IMAGE_TYPE_DETECT_MODEL", "GLM-4.6V-FlashX")

        # 未单独配置时，回退到既有 OCR 模型配置
        if not self.type_detect_api_key:
            self.type_detect_api_key = self.api_key
            self.type_detect_base_url = self.base_url
            self.type_detect_model = self.model

        # 图片 OCR（第二路由节点）支持独立配置；未配置时默认跟随第一节点
        self.ocr_api_key = os.getenv("IMAGE_OCR_API_KEY") or self.type_detect_api_key
        self.ocr_base_url = os.getenv("IMAGE_OCR_BASE_URL") or self.type_detect_base_url
        self.ocr_model = os.getenv("IMAGE_OCR_MODEL") or self.type_detect_model
        self.long_chat_ocr_api_key = (
            os.getenv("IMAGE_LONG_CHAT_OCR_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or ""
        )
        self.long_chat_ocr_base_url = (
            os.getenv("IMAGE_LONG_CHAT_OCR_BASE_URL")
            or ("https://dashscope.aliyuncs.com/compatible-mode/v1" if self.long_chat_ocr_api_key else "")
        )
        self.long_chat_ocr_model = os.getenv("IMAGE_LONG_CHAT_OCR_MODEL", "").strip()
        
        if not self.type_detect_api_key or not self.type_detect_model:
            logger.warning("第一节点(类型识别)模型配置不完整，detect_type 可能不可用")
        if not self.ocr_api_key or not self.ocr_model:
            logger.warning("第二节点(OCR)模型配置不完整，process_image 可能不可用")

    def _has_long_chat_ocr_override(self) -> bool:
        return bool(
            self.long_chat_ocr_api_key
            and self.long_chat_ocr_base_url
            and self.long_chat_ocr_model
        )
    
    def _encode_image_to_base64(self, image_bytes: bytes) -> str:
        """将图片字节转为 base64"""
        return base64.b64encode(image_bytes).decode("utf-8")

    def _guess_mime_type(self, image_bytes: bytes) -> str:
        """根据文件头猜测 MIME 类型。"""
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if image_bytes.startswith(b"RIFF") and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
            return "image/webp"
        if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
            return "image/gif"
        if image_bytes.startswith(b"BM"):
            return "image/bmp"
        return "image/jpeg"

    def _build_image_data_url(self, image_bytes: bytes) -> str:
        """构建 data URL，避免把 PNG 误标为 JPEG。"""
        mime_type = self._guess_mime_type(image_bytes)
        base64_image = self._encode_image_to_base64(image_bytes)
        return f"data:{mime_type};base64,{base64_image}"

    def _maybe_resize_image(self, image_bytes: bytes, max_edge: int, reason: str) -> bytes:
        """按最长边阈值缩图；阈值 <= 0 时关闭。"""
        if max_edge <= 0:
            return image_bytes

        try:
            with Image.open(BytesIO(image_bytes)) as img:
                width, height = img.size
                longest = max(width, height)
                if longest <= max_edge:
                    return image_bytes

                scale = max_edge / float(longest)
                new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
                resized = img.resize(new_size, resample)

                image_format = (img.format or "JPEG").upper()
                output = BytesIO()
                save_image = resized
                save_kwargs: dict = {}

                if image_format in {"JPEG", "JPG"}:
                    if resized.mode not in {"RGB", "L"}:
                        save_image = resized.convert("RGB")
                    image_format = "JPEG"
                    save_kwargs = {"quality": 85, "optimize": True}
                elif image_format == "PNG":
                    image_format = "PNG"
                    save_kwargs = {"optimize": True}
                elif image_format == "WEBP":
                    if resized.mode not in {"RGB", "L"}:
                        save_image = resized.convert("RGB")
                    image_format = "WEBP"
                    save_kwargs = {"quality": 85}
                else:
                    if resized.mode not in {"RGB", "L"}:
                        save_image = resized.convert("RGB")
                    image_format = "JPEG"
                    save_kwargs = {"quality": 85, "optimize": True}

                save_image.save(output, format=image_format, **save_kwargs)
                return output.getvalue()
        except Exception as e:
            # 缩图失败不阻断主流程，回退原图
            logger.warning("resize for %s failed: %s", reason, e)
            return image_bytes

    def _maybe_resize_for_type_detect(self, image_bytes: bytes) -> bytes:
        """类型识别前缩图，减少传输体积与视觉推理开销。"""
        return self._maybe_resize_image(
            image_bytes=image_bytes,
            max_edge=self.type_detect_max_edge,
            reason="type detect",
        )

    def _maybe_resize_for_ocr(self, image_bytes: bytes) -> bytes:
        """OCR 前仅对超大图缩图，平衡延迟与识别质量。"""
        return self._maybe_resize_image(
            image_bytes=image_bytes,
            max_edge=self.ocr_max_edge,
            reason="ocr",
        )

    def _get_image_size(self, image_bytes: bytes) -> tuple[int, int]:
        """读取原图尺寸。失败时返回 0,0。"""
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                return img.size
        except Exception as e:
            logger.warning("get image size failed: %s", e)
            return (0, 0)

    def _get_long_image_meta(self, image_bytes: bytes) -> dict:
        """根据原图尺寸判断是否命中超长图候选。"""
        width, height = self._get_image_size(image_bytes)
        aspect_ratio = (height / float(width)) if width > 0 else 0.0
        return {
            "width": width,
            "height": height,
            "aspect_ratio": round(aspect_ratio, 4),
            "is_candidate": bool(
                width > 0
                and height >= self.long_chat_min_height
                and aspect_ratio >= self.long_chat_min_aspect_ratio
            ),
        }

    def _build_probe_ranges(self, image_height: int) -> list[tuple[int, int]]:
        """为超长图生成顶部/中部/底部 probe 切片。"""
        if image_height <= 0:
            return []

        slice_height = max(1, min(self.long_chat_probe_height, image_height))
        starts = [
            0,
            max(0, (image_height - slice_height) // 2),
            max(0, image_height - slice_height),
        ]

        ranges: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for start in starts:
            end = min(image_height, start + slice_height)
            item = (start, end)
            if item not in seen:
                seen.add(item)
                ranges.append(item)
        return ranges

    def _smooth_numeric_series(self, values: list[float], window: int) -> list[float]:
        if not values:
            return []
        radius = max(0, window // 2)
        if radius == 0:
            return list(values)

        smoothed: list[float] = []
        for index in range(len(values)):
            lo = max(0, index - radius)
            hi = min(len(values), index + radius + 1)
            window_vals = values[lo:hi]
            smoothed.append(sum(window_vals) / max(len(window_vals), 1))
        return smoothed

    def _build_long_chat_activity_profile(self, image_bytes: bytes) -> tuple[list[float], float]:
        """构建长图逐行活动度曲线；数值越低越像切片边界。"""
        try:
            with Image.open(BytesIO(image_bytes)) as img:
                grayscale = img.convert("L")
                width, height = grayscale.size
                if width <= 0 or height <= 0:
                    return [], 1.0

                scan_width = min(max(32, self.long_chat_boundary_scan_width), width)
                if scan_width != width:
                    scale = scan_width / float(width)
                    scan_height = max(1, int(height * scale))
                    resample = Image.Resampling.BILINEAR if hasattr(Image, "Resampling") else Image.BILINEAR
                    grayscale = grayscale.resize((scan_width, scan_height), resample)
                else:
                    scale = 1.0

                scan_width, scan_height = grayscale.size
                data = list(grayscale.getdata())
                profile: list[float] = []
                diff_threshold = max(1, self.long_chat_boundary_diff_threshold)
                denom = max(scan_width - 1, 1)

                for y in range(scan_height):
                    row = data[y * scan_width:(y + 1) * scan_width]
                    transitions = 0
                    row_min = 255
                    row_max = 0
                    for x in range(1, len(row)):
                        left = row[x - 1]
                        right = row[x]
                        if abs(right - left) >= diff_threshold:
                            transitions += 1
                        if left < row_min:
                            row_min = left
                        if left > row_max:
                            row_max = left
                    if row:
                        last_value = row[-1]
                        if last_value < row_min:
                            row_min = last_value
                        if last_value > row_max:
                            row_max = last_value
                    transition_ratio = transitions / float(denom)
                    spread_ratio = (row_max - row_min) / 255.0 if row else 0.0
                    profile.append((transition_ratio * 0.7) + (spread_ratio * 0.3))

                return self._smooth_numeric_series(profile, self.long_chat_boundary_smooth_window), 1.0 / scale
        except Exception as exc:
            logger.warning("build long chat activity profile failed: %s", exc)
            return [], 1.0

    def _find_candidate_cut_lines(self, image_bytes: bytes) -> list[dict[str, float]]:
        """基于活动度低谷寻找候选切点。"""
        profile, scale_back = self._build_long_chat_activity_profile(image_bytes)
        if not profile:
            return []

        sorted_scores = sorted(profile)
        threshold_index = min(len(sorted_scores) - 1, max(0, int(len(sorted_scores) * 0.35)))
        dynamic_threshold = sorted_scores[threshold_index]
        min_gap_scaled = max(1, int(self.long_chat_boundary_min_gap / max(scale_back, 1.0)))

        candidates: list[dict[str, float]] = []
        last_added = -10**9
        for index, score in enumerate(profile):
            lo = max(0, index - 2)
            hi = min(len(profile), index + 3)
            if score > dynamic_threshold:
                continue
            if score != min(profile[lo:hi]):
                continue
            if index - last_added < min_gap_scaled:
                if candidates and score < float(candidates[-1]["score"]):
                    candidates[-1] = {"y": round(index * scale_back, 1), "score": round(score, 6)}
                    last_added = index
                continue
            candidates.append({"y": round(index * scale_back, 1), "score": round(score, 6)})
            last_added = index
        return candidates

    def _snap_segment_boundary(
        self,
        target_y: int,
        *,
        image_height: int,
        candidate_lines: list[dict[str, float]] | None = None,
        lower_bound: int = 0,
    ) -> tuple[int, dict[str, float] | None]:
        if image_height <= 0:
            return 0, None

        fallback = max(lower_bound, min(target_y, image_height))
        if not candidate_lines:
            return fallback, None

        radius = max(0, self.long_chat_boundary_search_radius)
        best: dict[str, float] | None = None
        best_y = fallback
        best_cost: tuple[float, float] | None = None
        for item in candidate_lines:
            candidate_y = int(round(float(item.get("y") or 0.0)))
            if candidate_y < lower_bound or candidate_y > image_height:
                continue
            delta = abs(candidate_y - target_y)
            if delta > radius:
                continue
            score = float(item.get("score") or 0.0)
            cost = (delta, score)
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = item
                best_y = candidate_y
        return best_y, best

    def _build_segment_ranges(
        self,
        image_height: int,
        candidate_lines: list[dict[str, float]] | None = None,
    ) -> list[tuple[int, int]]:
        """为超长图生成带重叠区的正式识别切片。"""
        if image_height <= 0:
            return []

        segment_height = max(1, self.long_chat_segment_height)
        overlap = min(max(0, self.long_chat_overlap), max(segment_height - 1, 0))
        step = max(1, segment_height - overlap)
        min_gap = max(1, self.long_chat_boundary_min_gap)

        ranges: list[tuple[int, int]] = []
        start = 0
        while start < image_height:
            ideal_next_start = start + step
            if ideal_next_start >= image_height:
                ranges.append((start, image_height))
                break

            lower_bound = min(image_height - 1, start + min_gap)
            next_start, matched_boundary = self._snap_segment_boundary(
                ideal_next_start,
                image_height=image_height - 1,
                candidate_lines=candidate_lines,
                lower_bound=lower_bound,
            )
            if next_start <= start:
                next_start = ideal_next_start
                matched_boundary = None

            end = min(image_height, next_start + overlap)
            if end <= start:
                end = min(image_height, start + segment_height)
            ranges.append((start, end))
            logger.info(
                "[long-chat] segment boundary: start=%d ideal_next=%d snapped_next=%d end=%d boundary=%s",
                start,
                ideal_next_start,
                next_start,
                end,
                matched_boundary,
            )
            start = next_start
        return ranges

    def _save_image_to_bytes(self, image: Image.Image, image_format: str) -> bytes:
        """按原图格式尽量保存图片。"""
        output = BytesIO()
        save_image = image
        save_kwargs: dict = {}
        normalized_format = (image_format or "JPEG").upper()

        if normalized_format in {"JPEG", "JPG"}:
            if image.mode not in {"RGB", "L"}:
                save_image = image.convert("RGB")
            normalized_format = "JPEG"
            save_kwargs = {"quality": 90, "optimize": True}
        elif normalized_format == "PNG":
            normalized_format = "PNG"
            save_kwargs = {"optimize": True}
        elif normalized_format == "WEBP":
            if image.mode not in {"RGB", "L"}:
                save_image = image.convert("RGB")
            normalized_format = "WEBP"
            save_kwargs = {"quality": 90}
        else:
            if image.mode not in {"RGB", "L"}:
                save_image = image.convert("RGB")
            normalized_format = "JPEG"
            save_kwargs = {"quality": 90, "optimize": True}

        save_image.save(output, format=normalized_format, **save_kwargs)
        return output.getvalue()

    def _crop_image_range(self, image_bytes: bytes, start_y: int, end_y: int) -> bytes:
        """按 y 轴区间裁剪图片，保持原始宽度。"""
        with Image.open(BytesIO(image_bytes)) as img:
            width, height = img.size
            crop_top = max(0, min(start_y, height))
            crop_bottom = max(crop_top + 1, min(end_y, height))
            cropped = img.crop((0, crop_top, width, crop_bottom))
            return self._save_image_to_bytes(cropped, img.format or "JPEG")

    def _looks_like_time_separator_text(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized:
            return False
        patterns = [
            r"^(昨天|今天|前天)$",
            r"^(昨天|今天|前天)\s+\d{1,2}:\d{2}$",
            r"^\d{1,2}:\d{2}$",
            r"^\d{1,2}月\d{1,2}日(?:\s+(上午|下午|晚上|凌晨)\d{1,2}:\d{2})?$",
            r"^\d{4}年\d{1,2}月\d{1,2}日(?:\s+(上午|下午|晚上|凌晨)\d{1,2}:\d{2})?$",
            r"^\d{1,2}月\d{1,2}日\s+(上午|下午|晚上|凌晨)\d{1,2}:\d{2}$",
            r"^(上午|下午|晚上|凌晨)\d{1,2}:\d{2}$",
            r"^(星期[一二三四五六日天]|周[一二三四五六日天])$",
        ]
        return any(re.fullmatch(pattern, normalized) for pattern in patterns)

    def _is_time_separator_sender(self, sender: str, content: str, timestamp: str) -> bool:
        """识别明显的时间/日期分隔行，避免被当成发送者。"""
        if content.strip() or timestamp.strip():
            return False
        return self._looks_like_time_separator_text(sender)

    def _is_time_separator_system_row(self, sender: str, content: str, timestamp: str) -> bool:
        """识别被模型误写成系统消息的时间分隔行。"""
        if sender.strip() != "系统":
            return False
        if timestamp.strip():
            return False
        return self._looks_like_time_separator_text(content)

    def _normalize_chat_content(self, content: str) -> str:
        """做最小工程归一化，服务边界去重。"""
        normalized = content or ""
        normalized = re.sub(r"<br\s*/?>", "<br>", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s*<br>\s*", "<br>", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        normalized = normalized.strip(" \t\r\n,，.。!！?？;；:：")
        return normalized

    def _build_row_match_keys(self, row: dict[str, str]) -> tuple[tuple[str, str, str], tuple[str, str], tuple[str]]:
        sender = " ".join((row.get("sender") or "").split())
        content = self._normalize_chat_content(row.get("content") or "")
        timestamp = " ".join((row.get("timestamp") or "").split())
        return (
            (sender, content, timestamp),
            (content, timestamp),
            (content,),
        )

    def _boundary_trust_score(self, row: dict[str, str]) -> int:
        try:
            return int(row.get("_boundary_distance") or 0)
        except Exception:
            return 0

    def _annotate_segment_rows(
        self,
        rows: list[dict[str, str]],
        *,
        segment_index: int,
        total_segments: int,
    ) -> list[dict[str, str]]:
        annotated: list[dict[str, str]] = []
        row_count = len(rows)
        for row_index, row in enumerate(rows):
            item = dict(row)
            item["_segment_index"] = segment_index
            item["_segment_count"] = total_segments
            item["_row_index"] = row_index
            item["_boundary_distance"] = min(row_index, max(row_count - row_index - 1, 0))
            annotated.append(item)
        return annotated

    def _dedupe_segment_boundary_rows(
        self,
        previous_rows: list[dict[str, str]],
        current_rows: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], int]:
        """只在相邻切片边界窗口内去重，避免误删远处真实重复消息。"""
        if not previous_rows or not current_rows:
            return list(current_rows), 0

        window = max(1, self.long_chat_dedupe_window)
        previous_window_start = max(0, len(previous_rows) - window)
        previous_window = previous_rows[previous_window_start:]
        previous_seen: dict[tuple[str, ...], int] = {}
        for local_index, row in enumerate(previous_window):
            absolute_index = previous_window_start + local_index
            for key in self._build_row_match_keys(row):
                previous_seen[key] = absolute_index

        deduped_current: list[dict[str, str]] = []
        removed = 0
        head_window = min(window, len(current_rows))

        for index, row in enumerate(current_rows):
            if index < head_window:
                keys = self._build_row_match_keys(row)
                matched_index = next((previous_seen[key] for key in keys if key in previous_seen), None)
                if matched_index is not None:
                    previous_row = previous_rows[matched_index]
                    if (
                        self._normalize_chat_content(previous_row.get("content") or "")
                        == self._normalize_chat_content(row.get("content") or "")
                        and " ".join((previous_row.get("timestamp") or "").split())
                        == " ".join((row.get("timestamp") or "").split())
                        and (previous_row.get("sender") or "").strip() != (row.get("sender") or "").strip()
                    ):
                        current_trust = self._boundary_trust_score(row)
                        previous_trust = self._boundary_trust_score(previous_row)
                        if current_trust > previous_trust:
                            previous_rows[matched_index] = dict(row)
                        removed += 1
                        continue
                    removed += 1
                    continue
            deduped_current.append(row)

        return deduped_current, removed

    def _extract_chat_table_rows(self, text: str) -> list[dict[str, str]]:
        """从模型输出的私聊 Markdown 表格中提取行。"""
        rows: list[dict[str, str]] = []
        filtered_time_rows = 0
        if not text:
            return rows

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.startswith("|") or not line.endswith("|"):
                continue

            parts = [part.strip() for part in line.split("|")[1:-1]]
            if len(parts) < 4:
                continue
            if parts[0] in {"发送者", ":---", "---"}:
                continue
            if all(part.replace(":", "").replace("-", "") == "" for part in parts):
                continue

            sender = parts[0].strip()
            content = "|".join(parts[1:-2]).strip()
            timestamp = parts[-2].strip()
            if not sender:
                continue
            if self._is_time_separator_sender(sender, content, timestamp):
                filtered_time_rows += 1
                continue
            if self._is_time_separator_system_row(sender, content, timestamp):
                filtered_time_rows += 1
                continue

            rows.append(
                {
                    "sender": sender,
                    "content": content,
                    "timestamp": timestamp,
                }
            )
        if filtered_time_rows:
            logger.info("[long-chat] filtered time separator rows: count=%d", filtered_time_rows)
        return rows

    def _dedupe_chat_rows(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        """去掉相邻切片边界上重复的消息。"""
        deduped: list[dict[str, str]] = []
        last_key = None

        for row in rows:
            sender = " ".join((row.get("sender") or "").split())
            content = self._normalize_chat_content(row.get("content") or "")
            timestamp = " ".join((row.get("timestamp") or "").split())
            key = (sender, content, timestamp)
            if key == last_key:
                continue
            deduped.append(row)
            last_key = key

        return deduped

    def _format_chat_table_rows(self, rows: list[dict[str, str]]) -> str:
        """将合并后的私聊消息重新组装为单份 Markdown 表格。"""
        lines = [
            "#### 记录1",
            "| 发送者 | 内容 | 时间戳 | 文本序号 |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for index, row in enumerate(rows, start=1):
            sender = row.get("sender", "").strip()
            content = row.get("content", "").strip()
            timestamp = row.get("timestamp", "").strip()
            lines.append(f"| {sender} | {content} | {timestamp} | {index} |")
        return "\n".join(lines)

    def _looks_like_explanatory_chat_text(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", (text or "").strip())
        if not normalized:
            return False
        keywords = [
            "视觉分隔线",
            "时间分隔线",
            "时间摘要",
            "以下是最新消息",
            "按视觉顺序",
            "仅用于判断时序",
            "系统提示语",
            "截图背景文字",
            "不是消息内容",
            "非用户消息",
            "不录入表格",
            "消息从",
            "时间线需结合",
            "此处为截图背景文字",
        ]
        return any(keyword in normalized for keyword in keywords)

    def _is_obviously_invalid_private_sender(self, sender: str) -> bool:
        normalized = re.sub(r"\s+", "", sender or "")
        if not normalized:
            return True
        bad_markers = [
            "{",
            "}",
            "发送者",
            "对方",
            "本人",
            "左侧",
            "右侧",
            "气泡",
            "头像",
            "绿色",
            "白色",
        ]
        return any(marker in normalized for marker in bad_markers)

    def _looks_like_named_private_sender(self, sender: str) -> bool:
        normalized = re.sub(r"\s+", "", sender or "")
        if not normalized:
            return False
        if any(char.isdigit() for char in normalized):
            return False
        if any(token in normalized for token in ["系统", "撤回", "红包", "转账", "通话", "拍一拍", "引用", "回复"]):
            return False
        return bool(re.fullmatch(r"[A-Za-z\u4e00-\u9fff·_-]{1,16}", normalized))

    def _looks_like_reply_preview_text(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", (text or "").strip())
        if not normalized:
            return False
        if self._looks_like_time_separator_text(normalized):
            return False
        if any(token in normalized for token in ["撤回", "红包", "转账", "通话", "拍一拍", "系统"]):
            return False
        return len(normalized) <= 48 and ("：" in normalized or ":" in normalized)

    def _normalize_private_sender(self, sender: str) -> Optional[str]:
        raw = (sender or "").strip()
        compact = re.sub(r"\s+", "", raw)
        alias_map = {
            "Crush": "Crush",
            "crush": "Crush",
            "CRUSH": "Crush",
            "用户": "用户",
            "User": "用户",
            "user": "用户",
            "USER": "用户",
            "系统": "系统",
            "System": "系统",
            "system": "系统",
            "{CRUSH_NAME}": "Crush",
            "{{crush_name}}": "Crush",
            "{crush_name}": "Crush",
            "{{CRUSH_NAME}}": "Crush",
            "{USER_NAME}": "用户",
            "{{user_name}}": "用户",
            "{user_name}": "用户",
            "{{USER_NAME}}": "用户",
        }
        if compact in alias_map:
            return alias_map[compact]
        if self._looks_like_time_separator_text(raw):
            return None
        if self._is_obviously_invalid_private_sender(compact):
            return None
        if self._looks_like_named_private_sender(raw):
            # 私聊输出契约只允许抽象角色；残留备注名统一视为左侧对方。
            return "Crush"
        return None

    def _normalize_group_sender(self, sender: str) -> Optional[str]:
        raw = (sender or "").strip()
        if not raw:
            return None
        compact = re.sub(r"\s+", "", raw)
        if compact in {"{USER_NAME}", "{{user_name}}", "{{USER_NAME}}", "{user_name}"}:
            return "用户"
        if compact in {"{CRUSH_NAME}", "{{crush_name}}", "{{CRUSH_NAME}}", "{crush_name}"}:
            return "Crush"
        if self._looks_like_time_separator_text(raw):
            return None
        if any(marker in compact for marker in ["发送者", "左侧", "右侧", "头像", "气泡"]):
            return None
        return raw

    def _clean_private_chat_rows(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        cleaned: list[dict[str, str]] = []
        for row in rows:
            sender = self._normalize_private_sender(row.get("sender") or "")
            content = (row.get("content") or "").strip()
            timestamp = (row.get("timestamp") or "").strip()
            if sender is None:
                continue
            if self._looks_like_time_separator_text(content) and not timestamp:
                continue
            if self._looks_like_explanatory_chat_text(content):
                continue
            if sender == "系统" and (self._looks_like_time_separator_text(content) or self._looks_like_explanatory_chat_text(content)):
                continue
            if sender == "系统" and not timestamp and self._looks_like_reply_preview_text(content):
                continue
            if not content and not timestamp:
                continue
            if not content and sender != "系统":
                continue
            normalized_content = self._normalize_chat_content(content)
            if not timestamp and any(
                prev.get("sender") == sender and self._normalize_chat_content(prev.get("content") or "") == normalized_content
                for prev in cleaned[-4:]
            ):
                continue
            cleaned.append(
                {
                    "sender": sender,
                    "content": content,
                    "timestamp": timestamp,
                }
            )
        return cleaned

    def _clean_group_chat_rows(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        cleaned: list[dict[str, str]] = []
        for row in rows:
            sender = self._normalize_group_sender(row.get("sender") or "")
            content = (row.get("content") or "").strip()
            timestamp = (row.get("timestamp") or "").strip()
            if sender is None:
                continue
            if sender == "系统" and (self._looks_like_time_separator_text(content) or self._looks_like_explanatory_chat_text(content)):
                continue
            if not content and not timestamp:
                continue
            if not content and sender != "系统":
                continue
            cleaned.append(
                {
                    "sender": sender,
                    "content": content,
                    "timestamp": timestamp,
                }
            )
        return cleaned

    def _clean_chat_markdown_output(self, text: str, screenshot_type: ScreenshotType) -> str:
        if screenshot_type not in {"private_chat_screenshot", "group_chat_screenshot"}:
            return text
        rows = self._extract_chat_table_rows(text)
        if not rows:
            return text

        if screenshot_type == "private_chat_screenshot":
            cleaned_rows = self._clean_private_chat_rows(rows)
        else:
            cleaned_rows = self._clean_group_chat_rows(rows)

        if not cleaned_rows:
            return text
        return self._format_chat_table_rows(cleaned_rows)

    async def _detect_type_once(self, image_bytes: bytes) -> dict:
        """单次类型识别，不包含长图 probe 特殊逻辑。"""
        default_type = "universal_screenshot_analysis"
        valid_types = {
            "private_chat_screenshot",
            "group_chat_screenshot",
            "moments_screenshot",
            "other_social_media_screenshot",
            "universal_screenshot_analysis",
        }
        valid_confidence = {"high", "medium", "low"}

        if not self.type_detect_api_key:
            return {
                "success": False,
                "screenshot_type": default_type,
                "confidence": "low",
                "reason": None,
                "error": "图片类型识别 API Key 未配置",
            }

        try:
            prompt = load_screenshot_prompt("type_detection")
            resized_bytes = self._maybe_resize_for_type_detect(image_bytes)
            image_data_url = self._build_image_data_url(resized_bytes)

            payload = {
                "model": self.type_detect_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_data_url
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": self.type_detect_max_tokens,
                "temperature": 0,
            }
            result = await self._post_chat_completion(
                self._apply_generation_controls(payload),
                api_key=self.type_detect_api_key,
                base_url=self.type_detect_base_url,
            )

            choices = result.get("choices")
            if not choices or not isinstance(choices, list):
                raise ValueError("豆包返回格式异常: 缺少 choices")
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                raise ValueError("豆包返回格式异常: message.content 非字符串")
            parsed = self._extract_json_dict(content) or {}

            screenshot_type = parsed.get("type", default_type)
            if screenshot_type not in valid_types:
                screenshot_type = default_type

            confidence = str(parsed.get("confidence", "low")).lower()
            if confidence not in valid_confidence:
                confidence = "low"

            reason = parsed.get("reason")
            if reason is not None:
                reason = str(reason)

            return {
                "success": True,
                "screenshot_type": screenshot_type,
                "confidence": confidence,
                "reason": reason,
                "error": None,
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "screenshot_type": default_type,
                "confidence": "low",
                "reason": None,
                "error": f"API 请求失败: {e.response.status_code}",
            }
        except Exception as e:
            err_text = str(e).strip()
            if not err_text:
                err_text = f"{type(e).__name__}: {repr(e)}"
            return {
                "success": False,
                "screenshot_type": default_type,
                "confidence": "low",
                "reason": None,
                "error": f"识别失败: {err_text}",
            }

    async def _probe_long_chat_candidate(
        self,
        image_bytes: bytes,
        image_meta: Optional[dict] = None,
    ) -> dict:
        """对超长图做顶部/中部/底部 probe，识别是否应强制进入聊天分支。"""
        meta = image_meta or self._get_long_image_meta(image_bytes)
        if not meta.get("is_candidate"):
            return {
                "matched_chat": False,
                "forced_type": None,
                "reason": None,
                "probes": [],
            }

        ranges = self._build_probe_ranges(int(meta.get("height") or 0))
        probes = []
        chat_types = {"private_chat_screenshot", "group_chat_screenshot"}

        logger.info(
            "[long-chat] probe start: width=%s, height=%s, aspect_ratio=%s, probe_count=%d",
            meta.get("width"),
            meta.get("height"),
            meta.get("aspect_ratio"),
            len(ranges),
        )

        for index, (start_y, end_y) in enumerate(ranges, start=1):
            segment_bytes = self._crop_image_range(image_bytes, start_y, end_y)
            probe_result = await self._detect_type_once(segment_bytes)
            probes.append(
                {
                    "index": index,
                    "start_y": start_y,
                    "end_y": end_y,
                    "result": probe_result,
                }
            )
            logger.info(
                "[long-chat] probe slice=%d/%d y=%d:%d -> type=%s success=%s confidence=%s",
                index,
                len(ranges),
                start_y,
                end_y,
                probe_result.get("screenshot_type"),
                probe_result.get("success"),
                probe_result.get("confidence"),
            )

            if probe_result.get("success") and probe_result.get("screenshot_type") in chat_types:
                return {
                    "matched_chat": True,
                    "forced_type": "private_chat_screenshot",
                    "reason": "long_chat_slice_probe",
                    "probes": probes,
                }

        return {
            "matched_chat": False,
            "forced_type": None,
            "reason": None,
            "probes": probes,
        }

    def _get_http_client(self) -> httpx.AsyncClient:
        """复用 AsyncClient，避免每次请求都重新建连。"""
        if self._http_client is None or self._http_client.is_closed:
            timeout = httpx.Timeout(
                timeout=self.timeout_seconds,
                connect=min(10.0, self.timeout_seconds),
            )
            limits = httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
                keepalive_expiry=30.0,
            )
            # 不继承宿主进程的代理环境变量，避免 OCR 请求被错误代理劫持。
            self._http_client = httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                trust_env=False,
            )
        return self._http_client

    def _apply_generation_controls(self, payload: dict) -> dict:
        """统一注入生成控制参数（默认关闭 reasoning_content 输出）。"""
        out = dict(payload)
        if self.disable_reasoning_output:
            out["thinking"] = {"type": "disabled"}
        return out

    async def _post_chat_completion(
        self,
        payload: dict,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> dict:
        """调用多模态接口，包含基础重试，规避瞬时连接抖动。"""
        import time
        request_api_key = api_key or self.api_key
        request_base_url = (base_url or self.base_url or "").rstrip("/")
        if not request_api_key:
            raise ValueError("API Key 未配置")
        if not request_base_url:
            raise ValueError("BASE URL 未配置")

        model_name = payload.get("model", "unknown")
        logger.info(
            "[vision-api] 准备请求: model=%s, base_url=%s, api_key=%s..., timeout=%.0fs",
            model_name, request_base_url, (request_api_key or "")[:8], self.timeout_seconds,
        )

        headers = {
            "Authorization": f"Bearer {request_api_key}",
            "Content-Type": "application/json",
        }
        retryable_status_codes = {408, 429, 500, 502, 503, 504}
        max_attempts = max(1, self.max_retries + 1)

        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            t_start = time.monotonic()
            try:
                client = self._get_http_client()
                url = f"{request_base_url}/chat/completions"
                logger.info("[vision-api] 发送请求 attempt=%d/%d: %s", attempt, max_attempts, url)
                response = await client.post(url, json=payload, headers=headers)
                elapsed = (time.monotonic() - t_start) * 1000
                logger.info(
                    "[vision-api] 收到响应 attempt=%d: status=%d, elapsed=%.1fms, content_length=%s",
                    attempt, response.status_code, elapsed,
                    response.headers.get("content-length", "unknown"),
                )
                if response.status_code in retryable_status_codes and attempt < max_attempts:
                    logger.warning("[vision-api] 可重试状态码 %d，等待后重试", response.status_code)
                    await asyncio.sleep(min(1.5, 0.4 * attempt))
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                elapsed = (time.monotonic() - t_start) * 1000
                last_exc = e
                resp_text = e.response.text[:500] if e.response else "N/A"
                logger.error(
                    "[vision-api] HTTP 错误 attempt=%d: status=%d, elapsed=%.1fms, body=%s",
                    attempt, e.response.status_code, elapsed, resp_text,
                )
                if e.response.status_code in retryable_status_codes and attempt < max_attempts:
                    await asyncio.sleep(min(1.5, 0.4 * attempt))
                    continue
                raise
            except (httpx.TransportError, httpx.TimeoutException) as e:
                elapsed = (time.monotonic() - t_start) * 1000
                last_exc = e
                logger.error(
                    "[vision-api] 传输/超时错误 attempt=%d: %s: %s, elapsed=%.1fms",
                    attempt, type(e).__name__, e, elapsed,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(min(1.5, 0.4 * attempt))
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("未知错误：豆包请求失败且未捕获具体异常")
    
    def _get_prompt_for_type(self, screenshot_type: ScreenshotType) -> str:
        """根据截图类型获取对应的 prompt"""
        return load_screenshot_prompt(screenshot_type)

    def _extract_json_dict(self, text: str) -> Optional[dict]:
        """从模型输出中提取 JSON 对象。"""
        if not text:
            return None

        raw = text.strip()

        # 优先直接解析纯 JSON
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        # 兼容 ```json ... ``` 包裹
        if "```" in raw:
            cleaned = raw.replace("```json", "```").replace("```JSON", "```")
            parts = cleaned.split("```")
            for part in parts:
                segment = part.strip()
                if not segment:
                    continue
                try:
                    parsed = json.loads(segment)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue

        # 最后尝试截取首尾大括号
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = raw[start:end + 1]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return None

        return None

    async def detect_type(self, image_bytes: bytes) -> dict:
        """
        自动识别截图类型。

        Returns:
            {
                "success": bool,
                "screenshot_type": str,
                "confidence": str,
                "reason": str | None,
                "error": str | None
            }
        """
        image_meta = self._get_long_image_meta(image_bytes)
        if image_meta.get("is_candidate"):
            probe_result = await self._probe_long_chat_candidate(image_bytes, image_meta=image_meta)
            if probe_result.get("matched_chat"):
                logger.info(
                    "[long-chat] detect_type forced private_chat_screenshot: width=%s, height=%s, probes=%d",
                    image_meta.get("width"),
                    image_meta.get("height"),
                    len(probe_result.get("probes") or []),
                )
                return {
                    "success": True,
                    "screenshot_type": "private_chat_screenshot",
                    "confidence": "high",
                    "reason": "long_chat_slice_probe",
                    "error": None,
                }

        return await self._detect_type_once(image_bytes)

    async def _process_image_single_pass(
        self,
        image_bytes: bytes,
        screenshot_type: ScreenshotType,
        additional_context: Optional[str] = None,
        *,
        ocr_override: Optional[tuple[str, str, str]] = None,
    ) -> dict:
        """单次整图/单切片识别，不包含长图切片逻辑。

        `ocr_override` 用于长图私聊专用 OCR 切换时显式注入 (api_key, base_url, model)，
        避免对 singleton 实例属性做跨 await 的修改（并发下会污染其他请求）。
        """
        if ocr_override is not None:
            ocr_api_key, ocr_base_url, ocr_model = ocr_override
        else:
            ocr_api_key, ocr_base_url, ocr_model = (
                self.ocr_api_key, self.ocr_base_url, self.ocr_model,
            )
        t0 = time.monotonic()
        logger.info(
            "[process_image] 开始: type=%s, image_size=%d bytes, context=%s, "
            "ocr_model=%s, ocr_base_url=%s, ocr_api_key=%s...",
            screenshot_type, len(image_bytes),
            repr(additional_context[:80]) if additional_context else None,
            ocr_model, ocr_base_url, (ocr_api_key or "")[:8],
        )

        if not ocr_api_key:
            logger.error("[process_image] OCR API Key 未配置，直接返回失败")
            return {
                "success": False,
                "text": "",
                "screenshot_type": screenshot_type,
                "error": "第二节点 OCR API Key 未配置"
            }

        try:
            base_prompt = self._get_prompt_for_type(screenshot_type)
            logger.info("[process_image] 加载 prompt: type=%s, prompt_len=%d", screenshot_type, len(base_prompt))
            if additional_context:
                base_prompt = f"{base_prompt}\n\n【用户补充说明】\n{additional_context}"
            
            resized_bytes = self._maybe_resize_for_ocr(image_bytes)
            logger.info(
                "[process_image] 缩图完成: original=%d bytes -> resized=%d bytes",
                len(image_bytes), len(resized_bytes),
            )
            image_data_url = self._build_image_data_url(resized_bytes)
            logger.info(
                "[process_image] data_url 构建完成: mime=%s, url_len=%d",
                self._guess_mime_type(resized_bytes), len(image_data_url),
            )
            
            payload = {
                "model": ocr_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": base_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_data_url
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": self.ocr_max_tokens
            }
            logger.info("[process_image] 准备调用 vision API: max_tokens=%d", self.ocr_max_tokens)

            result = await self._post_chat_completion(
                self._apply_generation_controls(payload),
                api_key=ocr_api_key,
                base_url=ocr_base_url,
            )
            
            choices = result.get("choices")
            if not choices or not isinstance(choices, list):
                logger.error("[process_image] API 返回格式异常: 缺少 choices, raw_keys=%s", list(result.keys()))
                raise ValueError("返回格式异常: 缺少 choices")
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            text = message.get("content") if isinstance(message, dict) else None
            if not isinstance(text, str):
                logger.error(
                    "[process_image] API 返回 content 非字符串: type=%s, message_keys=%s",
                    type(text).__name__, list(message.keys()) if isinstance(message, dict) else None,
                )
                raise ValueError("返回格式异常: message.content 非字符串")
            cleaned_text = self._clean_chat_markdown_output(text, screenshot_type)
            
            elapsed = (time.monotonic() - t0) * 1000
            logger.info(
                "[process_image] 成功: text_len=%d, elapsed=%.1fms, preview=%r",
                len(cleaned_text), elapsed, cleaned_text[:200],
            )
            return {
                "success": True,
                "text": cleaned_text,
                "screenshot_type": screenshot_type,
                "error": None
            }
            
        except httpx.HTTPStatusError as e:
            elapsed = (time.monotonic() - t0) * 1000
            resp_text = e.response.text[:500] if e.response else "N/A"
            logger.error(
                "[process_image] HTTP 错误: status=%d, elapsed=%.1fms, body=%s",
                e.response.status_code, elapsed, resp_text,
            )
            return {
                "success": False,
                "text": "",
                "screenshot_type": screenshot_type,
                "error": f"API 请求失败: {e.response.status_code} - {e.response.text}"
            }
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            err_text = str(e).strip()
            if not err_text:
                err_text = f"{type(e).__name__}: {repr(e)}"
            logger.error(
                "[process_image] 异常: %s, elapsed=%.1fms", err_text, elapsed, exc_info=True,
            )
            return {
                "success": False,
                "text": "",
                "screenshot_type": screenshot_type,
                "error": f"处理失败: {err_text}"
            }

    async def _process_long_private_chat_image(
        self,
        image_bytes: bytes,
        additional_context: Optional[str] = None,
        *,
        ocr_override: Optional[tuple[str, str, str]] = None,
    ) -> dict:
        """将超长聊天截图切片后按私聊截图逐段识别并合并。"""
        image_meta = self._get_long_image_meta(image_bytes)
        candidate_lines = self._find_candidate_cut_lines(image_bytes)
        segment_ranges = self._build_segment_ranges(
            int(image_meta.get("height") or 0),
            candidate_lines=candidate_lines,
        )
        merged_rows: list[dict[str, str]] = []
        raw_texts: list[str] = []
        segment_failures: list[str] = []
        boundary_removed_total = 0

        logger.info(
            "[long-chat] process start: width=%s, height=%s, segment_count=%d, "
            "segment_height=%d, overlap=%d, dedupe_window=%d",
            image_meta.get("width"),
            image_meta.get("height"),
            len(segment_ranges),
            self.long_chat_segment_height,
            self.long_chat_overlap,
            self.long_chat_dedupe_window,
        )
        if candidate_lines:
            logger.info(
                "[long-chat] candidate cut lines: count=%d sample=%s",
                len(candidate_lines),
                candidate_lines[:8],
            )

        for index, (start_y, end_y) in enumerate(segment_ranges, start=1):
            segment_started = time.monotonic()
            segment_bytes = self._crop_image_range(image_bytes, start_y, end_y)
            segment_context = (
                f"这是长图切片 {index}/{len(segment_ranges)}。"
                "只记录当前切片里清晰可见的消息。"
                "私聊里左侧白色/灰色气泡固定是 Crush，右侧绿色气泡固定是 用户。"
                "发送者只能按当前切片中每个气泡、语音条、图片卡片自身的左右位置判断，"
                "不要沿用上一切片末尾的 sender。"
                "不同气泡即不同消息，即使同侧连续出现也不要合并成一行。"
                "如果内容和左右位置冲突，永远优先相信左右位置，不要互换 Crush 和 用户。"
            )
            if additional_context:
                segment_context = f"{segment_context}\n{additional_context}"
            segment_result = await self._process_image_single_pass(
                image_bytes=segment_bytes,
                screenshot_type="private_chat_screenshot",
                additional_context=segment_context,
                ocr_override=ocr_override,
            )
            segment_elapsed = (time.monotonic() - segment_started) * 1000

            if not segment_result.get("success"):
                segment_failures.append(segment_result.get("error") or f"slice_{index}_failed")
                logger.warning(
                    "[long-chat] segment failed: slice=%d/%d y=%d:%d elapsed=%.1fms error=%s",
                    index,
                    len(segment_ranges),
                    start_y,
                    end_y,
                    segment_elapsed,
                    segment_result.get("error"),
                )
                continue

            segment_text = str(segment_result.get("text") or "")
            raw_texts.append(segment_text)
            parsed_rows = self._annotate_segment_rows(
                self._extract_chat_table_rows(segment_text),
                segment_index=index,
                total_segments=len(segment_ranges),
            )
            deduped_rows, boundary_removed = self._dedupe_segment_boundary_rows(merged_rows, parsed_rows)
            boundary_removed_total += boundary_removed
            if boundary_removed:
                logger.info(
                    "[long-chat] boundary dedupe: slice=%d/%d removed=%d head_window=%d",
                    index,
                    len(segment_ranges),
                    boundary_removed,
                    self.long_chat_dedupe_window,
                )
            merged_rows.extend(deduped_rows)
            logger.info(
                "[long-chat] segment success: slice=%d/%d y=%d:%d elapsed=%.1fms parsed_rows=%d "
                "rows_after_boundary_dedupe=%d text_len=%d",
                index,
                len(segment_ranges),
                start_y,
                end_y,
                segment_elapsed,
                len(parsed_rows),
                len(deduped_rows),
                len(segment_text),
            )

        deduped_rows = self._dedupe_chat_rows(merged_rows)
        logger.info(
            "[long-chat] merge finished: segment_count=%d success_count=%d failure_count=%d "
            "rows_before=%d rows_after=%d boundary_removed=%d",
            len(segment_ranges),
            len(raw_texts),
            len(segment_failures),
            len(merged_rows),
            len(deduped_rows),
            boundary_removed_total,
        )

        if deduped_rows:
            return {
                "success": True,
                "text": self._format_chat_table_rows(deduped_rows),
                "screenshot_type": "private_chat_screenshot",
                "error": None,
            }

        if raw_texts:
            logger.warning(
                "[long-chat] no parsed table rows, fallback to raw text join: segment_count=%d",
                len(raw_texts),
            )
            return {
                "success": True,
                "text": "\n\n".join(raw_texts),
                "screenshot_type": "private_chat_screenshot",
                "error": None,
            }

        logger.warning("[long-chat] all segments failed, fallback to single-pass private chat OCR")
        fallback_result = await self._process_image_single_pass(
            image_bytes=image_bytes,
            screenshot_type="private_chat_screenshot",
            additional_context=additional_context,
            ocr_override=ocr_override,
        )
        fallback_result["screenshot_type"] = "private_chat_screenshot"
        return fallback_result

    async def _process_long_private_chat_with_dedicated_ocr(
        self,
        image_bytes: bytes,
        additional_context: Optional[str] = None,
    ) -> dict:
        """长图命中后切换到专用 OCR 模型，但仍复用既有长图切片与合并逻辑。"""
        if not self._has_long_chat_ocr_override():
            logger.info("[long-chat] dedicated OCR override missing, fallback to segmented pipeline")
            return await self._process_long_private_chat_image(
                image_bytes=image_bytes,
                additional_context=additional_context,
            )

        # 以参数形式把专用 OCR 透传到底层方法，不要修改 self.ocr_* 属性 —
        # ImageProcessor 是 module-level 单例 (get_image_processor)，跨 await 修改
        # 属性会污染并发请求（其它短图 OCR 会读到长图专用 key/model）。
        ocr_override = (
            self.long_chat_ocr_api_key,
            self.long_chat_ocr_base_url,
            self.long_chat_ocr_model,
        )
        logger.info(
            "[long-chat] using dedicated OCR override: model=%s, base_url=%s",
            ocr_override[2],
            ocr_override[1],
        )
        result = await self._process_long_private_chat_image(
            image_bytes=image_bytes,
            additional_context=additional_context,
            ocr_override=ocr_override,
        )
        result["screenshot_type"] = "private_chat_screenshot"
        return result

    async def process_image(
        self,
        image_bytes: bytes,
        screenshot_type: ScreenshotType,
        additional_context: Optional[str] = None
    ) -> dict:
        """
        处理图片，返回结构化文本
        """
        image_meta = self._get_long_image_meta(image_bytes)
        requested_type = screenshot_type
        force_long_chat = False
        long_chat_reason = None

        if image_meta.get("is_candidate"):
            if requested_type == "private_chat_screenshot":
                force_long_chat = True
                long_chat_reason = "requested_chat_type"
            elif requested_type != "group_chat_screenshot":
                probe_result = await self._probe_long_chat_candidate(image_bytes, image_meta=image_meta)
                if probe_result.get("matched_chat"):
                    force_long_chat = True
                    long_chat_reason = probe_result.get("reason") or "long_chat_slice_probe"

        if force_long_chat:
            logger.info(
                "[long-chat] forcing private chat dedicated OCR + segmented pipeline: requested_type=%s width=%s height=%s reason=%s",
                requested_type,
                image_meta.get("width"),
                image_meta.get("height"),
                long_chat_reason,
            )
            return await self._process_long_private_chat_with_dedicated_ocr(
                image_bytes=image_bytes,
                additional_context=additional_context,
            )

        return await self._process_image_single_pass(
            image_bytes=image_bytes,
            screenshot_type=screenshot_type,
            additional_context=additional_context,
        )


# 全局单例
_image_processor: Optional[ImageProcessor] = None


def get_image_processor() -> ImageProcessor:
    """获取图片处理器实例（单例）"""
    global _image_processor
    if _image_processor is None:
        _image_processor = ImageProcessor()
    return _image_processor
