from agents.tooling.interrupts import build_inquiry_interrupt_payload


def test_build_inquiry_interrupt_payload_normalizes_question_ids_and_text():
    payload = build_inquiry_interrupt_payload(
        inquiry_card={
            "questions": [
                {"id": "", "question": "", "type": "single_choice"},
                {"id": "dup", "question": "第二题", "type": "single_choice"},
                {"id": "dup", "question": "   ", "type": "single_choice"},
                {"question": "末题", "type": "free_input_question"},
                "bad_item",
            ],
            "intro": None,
            "reasoning": None,
        }
    )

    questions = payload["questions"]
    # "bad_item" 字符串会被 normalizer 转为 {"question": "bad_item"}，因此共 5 道题
    assert [q["id"] for q in questions] == ["q1", "dup", "dup_2", "q4", "q5"]
    assert [q["question"] for q in questions] == ["问题1", "第二题", "问题3", "末题", "bad_item"]
    assert payload["type"] == "inquiry_card"
    assert payload["intro"] == ""
    assert payload["reasoning"] == ""


def test_build_inquiry_interrupt_payload_invalid_questions_fallback_empty_list():
    payload = build_inquiry_interrupt_payload(
        inquiry_card={
            "type": "",
            "questions": {"id": "q1"},
            "intro": 123,
            "reasoning": False,
        }
    )

    assert payload["type"] == "inquiry_card"
    assert payload["questions"] == []
    assert payload["intro"] == ""
    assert payload["reasoning"] == ""
