"""Onboarding v2 · 合一分析节点（LLM 节点①）

一次 vision LLM 调用，同时输出：
  - `skip_rules`：题库 A1-A5 的筛题决策（SkipRule）
  - `first_hook`：1-3 句的「判断 + 悬念」开场钩子

策略：
  1. 读 `prompts/analyze.md` 作为 system prompt，把题库 A1-A5 **动态拼接**到 prompt（不硬编码）
  2. user 消息：`free_text` + OCR 摘要 + 图片（OpenAI 多模态格式，image_url 直传原图 URL）
  3. LLM 输出 JSON，用 `AnalyzeResponse.model_validate` 严格校验
  4. 任何环节失败（LLM 超时 / JSON 解析失败 / schema 校验失败 / 题号缺失）→ 走降级 payload

降级 payload：
  - `skip_rules`：A1-A5 全部 `skip=False`，其他字段 null（前端按默认流程渲染全部 5 题）
  - `first_hook`：兜底文案「先把情况说得更细一些，我再帮你判断」

对齐 `API_CONTRACT.md §2` 的降级行为。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config import get_onboarding_vision_llm
from onboarding_v2.question_bank import QUESTION_BANK, list_question_ids
from onboarding_v2.schemas import AnalyzeRequest, AnalyzeResponse, FirstHook, SkipRule

# 可筛题的题号：A0 是性别题（不做筛题），仅 A1-A5 参与 analyze 的 skip_rules
_SKIPPABLE_QUESTION_IDS = [
    qid for qid in list_question_ids() if qid != "A0"
]

logger = logging.getLogger(__name__)


# ---------- 常量 ----------

# prompt 相对本文件的路径：onboarding_v2/prompts/analyze.md
_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "analyze.md"
)

# 最长等待时间（秒）。v2 结构化 FirstHook 输出明显变长（300+ 字），豆包实测 60-90s 常态。
# 默认拉到 120s；API_CONTRACT 如需收紧可通过 env 覆盖。
_LLM_TIMEOUT_SECONDS = float(os.getenv("ONBOARDING_ANALYZE_TIMEOUT", "120"))

# 降级钩子文案：与 hooks.py 的 summary_template 语气一致，但不触发题后模板替换。
# 注：now returns a FirstHook object (see `_build_fallback_first_hook`).
_FALLBACK_FIRST_HOOK_TITLE = "我先接住你的描述——细节再对一轮，我才好给专业诊断。"
_FALLBACK_FIRST_HOOK_BODY = (
    "你愿意把这段感受写出来，说明你心里有个结没打开。我想把你提到的细节一条条对准，再下判断，"
    "免得我说错、让你白走一趟。接下来我会用 5 道题把场景、关系、你真正想解决的问题分清楚。"
)


# ---------- 公共 API ----------


async def run_analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """合一分析入口。

    任何内部异常都不会向上抛，而是返回降级 `AnalyzeResponse`，
    保证 HTTP 层永远 200（对齐契约「不阻断用户流程」的降级原则）。
    """
    # 带一次重试：GLM-4.6V 在并发或长 prompt 场景下偶尔返回空 tool_calls+空 content，
    # 重试一次通常就能拿到稳定结构化输出
    last_error: str | None = None
    for attempt in (1, 2):
        try:
            llm_output = await asyncio.wait_for(
                _invoke_llm(request),
                timeout=_LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[onboarding_v2.analyze] attempt=%s LLM timeout after %ss",
                attempt,
                _LLM_TIMEOUT_SECONDS,
            )
            last_error = "timeout"
            continue
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[onboarding_v2.analyze] attempt=%s LLM invocation failed: %s",
                attempt,
                exc,
            )
            last_error = str(exc)
            continue

        try:
            if isinstance(llm_output, dict):
                return _validate_response_dict(llm_output)
            return _parse_and_validate(str(llm_output))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[onboarding_v2.analyze] attempt=%s parse/validate failed (%s); "
                "raw_preview=%r",
                attempt,
                exc,
                (str(llm_output) if llm_output else "")[:300],
            )
            last_error = str(exc)
            # 继续下一次 attempt

    logger.warning(
        "[onboarding_v2.analyze] exhausted retries; last_error=%s; falling back",
        last_error,
    )
    return _build_fallback_response()


# ---------- Prompt 组装 ----------


def _load_system_prompt() -> str:
    """加载 analyze.md 并把 `{question_bank_block}` 替换为动态题库片段。"""
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{question_bank_block}", _build_question_bank_block())


def _build_question_bank_block() -> str:
    """把 QUESTION_BANK 渲染成 prompt 可读的文本片段。

    不硬编码题库内容到 prompt 文件，避免题库更新时 prompt 漂移。
    """
    lines: list[str] = []
    for qid in _SKIPPABLE_QUESTION_IDS:
        q = QUESTION_BANK[qid]
        q_type = q.get("type", "single_choice")
        multi = "多选" if q.get("allow_multi") else "单选"
        lines.append(f"## {qid}（{multi}，{q_type}）")
        lines.append(f"题干：{q['question']}")
        lines.append("选项：")
        for opt in q.get("options", []):
            flags = []
            if opt.get("is_exclusive"):
                flags.append("互斥")
            if opt.get("allow_free_input"):
                flags.append("可自由输入")
            suffix = f"（{'+'.join(flags)}）" if flags else ""
            lines.append(f"  - {opt['id']}. {opt['label']}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _build_user_message_content(request: AnalyzeRequest) -> list[dict[str, Any]]:
    """组装 OpenAI/BigModel 多模态 content 数组。

    - 前面一段文本：自由描述 + 输出结构指令
    - 后面逐张追加 image_url 块（原图 URL 直传，vision 模型自行理解）

    注：analyze 节点直接吃图，**不再拼 OCR 文本**——OCR 只留给 report 节点。
    `AnalyzeRequest.ocr_texts` 字段保留但本函数忽略（向后兼容）。
    """
    text_parts: list[str] = []
    text_parts.append("【用户自由描述】")
    text_parts.append(request.free_text.strip())

    text_parts.append("")
    text_parts.append(
        "【聊天截图】请直接观察下方附带的截图内容（对话双方、关键情绪、"
        "时间节奏、是否有被拒绝/冷处理等），不要依赖外部 OCR。"
    )

    text_parts.append("")
    text_parts.append(
        "请严格按系统指令的 JSON 结构输出，包含 A1/A2/A3/A4/A5 全部 5 条 "
        "skip_rules 和一条 first_hook。"
    )

    content: list[dict[str, Any]] = [
        {"type": "text", "text": "\n".join(text_parts)}
    ]

    # 追加图片引用。对于本地 URL（upload-screenshot 返回的 supabase 公开 URL 或其他
    # http(s) 链接），直接塞给 vision 模型；模型侧会自行抓取。
    for url in request.image_urls or []:
        if not url or not isinstance(url, str):
            continue
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": url},
            }
        )

    return content


# ---------- LLM 调用 ----------


async def _invoke_llm(request: AnalyzeRequest) -> dict | str:
    """调用智谱 BigModel glm-4.6v（onboarding vision 旗舰）。

    策略：优先 tool_choice=auto 让 GLM 自行决定结构化输出；如果返回 tool_calls 有效
    dict，直接取 args；否则退回文本（文本路径在 run_analyze 里走 JSON 解析兜底）。

    说明：
    - 原本尝试过 tool_choice=force（指定 name），但 GLM-4.6V 在超长 system prompt
      + 强制 tool_choice 组合下经常思考后不调用工具（finish=stop, content='\\n'）。
      改为 auto 后模型会自然地用 tool_call，格式遵循远好于纯 JSON 文本。
    - 任何意外（schema 绑定失败、模型吐文本）都回退到旧 JSON 文本 parse 路径。
    """
    system_prompt = _load_system_prompt()
    user_content = _build_user_message_content(request)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ]

    # 温度 0.3：结构稳定的同时保留首发钩子文案的表达变化空间
    llm = get_onboarding_vision_llm(temperature=0.3)

    # 用 auto 鼓励 tool call 但不强制（规避 GLM-4.6V 长 prompt + 强制 tool_choice 的 bug）
    try:
        llm_with_tool = llm.bind_tools([AnalyzeResponse])
    except TypeError:
        from langchain_core.utils.function_calling import convert_to_openai_tool

        llm_with_tool = llm.bind_tools([convert_to_openai_tool(AnalyzeResponse)])

    response = await llm_with_tool.ainvoke(messages)

    # 优先路径：模型调用了工具
    tool_calls = getattr(response, "tool_calls", None) or []
    if tool_calls:
        first = tool_calls[0]
        args = first.get("args") if isinstance(first, dict) else getattr(first, "args", None)
        if isinstance(args, dict):
            logger.info(
                "[onboarding_v2.analyze] LLM tool_call ok: keys=%s",
                sorted(args.keys()),
            )
            return args
        logger.warning(
            "[onboarding_v2.analyze] tool_call args 不是 dict（type=%s），"
            "尝试 fallback 到文本解析",
            type(args).__name__,
        )

    # 兜底路径：模型直接吐文本
    content = getattr(response, "content", "")
    if isinstance(content, list):
        merged: list[str] = []
        for part in content:
            if isinstance(part, str):
                merged.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    merged.append(text)
        content = "".join(merged)
    if not isinstance(content, str):
        content = str(content)

    logger.info(
        "[onboarding_v2.analyze] LLM fallback text: len=%d preview=%r",
        len(content),
        content[:200],
    )
    return content


def _validate_response_dict(obj: dict[str, Any]) -> AnalyzeResponse:
    """校验 tool_call 返回的 dict，确保 skip_rules 覆盖 A1-A5 且能 model_validate。"""
    skip_rules = obj.get("skip_rules")
    if not isinstance(skip_rules, dict):
        raise ValueError("tool_call args: skip_rules missing or not a dict")
    expected = set(_SKIPPABLE_QUESTION_IDS)
    got = set(skip_rules.keys())
    missing = expected - got
    if missing:
        raise ValueError(
            f"tool_call args: skip_rules missing question ids: {sorted(missing)}"
        )
    return AnalyzeResponse.model_validate(obj)


# ---------- JSON 解析 ----------


def _extract_json_object(raw: str) -> dict[str, Any]:
    """从模型输出里抠出 JSON 对象。

    尝试顺序：
    1. 直接 `json.loads`
    2. 剥掉 ```json ... ``` / ``` ... ``` 代码块后再 `json.loads`
    3. 取第一个 `{` 到最后一个 `}` 之间的切片再 `json.loads`
    全部失败抛 ValueError。
    """
    if not raw or not raw.strip():
        raise ValueError("empty LLM response")

    text = raw.strip()

    # 路径 1：直接解析
    try:
        return _ensure_dict(json.loads(text))
    except Exception:
        pass

    # 路径 2：代码块剥离
    fence_match = re.search(r"```(?:json|JSON)?\s*(.+?)```", text, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return _ensure_dict(json.loads(candidate))
        except Exception:
            pass

    # 路径 3：首尾大括号截取
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        return _ensure_dict(json.loads(candidate))

    raise ValueError("no JSON object found in LLM response")


def _ensure_dict(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"expected JSON object, got {type(obj).__name__}")
    return obj


def _parse_and_validate(raw_text: str) -> AnalyzeResponse:
    """解析 LLM 输出并做严格 schema 校验。"""
    obj = _extract_json_object(raw_text)

    # 校验 skip_rules 键齐整 —— schema 层的 dict[str, SkipRule] 本身不强制五个题号，
    # 但契约要求必须覆盖 A1-A5，缺一就走降级。
    skip_rules = obj.get("skip_rules")
    if not isinstance(skip_rules, dict):
        raise ValueError("skip_rules missing or not a dict")
    expected = set(_SKIPPABLE_QUESTION_IDS)
    got = set(skip_rules.keys())
    missing = expected - got
    if missing:
        raise ValueError(f"skip_rules missing question ids: {sorted(missing)}")

    return AnalyzeResponse.model_validate(obj)


# ---------- 降级 ----------


def _build_fallback_first_hook() -> FirstHook:
    """结构完整的降级 FirstHook：字段齐全、evidences 占位、不触发前端渲染 bug。"""
    return FirstHook(
        verdict_tag="先补信息",
        verdict_color="violet",
        title=_FALLBACK_FIRST_HOOK_TITLE,
        body=_FALLBACK_FIRST_HOOK_BODY,
        highlights=["信息不足", "待细化"],
        evidences=[
            "你说的这段情况我已经收到——具体细节我想通过接下来的补充题再对一次。",
            "我不想在信息不够时给你武断的结论——宁可多问一题，也不想误判。",
        ],
        call_to_action="接下来的 5 道题每题 15 秒——答完我再给你一份完整诊断。",
    )


def _build_fallback_response() -> AnalyzeResponse:
    """契约规定的降级 payload：5 题全不跳 + 结构化兜底钩子。"""
    skip_rules = {
        qid: SkipRule(skip=False, reason=None, preselect=None, rewrite=None)
        for qid in _SKIPPABLE_QUESTION_IDS
    }
    return AnalyzeResponse(
        skip_rules=skip_rules,
        first_hook=_build_fallback_first_hook(),
    )
