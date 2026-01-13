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
from datetime import datetime
import uuid

from graph.context_types import (
    UserContext,
    HistorySummary,
    ConversationArchive,
    ActionGuideItem,
)
from config import get_llm


# ============================================================
# 输入类型定义
# ============================================================

ArchiveType = Literal[
    "action_guide",      # 行动指南归档
    "status_report",     # 现状分析归档
    "conversation",      # 对话压缩归档
]


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
    
    prompt = f"""你是信息整理专家。请从以下已完成的行动指南中提取信息并生成摘要。

## 行动指南内容
任务：{current_task}
完整内容：
{full_content}

## 任务
1. 生成**中等摘要**（100-200字）：概括任务目标、核心策略、预期效果
2. 生成**一句话摘要**（20-30字）：一句话概括这个任务
3. 提取**高价值信息**：从中识别出对理解用户/Crush/双方关系有帮助的信息

## 输出格式（JSON）
```json
{{
  "summary": "中等摘要内容",
  "one_liner": "一句话摘要",
  "extracted_info": {{
    "user_info": "关于用户的新发现（如性格、行为模式），没有则为空",
    "crush_info": "关于Crush的新发现，没有则为空",
    "both_info": "关于双方关系的新发现，没有则为空"
  }}
}}
```"""
    
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
    
    prompt = f"""你是信息整理专家。请从以下现状分析报告中提取信息并生成摘要。

## 现状分析报告
关系阶段：{stage}
原始总结：{summary_text}
完整报告：
{report_content}

## 任务
1. 生成**中等摘要**（100-200字）：概括关系阶段、核心问题、关键风险
2. 生成**一句话摘要**（20-30字）：一句话概括当前关系状态
3. 提取**高价值信息**：从诊断中识别出的关键洞察

## 输出格式（JSON）
```json
{{
  "summary": "中等摘要内容",
  "one_liner": "一句话摘要",
  "extracted_info": {{
    "user_info": "关于用户的分析结论（如依恋类型、沟通模式），没有则为空",
    "crush_info": "关于Crush的分析结论（如性格特征、态度倾向），没有则为空",
    "both_info": "关于双方关系的分析结论（如互动模式、问题根源），没有则为空"
  }}
}}
```"""
    
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
        role = "用户" if msg.get("role") == "user" else "小话"
        formatted_messages.append(f"{role}: {msg.get('content', '')}")
    conversation_text = "\n".join(formatted_messages)
    
    prompt = f"""你是信息整理专家。请从以下对话记录中提取信息并生成摘要。

## 对话记录
{conversation_text}

## 任务
1. 生成**对话摘要**（50-100字）：概括对话的核心话题和关键结论
2. 提取**关键话题**：用 2-5 个词标签概括
3. 提取**高价值信息**：用户透露的新事实、情感状态变化等

## 输出格式（JSON）
```json
{{
  "summary": "对话摘要内容",
  "key_topics": ["话题1", "话题2", "话题3"],
  "extracted_info": {{
    "user_info": "用户透露的关于自己的信息，没有则为空",
    "crush_info": "用户提到的关于Crush的信息，没有则为空",
    "both_info": "用户提到的关于双方关系的信息，没有则为空"
  }}
}}
```"""
    
    response = llm.invoke(prompt)
    parsed = _parse_json_response(response.content)
    
    # 构建 ConversationArchive
    conversation_archive = ConversationArchive(
        id=str(uuid.uuid4())[:8],
        summary=parsed.get("summary", "对话归档"),
        start_time=datetime.now().isoformat(),  # 实际应该从消息中提取
        end_time=datetime.now().isoformat(),
        turn_count=len(messages),
        key_topics=parsed.get("key_topics", []),
        extracted_info=parsed.get("extracted_info", {}),
    )
    
    return {
        "summary": conversation_archive,
        "extracted_info": parsed.get("extracted_info", {}),
        "archive_type": "conversation_archive",
    }


# ============================================================
# 辅助函数
# ============================================================

def _parse_json_response(content: str) -> dict:
    """解析 LLM 的 JSON 输出"""
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
        
        return json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        return {}


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
    if not extracted_info:
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
    
    return {
        "status_summary": result["summary"],
        "updated_context": updated_context,
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
    result = organize_and_archive(messages_to_archive, "conversation", existing_context)
    updated_context = merge_extracted_info_to_context(
        existing_context,
        result.get("extracted_info", {})
    )
    
    return {
        "conversation_archive": result["summary"],
        "updated_context": updated_context,
    }
