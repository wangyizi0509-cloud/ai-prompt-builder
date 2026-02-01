from __future__ import annotations


def test_feedback_instruction_prefers_ask_card():
    """
    单元测试：反馈模式动态注入的 instruction 必须明确
    - 支持并优先使用 ask(action="enable") 进入提问卡流程
    - 最终总结使用 [反馈完成] 标签（用于历史压缩保留）
    """
    from graph.nodes.guide_agent import _build_feedback_instruction, FEEDBACK_SUMMARY_TAG

    state = {}
    guide = {"title": "测试指南", "status": "in_progress"}
    feedback_mode = {
        "guide_id": "g_test",
        "prefilled_status": "partial",
        "prefilled_detail": "先做了一半，结果一般。",
    }

    instruction = _build_feedback_instruction(state, guide, feedback_mode)

    assert "【行动反馈流程】" in instruction
    assert 'ask(action="enable")' in instruction
    assert FEEDBACK_SUMMARY_TAG in instruction
    # 枚举约束应被明确写出，便于模型稳定填值
    assert "success / partial / failed / abandoned / other" in instruction

