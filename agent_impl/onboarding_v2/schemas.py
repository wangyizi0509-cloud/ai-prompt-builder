"""
Onboarding v2 · Pydantic v2 数据契约

本文件是 onboarding v2 模块的「数据宪法」，定义三个 REST 端点请求/响应
以及诊断报告结构。所有字段都是 Pydantic v2 strict 模式（`extra="forbid"`），
任何额外字段都会直接报错，避免 schema 漂移。

使用方：
  - Agent B（筛题/钩子 LLM 节点）：读 `AnalyzeRequest` / `AnalyzeResponse`
  - Agent C（诊断报告 LLM 节点）：读 `ReportRequest` / `DiagnosisReport`
  - Agent D（后端 REST 层）：导入全部 schema 用于 FastAPI 路由
  - Agent E（前端状态机）：用 TypeScript 类型对齐；JSON 结构以本文件为准
  - Agent F（付费闸门）：读 `DiagnosisReport.locked_teasers`
  - Agent G（main_agent 衔接）：读 `DiagnosisReport.collected_summary`

⚠️ 任何字段新增/修改都会破坏下游 6 个 agent，本文件冻结后不得修改。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------- 通用基类 ----------


class _StrictModel(BaseModel):
    """所有 onboarding v2 schema 的基类：禁止额外字段。"""

    model_config = ConfigDict(extra="forbid")


# ---------- /analyze 端点 ----------


class SkipRule(_StrictModel):
    """单道题（A1-A5）的筛题决策。

    字段语义：
    - `skip`：True 表示自由描述里信息已足够，直接跳过这道题
    - `reason`：给产品经理/日志的解释（例如「用户已提到同事关系」）
    - `preselect`：不跳过但建议预选的选项 id 列表（如 `["A"]`）
    - `rewrite`：不跳过但建议重写题干（例如「表白过了，TA 当时怎么回应？」）
    """

    skip: bool = Field(..., description="是否跳过该题")
    reason: str | None = Field(
        default=None,
        description="跳过/调整的原因，一句话解释。不跳过可为 null。",
    )
    preselect: list[str] | None = Field(
        default=None,
        description="预选的选项 id 列表（例如 ['A']）。无需预选则为 null。",
    )
    rewrite: str | None = Field(
        default=None,
        description="建议重写的题干文本。保留原题干则为 null。",
    )


class AnalyzeRequest(_StrictModel):
    """POST /api/onboarding/analyze 请求体。

    触发时机：用户在自由描述页（Step 2 入口）提交文字 + 截图后立即调用。
    """

    session_id: str = Field(..., description="前端生成的 UUID，会贯穿整个 onboarding。")
    free_text: str = Field(
        ...,
        min_length=5,
        description="用户的自由描述，至少 5 个字符。前端应在提交前校验。",
    )
    image_urls: list[str] = Field(
        default_factory=list,
        description="截图的访问 URL 列表，顺序与 `ocr_texts` 对齐。",
    )
    ocr_texts: list[str] = Field(
        default_factory=list,
        description="每张截图对应的 OCR 文本。如果 OCR 失败传空字符串占位。",
    )


class FirstHook(_StrictModel):
    """首发开场钩子的结构化数据契约（对齐设计稿 page3-opening-hook.jsx）。

    前端字段映射：
    - `verdict_tag` → 顶部大标签 `<Tag tone=verdict_color>`
    - `title`       → 大字判断标题（支持「」/"" 内片段高亮）
    - `body`        → 正文段落（2-3 句）
    - `highlights`  → chips 区的 3 个关键词
    - `evidences`   → "我从你的描述里看到了" 引证列表（每条引用截图原话或自由文本片段）
    - `call_to_action` → 底部"下一步"引导文案
    """

    verdict_tag: str = Field(
        ...,
        min_length=2,
        max_length=8,
        description="3-6 字的标签文案（例如「信号暴露」「关系定义期」「节奏错位」）。",
    )
    verdict_color: Literal["violet", "amber", "red", "green"] = Field(
        default="violet",
        description="标签配色枚举；前端映射 tone。",
    )
    title: str = Field(
        ...,
        min_length=14,
        max_length=48,
        description=(
            "18-32 字的大字判断标题（核心结论）。允许用「」或 \"\" 标注 1-2 个重点短语，"
            "前端会自动高亮。不要用 markdown 加粗。"
        ),
    )
    body: str = Field(
        ...,
        min_length=60,
        max_length=180,
        description="2-3 句、80-120 字的正文段落；先建立判断，再留悬念引出后续补充题。",
    )
    highlights: list[str] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="2-4 个 3-6 字关键词（例如『话题踩雷』『关系定义期』『对方撤回』）。",
    )
    evidences: list[str] = Field(
        ...,
        min_length=2,
        max_length=4,
        description=(
            "2-4 条引证，每条 20-60 字。必须直接引用用户自由文本原句或截图 OCR 原话（用「」或 "" 包住被引用片段），"
            "再附一句解读。禁止自编内容。"
        ),
    )
    call_to_action: str = Field(
        ...,
        min_length=16,
        max_length=80,
        description="1 句 · 20-60 字的衔接文案；自然过渡到后续 5 道补充题。",
    )


class AnalyzeResponse(_StrictModel):
    """POST /api/onboarding/analyze 响应体。

    消费方：前端状态机直接把 `skip_rules` 写进 localStorage，驱动题库循环；
    `first_hook` 立即在「第一个钩子页」渲染。
    """

    skip_rules: dict[str, SkipRule] = Field(
        ...,
        description="按题号（A1/A2/A3/A4/A5）返回的筛题决策。必须是 5 条。",
    )
    first_hook: FirstHook = Field(
        ...,
        description="基于自由描述 + 截图生成的首发开场钩子（结构化）。",
    )


# ---------- /report 端点 ----------


class ReportRequest(_StrictModel):
    """POST /api/onboarding/report 请求体。

    触发时机：题库循环全部完成（A1-A5 回答完毕或被跳过），前端把完整答卷回传。
    """

    session_id: str = Field(..., description="同 `AnalyzeRequest.session_id`。")
    free_text: str = Field(..., description="用户最初的自由描述（原文）。")
    ocr_texts: list[str] = Field(
        default_factory=list, description="截图 OCR 文本列表。"
    )
    answers: dict[str, str | list[str]] = Field(
        ...,
        description=(
            "按题号（A1-A5）记录答题结果。单选题值为 str（选项 id），"
            "多选题值为 list[str]。被 skip 的题应当不出现在字典里。"
        ),
    )


class StateLabel(_StrictModel):
    """诊断状态标签（一个有记忆点的名词）。

    六选一，对应需求文档 3.2 节：
    - 高危滑坡期 / 舒适区陷阱 / 临门犹豫期 / 信号过载期 / 空白探索期 / 僵局观察期
    """

    name: Literal[
        "高危滑坡期",
        "舒适区陷阱",
        "临门犹豫期",
        "信号过载期",
        "空白探索期",
        "僵局观察期",
    ] = Field(..., description="六个状态标签之一。")
    severity: Literal["danger", "warning", "opportunity", "neutral", "observation"] = (
        Field(..., description="状态严重程度枚举，前端用来决定配色。")
    )
    theme_color: str = Field(
        ...,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="状态标签主题色，hex 格式如 `#C00000`。",
    )


class ScoreItem(_StrictModel):
    """单个维度的分数 + 一句话解释。"""

    score: int = Field(..., ge=0, le=100, description="0-100 的整数分数。")
    note: str = Field(..., description="一句话解释这个分数意味着什么。")


class Scores5D(_StrictModel):
    """五维健康度模型：Attraction / Comfort / Romance / Trust / Engagement。"""

    A: ScoreItem = Field(..., description="吸引力 Attraction（ACR 原生）。")
    C: ScoreItem = Field(..., description="舒适感 Comfort（ACR 原生）。")
    R: ScoreItem = Field(..., description="张力 Romance（ACR 原生）。")
    T: ScoreItem = Field(..., description="信任度 Trust（Gottman 模型）。")
    E: ScoreItem = Field(..., description="回应度 Engagement（依恋理论）。")


class CoreIssue(_StrictModel):
    """诊断报告里的一条核心问题。"""

    title: str = Field(..., description="结论性判断标题（例如「需求感暴露过早」）。")
    evidence: str = Field(
        ...,
        description="具体证据：引用用户描述或截图里的细节，证明不是套话。",
    )


class TrendPrediction(_StrictModel):
    """趋势预判。"""

    tone: Literal["urgent", "hopeful"] = Field(
        ...,
        description="语气枚举：urgent（紧迫）或 hopeful（还有希望）。",
    )
    text: str = Field(..., description="一句话的走向预测。")


class LockedTeaser(_StrictModel):
    """付费内容预览条目。"""

    section: str = Field(..., description="能力模块名（例如「聊天指导」）。")
    teaser: str = Field(
        ...,
        description="露半句截断的具体内容，在用户最想知道答案处截断。",
    )


class DiagnosisReport(_StrictModel):
    """免费诊断报告的完整结构（/report 端点响应体）。

    结构对应设计稿 page7-report.jsx 四个区块：
    1) 状态标签 + 5 维雷达 + 核心问题 + 趋势预判（免费，本结构承载）
    2) locked_teasers → 付费预览区块
    3) 信任背书（由前端静态文案承担，不在 schema 里）
    4) urgency_text → 付费 CTA 区块顶部的紧迫感文案
    """

    report_id: str = Field(
        ...,
        description="报告唯一 id，建议格式 `CR-{8 位时间戳后缀}`。",
    )
    state_label: StateLabel = Field(..., description="状态标签（六选一）。")
    scores_5d: Scores5D = Field(..., description="五维健康度分数。")
    core_issues: list[CoreIssue] = Field(
        ...,
        min_length=2,
        max_length=3,
        description="核心问题 2-3 条（多了信息过载，少了震撼不够）。",
    )
    trend_prediction: TrendPrediction = Field(..., description="走向预测。")
    locked_teasers: list[LockedTeaser] = Field(
        ...,
        min_length=3,
        max_length=6,
        description="付费预览 3-6 条（对应设计稿 3 大能力 × 1-2 子项）。",
    )
    urgency_text: str = Field(
        ...,
        description="紧迫感文案（例如「窗口期约 2-3 周，越早介入扭转成本越低」）。",
    )
    collected_summary: str = Field(
        ...,
        description=(
            "一句话摘要，交给 main_agent 作为第一轮的诊断背景。"
            "参考模板：「用户是同事场景，关系 3-6 个月，已表白过一次 TA 委婉拒绝，"
            "目前 ACR 中 R 维度偏低（18 分），核心问题是需求感暴露过早。」"
        ),
    )
