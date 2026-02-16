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
        
        if not self.type_detect_api_key or not self.type_detect_model:
            logger.warning("第一节点(类型识别)模型配置不完整，detect_type 可能不可用")
        if not self.ocr_api_key or not self.ocr_model:
            logger.warning("第二节点(OCR)模型配置不完整，process_image 可能不可用")
    
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
            self._http_client = httpx.AsyncClient(timeout=timeout, limits=limits)
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
    
    async def process_image(
        self, 
        image_bytes: bytes, 
        screenshot_type: ScreenshotType,
        additional_context: Optional[str] = None
    ) -> dict:
        """
        处理图片，返回结构化文本
        """
        import time
        t0 = time.monotonic()
        logger.info(
            "[process_image] 开始: type=%s, image_size=%d bytes, context=%s, "
            "ocr_model=%s, ocr_base_url=%s, ocr_api_key=%s...",
            screenshot_type, len(image_bytes),
            repr(additional_context[:80]) if additional_context else None,
            self.ocr_model, self.ocr_base_url, (self.ocr_api_key or "")[:8],
        )

        if not self.ocr_api_key:
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
                "model": self.ocr_model,
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
                api_key=self.ocr_api_key,
                base_url=self.ocr_base_url,
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
            
            elapsed = (time.monotonic() - t0) * 1000
            logger.info(
                "[process_image] 成功: text_len=%d, elapsed=%.1fms, preview=%r",
                len(text), elapsed, text[:200],
            )
            return {
                "success": True,
                "text": text,
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


# 全局单例
_image_processor: Optional[ImageProcessor] = None


def get_image_processor() -> ImageProcessor:
    """获取图片处理器实例（单例）"""
    global _image_processor
    if _image_processor is None:
        _image_processor = ImageProcessor()
    return _image_processor
