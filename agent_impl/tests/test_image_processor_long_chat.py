from __future__ import annotations

import asyncio
from io import BytesIO

from PIL import Image

from utils.image_processor import ImageProcessor


def _build_processor() -> ImageProcessor:
    processor = ImageProcessor()
    processor.api_key = "test_api_key"
    processor.model = "test_model"
    processor.type_detect_api_key = "test_api_key"
    processor.type_detect_model = "test_type_detect_model"
    processor.type_detect_base_url = "https://example.com/v1"
    processor.ocr_api_key = "test_api_key"
    processor.ocr_model = "test_ocr_model"
    processor.ocr_base_url = "https://example.com/v1"
    processor.long_chat_ocr_api_key = ""
    processor.long_chat_ocr_model = ""
    processor.long_chat_ocr_base_url = ""
    return processor


def _make_png_bytes(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_long_image_candidate_detection():
    processor = _build_processor()

    long_bytes = _make_png_bytes(400, 6000)
    short_bytes = _make_png_bytes(1080, 2200)

    long_meta = processor._get_long_image_meta(long_bytes)
    short_meta = processor._get_long_image_meta(short_bytes)

    assert long_meta["is_candidate"] is True
    assert long_meta["width"] == 400
    assert long_meta["height"] == 6000
    assert short_meta["is_candidate"] is False


def test_build_segment_ranges_respects_overlap():
    processor = _build_processor()
    processor.long_chat_segment_height = 2600
    processor.long_chat_overlap = 220

    ranges = processor._build_segment_ranges(6000)

    assert ranges == [(0, 2600), (2380, 4980), (4760, 6000)]


def test_build_segment_ranges_snaps_to_candidate_cut_lines():
    processor = _build_processor()
    processor.long_chat_segment_height = 2600
    processor.long_chat_overlap = 220
    processor.long_chat_boundary_search_radius = 220

    ranges = processor._build_segment_ranges(
        6000,
        candidate_lines=[
            {"y": 2260.0, "score": 0.01},
            {"y": 4700.0, "score": 0.02},
        ],
    )

    assert ranges == [(0, 2480), (2260, 4920), (4700, 6000)]


def test_snap_segment_boundary_falls_back_without_nearby_candidate():
    processor = _build_processor()
    processor.long_chat_boundary_search_radius = 120

    snapped, matched = processor._snap_segment_boundary(
        2380,
        image_height=5999,
        candidate_lines=[{"y": 1800.0, "score": 0.01}],
        lower_bound=120,
    )

    assert snapped == 2380
    assert matched is None


def test_extract_chat_table_rows_filters_time_separator_rows():
    processor = _build_processor()

    text = """#### 记录1
| 发送者 | 内容 | 时间戳 | 文本序号 |
| :--- | :--- | :--- | :--- |
| 8月24日 上午09:04 |  |  | 1 |
| 昨天 19:18 |  |  | 2 |
| 系统 | 8月24日 上午11:02 |  | 3 |
| 用户 | 早安 |  | 3 |
| Crush | 你好 | 09:05 | 4 |"""

    rows = processor._extract_chat_table_rows(text)

    assert rows == [
        {"sender": "用户", "content": "早安", "timestamp": ""},
        {"sender": "Crush", "content": "你好", "timestamp": "09:05"},
    ]


def test_clean_chat_markdown_output_private_removes_explanatory_rows():
    processor = _build_processor()

    text = """#### 记录1
| 发送者 | 内容 | 时间戳 | 文本序号 |
| :--- | :--- | :--- | :--- |
| 系统 | （视觉分隔线，不录入表格） |  | 1 |
| {{user_name}} | 在吗 | 09:01 | 2 |
| 对方（女性头像） | 你好 | 09:02 | 3 |
| 用户 | 早安 | 09:03 | 4 |
| 系统 | 一条消息已被撤回 | 09:04 | 5 |
| 用户 |  |  | 6 |"""

    cleaned = processor._clean_chat_markdown_output(text, "private_chat_screenshot")

    assert "视觉分隔线" not in cleaned
    assert "{{user_name}}" not in cleaned
    assert "对方（女性头像）" not in cleaned
    assert "| 用户 | 在吗 | 09:01 | 1 |" in cleaned
    assert "| 用户 | 早安 | 09:03 | 2 |" in cleaned
    assert "| 系统 | 一条消息已被撤回 | 09:04 | 3 |" in cleaned


def test_clean_chat_markdown_output_private_removes_non_system_separator_rows():
    processor = _build_processor()

    text = """#### 记录1
| 发送者 | 内容 | 时间戳 | 文本序号 |
| :--- | :--- | :--- | :--- |
| 用户 | 22:15 |  | 1 |
| Crush | 以下是最新消息 |  | 2 |
| 用户 | 在吗 | 22:16 | 3 |"""

    cleaned = processor._clean_chat_markdown_output(text, "private_chat_screenshot")

    assert "| 用户 | 22:15 |" not in cleaned
    assert "| Crush | 以下是最新消息 |" not in cleaned
    assert "| 用户 | 在吗 | 22:16 | 1 |" in cleaned


def test_clean_chat_markdown_output_private_normalizes_named_sender_to_crush():
    processor = _build_processor()

    text = """#### 记录1
| 发送者 | 内容 | 时间戳 | 文本序号 |
| :--- | :--- | :--- | :--- |
| 蔡丹湧 | 好感是有的 | 9月20日 14:34 | 1 |
| 用户 | 你喜欢我吗 | 9月20日 14:07 | 2 |"""

    cleaned = processor._clean_chat_markdown_output(text, "private_chat_screenshot")

    assert "| 蔡丹湧 |" not in cleaned
    assert "| Crush | 好感是有的 | 9月20日 14:34 | 1 |" in cleaned


def test_clean_chat_markdown_output_private_removes_reply_preview_system_row():
    processor = _build_processor()

    text = """#### 记录1
| 发送者 | 内容 | 时间戳 | 文本序号 |
| :--- | :--- | :--- | :--- |
| 用户 | 挺好 |  | 1 |
| 系统 | 了呦刘：你跟你bz关系好嘛 |  | 2 |
| Crush | 也是 |  | 3 |"""

    cleaned = processor._clean_chat_markdown_output(text, "private_chat_screenshot")

    assert "了呦刘：你跟你bz关系好嘛" not in cleaned
    assert "| 用户 | 挺好 |  | 1 |" in cleaned
    assert "| Crush | 也是 |  | 2 |" in cleaned


def test_clean_chat_markdown_output_private_dedupes_recent_untimestamped_overlap_rows():
    processor = _build_processor()

    text = """#### 记录1
| 发送者 | 内容 | 时间戳 | 文本序号 |
| :--- | :--- | :--- | :--- |
| 用户 | 那好吧 | 8月24日 上午10:55 | 1 |
| 用户 | 那我只能等一周了 | 8月24日 上午10:55 | 2 |
| 用户 | 那好吧 |  | 3 |
| 用户 | 那我只能等一周了 |  | 4 |
| Crush | 哈哈 |  | 5 |"""

    cleaned = processor._clean_chat_markdown_output(text, "private_chat_screenshot")

    assert cleaned.count("那好吧") == 1
    assert cleaned.count("那我只能等一周了") == 1
    assert "| Crush | 哈哈 |  | 3 |" in cleaned


def test_clean_chat_markdown_output_group_normalizes_placeholder_sender():
    processor = _build_processor()

    text = """#### 记录1
| 发送者 | 内容 | 时间戳 | 文本序号 |
| :--- | :--- | :--- | :--- |
| 系统 | （时间摘要：昨天 22:15） |  | 1 |
| {{crush_name}} | 到了吗 | 22:16 | 2 |
| 张三 | 到门口了 | 22:17 | 3 |"""

    cleaned = processor._clean_chat_markdown_output(text, "group_chat_screenshot")

    assert "时间摘要" not in cleaned
    assert "{{crush_name}}" not in cleaned
    assert "| Crush | 到了吗 | 22:16 | 1 |" in cleaned
    assert "| 张三 | 到门口了 | 22:17 | 2 |" in cleaned


def test_boundary_dedupe_removes_head_window_duplicates_only():
    processor = _build_processor()
    processor.long_chat_dedupe_window = 2

    previous_rows = [
        {"sender": "用户", "content": "你好", "timestamp": "09:00"},
        {"sender": "Crush", "content": "在吗", "timestamp": "09:01"},
        {"sender": "用户", "content": "吃饭了吗", "timestamp": "09:02"},
    ]
    current_rows = [
        {"sender": "Crush", "content": "在吗", "timestamp": "09:01"},
        {"sender": "用户", "content": "吃饭了吗", "timestamp": "09:02"},
        {"sender": "Crush", "content": "还没", "timestamp": "09:03"},
        {"sender": "用户", "content": "吃饭了吗", "timestamp": "09:02"},
    ]

    deduped_rows, removed = processor._dedupe_segment_boundary_rows(previous_rows, current_rows)

    assert removed == 2
    assert deduped_rows == [
        {"sender": "Crush", "content": "还没", "timestamp": "09:03"},
        {"sender": "用户", "content": "吃饭了吗", "timestamp": "09:02"},
    ]


def test_boundary_dedupe_uses_normalized_content():
    processor = _build_processor()
    processor.long_chat_dedupe_window = 3

    previous_rows = [
        {"sender": "用户", "content": "你好<br>在吗", "timestamp": "09:00"},
    ]
    current_rows = [
        {"sender": "用户", "content": "你好 <br /> 在吗  ", "timestamp": "09:00"},
        {"sender": "Crush", "content": "在的", "timestamp": "09:01"},
    ]

    deduped_rows, removed = processor._dedupe_segment_boundary_rows(previous_rows, current_rows)

    assert removed == 1
    assert deduped_rows == [
        {"sender": "Crush", "content": "在的", "timestamp": "09:01"},
    ]


def test_boundary_dedupe_prefers_row_farther_from_segment_edge_on_sender_conflict():
    processor = _build_processor()
    processor.long_chat_dedupe_window = 3

    previous_rows = [
        {"sender": "用户", "content": "同一条消息", "timestamp": "09:00", "_boundary_distance": 0},
        {"sender": "Crush", "content": "下一条", "timestamp": "09:01", "_boundary_distance": 1},
    ]
    current_rows = [
        {"sender": "Crush", "content": "同一条消息", "timestamp": "09:00", "_boundary_distance": 3},
        {"sender": "用户", "content": "新的消息", "timestamp": "09:02", "_boundary_distance": 2},
    ]

    deduped_rows, removed = processor._dedupe_segment_boundary_rows(previous_rows, current_rows)

    assert removed == 1
    assert previous_rows[0]["sender"] == "Crush"
    assert deduped_rows == [
        {"sender": "用户", "content": "新的消息", "timestamp": "09:02", "_boundary_distance": 2},
    ]


def test_detect_type_long_chat_probe_forces_private():
    processor = _build_processor()
    long_bytes = _make_png_bytes(400, 6000)
    calls: list[int] = []

    async def _fake_detect_once(image_bytes: bytes):
        _ = image_bytes
        idx = len(calls)
        calls.append(idx)
        if idx == 1:
            return {
                "success": True,
                "screenshot_type": "group_chat_screenshot",
                "confidence": "high",
                "reason": "chat found",
                "error": None,
            }
        return {
            "success": True,
            "screenshot_type": "universal_screenshot_analysis",
            "confidence": "low",
            "reason": "not chat",
            "error": None,
        }

    processor._detect_type_once = _fake_detect_once  # type: ignore[method-assign]

    result = asyncio.run(processor.detect_type(long_bytes))

    assert result["success"] is True
    assert result["screenshot_type"] == "private_chat_screenshot"
    assert result["reason"] == "long_chat_slice_probe"
    assert len(calls) == 2


def test_detect_type_long_non_chat_falls_back_to_single_pass():
    processor = _build_processor()
    long_bytes = _make_png_bytes(400, 6000)
    calls: list[int] = []

    async def _fake_detect_once(image_bytes: bytes):
        _ = image_bytes
        idx = len(calls)
        calls.append(idx)
        if idx < 3:
            return {
                "success": True,
                "screenshot_type": "universal_screenshot_analysis",
                "confidence": "low",
                "reason": "not chat",
                "error": None,
            }
        return {
            "success": True,
            "screenshot_type": "moments_screenshot",
            "confidence": "medium",
            "reason": "full image fallback",
            "error": None,
        }

    processor._detect_type_once = _fake_detect_once  # type: ignore[method-assign]

    result = asyncio.run(processor.detect_type(long_bytes))

    assert result["success"] is True
    assert result["screenshot_type"] == "moments_screenshot"
    assert len(calls) == 4


def test_process_image_long_chat_merges_and_dedupes_from_universal_input():
    processor = _build_processor()
    processor.long_chat_segment_height = 2600
    processor.long_chat_overlap = 220
    processor.long_chat_dedupe_window = 8
    long_bytes = _make_png_bytes(400, 6000)
    calls: list[int] = []

    async def _fake_probe(image_bytes: bytes, image_meta: dict | None = None):
        _ = image_bytes, image_meta
        return {
            "matched_chat": True,
            "forced_type": "private_chat_screenshot",
            "reason": "long_chat_slice_probe",
            "probes": [],
        }

    async def _fake_single_pass(
        image_bytes: bytes,
        screenshot_type: str,
        additional_context: str | None = None,
        *,
        ocr_override=None,
    ):
        _ = image_bytes, additional_context, ocr_override
        idx = len(calls)
        calls.append(idx)
        outputs = [
            """#### 记录1
| 发送者 | 内容 | 时间戳 | 文本序号 |
| :--- | :--- | :--- | :--- |
| Crush | 你好呀 | 09:00 | 1 |
| 用户 | 早上好 | 09:01 | 2 |
| 8月24日 上午09:04 |  |  | 3 |""",
            """#### 记录1
| 发送者 | 内容 | 时间戳 | 文本序号 |
| :--- | :--- | :--- | :--- |
| 用户 | 早上好 | 09:01 | 1 |
| Crush | 吃饭了吗 | 09:02 | 2 |""",
            """#### 记录1
| 发送者 | 内容 | 时间戳 | 文本序号 |
| :--- | :--- | :--- | :--- |
| Crush | 吃饭了吗 | 09:02 | 1 |
| 用户 | 还没呢 | 09:03 | 2 |""",
        ]
        return {
            "success": True,
            "text": outputs[idx],
            "screenshot_type": screenshot_type,
            "error": None,
        }

    processor._probe_long_chat_candidate = _fake_probe  # type: ignore[method-assign]
    processor._process_image_single_pass = _fake_single_pass  # type: ignore[method-assign]

    result = asyncio.run(
        processor.process_image(
            image_bytes=long_bytes,
            screenshot_type="universal_screenshot_analysis",
        )
    )

    assert result["success"] is True
    assert result["screenshot_type"] == "private_chat_screenshot"
    assert len(calls) == 3
    assert "发送者1：对方（女性头像，戴眼镜）" not in result["text"]
    assert "| 8月24日 上午09:04 |  |  |" not in result["text"]
    assert "| Crush | 你好呀 | 09:00 | 1 |" in result["text"]
    assert "| 用户 | 早上好 | 09:01 | 2 |" in result["text"]
    assert "| Crush | 吃饭了吗 | 09:02 | 3 |" in result["text"]


def test_process_image_long_chat_uses_dedicated_model_with_segmented_pipeline():
    processor = _build_processor()
    processor.long_chat_ocr_api_key = "dashscope_key"
    processor.long_chat_ocr_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    processor.long_chat_ocr_model = "qwen-vl-plus"
    long_bytes = _make_png_bytes(400, 6000)
    seen = {}

    async def _fake_segmented(
        image_bytes: bytes,
        additional_context: str | None = None,
        *,
        ocr_override=None,
    ):
        _ = image_bytes, additional_context
        # 专用 OCR 必须通过参数透传，避免修改 singleton 实例属性
        assert ocr_override is not None, "dedicated OCR must be passed via ocr_override parameter"
        seen["api_key"], seen["base_url"], seen["model"] = ocr_override
        return {
            "success": True,
            "text": "#### 记录1\n| 发送者 | 内容 | 时间戳 | 文本序号 |\n| :--- | :--- | :--- | :--- |\n| Crush | 你好 |  | 1 |",
            "screenshot_type": "private_chat_screenshot",
            "error": None,
        }

    async def _fake_single_pass(*args, **kwargs):
        raise AssertionError("single-pass OCR should not be used for long-chat dedicated route")

    processor._process_image_single_pass = _fake_single_pass  # type: ignore[method-assign]
    processor._process_long_private_chat_image = _fake_segmented  # type: ignore[method-assign]

    result = asyncio.run(
        processor.process_image(
            image_bytes=long_bytes,
            screenshot_type="private_chat_screenshot",
        )
    )

    assert result["success"] is True
    assert result["screenshot_type"] == "private_chat_screenshot"
    assert seen == {
        "model": "qwen-vl-plus",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "dashscope_key",
    }
    assert processor.ocr_model == "test_ocr_model"
    assert processor.ocr_base_url == "https://example.com/v1"
    assert processor.ocr_api_key == "test_api_key"
