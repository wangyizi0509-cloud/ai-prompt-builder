import os
import sys
import uvicorn
import json
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal, Optional
from langgraph.errors import GraphRecursionError

# Add path to ensure imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# [PERF] graph.* 相关导入非常重（会连带 langchain_openai/openai/tiktoken），
# 会显著拖慢服务冷启动（/docs 长时间不可达）。
# 因此改为在各 endpoint 内“按需懒加载”。
from utils.image_processor import ScreenshotType
from datetime import datetime

app = FastAPI(title="Crushe AI Agent")

# Configure CORS to allow all origins (for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

class ChatRequest(BaseModel):
    message: str
    session_id: str

class CompleteGuideRequest(BaseModel):
    guide_id: str
    execution_status: Literal["perfect", "good", "normal", "failed", "skipped"]
    feedback: Optional[str] = ""
    session_id: str


class UpdateGuideStatusRequest(BaseModel):
    guide_id: str
    new_status: Literal["in_progress", "completed", "paused", "cancelled", "expired"]
    feedback: Optional[str] = None
    # 可选：仅在 completed 时有意义（保留兼容旧前端埋点）
    execution_status: Optional[Literal["perfect", "good", "normal", "failed", "skipped"]] = None
    session_id: str

class StreamChatRequest(BaseModel):
    message: str
    session_id: str
    stream_mode: Optional[Literal["values", "updates", "messages", "debug"]] = "updates"

# 注意：主要状态存储依赖 LangGraph Checkpointer
# sessions 仅用于极简缓存/兼容（非持久化）
sessions = {}
LOG_PATH = Path("/Users/ant/Desktop/Crushe/模型策略/.cursor/debug.log")


#region agent log
def _append_debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict):
    payload = {
        "sessionId": "debug-session",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
#endregion


# ============================================================
# 异步维护任务：提纯/归档（best-effort，不阻塞用户回复）
# ============================================================

def _safe_update_state(workflow, config: dict, updates: dict) -> None:
    if updates and hasattr(workflow, "update_state"):
        workflow.update_state(config, updates)


def _run_maintenance_tasks(session_id: str) -> None:
    """
    后台消费 maintenance_queue。
    - 读取最新 state（避免拿到过期的 final_state）
    - best-effort 执行：失败记录在 queue item 里，下一轮可重试
    """
    from graph.workflow import get_workflow
    from graph.archive_manager import (
        refine_on_onboarding_complete,
        compress_layer3,
        compress_task_reasoning,
        archive_guide_to_layer2,
        archive_status_to_layer2,
        archive_plan_to_layer2,
    )
    workflow = get_workflow()
    config = {"configurable": {"thread_id": session_id}}

    checkpoint = workflow.get_state(config)
    state = checkpoint.values if checkpoint and checkpoint.values else None
    if not state:
        return

    queue = state.get("maintenance_queue") or []
    if not isinstance(queue, list) or not queue:
        return

    flags = state.get("maintenance_flags") if isinstance(state.get("maintenance_flags"), dict) else {}

    updated_queue = []
    any_changes = False

    for item in queue:
        if not isinstance(item, dict):
            continue

        task_type = item.get("type")
        task_key = item.get("task_key")
        status = item.get("status", "queued")

        # 已完成/跳过的不再执行
        if status in ("done", "skipped"):
            updated_queue.append(item)
            continue

        # 标记 running
        running_item = dict(item)
        running_item["status"] = "running"
        running_item["attempts"] = int(running_item.get("attempts", 0) or 0) + 1
        running_item["last_error"] = None
        updated_queue.append(running_item)
        any_changes = True
        _safe_update_state(workflow, config, {"maintenance_queue": updated_queue})

        try:
            #region agent log
            _append_debug_log(
                run_id="maintenance",
                hypothesis_id="M1",
                location="server.py:_run_maintenance_tasks:start",
                message="Maintenance task started",
                data={
                    "session_id": session_id,
                    "type": task_type,
                    "task_key": task_key,
                    "attempts": running_item.get("attempts"),
                },
            )
            #endregion

            updates = {}

            if task_type == "onboarding_refine":
                updates = refine_on_onboarding_complete(state)
                # 标记 done
                flags = dict(flags)
                flags["onboarding_refine_done"] = True
                flags["onboarding_refine_queued"] = False
                updates["maintenance_flags"] = flags

            elif task_type == "layer3_compress":
                updates = compress_layer3(state)

            elif task_type == "task_reasoning_compress":
                updates = compress_task_reasoning(state)

            elif task_type == "archive_guide":
                payload = item.get("payload") or {}
                guide_id = payload.get("guide_id")
                if guide_id:
                    guide_obj = None
                    for g in state.get("action_guides", []) or []:
                        if isinstance(g, dict) and g.get("id") == guide_id:
                            guide_obj = g
                            break
                    # 兼容：若旧字段未同步，尝试从 Layer2 真源读取
                    if not guide_obj:
                        layer2_memory = state.get("layer2_memory") or {}
                        guides2 = layer2_memory.get("all_action_guides", []) if isinstance(layer2_memory, dict) else []
                        for g in guides2 or []:
                            if isinstance(g, dict) and g.get("id") == guide_id:
                                guide_obj = g
                                break
                    if guide_obj:
                        updates = archive_guide_to_layer2(guide_obj, state)
                        # 记录已归档 guide_id，避免重复
                        flags = dict(flags)
                        archived = flags.get("archived_guide_ids") or []
                        if not isinstance(archived, list):
                            archived = []
                        if guide_id not in archived:
                            archived.append(guide_id)
                        flags["archived_guide_ids"] = archived
                        updates["maintenance_flags"] = flags
                    else:
                        # 找不到 guide，则跳过
                        updates = {}

            elif task_type == "archive_status":
                payload = item.get("payload") or {}
                report_uid = payload.get("report_uid")
                if report_uid:
                    old_report = None
                    layer2_memory = state.get("layer2_memory") or {}
                    reports = layer2_memory.get("all_status_reports", []) if isinstance(layer2_memory, dict) else []
                    for r in reports or []:
                        if isinstance(r, dict) and r.get("id") == report_uid:
                            old_report = r
                            break
                    if old_report:
                        updates = archive_status_to_layer2(old_report, state)
                        flags = dict(flags)
                        archived = flags.get("archived_status_ids") or []
                        if not isinstance(archived, list):
                            archived = []
                        if report_uid not in archived:
                            archived.append(report_uid)
                        flags["archived_status_ids"] = archived
                        updates["maintenance_flags"] = flags

            elif task_type == "archive_plan":
                payload = item.get("payload") or {}
                plan_uid = payload.get("plan_uid")
                if plan_uid:
                    old_plan = None
                    layer2_memory = state.get("layer2_memory") or {}
                    plans = layer2_memory.get("all_action_plans", []) if isinstance(layer2_memory, dict) else []
                    for p in plans or []:
                        if isinstance(p, dict) and p.get("id") == plan_uid:
                            old_plan = p
                            break
                    if old_plan:
                        updates = archive_plan_to_layer2(old_plan, state)
                        flags = dict(flags)
                        archived = flags.get("archived_plan_ids") or []
                        if not isinstance(archived, list):
                            archived = []
                        if plan_uid not in archived:
                            archived.append(plan_uid)
                        flags["archived_plan_ids"] = archived
                        updates["maintenance_flags"] = flags

            else:
                # 未识别任务类型：跳过（保留给后续版本）
                done_item = dict(running_item)
                done_item["status"] = "skipped"
                done_item["last_error"] = f"unknown_task_type:{task_type}"
                updated_queue[-1] = done_item
                _safe_update_state(workflow, config, {"maintenance_queue": updated_queue})
                continue

            # 写回 memory 变更（如果有）
            if updates:
                state.update(updates)
                _safe_update_state(workflow, config, updates)

            # 标记 done
            done_item = dict(updated_queue[-1])
            done_item["status"] = "done"
            done_item["finished_at"] = datetime.now().isoformat()
            updated_queue[-1] = done_item
            _safe_update_state(workflow, config, {"maintenance_queue": updated_queue})

            #region agent log
            _append_debug_log(
                run_id="maintenance",
                hypothesis_id="M2",
                location="server.py:_run_maintenance_tasks:done",
                message="Maintenance task done",
                data={
                    "session_id": session_id,
                    "type": task_type,
                    "task_key": task_key,
                    "updated_keys": list(updates.keys()) if isinstance(updates, dict) else [],
                },
            )
            #endregion

        except Exception as e:
            fail_item = dict(updated_queue[-1])
            fail_item["status"] = "failed"
            fail_item["last_error"] = str(e)
            updated_queue[-1] = fail_item
            _safe_update_state(workflow, config, {"maintenance_queue": updated_queue})

            #region agent log
            _append_debug_log(
                run_id="maintenance",
                hypothesis_id="M3",
                location="server.py:_run_maintenance_tasks:failed",
                message="Maintenance task failed",
                data={
                    "session_id": session_id,
                    "type": task_type,
                    "task_key": task_key,
                    "error": str(e),
                },
            )
            #endregion

    # 最终写回（以防中途未写）
    if any_changes:
        _safe_update_state(workflow, config, {"maintenance_queue": updated_queue})


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
    from utils.image_processor import get_image_processor
    processor = get_image_processor()
    result = await processor.process_image(
        image_bytes=image_bytes,
        screenshot_type=screenshot_type,
        additional_context=context
    )
    
    print(f"📷 处理结果: success={result['success']}")
    
    return result

@app.post("/api/chat")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    print(f"Received message from session {request.session_id}: {request.message}")
    
    from graph.workflow import get_workflow
    from graph.state import create_initial_state
    workflow = get_workflow()
    # [FIX] 避免复杂多 Agent / 多工具链路触发 LangGraph 递归上限导致 500
    # 说明：此上限只影响单次 invoke 内部的节点步数，不影响跨轮次状态。
    config = {"configurable": {"thread_id": request.session_id}, "recursion_limit": 80}
    
    # 从 Checkpointer 获取历史状态（若不存在则初始化）
    checkpoint = workflow.get_state(config)
    base_state = checkpoint.values if checkpoint and checkpoint.values else None
    if base_state is None:
        print("Creating new session (checkpointer empty)")
        state = create_initial_state(request.message)
    else:
        state = base_state
        # 仅更新当前用户消息，消息追加交由 router/add_messages 处理
        state["user_message"] = request.message
        # [FIX] 每次新一轮 /api/chat 开始都重置单轮步数计数器，避免跨轮次累计导致误判“循环”
        state["_iteration_count"] = 0
        # 清理上一轮残留
        state["debug_log"] = []
        state["inquiry_card"] = None
        state["pending_questions"] = []
        state["pending_responses"] = []
        state["last_response_for_continuity"] = None

    # Invoke workflow
    try:
        print("Invoking workflow...")
        #region agent log
        _append_debug_log(
            run_id="pre-fix",
            hypothesis_id="H3",
            location="server.py:chat:entry",
            message="Enter chat endpoint",
            data={
                "session_id": request.session_id,
                "message_preview": request.message[:100],
                "use_stream": False,
            },
        )
        #endregion
        try:
            final_state = workflow.invoke(state, config)
        except GraphRecursionError as e:
            # [FIX] 不让前端收到 500：返回最新可用 state，提示用户/脚本下一轮继续
            checkpoint = workflow.get_state(config)
            fallback_state = checkpoint.values if checkpoint and checkpoint.values else state
            return {
                "response": "系统内部推理步骤过多（触发递归上限），本轮先暂停。请直接再发一句“继续/下一步”，我会在下一轮继续推进并补齐结果。",
                "pending_responses": [{
                    "from": "system",
                    "content": "系统内部推理步骤过多（触发递归上限），本轮先暂停。请直接再发一句“继续/下一步”，我会在下一轮继续推进并补齐结果。",
                    "phase": "immediate",
                }],
                "state": {
                    **fallback_state,
                    "debug_log": (fallback_state.get("debug_log") or []) + [{
                        "node": "server",
                        "step": "GraphRecursionError",
                        "error": str(e),
                    }],
                },
            }

        # 异步维护任务（提纯/归档/压缩）：不阻塞用户回复
        background_tasks.add_task(_run_maintenance_tasks, request.session_id)
        
        # 仅用于兼容/调试的轻量缓存
        sessions[request.session_id] = final_state
        
        # 处理 pending_responses
        pending_responses = final_state.get("pending_responses", [])
        
        # 向后兼容：合并所有回复为单个 response 字符串
        if pending_responses:
            combined_response = "\n\n".join([r["content"] for r in pending_responses if r.get("content")])
        else:
            combined_response = ""
        
        #region agent log
        _append_debug_log(
            run_id="pre-fix",
            hypothesis_id="H1",
            location="server.py:chat:final_state",
            message="Final state before response",
            data={
                "has_pending_responses": bool(pending_responses),
                "pending_resp_count": len(pending_responses),
                "pending_first_has_card": bool(pending_responses[0].get("inquiry_card")) if pending_responses else False,
                "state_has_inquiry_card": bool(final_state.get("inquiry_card")),
                "onboarding_completed": final_state.get("onboarding_completed"),
                "next_action": final_state.get("next_action"),
                "route_to": state.get("route_to"),
            },
        )
        #endregion
        
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


# ============ Streaming 接口 ============

@app.post("/api/chat/stream")
async def chat_stream(request: StreamChatRequest, background_tasks: BackgroundTasks):
    """
    流式聊天接口 - 实时查看 Agent 执行过程
    
    支持多种流模式：
    - values: 每个步骤后的完整状态
    - updates: 每个步骤的状态更新（推荐）
    - messages: LLM tokens 和元数据
    - debug: 最详细的调试信息
    
    使用 Server-Sent Events (SSE) 格式返回数据
    """
    print(f"[Stream] Received message from session {request.session_id}: {request.message}")
    print(f"[Stream] Stream mode: {request.stream_mode}")
    
    from graph.workflow import get_workflow
    from graph.state import create_initial_state
    workflow = get_workflow()
    # [FIX] 避免复杂链路触发递归上限导致流式中断
    config = {"configurable": {"thread_id": request.session_id}, "recursion_limit": 120}
    
    checkpoint = workflow.get_state(config)
    base_state = checkpoint.values if checkpoint and checkpoint.values else None
    if base_state is None:
        print("[Stream] Creating new session (checkpointer empty)")
        state = create_initial_state(request.message)
    else:
        print("[Stream] Restoring existing session (checkpointer)")
        state = base_state
        state["user_message"] = request.message
        state["debug_log"] = []
        state["inquiry_card"] = None
        state["pending_questions"] = []
        state["pending_responses"] = []
        state["last_response_for_continuity"] = None
    
    async def generate_stream():
        """生成流式响应"""
        final_state = None
        try:
            # 使用 astream 进行异步流式调用
            # 在流式过程中累积最终状态
            async for chunk in workflow.astream(state, config=config, stream_mode=request.stream_mode):
                # 统一前端期望的事件格式
                event_name = request.stream_mode or "values"
                chunk_data = {
                    "event": event_name,  # 前端据此判断类型：values / updates / messages / debug
                    "data": chunk,
                    "stream_mode": request.stream_mode
                }
                
                #region agent log
                _append_debug_log(
                    run_id="pre-fix",
                    hypothesis_id="H3",
                    location="server.py:chat_stream:chunk",
                    message="Stream chunk",
                    data={
                        "event": event_name,
                        "has_inquiry_card": bool(chunk.get("inquiry_card")) if isinstance(chunk, dict) else False,
                        "has_pending_responses": bool(chunk.get("pending_responses")) if isinstance(chunk, dict) else False,
                        "pending_resp_count": len(chunk.get("pending_responses", []) or []) if isinstance(chunk, dict) else None,
                        "nodes": list(chunk.keys()) if isinstance(chunk, dict) else None,
                    },
                )
                #endregion

                # SSE 格式：data: {json}\n\n
                yield f"data: {json.dumps(chunk_data, ensure_ascii=False, default=str)}\n\n"
                
                # 累积状态（用于获取最终状态）
                if request.stream_mode == "values":
                    # values 模式：chunk 就是完整状态
                    final_state = chunk
                elif request.stream_mode == "updates":
                    # updates 模式：需要合并更新到状态
                    for node_name, node_update in chunk.items():
                        state.update(node_update)
                        #region agent log
                        _append_debug_log(
                            run_id="pre-fix",
                            hypothesis_id="H2",
                            location="server.py:chat_stream:updates_merge",
                            message="Merging stream update",
                            data={
                                "node": node_name,
                                "has_inquiry_card": bool(node_update.get("inquiry_card")),
                                "pending_resp_count": len(node_update.get("pending_responses", []) or []),
                                "onboarding_completed": node_update.get("onboarding_completed"),
                                "next_action": node_update.get("next_action"),
                            },
                        )
                        #endregion
                    final_state = state
                    
                    # 输出友好的信息
                    for node_name, node_update in chunk.items():
                        # 提取消息信息
                        if "messages" in node_update:
                            messages = node_update["messages"]
                            if messages:
                                last_msg = messages[-1]
                                if hasattr(last_msg, "content") and last_msg.content:
                                    info = {
                                        "type": "info",
                                        "node": node_name,
                                        "message": f"Agent 回复: {last_msg.content[:100]}..."
                                    }
                                    yield f"data: {json.dumps(info, ensure_ascii=False)}\n\n"
                                elif hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                                    tool_names = [tc.get("name", "unknown") for tc in last_msg.tool_calls]
                                    info = {
                                        "type": "info",
                                        "node": node_name,
                                        "message": f"调用工具: {', '.join(tool_names)}"
                                    }
                                    yield f"data: {json.dumps(info, ensure_ascii=False)}\n\n"
            
            # 流式执行完成后，使用累积的最终状态
            if final_state is None:
                # 如果没有累积到状态，使用原始状态
                final_state = state
            
            # 异步维护任务（提纯/归档/压缩）：不阻塞流式返回
            background_tasks.add_task(_run_maintenance_tasks, request.session_id)
            
            # 更新会话
            sessions[request.session_id] = final_state
            
            #region agent log
            _append_debug_log(
                run_id="pre-fix",
                hypothesis_id="H2",
                location="server.py:chat_stream:final_state",
                message="Final state before stream completion",
                data={
                    "has_pending_responses": bool(final_state.get("pending_responses")),
                    "pending_resp_count": len(final_state.get("pending_responses", []) or []),
                    "pending_first_has_card": bool(final_state.get("pending_responses", [{}])[0].get("inquiry_card")) if final_state.get("pending_responses") else False,
                    "state_has_inquiry_card": bool(final_state.get("inquiry_card")),
                    "onboarding_completed": final_state.get("onboarding_completed"),
                    "next_action": final_state.get("next_action"),
                },
            )
            #endregion
            
            # 发送完成信号
            completion = {
                "type": "done",
                "message": "流式执行完成",
                "final_state": {
                    "message_count": len(final_state.get("messages", [])),
                    "has_response": bool(final_state.get("pending_responses")),
                }
            }
            yield f"data: {json.dumps(completion, ensure_ascii=False, default=str)}\n\n"
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"[Stream] Error: {error_trace}")
            
            error_data = {
                "type": "error",
                "error": str(e),
                "traceback": error_trace
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        background=background_tasks,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用 nginx 缓冲
        }
    )


# ============ 指南状态更新接口 ============

@app.post("/api/update_guide_status")
async def update_guide_status(request: UpdateGuideStatusRequest):
    """
    更新行动指南状态（支持 6 状态机中的可变更状态）。
    - 写入 v3.1 真源：layer2_memory.all_action_guides
    - 向后兼容：同步写回 state.action_guides
    """
    print(
        f"✅ 收到指南状态更新请求: guide_id={request.guide_id}, new_status={request.new_status}, session={request.session_id}"
    )

    from graph.workflow import get_workflow
    from graph.context_types import (
        create_empty_layer2_memory,
        is_valid_action_guide_status_transition,
    )
    from graph.archive_manager import archive_guide_on_completion  # legacy (kept for compatibility)
    workflow = get_workflow()
    config = {"configurable": {"thread_id": request.session_id}}
    checkpoint = workflow.get_state(config)
    state = checkpoint.values if checkpoint and checkpoint.values else None
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    # 统一从 Layer2Memory 真源读取；若缺失则从旧字段回填
    layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
    all_guides = list(layer2_memory.get("all_action_guides", []))
    if not all_guides:
        legacy = state.get("action_guides", []) or []
        if isinstance(legacy, list) and legacy:
            all_guides = list(legacy)

    guide_index = None
    guide = None
    for idx, g in enumerate(all_guides):
        if isinstance(g, dict) and g.get("id") == request.guide_id:
            guide_index = idx
            guide = g
            break
    if guide_index is None or not guide:
        raise HTTPException(status_code=404, detail=f"Guide with id {request.guide_id} not found")

    current_status = str(guide.get("status") or "pending")
    if not is_valid_action_guide_status_transition(current_status, request.new_status):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition: {current_status} -> {request.new_status}",
        )

    updated_guide = dict(guide)
    updated_guide["status"] = request.new_status

    # 非终态清理 completed_at；终态补齐 completed_at
    if request.new_status in ("completed", "cancelled", "expired"):
        updated_guide["completed_at"] = datetime.now().isoformat()
    else:
        updated_guide["completed_at"] = None

    # 反馈写入（用于归档/展示）：优先 one_liner，其次 summary
    if request.feedback:
        if not updated_guide.get("one_liner"):
            updated_guide["one_liner"] = request.feedback
        if request.new_status in ("cancelled", "expired") and not updated_guide.get("summary"):
            updated_guide["summary"] = request.feedback
        # 保留旧字段名（兼容）
        updated_guide["user_feedback"] = request.feedback

    if request.execution_status:
        updated_guide["execution_status"] = request.execution_status

    updated_guides = list(all_guides)
    updated_guides[guide_index] = updated_guide

    updated_layer2 = dict(layer2_memory)
    updated_layer2["all_action_guides"] = updated_guides
    updated_layer2["last_updated"] = datetime.now().isoformat()
    updated_layer2["version"] = layer2_memory.get("version", 1) + 1
    state["layer2_memory"] = updated_layer2

    # 向后兼容
    state["action_guides"] = updated_guides

    # 终态触发归档（具体归档规则在 archive_manager 中适配）
    if request.new_status in ("completed", "cancelled", "expired"):
        try:
            archive_updates = archive_guide_on_completion(updated_guide, state)
            for k in ("history_archive", "user_context", "layer1_memory", "layer2_memory", "layer3_memory"):
                if k in archive_updates:
                    state[k] = archive_updates[k]
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"⚠️ 归档失败: {str(e)}")

    if hasattr(workflow, "update_state"):
        workflow.update_state(config, state)

    return {"success": True, "state": state}


# ============ 完成指南接口（兼容旧前端） ============

@app.post("/api/complete_guide")
async def complete_guide(request: CompleteGuideRequest):
    """
    [兼容] 旧接口：标记行动指南为已完成。
    建议迁移到 /api/update_guide_status。
    """
    wrapper = UpdateGuideStatusRequest(
        guide_id=request.guide_id,
        new_status="completed",
        feedback=request.feedback,
        execution_status=request.execution_status,
        session_id=request.session_id,
    )
    return await update_guide_status(wrapper)


# ============ 调试接口 ============

@app.get("/api/debug/context/{session_id}")
async def get_debug_context(session_id: str):
    """
    获取当前会话的上下文调试信息
    
    返回分层的上下文状态，用于前端调试面板显示
    """
    workflow = get_workflow()
    config = {"configurable": {"thread_id": session_id}}
    checkpoint = workflow.get_state(config)
    state = checkpoint.values if checkpoint and checkpoint.values else {}
    
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
    
    # v3.1 真源：分层 memory
    layer1_memory = state.get("layer1_memory") or {}
    layer2_memory = state.get("layer2_memory") or {}
    layer3_memory = state.get("layer3_memory") or {}
    maintenance_queue = state.get("maintenance_queue") or []
    maintenance_flags = state.get("maintenance_flags") or {}

    # 计算压缩触发相关信息（用于可视化验证）
    # 注意：这里仅用于 debug 面板，允许做相对“重”的 import。
    try:
        from graph.archive_manager import (
            LAYER2_ARCHIVE_CONFIG,
            LAYER3_ARCHIVE_CONFIG,
            check_layer3_compression_needed,
        )
        from utils.message_utils import count_user_turns
    except Exception:
        LAYER2_ARCHIVE_CONFIG = {}
        LAYER3_ARCHIVE_CONFIG = {}
        check_layer3_compression_needed = None
        count_user_turns = None

    # 兼容字段（旧）
    user_context = state.get("user_context", {}) or layer1_memory.get("full_data", {})
    history_archive = state.get("history_archive", {})
    
    # 获取 Crush 聊天存储
    crush_chat_storage = state.get("crush_chat_storage", {})
    
    return {
        "session_id": session_id,
        "onboarding_status": {
            "completed": bool(state.get("onboarding_completed", False)),
            "turn_count": state.get("onboarding_turn_count", 0),
            "max_turns": state.get("onboarding_max_turns", 3),
            "has_handoff": bool(state.get("onboarding_handoff")),
        },
        "maintenance": {
            "queue_size": len(maintenance_queue) if isinstance(maintenance_queue, list) else 0,
            "queue": maintenance_queue if isinstance(maintenance_queue, list) else [],
            "flags": maintenance_flags if isinstance(maintenance_flags, dict) else {},
            "last_finalized_at": state.get("maintenance_last_finalized_at"),
        },
        "archive_config": {
            # 便于你验证“配置是否生效”（当前为代码常量）
            "layer2": LAYER2_ARCHIVE_CONFIG or {},
            "layer3": LAYER3_ARCHIVE_CONFIG or {},
        },
        # === 归档/整理后的“产物”预览（用于前端直观验收）===
        # 说明：只返回最近 N 条，避免 payload 过大；需要全量/全文再考虑加单独接口。
        "organized_outputs": {
            "layer3_conversation_summaries": (
                (layer3_memory.get("conversation_summaries", [])[-5:] if isinstance(layer3_memory, dict) else [])
            ),
            "layer2_status_reports_history": (
                [
                    {
                        "id": r.get("id"),
                        "created_at": r.get("created_at"),
                        "stage": r.get("report", {}).get("stage") if isinstance(r.get("report"), dict) else r.get("stage"),
                        "summary": (r.get("summary") or "").strip(),
                        "one_liner": (r.get("one_liner") or "").strip(),
                    }
                    for r in (layer2_memory.get("all_status_reports", []) if isinstance(layer2_memory, dict) else [])
                    if isinstance(r, dict) and not r.get("is_current")
                ][-5:]
            ),
            "layer2_action_plans_history": (
                [
                    {
                        "id": p.get("id"),
                        "created_at": p.get("created_at"),
                        "summary": (p.get("summary") or "").strip(),
                        "one_liner": (p.get("one_liner") or "").strip(),
                    }
                    for p in (layer2_memory.get("all_action_plans", []) if isinstance(layer2_memory, dict) else [])
                    if isinstance(p, dict) and not p.get("is_current")
                ][-5:]
            ),
            "layer2_terminal_guides": (
                [
                    {
                        "id": g.get("id"),
                        "status": g.get("status"),
                        "created_at": g.get("created_at"),
                        "completed_at": g.get("completed_at"),
                        "current_task": (
                            (g.get("guide") or {}).get("current_task")
                            if isinstance(g.get("guide"), dict)
                            else None
                        ),
                        "one_liner": (g.get("one_liner") or "").strip(),
                        "summary": (g.get("summary") or "").strip(),
                    }
                    for g in (layer2_memory.get("all_action_guides", []) if isinstance(layer2_memory, dict) else [])
                    if isinstance(g, dict) and (g.get("status") in ("completed", "cancelled", "expired"))
                ][-5:]
            ),
            "layer2_dynamic_intels": (
                (layer2_memory.get("dynamic_intels", [])[-10:] if isinstance(layer2_memory, dict) else [])
            ),
        },
        "layered_memory": {
            "layer1": {
                "version": layer1_memory.get("version") if isinstance(layer1_memory, dict) else None,
                "last_updated": layer1_memory.get("last_updated") if isinstance(layer1_memory, dict) else None,
            },
            "layer2": {
                "version": layer2_memory.get("version") if isinstance(layer2_memory, dict) else None,
                "last_updated": layer2_memory.get("last_updated") if isinstance(layer2_memory, dict) else None,
                "status_reports_total": len(layer2_memory.get("all_status_reports", [])) if isinstance(layer2_memory, dict) else 0,
                "action_plans_total": len(layer2_memory.get("all_action_plans", [])) if isinstance(layer2_memory, dict) else 0,
                "action_guides_total": len(layer2_memory.get("all_action_guides", [])) if isinstance(layer2_memory, dict) else 0,
                "dynamic_intels_total": len(layer2_memory.get("dynamic_intels", [])) if isinstance(layer2_memory, dict) else 0,
            },
            "layer3": {
                "version": layer3_memory.get("version") if isinstance(layer3_memory, dict) else None,
                "last_updated": layer3_memory.get("last_updated") if isinstance(layer3_memory, dict) else None,
                "all_messages_count": len(layer3_memory.get("all_messages", [])) if isinstance(layer3_memory, dict) else 0,
                "conversation_summaries_count": len(layer3_memory.get("conversation_summaries", [])) if isinstance(layer3_memory, dict) else 0,
            },
        },
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
        "layer3_conversation": (lambda: {
            # 兼容前端旧字段命名（message_count / needs_compression / compression_threshold）
            "message_count": len(state.get("messages", [])),
            "messages_count_workspace": len(state.get("messages", [])),
            "all_messages_count_fullstore": len(layer3_memory.get("all_messages", [])) if isinstance(layer3_memory, dict) else len(state.get("messages", [])),
            "conversation_summaries_count": len(layer3_memory.get("conversation_summaries", [])) if isinstance(layer3_memory, dict) else 0,
            "compression_threshold": (LAYER3_ARCHIVE_CONFIG or {}).get("compression_threshold"),
            "compression_batch_size": (LAYER3_ARCHIVE_CONFIG or {}).get("compression_batch_size"),
            "max_recent_turns": (LAYER3_ARCHIVE_CONFIG or {}).get("max_recent_turns"),
            "current_user_turns": (
                _current_turns := (
                    count_user_turns(layer3_memory.get("all_messages", state.get("messages", [])))
                    if callable(count_user_turns)
                    else 0
                )
            ),
            "turns_to_next_compression": (
                # 计算距离下次压缩还差多少轮
                (lambda threshold, batch_size, turns: (
                    threshold - turns + 1 if turns <= threshold else
                    batch_size - ((turns - threshold) % batch_size) if ((turns - threshold) % batch_size) != 0 else 0
                ))(
                    (LAYER3_ARCHIVE_CONFIG or {}).get("compression_threshold", 45),
                    (LAYER3_ARCHIVE_CONFIG or {}).get("compression_batch_size", 5),
                    _current_turns if isinstance(_current_turns, int) else 0
                )
            ),
            "needs_compression": (
                bool(check_layer3_compression_needed(state))
                if callable(check_layer3_compression_needed)
                else None
            ),
            "messages_preview": (layer3_memory.get("all_messages", [])[-5:] if isinstance(layer3_memory, dict) else []) or (state.get("messages", [])[-5:] if state.get("messages") else []),
        })(),
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


# ============ 全文展开接口（用于调试面板）============

@app.get("/api/debug/detail/status_report/{session_id}/{report_id}")
async def get_status_report_detail(session_id: str, report_id: str):
    """
    获取现状报告全文（用于调试面板展开查看）
    """
    workflow = get_workflow()
    config = {"configurable": {"thread_id": session_id}}
    checkpoint = workflow.get_state(config)
    state = checkpoint.values if checkpoint and checkpoint.values else {}
    
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    layer2_memory = state.get("layer2_memory") or {}
    all_reports = layer2_memory.get("all_status_reports", []) if isinstance(layer2_memory, dict) else []
    
    for r in all_reports:
        if isinstance(r, dict) and str(r.get("id")) == str(report_id):
            return {
                "id": r.get("id"),
                "created_at": r.get("created_at"),
                "is_current": r.get("is_current"),
                "stage": r.get("stage") or (r.get("report", {}).get("stage") if isinstance(r.get("report"), dict) else None),
                "summary": r.get("summary"),
                "one_liner": r.get("one_liner"),
                "report_content": r.get("report_content") or (r.get("report", {}).get("report_content") if isinstance(r.get("report"), dict) else None),
                "full_report": r.get("report") if isinstance(r.get("report"), dict) else r,
            }
    
    raise HTTPException(status_code=404, detail=f"Report with id {report_id} not found")


@app.get("/api/debug/detail/action_guide/{session_id}/{guide_id}")
async def get_action_guide_detail(session_id: str, guide_id: str):
    """
    获取行动指南全文（用于调试面板展开查看）
    """
    workflow = get_workflow()
    config = {"configurable": {"thread_id": session_id}}
    checkpoint = workflow.get_state(config)
    state = checkpoint.values if checkpoint and checkpoint.values else {}
    
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    layer2_memory = state.get("layer2_memory") or {}
    all_guides = layer2_memory.get("all_action_guides", []) if isinstance(layer2_memory, dict) else []
    
    # 兼容旧字段
    if not all_guides:
        all_guides = state.get("action_guides", []) or []
    
    for g in all_guides:
        if isinstance(g, dict) and str(g.get("id")) == str(guide_id):
            guide_content = g.get("guide", {}) if isinstance(g.get("guide"), dict) else {}
            return {
                "id": g.get("id"),
                "status": g.get("status"),
                "created_at": g.get("created_at"),
                "completed_at": g.get("completed_at"),
                "current_task": guide_content.get("current_task"),
                "summary": g.get("summary"),
                "one_liner": g.get("one_liner"),
                "user_feedback": g.get("user_feedback"),
                "execution_status": g.get("execution_status"),
                "guide_content": guide_content.get("guide_content"),
                "full_guide": g,
            }
    
    raise HTTPException(status_code=404, detail=f"Guide with id {guide_id} not found")


@app.get("/api/debug/detail/compressed_messages/{session_id}/{summary_index}")
async def get_compressed_messages_detail(session_id: str, summary_index: int):
    """
    获取压缩前的原始对话片段（用于调试面板展开查看）
    
    注意：目前压缩时只保留摘要，原始消息被删除。
    如果需要保留原始消息，需要在 compress_layer3 里额外存储。
    这里返回 summary 的详细信息 + 相关元数据。
    """
    workflow = get_workflow()
    config = {"configurable": {"thread_id": session_id}}
    checkpoint = workflow.get_state(config)
    state = checkpoint.values if checkpoint and checkpoint.values else {}
    
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    
    layer3_memory = state.get("layer3_memory") or {}
    summaries = layer3_memory.get("conversation_summaries", []) if isinstance(layer3_memory, dict) else []
    
    if summary_index < 0 or summary_index >= len(summaries):
        raise HTTPException(status_code=404, detail=f"Summary at index {summary_index} not found")
    
    summary = summaries[summary_index]
    return {
        "index": summary_index,
        "summary": summary.get("summary") if isinstance(summary, dict) else str(summary),
        "turn_count": summary.get("turn_count") if isinstance(summary, dict) else None,
        "key_topics": summary.get("key_topics") if isinstance(summary, dict) else None,
        "created_at": summary.get("created_at") if isinstance(summary, dict) else None,
        "extracted_info": summary.get("extracted_info") if isinstance(summary, dict) else None,
        # 原始消息目前不保留，这里返回提示信息
        "original_messages": None,
        "note": "原始消息在压缩后被删除，仅保留摘要。如需保留原始消息，需修改 compress_layer3 逻辑。",
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
