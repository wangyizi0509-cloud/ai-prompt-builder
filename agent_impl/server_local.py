"""
本地直接运行模式 - 不需要 langgraph dev / Docker
直接在进程内运行 LangGraph workflow
"""
import os
import sys
import uuid
import hashlib
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio

# 添加当前目录到 path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# 加载 .env
from dotenv import load_dotenv
load_dotenv(os.path.join(current_dir, ".env"))

# 导入 workflow
from graph.workflow import create_workflow
from langgraph.checkpoint.memory import MemorySaver

app = FastAPI(title="Crushe AI Agent (Local Mode)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("=" * 60)
print("🚀 LOCAL MODE - 不需要 langgraph dev / Docker")
print("=" * 60)

# 创建带 checkpointer 的 workflow
checkpointer = MemorySaver()
workflow = create_workflow()
graph = workflow.compile(checkpointer=checkpointer)
print("✅ Workflow 编译完成")


def session_to_thread_id(session_id: str) -> str:
    """将任意 session_id 转换为有效的 UUID"""
    try:
        uuid.UUID(session_id)
        return session_id
    except ValueError:
        hash_obj = hashlib.md5(session_id.encode())
        hex_digest = hash_obj.hexdigest()
        return str(uuid.UUID(hex=hex_digest[:32]))


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    user_id: Optional[str] = None
    images: Optional[List[str]] = None  # base64 encoded images


class ChatResponse(BaseModel):
    response: str
    session_id: str
    metadata: Optional[Dict[str, Any]] = None


@app.get("/ok")
async def health_check():
    """健康检查端点 - 兼容 langgraph server"""
    return {"ok": True}


@app.get("/api/health")
async def api_health():
    """API 健康检查"""
    return {"status": "ok", "mode": "local"}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """聊天 API - 同步模式"""
    thread_id = session_to_thread_id(request.session_id)
    
    # 构建消息
    content = []
    if request.message:
        content.append({"type": "text", "text": request.message})
    if request.images:
        for img in request.images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img}"}
            })
    
    # 如果只有文本，简化格式
    if len(content) == 1 and content[0]["type"] == "text":
        message_content = request.message
    else:
        message_content = content
    
    current_message_id = str(uuid.uuid4())
    input_data = {
        "user_message": message_content,
        "current_message_id": current_message_id,
        "messages": [{"role": "user", "content": message_content, "id": current_message_id}],
        "user_id": request.user_id or "anonymous",
    }
    
    config = {"configurable": {"thread_id": thread_id}, "checkpointer": checkpointer}
    
    try:
        result = await asyncio.to_thread(graph.invoke, input_data, config)
        
        # 提取最后一条助手消息
        messages = result.get("messages", [])
        assistant_msg = ""
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                assistant_msg = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
            elif isinstance(msg, dict) and msg.get("role") == "assistant":
                assistant_msg = msg.get("content", "")
                break
        
        return ChatResponse(
            response=assistant_msg or "抱歉，我没有生成回复",
            session_id=request.session_id,
            metadata={"thread_id": thread_id}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "detail": traceback.format_exc()}
        )


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """聊天 API - 流式模式"""
    thread_id = session_to_thread_id(request.session_id)
    
    # 构建消息
    message_content = request.message
    if request.images:
        content = [{"type": "text", "text": request.message}]
        for img in request.images:
            content.append({
                "type": "image_url", 
                "image_url": {"url": f"data:image/jpeg;base64,{img}"}
            })
        message_content = content
    
    input_data = {
        "messages": [{"role": "user", "content": message_content}],
        "user_id": request.user_id or "anonymous",
    }
    
    config = {"configurable": {"thread_id": thread_id}, "checkpointer": checkpointer}
    
    async def generate():
        try:
            # 使用 stream 模式
            for chunk in graph.stream(input_data, config, stream_mode="messages"):
                if chunk:
                    # chunk 格式: (message, metadata)
                    if isinstance(chunk, tuple) and len(chunk) >= 1:
                        msg = chunk[0]
                        if hasattr(msg, "content") and msg.content:
                            content = msg.content
                            if isinstance(content, str):
                                yield f"data: {content}\n\n"
                            elif isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        yield f"data: {item['text']}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: [ERROR] {str(e)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# 挂载前端静态文件
frontend_path = os.path.join(current_dir, "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
    print(f"✅ 前端已挂载: {frontend_path}")
else:
    print(f"⚠️ 前端目录不存在: {frontend_path}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🌐 服务启动中...")
    print("=" * 60)
    print("📍 访问地址:")
    print("   - 前端界面: http://localhost:8000")
    print("   - API 文档: http://localhost:8000/docs")
    print("   - 健康检查: http://localhost:8000/ok")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
