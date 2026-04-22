from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from typing import Any, Literal, Optional
import logging
from auth_utils import get_optional_user

ScreenshotType = Literal[
    "private_chat_screenshot",
    "group_chat_screenshot",
    "moments_screenshot",
    "other_social_media_screenshot",
    "universal_screenshot_analysis",
    "screenshot",  # 通用截图类型，后端自动识别具体类型
]

router = APIRouter()
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 内部 helper —— 把「上传到存储」和「OCR」拆开，既给新端点用，也保持原
# /upload-screenshot 的外部契约不变（向后兼容旧前端 / 主聊天页 / 主 agent）。
# --------------------------------------------------------------------------- #


async def _do_upload(
    *,
    image_bytes: bytes,
    filename: str,
    session_id: str,
    user_id: str,
    eval_mode: bool,
) -> dict[str, Any]:
    """仅做"上传到 Supabase / 占位"，返回 {success, url, path, error}。

    - eval_mode=true 时跳过 Supabase，直接返回 success=true + url=""（本地占位）
    - 非 eval_mode 时，先 ensure_thread_exists 再 upload_user_image
    """
    import time

    if eval_mode:
        # eval_mode 下不走 Supabase，URL 留空——analyze 会以"无图"模式工作（纯文本分析，
        # GLM-4.6V 仍能基于自由描述给出结构化首发钩子，已在 benchmark 验证）。
        # 线上正式链路走非 eval_mode 分支，Supabase 存完后返回公开 HTTPS URL。
        logger.info(
            "[upload] eval_mode=1: 跳过 Supabase 存储（URL 留空，analyze 走纯文本）, session=%s",
            session_id,
        )
        return {"success": True, "url": "", "path": "", "error": None, "eval_mode": True}

    from api.sdk_client import ensure_thread_exists
    from supabase_service.client import upload_user_image

    logger.info(
        "[upload] ensure_thread_exists: session=%s, user=%s", session_id, user_id
    )
    await ensure_thread_exists(session_id, user_id if user_id != "anonymous" else None)

    t0 = time.monotonic()
    upload_result = await upload_user_image(
        user_id=user_id,
        image_data=image_bytes,
        filename=filename or "screenshot.png",
    )
    t1 = time.monotonic()

    if not upload_result.get("success"):
        logger.warning(
            "[upload] Supabase 存储失败 (%.1fms): error=%s",
            (t1 - t0) * 1000,
            upload_result.get("error"),
        )
    else:
        logger.info(
            "[upload] Supabase 存储成功 (%.1fms): url=%s",
            (t1 - t0) * 1000,
            upload_result.get("url"),
        )
    return upload_result


async def _do_ocr(
    *,
    image_bytes: bytes,
    screenshot_type: str,
    context: Optional[str],
) -> dict[str, Any]:
    """仅做 OCR，返回 {success, text, screenshot_type, error}。

    处理 "screenshot" 通用占位类型的自动识别。
    """
    import time

    from utils.image_processor import get_image_processor

    processor = get_image_processor()
    logger.info(
        "[ocr] 开始 OCR 处理: type=%s, model=%s, base_url=%s",
        screenshot_type,
        processor.ocr_model,
        processor.ocr_base_url,
    )

    resolved_type = screenshot_type
    if screenshot_type == "screenshot":
        detect_result = await processor.detect_type(image_bytes=image_bytes)
        resolved_type = (
            detect_result.get("screenshot_type") or "universal_screenshot_analysis"
        )
        logger.info(
            "[ocr] 通用截图类型自动识别: detected=%s, confidence=%s",
            resolved_type,
            detect_result.get("confidence"),
        )

    t0 = time.monotonic()
    try:
        result = await processor.process_image(
            image_bytes=image_bytes,
            screenshot_type=resolved_type,
            additional_context=context,
        )
    except Exception as e:
        logger.error("[ocr] OCR 处理抛出异常: %s", e, exc_info=True)
        result = {
            "success": False,
            "text": "",
            "screenshot_type": screenshot_type,
            "error": f"OCR 处理异常: {str(e)}",
        }
    t1 = time.monotonic()

    text_preview = (result.get("text") or "")[:200]
    logger.info(
        "[ocr] 处理完成: success=%s, ocr_time=%.1fms, text_len=%d, preview=%r, error=%s",
        result.get("success"),
        (t1 - t0) * 1000,
        len(result.get("text") or ""),
        text_preview,
        result.get("error"),
    )
    return result


# --------------------------------------------------------------------------- #
# 端点 1：/upload-screenshot —— 原有合并端点（上传 + OCR 一次完成，向后兼容）
# --------------------------------------------------------------------------- #


@router.post("/upload-screenshot")
async def upload_screenshot(
    file: UploadFile = File(...),
    screenshot_type: ScreenshotType = Form(...),
    session_id: str = Form(...),
    context: Optional[str] = Form(None),
    eval_mode: bool = Form(False),
    current_user=Depends(get_optional_user),
):
    """
    上传截图并转换为文本（合并端点，向后兼容）。

    Onboarding v2 已经改用 `/upload-only` + `/ocr-only` 两段并行，但主聊天页
    和其他 inquiry_card 仍用这个合并端点，不要删。
    """
    import time

    t0 = time.monotonic()
    logger.info(
        "[upload-screenshot] 收到截图上传: type=%s, session=%s, filename=%s, content_type=%s",
        screenshot_type,
        session_id,
        file.filename,
        file.content_type,
    )

    try:
        image_bytes = await file.read()
        logger.info(
            "[upload-screenshot] 读取图片成功: size=%d bytes", len(image_bytes)
        )
    except Exception as e:
        logger.error("[upload-screenshot] 读取图片失败: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    try:
        user_id = current_user["user_id"] if current_user else "anonymous"

        # 1. 上传
        upload_result = await _do_upload(
            image_bytes=image_bytes,
            filename=file.filename or "screenshot.png",
            session_id=session_id,
            user_id=user_id,
            eval_mode=eval_mode,
        )

        # 2. OCR
        result = await _do_ocr(
            image_bytes=image_bytes,
            screenshot_type=screenshot_type,
            context=context,
        )

        # 3. 合并：把图片 URL 注入到 OCR 结果里（与旧契约完全一致）
        if upload_result.get("success") and upload_result.get("url"):
            result["image_url"] = upload_result["url"]
            result["storage_path"] = upload_result.get("path")
        if eval_mode:
            result["eval_mode"] = True

        logger.info(
            "[upload-screenshot] 处理完成: success=%s, eval_mode=%s, total_time=%.1fms",
            result.get("success"),
            eval_mode,
            (time.monotonic() - t0) * 1000,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        elapsed = (time.monotonic() - t0) * 1000
        logger.error(
            "[upload-screenshot] ‼️ 未捕获异常 (%.1fms): %s", elapsed, e, exc_info=True
        )
        return {
            "success": False,
            "text": "",
            "screenshot_type": screenshot_type,
            "error": f"服务器内部错误: {type(e).__name__}: {str(e)}",
        }


# --------------------------------------------------------------------------- #
# 端点 2：/upload-only —— 只上传，不跑 OCR（~2s 返回，给 onboarding v2 前端
# 并行化用：前端一拿到 URL 就能立刻触发 /api/onboarding/analyze）
# --------------------------------------------------------------------------- #


@router.post("/upload-only")
async def upload_only(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    eval_mode: bool = Form(False),
    current_user=Depends(get_optional_user),
):
    """仅做「上传图片 → 拿到 URL」，不跑 OCR。返回 {success, url, path, error}。

    onboarding v2 前端并行化：上传完立刻 refresh 提交按钮，OCR 在后台另一路跑。
    """
    import time

    t0 = time.monotonic()
    logger.info(
        "[upload-only] 收到: session=%s, filename=%s", session_id, file.filename
    )

    try:
        image_bytes = await file.read()
    except Exception as e:
        logger.error("[upload-only] 读取图片失败: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    user_id = current_user["user_id"] if current_user else "anonymous"
    try:
        result = await _do_upload(
            image_bytes=image_bytes,
            filename=file.filename or "screenshot.png",
            session_id=session_id,
            user_id=user_id,
            eval_mode=eval_mode,
        )
    except Exception as e:
        logger.error("[upload-only] ‼️ 未捕获异常: %s", e, exc_info=True)
        return {
            "success": False,
            "url": "",
            "path": "",
            "error": f"服务器内部错误: {type(e).__name__}: {str(e)}",
        }

    logger.info(
        "[upload-only] 完成: success=%s, time=%.1fms",
        result.get("success"),
        (time.monotonic() - t0) * 1000,
    )
    return result


# --------------------------------------------------------------------------- #
# 端点 3：/ocr-only —— 只跑 OCR，不上传（前端拿到 URL 后后台补 OCR 文本）
# --------------------------------------------------------------------------- #


@router.post("/ocr-only")
async def ocr_only(
    file: UploadFile = File(...),
    screenshot_type: ScreenshotType = Form(...),
    session_id: str = Form(...),
    context: Optional[str] = Form(None),
    current_user=Depends(get_optional_user),
):
    """仅跑 OCR，不做上传/存储。返回 {success, text, screenshot_type, error}。

    配合 /upload-only 实现 onboarding v2 前端并行化：前端用同一个文件发两次
    请求——一次拿 URL（快，给 analyze 用），一次拿 OCR 文本（慢，给 report 用）。
    """
    import time

    _ = current_user  # 预留鉴权扩展
    t0 = time.monotonic()
    logger.info(
        "[ocr-only] 收到: type=%s, session=%s, filename=%s",
        screenshot_type,
        session_id,
        file.filename,
    )

    try:
        image_bytes = await file.read()
    except Exception as e:
        logger.error("[ocr-only] 读取图片失败: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    try:
        result = await _do_ocr(
            image_bytes=image_bytes,
            screenshot_type=screenshot_type,
            context=context,
        )
    except Exception as e:
        logger.error("[ocr-only] ‼️ 未捕获异常: %s", e, exc_info=True)
        return {
            "success": False,
            "text": "",
            "screenshot_type": screenshot_type,
            "error": f"服务器内部错误: {type(e).__name__}: {str(e)}",
        }

    logger.info(
        "[ocr-only] 完成: success=%s, time=%.1fms",
        result.get("success"),
        (time.monotonic() - t0) * 1000,
    )
    return result


# --------------------------------------------------------------------------- #
# 端点 4：/detect-type —— 仅做类型识别（保留）
# --------------------------------------------------------------------------- #


@router.post("/detect-type")
async def detect_screenshot_type(
    file: UploadFile = File(...),
    current_user=Depends(get_optional_user),
):
    """自动识别截图类型"""
    _ = current_user

    try:
        image_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")

    from utils.image_processor import get_image_processor

    processor = get_image_processor()
    result = await processor.detect_type(image_bytes=image_bytes)
    return result
