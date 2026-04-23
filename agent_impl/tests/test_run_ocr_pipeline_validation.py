from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_ocr_pipeline_validation.py"
SPEC = importlib.util.spec_from_file_location("run_ocr_pipeline_validation", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_normalize_layout_parsing_url_supports_chat_completion_base() -> None:
    url = MODULE._normalize_layout_parsing_url("https://open.bigmodel.cn/api/paas/v4/chat/completions")
    assert url == "https://open.bigmodel.cn/api/paas/v4/layout_parsing"


def test_build_second_node_configs_dedupes_reference_and_marks_glm_ocr_mode() -> None:
    configs = MODULE._build_second_node_configs(
        reference_provider="glm",
        reference_model="GLM-4.6V-FlashX",
        candidate_models=["GLM-4.6V-FlashX", "GLM-OCR"],
    )

    assert [cfg["model"] for cfg in configs] == [
        "GLM-4.6V-FlashX",
        "GLM-OCR",
    ]
    assert [cfg["mode"] for cfg in configs] == [
        "chat_completion",
        "layout_parsing",
    ]


def test_load_image_cases_supports_object_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "cases.json"
    manifest.write_text(
        """
        {
          "cases": [
            {
              "image_path": "/tmp/a.png",
              "expected_type": "private_chat_screenshot",
              "store_uri_env": "VOLC_IMAGEX_STORE_URI_1"
            }
          ]
        }
        """.strip(),
        encoding="utf-8",
    )

    cases = MODULE._load_image_cases(manifest)

    assert cases == [
        {
            "image_path": "/tmp/a.png",
            "expected_type": "private_chat_screenshot",
            "store_uri_env": "VOLC_IMAGEX_STORE_URI_1",
        }
    ]
