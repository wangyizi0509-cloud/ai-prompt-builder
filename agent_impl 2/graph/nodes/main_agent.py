"""
主 Agent 节点 (Main Agent)
决策中枢，负责回应用户和决策下一步行动

采用 Anthropic 渐进式加载模式（Tool-based）：
- 系统提示只包含 Skills 的元数据（name + description）
- 模型通过 load_skill_instructions 工具按需加载完整技能指令
- 工作流自动处理工具调用循环

支持的功能：
1. 回应用户（简短、共情、承上启下）
2. 决策下一步行动（调用子 Agent 或结束本轮）
3. 如需提问，调用 load_skill_instructions 工具获取提问指令
4. 子 Agent 返回后再决策（灵活判断，无固定流程）
5. 根据意图类型使用咨询 Skills 直接回复（解答疑惑、情感陪伴）

上下文架构更新 (v2.0)：
- 使用分层上下文架构（Layer 0-4）
- 通过 context_builder 统一组装上下文
"""

import json
from typing import Any

from graph.state import AgentState
from graph.context_builder import build_context_dict
from skills import get_inquiry_skill, get_consult_answer_skill, get_emotion_support_skill, load_skill_instructions
from utils.prompt_loader import load_prompt
from config import get_llm


def main_agent_node(state: AgentState) -> dict[str, Any]:
    """
    主 Agent 节点
    
    职责：
    1. 回应用户（简短、共情、承上启下）
    2. 决策下一步行动（调用子 Agent 或结束本轮）
    3. 如需技能指令，通过 load_skill_instructions 工具获取
    4. 子 Agent 返回后再决策（灵活判断，无固定流程）
    5. 使用咨询 Skills 直接回复（解答疑惑、情感陪伴）
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    # 绑定 Skill 加载工具
    llm = get_llm(temperature=0.7).bind_tools([load_skill_instructions])
    
    # === 检测执行模式 ===
    # 模式1：从提问中恢复（主 Agent 之前提问，用户回答了）
    is_resuming = (state.get("current_agent") == "main_agent" and 
                   state.get("agent_resume_point") == "continue_decision")
    
    # 模式2：子 Agent 返回后的再决策
    from_sub_agent = state.get("completion_status") is not None
    
    # 模式3：工具调用返回（skill_tools 执行完成后回到这里）
    from_tool_call = state.get("_tool_caller") == "main_agent"
    
    if is_resuming:
        print(f"[DEBUG] MainAgent: Resuming from ask_user, question_count={state.get('question_count', 0)}")
    elif from_sub_agent:
        print(f"[DEBUG] MainAgent: Re-decision after sub-agent, status={state.get('completion_status')}, summary={state.get('result_summary')}")
    elif from_tool_call:
        print(f"[DEBUG] MainAgent: Continuing after tool call")
    
    # === 获取提问状态（用于恢复执行）===
    question_count = state.get("question_count", 0)
    max_questions = state.get("max_questions", 3)
    
    # 加载 Prompt
    try:
        prompt_template = load_prompt("main_agent")
    except FileNotFoundError:
        prompt_template = _get_default_prompt(from_sub_agent, is_resuming)
    
    # 构建上下文（使用新的分层上下文架构）
    context_dict = build_context_dict(state)
    
    # 填充 Prompt
    format_kwargs = {
        "user_message": state.get("user_message", ""),
        # 新版：使用分层上下文
        "user_context": context_dict.get("user_context", "暂无用户信息"),
        "status_report": context_dict.get("status_report", "暂无"),
        "action_plan": context_dict.get("action_plan", "暂无"),
        "action_guide": context_dict.get("action_guides", "暂无"),  # 新版支持多个指南
        "action_guides": context_dict.get("action_guides", "暂无"),
        "conversation_history": context_dict.get("conversation_history", "无历史对话"),
        # 向后兼容：保留旧版变量
        "user_profile": context_dict.get("user_profile", "{}"),
        # Skills 元数据 + 工具使用说明
        "skills_prompt": _get_skills_metadata_prompt(),
    }
    
    # 如果是再决策，添加子 Agent 完成信号信息
    if from_sub_agent:
        format_kwargs["completion_status"] = state.get("completion_status", "")
        format_kwargs["result_summary"] = state.get("result_summary", "")
    
    # 如果是恢复执行，添加恢复上下文
    if is_resuming:
        format_kwargs["is_resuming"] = True
        format_kwargs["question_count"] = question_count
    
    prompt = prompt_template.format(**format_kwargs)
    
    # === 调用 LLM（模型自主决定是否需要工具）===
    print(f"[DEBUG] MainAgent: Invoking LLM with tool binding")
    response = llm.invoke(prompt)
    
    # 检查是否有工具调用
    if hasattr(response, "tool_calls") and response.tool_calls:
        # 模型决定调用工具，返回消息让 workflow 路由到 skill_tools
        print(f"[DEBUG] MainAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
        return {
            "messages": [response],
            "current_agent": "main_agent",  # 标记调用来源
            "debug_log": [{
                "node": "main_agent",
                "step": "Tool Call Requested",
                "tool_calls": [tc["name"] for tc in response.tool_calls],
            }]
        }
    
    # 没有工具调用，解析响应
    result = _parse_response(response.content, state)
    
    # 记录调试日志
    result["debug_log"] = [{
        "node": "main_agent",
        "step": "Response Generated",
        "prompt": prompt,
        "response": response.content,
        "parsed_result": result.copy()
    }]
    
    # === 处理提问逻辑 ===
    response_content = result.get("response_content", "")
    next_action = result.get("next_action", "end_turn")
    inquiry_card = result.get("inquiry_card")
    need_questions = result.get("need_questions", False)
    
    # 检查是否需要提问 (兼容 next_action="ask_user" 或 need_questions=true)
    need_to_ask = (next_action == "ask_user" or need_questions)
    
    if need_to_ask and question_count < max_questions:
        print(f"[DEBUG] MainAgent: ask_user triggered (count={question_count}/{max_questions})")
        
        # 检查是否有完整的 inquiry_card
        if inquiry_card and inquiry_card.get("questions"):
            # 提取问题列表
            questions = inquiry_card.get("questions", [])
            result["pending_questions"] = [q.get("question", "") if isinstance(q, dict) else str(q) for q in questions]
            print(f"[DEBUG] MainAgent: Generated {len(questions)} questions")
            
            # 引导语处理
            intro = inquiry_card.get("intro", "")
            if intro and not response_content.strip():
                response_content = intro
                result["response_content"] = response_content
            
            # === 设置暂停-恢复状态 ===
            result["next_action"] = "ask_user"
            result["current_agent"] = "main_agent"
            result["agent_resume_point"] = "continue_decision"
            result["question_count"] = question_count + 1
            
            print(f"[DEBUG] MainAgent: Setting pause state, will resume after user answers")
        else:
            # 没有生成完整的 inquiry_card，降级处理
            print(f"[WARNING] MainAgent: inquiry_card missing or incomplete, falling back to end_turn")
            result["next_action"] = "end_turn"
            result["inquiry_card"] = None
            result["pending_questions"] = []
    
    elif next_action == "ask_user" and question_count >= max_questions:
        # 已达到最大提问次数，强制继续
        print(f"[DEBUG] MainAgent: Reached max questions ({max_questions}), proceeding without more questions")
        result["inquiry_card"] = None
        result["pending_questions"] = []
        result["next_action"] = "end_turn"
        
    else:
        # 不需要提问
        if not inquiry_card:
            result["inquiry_card"] = None
        result["pending_questions"] = []
        
        # 清除暂停状态（如果是从恢复执行来的）
        if is_resuming:
            result["current_agent"] = None
            result["agent_resume_point"] = None
            result["question_count"] = 0
    
    # === 处理 pending_responses ===
    # 获取当前已有的 pending_responses（可能由之前的子 Agent 添加）
    existing_responses = state.get("pending_responses", [])
    next_action = result.get("next_action", "end_turn")
    
    # 如果主 Agent 有回复内容，添加到 pending_responses
    if response_content:
        # 根据是否是再决策和下一步动作，决定 phase
        if from_sub_agent:
            # 再决策模式：根据刚完成的任务决定 phase
            result_summary = state.get("result_summary", "")
            if "现状分析" in result_summary:
                phase = "after_status"
            elif "行动规划" in result_summary:
                phase = "after_plan"
            elif "行动指南" in result_summary:
                phase = "after_guide"
            else:
                phase = "immediate"
        else:
            # 首次回复，立即展示
            phase = "immediate"
        
        result["pending_responses"] = existing_responses + [{
            "from": "main_agent", 
            "content": response_content,
            "phase": phase
        }]
        result["messages"] = [{"role": "assistant", "content": response_content}]
        
        # 如果要调用子 Agent，记录这次回复以保持对话连贯
        if next_action in ["call_status", "call_plan", "call_guide"]:
            result["last_response_for_continuity"] = response_content
        else:
            result["last_response_for_continuity"] = None
    else:
        # 主 Agent 不说话，保留现有的 pending_responses
        result["pending_responses"] = existing_responses
        result["messages"] = []
        result["last_response_for_continuity"] = None
    
    # === 清除子 Agent 完成信号（再决策完成） ===
    result["completion_status"] = None
    result["result_summary"] = None
    
    # === 防止重复调用子 Agent（关键修复：必须在清除完成信号之后检查）===
    # 如果刚完成某个子 Agent，并且对应的结果已经存在，强制结束本轮，避免无限循环
    if from_sub_agent:
        # 从 state 中获取（因为 result 中已经清除了）
        result_summary = state.get("result_summary", "")
        next_action = result.get("next_action", "end_turn")
        
        # 检查是否刚完成某个子 Agent，并且又要调用同一个 Agent
        should_force_end = False
        force_end_reason = ""
        
        if "现状分析" in result_summary and next_action == "call_status":
            # 刚完成 StatusAgent，又要调用 StatusAgent
            status_report = state.get("status_report")
            if status_report:
                should_force_end = True
                force_end_reason = "StatusAgent"
        
        elif "行动规划" in result_summary and next_action == "call_plan":
            # 刚完成 PlanAgent，又要调用 PlanAgent
            action_plan = state.get("action_plan")
            if action_plan:
                should_force_end = True
                force_end_reason = "PlanAgent"
        
        elif "行动指南" in result_summary and next_action == "call_guide":
            # 刚完成 GuideAgent，又要调用 GuideAgent
            action_guides = state.get("action_guides", [])
            action_guide = state.get("action_guide")
            if action_guides or action_guide:
                should_force_end = True
                force_end_reason = "GuideAgent"
        
        if should_force_end:
            print(f"[DEBUG] MainAgent: {force_end_reason} just completed, forcing end_turn to prevent infinite loop")
            result["next_action"] = "end_turn"
            # 如果没有回复内容，给一个默认的过渡回复
            if not result.get("response_content"):
                if force_end_reason == "StatusAgent":
                    result["response_content"] = "现状分析已经完成，接下来我帮你规划一下行动方向～"
                elif force_end_reason == "PlanAgent":
                    result["response_content"] = "行动规划已经完成，接下来我为你生成具体的行动指南～"
                elif force_end_reason == "GuideAgent":
                    result["response_content"] = "好的，行动指南已经为你准备好了，快去执行吧！有任何进展记得回来告诉我～"
    
    # === 处理行动完成检测 ===
    mark_guide_completed = result.get("mark_guide_completed", False)
    completed_guide_id = result.get("completed_guide_id")
    
    if mark_guide_completed and completed_guide_id:
        print(f"[DEBUG] MainAgent: Detected guide completion, guide_id={completed_guide_id}")
        
        # 查找指南
        action_guides = state.get("action_guides", [])
        guide_index = None
        guide = None
        
        for idx, g in enumerate(action_guides):
            if g.get("id") == completed_guide_id:
                guide_index = idx
                guide = g
                break
        
        # 如果找不到指定ID，尝试找最近的一个 pending 或 in_progress 的指南
        if not guide:
            for idx, g in enumerate(action_guides):
                if g.get("status") in ("pending", "in_progress"):
                    guide_index = idx
                    guide = g
                    completed_guide_id = g.get("id")
                    break
        
        if guide and guide.get("status") != "completed":
            from datetime import datetime
            from graph.archive_manager import archive_guide_on_completion
            
            # 更新指南状态
            updated_guide = guide.copy()
            updated_guide["status"] = "completed"
            updated_guide["completed_at"] = datetime.now().isoformat()
            updated_guide["execution_status"] = "normal"  # 默认值，用户可以通过前端按钮提供更详细的反馈
            updated_guide["user_feedback"] = ""  # Agent检测到的完成，没有详细反馈
            
            # 更新 state 中的指南列表
            updated_guides = list(action_guides)
            updated_guides[guide_index] = updated_guide
            result["action_guides"] = updated_guides
            
            # 调用归档函数
            try:
                # 创建临时 state 用于归档
                temp_state = state.copy()
                temp_state["action_guides"] = updated_guides
                
                archive_updates = archive_guide_on_completion(updated_guide, temp_state)
                
                # 合并归档更新到 result
                if "history_archive" in archive_updates:
                    result["history_archive"] = archive_updates["history_archive"]
                if "user_context" in archive_updates:
                    result["user_context"] = archive_updates["user_context"]
                
                print(f"[DEBUG] MainAgent: Guide archived successfully: guide_id={completed_guide_id}")
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[ERROR] MainAgent: Failed to archive guide: {e}")
                # 即使归档失败，也更新状态为已完成
    
    return result


def _get_skills_metadata_prompt() -> str:
    """
    获取所有 Skills 的元数据（第一层：Metadata Level）+ 工具使用说明
    
    只加载元数据，模型通过 load_skill_instructions 工具按需加载完整指令
    """
    inquiry_skill = get_inquiry_skill()
    consult_skill = get_consult_answer_skill()
    emotion_skill = get_emotion_support_skill()
    
    return f"""
---

## 📚 可用 Skills（通过工具按需加载）

{inquiry_skill.get_metadata_prompt()}
{consult_skill.get_metadata_prompt()}
{emotion_skill.get_metadata_prompt()}

### 如何使用 Skills

当你判断需要使用某个 Skill 时，请调用 `load_skill_instructions` 工具获取完整指令：

- **需要提问收集信息** → 调用 `load_skill_instructions(skill_id="inquiry_skill")`
- **需要解答情感疑惑** → 调用 `load_skill_instructions(skill_id="consult_answer_skill")`  
- **需要情感陪伴支持** → 调用 `load_skill_instructions(skill_id="emotion_support_skill")`

调用工具后，你会收到该 Skill 的完整执行指令，然后根据指令生成回复。

---
"""


def _format_history(messages: list) -> str:
    """格式化对话历史"""
    if not messages:
        return "无历史对话"
    
    # 只保留最近 10 条消息
    recent = messages[-10:]
    formatted = []
    for msg in recent:
        role = "用户" if msg["role"] == "user" else "小话"
        formatted.append(f"{role}: {msg['content']}")
    
    return "\n".join(formatted)


def _parse_response(content: str, state: AgentState) -> dict[str, Any]:
    """解析 LLM 输出"""
    try:
        # 尝试解析 JSON
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            # 尝试找到 JSON 对象
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                json_str = content[start:end]
            else:
                json_str = content
        
        data = json.loads(json_str)
        
        # 映射 next_action
        next_action_map = {
            "ask_user": "ask_user",
            "call_status": "call_status",
            "call_plan": "call_plan",
            "call_guide": "call_guide",
            "end_turn": "end_turn",
        }
        
        next_action = data.get("next_action", "end_turn")
        if next_action not in next_action_map:
            next_action = "end_turn"
        
        # response 可以为 null（可选回复）
        response_raw = data.get("response", data.get("assistant_response"))
        response_content = response_raw if response_raw else ""
        
        # 解析 inquiry_card（如果有）
        inquiry_card = data.get("inquiry_card")
        
        # 检测行动完成标记
        mark_guide_completed = data.get("mark_guide_completed", False)
        completed_guide_id = data.get("completed_guide_id")
        
        return {
            "response_content": response_content,
            "next_action": next_action,
            "intent_type": data.get("intent_type", "action_trigger"),
            "need_questions": data.get("need_questions", False),
            "inquiry_card": inquiry_card,  # 渐进式加载：直接从输出获取
            "pending_questions": [],
            "mark_guide_completed": mark_guide_completed,
            "completed_guide_id": completed_guide_id,
        }
    
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        # 解析失败，返回默认值
        return {
            "response_content": content.strip() if content else "我理解你的情况了，让我想想怎么帮你。",
            "next_action": "end_turn",
            "intent_type": "action_trigger",
            "inquiry_card": None,
            "pending_questions": [],
            "user_profile": state.get("user_profile", {}),
        }


def _update_profile(current_profile: dict, new_info: dict) -> dict:
    """
    更新用户画像（旧版，向后兼容）
    
    @deprecated: 建议使用 _update_user_context 更新 3×3 矩阵
    """
    if not new_info:
        return current_profile
    
    updated = current_profile.copy()
    
    # 合并已知事实
    if "known_facts" in new_info:
        existing_facts = updated.get("known_facts", [])
        new_facts = new_info["known_facts"]
        updated["known_facts"] = list(set(existing_facts + new_facts))
        del new_info["known_facts"]
    
    # 更新其他字段
    updated.update(new_info)
    
    return updated


def _get_default_prompt(from_sub_agent: bool = False, is_resuming: bool = False) -> str:
    """
    获取默认 Prompt
    
    采用 Tool-based 渐进式加载模式：
    - 系统提示只包含 Skills 的元数据
    - 模型通过 load_skill_instructions 工具按需加载完整指令
    """
    base_prompt = """你是小话，一个专业的 AI 恋爱军师。你的任务是帮助用户解决与 Crush 相处过程中的情感推进问题。

## 当前用户消息
{user_message}

## 用户画像
{user_profile}

## 现状分析报告
{status_report}

## 行动规划
{action_plan}

## 行动指南
{action_guide}

## 对话历史
{conversation_history}

{skills_prompt}
"""
    
    if from_sub_agent:
        # 再决策模式：子 Agent 完成后回到主 Agent
        base_prompt += """
## 子 Agent 完成信号
- 完成状态: {completion_status}
- 结果摘要: {result_summary}

## 你的任务（再决策模式）
子 Agent 已完成任务并返回，分析结果已经更新到看板中（前端会自动展示）。
你需要：
1. 给用户一个简短的过渡或引导
2. **根据当前情况灵活决定下一步**（不要固定流程！）

## 决策原则（灵活判断，非固定流程）
- **用户之前是否表达过明确诉求**
- **当前看板状态**：哪些已有，哪些缺失
- **对话上下文**：用户的期望和情绪状态

**重要**：不要假设用户一定想要完整流程，每一步都要根据实际情况判断。

## 输出格式
```json
{{
  "response": "给用户的回复",
  "intent_type": "action_trigger",
  "next_action": "ask_user|call_status|call_plan|call_guide|end_turn",
  "inquiry_card": null,
  "extracted_info": {{}}
}}
```
"""
    elif is_resuming:
        # 恢复执行模式：用户回答了之前的提问
        base_prompt += """
## 恢复执行模式
你之前向用户提问，用户已经回答了。当前是第 {question_count} 轮提问。

## 你的任务
1. 分析用户的回答，提取有用信息
2. 判断信息是否足够继续
3. 决定下一步行动

## 决策逻辑
- 如果信息仍然不足，可以继续提问（ask_user + inquiry_card）
- 如果信息足够，决定是调用子 Agent 还是直接回复
- 如果是简单咨询或情感陪伴，根据上面的 Skills 指导原则直接回复

## 输出格式
```json
{{
  "response": "给用户的回复",
  "intent_type": "consult_only|emotion_vent|action_trigger|info_update",
  "next_action": "ask_user|call_status|call_plan|call_guide|end_turn",
  "inquiry_card": null,
  "extracted_info": {{}}
}}
```
"""
    else:
        # 正常模式：处理用户输入
        base_prompt += """
## 你的任务
1. **理解用户意图**：判断用户是纯咨询、情绪发泄、还是需要触发行动
2. **回应用户**：根据意图类型，使用上面对应的 Skill 指导原则生成回复
3. **决策下一步**：判断是否需要调用子 Agent 或向用户提问

## 意图分类与 Skill 使用
- `consult_only`: 纯咨询问题 → 按「解答情感疑惑 Skill」的原则回复
- `emotion_vent`: 情绪发泄/倾诉 → 按「情感陪伴 Skill」的原则回复
- `action_trigger`: 需要触发行动流程
- `info_update`: 用户提供了新信息

## 决策逻辑
- 如果是咨询/陪伴 → 直接用对应 Skill 原则生成回复，`next_action="end_turn"`
- 如果信息不足 → `next_action="ask_user"`，并填充 `inquiry_card`（按提问 Skill 格式）
- 如果需要更新看板 → 设置对应的 `next_action`

## 输出格式
```json
{{
  "response": "给用户的回复（根据意图类型使用对应 Skill 原则）",
  "intent_type": "consult_only|emotion_vent|action_trigger|info_update",
  "next_action": "ask_user|call_status|call_plan|call_guide|end_turn",
  "need_questions": false,
  "inquiry_card": null
}}
```

### 🔴 重要：inquiry_card 字段规则

**只有在需要提问时才填充 `inquiry_card`**：
- 当 `next_action="ask_user"` 或 `need_questions=true` 时，才需要填充 `inquiry_card`
- 其他情况下，`inquiry_card` 必须为 `null`

**当需要提问时，`inquiry_card` 格式如下**（参考上面的「提问 Skill」完整规范）：
```json
{{
  "inquiry_card": {{
    "questions": [
      {{
        "id": "q1",
        "type": "free_input_question|single_choice|multiple_choice|private_chat_screenshot|group_chat_screenshot|moments_screenshot|other_social_media_screenshot",
        "question": "问题内容（简练、直接）",
        "info_type": 1,
        "options": ["选项1", "选项2"],
        "source_type": 1,
        "is_required": true,
        "purpose": "问这个问题的目的"
      }}
    ],
    "intro": "引导语（简短、有角色感）",
    "reasoning": "为什么问这些问题（内部分析）"
  }}
}}
```

**注意**：
- `response` 是给用户的回复，如果要提问，这里可以是简短的过渡语
"""
    
    return base_prompt

