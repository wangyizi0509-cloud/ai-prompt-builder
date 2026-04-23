"""
Onboarding Agent

职责：
- 首次使用时补齐用户/Crush 基础画像与核心痛点
- 每轮单问，最多 onboarding_max_turns 轮
- 信息充足时输出 onboarding_handoff，给主 Agent 提示下一步
"""

import json
import hashlib
import time
from pathlib import Path
from typing import Any, Dict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt

from agents.tooling.patch import merge_patches, merge_state_patch
from config import get_llm
from graph.message_builder import build_messages_for_model
from graph.runtime_config import sanitize_runtime_config
from graph.tools.ask_human import ask_human
from onboarding.tools import build_onboarding_submit_patch, create_submit_onboarding_tool
from onboarding.state import OnboardingHandoff


LOGIC_PATH = Path(__file__).parent / "onboarding_logic.md"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = PROJECT_ROOT / ".cursor" / "debug.log"
GUIDE_DONE_TOKEN = "[SYS:CRUSHE_GUIDE_DONE]"
DEFAULT_PRE_SUBMIT_CONTENT = "截图看完了，情况比你想的复杂，我先给你生成一张局势初判卡。"
DEFAULT_POST_SUBMIT_CONTENT = "我的初步判断先到这里。真正的攻坚战才刚开始，我会基于你们最近互动做一次深度复盘。"
GUIDE_GATE_REMINDER_CONTENT = (
    "我已经整理好初步判断。请先点击下方《Crushe使用指南》并完成阅读，"
    "完成后我会继续为你输出完整策略。"
)


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


def _build_onboarding_runtime_context_message(
    *,
    turn_count: int,
    max_turns: int,
    reference_questions: str,
) -> str:
    """构建 onboarding 运行时动态上下文（独立 HumanMessage，不进入 system prompt）。"""
    ref = reference_questions.strip() if reference_questions else "（暂无参考问题）"
    return (
        "<onboarding_runtime>\n"
        f"  <turn_count>{int(turn_count)}</turn_count>\n"
        f"  <max_turns>{int(max_turns)}</max_turns>\n"
        "  <reference_questions>\n"
        f"{ref}\n"
        "  </reference_questions>\n"
        "</onboarding_runtime>\n\n"
        "请结合以上运行时上下文执行本轮 Onboarding。"
    )


def _build_onboarding_initial_messages(
    *,
    state: dict[str, Any],
    user_message: str,
    turn_count: int,
    max_turns: int,
    reference_questions: str,
) -> list[BaseMessage]:
    """
    构建 onboarding 模型输入消息栈：
    System + Dossier + Ack + History + RuntimeContext + CurrentInput
    """
    initial_messages = build_messages_for_model(
        state=state,
        agent_name="onboarding_agent",
        current_input=user_message,
    )
    runtime_message = HumanMessage(
        content=_build_onboarding_runtime_context_message(
            turn_count=turn_count,
            max_turns=max_turns,
            reference_questions=reference_questions,
        )
    )
    if user_message and initial_messages:
        initial_messages = list(initial_messages[:-1]) + [runtime_message, initial_messages[-1]]
    else:
        initial_messages = list(initial_messages) + [runtime_message]
    return initial_messages


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


def _normalize_interrupt_answers(raw_answer: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    统一 interrupt 恢复值格式：
    - 若前端传入 {"answers": {...}}，提取内部 answers
    - 若直接传入 dict，视为 answers
    - 其他类型包装为 {"answer": value}
    """
    if isinstance(raw_answer, dict):
        answers_obj = raw_answer.get("answers")
        if isinstance(answers_obj, dict):
            return answers_obj, {"answers": answers_obj}
        return raw_answer, {"answers": raw_answer}
    return {"answer": raw_answer}, {"answers": {"answer": raw_answer}}


def _answer_fingerprint(answers: dict[str, Any]) -> str:
    if not isinstance(answers, dict) or not answers:
        return ""
    try:
        canonical = json.dumps(answers, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        canonical = str(answers)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_onboarding_answer_progress_patch(state: dict[str, Any], raw_answer: Any) -> dict[str, Any]:
    if not isinstance(raw_answer, dict):
        return {}

    normalized_answers, wrapped_answers = _normalize_interrupt_answers(raw_answer)
    if not normalized_answers:
        return {}

    fingerprint = _answer_fingerprint(normalized_answers)
    if not fingerprint:
        return {}

    last_fingerprint = str(state.get("onboarding_last_answer_fingerprint") or "")
    patch: dict[str, Any] = {
        "onboarding_last_answer_fingerprint": fingerprint,
    }
    if fingerprint != last_fingerprint:
        patch["onboarding_turn_count"] = int(state.get("onboarding_turn_count", 0) or 0) + 1
    patch["inquiry_answers"] = wrapped_answers
    return patch


def _format_resume_answers_for_history(inquiry_card: dict, answers: dict[str, Any]) -> str:
    """
    将 resume answers 转成可读文本，写入 user_message/raw_inputs，
    便于 onboarding 的后续抽取逻辑直接复用。
    """
    questions = inquiry_card.get("questions") if isinstance(inquiry_card, dict) else None
    lines: list[str] = []

    if isinstance(questions, list) and questions:
        for q in questions:
            if not isinstance(q, dict):
                continue
            qid = str(q.get("id") or "").strip()
            if not qid or qid not in answers:
                continue
            value = answers.get(qid)
            if isinstance(value, list):
                answer_text = "、".join(str(v) for v in value)
            elif isinstance(value, dict):
                answer_text = json.dumps(value, ensure_ascii=False)
            else:
                answer_text = str(value)
            question_text = str(q.get("question") or qid)
            lines.append(f"{question_text}：{answer_text}")

    if not lines and isinstance(answers, dict) and answers:
        for k, v in answers.items():
            if isinstance(v, list):
                value_text = "、".join(str(x) for x in v)
            elif isinstance(v, dict):
                value_text = json.dumps(v, ensure_ascii=False)
            else:
                value_text = str(v)
            lines.append(f"{k}：{value_text}")

    if not lines:
        return "用户已提交补充信息"
    return "\n\n".join(lines)


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


def _tool_output_to_content(result: Any) -> str:
    if isinstance(result, dict) and "output" in result:
        return str(result.get("output") or "")
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False)
    except Exception:
        return str(result)


def _extract_state_patch(result: Any) -> dict:
    if isinstance(result, dict) and isinstance(result.get("state_patch"), dict):
        return dict(result.get("state_patch") or {})
    return {}


def _wrap_tools_for_patch_collection(tools: list[BaseTool], patches: list[dict]) -> list[BaseTool]:
    wrapped: list[BaseTool] = []
    for tool in tools:
        if not isinstance(tool, BaseTool):
            wrapped.append(tool)
            continue

        def _make_wrapped(inner: BaseTool):
            def _wrapped(**kwargs):
                result = inner.invoke(kwargs)
                patch = _extract_state_patch(result)
                if patch:
                    patches.append(patch)
                return _tool_output_to_content(result)

            return _wrapped

        wrapped.append(
            StructuredTool.from_function(
                func=_make_wrapped(tool),
                name=getattr(tool, "name", None) or tool.__class__.__name__,
                description=getattr(tool, "description", None) or "",
                return_direct=bool(getattr(tool, "return_direct", False)),
                args_schema=getattr(tool, "args_schema", None),
            )
        )
    return wrapped


def _run_onboarding_supervisor(
    *,
    llm: Any,
    tools: list[BaseTool],
    initial_messages: list[BaseMessage],
    config: RunnableConfig | None = None,
    max_rounds: int = 6,
) -> dict[str, Any]:
    patches: list[dict] = []
    wrapped_tools = _wrap_tools_for_patch_collection(list(tools or []), patches)
    base_cfg = sanitize_runtime_config(config)
    cfg = dict(base_cfg or {})
    cfg["recursion_limit"] = max(25, int(max_rounds or 6) * 4 + 10)

    # Tool-loop is transient; avoid passing non-serializable checkpointer objects from outer runtime.
    cfg.pop("checkpointer", None)
    configurable = cfg.get("configurable")
    if isinstance(configurable, dict):
        configurable_copy = dict(configurable)
        configurable_copy.pop("checkpointer", None)
        configurable_copy.pop("__pregel_checkpointer", None)
        cfg["configurable"] = configurable_copy

    agent_graph = create_agent(
        model=llm,
        tools=wrapped_tools,
        system_prompt=None,
        name="onboarding_tool_loop_agent",
        checkpointer=None,
    )
    try:
        result = agent_graph.invoke({"messages": list(initial_messages)}, config=cfg)
    except GraphInterrupt as e:
        interrupts = list(getattr(e, "interrupts", ()) or [])
        if not interrupts and getattr(e, "args", None):
            first = e.args[0]
            if isinstance(first, (list, tuple)):
                interrupts = list(first)
        return {
            "final": AIMessage(content=""),
            "new_messages": [],
            "patches": patches,
            "__interrupt__": interrupts,
        }

    messages_out = list(result.get("messages") or []) if isinstance(result, dict) else []
    final = messages_out[-1] if messages_out else AIMessage(content="")
    new_messages = messages_out[len(initial_messages) :] if len(messages_out) >= len(initial_messages) else messages_out
    out = {
        "final": final,
        "new_messages": new_messages,
        "patches": patches,
    }
    if isinstance(result, dict) and "__interrupt__" in result:
        out["__interrupt__"] = result["__interrupt__"]
    return out


def _interrupt_value_from_supervisor(value: Any) -> dict[str, Any]:
    interrupts = value if isinstance(value, list) else []
    if not interrupts:
        return {}
    first = interrupts[0]
    if isinstance(first, dict):
        payload = first.get("value")
    else:
        payload = getattr(first, "value", None)
    return payload if isinstance(payload, dict) else {}


def _parse_tool_call_args(raw_args: Any) -> dict[str, Any]:
    if isinstance(raw_args, dict):
        return dict(raw_args)
    if isinstance(raw_args, str):
        text = raw_args.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _extract_submit_onboarding_sequence(new_messages: list[Any]) -> dict[str, Any]:
    normalized = _convert_messages_to_dict(new_messages or [])
    submit_idx = -1
    pre_submit_content = ""
    post_submit_content = ""

    for idx, msg in enumerate(normalized):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        tool_calls = msg.get("tool_calls")
        if role in ("assistant", "ai") and isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict) and str(tc.get("name") or "").strip() == "submit_onboarding":
                    submit_idx = idx
                    pre_submit_content = str(msg.get("content") or "").strip()
                    break
        if submit_idx >= 0:
            break

    if submit_idx >= 0:
        for msg in normalized[submit_idx + 1 :]:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role not in ("assistant", "ai"):
                continue
            if msg.get("tool_calls"):
                continue
            content = str(msg.get("content") or "").strip()
            if content:
                post_submit_content = content
                break

    return {
        "submit_called": submit_idx >= 0,
        "pre_submit_content": pre_submit_content,
        "post_submit_content": post_submit_content,
    }


def _extract_submit_onboarding_args(new_messages: list[Any]) -> dict[str, Any]:
    normalized = _convert_messages_to_dict(new_messages or [])
    for msg in normalized:
        if not isinstance(msg, dict):
            continue
        tool_calls = msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            if str(tc.get("name") or "").strip() != "submit_onboarding":
                continue
            args = _parse_tool_call_args(tc.get("args"))
            if args:
                return args
            function_obj = tc.get("function")
            if isinstance(function_obj, dict):
                parsed = _parse_tool_call_args(function_obj.get("arguments"))
                if parsed:
                    return parsed
            parsed_alt = _parse_tool_call_args(tc.get("arguments"))
            if parsed_alt:
                return parsed_alt
    return {}


def _build_submit_pending_responses(
    pre_submit_content: str,
    post_submit_content: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for phase, content in (
        ("pre_submit", pre_submit_content),
        ("post_submit", post_submit_content),
    ):
        text = str(content or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(
            {
                "from": "onboarding",
                "content": text,
                "phase": phase,
            }
        )
    return items


def _build_guide_gate_pending_responses() -> list[dict[str, Any]]:
    return [
        {
            "from": "onboarding",
            "content": GUIDE_GATE_REMINDER_CONTENT,
            "phase": "guide_gate",
            "showGuideButton": True,
            "messageKey": "guide_gate",
        }
    ]


def _has_submit_patch(patch: dict[str, Any] | None) -> bool:
    if not isinstance(patch, dict):
        return False
    if patch.get("pending_crushe_guide") is True:
        return True
    return isinstance(patch.get("onboarding_handoff"), dict)


def _build_preliminary_assessment_fallback(
    *,
    llm: Any,
    preliminary_assessment: dict[str, Any] | None,
    handoff: dict[str, Any],
    conversation_history: str,
    user_message: str,
    turn_count: int,
    allow_llm_fallback: bool = True,
) -> dict[str, Any] | None:
    if isinstance(preliminary_assessment, dict):
        return preliminary_assessment

    if allow_llm_fallback:
        try:
            _append_debug_log(
                run_id="tool-refactor",
                hypothesis_id="OB-H2",
                location="onboarding_agent.py:_build_preliminary_assessment_fallback:start",
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
                '  "preliminary_assessment": {\n'
                '    "verdict": "🟡迷雾",\n'
                '    "evidence": "...",\n'
                '    "projection": "...",\n'
                '    "call_to_action": "..."\n'
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
                    candidate = pa_parsed
            if isinstance(candidate, dict):
                preliminary_assessment = {
                    "verdict": candidate.get("verdict", ""),
                    "evidence": candidate.get("evidence", ""),
                    "projection": candidate.get("projection", ""),
                    "call_to_action": candidate.get("call_to_action", ""),
                }
            _append_debug_log(
                run_id="tool-refactor",
                hypothesis_id="OB-H2",
                location="onboarding_agent.py:_build_preliminary_assessment_fallback:done",
                message="Preliminary assessment fallback finished",
                data={
                    "success": bool(preliminary_assessment),
                    "verdict": (preliminary_assessment or {}).get("verdict"),
                },
            )
        except Exception:
            _append_debug_log(
                run_id="tool-refactor",
                hypothesis_id="OB-H2",
                location="onboarding_agent.py:_build_preliminary_assessment_fallback:error",
                message="Preliminary assessment fallback failed",
                data={},
            )
            preliminary_assessment = None

    if isinstance(preliminary_assessment, dict):
        return preliminary_assessment

    rec_text = handoff.get("recommendation") or ""
    verdict = ""
    if "高危" in rec_text or "危险" in rec_text:
        verdict = "🔴高危"
    elif "迷雾" in rec_text or "不明" in rec_text:
        verdict = "🟡迷雾"
    elif "机会" in rec_text or "可行" in rec_text:
        verdict = "🟢机会"
    if verdict:
        return {
            "verdict": verdict,
            "evidence": "",
            "projection": "",
            "call_to_action": "",
        }
    return None


def _attach_preliminary_assessment_to_result(result: dict, preliminary_assessment: dict[str, Any] | None) -> dict:
    if not isinstance(preliminary_assessment, dict):
        return result
    out = dict(result)
    out["preliminary_assessment"] = preliminary_assessment
    pending = list(out.get("pending_responses") or [])
    if pending and isinstance(pending[0], dict):
        first = dict(pending[0])
        first["preliminary_assessment"] = preliminary_assessment
        pending[0] = first
        out["pending_responses"] = pending
    return out


# 使用统一的 resume 检测函数
from agents.tooling.interrupts import is_resuming


def onboarding_agent_node(state: dict, config: RunnableConfig | None = None) -> dict:
    """
    Onboarding 节点（Tool-Call 主路径 + Legacy JSON 兼容兜底）：
    - 主路径：ask_human / submit_onboarding
    - 兜底：解析旧 JSON 输出，但仍通过工具落库
    """
    import logging as _logging
    _ob_logger = _logging.getLogger("onboarding.agent_node")

    reference_questions = _load_reference_questions()

    working_state: dict[str, Any] = dict(state or {})
    user_message = str(working_state.get("user_message") or "")
    collected_info = working_state.get("collected_info", {}) or {}
    turn_count = int(working_state.get("onboarding_turn_count", 0) or 0)
    max_turns = int(working_state.get("onboarding_max_turns", 3) or 3)
    existing_messages = _convert_messages_to_dict(working_state.get("messages", []))
    pre_supervisor_patch: dict[str, Any] = {}

    _is_resume = is_resuming(config)
    cfg_keys: list[str] | None = None
    cfg_thread_id: str | None = None
    cfg_resuming_flag: Any = None
    cfg_configurable_keys: list[str] | None = None
    if isinstance(config, dict):
        cfg_keys = list(config.keys())
        configurable = config.get("configurable")
        if isinstance(configurable, dict):
            cfg_thread_id = str(configurable.get("thread_id") or "") or None
            cfg_resuming_flag = configurable.get("__pregel_resuming")
            cfg_configurable_keys = list(configurable.keys())
    _ob_logger.info(
        "[onboarding] config: has_config=%s, cfg_keys=%s, configurable_keys=%s, thread_id=%s, __pregel_resuming=%s",
        bool(config),
        cfg_keys,
        cfg_configurable_keys,
        cfg_thread_id,
        cfg_resuming_flag,
    )
    _ob_logger.info(
        "[onboarding] 入口: is_resuming=%s, turn_count=%d, max_turns=%d, "
        "onboarding_completed=%s, pending_crushe_guide=%s, "
        "has_inquiry_card=%s, has_inquiry_answers=%s, has_state_interrupt=%s, state_interrupt_len=%s, user_message_len=%d",
        _is_resume, turn_count, max_turns,
        working_state.get("onboarding_completed"),
        working_state.get("pending_crushe_guide"),
        bool(working_state.get("inquiry_card")),
        bool(working_state.get("inquiry_answers")),
        bool(working_state.get("__interrupt__")),
        len(working_state.get("__interrupt__") or []) if isinstance(working_state.get("__interrupt__"), list) else None,
        len(user_message),
    )

    if _is_resume:
        _ob_logger.info(
            "[onboarding] resuming detected: inquiry_answers_present=%s, has_interrupt_payload=%s",
            bool(working_state.get("inquiry_answers")),
            bool(working_state.get("_onboarding_interrupt_payload")),
        )

    # 如果已完成 Onboarding，但需要先完成 Crushe 指南，则拦截等待
    # 注意：此检查在 resume 处理之后，resume 时如果 pending_crushe_guide=True 已在上面清掉
    if working_state.get("pending_crushe_guide"):
        _ob_logger.info(
            "[onboarding] pending_crushe_guide=True, user_message=%r, is_guide_done=%s",
            (user_message or "")[:80], (user_message or "").strip() == GUIDE_DONE_TOKEN,
        )
        if (user_message or "").strip() == GUIDE_DONE_TOKEN:
            handoff = working_state.get("onboarding_handoff") or {
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
        _ob_logger.warning("[onboarding] ⚠️ pending_crushe_guide 提前退出: 未收到 GUIDE_DONE_TOKEN, route_to=end")
        return {
            "onboarding_completed": False,
            "pending_crushe_guide": True,
            "collected_info": collected_info,
            "pending_responses": _build_guide_gate_pending_responses(),
            "next_action": "end_turn",
            "route_to": "end",
            "_onboarding_interrupted": False,
            "_onboarding_interrupt_payload": {},
        }

    _ob_logger.info("[onboarding] 进入 supervisor 主逻辑: turn_count=%d, max_turns=%d", turn_count, max_turns)
    initial_messages = _build_onboarding_initial_messages(
        state=working_state,
        user_message=user_message,
        turn_count=turn_count,
        max_turns=max_turns,
        reference_questions=reference_questions,
    )
    # 仅用于兜底路径的初判补全，不再作为主链路模型输入
    conversation_history = _build_conversation_history(existing_messages)

    def state_getter() -> dict:
        return working_state

    submit_tool = create_submit_onboarding_tool(state_getter)
    tools: list[BaseTool] = [ask_human, submit_tool]
    llm = None
    supervisor: dict[str, Any] | None = None

    try:
        llm = get_llm(temperature=0.3, use_tools=True)
        supervisor = _run_onboarding_supervisor(
            llm=llm,
            tools=tools,
            initial_messages=initial_messages,
            config=config,
            max_rounds=6,
        )
    except Exception as e:
        _append_debug_log(
            run_id="tool-refactor",
            hypothesis_id="OB-H0",
            location="onboarding_agent.py:onboarding_agent_node:tool_supervisor_error",
            message="Tool supervisor failed; fallback to legacy parser",
            data={"error": str(e)},
        )
        supervisor = None

    merged_tool_patch = merge_patches(dict(pre_supervisor_patch), supervisor.get("patches", [])) if supervisor else dict(pre_supervisor_patch)
    progress_patch = _build_onboarding_answer_progress_patch(working_state, merged_tool_patch.get("inquiry_answers"))
    if progress_patch:
        merged_tool_patch = merge_state_patch(merged_tool_patch, progress_patch)

    if merged_tool_patch:
        working_state = merge_state_patch(working_state, merged_tool_patch)
        turn_count = int(working_state.get("onboarding_turn_count", turn_count) or turn_count)

    new_messages = list(supervisor.get("new_messages") or []) if supervisor else []
    submit_sequence = _extract_submit_onboarding_sequence(new_messages)
    submit_args = _extract_submit_onboarding_args(new_messages)
    submit_called = bool(submit_sequence.get("submit_called"))
    submit_patch_available = _has_submit_patch(merged_tool_patch)

    if supervisor and "__interrupt__" in supervisor:
        payload = _interrupt_value_from_supervisor(supervisor["__interrupt__"])
        _append_debug_log(
            run_id="tool-refactor",
            hypothesis_id="OB-H1",
            location="onboarding_agent.py:onboarding_agent_node:tool_path_interrupt",
            message="Onboarding tool path emitted interrupt",
            data={
                "has_payload": bool(payload),
                "merged_patch_keys": sorted(merged_tool_patch.keys()) if merged_tool_patch else [],
                "has_inquiry_answers": bool(merged_tool_patch.get("inquiry_answers")) if merged_tool_patch else False,
                "onboarding_turn_count": working_state.get("onboarding_turn_count"),
            },
        )
        interrupt_update = dict(merged_tool_patch or {})
        if isinstance(payload, dict) and payload:
            interrupt_update["inquiry_card"] = payload
        interrupt_update["_onboarding_interrupted"] = True
        interrupt_update["_onboarding_interrupt_payload"] = payload if isinstance(payload, dict) else {}
        interrupt_update.setdefault("next_action", "end_turn")
        interrupt_update.setdefault("route_to", "onboarding")
        return interrupt_update

    if submit_called or submit_patch_available:
        result = dict(merged_tool_patch or {})
        if not submit_patch_available:
            synthesized_submit_patch = build_onboarding_submit_patch(
                state_snapshot=working_state,
                submit_args=submit_args,
            )
            result = merge_state_patch(synthesized_submit_patch, result)

        result.setdefault("onboarding_completed", False)
        result.setdefault("pending_crushe_guide", True)
        result.setdefault("next_action", "end_turn")

        pre_submit_content = str(submit_sequence.get("pre_submit_content") or "").strip() or DEFAULT_PRE_SUBMIT_CONTENT
        post_submit_content = str(submit_sequence.get("post_submit_content") or "").strip() or DEFAULT_POST_SUBMIT_CONTENT
        result["pending_responses"] = _build_submit_pending_responses(
            pre_submit_content=pre_submit_content,
            post_submit_content=post_submit_content,
        )

        handoff = result.get("onboarding_handoff") if isinstance(result.get("onboarding_handoff"), dict) else {}
        preliminary = _build_preliminary_assessment_fallback(
            llm=llm,
            preliminary_assessment=result.get("preliminary_assessment"),
            handoff=handoff,
            conversation_history=conversation_history,
            user_message=user_message,
            turn_count=turn_count,
            allow_llm_fallback=False,
        )
        result = _attach_preliminary_assessment_to_result(result, preliminary)
        _append_debug_log(
            run_id="tool-refactor",
            hypothesis_id="OB-H1",
            location="onboarding_agent.py:onboarding_agent_node:tool_path_submit",
            message="Onboarding completed via submit_onboarding tool",
            data={
                "submit_called": submit_called,
                "patch_recovered_from_args": bool(submit_called and not submit_patch_available),
                "has_pending": bool(result.get("pending_responses")),
                "has_preliminary_assessment": bool(result.get("preliminary_assessment")),
            },
        )
        result.setdefault("_onboarding_interrupted", False)
        result.setdefault("_onboarding_interrupt_payload", {})
        return result

    # === Legacy JSON 兼容兜底 ===
    _append_debug_log(
        run_id="tool-refactor",
        hypothesis_id="OB-H3",
        location="onboarding_agent.py:onboarding_agent_node:legacy_fallback:start",
        message="Fallback to legacy JSON parser",
        data={
            "has_supervisor": bool(supervisor),
            "legacy_fallback_hit": True,
            "submit_called": submit_called,
            "submit_patch_available": submit_patch_available,
        },
    )

    if llm is None:
        llm = get_llm(temperature=0.3)

    legacy_content = ""
    if supervisor and getattr(supervisor.get("final"), "content", None) is not None:
        legacy_content = str(getattr(supervisor["final"], "content", "") or "")
    if not legacy_content:
        try:
            llm_resp = llm.invoke(initial_messages)
            legacy_content = str(getattr(llm_resp, "content", "") or "")
        except Exception:
            legacy_content = ""

    legacy_turn_count = turn_count
    legacy_user_message = user_message
    legacy_messages = list(existing_messages)
    legacy_collected_info = collected_info
    resume_wrapped_answers: dict[str, Any] | None = (
        working_state.get("inquiry_answers") if isinstance(working_state.get("inquiry_answers"), dict) else None
    )

    for _ in range(max(2, max_turns + 2)):
        parsed = _safe_json_loads(legacy_content)
        needs_more = bool(parsed.get("needs_more", False))
        preliminary_assessment = parsed.get("preliminary_assessment")
        if not isinstance(preliminary_assessment, dict):
            preliminary_assessment = None

        inquiry_card = parsed.get("inquiry_card") or {}
        questions = inquiry_card.get("questions", []) if isinstance(inquiry_card, dict) else []
        question_text = questions[0].get("question") if questions and isinstance(questions[0], dict) else parsed.get("question")
        if not question_text:
            question_text = _pick_next_question(legacy_collected_info)

        response_text = parsed.get("response") or inquiry_card.get("intro") or (question_text or "为确保理解你的情况，我想确认一下关键背景。")

        if needs_more and not questions and question_text:
            inquiry_card = {
                "questions": [
                    {
                        "id": f"onboard_q_{legacy_turn_count}",
                        "question": question_text,
                        "type": "free_input_question",
                        "info_type": 1,
                        "is_required": True,
                        "purpose": "补充关键背景",
                    }
                ],
                "intro": response_text,
                "reasoning": "Based on missing profile info",
            }

        updated_info = parsed.get("collected_info") or legacy_collected_info
        updated_info = _merge_collected(updated_info, legacy_user_message)

        _append_debug_log(
            run_id="tool-refactor",
            hypothesis_id="OB-H3",
            location="onboarding_agent.py:onboarding_agent_node:legacy_fallback:parsed",
            message="Parsed fallback onboarding output",
            data={
                "needs_more": needs_more,
                "question_text": question_text,
                "turn_count": legacy_turn_count,
            },
        )

        if needs_more and legacy_turn_count < max_turns and question_text:
            if isinstance(inquiry_card, dict) and inquiry_card.get("type") is None:
                inquiry_card = dict(inquiry_card)
                inquiry_card["type"] = "inquiry_card"
            return {
                "onboarding_completed": False,
                "pending_crushe_guide": False,
                "collected_info": legacy_collected_info,
                "inquiry_card": inquiry_card,
                "_onboarding_interrupted": True,
                "_onboarding_interrupt_payload": inquiry_card,
                "next_action": "end_turn",
                "route_to": "onboarding",
            }

        recommendation = parsed.get("recommendation", "")
        suggested_action = parsed.get("suggested_action", "") or "建议进行现状分析"
        reason = parsed.get("reason", "")
        handoff: OnboardingHandoff = {
            "collected_context": updated_info,
            "recommendation": recommendation or "信息已收集完毕，进入主流程进一步分析。",
            "suggested_action": suggested_action or "建议进行现状分析",
            "reason": reason or "Onboarding 收集完成。",
        }

        preliminary_assessment = _build_preliminary_assessment_fallback(
            llm=llm,
            preliminary_assessment=preliminary_assessment,
            handoff=handoff,
            conversation_history=conversation_history,
            user_message=legacy_user_message,
            turn_count=legacy_turn_count,
            allow_llm_fallback=True,
        )

        working_state["collected_info"] = updated_info
        if resume_wrapped_answers is not None:
            working_state["inquiry_answers"] = resume_wrapped_answers
        submit_result = submit_tool.invoke(
            {
                "response": parsed.get("response") or handoff["recommendation"],
                "recommendation": handoff["recommendation"],
                "suggested_action": handoff["suggested_action"],
                "reason": handoff["reason"],
                "preliminary_assessment": preliminary_assessment,
                "collected_info": updated_info,
            }
        )
        submit_patch = _extract_state_patch(submit_result)
        if resume_wrapped_answers is not None:
            submit_patch["inquiry_answers"] = resume_wrapped_answers
        submit_patch["onboarding_turn_count"] = int(working_state.get("onboarding_turn_count", legacy_turn_count) or legacy_turn_count)
        if working_state.get("onboarding_last_answer_fingerprint"):
            submit_patch["onboarding_last_answer_fingerprint"] = working_state.get("onboarding_last_answer_fingerprint")
        submit_patch = _attach_preliminary_assessment_to_result(submit_patch, preliminary_assessment)
        _append_debug_log(
            run_id="tool-refactor",
            hypothesis_id="OB-H3",
            location="onboarding_agent.py:onboarding_agent_node:legacy_fallback:submit",
            message="Completed onboarding via legacy fallback + submit_onboarding",
            data={
                "has_pending": bool(submit_patch.get("pending_responses")),
                "has_preliminary_assessment": bool(submit_patch.get("preliminary_assessment")),
            },
        )
        return submit_patch

    return {
        "onboarding_completed": False,
        "pending_crushe_guide": True,
        "collected_info": legacy_collected_info,
        "next_action": "end_turn",
        "route_to": "end",
    }
