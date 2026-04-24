"""
Onboarding v2 · LLM 节点③:免费诊断报告生成。

入口:`run_report(request) -> DiagnosisReport`
- 基于自由描述 + 截图 OCR + 题库答卷,一次 LLM 调用生成完整报告
- 强制使用 Pydantic strict schema 校验输出,失败自动重试 1 次
- 两次都失败 → 抛 HTTPException(500, REPORT_GENERATION_FAILED),由 FastAPI 层兜底

外部依赖:
- `config.get_llm`:拿默认 LLM 实例(报告是纯文本任务,截图已经 OCR 过了)
- `onboarding_v2.schemas`:请求/响应 schema
- `onboarding_v2.question_bank`:用于把 `answers` 还原成"问题:选项"可读文本
- `prompts/diagnosis_report.md`:system prompt,专家角色 + 输出规范
"""

from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable
from pydantic import ValidationError

from config import get_thinking_llm
from onboarding_v2.question_bank import QUESTION_BANK
from onboarding_v2.schemas import DiagnosisReport, ReportRequest

logger = logging.getLogger(__name__)

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "diagnosis_report.md"
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _load_system_prompt() -> str:
    """读取 system prompt 原文(一次调用读一次,测试里可以 monkeypatch 改)。"""
    return PROMPT_PATH.read_text(encoding="utf-8")


def _generate_report_id() -> str:
    """生成 `CR-{8位十六进制}` 格式的 report_id。"""
    return f"CR-{secrets.token_hex(4).upper()}"


def _render_answers(answers: dict[str, str | list[str]]) -> str:
    """把 `{"A3": ["A"], "A5": "C"}` 还原成可读的"问题:选项文案"。

    - 题号不在题库里的直接跳过(防御式编程)
    - 选项 id 匹配不上的标"未知选项",不报错
    - 单选/多选都处理
    """
    if not answers:
        return "(用户未回答任何题目——全部被 skip 或答卷缺失)"

    lines: list[str] = []
    for qid in ("A1", "A2", "A3", "A4", "A5"):
        if qid not in answers:
            continue
        q = QUESTION_BANK.get(qid)
        if not q:
            continue

        chosen = answers[qid]
        chosen_ids: list[str] = [chosen] if isinstance(chosen, str) else list(chosen)

        options_map = {o["id"]: o["label"] for o in q["options"]}
        chosen_labels = [
            f"[{cid}] {options_map.get(cid, '未知选项')}" for cid in chosen_ids
        ]

        lines.append(
            f"- {qid} 「{q['question']}」\n  用户选择:{'、'.join(chosen_labels)}"
        )

    return "\n".join(lines) if lines else "(所有答题键都不在题库里)"


def _build_user_prompt(request: ReportRequest) -> str:
    """拼装 user prompt:自由描述 + OCR + 答卷。"""
    free_text = (request.free_text or "").strip() or "(用户未填写自由描述)"

    ocr_blocks = [t.strip() for t in request.ocr_texts if t and t.strip()]
    if ocr_blocks:
        ocr_section = "\n\n---\n\n".join(
            f"【截图 {i + 1} OCR】\n{t}" for i, t in enumerate(ocr_blocks)
        )
    else:
        ocr_section = "(无截图或 OCR 全部为空)"

    answer_section = _render_answers(request.answers)

    return (
        "# 用户自由描述\n"
        f"{free_text}\n\n"
        "# 截图 OCR 文本\n"
        f"{ocr_section}\n\n"
        "# 题库答卷\n"
        f"{answer_section}\n\n"
        "请通过 `DiagnosisReport` 工具提交诊断报告(tool_call)。"
        "不要输出自然语言文字、不要代码块,直接调用工具。"
    )


def _extract_text_content(raw: Any) -> str:
    """从 LLM 原始响应里取出可 JSON 解析的文本。

    兼容:
    - BaseMessage(AIMessage):`raw.content` 是 str 或 list[dict]
    - str:直接返回
    - dict:尝试 `content` 或整体 json 序列化
    """
    if isinstance(raw, str):
        return raw
    content = getattr(raw, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # langchain 多模态消息:content 是 list[dict],取所有 text 片段
        parts: list[str] = []
        for blk in content:
            if isinstance(blk, dict) and isinstance(blk.get("text"), str):
                parts.append(blk["text"])
            elif isinstance(blk, str):
                parts.append(blk)
        return "\n".join(parts)
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    # 兜底:直接 str()
    return str(raw)


def _strip_code_fence(text: str) -> str:
    """如果 LLM 顽固地用 ```json 包裹,剥掉外层代码块。"""
    s = (text or "").strip()
    if s.startswith("```"):
        # 去掉首行 ```xxx
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1 :]
        # 去掉结尾 ```
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _validate_report_payload(payload: Any, *, report_id: str) -> DiagnosisReport:
    """把任意 payload(dict / BaseModel / str 的 JSON)严格校验为 DiagnosisReport。

    - 若是 BaseModel 实例:转 dict 后覆盖 report_id,重新校验
    - 若是 dict:覆盖 report_id,model_validate
    - 若是 str:先 json.loads(支持去除 ```json 代码块),再走 dict 分支
    - 任何失败都往外抛 ValidationError / ValueError / json.JSONDecodeError,由上层 catch
    """
    if isinstance(payload, DiagnosisReport):
        data = payload.model_dump()
    elif isinstance(payload, dict):
        data = dict(payload)
    elif isinstance(payload, str):
        stripped = _strip_code_fence(payload)
        data = json.loads(stripped)
        if not isinstance(data, dict):
            raise ValueError("LLM JSON 顶层不是对象")
    else:
        # 其他类型(例如带 content 属性的消息):尝试提取文本 + json.loads
        text = _extract_text_content(payload)
        stripped = _strip_code_fence(text)
        data = json.loads(stripped)
        if not isinstance(data, dict):
            raise ValueError("LLM 输出 JSON 顶层不是对象")

    # 统一覆盖为后端生成的 report_id(防止 LLM 乱编或遗漏)
    data["report_id"] = report_id

    return DiagnosisReport.model_validate(data)


async def _call_llm_once(
    system_prompt: str, user_prompt: str, *, report_id: str
) -> DiagnosisReport:
    """单次 LLM 调用 + schema 校验;失败直接抛异常,由 `run_report` 做重试。

    实现策略:**DeepSeek v3.2 thinking + tool calling**。
    - `get_thinking_llm()` 返回启用 `extra_body={"thinking":{"type":"enabled"}}` 的
      ChatOpenAI 实例(deepseek-chat + thinking mode)
    - `bind_tools([DiagnosisReport], tool_choice=...)` 强制模型通过 tool_call 提交报告,
      避免 JSON mode 的 schema 遵循弱点(豆包经常返回不合 schema 的 JSON 文本)
    - 从 `AIMessage.tool_calls[0]["args"]` 读出结构化参数,直接 `DiagnosisReport.model_validate`
    - tool_calls 为空 / args 非 dict / 校验失败 → 抛 ValueError/ValidationError,
      交给 `run_report` 的重试循环处理
    """
    llm = get_thinking_llm(temperature=0.6)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    # 绑定 DiagnosisReport 工具(tool_choice=auto)。
    #
    # 注:DeepSeek thinking 模式(`extra_body={"thinking":{...}}`)在 DeepSeek 服务端会
    # 走 reasoner 路径,而 `deepseek-reasoner` 不接受强制 tool_choice=function,会报
    # "does not support this tool_choice"。所以这里只 bind 工具、不强制 choice,
    # 依赖 prompt 硬约束("必须调用 DiagnosisReport 工具")让模型自主调用。
    try:
        llm_with_tool = llm.bind_tools([DiagnosisReport])
    except TypeError:
        from langchain_core.utils.function_calling import convert_to_openai_tool

        llm_with_tool = llm.bind_tools([convert_to_openai_tool(DiagnosisReport)])

    if hasattr(llm_with_tool, "ainvoke"):
        response = await llm_with_tool.ainvoke(messages)
    else:
        response = llm_with_tool.invoke(messages)

    tool_calls = getattr(response, "tool_calls", None) or []
    if not tool_calls:
        raise ValueError(
            "LLM 未调用 DiagnosisReport 工具(thinking+tool_call 路径失败, "
            "response_content=%r)" % (getattr(response, "content", ""),)[:160]
        )

    args = tool_calls[0].get("args")
    if not isinstance(args, dict):
        raise ValueError(
            "LLM tool_call args 不是 dict(type=%s)" % type(args).__name__
        )

    return _validate_report_payload(args, report_id=report_id)


# --------------------------------------------------------------------------- #
# 对外入口
# --------------------------------------------------------------------------- #


@traceable(name="onboarding_report", run_type="chain")
async def run_report(request: ReportRequest) -> DiagnosisReport:
    """生成诊断报告(带 1 次重试,失败抛 HTTPException 500)。

    Args:
        request: 题库答卷 + 自由描述 + OCR 文本

    Returns:
        完整的 `DiagnosisReport`(已通过 Pydantic strict 校验)

    Raises:
        HTTPException(status_code=500, detail="REPORT_GENERATION_FAILED"):
            LLM 连续两次调用失败 / schema 校验不过 / 其他未捕获异常
    """
    system_prompt = _load_system_prompt()
    user_prompt = _build_user_prompt(request)
    report_id = _generate_report_id()

    last_error: Exception | None = None
    for attempt in (1, 2):
        try:
            report = await _call_llm_once(
                system_prompt, user_prompt, report_id=report_id
            )
            if attempt == 2:
                logger.info("run_report 第二次尝试成功 (session=%s)", request.session_id)
            return report
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_error = e
            logger.warning(
                "run_report 尝试 %s/2 失败 (session=%s):%s",
                attempt,
                request.session_id,
                e,
            )
        except HTTPException:
            raise  # 已经是 HTTPException,别包第二层
        except Exception as e:  # noqa: BLE001 - LLM 调用可能抛各种 provider 异常
            last_error = e
            logger.warning(
                "run_report 尝试 %s/2 调用 LLM 异常 (session=%s):%s",
                attempt,
                request.session_id,
                e,
            )

    logger.error(
        "run_report 两次重试全部失败 (session=%s),最后一次错误:%s",
        request.session_id,
        last_error,
    )
    raise HTTPException(
        status_code=500,
        detail="REPORT_GENERATION_FAILED",
    )
