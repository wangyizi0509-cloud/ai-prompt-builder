"""
LangGraph Studio 兼容服务器
创建一个简单的服务器来暴露 LangGraph API，供 Studio 连接
"""

import os
import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from graph.workflow import get_workflow

app = FastAPI(title="LangGraph Studio Server")

# 允许 CORS（Studio 需要跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 获取工作流
workflow = get_workflow()

@app.get("/")
async def root():
    return {
        "message": "LangGraph Studio Server",
        "status": "running",
        "graph": "crushe_agent"
    }

@app.get("/api/assistants")
async def list_assistants():
    """列出可用的 assistants (graphs)"""
    return {
        "assistants": [
            {
                "assistant_id": "crushe_agent",
                "name": "crushe_agent",
                "description": "AI恋爱军师 Agent - 主工作流",
                "graph_id": "crushe_agent"
            }
        ]
    }

@app.get("/api/assistants/{assistant_id}")
async def get_assistant(assistant_id: str):
    """获取 assistant 详情"""
    if assistant_id == "crushe_agent":
        return {
            "assistant_id": "crushe_agent",
            "name": "crushe_agent",
            "description": "AI恋爱军师 Agent - 主工作流",
            "graph_id": "crushe_agent"
        }
    return {"error": "Assistant not found"}

@app.get("/api/threads")
async def list_threads():
    """列出所有线程"""
    return {"threads": []}

@app.post("/api/assistants/{assistant_id}/threads")
async def create_thread(assistant_id: str):
    """创建新线程"""
    import uuid
    thread_id = str(uuid.uuid4())
    return {
        "thread_id": thread_id,
        "assistant_id": assistant_id
    }

@app.get("/api/threads/{thread_id}")
async def get_thread(thread_id: str):
    """获取线程详情"""
    return {
        "thread_id": thread_id,
        "values": {}
    }

@app.post("/api/threads/{thread_id}/runs")
async def create_run(thread_id: str, input: dict):
    """创建并执行 run"""
    from pydantic import BaseModel
    
    class RunRequest(BaseModel):
        assistant_id: str = "crushe_agent"
        input: dict = {}
    
    try:
        # 从 input 中提取实际输入
        actual_input = input.get("input", input)
        result = workflow.invoke(actual_input)
        import uuid
        run_id = str(uuid.uuid4())
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "success",
            "values": result
        }
    except Exception as e:
        import uuid
        run_id = str(uuid.uuid4())
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "error",
            "error": str(e)
        }

@app.get("/api/threads/{thread_id}/runs/{run_id}")
async def get_run(thread_id: str, run_id: str):
    """获取 run 状态"""
    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "status": "completed"
    }

@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}

@app.get("/api/health")
async def api_health():
    """API 健康检查"""
    return {"status": "ok", "version": "1.0"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 2024))
    print(f"🚀 启动 LangGraph Studio 服务器...")
    print(f"📡 API: http://localhost:{port}")
    print(f"🌐 Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)

