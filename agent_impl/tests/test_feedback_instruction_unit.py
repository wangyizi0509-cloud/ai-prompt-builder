from __future__ import annotations


def test_feedback_summary_tag_is_excluded_from_qa_history():
    """
    单元测试：反馈追问历史抽取逻辑必须排除总结标记内容
    - FEEDBACK_SUMMARY_TAG 用于历史压缩保留，但不应进入 qa_history
    """
    from graph.tools.submit_tools import _build_feedback_qa_history, FEEDBACK_SUMMARY_TAG

    messages = [
        {"id": "m1", "role": "user", "content": "我来反馈一下执行情况"},
        {"id": "m2", "role": "assistant", "content": "你做得怎么样？"},
        {"id": "m3", "role": "user", "content": "完成一半，效果一般"},
        {"id": "m4", "role": "assistant", "content": f"{FEEDBACK_SUMMARY_TAG} 总结：已记录反馈"},
        {"id": "m5", "role": "assistant", "content": "下一步我们再微调"},
    ]

    qa = _build_feedback_qa_history(messages, start_message_id="m1", keep_tag=FEEDBACK_SUMMARY_TAG)
    assert all(FEEDBACK_SUMMARY_TAG not in item.get("content", "") for item in qa)
    assert [x["role"] for x in qa] == ["user", "ai", "user", "ai"]
