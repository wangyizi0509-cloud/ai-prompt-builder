#!/usr/bin/env python3
"""
短图私聊截图 — 多模型直接对比脚本

不依赖 FastAPI 服务，直接调用各视觉模型 API，用同一套 prompt 对比：
  1. GLM-4.6V-FlashX       (当前生产基线, 智谱 BigModel)
  2. GLM-4.1V-Thinking-FlashX (新候选,  智谱 BigModel, 带思维链)
  3. qwen3-vl-plus           (新候选,  阿里 DashScope)

用法示例
--------
# 测默认 5 张 sender_flip 问题图：
python scripts/run_short_image_model_compare.py

# 测指定图片：
python scripts/run_short_image_model_compare.py \
    --image-id 5055499a75d867a5bd4059db5caf009e \
    --image-id 6710ebfaed07bd1d9d63be9a0d2f2665

# 测 failure_pool 子集：
python scripts/run_short_image_model_compare.py --subset failure_pool

# 只测某几个模型：
python scripts/run_short_image_model_compare.py --models glm-baseline,qwen3
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from PIL import Image

# ── 路径设置 ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "评估集" / "聊天截图"
OUTPUT_ROOT = PROJECT_ROOT / "artifacts" / "short_image_model_compare"
PROMPT_PATH = PROJECT_ROOT / "agent_impl" / "prompts" / "screenshots" / "private_chat_screenshot.md"

load_dotenv(PROJECT_ROOT / ".env")

# ── 默认测试集（5 张 sender_flip 重点样本）─────────────────────────────────
DEFAULT_IMAGE_IDS = [
    "5055499a75d867a5bd4059db5caf009e",
    "6710ebfaed07bd1d9d63be9a0d2f2665",
    "a86d33b681fc3d6ad56e0e4e0e735ee2",
    "e33421e6c755bd986ed8fa91bfeae3b1",
    "ec002086bfbb35857c2e2ec51b0ba279",
]

FAILURE_POOL_IMAGE_IDS = [
    "0923859fb43467198c8a301a24c284cd",
    "13401615760079295",
    "5055499a75d867a5bd4059db5caf009e",
    "6710ebfaed07bd1d9d63be9a0d2f2665",
    "9354d39f7091f12e92f61955039317b8",
    "a86d33b681fc3d6ad56e0e4e0e735ee2",
    "b62c3f3ba60a0bf425e4656df896e13f",
    "c814a17b460651030fdf2c907f257e50",
    "ccb0692709b04223534582eca2f86c55",
    "e33421e6c755bd986ed8fa91bfeae3b1",
    "eec1408930a9193ce1cdac57126fe8df",
]

ALL_IMAGE_IDS: list[str] | None = None  # None = 运行时扫描目录

SUBSETS: dict[str, list[str] | None] = {
    "default": DEFAULT_IMAGE_IDS,
    "failure_pool": FAILURE_POOL_IMAGE_IDS,
    "all": None,  # 运行时扫描整个 DATASET_DIR
}

# ── 模型配置 ──────────────────────────────────────────────────────────────────
# enable_thinking=True  → 不注入 "thinking": {"type": "disabled"}，让模型推理
# enable_thinking=False → 注入 disable，与当前生产行为一致
MODEL_CONFIGS: dict[str, dict[str, Any]] = {
    "glm-baseline": {
        "label": "GLM-4.6V-FlashX (当前基线)",
        "model_name": "GLM-4.6V-FlashX",
        "api_key_env": "IMAGE_TYPE_DETECT_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "max_tokens": 2000,
        "enable_thinking": False,  # 与生产保持一致
    },
    "glm-thinking": {
        "label": "GLM-4.1V-Thinking-FlashX (新候选)",
        "model_name": "GLM-4.1V-Thinking-FlashX",
        "api_key_env": "IMAGE_TYPE_DETECT_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "max_tokens": 2000,
        "enable_thinking": True,  # 开启思维链，这正是它的差异化能力
    },
    "qwen3": {
        "label": "qwen3-vl-plus (新候选)",
        "model_name": "qwen3-vl-plus",
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "max_tokens": 2000,
        "enable_thinking": False,
    },
}

# ── 图片尺寸上限（与生产 OCR 路径保持一致）──────────────────────────────────
OCR_MAX_EDGE = int(os.getenv("IMAGE_OCR_MAX_EDGE", "3000"))

# 短图判定阈值（超过此高度才算长图，不在本脚本测试范围内）
LONG_CHAT_MIN_HEIGHT = int(os.getenv("IMAGE_LONG_CHAT_MIN_HEIGHT", "5000"))

# ── Sender 问题自动检测 ────────────────────────────────────────────────────────
ILLEGAL_SENDER_PATTERNS = [
    r"发送者\s*1", r"发送者\s*2",
    r"\|\s*对方\s*\|", r"\|\s*本人\s*\|",
    r"左侧.*用户", r"右侧.*Crush",
    r"\|\s*用户1\s*\|", r"\|\s*用户2\s*\|",
    r"\|\s*A\s*\|", r"\|\s*B\s*\|",
]
TIME_SEP_AS_MESSAGE = re.compile(
    r"\|\s*(昨天|今天|星期[一二三四五六日]|\d{1,2}:\d{2}|以下是最新消息)\s*\|"
)


def detect_output_issues(text: str) -> list[str]:
    """从模型输出文本里自动检测常见问题标签。"""
    issues: list[str] = []
    if not text:
        issues.append("empty_output")
        return issues

    # 非法 sender
    for pat in ILLEGAL_SENDER_PATTERNS:
        if re.search(pat, text):
            issues.append("illegal_sender")
            break

    # 时间分隔线误当消息
    if TIME_SEP_AS_MESSAGE.search(text):
        issues.append("time_sep_as_message")

    # 是否包含正确的 sender
    has_crush = "Crush" in text
    has_user = "用户" in text
    if not has_crush and not has_user:
        issues.append("no_valid_sender")
    elif not has_crush:
        issues.append("missing_crush_sender")
    elif not has_user:
        issues.append("missing_user_sender")

    # 输出是否有表格结构
    if "| 发送者 |" not in text and "|发送者|" not in text:
        issues.append("no_table_header")

    return issues


# ── 图片处理 ──────────────────────────────────────────────────────────────────

def load_and_resize_image(image_path: Path, max_edge: int) -> tuple[bytes, str]:
    """读取图片，按最长边缩放，返回 (bytes, mime_type)。"""
    with image_path.open("rb") as fh:
        raw = fh.read()

    # 检测 MIME
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif raw[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        mime = "image/jpeg"

    if max_edge <= 0:
        return raw, mime

    img = Image.open(image_path)
    w, h = img.size
    if max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        from io import BytesIO
        buf = BytesIO()
        fmt = "PNG" if mime == "image/png" else "JPEG"
        img.save(buf, format=fmt, quality=92)
        return buf.getvalue(), mime

    return raw, mime


def build_data_url(image_bytes: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"


# ── API 调用 ──────────────────────────────────────────────────────────────────

async def call_vision_model(
    *,
    model_cfg: dict[str, Any],
    prompt: str,
    image_bytes: bytes,
    mime: str,
    client: httpx.AsyncClient,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """向单个模型发请求，返回结构化结果。"""
    api_key = os.getenv(model_cfg["api_key_env"], "").strip()
    if not api_key:
        return {
            "success": False,
            "text": "",
            "thinking": "",
            "latency_ms": 0.0,
            "error": f"API key 未配置: {model_cfg['api_key_env']}",
        }

    data_url = build_data_url(image_bytes, mime)
    payload: dict[str, Any] = {
        "model": model_cfg["model_name"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": model_cfg["max_tokens"],
    }
    if not model_cfg.get("enable_thinking", True):
        payload["thinking"] = {"type": "disabled"}

    base_url = model_cfg["base_url"].rstrip("/")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{base_url}/chat/completions"

    t0 = time.monotonic()
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        return {
            "success": False,
            "text": "",
            "thinking": "",
            "latency_ms": elapsed_ms,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:300]}",
        }
    except Exception as e:
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        return {
            "success": False,
            "text": "",
            "thinking": "",
            "latency_ms": elapsed_ms,
            "error": f"{type(e).__name__}: {e}",
        }

    choices = data.get("choices") or []
    if not choices:
        return {
            "success": False,
            "text": "",
            "thinking": "",
            "latency_ms": elapsed_ms,
            "error": "返回缺少 choices",
        }

    message = choices[0].get("message", {})
    content = message.get("content") or ""
    # GLM-4.1V-Thinking 把推理过程放在 reasoning_content 里
    thinking_text = message.get("reasoning_content") or ""

    return {
        "success": True,
        "text": content,
        "thinking": thinking_text,
        "latency_ms": elapsed_ms,
        "error": None,
    }


# ── 单张图片的全模型评测 ──────────────────────────────────────────────────────

async def run_one_image(
    image_path: Path,
    prompt: str,
    model_ids: list[str],
    client: httpx.AsyncClient,
    timeout: float,
) -> dict[str, Any]:
    """并发跑所有模型，返回该图片的完整结果。"""
    image_bytes, mime = load_and_resize_image(image_path, OCR_MAX_EDGE)

    # 判断是否短图（超过阈值算长图，本脚本聚焦短图）
    img = Image.open(image_path)
    width, height = img.size
    is_long = height >= LONG_CHAT_MIN_HEIGHT

    tasks = {
        model_id: asyncio.create_task(
            call_vision_model(
                model_cfg=MODEL_CONFIGS[model_id],
                prompt=prompt,
                image_bytes=image_bytes,
                mime=mime,
                client=client,
                timeout=timeout,
            )
        )
        for model_id in model_ids
    }
    results = {mid: await t for mid, t in tasks.items()}

    model_results = {}
    for model_id, result in results.items():
        issues = detect_output_issues(result["text"]) if result["success"] else ["api_error"]
        model_results[model_id] = {
            **result,
            "issues": issues,
            "has_issues": bool(issues),
        }

    return {
        "image_id": image_path.stem,
        "image_path": str(image_path),
        "width": width,
        "height": height,
        "is_long_chat": is_long,
        "models": model_results,
    }


# ── 报告生成 ──────────────────────────────────────────────────────────────────

def _issue_badge(issues: list[str]) -> str:
    if not issues:
        return "✅ 无问题"
    critical = {"illegal_sender", "no_valid_sender", "missing_crush_sender", "missing_user_sender", "api_error"}
    level = "🔴" if any(i in critical for i in issues) else "🟡"
    return f"{level} {', '.join(issues)}"


def build_markdown_report(
    run_id: str,
    image_results: list[dict[str, Any]],
    model_ids: list[str],
    elapsed_total_s: float,
) -> str:
    lines: list[str] = [
        "# 短图私聊截图 — 多模型对比报告",
        "",
        f"- Run ID: `{run_id}`",
        f"- 生成时间: `{datetime.now(timezone.utc).isoformat()}`",
        f"- 总耗时: `{elapsed_total_s:.1f}s`",
        f"- 图片数: `{len(image_results)}`",
        f"- 模型数: `{len(model_ids)}`",
        "",
        "## 模型配置",
        "",
    ]
    for mid in model_ids:
        cfg = MODEL_CONFIGS[mid]
        thinking_flag = "开启" if cfg.get("enable_thinking") else "关闭"
        lines.append(f"- **{mid}**: {cfg['label']}  ")
        lines.append(f"  model=`{cfg['model_name']}`, 思维链=`{thinking_flag}`")
    lines.append("")

    # ── 汇总表 ────────────────────────────────────────────────────────────────
    lines += [
        "## 汇总：各模型问题统计",
        "",
        "| 模型 | 成功数 | 有问题数 | 无问题数 | 平均时延(ms) | 主要问题 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for mid in model_ids:
        cfg = MODEL_CONFIGS[mid]
        successes = [r for r in image_results if r["models"][mid]["success"]]
        has_issue_count = sum(1 for r in image_results if r["models"][mid]["has_issues"])
        clean_count = len(image_results) - has_issue_count
        latencies = [r["models"][mid]["latency_ms"] for r in image_results if r["models"][mid]["success"]]
        avg_lat = round(sum(latencies) / len(latencies), 0) if latencies else 0

        all_issues: list[str] = []
        for r in image_results:
            all_issues.extend(r["models"][mid]["issues"])
        from collections import Counter
        top_issues = ", ".join(f"{k}×{v}" for k, v in Counter(all_issues).most_common(3))

        lines.append(
            f"| {cfg['label']} | {len(successes)}/{len(image_results)} "
            f"| {has_issue_count} | {clean_count} | {avg_lat} | {top_issues or '-'} |"
        )
    lines.append("")

    # ── 逐图对比 ──────────────────────────────────────────────────────────────
    lines.append("## 逐图对比")
    lines.append("")

    for r in image_results:
        iid = r["image_id"]
        lines += [
            f"---",
            f"### 🖼 {iid}",
            f"- 尺寸: `{r['width']}×{r['height']}`",
            f"- 长图: `{r['is_long_chat']}`",
            "",
        ]
        for mid in model_ids:
            cfg = MODEL_CONFIGS[mid]
            mr = r["models"][mid]
            badge = _issue_badge(mr["issues"])
            lines += [
                f"#### [{mid}] {cfg['label']}",
                f"- 状态: {'✅ 成功' if mr['success'] else '❌ 失败'}  |  时延: `{mr['latency_ms']}ms`",
                f"- 问题检测: {badge}",
            ]
            if mr.get("thinking"):
                lines.append(f"- 推理过程（摘要）: `{mr['thinking'][:200]}...`")
            if mr["success"]:
                preview = mr["text"][:600].replace("\n", "\n  ")
                lines += [
                    "- 输出预览:",
                    "",
                    "  ```",
                    f"  {preview}",
                    "  ```",
                ]
            else:
                lines.append(f"- 错误: `{mr['error']}`")
            lines.append("")

    return "\n".join(lines)


# ── 主流程 ────────────────────────────────────────────────────────────────────

def resolve_images(
    dataset_dir: Path,
    image_ids: list[str] | None,
    subset: str | None,
) -> list[Path]:
    # --subset all → 扫描整个目录
    if subset == "all":
        return sorted(
            p for p in dataset_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        )

    if subset and subset in SUBSETS:
        ids = SUBSETS[subset]
    elif image_ids:
        ids = image_ids
    else:
        ids = DEFAULT_IMAGE_IDS

    paths: list[Path] = []
    for iid in ids:
        for suffix in (".jpg", ".jpeg", ".png", ".webp"):
            p = dataset_dir / f"{iid}{suffix}"
            if p.exists():
                paths.append(p)
                break
        else:
            print(f"[WARN] 找不到图片: {iid}", file=sys.stderr)
    return paths


async def run_compare(
    image_ids: list[str] | None,
    subset: str | None,
    model_ids: list[str],
    timeout: float,
    concurrency: int,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"short_model_compare_{stamp}"
    run_dir = OUTPUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    images = resolve_images(DATASET_DIR, image_ids, subset)
    if not images:
        raise RuntimeError(f"没有找到可测试的图片，请检查 {DATASET_DIR}")

    print(f"[INFO] Run ID: {run_id}")
    print(f"[INFO] 图片数: {len(images)}, 模型数: {len(model_ids)}")
    for mid in model_ids:
        print(f"[INFO]   模型: {mid} ({MODEL_CONFIGS[mid]['label']})")

    t_total = time.monotonic()
    async with httpx.AsyncClient() as client:
        sem = asyncio.Semaphore(concurrency)

        async def _bounded(img_path: Path) -> dict[str, Any]:
            async with sem:
                print(f"[RUN ] {img_path.name} ...")
                result = await run_one_image(img_path, prompt, model_ids, client, timeout)
                issues_summary = {
                    mid: result["models"][mid]["issues"]
                    for mid in model_ids
                }
                print(f"[DONE] {img_path.stem} | {issues_summary}")
                return result

        image_results = await asyncio.gather(*[_bounded(p) for p in images])

    elapsed = time.monotonic() - t_total

    # 保存 JSON
    report_data = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_total_s": round(elapsed, 2),
        "model_ids": model_ids,
        "model_configs": {
            mid: {
                "label": MODEL_CONFIGS[mid]["label"],
                "model_name": MODEL_CONFIGS[mid]["model_name"],
                "enable_thinking": MODEL_CONFIGS[mid]["enable_thinking"],
            }
            for mid in model_ids
        },
        "image_count": len(image_results),
        "results": image_results,
    }
    json_path = run_dir / "compare_results.json"
    json_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 保存 Markdown
    md = build_markdown_report(run_id, list(image_results), model_ids, elapsed)
    md_path = run_dir / "compare_report.md"
    md_path.write_text(md, encoding="utf-8")

    print(f"\n[DONE] 耗时 {elapsed:.1f}s")
    print(f"[OUT ] JSON:     {json_path}")
    print(f"[OUT ] Markdown: {md_path}")
    return run_dir


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--image-id",
        action="append",
        default=[],
        metavar="IMAGE_ID",
        help="指定要测试的图片 ID（可多次使用）",
    )
    parser.add_argument(
        "--subset",
        choices=list(SUBSETS.keys()),
        default=None,
        help="使用预定义子集（all=扫描整个数据集目录）",
    )
    parser.add_argument(
        "--models",
        default=",".join(MODEL_CONFIGS.keys()),
        help=f"逗号分隔的模型 ID，可选: {', '.join(MODEL_CONFIGS.keys())}",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="单次 API 超时秒数")
    parser.add_argument("--concurrency", type=int, default=2, help="最大并发图片数")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    model_ids = [m.strip() for m in args.models.split(",") if m.strip()]
    invalid = [m for m in model_ids if m not in MODEL_CONFIGS]
    if invalid:
        print(f"[ERROR] 未知模型 ID: {invalid}，可选: {list(MODEL_CONFIGS.keys())}", file=sys.stderr)
        return 1

    run_dir = asyncio.run(
        run_compare(
            image_ids=args.image_id or None,
            subset=args.subset,
            model_ids=model_ids,
            timeout=args.timeout,
            concurrency=args.concurrency,
        )
    )
    print(json.dumps({"ok": True, "run_dir": str(run_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
