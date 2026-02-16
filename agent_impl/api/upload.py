from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from typing import Literal, Optional
import logging
from auth_utils import get_optional_user

ScreenshotType = Literal[
    "private_chat_screenshot",
    "group_chat_screenshot",
    "moments_screenshot",
    "other_social_media_screenshot",
    "universal_screenshot_analysis",
]

router = APIRouter()
logger = logging.getLogger(__name__)


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
    import time
    t0 = time.monotonic()
    logger.info(
        "[upload-screenshot] 收到截图上传: type=%s, session=%s, filename=%s, content_type=%s",
        screenshot_type, session_id, file.filename, file.content_type,
    )

    try:
        image_bytes = await file.read()
        logger.info("[upload-screenshot] 读取图片成功: size=%d bytes", len(image_bytes))
    except Exception as e:
        logger.error("[upload-screenshot] 读取图片失败: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    # 整体 try/except：确保所有异常都记录到 backend.log（而非仅 uvicorn stderr）
    try:
        from api.sdk_client import ensure_thread_exists
        from supabase_service.client import upload_user_image
        from utils.image_processor import get_image_processor

        # 1. 上传到 Supabase Storage
        user_id = current_user['user_id'] if current_user else "anonymous"
        logger.info("[upload-screenshot] ensure_thread_exists: session=%s, user=%s", session_id, user_id)
        await ensure_thread_exists(session_id, user_id if user_id != "anonymous" else None)
        logger.info("[upload-screenshot] ensure_thread_exists 完成")

        t1 = time.monotonic()
        upload_result = await upload_user_image(
            user_id=user_id,
            image_data=image_bytes,
            filename=file.filename or "screenshot.png"
        )
        t2 = time.monotonic()

        if not upload_result['success']:
            logger.warning(
                "[upload-screenshot] Supabase 存储失败 (%.1fms): error=%s",
                (t2 - t1) * 1000, upload_result.get("error"),
            )
        else:
            logger.info(
                "[upload-screenshot] Supabase 存储成功 (%.1fms): url=%s",
                (t2 - t1) * 1000, upload_result.get("url"),
            )

        # 2. 调用多模态模型处理 (OCR)
        processor = get_image_processor()
        logger.info(
            "[upload-screenshot] 开始 OCR 处理: model=%s, base_url=%s",
            processor.ocr_model, processor.ocr_base_url,
        )
        t3 = time.monotonic()
        try:
            result = await processor.process_image(
                image_bytes=image_bytes,
                screenshot_type=screenshot_type,
                additional_context=context
            )
        except Exception as e:
            logger.error("[upload-screenshot] OCR 处理抛出异常: %s", e, exc_info=True)
            result = {
                "success": False,
                "text": "",
                "screenshot_type": screenshot_type,
                "error": f"OCR 处理异常: {str(e)}"
            }
        t4 = time.monotonic()

        # 3. 将图片 URL 注入到结果中
        if upload_result['success']:
            result['image_url'] = upload_result['url']
            result['storage_path'] = upload_result['path']

        text_preview = (result.get("text") or "")[:200]
        logger.info(
            "[upload-screenshot] 处理完成: success=%s, ocr_time=%.1fms, total_time=%.1fms, "
            "text_len=%d, text_preview=%r, error=%s",
            result.get("success"),
            (t4 - t3) * 1000,
            (t4 - t0) * 1000,
            len(result.get("text") or ""),
            text_preview,
            result.get("error"),
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        logger.error(
            "[upload-screenshot] ‼️ 未捕获异常 (%.1fms): %s",
            elapsed, e, exc_info=True,
        )
        return {
            "success": False,
            "text": "",
            "screenshot_type": screenshot_type,
            "error": f"服务器内部错误: {type(e).__name__}: {str(e)}"
        }


@router.post("/detect-type")
async def detect_screenshot_type(
    file: UploadFile = File(...),
    current_user = Depends(get_optional_user)
):
    """
    自动识别截图类型
    """
    _ = current_user  # 预留权限扩展，当前接口仅做可选登录校验

    try:
        image_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    from utils.image_processor import get_image_processor

    processor = get_image_processor()
    result = await processor.detect_type(image_bytes=image_bytes)
    return result
