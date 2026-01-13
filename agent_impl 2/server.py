import os
import sys
import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Literal, Optional

# Add path to ensure imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from graph.workflow import get_workflow
from graph.state import create_initial_state
from graph.archive_manager import archive_guide_on_completion
from graph.context_builder import check_and_compress_if_needed
from utils.image_processor import get_image_processor, ScreenshotType
from datetime import datetime

app = FastAPI(title="Crushe AI Agent")

class ChatRequest(BaseModel):
    message: str
    session_id: str

class CompleteGuideRequest(BaseModel):
    guide_id: str
    execution_status: Literal["perfect", "good", "normal", "failed", "skipped"]
    feedback: Optional[str] = ""
    session_id: str

# Simple in-memory session storage
sessions = {}


# ============ 图片上传接口 ============

@app.post("/api/upload-screenshot")
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
    
    # 读取图片
    try:
        image_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取图片失败: {str(e)}")
    
    # 调用多模态模型处理
    processor = get_image_processor()
    result = await processor.process_image(
        image_bytes=image_bytes,
        screenshot_type=screenshot_type,
        additional_context=context
    )
    
    print(f"📷 处理结果: success={result['success']}")
    
    return result

@app.post("/api/chat")
async def chat(request: ChatRequest):
    print(f"Received message from session {request.session_id}: {request.message}")
    
    workflow = get_workflow()
    
    # Get or create state
    if request.session_id not in sessions:
        print("Creating new session")
        # For new session, create initial state
        state = create_initial_state(request.message)
    else:
        print("Restoring existing session")
        # For existing session, update with new message
        state = sessions[request.session_id].copy()
        state["user_message"] = request.message
        state["messages"].append({"role": "user", "content": request.message})
        
        # Clear debug log for the new turn so we only see current thought process
        state["debug_log"] = []
        # Clear inquiry_card from previous turn to avoid residual questions
        state["inquiry_card"] = None
        state["pending_questions"] = []
        # Clear pending_responses for the new turn
        state["pending_responses"] = []
        # Clear last_response_for_continuity
        state["last_response_for_continuity"] = None

    # Invoke workflow
    try:
        print("Invoking workflow...")
        final_state = workflow.invoke(state)
        
        # 检查并执行对话压缩（如果需要）
        compression_updates = check_and_compress_if_needed(final_state)
        if compression_updates:
            final_state.update(compression_updates)
            print(f"[Server] Conversation compressed, kept {len(final_state.get('messages', []))} messages")
        
        # Update session
        sessions[request.session_id] = final_state
        
        # 处理 pending_responses
        pending_responses = final_state.get("pending_responses", [])
        
        # 向后兼容：合并所有回复为单个 response 字符串
        if pending_responses:
            combined_response = "\n\n".join([r["content"] for r in pending_responses if r.get("content")])
        else:
            combined_response = ""
        
        # Return response and state (including debug_log)
        return {
            "response": combined_response,
            "pending_responses": pending_responses,  # 新增：分条回复列表
            "state": final_state
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============ 完成指南接口 ============

@app.post("/api/complete_guide")
async def complete_guide(request: CompleteGuideRequest):
    """
    标记行动指南为已完成并归档
    
    Args:
        request: 包含指南ID、执行状态、反馈和会话ID
    
    Returns:
        更新后的状态
    """
    print(f"✅ 收到完成指南请求: guide_id={request.guide_id}, status={request.execution_status}, session={request.session_id}")
    
    # 获取会话状态
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    state = sessions[request.session_id]
    
    # 查找指南
    action_guides = state.get("action_guides", [])
    guide_index = None
    guide = None
    
    for idx, g in enumerate(action_guides):
        if g.get("id") == request.guide_id:
            guide_index = idx
            guide = g
            break
    
    if not guide:
        raise HTTPException(status_code=404, detail=f"Guide with id {request.guide_id} not found")
    
    if guide.get("status") == "completed":
        # 已经完成，直接返回
        return {"state": state}
    
    # 更新指南状态
    updated_guide = guide.copy()
    updated_guide["status"] = "completed"
    updated_guide["completed_at"] = datetime.now().isoformat()
    updated_guide["execution_status"] = request.execution_status
    updated_guide["user_feedback"] = request.feedback
    
    # 更新 state 中的指南列表
    updated_guides = list(action_guides)
    updated_guides[guide_index] = updated_guide
    state["action_guides"] = updated_guides
    
    # 调用归档函数
    try:
        archive_updates = archive_guide_on_completion(updated_guide, state)
        
        # 合并归档更新到 state
        if "history_archive" in archive_updates:
            state["history_archive"] = archive_updates["history_archive"]
        if "user_context" in archive_updates:
            state["user_context"] = archive_updates["user_context"]
        
        print(f"✅ 指南归档完成: guide_id={request.guide_id}")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"⚠️ 归档失败: {str(e)}")
        # 即使归档失败，也更新状态为已完成
    
    # 更新会话
    sessions[request.session_id] = state
    
    return {
        "success": True,
        "state": state
    }


# ============ 调试接口 ============

@app.get("/api/debug/context/{session_id}")
async def get_debug_context(session_id: str):
    """
    获取当前会话的上下文调试信息
    
    返回分层的上下文状态，用于前端调试面板显示
    """
    state = sessions.get(session_id, {})
    
    if not state:
        return {
            "error": "Session not found",
            "session_id": session_id,
            "layer1_static": None,
            "layer2_working": None,
            "layer3_conversation": None,
            "layer4_archive": None,
            "crush_chat": None,
        }
    
    # 获取用户上下文（Layer 1）
    user_context = state.get("user_context", {})
    
    # 获取历史归档（Layer 4）
    history_archive = state.get("history_archive", {})
    
    # 获取 Crush 聊天存储
    crush_chat_storage = state.get("crush_chat_storage", {})
    
    return {
        "session_id": session_id,
        "layer1_static": {
            "user_info": user_context.get("user_info", {}),
            "crush_info": user_context.get("crush_info", {}),
            "both_info": user_context.get("both_info", {}),
        },
        "layer2_working": {
            "status_report": state.get("status_report"),
            "action_plan": state.get("action_plan"),
            "action_guides": state.get("action_guides", []),
            "recent_messages": state.get("messages", [])[-10:] if state.get("messages") else [],
        },
        "layer3_conversation": {
            "message_count": len(state.get("messages", [])),
            "compression_threshold": 45,
            "needs_compression": len(state.get("messages", [])) > 45,
            "messages_preview": state.get("messages", [])[-5:] if state.get("messages") else [],
        },
        "layer4_archive": {
            "status_history_count": len(history_archive.get("status_history", [])),
            "guide_history_count": len(history_archive.get("guide_history", [])),
            "plan_history_count": len(history_archive.get("plan_history", [])),
            "conversation_archive_count": len(history_archive.get("conversation_archive", [])),
            "status_history": history_archive.get("status_history", []),
            "guide_history": history_archive.get("guide_history", []),
        },
        "crush_chat": {
            "metadata": crush_chat_storage.get("metadata", {}) if crush_chat_storage else {},
            "summary": crush_chat_storage.get("summary", {}) if crush_chat_storage else {},
        },
    }


# Mount frontend static files
# We mount this LAST to ensure API routes are checked first
frontend_path = os.path.join(current_dir, "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
else:
    print(f"Warning: Frontend path not found: {frontend_path}")

if __name__ == "__main__":
    print("Starting server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
