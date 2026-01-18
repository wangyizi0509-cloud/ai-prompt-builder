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

from graph.context_types import (
    UserContext,
    HistorySummary,
    ConversationArchive,
    ActionGuideItem,
    ActionPlanItem,
    DynamicIntelItem,
    create_dynamic_intel_item,
)
from utils.message_utils import get_msg_role_and_content, count_user_turns
from config import get_llm


# ============================================================
# Prompt 模板加载（统一存放在 context_system/04_Prompts）
# ============================================================

_PROMPT_FILE = (
    Path(__file__).resolve().parents[2]
    / "context_system"
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
        return _process_action_guide(content, llm, existing_user_context)
    elif content_type == "status_report":
        return _process_status_report(content, llm, existing_user_context)
    elif content_type == "action_plan":
        return _process_action_plan(content, llm, existing_user_context)
    elif content_type == "conversation":
        return _process_conversation(content, llm, existing_user_context)
    else:
        raise ValueError(f"Unknown content_type: {content_type}")


# ============================================================
# 分类处理函数
# ============================================================

def _process_action_guide(
    guide: ActionGuideItem,
    llm,
    existing_context: Optional[UserContext],
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
    prompt = _render_prompt(
        tpl,
        {
            "__GUIDE_CURRENT_TASK__": str(current_task or ""),
            "__GUIDE_FULL_CONTENT__": str(full_content or ""),
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
    prompt = _render_prompt(
        tpl,
        {
            "__STATUS_STAGE__": str(stage or ""),
            "__STATUS_SUMMARY_TEXT__": str(summary_text or ""),
            "__STATUS_REPORT_CONTENT__": str(report_content or ""),
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
    prompt = _render_prompt(
        tpl,
        {
            "__PLAN_GOAL__": str(goal or ""),
            "__PLAN_STRATEGY__": str(strategy or ""),
            "__PLAN_CONTENT__": str(plan_content or ""),
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
) -> dict:
    """
    处理对话压缩归档
    
    生成：
    1. 对话摘要：核心话题、关键结论
    2. 关键话题标签
    3. 提取高价值信息：用户透露的事实、情感状态变化等
    """
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
        },
    )
    
    response = llm.invoke(prompt)
    parsed = _parse_json_response(response.content)
    
    # [FIX] 确保 extracted_info 和 key_topics 是正确的类型
    extracted_info = parsed.get("extracted_info", {})
    if not isinstance(extracted_info, dict):
        extracted_info = {}
    key_topics = parsed.get("key_topics", [])
    if not isinstance(key_topics, list):
        key_topics = [str(key_topics)] if key_topics else []
    
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
    """从文本中提取动态情报"""
    if not text:
        return []
    llm = get_llm(temperature=0.2)
    prompt = f"""你是一名情报提取员，请从以下文本中提取【动态情报】。

动态情报定义：短期时效信息，包括日程、心情、状态、意图。

输入文本：
{text}

请输出 JSON 数组，字段：
- content: 情报内容（简洁，保留时间/情绪等关键细节）
- category: schedule|mood|status|intent
- subject: user|crush （信息主体）
- expire_at: ISO 时间，可为空（如果为空将使用默认 TTL 计算）
- valid_from: ISO 时间，可为空
- source_msg_id: 字符串，可为空
- confidence: 0-1 浮点

示例：
[
  {{"content":"下周三去上海出差","category":"schedule","subject":"crush","expire_at":"","valid_from":"","source_msg_id":"","confidence":0.9}}
]"""
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
) -> UserContext:
    """
    将提取的信息合并到现有的用户上下文中
    
    合并策略：追加到对应字段的 ai_provide 部分
    
    Args:
        existing_context: 现有的 3×3 矩阵
        extracted_info: 整理 Agent 提取的信息
    
    Returns:
        更新后的 UserContext
    """
    # [FIX] 防御性检查：确保 extracted_info 是 dict
    if not extracted_info or not isinstance(extracted_info, dict):
        return existing_context
    
    # 深拷贝避免修改原对象
    updated = {
        "user_info": dict(existing_context.get("user_info", {})),
        "crush_info": dict(existing_context.get("crush_info", {})),
        "both_info": dict(existing_context.get("both_info", {})),
    }
    
    # 合并 user_info
    if extracted_info.get("user_info"):
        existing_ai = updated["user_info"].get("ai_provide", "")
        new_info = extracted_info["user_info"]
        if existing_ai:
            updated["user_info"]["ai_provide"] = f"{existing_ai}\n{new_info}"
        else:
            updated["user_info"]["ai_provide"] = new_info
    
    # 合并 crush_info
    if extracted_info.get("crush_info"):
        existing_ai = updated["crush_info"].get("ai_provide", "")
        new_info = extracted_info["crush_info"]
        if existing_ai:
            updated["crush_info"]["ai_provide"] = f"{existing_ai}\n{new_info}"
        else:
            updated["crush_info"]["ai_provide"] = new_info
    
    # 合并 both_info
    if extracted_info.get("both_info"):
        existing_ai = updated["both_info"].get("ai_provide", "")
        new_info = extracted_info["both_info"]
        if existing_ai:
            updated["both_info"]["ai_provide"] = f"{existing_ai}\n{new_info}"
        else:
            updated["both_info"]["ai_provide"] = new_info
    
    return UserContext(**updated)


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
    result = organize_and_archive(guide, "action_guide", existing_context)
    updated_context = merge_extracted_info_to_context(
        existing_context, 
        result.get("extracted_info", {})
    )
    
    return {
        "guide_summary": result["summary"],
        "updated_context": updated_context,
    }


def archive_replaced_status_report(
    old_report: dict,
    existing_context: UserContext,
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
    result = organize_and_archive(old_report, "status_report", existing_context)
    updated_context = merge_extracted_info_to_context(
        existing_context,
        result.get("extracted_info", {})
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
) -> dict:
    """
    归档被替换的行动规划

    Returns:
        {
            "plan_summary": HistorySummary,
            "updated_context": UserContext,
        }
    """
    result = organize_and_archive(old_plan, "action_plan", existing_context)
    updated_context = merge_extracted_info_to_context(
        existing_context,
        result.get("extracted_info", {})
    )
    return {
        "plan_summary": result["summary"],
        "updated_context": updated_context,
        "dynamic_intels": [],
    }


def archive_conversation_batch(
    messages_to_archive: list[dict],
    existing_context: UserContext,
) -> dict:
    """
    批量归档对话
    
    Args:
        messages_to_archive: 需要归档的消息列表
        existing_context: 现有用户上下文
    
    Returns:
        {
            "conversation_archive": ConversationArchive,
            "updated_context": UserContext,
        }
    """
    print(f"[OrganizeAgent] archive_conversation_batch called with {len(messages_to_archive)} messages")
    result = organize_and_archive(messages_to_archive, "conversation", existing_context)
    print(f"[OrganizeAgent] organize_and_archive returned: {list(result.keys()) if isinstance(result, dict) else type(result)}")
    
    extracted_info = result.get("extracted_info", {})
    print(f"[OrganizeAgent] extracted_info type: {type(extracted_info)}")
    
    # [FIX] 确保 extracted_info 是 dict
    if not isinstance(extracted_info, dict):
        print(f"[OrganizeAgent] WARNING: extracted_info is not dict, using empty dict")
        extracted_info = {}
    
    updated_context = merge_extracted_info_to_context(
        existing_context,
        extracted_info
    )
    print(f"[OrganizeAgent] updated_context type: {type(updated_context)}")
    dynamic_intels = extract_dynamic_intel_from_messages(messages_to_archive)
    print(f"[OrganizeAgent] dynamic_intels type: {type(dynamic_intels)}")
    
    return {
        "conversation_archive": result["summary"],
        "updated_context": updated_context,
        "dynamic_intels": dynamic_intels,
    }
