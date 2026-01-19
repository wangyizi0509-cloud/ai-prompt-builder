from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from typing import Literal, Optional
from auth_utils import get_optional_user

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
    context: Optional[str] = Form(None),
    current_user = Depends(get_optional_user)
):
    """
    上传截图并转换为文本
    """
    print(f"📷 收到截图上传: type={screenshot_type}, session={session_id}")
    
    try:
        image_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")
    
    from api.sdk_client import ensure_thread_exists
    from supabase_service.client import upload_user_image
    from utils.image_processor import get_image_processor

    # 1. 上传到 Supabase Storage
    user_id = current_user['user_id'] if current_user else "anonymous"
    # 确保 thread 存在以便关联 (虽然这里主要是为了 user_id)
    await ensure_thread_exists(session_id, user_id if user_id != "anonymous" else None)
    
    upload_result = await upload_user_image(
        user_id=user_id,
        image_data=image_bytes,
        filename=file.filename or "screenshot.png"
    )
    
    if not upload_result['success']:
        print(f"⚠️ 图片上传 Supabase 失败: {upload_result.get('error')}")
        # 继续 OCR 处理，但不中断流程
    else:
        print(f"✅ 图片已存储到 Supabase: {upload_result.get('url')}")

    # 2. 调用多模态模型处理 (OCR)
    processor = get_image_processor()
    result = await processor.process_image(
        image_bytes=image_bytes,
        screenshot_type=screenshot_type,
        additional_context=context
    )
    
    # 3. 将图片 URL 注入到结果中
    if upload_result['success']:
        result['image_url'] = upload_result['url']
        result['storage_path'] = upload_result['path']
    
    print(f"📷 处理结果: success={result['success']}")
    
    return result

