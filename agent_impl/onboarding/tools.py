from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agents.tooling.tool_result import ok


class SubmitOnboardingInput(BaseModel):
    response: str = Field(description="给用户的可见回复（兜底文案；主流程优先使用模型前后两段引导）")
    recommendation: str = Field(description="给主流程的交接建议")
    suggested_action: str = Field(description="给主流程的下一步动作建议（自然语言）")
    reason: str = Field(default="", description="建议原因（可选）")
    preliminary_assessment: dict[str, Any] | None = Field(
        default=None,
        description="局势初判卡（可选）",
    )
    collected_info: dict[str, Any] | None = Field(
        default=None,
        description="收集到的信息（可选，未提供时使用 state.collected_info）",
    )


def _ensure_collected_shape(collected: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(collected or {})
    merged.setdefault("raw_inputs", [])
    merged.setdefault("user_profile", {})
    merged.setdefault("crush_profile", {})
    merged.setdefault("pain_points", [])
    return merged


def _append_raw_input_once(collected: dict[str, Any], text: str) -> dict[str, Any]:
    content = (text or "").strip()
    if not content:
        return collected
    history = list(collected.get("raw_inputs", []) or [])
    if content not in history:
        history.append(content)
    collected["raw_inputs"] = history
    return collected


def _normalize_interrupt_answers(raw_answer: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(raw_answer, dict):
        answers_obj = raw_answer.get("answers")
        if isinstance(answers_obj, dict):
            return answers_obj, {"answers": answers_obj}
        return raw_answer, {"answers": raw_answer}
    return {"answer": raw_answer}, {"answers": {"answer": raw_answer}}


def _format_resume_answers_for_history(inquiry_card: dict[str, Any], answers: dict[str, Any]) -> str:
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


def build_onboarding_submit_patch(
    state_snapshot: dict[str, Any] | None,
    submit_args: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    构建 submit_onboarding 的标准 state patch。

    该函数是纯函数：输入 state 快照 + submit 参数，输出可直接 merge 的 patch。
    """
    state = state_snapshot if isinstance(state_snapshot, dict) else {}
    args = submit_args if isinstance(submit_args, dict) else {}

    current_collected = state.get("collected_info") if isinstance(state.get("collected_info"), dict) else {}
    merged_collected = _ensure_collected_shape(args.get("collected_info") or current_collected)

    user_message = str(state.get("user_message") or "").strip()
    inquiry_answers = state.get("inquiry_answers")
    inquiry_card = state.get("inquiry_card") if isinstance(state.get("inquiry_card"), dict) else {}

    if isinstance(inquiry_answers, dict):
        normalized_answers, wrapped_answers = _normalize_interrupt_answers(inquiry_answers)
        resume_message = _format_resume_answers_for_history(inquiry_card, normalized_answers)
        merged_collected = _append_raw_input_once(merged_collected, resume_message)
        inquiry_answers_patch = wrapped_answers
    else:
        if user_message:
            merged_collected = _append_raw_input_once(merged_collected, user_message)
        inquiry_answers_patch = inquiry_answers

    recommendation = str(args.get("recommendation") or "").strip() or "信息已收集完毕，进入主流程进一步分析。"
    suggested_action = str(args.get("suggested_action") or "").strip() or "建议进行现状分析"
    reason = str(args.get("reason") or "").strip() or "Onboarding 收集完成。"
    response = str(args.get("response") or "").strip()

    handoff = {
        "collected_context": merged_collected,
        "recommendation": recommendation,
        "suggested_action": suggested_action,
        "reason": reason,
    }

    content = response or recommendation
    patch: dict[str, Any] = {
        "onboarding_completed": False,
        "pending_crushe_guide": True,
        "onboarding_handoff": handoff,
        "collected_info": merged_collected,
        "inquiry_answers": inquiry_answers_patch,
        "inquiry_card": None,
        "next_action": "end_turn",
        "pending_responses": [
            {
                "from": "onboarding",
                "content": content,
                "phase": "submit_fallback",
            }
        ],
    }

    preliminary_assessment = args.get("preliminary_assessment")
    if isinstance(preliminary_assessment, dict):
        patch["preliminary_assessment"] = preliminary_assessment
        patch["pending_responses"][0]["preliminary_assessment"] = preliminary_assessment

    return patch


def create_submit_onboarding_tool(state_getter: Callable[[], dict]) -> StructuredTool:
    def _submit_onboarding(
        response: str,
        recommendation: str,
        suggested_action: str,
        reason: str = "",
        preliminary_assessment: dict[str, Any] | None = None,
        collected_info: dict[str, Any] | None = None,
    ) -> dict:
        state = state_getter() or {}
        patch = build_onboarding_submit_patch(
            state_snapshot=state,
            submit_args={
                "response": response,
                "recommendation": recommendation,
                "suggested_action": suggested_action,
                "reason": reason,
                "preliminary_assessment": preliminary_assessment,
                "collected_info": collected_info,
            },
        )
        return ok(output="已提交 onboarding 收口", state_patch=patch)

    return StructuredTool.from_function(
        func=_submit_onboarding,
        name="submit_onboarding",
        description="提交 onboarding 结果并写入状态（含 handoff/pending_crushe_guide）。",
        args_schema=SubmitOnboardingInput,
        return_direct=True,
    )
