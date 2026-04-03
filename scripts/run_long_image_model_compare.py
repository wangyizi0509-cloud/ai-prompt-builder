#!/usr/bin/env python3
"""
长图私聊截图 — 切片 pipeline 对比脚本

通过复用 ImageProcessor 的完整长图切片 + 合并逻辑，直接对比：
  1. qwen-vl-plus    (当前长图生产基线)
  2. qwen3-vl-plus   (新候选)

用法
----
python3 scripts/run_long_image_model_compare.py
python3 scripts/run_long_image_model_compare.py --image-id 13401615760079295
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "评估集" / "聊天截图"
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "long_image_model_compare"

load_dotenv(PROJECT_ROOT / ".env")

# 长图测试图片（默认就那一张）
DEFAULT_LONG_IMAGE_IDS = ["13401615760079295"]

MODELS = {
    "qwen-vl-plus": {
        "label": "qwen-vl-plus（当前长图基线）",
        "model": "qwen-vl-plus",
        "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "qwen3-vl-plus": {
        "label": "qwen3-vl-plus（新候选）",
        "model": "qwen3-vl-plus",
        "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
}


async def run_with_model(image_bytes: bytes, model_key: str) -> dict:
    """用指定模型跑完整长图 pipeline，返回结果。"""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "agent_impl"))
    from utils.image_processor import ImageProcessor

    cfg = MODELS[model_key]
    processor = ImageProcessor()

    # 临时覆盖长图 OCR 配置
    processor.long_chat_ocr_api_key = cfg["api_key"]
    processor.long_chat_ocr_base_url = cfg["base_url"]
    processor.long_chat_ocr_model = cfg["model"]

    t0 = time.monotonic()
    result = await processor._process_long_private_chat_with_dedicated_ocr(image_bytes)
    elapsed_ms = round((time.monotonic() - t0) * 1000, 0)

    return {
        "model_key": model_key,
        "label": cfg["label"],
        "success": result.get("success", False),
        "text": result.get("text", ""),
        "error": result.get("error"),
        "elapsed_ms": elapsed_ms,
    }


def count_rows(text: str) -> int:
    count = 0
    for line in text.splitlines():
        line = line.strip()
        if (
            line.startswith("|")
            and "| :---" not in line
            and "| 发送者" not in line
            and line.count("|") >= 4
        ):
            count += 1
    return count


def first_n_rows(text: str, n: int = 5) -> list[str]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if (
            line.startswith("|")
            and "| :---" not in line
            and "| 发送者" not in line
            and line.count("|") >= 4
        ):
            rows.append(line)
            if len(rows) >= n:
                break
    return rows


def build_report(image_id: str, results: list[dict]) -> str:
    lines = [
        "# 长图私聊截图 — 切片 pipeline 模型对比报告",
        "",
        f"- 图片: `{image_id}`",
        f"- 生成时间: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "## 对比结果",
        "",
    ]
    for r in results:
        lines += [
            f"### {r['label']}",
            f"- 状态: {'✅ 成功' if r['success'] else '❌ 失败'}",
            f"- 耗时: `{r['elapsed_ms']}ms`",
            f"- 提取行数: `{count_rows(r['text'])}`",
            "",
            "#### 前 10 条消息",
            "",
            "| 发送者 | 内容 | 时间戳 |",
            "| --- | --- | --- |",
        ]
        if r["success"]:
            for row in first_n_rows(r["text"], 10):
                lines.append(row.rsplit("|", 1)[0] + "|")  # 去掉序号列
        else:
            lines.append(f"| ❌ | {r['error']} |  |")
        lines.append("")

    # 完整输出
    lines += ["## 完整输出对比", ""]
    for r in results:
        lines += [
            f"### {r['label']} — 完整输出",
            "",
            "```",
            r["text"][:3000] if r["success"] else f"ERROR: {r['error']}",
            "```",
            "",
        ]
    return "\n".join(lines)


async def main_async(image_ids: list[str]) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / f"long_compare_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    for image_id in image_ids:
        image_path = None
        for suffix in (".jpeg", ".jpg", ".png", ".webp"):
            p = DATASET_DIR / f"{image_id}{suffix}"
            if p.exists():
                image_path = p
                break
        if not image_path:
            print(f"[WARN] 找不到图片: {image_id}", file=sys.stderr)
            continue

        image_bytes = image_path.read_bytes()
        print(f"\n[INFO] 图片: {image_path.name} ({len(image_bytes)//1024}KB)")

        all_results = []
        for model_key in MODELS:
            print(f"[RUN ] {model_key} ...")
            result = await run_with_model(image_bytes, model_key)
            rows = count_rows(result["text"])
            print(f"[DONE] {model_key}: {'✅' if result['success'] else '❌'} | {rows}行 | {result['elapsed_ms']}ms")
            if result["success"]:
                for row in first_n_rows(result["text"], 3):
                    print(f"       {row}")
            all_results.append(result)

        # 保存
        json_path = run_dir / f"{image_id}_compare.json"
        md_path = run_dir / f"{image_id}_compare.md"
        json_path.write_text(
            json.dumps(
                {"image_id": image_id, "results": all_results},
                ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        md_path.write_text(build_report(image_id, all_results), encoding="utf-8")
        print(f"\n[OUT ] {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-id", action="append", default=[], metavar="ID")
    args = parser.parse_args()
    ids = args.image_id or DEFAULT_LONG_IMAGE_IDS
    asyncio.run(main_async(ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
