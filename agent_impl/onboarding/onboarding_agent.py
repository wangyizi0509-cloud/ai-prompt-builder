"""
Onboarding Agent

职责：
- 首次使用时补齐用户/Crush 基础画像与核心痛点
- 每轮单问，最多 onboarding_max_turns 轮
- 信息充足时输出 onboarding_handoff，给主 Agent 提示下一步
"""

import json
import time
from pathlib import Path
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from config import get_llm
from onboarding.state import OnboardingHandoff
from utils.prompt_loader import parse_frontmatter


PROMPT_PATH = Path(__file__).parent / "prompts" / "onboarding_agent.md"
LOGIC_PATH = Path(__file__).parent / "onboarding_logic.md"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = PROJECT_ROOT / ".cursor" / "debug.log"
GUIDE_DONE_TOKEN = "[SYS:CRUSHE_GUIDE_DONE]"


#region agent log
def _append_debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict):
    """Append a single NDJSON debug log line to the shared log path."""
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
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Logging failure should never break execution
        pass
#endregion


def _load_reference_questions() -> str:
    try:
        return LOGIC_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _load_prompt(reference_questions: str) -> str:
    """
    加载 Prompt，并用占位符注入参考问题。
    如果未找到占位符，则降级为在结尾追加参考问题。
    """
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    _, content = parse_frontmatter(raw)
    content = content.strip()

    placeholder = "{REFERENCE_QUESTIONS}"
    if placeholder in content:
        return content.replace(placeholder, reference_questions or "（暂无参考问题）")

    # fallback：无占位符则直接拼接
    suffix = "\n\n## 参考问题（可自由改写）\n" + (reference_questions or "（暂无参考问题）")
    return content + suffix


def _safe_json_loads(text: str) -> Dict[str, Any]:
    """宽松解析 LLM 输出为 JSON。失败则返回空字典。"""
    if not text:
        return {}
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]
        return json.loads(text)
    except Exception:
        return {}


def _pick_next_question(collected: dict) -> str:
    """基于缺口挑选下一问（简单规则，LLM 失败时的兜底）。"""
    user_profile = collected.get("user_profile", {})
    crush_profile = collected.get("crush_profile", {})
    pain_points = collected.get("pain_points", [])

    if not user_profile.get("gender"):
        return "你的性别是？"
    if not user_profile.get("birth_year"):
        return "你的出生年份是？"
    if not user_profile.get("experience_level"):
        return "你觉得自己的情感经验阶段是？（萌新/进阶/资深/疗愈期）"
    if not crush_profile.get("name"):
        return "方便告诉我对方的昵称或备注吗？"
    if not crush_profile.get("gender"):
        return "Ta 的性别是？"
    if not crush_profile.get("age"):
        return "Ta 的年龄或预估年龄是？"
    if not crush_profile.get("channel"):
        return "你们是如何认识的？（社交软件/偶遇/朋友介绍/同事同学等）"
    if not pain_points:
        return "现在最让你头疼的点是什么？比如找不到话题、约不出来、忽冷忽热等。"
    return ""


def _merge_collected(collected: dict, new_raw: str) -> dict:
    """轻量合并收集信息：目前仅追加用户自由文本，留待后续模型抽取。"""
    merged = dict(collected or {})
    history = list(merged.get("raw_inputs", []))
    if new_raw:
        history.append(new_raw.strip())
    merged["raw_inputs"] = history
    merged.setdefault("user_profile", {})
    merged.setdefault("crush_profile", {})
    merged.setdefault("pain_points", [])
    return merged


from graph.state import convert_message_to_dict


def _convert_messages_to_dict(messages: list) -> list:
    """
    将 LangChain Message 或 dict 统一转为 dict，避免测试中对 .get 的访问报错。
    """
    result = []
    for m in messages or []:
        try:
            msg = convert_message_to_dict(m)
            role = msg.get("role")
            if role == "human":
                msg["role"] = "user"
            elif role == "ai":
                msg["role"] = "assistant"
            result.append(msg)
        except Exception:
            # 最小容错
            if isinstance(m, dict):
                role = m.get("role")
                if role == "human":
                    m["role"] = "user"
                elif role == "ai":
                    m["role"] = "assistant"
                result.append(m)
            elif hasattr(m, "content"):
                role = getattr(m, "type", getattr(m, "role", "assistant"))
                if role == "human":
                    role = "user"
                elif role == "ai":
                    role = "assistant"
                result.append({"role": role, "content": m.content})
    return result


def _replace_last_user_message(messages: list, from_text: str, to_text: str) -> list:
    """Replace the last user message content if it matches the token."""
    if not messages:
        return messages
    last = messages[-1]
    if (
        isinstance(last, dict)
        and last.get("role") == "user"
        and (last.get("content") or "").strip() == from_text
    ):
        updated = dict(last)
        updated["content"] = to_text
        return messages[:-1] + [updated]
    return messages


def _build_conversation_history(messages: list) -> str:
    """
    构建对话历史（与主 Agent 格式一致）
    
    格式: **用户**: xxx / **小话**: xxx
    """
    if not messages:
        return "无历史对话"
    
    formatted = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        if not content or not content.strip():
            continue
        
        # 处理 assistant 消息：如果是 JSON，提取 response 字段
        if role == "assistant":
            content = _extract_response_from_json(content)
            if not content:
                continue
            formatted.append(f"**小话**: {content}")
        elif role == "user":
            formatted.append(f"**用户**: {content}")
    
    if not formatted:
        return "无历史对话"
    
    return "\n\n".join(formatted)


def _extract_response_from_json(content: str) -> str:
    """
    从 JSON 格式的 assistant 消息中提取 response 字段
    """
    if not content:
        return ""
    
    content = content.strip()
    
    # 尝试解析 JSON
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        elif content.startswith("{"):
            start = content.find("{")
            end = content.rfind("}") + 1
            json_str = content[start:end]
        else:
            return content
        
        data = json.loads(json_str)
        
        parts = []
        
        # 提取 response
        response = data.get("response", "")
        if response:
            parts.append(response)
        
        # 如果有 inquiry_card，提取问题文本
        inquiry_card = data.get("inquiry_card")
        if inquiry_card and inquiry_card.get("questions"):
            questions = inquiry_card.get("questions", [])
            if questions:
                question_texts = []
                for q in questions:
                    if isinstance(q, dict):
                        q_text = q.get("question", "")
                        if q_text:
                            question_texts.append(f"- {q_text}")
                    elif isinstance(q, str):
                        question_texts.append(f"- {q}")
                
                if question_texts:
                    parts.append("【提问】\n" + "\n".join(question_texts))
        
        if parts:
            return "\n".join(parts)
        
        return content
        
    except (json.JSONDecodeError, KeyError, IndexError):
        return content


def _strip_preliminary_assessment_from_json(content: str) -> str:
    """
    清理 onboarding 的 preliminary_assessment，避免进入后续模型输入。
    仅对 JSON 格式内容做字段移除，其他内容原样返回。
    """
    if not content:
        return ""
    content = content.strip()
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        elif content.startswith("{"):
            start = content.find("{")
            end = content.rfind("}") + 1
            json_str = content[start:end]
        else:
            return content
        data = json.loads(json_str)
        if isinstance(data, dict) and "preliminary_assessment" in data:
            data.pop("preliminary_assessment", None)
            return json.dumps(data, ensure_ascii=False)
        return content
    except (json.JSONDecodeError, KeyError, IndexError):
        return content


def onboarding_agent_node(state: dict, config: RunnableConfig | None = None) -> dict:
    """
    Onboarding 节点：
    - 调用 LLM 生成下一问或直接输出 handoff
    - 对话历史格式与主 Agent 保持一致
    """
    reference = _load_reference_questions()
    llm = get_llm(temperature=0.3)
    prompt_body = _load_prompt(reference)

    user_message = state.get("user_message", "")
    collected_info = state.get("collected_info", {}) or {}
    turn_count = state.get("onboarding_turn_count", 0)
    max_turns = state.get("onboarding_max_turns", 3)
    last_question = state.get("last_onboarding_question")

    # 统一消息为 dict，确保不丢失已有用户消息
    existing_messages = _convert_messages_to_dict(state.get("messages", []))

    # 如果已完成 Onboarding，但需要先完成 Crushe 指南，则拦截等待
    if state.get("pending_crushe_guide"):
        if (user_message or "").strip() == GUIDE_DONE_TOKEN:
            handoff = state.get("onboarding_handoff") or {
                "collected_context": collected_info,
                "recommendation": "信息已收集完毕，进入主流程进一步分析。",
                "suggested_action": "建议进行现状分析",
                "reason": "Onboarding 收集完成。",
            }
            # 清理 token，避免进入主流程
            cleaned_messages = _replace_last_user_message(existing_messages, GUIDE_DONE_TOKEN, "继续")
            onboarding_ack = (
                "[SYS:ONBOARDING_DONE] 用户初次注册流程已完成，可以正式进入业务流程。"
                f"\n参考建议：{handoff.get('suggested_action')}（仅供参考，最终由主流程决定）"
            )
            return {
                "onboarding_completed": True,
                "pending_crushe_guide": False,
                "onboarding_handoff": handoff,
                "collected_info": collected_info,
                "user_message": "继续",
                "messages": cleaned_messages + [
                    {
                        "role": "assistant",
                        "name": "onboarding_agent",
                        "content": onboarding_ack,
                    }
                ],
                "next_action": "end_turn",
            }
        return {
            "onboarding_completed": False,
            "pending_crushe_guide": True,
            "collected_info": collected_info,
            "next_action": "end_turn",
            "route_to": "end",
        }

    # 构建对话历史（与主 Agent 格式一致）
    conversation_history = _build_conversation_history(existing_messages)

    # 组装给 LLM 的上下文（使用占位符替换）
    prompt = prompt_body.format(
        conversation_history=conversation_history,
        turn_count=turn_count,
        max_turns=max_turns,
    )

    try:
        llm_resp = llm.invoke(prompt)
        parsed = _safe_json_loads(getattr(llm_resp, "content", ""))
    except Exception as e:
        print(f"[ERROR] OnboardingAgent LLM invoke failed: {str(e)}")
        # 兜底：返回一个默认问题
        parsed = {}
        llm_resp = type('obj', (object,), {'content': ''})


    needs_more = bool(parsed.get("needs_more", False))
    preliminary_assessment = parsed.get("preliminary_assessment")
    if not isinstance(preliminary_assessment, dict):
        preliminary_assessment = None
    # 优先使用 inquiry_card 中的问题，兼容旧格式 question
    inquiry_card = parsed.get("inquiry_card") or {}
    questions = inquiry_card.get("questions", [])
    question_text = questions[0].get("question") if questions else parsed.get("question")

    #region agent log
    _append_debug_log(
        run_id="pre-fix",
        hypothesis_id="H1",
        location="onboarding_agent.py:onboarding_agent_node:parsed",
        message="Parsed onboarding LLM output",
        data={
            "needs_more": needs_more,
            "has_inquiry_card": bool(inquiry_card),
            "questions_count": len(questions),
            "question_text": question_text,
            "turn_count": turn_count,
            "max_turns": max_turns,
        },
    )
    #endregion

    # 如果 LLM 没生成有效问题，尝试兜底
    if not question_text:
        question_text = _pick_next_question(collected_info)

    # 构造 response/intro
    response_text = parsed.get("response") or inquiry_card.get("intro") or (question_text or "为确保理解你的情况，我想确认一下关键背景。")
    
    # 构造完整的 inquiry_card（如果缺失）
    if needs_more and not questions and question_text:
        inquiry_card = {
            "questions": [{
                "id": f"onboard_q_{turn_count}",
                "question": question_text,
                "type": "free_input_question",
                "info_type": 1,
                "is_required": True,
                "purpose": "补充关键背景"
            }],
            "intro": response_text,
            "reasoning": "Based on missing profile info"
        }

    recommendation = parsed.get("recommendation", "")
    # suggested_action：自然语言建议，不再做枚举约束
    suggested_action = parsed.get("suggested_action", "") or "建议进行现状分析"
    reason = parsed.get("reason", "")
    updated_info = parsed.get("collected_info") or collected_info

    # 如果模型未给出问题且仍需追问，直接结束
    if needs_more and not question_text:
        needs_more = False

    # 追加当前输入到收集信息
    updated_info = _merge_collected(updated_info, user_message)

    if needs_more and turn_count < max_turns:
        # 仅注入“回复 + 问题”到消息历史，避免混入结构化或内部字段
        question_suffix = f"\n\n问题：{question_text}" if question_text else ""
        onboarding_message = f"{response_text}{question_suffix}".strip()
        # 不使用 interrupt，直接返回提问卡和回复，结束本轮
        result = {
            "onboarding_completed": False,
            "onboarding_turn_count": turn_count + 1,
            "last_onboarding_question": question_text,
            "collected_info": updated_info,
            "inquiry_card": inquiry_card,  # 顶层暴露给前端
            "pending_responses": [
                {
                    "from": "onboarding",
                    "content": response_text,
                    "phase": "immediate",
                    "inquiry_card": inquiry_card,
                }
            ],
            "messages": existing_messages + [
                {
                    "role": "assistant",
                    "name": "onboarding_agent",
                    "content": onboarding_message,
                },
            ],
            "route_to": "end",  # 结束本轮，等待用户回答
            "next_action": "ask_user",
        }
        #region agent log
        _append_debug_log(
            run_id="pre-fix",
            hypothesis_id="H1",
            location="onboarding_agent.py:onboarding_agent_node:return_needs_more",
            message="Returning onboarding inquiry card",
            data={
                "questions_count": len(inquiry_card.get("questions", [])) if inquiry_card else 0,
                "pending_has_card": bool(result["pending_responses"][0].get("inquiry_card")),
                "result_inquiry_card_present": bool(result.get("inquiry_card")),
                "pending_from": result["pending_responses"][0].get("from"),
                "turn_count": result["onboarding_turn_count"],
            },
        )
        #endregion
        return result

    # 信息足够或达到上限，生成 handoff
    handoff: OnboardingHandoff = {
        "collected_context": updated_info,
        "recommendation": recommendation or "信息已收集完毕，进入主流程进一步分析。",
        "suggested_action": suggested_action or "建议进行现状分析",
        "reason": reason or "Onboarding 收集完成。",
    }

    # 如果模型没有按协议产出 preliminary_assessment，则在完成时做一次“补全生成”（仅补字段，不改变 handoff）
    # 目的：保证前端能展示《局势初判卡》，同时不影响主流程的 recommendation/suggested_action。
    if not preliminary_assessment:
        try:
            _append_debug_log(
                run_id="pre-fix",
                hypothesis_id="H2",
                location="onboarding_agent.py:onboarding_agent_node:prelim_fallback:start",
                message="Preliminary assessment missing; starting fallback generation",
                data={"turn_count": turn_count, "has_rec": bool(handoff.get("recommendation"))},
            )
            pa_prompt = (
                "你是AI恋爱军师小话。请基于用户提供的信息，生成《局势初判卡》JSON。\n"
                "要求：只输出 JSON，不要输出其它文字；字段固定为 verdict/evidence/projection/call_to_action。\n\n"
                f"【对话历史】\n{conversation_history}\n\n"
                f"【用户本轮补充】\n{user_message}\n\n"
                "输出示例：\n"
                "{\n"
                '  \"preliminary_assessment\": {\n'
                '    \"verdict\": \"🟡迷雾\",\n'
                '    \"evidence\": \"...\",\n'
                '    \"projection\": \"...\",\n'
                '    \"call_to_action\": \"...\"\n'
                "  }\n"
                "}\n"
            )
            pa_resp = llm.invoke(pa_prompt)
            pa_parsed = _safe_json_loads(getattr(pa_resp, "content", ""))
            candidate = None
            if isinstance(pa_parsed, dict):
                if isinstance(pa_parsed.get("preliminary_assessment"), dict):
                    candidate = pa_parsed.get("preliminary_assessment")
                else:
                    # 兼容：模型可能直接输出四字段对象
                    candidate = pa_parsed
            if isinstance(candidate, dict):
                preliminary_assessment = {
                    "verdict": candidate.get("verdict", ""),
                    "evidence": candidate.get("evidence", ""),
                    "projection": candidate.get("projection", ""),
                    "call_to_action": candidate.get("call_to_action", ""),
                }
            _append_debug_log(
                run_id="pre-fix",
                hypothesis_id="H2",
                location="onboarding_agent.py:onboarding_agent_node:prelim_fallback:done",
                message="Preliminary assessment fallback finished",
                data={
                    "success": bool(preliminary_assessment),
                    "verdict": (preliminary_assessment or {}).get("verdict"),
                },
            )
        except Exception:
            _append_debug_log(
                run_id="pre-fix",
                hypothesis_id="H2",
                location="onboarding_agent.py:onboarding_agent_node:prelim_fallback:error",
                message="Preliminary assessment fallback failed",
                data={},
            )
            preliminary_assessment = None

    # 最终兜底：若补全仍失败，则仅根据 recommendation 做“判词”提取（不编造证据/走势/CTA）
    if not preliminary_assessment:
        rec_text = handoff.get("recommendation") or ""
        verdict = ""
        if "高危" in rec_text or "危险" in rec_text:
            verdict = "🔴高危"
        elif "迷雾" in rec_text or "不明" in rec_text:
            verdict = "🟡迷雾"
        elif "机会" in rec_text or "可行" in rec_text:
            verdict = "🟢机会"
        if verdict:
            preliminary_assessment = {
                "verdict": verdict,
                "evidence": "",
                "projection": "",
                "call_to_action": "",
            }

    onboarding_ack = (
        "[SYS:ONBOARDING_DONE] 用户初次注册流程已完成，可以正式进入业务流程。"
        f"\n参考建议：{handoff.get('suggested_action')}（仅供参考，最终由主流程决定）"
    )
    result = {
        "onboarding_completed": False,  # 等待用户看完 Crushe 指南再进入主流程
        "pending_crushe_guide": True,
        "onboarding_handoff": handoff,
        "collected_info": updated_info,
        "pending_responses": [
            {
                "from": "onboarding",
                # 用户可见回复：优先使用模型的 response 字段，其次降级为 recommendation
                "content": (parsed.get("response") or handoff["recommendation"]),
                "phase": "immediate",
                # 若模型提供了局势初判卡，则一并透传给前端（用于聊天流展示）
                **({"preliminary_assessment": preliminary_assessment} if preliminary_assessment else {}),
            }
        ],
        # 顶层透传：便于前端在 state 更新时直接识别并渲染
        **({"preliminary_assessment": preliminary_assessment} if preliminary_assessment else {}),
    }
    #region agent log
    _append_debug_log(
        run_id="pre-fix",
        hypothesis_id="H2",
        location="onboarding_agent.py:onboarding_agent_node:return_completed",
        message="Onboarding completed path",
        data={
            "handoff_suggested_action": handoff.get("suggested_action"),
            "has_pending": bool(result.get("pending_responses")),
            "collected_info_keys": list(updated_info.keys()),
        },
    )
    #endregion
    return result
