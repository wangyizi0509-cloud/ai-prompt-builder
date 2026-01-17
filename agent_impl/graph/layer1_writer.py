"""
Layer 1 写入逻辑（原子记忆）
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Literal, Callable, Any
import uuid

from graph.context_types import (
    Layer1Memory,
    Layer2Memory,
    AtomicMemory,
    DynamicIntelItem,
)


TargetType = Literal["user_info", "crush_info", "both_info"]
SourceType = Literal["user_provide", "fact", "ai_provide"]


def save_atomic_memory(
    layer1_memory: Layer1Memory,
    layer2_memory: Layer2Memory,
    target: TargetType,
    source: SourceType,
    content: str,
    source_type: str,
    confidence: Optional[float] = None,
    confidence_reason: Optional[str] = None,
    *,
    llm: Optional[Callable[[str], Any]] = None,
    now: Optional[datetime] = None,
) -> tuple[Layer1Memory, Layer2Memory]:
    """
    写入一条原子记忆（含去重 / 覆盖 / 长短期分流）
    """
    content = (content or "").strip()
    if not content:
        return layer1_memory, layer2_memory

    now = now or datetime.now()
    _ensure_layer1(layer1_memory)

    target_block = layer1_memory["full_data"].setdefault(target, {})
    if source == "user_provide":
        target_block.setdefault("user_provide", [])
    elif source == "fact":
        target_block.setdefault("fact", [])
    elif source == "ai_provide":
        target_block.setdefault("ai_provide", [])

    # 1) 语义去重
    existing_list = list(target_block.get(source, []) or [])
    for item in existing_list:
        if not isinstance(item, dict):
            continue
        existing_content = str(item.get("content") or "")
        if _llm_judge_duplicate(existing_content, content, llm):
            return layer1_memory, layer2_memory

    # 2) 按来源执行写入策略
    if source == "user_provide":
        target_block["user_provide"] = _replace_by_attribute(
            existing_list,
            content,
            llm,
        )
        target_block["user_provide"].append(
            _build_atomic_memory(content, source_type, confidence, confidence_reason, now)
        )
        _touch_layer1(layer1_memory, now)
        return layer1_memory, layer2_memory

    if source == "ai_provide":
        if confidence is None:
            confidence = 0.6
        if not confidence_reason:
            confidence_reason = "自动补充：AI 分析结论"
        target_block["ai_provide"] = _replace_by_dimension(
            existing_list,
            content,
            llm,
        )
        target_block["ai_provide"].append(
            _build_atomic_memory(content, source_type, confidence, confidence_reason, now)
        )
        _touch_layer1(layer1_memory, now)
        return layer1_memory, layer2_memory

    # 事实：长短期分流
    if source == "fact":
        is_long_term = _llm_judge_fact_term(content, llm)
        if is_long_term:
            target_block["fact"].append(
                _build_atomic_memory(content, source_type, confidence, confidence_reason, now)
            )
            _touch_layer1(layer1_memory, now)
            return layer1_memory, layer2_memory

        # 短期事实 -> Layer 2 动态情报板
        _append_dynamic_intel(
            layer2_memory,
            content=content,
            now=now,
            confidence=confidence,
            confidence_reason=confidence_reason,
            target=target,
        )
        _touch_layer2(layer2_memory, now)
        return layer1_memory, layer2_memory

    return layer1_memory, layer2_memory


def _build_atomic_memory(
    content: str,
    source_type: str,
    confidence: Optional[float],
    confidence_reason: Optional[str],
    now: datetime,
) -> AtomicMemory:
    created_at = now.strftime("%Y-%m-%dT%H")
    data: AtomicMemory = {
        "id": str(uuid.uuid4())[:8],
        "content": content,
        "created_at": created_at,
        "source_type": source_type,
    }
    if confidence is not None:
        data["confidence"] = confidence
    if confidence_reason:
        data["confidence_reason"] = confidence_reason
    return data


def _ensure_layer1(layer1_memory: Layer1Memory) -> None:
    if "full_data" not in layer1_memory or not isinstance(layer1_memory.get("full_data"), dict):
        layer1_memory["full_data"] = {"user_info": {}, "crush_info": {}, "both_info": {}}
    for key in ("user_info", "crush_info", "both_info"):
        if key not in layer1_memory["full_data"] or not isinstance(layer1_memory["full_data"][key], dict):
            layer1_memory["full_data"][key] = {}


def _touch_layer1(layer1_memory: Layer1Memory, now: datetime) -> None:
    layer1_memory["last_updated"] = now.isoformat()
    layer1_memory["update_count"] = int(layer1_memory.get("update_count") or 0) + 1
    layer1_memory["version"] = int(layer1_memory.get("version") or 1) + 1


def _touch_layer2(layer2_memory: Layer2Memory, now: datetime) -> None:
    layer2_memory["last_updated"] = now.isoformat()
    layer2_memory["version"] = int(layer2_memory.get("version") or 1) + 1


def _append_dynamic_intel(
    layer2_memory: Layer2Memory,
    *,
    content: str,
    now: datetime,
    confidence: Optional[float],
    confidence_reason: Optional[str],
    target: TargetType,
) -> None:
    subject = "user" if target == "user_info" else "crush"
    expires = now + timedelta(days=14)
    item: DynamicIntelItem = {
        "id": str(uuid.uuid4())[:8],
        "content": content,
        "created_at": now.strftime("%Y-%m-%dT%H"),
        "expire_at": expires.strftime("%Y-%m-%dT00"),
        "subject": subject,
        "category": "status",
        "confidence": confidence if confidence is not None else 0.6,
        "confidence_reason": confidence_reason or "自动补充：短期事实分流",
        "source_type": "conversation",
    }
    layer2_memory.setdefault("dynamic_intels", [])
    layer2_memory["dynamic_intels"].append(item)


def _llm_judge_duplicate(existing: str, new: str, llm: Optional[Callable[[str], Any]]) -> bool:
    if not existing:
        return False
    if not llm:
        return existing.strip() == new.strip()
    prompt = (
        "判断以下两条信息是否表达相同含义，只回答 duplicate 或 new：\n"
        f"- 已有信息：「{existing}」\n"
        f"- 新信息：「{new}」\n"
    )
    result = _invoke_llm(llm, prompt).strip().lower()
    return "duplicate" in result


def _replace_by_attribute(
    existing_list: list[AtomicMemory],
    new_content: str,
    llm: Optional[Callable[[str], Any]],
) -> list[AtomicMemory]:
    if not llm:
        return existing_list
    kept: list[AtomicMemory] = []
    for item in existing_list:
        content = str(item.get("content") or "")
        if not _llm_judge_same_attribute(content, new_content, llm):
            kept.append(item)
    return kept


def _replace_by_dimension(
    existing_list: list[AtomicMemory],
    new_content: str,
    llm: Optional[Callable[[str], Any]],
) -> list[AtomicMemory]:
    if not llm:
        return existing_list
    kept: list[AtomicMemory] = []
    for item in existing_list:
        content = str(item.get("content") or "")
        if not _llm_judge_same_dimension(content, new_content, llm):
            kept.append(item)
    return kept


def _llm_judge_same_attribute(existing: str, new: str, llm: Callable[[str], Any]) -> bool:
    if not existing:
        return False
    prompt = (
        "判断以下两条信息是否属于同一属性，只回答 yes 或 no：\n"
        f"- 信息A：「{existing}」\n"
        f"- 信息B：「{new}」\n"
    )
    result = _invoke_llm(llm, prompt).strip().lower()
    return result.startswith("y")


def _llm_judge_same_dimension(existing: str, new: str, llm: Callable[[str], Any]) -> bool:
    if not existing:
        return False
    prompt = (
        "判断以下两条分析是否属于同一维度，只回答 yes 或 no：\n"
        f"- 分析A：「{existing}」\n"
        f"- 分析B：「{new}」\n"
    )
    result = _invoke_llm(llm, prompt).strip().lower()
    return result.startswith("y")


def _llm_judge_fact_term(content: str, llm: Optional[Callable[[str], Any]]) -> bool:
    if not llm:
        # 简单启发式：包含明确近期时间词 → 短期
        keywords = ["今天", "明天", "后天", "下周", "本周", "最近", "今晚", "本月"]
        return not any(k in content for k in keywords)
    prompt = (
        "判断以下信息是长期事实还是短期事实，只回答 long_term 或 short_term：\n"
        f"信息：「{content}」\n"
        "- 长期事实：长期有效，如性格、习惯、背景\n"
        "- 短期事实：有时效性，如近期计划、当前状态\n"
    )
    result = _invoke_llm(llm, prompt).strip().lower()
    return "long_term" in result


def _invoke_llm(llm: Callable[[str], Any], prompt: str) -> str:
    try:
        if hasattr(llm, "invoke"):
            return str(llm.invoke(prompt))
        if hasattr(llm, "ainvoke"):
            return str(llm.ainvoke(prompt))
        return str(llm(prompt))
    except Exception:
        return ""
