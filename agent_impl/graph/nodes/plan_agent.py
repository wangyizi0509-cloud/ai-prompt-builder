"""
行动规划 Agent 节点 (Action Plan Agent)
负责制定宏观战略规划

上下文架构更新 (v2.0)：
- 使用分层上下文架构（Layer 0-4）
- 通过 context_builder 统一组装上下文

任务管理更新 (v2.1)：
- 任务边界：被调用时开始新任务，产出规划时结束
- 思考过程：同一任务内保留，任务结束时归档
- 报告编号：每次产出规划分配递增编号
"""

import json
from typing import Any
from datetime import datetime

from graph.state import AgentState, ActionPlan
from graph.message_builder import build_messages_for_model
from graph.context_types import create_new_task
from utils.message_utils import get_msg_role_and_content
from graph.tools.ask_tool import get_ask_tool
from graph.tools.submit_tools import submit_action_plan, return_to_main
from config import get_llm, get_thinking_llm, is_thinking_with_tools_enabled


# ============================================================
# 任务管理辅助函数
# ============================================================

def _extract_reasoning_content(response) -> str | None:
    if response is None:
        return None
    additional_kwargs = getattr(response, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict) and additional_kwargs.get("reasoning_content"):
        return additional_kwargs.get("reasoning_content")
    return getattr(response, "reasoning_content", None)

def _get_next_task_id(task_list: list) -> str:
    """生成下一个任务 ID"""
    if not task_list:
        return "task_001"
    
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
    """开始新任务"""
    task_registry = state.get("task_registry", {})
    task_list = list(task_registry.get("plan_agent", []))
    
    for task in task_list:
        task["is_active"] = False
    
    new_task_id = _get_next_task_id(task_list)
    new_task = create_new_task(new_task_id)
    task_list.append(new_task)
    
    print(f"[DEBUG] PlanAgent: Started new task {new_task_id}")
    
    return {
        "task_registry": {
            **task_registry,
            "plan_agent": task_list,
        }
    }


def _complete_current_task(state: AgentState) -> dict:
    """完成当前任务"""
    task_registry = state.get("task_registry", {})
    task_list = list(task_registry.get("plan_agent", []))
    
    for task in task_list:
        if task.get("is_active", False):
            task["is_active"] = False
            task["completed_at"] = datetime.now().isoformat()
            print(f"[DEBUG] PlanAgent: Completed task {task.get('task_id')}")
            break
    
    return {
        "task_registry": {
            **task_registry,
            "plan_agent": task_list,
        }
    }

def plan_agent_node(state: AgentState) -> dict[str, Any]:
    """
    行动规划 Agent 节点
    
    职责：
    1. 基于现状分析制定宏观战略
    2. 设定阶段性目标
    3. 确定核心策略方向
    4. 规划分阶段计划
    5. 如果信息不足，通过工具获取提问技能指令
    
    任务边界：
    - 新任务触发：被调用时（非恢复执行）
    - 任务结束：产出规划（completion_status=COMPLETED）
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    # 提问节流（同一 agent 连续提问 <= max_question_streak；中间发生非提问动作则清零）
    streak_agent = state.get("question_streak_agent")
    streak_count = int(state.get("question_streak_count", 0) or 0)
    max_streak = int(state.get("max_question_streak", 3) or 3)

    # 向后兼容：旧字段仍可能被外部依赖（日志/测试）
    question_count = int(state.get("question_count", 0) or 0)
    max_questions = int(state.get("max_questions", 3) or 3)
    
    # === 任务边界判定 ===
    is_resuming = (state.get("current_agent") == "plan_agent" and 
                   state.get("agent_resume_point") == "continue_planning")
    
    task_updates = {}
    if not is_resuming:
        task_updates = _start_new_task(state)
    
    # 工具调用返回检查（增强版）
    messages = state.get("messages", [])
    last_msg_role = ""
    last_tool_content = None
    if messages:
        last_msg_role, last_tool_content = get_msg_role_and_content(messages[-1])
    
    from_tool_call = (state.get("_tool_caller") == "plan_agent" or last_msg_role == "tool")
    
    if from_tool_call:
        print(f"[DEBUG] PlanAgent: Continuing after tool call (last_role={last_msg_role})")
    
    # 准备 LLM（工具绑定在决策后进行）
    # 如果启用了思考模式+工具调用，使用 get_thinking_llm
    if is_thinking_with_tools_enabled():
        base_llm = get_thinking_llm(temperature=0.6)
    else:
        base_llm = get_llm(temperature=0.6, use_tools=True)
    if from_tool_call:
        print("[DEBUG] PlanAgent: Second stage (from_tool_call), tools disabled to prevent loop")
    
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
    # 否则模型会看到类似这样的消息栈：
    #   ...历史对话...
    #   plan_agent: (tool_call)
    #   tool: inquiry skill 指令
    #   user: "好"  ← 这会误导模型认为用户已确认，直接跳过提问
    current_input = "" if from_tool_call else state.get("user_message", "")
    
    model_messages = build_messages_for_model(
        state=state,
        agent_name="plan_agent",
        current_input=current_input,
    )
    prompt_source = "message_builder"
    prompt_fallback = False

    # === 调用 LLM（工具驱动）===
    ask_mode = state.get("ask_mode", False)
    print(f"[DEBUG] PlanAgent: Invoking LLM (from_tool_call={from_tool_call}, ask_mode={ask_mode})")
    response = None
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
            print("[DEBUG] PlanAgent: Forced ask tool call (Phase 2: generate inquiry_card)")
            if hasattr(response, "name"):
                response.name = "plan_agent"
            reasoning_content = _extract_reasoning_content(response)
            return {
                "messages": [response],
                "current_agent": "plan_agent",
                "_tool_caller": "plan_agent",
                "_reasoning_content_cache": reasoning_content,
                "debug_log": [{
                    "node": "plan_agent",
                    "step": "Tool Call Requested (ask forced, Phase 2)",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }],
            }
    
    elif from_tool_call:
        # 允许在委派后继续发起 ask/submit 工具调用
        ask_tool = get_ask_tool(False)
        llm_with_tools = base_llm.bind_tools(
            [ask_tool, submit_action_plan, return_to_main],
            parallel_tool_calls=True,
        )
        response = llm_with_tools.invoke(model_messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"[DEBUG] PlanAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
            if hasattr(response, "name"):
                response.name = "plan_agent"
            reasoning_content = _extract_reasoning_content(response)
            return {
                "messages": [response],
                "current_agent": "plan_agent",
                "_tool_caller": "plan_agent",
                "_reasoning_content_cache": reasoning_content,
                "debug_log": [{
                    "node": "plan_agent",
                    "step": "Tool Call Requested",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }],
            }
    else:
        # 使用定制工具：plan_agent 只允许使用 inquiry skill
        # 允许子 Agent 直接进入 ask 两阶段提问（Phase 1: ask(action="enable")）
        ask_tool = get_ask_tool(False)
        llm_with_tools = base_llm.bind_tools(
            [ask_tool, submit_action_plan, return_to_main],
            parallel_tool_calls=True,
        )
        response = llm_with_tools.invoke(model_messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"[DEBUG] PlanAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
            if hasattr(response, "name"):
                response.name = "plan_agent"
            reasoning_content = _extract_reasoning_content(response)
            return {
                "messages": [response],
                "current_agent": "plan_agent",
                "_tool_caller": "plan_agent",
                "_reasoning_content_cache": reasoning_content,
                "debug_log": [{
                    "node": "plan_agent",
                    "step": "Tool Call Requested",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }],
            }
    
    # 模型未调用工具，直接返回模型的回复内容
    print(f"[DEBUG] PlanAgent: No tool call, returning model response directly")
    if hasattr(response, "name"):
        response.name = "plan_agent"
    reasoning_content = _extract_reasoning_content(response)
    result = {
        "messages": [response],
        "current_agent": "plan_agent",
        "_tool_caller": None,
        "_reasoning_content_cache": reasoning_content,
        "debug_log": [{
            "node": "plan_agent",
            "step": "No Tool Call - Direct Response",
        }],
    }
    if task_updates and "task_registry" not in result:
        result["task_registry"] = task_updates.get("task_registry", state.get("task_registry", {}))
    return result


def _format_history(messages: list) -> str:
    """格式化对话历史，包含工具调用结果"""
    if not messages:
        return "无历史对话"
    
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
        return {
            "task_id": "",
            "thought": "",
            "goal": "建立良好的互动关系",
            "strategy": "需要更多信息来制定具体策略",
            "phases": [],
            "key_principles": ["保持真诚", "循序渐进"],
            "summary": "基于目前的信息，建议先建立稳定的互动模式",
        }


def _build_action_plan(data: dict) -> ActionPlan:
    """从解析的数据构建 ActionPlan"""
    return ActionPlan(
        goal=data.get("goal", "建立良好的互动关系"),
        strategy=data.get("strategy", "循序渐进，稳步推进"),
        phases=data.get("phases", []),
        key_principles=data.get("key_principles", []),
        summary=data.get("summary", ""),
    )


def _format_plan_as_markdown(data: dict) -> str:
    """将规划结果转为 Markdown 供前端直接渲染"""
    parts = []
    if data.get("goal"):
        parts.append(f"## 阶段目标\n{data['goal']}\n")
    if data.get("strategy"):
        parts.append(f"## 核心策略\n{data['strategy']}\n")
    if data.get("phases"):
        parts.append("## 分阶段计划\n")
        for i, phase in enumerate(data.get("phases", []), 1):
            name = phase.get("name", f"阶段{i}")
            desc = phase.get("description", "")
            duration = phase.get("duration")
            milestone = phase.get("milestone")
            parts.append(f"### 阶段 {i}: {name}\n")
            if desc:
                parts.append(f"{desc}\n")
            if duration:
                parts.append(f"- 预计时长: {duration}\n")
            if milestone:
                parts.append(f"- 里程碑: {milestone}\n")
    if data.get("key_principles"):
        parts.append("## 关键原则\n")
        for p in data.get("key_principles", []):
            parts.append(f"- {p}\n")
    if data.get("summary"):
        parts.append(f"## 规划总结\n{data.get('summary')}\n")
    return "\n".join(parts)


def _generate_response(action_plan: ActionPlan) -> str:
    """根据规划结果生成回复"""
    goal = action_plan.get("goal", "")
    strategy = action_plan.get("strategy", "")
    phases = action_plan.get("phases", [])
    key_principles = action_plan.get("key_principles", [])
    
    response_parts = [
        f"好的，基于前面的分析，我帮你制定了一个行动规划：\n",
        f"\n**阶段目标**: {goal}\n",
        f"\n**核心策略**: {strategy}\n",
    ]
    
    if phases:
        response_parts.append("\n**分阶段计划**:")
        for i, phase in enumerate(phases[:3], 1):
            phase_name = phase.get("name", f"阶段{i}")
            phase_desc = phase.get("description", "")
            response_parts.append(f"\n{i}. **{phase_name}**: {phase_desc}")
    
    if key_principles:
        response_parts.append("\n\n**关键原则**:")
        for principle in key_principles[:3]:
            response_parts.append(f"\n• {principle}")
    
    response_parts.append("\n\n这个规划你觉得怎么样？如果没问题，我可以帮你生成具体的行动指南。")
    
    return "".join(response_parts)


def _get_default_prompt() -> str:
    """获取默认 Prompt"""
    return """你是小话，一个专业的 AI 恋爱军师，正在为用户制定行动规划。

## 对话连贯性
你刚刚对用户说过："{last_response}"
如果需要向用户提问，请保持对话连贯，不要重复开场白，自然地接着上面的话继续说。

## 用户画像
{user_profile}

## 现状分析报告
{status_report}

## 对话历史
{conversation_history}

## 规划原则
1. **目标明确**：设定清晰的阶段性目标
2. **策略可行**：确保策略符合用户实际情况
3. **循序渐进**：分阶段推进，避免操之过急
4. **风险可控**：考虑潜在风险并预留调整空间

---

{inquiry_skill_metadata}

# 判断信息是否足够

## 你的任务
1. 判断信息是否足够制定规划
2. 如果信息不足，使用 `ask` 两阶段提问（先 `ask(action="enable")`，再 `ask(questions=[...], intro=..., reasoning=...)`）
3. 如果信息足够，输出规划结果

## 输出格式
请以 JSON 格式输出：
```json
{{
  "task_id": "当前任务ID（例如 task_001）。",
  "thought": "本轮内部思考（给系统看的，不给用户看）。要求：简短、决策导向。",
  "response": "如果需要提问，这里写你要对用户说的话（保持连贯，不要重复开场）",
  "inquiry_card": null,
  "goal": "阶段性目标",
  "strategy": "核心策略方向",
  "phases": [
    {{
      "name": "阶段名称",
      "description": "阶段描述",
      "duration": "预计时长",
      "key_actions": ["关键动作1", "关键动作2"]
    }}
  ],
  "key_principles": ["关键原则1", "关键原则2"],
  "summary": "规划总结"
}}
```
"""

