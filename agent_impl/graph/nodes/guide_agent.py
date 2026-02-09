from __future__ import annotations

from typing import Any

from graph.tools.submit_tools import FEEDBACK_SUMMARY_TAG


def _build_feedback_instruction(state: dict, guide: dict, feedback_mode: dict) -> str:
    title = guide.get("title") if isinstance(guide, dict) else ""
    title_text = str(title) if isinstance(title, (str, int, float, bool)) else ""
    prefilled_status = ""
    prefilled_detail = ""
    if isinstance(feedback_mode, dict):
        s = feedback_mode.get("prefilled_status")
        d = feedback_mode.get("prefilled_detail")
        prefilled_status = str(s) if isinstance(s, (str, int, float, bool)) else ""
        prefilled_detail = str(d) if isinstance(d, (str, int, float, bool)) else ""

    lines: list[str] = []
    lines.append("【行动反馈流程】")
    if title_text:
        lines.append(f"目标指南：{title_text}")
    if prefilled_status or prefilled_detail:
        lines.append("已知反馈（可用则用，不确定就不要硬填）：")
        if prefilled_status:
            lines.append(f"- prefilled_status: {prefilled_status}")
        if prefilled_detail:
            lines.append(f"- prefilled_detail: {prefilled_detail}")

    lines.append("当信息不足时，优先用提问卡收集信息：先调用 ask(action=\"enable\") 进入提问模式。")
    lines.append(f"完成写入后，在 content 输出以 {FEEDBACK_SUMMARY_TAG} 开头的一句最短总结。")
    lines.append("completion_status 可选值：success / partial / failed / abandoned / other")
    return "\n".join(lines)


__all__ = ["_build_feedback_instruction", "FEEDBACK_SUMMARY_TAG"]
