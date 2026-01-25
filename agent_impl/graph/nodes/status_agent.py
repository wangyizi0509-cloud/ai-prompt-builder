"""
现状分析 Agent 节点 (Status Analysis Agent)
负责诊断用户问题、判断 ACR 阶段、定位 L/T 线

采用 Tool-based 渐进式加载模式：
- 系统提示只包含 Skills 的元数据
- 模型通过 load_skill 工具按需加载完整指令

上下文架构更新 (v2.0)：
- 使用分层上下文架构（Layer 0-4）
- 通过 context_builder 统一组装上下文

任务管理更新 (v2.1)：
- 任务边界：被调用时开始新任务，产出报告时结束
- 思考过程：同一任务内保留，任务结束时归档
- 报告编号：每次产出报告分配递增编号
"""

import json
from typing import Any
from datetime import datetime

from graph.state import AgentState, StatusReport
from graph.message_builder import build_messages_for_model
from graph.context_types import (
    create_new_task,
    get_active_task,
    create_empty_layer2_memory,
    create_status_report_item,
)
from utils.message_utils import get_msg_role_and_content
from skills import create_inquiry_only_loader
from graph.tools.ask_tool import get_ask_tool, ask_user
from config import get_llm


# ============================================================
# 任务管理辅助函数
# ============================================================

def _get_next_task_id(task_list: list) -> str:
    """生成下一个任务 ID（格式：task_001, task_002, ...）"""
    if not task_list:
        return "task_001"
    
    # 找到最大的任务编号
    max_num = 0
    for task in task_list:
        task_id = task.get("task_id", "")
        if task_id.startswith("task_"):
            try:
                num = int(task_id.split("_")[1])
                max_num = max(max_num, num)
            except (ValueError, IndexError):
                pass
    
    return f"task_{max_num + 1:03d}"


def _start_new_task(state: AgentState) -> dict:
    """
    开始新任务（被调用时，非恢复执行）
    
    Returns:
        包含 task_registry 更新的字典
    """
    task_registry = state.get("task_registry", {})
    task_list = list(task_registry.get("status_agent", []))
    
    # 将之前的活跃任务标记为非活跃
    for task in task_list:
        task["is_active"] = False
    
    # 创建新任务
    new_task_id = _get_next_task_id(task_list)
    new_task = create_new_task(new_task_id)
    task_list.append(new_task)
    
    print(f"[DEBUG] StatusAgent: Started new task {new_task_id}")
    
    return {
        "task_registry": {
            **task_registry,
            "status_agent": task_list,
        }
    }


def _add_reasoning_note(state: AgentState, note: str) -> dict:
    """
    添加思考记录到当前活跃任务
    
    Args:
        state: 当前状态
        note: 思考记录
    
    Returns:
        包含 task_registry 更新的字典
    """
    task_registry = state.get("task_registry", {})
    task_list = list(task_registry.get("status_agent", []))
    
    # 找到当前活跃任务并添加思考记录
    for task in task_list:
        if task.get("is_active", False):
            reasoning = list(task.get("reasoning", []))
            reasoning.append(note)
            task["reasoning"] = reasoning
            break
    
    return {
        "task_registry": {
            **task_registry,
            "status_agent": task_list,
        }
    }


def _complete_current_task(state: AgentState) -> dict:
    """
    完成当前任务（产出报告时）
    
    注意：不删除任务，只是标记为非活跃，保留思考过程
    
    Returns:
        包含 task_registry 更新的字典
    """
    task_registry = state.get("task_registry", {})
    task_list = list(task_registry.get("status_agent", []))
    
    # 将当前活跃任务标记为非活跃
    for task in task_list:
        if task.get("is_active", False):
            task["is_active"] = False
            task["completed_at"] = datetime.now().isoformat()
            print(f"[DEBUG] StatusAgent: Completed task {task.get('task_id')}")
            break
    
    return {
        "task_registry": {
            **task_registry,
            "status_agent": task_list,
        }
    }

def status_agent_node(state: AgentState) -> dict[str, Any]:
    """
    现状分析 Agent 节点
    
    职责：
    1. 分析用户与 Crush 的关系现状
    2. 判断 ACR（吸引力/舒适感/张力）三维状态
    3. 定位 L 线（正常线）或 T 线（陷阱线）阶段
    4. 识别核心问题和风险点
    5. 如果信息不足，通过工具获取提问技能指令
    
    任务边界：
    - 新任务触发：被调用时（非恢复执行）
    - 任务结束：产出报告（completion_status=COMPLETED）
    - 提问等待用户回答后恢复执行，仍属于同一任务
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    question_count = state.get("question_count", 0)
    max_questions = state.get("max_questions", 3)
    
    # === 任务边界判定 ===
    is_resuming = (state.get("current_agent") == "status_agent" and 
                   state.get("agent_resume_point") == "continue_analysis")
    
    # 初始化任务管理更新
    task_updates = {}
    
    if not is_resuming:
        # 非恢复执行 = 新任务开始
        task_updates = _start_new_task(state)
        print(f"[DEBUG] StatusAgent: New task started")
    
    # 工具调用返回检查（增强版）
    messages = state.get("messages", [])
    last_msg_role = ""
    last_tool_content = None
    if messages:
        last_msg_role, last_tool_content = get_msg_role_and_content(messages[-1])
    
    from_tool_call = (state.get("_tool_caller") == "status_agent" or last_msg_role == "tool")
    
    if from_tool_call:
        print(f"[DEBUG] StatusAgent: Continuing after tool call (last_role={last_msg_role})")
    
    # 准备 LLM（工具绑定在决策后进行）
    base_llm = get_llm(temperature=0.5)
    if from_tool_call:
        print("[DEBUG] StatusAgent: Second stage (from_tool_call), tools disabled to prevent loop")
    
    # 注入工具指令（如果刚从工具返回）
    if from_tool_call and not last_tool_content:
        # [FIX] 优先检查 _last_tool_content（skill_tools_node 直接设置的，最可靠）
        cached_content = state.get("_last_tool_content")
        if cached_content:
            last_tool_content = cached_content
        
        # 其次回溯 messages 查找 tool 消息
        if not last_tool_content:
            for msg in reversed(messages or []):
                r, c = get_msg_role_and_content(msg)
                if r == "tool" and c:
                    last_tool_content = c
                    break
        
        # 最后从 _last_tool_outputs 列表中提取
        if not last_tool_content:
            cached_tool_outputs = state.get("_last_tool_outputs")
            if isinstance(cached_tool_outputs, list):
                for item in reversed(cached_tool_outputs):
                    if not isinstance(item, dict):
                        continue
                    cached_content = item.get("content") or item.get("tool_output") or ""
                    if cached_content:
                        last_tool_content = cached_content
                        break

    # [FIX] 当从工具调用返回时，不应该再次添加用户的上一条输入
    # 否则模型会看到错误的消息栈，误以为用户已确认，跳过提问
    current_input = "" if from_tool_call else state.get("user_message", "")
    
    model_messages = build_messages_for_model(
        state=state,
        agent_name="status_agent",
        current_input=current_input,
    )
    prompt_source = "message_builder"
    prompt_fallback = False

    # === 调用 LLM（工具驱动）===
    ask_mode = state.get("ask_mode", False)
    print(f"[DEBUG] StatusAgent: Invoking LLM (from_tool_call={from_tool_call}, ask_mode={ask_mode})")
    response = None
    parsed = None
    pending_action = state.get("_pending_action") or ""
    
    # Phase 2: ask_mode=True 后强制调用 ask 工具生成 inquiry_card
    if from_tool_call and pending_action == "ask":
        ask_full_tool = get_ask_tool(True)
        llm_with_tools = base_llm.bind_tools(
            [ask_full_tool],
            tool_choice={"type": "function", "function": {"name": "ask"}},
        )
        response = llm_with_tools.invoke(model_messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print("[DEBUG] StatusAgent: Forced ask tool call (Phase 2: generate inquiry_card)")
            if hasattr(response, "name"):
                response.name = "status_agent"
            return {
                "messages": [response],
                "current_agent": "status_agent",
                "_tool_caller": "status_agent",
                "debug_log": [{
                    "node": "status_agent",
                    "step": "Tool Call Requested (ask forced, Phase 2)",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }],
            }
    
    # 向后兼容：原 inquiry skill 的两阶段处理
    elif from_tool_call and pending_action == "inquiry":
        llm_with_tools = base_llm.bind_tools(
            [ask_user],
            tool_choice={"type": "function", "function": {"name": "ask_user"}},
        )
        response = llm_with_tools.invoke(model_messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print("[DEBUG] StatusAgent: Forced ask_user tool call after inquiry skill")
            if hasattr(response, "name"):
                response.name = "status_agent"
            return {
                "messages": [response],
                "current_agent": "status_agent",
                "_tool_caller": "status_agent",
                "debug_log": [{
                    "node": "status_agent",
                    "step": "Tool Call Requested (ask_user forced)",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }],
            }
    elif from_tool_call:
        response = base_llm.invoke(model_messages)
    else:
        # 使用定制工具：status_agent 只允许使用 inquiry skill
        inquiry_tool = create_inquiry_only_loader()
<<<<<<< Current (Your changes)
        llm_with_tools = base_llm.bind_tools([inquiry_tool])
=======
        # 允许子 Agent 直接进入 ask 两阶段提问（Phase 1: ask(action="enable")）
        ask_tool = get_ask_tool(False)
        llm_with_tools = base_llm.bind_tools([ask_tool, inquiry_tool])
>>>>>>> Incoming (Background Agent changes)
        response = llm_with_tools.invoke(model_messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"[DEBUG] StatusAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
            if hasattr(response, "name"):
                response.name = "status_agent"
            return {
                "messages": [response],
                "current_agent": "status_agent",
                "_tool_caller": "status_agent",
                "debug_log": [{
                    "node": "status_agent",
                    "step": "Tool Call Requested",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }],
            }
    
    # 解析响应（若决策已解析则复用）
    if parsed is None:
        parsed = _parse_response(response.content)
    
    result = {
        "next_action": "end_turn",
        "debug_log": [{
            "node": "status_agent",
            "step": "Response Generated",
            "prompt_source": prompt_source,
            "prompt_fallback": prompt_fallback,
            # "prompt": prompt,  # [FIX] 移除完整 prompt 存储，防止 state 爆炸
            "response": response.content[:500] + "..." if len(response.content) > 500 else response.content,
            "parsed_result": parsed,
            "question_count": question_count,
        }],
    }
    
    # 检查是否需要提问
    inquiry_card = parsed.get("inquiry_card")
    questions_list = inquiry_card.get("questions", []) if isinstance(inquiry_card, dict) else []
    if from_tool_call and last_tool_content and not questions_list:
        err_msg = "系统异常：已加载提问指令但未生成问题列表（inquiry_card.questions 为空）。请重试。"
        result["status_report"] = None
        result["inquiry_card"] = None
        result["pending_questions"] = []
        existing_responses = state.get("pending_responses", [])
        result["pending_responses"] = existing_responses + [{"from": "status_agent", "content": err_msg, "phase": "after_status"}]
        result["messages"] = [{"role": "assistant", "name": "status_agent", "content": err_msg}]
        result["current_agent"] = "status_agent"
        result["agent_resume_point"] = "continue_analysis"
        result["completion_status"] = None
        result["result_summary"] = None
        return result

    if questions_list and question_count < max_questions:
        # ⚠️ 严格模式（按你的要求）：不做任何“纠错二次调用”、不做任何“工程兜底造 inquiry_card”
        # - Phase 1：应由模型触发 tool_calls（上面已处理 tool_calls 分支）
        # - Phase 2：必须输出 inquiry_card.questions，否则直接报错并结束本轮（暴露问题，便于排查）

        # 至此：必须有 inquiry_card.questions，才能真正发起提问
        print(f"[DEBUG] StatusAgent: Asking questions (count={len(questions_list)})")

        result["inquiry_card"] = inquiry_card
        result["pending_questions"] = [
            q.get("question", "") if isinstance(q, dict) else str(q)
            for q in questions_list
        ]

        # === 设置恢复状态 ===
        result["current_agent"] = "status_agent"
        result["agent_resume_point"] = "continue_analysis"
        result["question_count"] = question_count + 1

        # 信息不足时，不生成报告，等待用户回答
        result["status_report"] = None
        response_content = (parsed.get("response") or "").strip()
        if not response_content:
            response_content = (inquiry_card.get("intro") or "").strip()
        if not response_content:
            response_content = "为了更准确地分析你们的情况，我需要再了解一些细节～"

        existing_responses = state.get("pending_responses", [])
        result["pending_responses"] = existing_responses + [{
            "from": "status_agent",
            "content": response_content,
            "phase": "after_status"
        }]

        # 保留模型原始输出（应包含 inquiry_card），便于 context_builder 从历史中抽取【提问】
        raw_assistant_msg = getattr(response, "content", "") or response_content
        result["messages"] = [{
            "role": "assistant",
            "name": "status_agent",
            "content": raw_assistant_msg,
            "metadata": {
                "task_id": parsed.get("task_id") if isinstance(parsed, dict) else "",
                "thought": parsed.get("thought") if isinstance(parsed, dict) else "",
            }
        }]

        result["completion_status"] = None
        result["result_summary"] = None

    else:
        # 不需要提问（或提问次数已达上限），生成报告
        
        # === 分配报告编号 ===
        report_counter = state.get("report_counter", {"status_report": 0, "action_plan": 0, "action_guide": 0})
        new_report_id = report_counter.get("status_report", 0) + 1
        
        # 构建带编号的报告（前端使用 Markdown string）
        # 真实 API 下，模型可能返回 report_content=null（None），这里必须做强健兜底，避免 TypeError
        report_content_raw = parsed.get("report_content")
        report_content = report_content_raw if isinstance(report_content_raw, str) else ""
        if not report_content.strip():
            # fallback：尽量使用模型原始输出（至少保证是 string，避免“空报告”导致前端体验崩坏）
            raw_text = getattr(response, "content", "") or ""
            report_content = raw_text.strip()
        if not report_content.strip():
            report_content = "暂时无法生成完整的现状分析报告，请补充更多关键信息（如你们最近一次互动、对方的具体反应）。"
        result["status_report"] = report_content  # Markdown string for frontend rendering
        # 单独存储报告编号，便于其他模块引用
        result["status_report_id"] = new_report_id
        
        # 更新报告计数器
        result["report_counter"] = {
            **report_counter,
            "status_report": new_report_id
        }

        # === 写入 Layer 2 真源（current_status_report + status_report_history）===
        layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
        
        # 获取当前报告和历史报告
        old_current = layer2_memory.get("current_status_report")
        history = list(layer2_memory.get("status_report_history", []))
        
        # 将旧 current 移入历史（summary/one_liner 由异步归档补齐）
        if old_current:
            history.insert(0, old_current)

        new_report_item = create_status_report_item(
            report_content=report_content,
            report_id=new_report_id,
            stage=parsed.get("stage", ""),
            stage_description=parsed.get("stage_description", ""),
            acr_analysis=parsed.get("acr_analysis", {}) or {},
            key_issues=parsed.get("key_issues", []) or [],
            risk_points=parsed.get("risk_points", []) or [],
        )

        updated_layer2 = dict(layer2_memory)
        updated_layer2["current_status_report"] = new_report_item
        updated_layer2["status_report_history"] = history
        updated_layer2["last_updated"] = datetime.now().isoformat()
        updated_layer2["version"] = layer2_memory.get("version", 1) + 1
        result["layer2_memory"] = updated_layer2
        
        # === 清除恢复状态 ===
        result["current_agent"] = None
        result["agent_resume_point"] = None
        result["question_count"] = 0
        result["collected_info"] = {}
        # 显式清除 inquiry_card，避免残留上一轮的问题
        result["inquiry_card"] = None
        result["pending_questions"] = []
        
        # === 设置完成信号 ===
        result["completion_status"] = "COMPLETED"
        result["result_summary"] = f"现状分析完成：{(report_content or '')[:50]}..."
        
        # === 完成当前任务（归档思考过程，不删除）===
        task_complete_updates = _complete_current_task(state)
        result["task_registry"] = task_complete_updates.get("task_registry", state.get("task_registry", {}))
        
        # === 在 Layer 3 记录报告产出 ===
        # 子 Agent 完成时发送简短通知，完整报告在看板（status_report）中展示
        existing_responses = state.get("pending_responses", [])
        result["pending_responses"] = existing_responses
        result["messages"] = [{
            "role": "assistant",
            "name": "status_agent",
            "content": f"（现状分析报告{new_report_id}已生成）",
            "metadata": {
                "task_id": parsed.get("task_id"),
                "thought": parsed.get("thought"),
            }
        }]
        
        print(f"[DEBUG] StatusAgent: Report {new_report_id} generated")
        
    # === 清除工具调用来源（防止无限循环） ===
    result["_tool_caller"] = None
    # 清除工具输出缓存，避免后续轮次误注入
    result["_last_tool_outputs"] = None
    result["_last_tool_content"] = None
    
    # === 合并任务管理更新 ===
    if task_updates and "task_registry" not in result:
        result["task_registry"] = task_updates.get("task_registry", state.get("task_registry", {}))

    # 清理 handoff 指令，避免后续轮次误注入
    result["_handoff_target"] = None
    result["_handoff_instruction"] = None
    result["instruction"] = None
    
    return result


def _format_history(messages: list) -> str:
    """格式化对话历史，包含工具调用结果"""
    if not messages:
        return "无历史对话"
    
    # 只保留最近 10 条消息
    recent = messages[-10:]
    formatted = []
    for msg in recent:
        msg_role, msg_content = get_msg_role_and_content(msg)
        if msg_role == "user":
            role = "用户"
        elif msg_role == "assistant" or msg_role == "ai":
            role = "小话"
        elif msg_role == "tool":
            role = "工具输出"
        else:
            continue
            
        formatted.append(f"{role}: {msg_content}")
    
    return "\n".join(formatted)


def _parse_response(content: str) -> dict:
    """解析 LLM 输出，返回原始字典"""
    try:
        # 尝试解析 JSON
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                json_str = content[start:end]
            else:
                json_str = content
        
        return json.loads(json_str)
    
    except (json.JSONDecodeError, KeyError, IndexError):
        # 解析失败，返回默认值
        return {
            "task_id": "",
            "thought": "",
            "report_content": content.strip() if content else "暂时无法完成分析，请提供更多信息。",
        }


def _build_status_report(data: dict) -> StatusReport:
    """从解析的数据构建 StatusReport"""
    return StatusReport(
        stage=data.get("stage", ""),
        stage_description=data.get("stage_description", ""),
        acr_analysis=data.get("acr_analysis", {}),
        key_issues=data.get("key_issues", []),
        risk_points=data.get("risk_points", []),
        summary=data.get("summary", ""),
        report_content=data.get("report_content", ""),  # Markdown 格式的完整报告
    )


def _generate_response(status_report: StatusReport) -> str:
    """根据分析结果生成回复"""
    stage = status_report.get("stage", "未知")
    stage_desc = status_report.get("stage_description", "")
    summary = status_report.get("summary", "")
    key_issues = status_report.get("key_issues", [])
    
    response_parts = [
        f"根据你描述的情况，我帮你分析了一下：\n",
        f"**当前阶段**: {stage} - {stage_desc}\n",
    ]
    
    if summary:
        response_parts.append(f"\n**总体判断**: {summary}\n")
    
    if key_issues:
        response_parts.append("\n**需要注意的点**:")
        for issue in key_issues[:3]:  # 最多显示 3 个
            response_parts.append(f"\n• {issue}")
    
    response_parts.append("\n\n你觉得这个分析准确吗？如果有补充或者不同意的地方，告诉我，我来调整。")
    
    return "".join(response_parts)


def _get_default_prompt() -> str:
    """获取默认 Prompt - 迁移自 Strategy_Library/Emotional_Compass"""
    return """# 人设定位
你是用户的恋爱军师「小话」。

## 角色定义
你不是一个温吞的情感抚慰师，也不是只会说漂亮话的客服。你是一个**"委婉诚实 (Tactful Honesty)"的策略顾问**。你的职责是帮用户看清残酷的现实，并制定赢面最大的策略。

**根据用户性别，调整角色气质：**
- **男性用户**：你是他的"战术指挥官"，像一个靠谱的老大哥，带他打赢这场仗。
- **女性用户**：你是她的"闺蜜参谋"，像一个毒舌但真心的好姐妹，帮她拆解剧本、看透人心。

## 核心价值（通用）
- **去我执**：用户往往因为"想当然"而犯错，你的核心价值是打破 TA 的主观幻想，回归客观规律。
- **SOP化**：用户执行力有限，指令必须清晰到"傻瓜式"执行。

---

## 语言风格

### 通用原则
1. **亦师亦友**：不说官话套话，要说人话。
2. **犀利直接**：一针见血地指出问题，但要基于共情。
3. **用户视角**：使用用户能听懂的大白话，**严禁使用 "ACR"、"A值"、"L/T线" 等技术术语**，把它们嚼碎了变成"好奇心"、"安全感"、"备胎陷阱"等自然语言。
4. **去 PUA 化表达**：严禁使用 PUA 圈层黑话或带有**性别对立、物化对方**视角的词汇。
    - ❌ *禁止词汇*：废物测试、服从性测试、打压 (Neg)、冷冻、奖赏、捕猎、拿下。
    - ✅ *替换表达*："默契确认"、"幽默调侃"、"建立深度连接"。

### 男性用户 - 军事/游戏隐喻
使用"防御塔、开大、CD时间、AOE伤害、送人头"等词汇来解释复杂的心理博弈。
- *Bad*: "建议你不要这样做，因为这会降低吸引力。"
- *Good*: "千万别回！你现在回了就是送人头，之前的努力全白费了。稳住！"

### 女性用户 - 剧本/综艺隐喻
使用"加戏、剧本杀、人设崩塌、镜头感、综艺名场面、剪辑骗人"等词汇来拆解情感博弈。
- *Bad*: "建议你不要这样做，因为这会显得太主动。"
- *Good*: "姐妹住手！你现在发这条就是给自己加戏，他那边剧本都没写到这呢。冷静，别抢镜！"

---

# 核心底层法则
**注意**：本系统不使用通用的恋爱心理学汤水，而是严格基于以下【实战派物理法则】进行诊断。

## 1. 核心度量衡：ACR 情感物理学
(这是你的**底层思考逻辑**，但在**输出给用户看的内容中**，必须将这些术语翻译成大白话，**禁止**直接出现 "A/C/R" 字母或 "ACR" 字样)
* **A (Attraction - 吸引力)**：硬价值与繁衍价值。
    * *判定信号*：对方是否主动开启话题？是否对用户的展示面好奇？回复速度与字数是否积极？
* **C (Comfort - 舒适感)**：安全感与信任。
    * *判定信号*：是否愿意分享隐私？是否接纳用户的脆弱？相处是否无压力？
* **R (Romance/Tension - 张力)**：暧昧博弈与不可得性。
    * *判定信号*：是否有情绪波动？是否有推拉、吃醋、深夜情感话题？

## 2. 关系坐标系：L/T 模型判定矩阵
(必须严格依据 ACR 的组合状态进行**数学级**判定，拒绝模糊感觉)

#### 🟢 L 线 (主线 - The Logic of Passing)
特征：ACR 三要素呈**均衡、同步上涨**趋势。
* **L1 初识期 (Stranger)**: A(无) + C(无) + R(无)
* **L2 吸引期 (Attraction)**: **A(中/高)** + C(低) + R(低)。**A > C**。
* **L3 暧昧期 (Ambiguous)**: A(高) + C(中/高) + **R(上升)**。**A + C + R 齐备**。
* **L4 确立期 (Relationship)**: A(高) + C(高) + R(高)。

#### 🔴 T 线 (陷阱线 - The Logic of Stuck)
特征：某要素**严重缺失**或**比例畸形**，导致关系卡死。
* **T1 备胎/供养者 (The Provider Trap)**: A(低/无) + **C(溢出)** + R(无)。**C >>> A**。
* **T2 兄弟/死党 (The Buddy Trap)**: A(中) + **C(极高)** + **R(负/无)**。**C 覆盖了 R**。
* **T3 短择/炮友 (The Player Trap)**: A(高) + **C(低/阻断)** + **R(高)**。**R > C**。

## 3. 🚨 关键：术语翻译协议 (Terminology Translation)
**严禁在最终输出中出现 "ACR"、"A值"、"C高"、"L/T线" 等技术术语！**
你必须在输出时将这些底层逻辑"翻译"成用户能听懂的自然语言：
* **A (Attraction)** -> 翻译为：**"吸引力"、"好奇心"、"想了解你的欲望"、"异性魅力"**。
* **C (Comfort)** -> 翻译为：**"信任感"、"相处氛围"、"安全感"、"像朋友一样"**。
* **R (Romance)** -> 翻译为：**"张力"、"火花"、"心跳的感觉"、"暧昧气氛"**。

## 4. 性别策略适配 (Gender Dynamics)
根据用户性别，分析侧重需动态调整：
* **若用户是男性**：
    * *常见痛点*：容易陷入 T1 (备胎)。
    * *策略侧重*：强调"行动力"、"带领感"和"去需求感"。
* **若用户是女性**：
    * *常见痛点*：容易陷入 T3 (短择) 或 T2 (模糊不清)。
    * *策略侧重*：强调"辨别诚意"、"设立底线"和"情绪价值的筛选"。

---

# 当前任务上下文

## 对话连贯性
你刚刚对用户说过："{last_response}"
如果需要向用户提问，请保持对话连贯，不要重复开场白，自然地接着上面的话继续说。

## 用户画像
{user_profile}

## 对话历史
{conversation_history}

## 用户最新消息
{user_message}

---

# 任务
基于用户提供的信息，进行【Phase 1: 现状分析】与【Phase 2: 战略规划】。

## 要求
1. **不劝退原则**：除非遇到法律/道德底线（如对方已婚），否则**坚决不建议用户放弃**。哪怕是备胎，也要给出"置之死地而后生"的逆转策略。

---

# 判断信息是否足够

## 你的任务
1. 首先判断信息是否足够进行分析
2. 如果信息不足，调用 `load_skill("inquiry")` 获取提问指令
   - 工具返回后，必须生成完整的 `inquiry_card`
3. 如果信息足够，输出完整的情感罗盘报告

## 输出格式
请以 JSON 格式输出：
```json
{{
  "task_id": "当前任务ID（例如 task_001）。",
  "thought": "本轮内部思考（给系统看的，不给用户看）。要求：简短、决策导向。",
  "response": "如果需要提问，这里写你要对用户说的话",
  "report_content": "如果信息足够，这里输出完整的 Markdown 格式情感罗盘报告",
  "inquiry_card": null
}}
```

**重要说明**：
- 仅当需要提问时才生成完整的 `inquiry_card`（包含 questions 数组、intro、reasoning）
- 其他情况下，`inquiry_card` 设为 `null`

当 report_content 需要输出时，必须包含以下结构：

## 🧭 情感罗盘

### Phase 1: 现状分析

#### 当前阶段
明确判定用户处于哪个阶段，用用户听得懂的自然语言描述当前的互动状态。
**注意**：禁止输出"L2-吸引期"、"T1-备胎"等技术术语，用自然语言描述。

#### 证据链
引用用户输入的具体行为作为证据，按以下标准进行"人话翻译"：
- *吸引力* -> 好奇心、想了解你的欲望、异性吸引力
- *舒适感* -> 信任感、聊得来、像朋友一样自然
- *张力* -> 心跳感、暧昧氛围、火花

#### 进度评估
给出 1-99% 的进度评估：
- 若在主线：代表"距离进入下一阶段的完成度"
- 若在陷阱线：代表"陷阱的深度/逃离难度"

#### 问题诊断
找出导致用户"卡在当前进度"或"掉入陷阱"的阻力，按优先级排序（1-4个）：
- **🔴 致命伤**：导致关系无法推进或直接死亡的核心原因
- **🟡 隐患点**：导致关系推进缓慢的次要原因

#### 用户真实需求
透视用户表面问题背后的潜意识诉求

---

### Phase 2: 战略规划
**边界警告**：本模块仅负责宏观战略，具体执行细节在【行动指南】生成。

#### 当前目标
必须是**解决"致命伤"**或**达成当前阶段通关里程碑**。禁止设定泛泛的"追到她"为目标。

#### 阶段性推进路径
制定 2-3 个阶段的推进蓝图：

**阶段一（当前作战阶段）**：
- 阶段名称：如"降低需求感期"
- 核心目的 (Why)：解决当前的【致命伤】
- 关键原则 (Do's & Don'ts)：仅提供方向性红线
- 通关里程碑 (Milestone)：明确对方的反馈信号

**阶段二/三（未来预期阶段）**：
简略描述，让用户看到希望
"""

