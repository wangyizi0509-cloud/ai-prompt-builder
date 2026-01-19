from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Literal, Optional

ScreenshotType = Literal[
    "private_chat_screenshot",
    "group_chat_screenshot",
    "moments_screenshot",
    "other_social_media_screenshot",
    "universal_screenshot_analysis",
]

router = APIRouter()


@router.post("/upload-screenshot")
async def upload_screenshot(
    file: UploadFile = File(...),
    screenshot_type: ScreenshotType = Form(...),
    session_id: str = Form(...),
    context: Optional[str] = Form(None)
):
    """
    上传截图并转换为文本
    
    Args:
        file: 图片文件
        screenshot_type: 截图类型 (private_chat_screenshot / group_chat_screenshot / moments_screenshot / other_social_media_screenshot)
        session_id: 会话 ID
        context: 用户补充说明（可选）
    
    Returns:
        {
            "success": bool,
            "text": str,  # 提取的文本，可直接作为用户输入
            "screenshot_type": str,
            "error": str | None
        }
    """
    print(f"📷 收到截图上传: type={screenshot_type}, session={session_id}")
    
    try:
        image_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")
    
    from utils.image_processor import get_image_processor
    processor = get_image_processor()
    result = await processor.process_image(
        image_bytes=image_bytes,
        screenshot_type=screenshot_type,
        additional_context=context
    )
    
    print(f"📷 处理结果: success={result['success']}")
    
    return result
