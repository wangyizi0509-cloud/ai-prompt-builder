"""
整理 Agent (Organize Agent)
负责在信息从「高优」变「低优」时提取高价值信息并归档

职责：
1. 提取高价值信息 → 写入 3×3 静态情报矩阵
2. 生成压缩摘要 → 写入对应的历史存档

触发时机：
- 行动指南执行完毕
- 现状分析被新版替换
- 对话滚动窗口压缩时

特点：
- 纯后端处理，不与用户交互
- 根据输入类型分类处理，输出到不同归档位置
"""

import json
from typing import Literal, Optional, Any
from datetime import datetime, timedelta
import uuid
from pathlib import Path
import logging

from graph.context_types import (
    UserContext,
    HistorySummary,
    ConversationArchive,
    ActionGuideItem,
    ActionPlanItem,
    Layer2Memory,
    DynamicIntelItem,
    create_dynamic_intel_item,
)
from utils.message_utils import get_msg_role_and_content, count_user_turns
from config import get_llm


logger = logging.getLogger(__name__)

# ============================================================
# Prompt 模板加载（统一存放在 context_system_v2/04_Prompts）
# ============================================================

_PROMPT_FILE = (
    Path(__file__).resolve().parents[2]
    / "context_system_v2"
    / "04_Prompts"
    / "organize_agent_prompts.md"
)
_PROMPT_CACHE: dict[str, str] = {}


def _extract_template_block(text: str, name: str) -> str:
    start_tag = f"<!-- TEMPLATE: {name} -->"
    end_tag = "<!-- END_TEMPLATE -->"

    start = text.find(start_tag)
    if start == -1:
        return ""
    start = start + len(start_tag)

    end = text.find(end_tag, start)
    if end == -1:
        return ""

    return text[start:end].strip()


def _load_prompt_template(name: str) -> str:
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]

    try:
        raw = _PROMPT_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        _PROMPT_CACHE[name] = ""
        return ""

    tpl = _extract_template_block(raw, name)
    _PROMPT_CACHE[name] = tpl
    return tpl


def _render_prompt(template: str, mapping: dict[str, str]) -> str:
    out = template or ""
    for k, v in (mapping or {}).items():
        out = out.replace(k, v if v is not None else "")
    return out.strip()


def _build_existing_context_blocks(
    existing_context: Optional[UserContext],
    existing_layer2_memory: Optional[Layer2Memory],
) -> tuple[str, str]:
    from graph.context_builder import _build_layer1_static_intel, _build_dynamic_intel_board

    layer1_text = _build_layer1_static_intel(existing_context) if existing_context else ""
    if not layer1_text:
        layer1_text = "暂无"

    layer2_text = _build_dynamic_intel_board(existing_layer2_memory) if existing_layer2_memory else ""
    if not layer2_text:
        layer2_text = "暂无"

    return layer1_text, layer2_text


# ============================================================
# 输入类型定义
# ============================================================

ArchiveType = Literal[
    "action_guide",      # 行动指南归档
    "status_report",     # 现状分析归档
    "action_plan",       # 行动规划归档
    "conversation",      # 对话压缩归档
    "dynamic_intel",     # 动态情报抽取
]

# 动态情报默认 TTL （单位：天）
# 注意：category 是自由文本（LLM 自定义），以下仅为常见类型的默认 TTL
# 未在此列表中的 category 使用默认 14 天
DEFAULT_INTEL_TTL_DAYS = {
    "schedule": 2,    # 日程类：事件结束后 2 天
    "mood": 3,        # 情绪类：3 天后
    "status": 7,      # 临时状态类：7 天后
    "intent": 14,     # 意向类：14 天后
}
DEFAULT_INTEL_TTL_FALLBACK = 14  # 其他 category 的默认 TTL


# ============================================================
# 整理 Agent 核心函数
# ============================================================

def organize_and_archive(
    content: Any,
    content_type: ArchiveType,
    existing_user_context: Optional[UserContext] = None,
    existing_layer2_memory: Optional[Layer2Memory] = None,
) -> dict:
    """
    整理并归档信息
    
    根据输入类型分类处理：
    - action_guide: 生成行动指南摘要 + 提取高价值信息
    - status_report: 生成现状分析摘要 + 提取高价值信息
    - conversation: 生成对话摘要 + 提取高价值信息
    
    Args:
        content: 待归档的内容
        content_type: 内容类型
        existing_user_context: 现有的用户上下文（用于合并提取的信息）
    
    Returns:
        {
            "summary": HistorySummary 或 ConversationArchive,
            "extracted_info": dict (待合并到 user_context 的信息),
        }
    """
    llm = get_llm(temperature=0.3)  # 低温度，保证稳定性
    
    # 根据类型选择不同的处理策略
    if content_type == "action_guide":
        return _process_action_guide(content, llm, existing_user_context, existing_layer2_memory)
    elif content_type == "status_report":
        return _process_status_report(content, llm, existing_user_context, existing_layer2_memory)
    elif content_type == "action_plan":
        return _process_action_plan(content, llm, existing_user_context, existing_layer2_memory)
    elif content_type == "conversation":
        return _process_conversation(content, llm, existing_user_context, existing_layer2_memory)
    else:
        raise ValueError(f"Unknown content_type: {content_type}")


# ============================================================
# 分类处理函数
# ============================================================

def _process_action_guide(
    guide: ActionGuideItem,
    llm,
    existing_context: Optional[UserContext],
    existing_layer2_memory: Optional[Layer2Memory],
) -> dict:
    """
    处理行动指南归档
    
    生成：
    1. 中等摘要（100-200字）：任务目标、执行情况、结果
    2. 一句话摘要（20-30字）
    3. 提取高价值信息：用户执行任务过程中暴露的性格特点、Crush 反馈等
    """
    guide_content = guide.get("guide", {})
    full_content = guide_content.get("guide_content", "")
    current_task = guide_content.get("current_task", "未命名任务")

    tpl = _load_prompt_template("action_guide")
    layer1_text, layer2_text = _build_existing_context_blocks(existing_context, existing_layer2_memory)
    prompt = _render_prompt(
        tpl,
        {
            "__GUIDE_CURRENT_TASK__": str(current_task or ""),
            "__GUIDE_FULL_CONTENT__": str(full_content or ""),
            "__EXISTING_LAYER1__": layer1_text,
            "__EXISTING_LAYER2__": layer2_text,
        },
    )
    
    response = llm.invoke(prompt)
    parsed = _parse_json_response(response.content)
    
    # 构建 HistorySummary
    history_summary = HistorySummary(
        id=str(uuid.uuid4())[:8],
        summary=parsed.get("summary", f"任务：{current_task}"),
        one_liner=parsed.get("one_liner", current_task[:30]),
        created_at=datetime.now().isoformat(),
        full_content=full_content,
    )
    
    return {
        "summary": history_summary,
        "extracted_info": parsed.get("extracted_info", {}),
        "archive_type": "guide_history",
    }


def _process_status_report(
    report: dict,
    llm,
    existing_context: Optional[UserContext],
    existing_layer2_memory: Optional[Layer2Memory],
) -> dict:
    """
    处理现状分析归档
    
    生成：
    1. 中等摘要：关系阶段、核心问题、风险点
    2. 一句话摘要
    3. 提取高价值信息：诊断过程中发现的关键洞察
    """
    report_content = report.get("report_content", "")
    stage = report.get("stage", "")
    summary_text = report.get("summary", "")

    tpl = _load_prompt_template("status_report")
    layer1_text, layer2_text = _build_existing_context_blocks(existing_context, existing_layer2_memory)
    prompt = _render_prompt(
        tpl,
        {
            "__STATUS_STAGE__": str(stage or ""),
            "__STATUS_SUMMARY_TEXT__": str(summary_text or ""),
            "__STATUS_REPORT_CONTENT__": str(report_content or ""),
            "__EXISTING_LAYER1__": layer1_text,
            "__EXISTING_LAYER2__": layer2_text,
        },
    )
    
    response = llm.invoke(prompt)
    parsed = _parse_json_response(response.content)
    
    # 构建 HistorySummary
    history_summary = HistorySummary(
        id=str(uuid.uuid4())[:8],
        summary=parsed.get("summary", summary_text or f"阶段：{stage}"),
        one_liner=parsed.get("one_liner", stage[:30] if stage else "现状分析"),
        created_at=datetime.now().isoformat(),
        full_content=report_content,
    )
    
    return {
        "summary": history_summary,
        "extracted_info": parsed.get("extracted_info", {}),
        "archive_type": "status_history",
    }


def _process_action_plan(
    plan: ActionPlanItem,
    llm,
    existing_context: Optional[UserContext],
    existing_layer2_memory: Optional[Layer2Memory],
) -> dict:
    """
    处理行动规划归档

    生成：
    1. 中等摘要：目标、策略、关键阶段
    2. 一句话摘要
    3. 提取高价值信息：规划中对用户/Crush/关系的关键判断
    """
    plan_content = plan.get("plan_content", "")
    goal = plan.get("goal", "")
    strategy = plan.get("strategy", "")

    tpl = _load_prompt_template("action_plan")
    layer1_text, layer2_text = _build_existing_context_blocks(existing_context, existing_layer2_memory)
    prompt = _render_prompt(
        tpl,
        {
            "__PLAN_GOAL__": str(goal or ""),
            "__PLAN_STRATEGY__": str(strategy or ""),
            "__PLAN_CONTENT__": str(plan_content or ""),
            "__EXISTING_LAYER1__": layer1_text,
            "__EXISTING_LAYER2__": layer2_text,
        },
    )

    response = llm.invoke(prompt)
    parsed = _parse_json_response(response.content)

    history_summary = HistorySummary(
        id=str(uuid.uuid4())[:8],
        summary=parsed.get("summary", goal or "行动规划"),
        one_liner=parsed.get("one_liner", (goal or strategy or "行动规划")[:30]),
        created_at=datetime.now().isoformat(),
        full_content=plan_content,
    )

    return {
        "summary": history_summary,
        "extracted_info": parsed.get("extracted_info", {}),
        "archive_type": "plan_history",
    }


def _process_conversation(
    messages: list[dict],
    llm,
    existing_context: Optional[UserContext],
    existing_layer2_memory: Optional[Layer2Memory],
) -> dict:
    """
    处理对话压缩归档
    
    新版 Prompt 一次输出包含：
    1. 对话摘要 + 关键话题
    2. layer1_info（Layer 1 长期信息，3×3 矩阵）
    3. dynamic_intel（Layer 2 动态情报）
    """
    existing_layer1_text, existing_layer2_text = _build_existing_context_blocks(
        existing_context,
        existing_layer2_memory,
    )

    # 格式化对话
    formatted_messages = []
    for msg in messages:
        msg_role, msg_content = get_msg_role_and_content(msg)
        role = "用户" if msg_role == "user" else "小话"
        formatted_messages.append(f"{role}: {msg_content}")
    conversation_text = "\n".join(formatted_messages)

    tpl = _load_prompt_template("conversation")
    prompt = _render_prompt(
        tpl,
        {
            "__CONVERSATION_TEXT__": str(conversation_text or ""),
            "__EXISTING_LAYER1__": str(existing_layer1_text or ""),
            "__EXISTING_LAYER2__": str(existing_layer2_text or ""),
        },
    )

    llm_calls = 0
    response = llm.invoke(prompt)
    llm_calls += 1
    logger.info(f"_process_conversation llm_calls={llm_calls}")
    parsed = _parse_json_response(response.content)
    
    # 解析 Layer 1 信息（注意：新 Prompt 输出字段名是 layer1_info）
    extracted_info = parsed.get("layer1_info", {})
    if not isinstance(extracted_info, dict):
        extracted_info = {}
    
    # 解析关键话题
    key_topics = parsed.get("key_topics", [])
    if not isinstance(key_topics, list):
        key_topics = [str(key_topics)] if key_topics else []
    
    # 解析动态情报（Layer 2）
    raw_dynamic_intel = parsed.get("dynamic_intel", [])
    if not isinstance(raw_dynamic_intel, list):
        raw_dynamic_intel = []
    # 使用 _normalize_dynamic_intels 规范化为 DynamicIntelItem 格式
    dynamic_intels = _normalize_dynamic_intels(raw_dynamic_intel)
    
    # 构建 ConversationArchive
    conversation_archive = ConversationArchive(
        id=str(uuid.uuid4())[:8],
        summary=parsed.get("summary", "对话归档"),
        start_time=datetime.now().isoformat(),  # 实际应该从消息中提取
        end_time=datetime.now().isoformat(),
        turn_count=count_user_turns(messages),  # 以用户消息为基准计算轮次
        key_topics=key_topics,
        extracted_info=extracted_info,
    )
    
    return {
        "summary": conversation_archive,
        "extracted_info": extracted_info,
        "dynamic_intels": dynamic_intels,  # 新增：直接从 LLM 输出解析
        "archive_type": "conversation_archive",
    }


# ============================================================
# 动态情报抽取
# ============================================================

def extract_dynamic_intel_from_messages(
    messages: list[dict],
    source_msg_id: Optional[str] = None,
) -> list[DynamicIntelItem]:
    """从消息列表中提取动态情报"""
    if not messages:
        return []
    formatted = []
    for msg in messages:
        role, content = get_msg_role_and_content(msg)
        if not content:
            continue
        role_label = "用户" if role == "user" else "小话"
        formatted.append(f"{role_label}: {content}")
    return extract_dynamic_intel_from_text("\n".join(formatted), source_msg_id=source_msg_id)


def extract_dynamic_intel_from_text(
    text: str,
    source_msg_id: Optional[str] = None,
) -> list[DynamicIntelItem]:
    """从文本中提取动态情报（短期/时效性信息）"""
    if not text:
        return []
    
    # 尝试从模板文件加载 Prompt
    tpl = _load_prompt_template("dynamic_intel")
    if tpl:
        prompt = _render_prompt(tpl, {"__DYNAMIC_INTEL_TEXT__": text})
    else:
        # 回退到内联 Prompt（兜底）
        prompt = f"""你是信息整理专家，请从以下文本中提取【动态情报】— 短期/时效性信息。

动态情报是有时效性的信息，过一段时间就会失效或变化。

典型类型：
- schedule（日程）：近期计划、约定、行程，如"下周三要去上海出差"
- mood（情绪）：当前心情、情绪变化，如"最近心情不太好"
- status（状态）：短期状态、临时情况，如"最近在加班"
- intent（意向）：近期打算、想法，如"想约她看电影"

输入文本：
{text}

请输出 JSON 数组，字段：
- content: 情报内容（简洁，保留时间/情绪等关键细节）
- category: schedule|mood|status|intent
- subject: user|crush （信息主体：关于用户还是关于 Crush）
- expire_at: ISO 时间，可为空（系统会根据 category 自动计算）
- valid_from: ISO 时间，可为空
- confidence: 0-1 浮点
- confidence_reason: 置信度原因

示例：
[
  {{"content":"下周三去上海见 Crush","category":"schedule","subject":"user","expire_at":"","valid_from":"","confidence":0.95,"confidence_reason":"用户明确表述"}}
]

如果没有发现动态情报，输出空数组 []"""
    
    llm = get_llm(temperature=0.2)
    response = llm.invoke(prompt)
    raw_items = _parse_json_list(response.content)
    return _normalize_dynamic_intels(raw_items, source_msg_id=source_msg_id)


def _normalize_dynamic_intels(
    items: list[dict],
    *,
    source_msg_id: Optional[str] = None,
) -> list[DynamicIntelItem]:
    """规范化 LLM 输出并填充默认 TTL"""
    normalized: list[DynamicIntelItem] = []
    now = datetime.now()

    for item in items or []:
        # [FIX] 跳过非 dict 类型的元素
        if not isinstance(item, dict):
            continue
        content = (item or {}).get("content", "").strip()
        category = (item or {}).get("category", "").strip()
        subject = (item or {}).get("subject", "user").strip() or "user"
        if not content or not category:
            continue

        valid_from = item.get("valid_from") or now.isoformat()
        expire_at = item.get("expire_at") or _calc_expire_at(category, valid_from)
        confidence = float(item.get("confidence", 0.8))
        confidence_reason = (item or {}).get("confidence_reason", "").strip()

        intel = create_dynamic_intel_item(
            content=content,
            category=category,  # type: ignore[arg-type]
            subject=subject,    # type: ignore[arg-type]
            valid_from=valid_from,
            expire_at=expire_at,
            confidence=confidence,
            confidence_reason=confidence_reason,
        )
        normalized.append(intel)
    return normalized


def _calc_expire_at(category: str, valid_from: str) -> str:
    """根据类别计算默认过期时间"""
    days = DEFAULT_INTEL_TTL_DAYS.get(category, DEFAULT_INTEL_TTL_FALLBACK)
    try:
        start = datetime.fromisoformat(valid_from)
    except Exception:
        start = datetime.now()
    expire = start + timedelta(days=days)
    return expire.isoformat()


# ============================================================
# 辅助函数
# ============================================================

def _parse_json_response(content: str) -> dict:
    """解析 LLM 的 JSON 输出，始终返回 dict"""
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                json_str = content[start:end]
            else:
                json_str = content
        
        result = json.loads(json_str)
        # [FIX] 确保返回 dict，如果 LLM 返回了 list 则取第一个元素或返回空 dict
        if isinstance(result, list):
            return result[0] if result and isinstance(result[0], dict) else {}
        if not isinstance(result, dict):
            return {}
        return result
    except (json.JSONDecodeError, IndexError):
        return {}


def _parse_json_list(content: str) -> list[dict]:
    """解析 JSON 数组输出"""
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content
        data = json.loads(json_str)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def merge_extracted_info_to_context(
    existing_context: UserContext,
    extracted_info: dict,
    source_type: Literal["onboarding", "conversation", "report"] = "conversation",
) -> UserContext:
    """
    将提取的信息合并到现有的用户上下文中
    
    合并策略：
    - 新格式（v2）：按 user_provide/fact/ai_provide 分类写入对应字段
    - 旧格式（v1）：兼容处理，写入 ai_provide（向后兼容）
    
    新格式 extracted_info 示例：
    {
        "user_info": {
            "user_provide": ["用户说的信息1", "用户说的信息2"],
            "fact": ["客观事实1"],
            "ai_provide": ["AI分析结论1"]
        },
        ...
    }
    
    旧格式 extracted_info 示例（向后兼容）：
    {
        "user_info": "字符串信息",
        ...
    }
    
    Args:
        existing_context: 现有的 3×3 矩阵
        extracted_info: 整理 Agent 提取的信息
        source_type: 信息来源类型（用于创建 AtomicMemory）
    
    Returns:
        更新后的 UserContext
    """
    from graph.context_types import create_atomic_memory
    
    # [FIX] 防御性检查：确保 extracted_info 是 dict
    if not extracted_info or not isinstance(extracted_info, dict):
        return existing_context
    
    # 深拷贝避免修改原对象
    updated = {
        "user_info": dict(existing_context.get("user_info", {})),
        "crush_info": dict(existing_context.get("crush_info", {})),
        "both_info": dict(existing_context.get("both_info", {})),
    }
    
    # 确保每个维度都有三个来源字段（列表格式）
    for dimension in ["user_info", "crush_info", "both_info"]:
        for source in ["user_provide", "fact", "ai_provide"]:
            if source not in updated[dimension]:
                updated[dimension][source] = []
            # 兼容旧的字符串格式：如果是字符串，转换为列表
            elif isinstance(updated[dimension][source], str):
                old_str = updated[dimension][source].strip()
                if old_str:
                    # 旧字符串格式迁移：创建一个 AtomicMemory
                    updated[dimension][source] = [
                        create_atomic_memory(old_str, source_type)
                    ]
                else:
                    updated[dimension][source] = []
    
    # 合并 user_info, crush_info, both_info
    for dimension in ["user_info", "crush_info", "both_info"]:
        dim_info = extracted_info.get(dimension)
        if not dim_info:
            continue
        
        # 判断是新格式（dict with user_provide/fact/ai_provide）还是旧格式（string）
        if isinstance(dim_info, dict):
            # 新格式 v2：按来源分类
            _merge_dimension_v2(updated[dimension], dim_info, source_type)
        elif isinstance(dim_info, str) and dim_info.strip():
            # 旧格式 v1：兼容处理，写入 ai_provide
            _merge_dimension_v1(updated[dimension], dim_info, source_type)
    
    return UserContext(**updated)


def _is_semantically_duplicate(existing_content: str, new_content: str) -> bool:
    """
    判断两条信息是否语义重复（轻量级，避免额外 LLM 调用）
    """
    existing = (existing_content or "").strip().lower()
    new = (new_content or "").strip().lower()
    if not existing or not new:
        return False
    if existing == new:
        return True

    def _normalize(text: str) -> str:
        return (
            text.replace("'", "")
            .replace('"', "")
            .replace("：", ":")
            .replace("、", ",")
            .replace(" ", "")
        )

    if _normalize(existing) == _normalize(new):
        return True

    if len(existing) > 5 and len(new) > 5:
        if existing in new or new in existing:
            return True

    return False


def _merge_dimension_v2(
    target: dict,
    source_info: dict,
    source_type: Literal["onboarding", "conversation", "report"],
) -> None:
    """
    合并新格式（v2）的信息到目标维度
    
    source_info 格式：
    {
        "user_provide": ["信息1", "信息2"],
        "fact": ["事实1"],
        "ai_provide": ["分析1"]
    }
    """
    from graph.context_types import create_atomic_memory
    
    for field in ["user_provide", "fact", "ai_provide"]:
        items = source_info.get(field, [])
        if not items:
            continue
        
        # 确保是列表
        if isinstance(items, str):
            items = [items] if items.strip() else []
        elif not isinstance(items, list):
            continue

        # 遍历每条信息，创建 AtomicMemory 并追加（带去重与更新）
        for item in items:
            if not item:
                continue

            action = ""
            old_keyword = ""
            content = ""
            if isinstance(item, dict):
                action = str(item.get("action") or "").strip().lower()
                old_keyword = str(item.get("old") or "").strip()
                content = str(item.get("content") or "").strip()
            elif isinstance(item, str):
                content = item.strip()
            else:
                continue

            if not content:
                continue

            if action == "update":
                replaced = False
                if old_keyword:
                    for i, existing in enumerate(target[field]):
                        existing_content = (
                            str(existing.get("content") or "") if isinstance(existing, dict) else str(existing)
                        )
                        if old_keyword in existing_content:
                            target[field][i] = create_atomic_memory(
                                content,
                                source_type,
                                confidence=0.8 if field == "ai_provide" else None,
                                confidence_reason="整理Agent从内容中提取" if field == "ai_provide" else None,
                            )
                            replaced = True
                            break
                if not replaced:
                    for i, existing in enumerate(target[field]):
                        existing_content = (
                            str(existing.get("content") or "") if isinstance(existing, dict) else str(existing)
                        )
                        if _is_semantically_duplicate(existing_content, content):
                            target[field][i] = create_atomic_memory(
                                content,
                                source_type,
                                confidence=0.8 if field == "ai_provide" else None,
                                confidence_reason="整理Agent从内容中提取" if field == "ai_provide" else None,
                            )
                            replaced = True
                            break
                if not replaced:
                    if field == "ai_provide":
                        atomic = create_atomic_memory(
                            content,
                            source_type,
                            confidence=0.8,
                            confidence_reason="整理Agent从内容中提取",
                        )
                    else:
                        atomic = create_atomic_memory(content, source_type)
                    target[field].append(atomic)
                continue

            is_duplicate = False
            for existing in target[field]:
                existing_content = (
                    str(existing.get("content") or "") if isinstance(existing, dict) else str(existing)
                )
                if _is_semantically_duplicate(existing_content, content):
                    is_duplicate = True
                    break
            if is_duplicate:
                continue

            if field == "ai_provide":
                atomic = create_atomic_memory(
                    content,
                    source_type,
                    confidence=0.8,
                    confidence_reason="整理Agent从内容中提取",
                )
            else:
                atomic = create_atomic_memory(content, source_type)

            target[field].append(atomic)


def _merge_dimension_v1(
    target: dict,
    info_str: str,
    source_type: Literal["onboarding", "conversation", "report"],
) -> None:
    """
    合并旧格式（v1）的信息到目标维度（向后兼容）
    
    旧格式：直接是一个字符串，全部写入 ai_provide
    """
    from graph.context_types import create_atomic_memory
    
    content = info_str.strip()
    if not content:
        return
    
    # 旧格式默认写入 ai_provide（保持向后兼容）
    atomic = create_atomic_memory(
        content,
        source_type,
        confidence=0.8,
        confidence_reason="整理Agent从内容中提取（旧格式兼容）"
    )
    target["ai_provide"].append(atomic)


def summarize_task_reasoning(
    reasoning_items: list[str],
    current_summary: str,
) -> str:
    """
    压缩任务思考过程
    
    Args:
        reasoning_items: 需要压缩的思考过程列表
        current_summary: 当前已有的摘要
    
    Returns:
        新的摘要
    """
    if not reasoning_items:
        return current_summary
        
    llm = get_llm(temperature=0.3)
    
    reasoning_text = "\n".join(f"- {item}" for item in reasoning_items)

    tpl = _load_prompt_template("task_reasoning")
    prompt = _render_prompt(
        tpl,
        {
            "__CURRENT_SUMMARY__": str(current_summary or "暂无"),
            "__REASONING_TEXT__": str(reasoning_text or ""),
        },
    )

    response = llm.invoke(prompt)
    return response.content.strip()


# ============================================================
# 批量处理函数（供外部调用）
# ============================================================

def archive_completed_guide(
    guide: ActionGuideItem,
    existing_context: UserContext,
    existing_layer2_memory: Optional[Layer2Memory] = None,
) -> dict:
    """
    归档已完成的行动指南
    
    Args:
        guide: 已完成的行动指南
        existing_context: 现有用户上下文
    
    Returns:
        {
            "guide_summary": HistorySummary,
            "updated_context": UserContext,
        }
    """
    result = organize_and_archive(guide, "action_guide", existing_context, existing_layer2_memory)
    updated_context = merge_extracted_info_to_context(
        existing_context, 
        result.get("extracted_info", {}),
        source_type="report"  # 行动指南归档
    )
    
    return {
        "guide_summary": result["summary"],
        "updated_context": updated_context,
    }


def archive_replaced_status_report(
    old_report: dict,
    existing_context: UserContext,
    existing_layer2_memory: Optional[Layer2Memory] = None,
) -> dict:
    """
    归档被替换的现状分析报告
    
    Args:
        old_report: 被替换的旧报告
        existing_context: 现有用户上下文
    
    Returns:
        {
            "status_summary": HistorySummary,
            "updated_context": UserContext,
        }
    """
    result = organize_and_archive(old_report, "status_report", existing_context, existing_layer2_memory)
    updated_context = merge_extracted_info_to_context(
        existing_context,
        result.get("extracted_info", {}),
        source_type="report"  # 现状报告归档
    )
    dynamic_intels = extract_dynamic_intel_from_text(
        old_report.get("report_content", ""),
        source_msg_id=old_report.get("id"),
    )
    
    return {
        "status_summary": result["summary"],
        "updated_context": updated_context,
        "dynamic_intels": dynamic_intels,
    }


def archive_replaced_action_plan(
    old_plan: ActionPlanItem,
    existing_context: UserContext,
    existing_layer2_memory: Optional[Layer2Memory] = None,
) -> dict:
    """
    归档被替换的行动规划

    Returns:
        {
            "plan_summary": HistorySummary,
            "updated_context": UserContext,
        }
    """
    result = organize_and_archive(old_plan, "action_plan", existing_context, existing_layer2_memory)
    updated_context = merge_extracted_info_to_context(
        existing_context,
        result.get("extracted_info", {}),
        source_type="report"  # 行动规划归档
    )
    return {
        "plan_summary": result["summary"],
        "updated_context": updated_context,
        "dynamic_intels": [],
    }


def archive_conversation_batch(
    messages_to_archive: list[dict],
    existing_context: UserContext,
    existing_layer2_memory: Optional[Layer2Memory] = None,
) -> dict:
    """
    批量归档对话
    
    新版：一次 LLM 调用同时获取 Layer 1 信息和动态情报，不再单独调用动态情报提取。
    
    Args:
        messages_to_archive: 需要归档的消息列表
        existing_context: 现有用户上下文
    
    Returns:
        {
            "conversation_archive": ConversationArchive,
            "updated_context": UserContext,
            "dynamic_intels": list[DynamicIntelItem],
        }
    """
    logger.info(f"archive_conversation_batch called with {len(messages_to_archive)} messages")
    result = organize_and_archive(
        messages_to_archive,
        "conversation",
        existing_context,
        existing_layer2_memory,
    )
    logger.info(f"organize_and_archive returned: {list(result.keys()) if isinstance(result, dict) else type(result)}")
    
    extracted_info = result.get("extracted_info", {})
    logger.info(f"extracted_info type: {type(extracted_info)}")
    
    # [FIX] 确保 extracted_info 是 dict
    if not isinstance(extracted_info, dict):
        logger.warning(f"WARNING: extracted_info is not dict, using empty dict")
        extracted_info = {}
    
    updated_context = merge_extracted_info_to_context(
        existing_context,
        extracted_info,
        source_type="conversation"  # 对话压缩
    )
    logger.info(f"updated_context type: {type(updated_context)}")
    
    # 直接从 result 获取动态情报（不再单独调用 extract_dynamic_intel_from_messages）
    dynamic_intels = result.get("dynamic_intels", [])
    logger.info(f"dynamic_intels count: {len(dynamic_intels)}")
    
    return {
        "conversation_archive": result["summary"],
        "updated_context": updated_context,
        "dynamic_intels": dynamic_intels,
    }
