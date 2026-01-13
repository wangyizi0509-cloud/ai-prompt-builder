"""
行动规划 Agent 节点 (Action Plan Agent)
负责制定宏观战略规划

采用 Tool-based 渐进式加载模式：
- 系统提示只包含 Skills 的元数据
- 模型通过 load_skill_instructions 工具按需加载完整指令

上下文架构更新 (v2.0)：
- 使用分层上下文架构（Layer 0-4）
- 通过 context_builder 统一组装上下文
"""

import json
from typing import Any

from graph.state import AgentState, ActionPlan
from graph.context_builder import build_context_dict
from skills.inquiry import get_inquiry_skill
from skills import load_skill_instructions
from utils.prompt_loader import load_prompt
from config import get_llm


def plan_agent_node(state: AgentState) -> dict[str, Any]:
    """
    行动规划 Agent 节点
    
    职责：
    1. 基于现状分析制定宏观战略
    2. 设定阶段性目标
    3. 确定核心策略方向
    4. 规划分阶段计划
    5. 如果信息不足，通过工具获取提问技能指令
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    # 绑定 Skill 加载工具
    llm = get_llm(temperature=0.6).bind_tools([load_skill_instructions])
    
    # === 恢复执行检查 ===
    is_resuming = (state.get("current_agent") == "plan_agent" and 
                   state.get("agent_resume_point") == "continue_planning")
    question_count = state.get("question_count", 0)
    max_questions = state.get("max_questions", 3)
    collected_info = state.get("collected_info", {})
    
    # 工具调用返回检查
    from_tool_call = state.get("_tool_caller") == "plan_agent"
    
    if is_resuming:
        print(f"[DEBUG] PlanAgent resuming from question {question_count}")
    elif from_tool_call:
        print(f"[DEBUG] PlanAgent: Continuing after tool call")
    
    # 加载 Prompt
    try:
        prompt_template = load_prompt("plan_agent")
    except FileNotFoundError:
        prompt_template = _get_default_prompt()
    
    # 获取主 Agent 刚说的话（用于保持对话连贯）
    last_response = state.get("last_response_for_continuity", "")
    
    # 构建上下文（使用新的分层上下文架构）
    context_dict = build_context_dict(state)
    
    # 获取 InquirySkill 元数据 + 工具使用说明
    inquiry_skill = get_inquiry_skill()
    inquiry_metadata = f"""
---

## 📚 可用 Skill（通过工具按需加载）

{inquiry_skill.get_metadata_prompt()}

### 如何使用

如果信息不足需要提问，请调用 `load_skill_instructions(skill_id="inquiry_skill")` 获取完整的提问指令。

---
"""
    
    # 填充 Prompt
    prompt = prompt_template.format(
        # 新版：使用分层上下文
        user_context=context_dict.get("user_context", "暂无用户信息"),
        status_report=context_dict.get("status_report", "暂无"),
        conversation_history=context_dict.get("conversation_history", "无历史对话"),
        last_response=last_response if last_response else "无",
        # 向后兼容
        user_profile=context_dict.get("user_profile", "{}"),
        # Skills 元数据
        inquiry_skill_metadata=inquiry_metadata,
    )
    
    # === 调用 LLM（模型自主决定是否需要工具）===
    print(f"[DEBUG] PlanAgent: Invoking LLM with tool binding")
    response = llm.invoke(prompt)
    
    # 检查是否有工具调用
    if hasattr(response, "tool_calls") and response.tool_calls:
        # 模型决定调用工具，返回消息让 workflow 路由到 skill_tools
        print(f"[DEBUG] PlanAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
        return {
            "messages": [response],
            "current_agent": "plan_agent",  # 标记调用来源
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
            "step": "Response Generated" + (" (resumed)" if is_resuming else ""),
            "prompt": prompt,
            "response": response.content,
            "parsed_result": parsed,
            "question_count": question_count,
        }],
    }
    
    # 检查是否需要提问
    need_questions = parsed.get("need_questions", False)
    inquiry_card = parsed.get("inquiry_card")
    
    if need_questions and inquiry_card and inquiry_card.get("questions") and question_count < max_questions:
        print(f"[DEBUG] PlanAgent: Generated {len(inquiry_card.get('questions', []))} questions")
        
        result["inquiry_card"] = inquiry_card
        result["pending_questions"] = [q.get("question", "") if isinstance(q, dict) else str(q) for q in inquiry_card.get("questions", [])]
        
        # === 设置恢复状态 ===
        result["current_agent"] = "plan_agent"
        result["agent_resume_point"] = "continue_planning"
        result["question_count"] = question_count + 1
        result["collected_info"] = collected_info
        
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
        result["messages"] = [{"role": "assistant", "content": response_content}]
        # 未完成，不设置完成信号
        result["completion_status"] = None
        result["result_summary"] = None
    else:
        # 不需要提问或已生成规划
        if not need_questions:
            action_plan = _build_action_plan(parsed)
            result["action_plan"] = action_plan
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
            result["result_summary"] = f"行动规划完成：{action_plan.get('goal', '')} - {action_plan.get('strategy', '')}"
            
            # 子 Agent 完成时不发送对话消息，完整报告在看板（action_plan）中展示
        # 保留现有的 pending_responses，不覆盖
        existing_responses = state.get("pending_responses", [])
        result["pending_responses"] = existing_responses
        result["messages"] = []
    
    return result


def _format_history(messages: list) -> str:
    """格式化对话历史"""
    if not messages:
        return "无历史对话"
    
    recent = messages[-10:]
    formatted = []
    for msg in recent:
        role = "用户" if msg["role"] == "user" else "小话"
        formatted.append(f"{role}: {msg['content']}")
    
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

## 你的任务
1. 判断信息是否足够制定规划
2. 如果信息不足，设置 `need_questions=true`（不需要填写 `question_goal`，目标在你心中即可）
   - 如果设置了 `need_questions=true`，系统会自动加载「提问引导 Skill」的完整指令，你需要生成完整的 `inquiry_card`
3. 如果信息足够，输出规划结果

## 输出格式
请以 JSON 格式输出：
```json
{{
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

