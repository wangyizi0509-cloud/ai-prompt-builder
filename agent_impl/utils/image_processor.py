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
import httpx
import logging
from typing import Literal, Optional
from dotenv import load_dotenv

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
        
        if not self.api_key or not self.model:
            logger.warning("DOUBAO_API_KEY 或 DOUBAO_ENDPOINT_ID 未配置，图片处理功能将不可用")
    
    def _encode_image_to_base64(self, image_bytes: bytes) -> str:
        """将图片字节转为 base64"""
        return base64.b64encode(image_bytes).decode("utf-8")
    
    def _get_prompt_for_type(self, screenshot_type: ScreenshotType) -> str:
        """根据截图类型获取对应的 prompt"""
        return load_screenshot_prompt(screenshot_type)
    
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
            base64_image = self._encode_image_to_base64(image_bytes)
            
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
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 2000
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
            
            # 提取文本
            text = result["choices"][0]["message"]["content"]
            
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
            return {
                "success": False,
                "text": "",
                "screenshot_type": screenshot_type,
                "error": f"处理失败: {str(e)}"
            }


# 全局单例
_image_processor: Optional[ImageProcessor] = None


def get_image_processor() -> ImageProcessor:
    """获取图片处理器实例（单例）"""
    global _image_processor
    if _image_processor is None:
        _image_processor = ImageProcessor()
    return _image_processor
