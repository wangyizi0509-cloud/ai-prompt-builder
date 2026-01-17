"""
行动规划 Agent 节点 (Action Plan Agent)
负责制定宏观战略规划

采用 Tool-based 渐进式加载模式：
- 系统提示只包含 Skills 的元数据
- 模型通过 load_skill_instructions 工具按需加载完整指令

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
from graph.context_builder import build_context_dict
from graph.context_types import (
    create_new_task,
    create_empty_layer2_memory,
    create_action_plan_item,
)
from utils.message_utils import get_msg_role_and_content
from skills.inquiry import get_inquiry_skill
from skills import load_inquiry_skill_instructions
from utils.prompt_loader import load_prompt, get_prompt_path
from config import get_llm


# ============================================================
# 任务管理辅助函数
# ============================================================

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
    
    # 绑定工具：与 main_agent 保持一致，只有从工具返回时禁用
    llm = get_llm(temperature=0.6)
    if not from_tool_call:
        llm = llm.bind_tools([load_inquiry_skill_instructions])
    else:
        print("[DEBUG] PlanAgent: Second stage (from_tool_call), tools disabled to prevent loop")
    
    # 加载 Prompt
    try:
        prompt_name = "plan_agent"
        prompt_path = get_prompt_path(prompt_name)
        prompt_template = load_prompt(prompt_name)
        prompt_source = str(prompt_path)
        prompt_fallback = False
    except FileNotFoundError:
        prompt_template = _get_default_prompt()
        prompt_source = "fallback:_get_default_prompt(FileNotFoundError)"
        prompt_fallback = True
    
    # 获取主 Agent 刚说的话（用于保持对话连贯）
    last_response = state.get("last_response_for_continuity", "")
    
    # 构建上下文（使用新的分层上下文架构）
    context_dict = build_context_dict(state, target_agent="plan_agent")
    
    # 获取 InquirySkill 元数据 + 工具使用说明
    inquiry_skill = get_inquiry_skill()
    inquiry_metadata = f"""
---

## 📚 可用 Skill（通过工具按需加载）

{inquiry_skill.get_metadata_prompt()}

### 如何使用

**如果你在对话历史（工具输出）或下方的「刚刚获取到的 Skill 指令」中已经包含了所需指令，请直接根据指令生成回复，禁止重复调用工具。**

只有当信息不足需要提问，且 **还没有获取过提问指令** 时，请调用 `load_inquiry_skill_instructions()`。

---
"""
    # 注入工具指令（如果刚从工具返回）
    if from_tool_call and not last_tool_content:
        # 兜底：回溯查找最近一次 tool 输出
        for msg in reversed(messages or []):
            r, c = get_msg_role_and_content(msg)
            if r == "tool" and c:
                last_tool_content = c
                break

    if from_tool_call and last_tool_content:
        inquiry_metadata = f"""
{inquiry_metadata}

### ⚠️ 重要：你刚才已经成功获取了以下提问指令
{last_tool_content}

## 🟢 第二阶段执行指令 (CRITICAL)
你已经成功加载了提问 Skill 指令。现在是**第二阶段**。

**你主动请求了提问工具，说明你认为信息不足。请立即根据上面的 Skill 指令生成提问。**

**必填项检查**：
- 必须设置 `need_questions=true`
- 必须生成完整的 `inquiry_card` JSON 对象，**严禁**设为 null
- **严禁**直接输出规划结果（goal/strategy/phases 等），你必须先提问！

**禁止再次调用 load_inquiry_skill_instructions 工具！**
"""

    # 填充 Prompt
    from collections import defaultdict
    try:
        prompt = prompt_template.format_map(defaultdict(str, {
            # 新版：使用分层上下文
            "instruction": context_dict.get("instruction") or "无",
            "user_context": context_dict.get("user_context", "暂无用户信息"),
            "status_report": context_dict.get("status_report", "暂无"),
            "action_plan": context_dict.get("action_plan", "暂无"),
            "action_guides": context_dict.get("action_guides", "暂无"),
            "bound_action_guides": context_dict.get("bound_action_guides", ""),
            "conversation_history": context_dict.get("conversation_history", "无历史对话"),
            "current_task_id": context_dict.get("current_task_id", ""),
            "task_reasoning": context_dict.get("task_reasoning", ""),
            "last_response": last_response if last_response else "无",
            # 向后兼容
            "user_profile": context_dict.get("user_profile", "{}"),
            # Skills 元数据
            "inquiry_skill_metadata": inquiry_metadata,
        }))
    except Exception:
        prompt = _get_default_prompt()
        prompt_source = "fallback:_get_default_prompt(format_error)"
        prompt_fallback = True

    # === 调用 LLM（模型自主决定是否需要工具）===
    print(f"[DEBUG] PlanAgent: Invoking LLM (from_tool_call={from_tool_call})")
    
    # 归还工具箱：不再强制禁用工具
    response = llm.invoke(prompt)
    
    # 检查是否有工具调用
    if hasattr(response, "tool_calls") and response.tool_calls:
        # 模型决定调用工具，返回消息让 workflow 路由到 skill_tools
        print(f"[DEBUG] PlanAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
        return {
            "user_message": state.get("user_message", ""),
            "user_context": state.get("user_context", {}),
            # 兼容测试与工作流：工具调用阶段视为 ask_user（请求加载提问 Skill）
            "next_action": "ask_user",
            "need_questions": True,
            "inquiry_card": None,
            "messages": [response],
            "current_agent": "plan_agent",  # 标记调用来源
            "_tool_caller": "plan_agent",   # 显式标记工具调用来源
            "debug_log": [{
                "node": "plan_agent",
                "step": "Tool Call Requested",
                "tool_calls": [tc["name"] for tc in response.tool_calls],
            }]
        }
    
    # 没有工具调用，解析响应
    parsed = _parse_response(response.content)
    
    result = {
        "next_action": "end_turn",
        "debug_log": [{
            "node": "plan_agent",
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
    need_questions = bool(parsed.get("need_questions", False))
    inquiry_card = parsed.get("inquiry_card")

    questions_list = inquiry_card.get("questions", []) if isinstance(inquiry_card, dict) else []
    next_streak = (streak_count + 1) if (streak_agent == "plan_agent") else 1
    allow_ask = next_streak <= max_streak

    if need_questions and questions_list and allow_ask:
        print(f"[DEBUG] PlanAgent: Generated {len(inquiry_card.get('questions', []))} questions")
        
        result["inquiry_card"] = inquiry_card
        result["pending_questions"] = [q.get("question", "") if isinstance(q, dict) else str(q) for q in questions_list]
        
        # === 设置恢复状态 ===
        result["current_agent"] = "plan_agent"
        result["agent_resume_point"] = "continue_planning"
        # 连续提问计数
        result["question_streak_agent"] = "plan_agent"
        result["question_streak_count"] = next_streak
        # 旧字段：保持与 streak 对齐
        result["question_count"] = next_streak
        
        # 信息不足时，不生成规划，等待用户回答
        result["action_plan"] = None
        response_content = parsed.get("response", "")
        # 如果 Agent 没有生成回复，使用 intro 作为引导语
        if not response_content.strip() and inquiry_card.get("intro"):
            response_content = inquiry_card.get("intro")
        elif not response_content.strip():
            response_content = "为了给你制定更精准的计划，我需要再了解一些情况～"
        # 累积到 pending_responses（不覆盖之前的消息）
        existing_responses = state.get("pending_responses", [])
        result["pending_responses"] = existing_responses + [{
            "from": "plan_agent", 
            "content": response_content,
            "phase": "after_plan"  # 行动规划阶段的提问
        }]
        # 保留原始 LLM 输出，确保下一轮上下文能看到完整问题列表
        raw_assistant_msg = response.content if getattr(response, "content", None) else response_content
        result["messages"] = [{
            "role": "assistant",
            "content": raw_assistant_msg,
            "metadata": {
                "task_id": parsed.get("task_id"),
                "thought": parsed.get("thought"),
            }
        }]
        # 未完成，不设置完成信号
        result["completion_status"] = None
        result["result_summary"] = None

    else:
        # 不需要提问或已生成规划
        if not need_questions:
            # === 分配规划编号 ===
            report_counter = state.get("report_counter", {"status_report": 0, "action_plan": 0, "action_guide": 0})
            new_plan_id = report_counter.get("action_plan", 0) + 1
            
            plan_markdown = _format_plan_as_markdown(parsed)
            result["action_plan"] = plan_markdown  # Markdown string for frontend rendering
            result["action_plan_id"] = new_plan_id
            
            # 更新报告计数器
            result["report_counter"] = {
                **report_counter,
                "action_plan": new_plan_id
            }

            # === 写入 Layer 2 真源（current_action_plan + action_plan_history）===
            layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
            
            # 获取当前规划和历史规划
            old_current = layer2_memory.get("current_action_plan")
            history = list(layer2_memory.get("action_plan_history", []))
            
            # 将旧 current 移入历史（summary/one_liner 由异步归档补齐）
            if old_current:
                history.insert(0, old_current)

            new_plan_item = create_action_plan_item(
                plan_content=plan_markdown,
                plan_id=new_plan_id,
                goal=parsed.get("goal", "") or "",
                strategy=parsed.get("strategy", "") or "",
                phases=parsed.get("phases", []) or [],
                key_principles=parsed.get("key_principles", []) or [],
            )

            updated_layer2 = dict(layer2_memory)
            updated_layer2["current_action_plan"] = new_plan_item
            updated_layer2["action_plan_history"] = history
            updated_layer2["last_updated"] = datetime.now().isoformat()
            updated_layer2["version"] = layer2_memory.get("version", 1) + 1
            result["layer2_memory"] = updated_layer2
            
            # === 清除恢复状态 ===
            result["current_agent"] = None
            result["agent_resume_point"] = None
            # 非提问动作：清零“连续提问计数”
            result["question_streak_agent"] = None
            result["question_streak_count"] = 0
            # 旧字段清零
            result["question_count"] = 0
            result["collected_info"] = {}
            # 显式清除 inquiry_card，避免残留上一轮的问题
            result["inquiry_card"] = None
            result["pending_questions"] = []
            
            # === 设置完成信号 ===
            result["completion_status"] = "COMPLETED"
            result["result_summary"] = f"行动规划完成：{parsed.get('goal', '')} - {parsed.get('strategy', '')}"
            
            # === 完成当前任务 ===
            task_complete_updates = _complete_current_task(state)
            if "task_registry" in task_complete_updates:
                result["task_registry"] = task_complete_updates.get("task_registry", {})
            
            # === 在 Layer 3 记录规划产出 ===
            result["messages"] = [{
                "role": "assistant",
                "content": f"（行动规划{new_plan_id}已生成）",
                "metadata": {
                    "task_id": parsed.get("task_id"),
                    "thought": parsed.get("thought"),
                }
            }]
            
            print(f"[DEBUG] PlanAgent: Plan {new_plan_id} generated")
        else:
            result["messages"] = []
            
        # 保留现有的 pending_responses，不覆盖
        existing_responses = state.get("pending_responses", [])
        result["pending_responses"] = existing_responses
        
    # === 清除工具调用来源（防止无限循环） ===
    result["_tool_caller"] = None
    
    # === 合并任务管理更新 ===
    if task_updates:
        if "task_registry" in task_updates:
            result["task_registry"] = task_updates.get("task_registry", {})
    
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
            "need_questions": False,
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
2. 如果信息不足，设置 `need_questions=true`（不需要填写 `question_goal`，目标在你心中即可）
   - 如果设置了 `need_questions=true`，系统会自动加载「提问引导 Skill」的完整指令，你需要生成完整的 `inquiry_card`
3. 如果信息足够，输出规划结果

## 输出格式
请以 JSON 格式输出：
```json
{{
  "task_id": "当前任务ID（例如 task_001）。",
  "thought": "本轮内部思考（给系统看的，不给用户看）。要求：简短、决策导向。",
  "need_questions": false,
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

