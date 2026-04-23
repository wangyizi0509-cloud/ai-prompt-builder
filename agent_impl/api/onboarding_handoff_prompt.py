"""Onboarding v2 → main_agent 首轮消息拼装。

付费后前端把漏斗阶段采集的原始素材(自由描述、截图 OCR、答题)用
`onboarding_payload` 字段传给 `/api/chat/stream`。本文件负责把结构化 payload
渲染成一段固定模板的 user_message,作为 main_agent 首轮唯一输入。

关键约束:
- 首轮 user_message 完全由这个模板产出,不拼接用户的 `message`(付费后首轮
  用户并没有输入)
- 模板第一段是「系统指令 · 仅本轮」,显式告诉 main_agent 立即调用
  call_status_agent,并要求 instruction 只写「目的」,不要总结
- status 子图通过 parent_state 透传能看到同一批原始素材,因此 main 不需要
  替 status 做信息总结
- 非首轮即使前端误传了 payload,调用方需自行忽略(参考 chat.py:
  `_is_first_turn_for_thread`)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OnboardingOcr(BaseModel):
    ocr_result: str = ""
    ocr_failed: bool = False


class OnboardingPayload(BaseModel):
    """Onboarding v2 漏斗阶段采集的原始素材。"""

    free_text: str = ""
    ocr_texts: list[OnboardingOcr] = Field(default_factory=list)
    answers: dict[str, Any] = Field(default_factory=dict)


_SYSTEM_INSTRUCTION = """[系统指令 · 仅本轮]
用户刚完成 Onboarding 诊断漏斗并付费进入主对话,这是第一次对话。
请立即执行:
1. 直接调用 call_status_agent 生成首份现状报告,不要先跟用户寒暄或重复提问
2. instruction 段只写「目的」,例如「基于 onboarding 诊断素材生成首份现状报告」
   —— 不要复述用户原话或做任何总结,status 子图会自动看到本消息的完整素材
3. status 报告产出后,基于报告结论给用户首轮开场回复
本指令仅本轮有效,后续轮次不会再出现。"""


def _render_answers(answers: dict[str, Any]) -> list[str]:
    """把 {"A3": ["A","C"], "A5": "B"} 渲染成人话 bullet 列表。"""
    # 按题号排序,保证输出稳定
    from onboarding_v2.question_bank import QUESTION_BANK

    lines: list[str] = []
    for qid in sorted(answers.keys()):
        raw = answers.get(qid)
        if raw is None:
            continue
        q = QUESTION_BANK.get(qid)
        if not q:
            # 未知题号:保留 raw 值,避免数据丢失
            lines.append(f"- {qid}: {raw}")
            continue

        # 归一化为 list,单选也走同一路径
        picked = raw if isinstance(raw, list) else [raw]
        option_map = {opt.get("id"): opt.get("label", "") for opt in q.get("options", [])}
        rendered_items: list[str] = []
        for code in picked:
            label = option_map.get(code)
            if label:
                rendered_items.append(f"{code}={label}")
            else:
                # 允许用户自由输入时 code 可能是文本本身
                rendered_items.append(str(code))

        question_title = str(q.get("question") or "").strip()
        # 去掉「（可多选）」这类括号尾和问号结尾,让 bullet 标题更短
        short_title = question_title.split("（")[0].split("(")[0].rstrip("？?，,。.").strip()
        lines.append(f"- {qid}({short_title}):{', '.join(rendered_items)}")
    return lines


def render_onboarding_first_turn_message(payload: OnboardingPayload) -> str:
    """把 onboarding_payload 渲染成首轮 user_message(固定模板)。"""
    sections: list[str] = [_SYSTEM_INSTRUCTION, "", "[诊断素材]", "## 用户自由描述"]

    free_text = (payload.free_text or "").strip()
    sections.append(free_text if free_text else "(用户未填写)")
    sections.append("")

    if payload.ocr_texts:
        sections.append("## 截图 OCR")
        for idx, item in enumerate(payload.ocr_texts, 1):
            sections.append(f"### 截图 {idx}")
            text = (item.ocr_result or "").strip()
            if text:
                sections.append(text)
            elif item.ocr_failed:
                sections.append("(OCR 失败)")
            else:
                sections.append("(OCR 为空)")
            sections.append("")

    if payload.answers:
        sections.append("## 筛题答卷")
        sections.extend(_render_answers(payload.answers))

    # 收尾去掉末尾多余空行
    while sections and sections[-1] == "":
        sections.pop()
    return "\n".join(sections)
