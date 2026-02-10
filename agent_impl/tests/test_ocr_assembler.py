from utils.ocr_assembler import assemble_ocr_text


def test_chat_assembler_speaker_assignment_by_x():
    lines = [
        {
            "content": "我交手机了",
            "confidence": 0.99,
            "bbox": {"x_min": 700, "x_max": 980, "y_min": 100, "y_max": 140},
            "cx": 840,
            "cy": 120,
        },
        {
            "content": "拜拜",
            "confidence": 0.98,
            "bbox": {"x_min": 720, "x_max": 980, "y_min": 146, "y_max": 188},
            "cx": 850,
            "cy": 167,
        },
        {
            "content": "好的",
            "confidence": 0.97,
            "bbox": {"x_min": 60, "x_max": 320, "y_min": 230, "y_max": 268},
            "cx": 190,
            "cy": 249,
        },
    ]

    assembled = assemble_ocr_text(
        screenshot_type="private_chat_screenshot",
        lines=lines,
        image_width=1080,
        image_height=1800,
    )
    msgs = assembled["structured_messages"]

    assert len(msgs) >= 2
    assert msgs[0]["speaker"] == "USER"
    assert "我交手机了" in msgs[0]["text"]
    assert msgs[1]["speaker"] == "CRUSH"


def test_chat_assembler_marks_time_line_as_system():
    lines = [
        {
            "content": "8月24日上午09:04",
            "confidence": 0.99,
            "bbox": {"x_min": 420, "x_max": 660, "y_min": 100, "y_max": 130},
            "cx": 540,
            "cy": 115,
        },
        {
            "content": "早安",
            "confidence": 0.97,
            "bbox": {"x_min": 710, "x_max": 900, "y_min": 170, "y_max": 210},
            "cx": 805,
            "cy": 190,
        },
    ]
    assembled = assemble_ocr_text(
        screenshot_type="private_chat_screenshot",
        lines=lines,
        image_width=1080,
        image_height=1800,
    )
    msgs = assembled["structured_messages"]
    assert msgs[0]["speaker"] == "SYSTEM"
    assert msgs[1]["speaker"] == "USER"

