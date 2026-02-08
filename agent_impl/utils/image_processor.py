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
from typing import Literal, Optional
from dotenv import load_dotenv

load_dotenv()

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
        print(f"Error loading prompt for {screenshot_type}: {e}")
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
        
        if not self.api_key or not self.model:
            print("⚠️ 警告: DOUBAO_API_KEY 或 DOUBAO_ENDPOINT_ID 未配置，图片处理功能将不可用")
    
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

    async def _post_chat_completion(self, payload: dict) -> dict:
        """调用豆包接口，包含基础重试，规避瞬时连接抖动。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        retryable_status_codes = {408, 429, 500, 502, 503, 504}
        max_attempts = max(1, self.max_retries + 1)

        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                if response.status_code in retryable_status_codes and attempt < max_attempts:
                    await asyncio.sleep(min(1.5, 0.4 * attempt))
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response.status_code in retryable_status_codes and attempt < max_attempts:
                    await asyncio.sleep(min(1.5, 0.4 * attempt))
                    continue
                raise
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
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

        if not self.api_key:
            return {
                "success": False,
                "screenshot_type": default_type,
                "confidence": "low",
                "reason": None,
                "error": "豆包 API Key 未配置",
            }

        try:
            prompt = load_screenshot_prompt("type_detection")
            image_data_url = self._build_image_data_url(image_bytes)

            payload = {
                "model": self.model,
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
                "max_tokens": 500,
            }
            result = await self._post_chat_completion(payload)

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
        
        Args:
            image_bytes: 图片的字节数据
            screenshot_type: 截图类型，决定使用哪个 prompt
            additional_context: 额外的上下文信息（可选）
        
        Returns:
            {
                "success": bool,
                "text": str,  # 提取的文本内容
                "screenshot_type": str,
                "error": str | None
            }
        """
        if not self.api_key:
            return {
                "success": False,
                "text": "",
                "screenshot_type": screenshot_type,
                "error": "豆包 API Key 未配置"
            }
        
        try:
            # 构建 prompt
            base_prompt = self._get_prompt_for_type(screenshot_type)
            if additional_context:
                base_prompt = f"{base_prompt}\n\n【用户补充说明】\n{additional_context}"
            
            # 构建请求
            image_data_url = self._build_image_data_url(image_bytes)
            
            # 豆包 Vision API 兼容 OpenAI 格式
            payload = {
                "model": self.model,
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
                "max_tokens": 2000
            }
            result = await self._post_chat_completion(payload)
            
            # 提取文本
            choices = result.get("choices")
            if not choices or not isinstance(choices, list):
                raise ValueError("豆包返回格式异常: 缺少 choices")
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            text = message.get("content") if isinstance(message, dict) else None
            if not isinstance(text, str):
                raise ValueError("豆包返回格式异常: message.content 非字符串")
            
            return {
                "success": True,
                "text": text,
                "screenshot_type": screenshot_type,
                "error": None
            }
            
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "text": "",
                "screenshot_type": screenshot_type,
                "error": f"API 请求失败: {e.response.status_code} - {e.response.text}"
            }
        except Exception as e:
            err_text = str(e).strip()
            if not err_text:
                err_text = f"{type(e).__name__}: {repr(e)}"
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
