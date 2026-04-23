from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_impl.scripts import run_ocr_pipeline_validation as validation


def test_build_second_node_configs_keeps_reference_then_glm_candidate_order():
    configs = validation._build_second_node_configs(  # pylint: disable=protected-access
        reference_provider="glm",
        reference_model="GLM-4.6V-FlashX",
        candidate_models=["GLM-4.6V-FlashX", "GLM-OCR"],
    )

    assert [cfg["key"] for cfg in configs] == [
        "reference__glm_4_6v_flashx",
        "glm_ocr",
    ]
    assert [cfg["mode"] for cfg in configs] == [
        "chat_completion",
        "layout_parsing",
    ]
    assert validation._build_glm_shadow_fallback_order(configs) == [  # pylint: disable=protected-access
        "reference__glm_4_6v_flashx",
        "glm_ocr",
    ]


def test_build_human_scores_uses_dynamic_second_node_order():
    ab_result = {
        "notes": {
            "second_node_configs": [
                {"key": "reference__glm_4_6v_flashx", "label": "reference_model", "model": "GLM-4.6V-FlashX", "provider": "glm"},
                {"key": "glm_ocr", "label": "GLM-OCR", "model": "GLM-OCR", "provider": "glm"},
            ]
        },
        "results": [
            {
                "image_path": "/tmp/sample.png",
                "second_node": {
                    "reference__glm_4_6v_flashx": {"result": {"text": "短文本"}},
                    "glm_ocr": {"result": {"text": "结构化 markdown"}},
                },
            }
        ],
    }
    shadow_result = {
        "results": [
            {
                "image_path": "/tmp/sample.png",
                "result": {"text": "shadow text"},
            }
        ]
    }

    scores = validation.build_human_scores(ab_result, shadow_result)

    assert scores["second_node_order"] == [
        "reference__glm_4_6v_flashx",
        "glm_ocr",
        "ocr_shadow",
    ]
    row = scores["scores"][0]["model_scores"]
    assert row["glm_ocr"]["provider"] == "glm"
    assert row["ocr_shadow"]["provider"] == "ocr"


def test_parse_args_supports_cases_manifest_and_repeated_candidates():
    args = validation.parse_args(
        [
            "--cases-manifest",
            "/tmp/cases.json",
            "--reference-provider",
            "doubao",
            "--reference-model",
            "Doubao-Seed-1.6-flash",
            "--candidate-model",
            "GLM-4.6V-FlashX",
            "--candidate-model",
            "GLM-OCR",
            "--shadow-fallback-key",
            "glm_4_6v_flashx",
            "--shadow-fallback-key",
            "glm_ocr",
        ]
    )

    assert args.cases_manifest == "/tmp/cases.json"
    assert args.reference_provider == "doubao"
    assert args.reference_model == "Doubao-Seed-1.6-flash"
    assert args.candidate_models == ["GLM-4.6V-FlashX", "GLM-OCR"]
    assert args.shadow_fallback_keys == ["glm_4_6v_flashx", "glm_ocr"]


def test_default_image_cases_are_private_chat_only():
    assert validation.DEFAULT_GLM_CANDIDATE_MODELS == ["GLM-4.6V-FlashX", "GLM-OCR"]
    assert len(validation.IMAGE_CASES) == 2
    assert {case["expected_type"] for case in validation.IMAGE_CASES} == {"private_chat_screenshot"}
