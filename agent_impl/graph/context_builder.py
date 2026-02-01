"""
上下文组装器
实现分层长期记忆架构，从各层长期记忆中提取信息输入到 Agent

策略文档参考：
- 综合压缩策略：context_system/03_Strategies/Compression_Strategy/compression_strategy_v1.0.md
- 提取策略：context_system/03_Strategies/Extraction_Strategy/extraction_strategy_v1.0.md
- 存储策略：context_system/03_Strategies/Storage_Strategy/storage_strategy_v1.0.md

规范文档参考：
- Layer 1 规范：context_system/02_Specs/layer1_spec_v1.0.md
- Layer 2 规范：context_system/02_Specs/layer2_spec_v1.0.md
- Layer 3 规范：context_system/02_Specs/layer3_spec_v1.0.md
- 组装规范：context_system/02_Specs/context_assembly_spec.md
- 任务系统：context_system/02_Specs/task_system_spec.md

分层长期记忆架构：
- Layer 0: 系统指令区（只读常驻）
- Layer 1: 静态情报（原子记忆结构）
- Layer 2: 工作上下文（报告/规划/指南/动态情报）
- Layer 3: 对话历史（摘要/任务笔记/最近对话）
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Literal

if TYPE_CHECKING:
    from graph.state import AgentState

from graph.context_types import (
    # Layer 1
    UserContext,
    Layer1Memory,
    # Layer 2
    Layer2Memory,
    ActionGuideItem,
    StatusReportItem,
    ActionPlanItem,
    get_active_action_guides,
    get_completed_action_guides,
    get_valid_dynamic_intels,
    # Layer 3
    Layer3Memory,
    ConversationSummary,
    # 任务系统
    AgentTaskRegistry,
    TaskState,
    get_active_task,
    create_empty_user_context,
)
from graph.extraction_strategy import ExtractionPipeline
from utils.message_utils import get_msg_role_and_content
from graph.tools.task_tools import (
    format_task_index,
    format_active_task_payload,
    get_task_list_for_agent,
    get_active_task as get_active_task_from_list,
)


# ============================================================
# Token 预算常量
# ============================================================

TOKEN_BUDGET = {
    "total": 62000,               # 总预算（安全边际）
    "output_reserve": 8000,       # 预留给模型输出
    "layer0_system": 4000,        # 系统指令区
    "layer1_static": 15000,       # 静态情报区
    "layer2_working": 20000,      # 工作上下文
    "layer3_conversation": 15000, # 对话历史（25轮 + 摘要）
}

# Layer 1 默认配置
LAYER1_DEFAULT_CONFIG = {
    "mode": "full",              # full=完整保留, compressed=压缩模式
    "max_tokens": 15000,         # 压缩模式下的 token 上限
}

# Layer 2 默认配置
LAYER2_DEFAULT_CONFIG = {
    "recent_summary_count": 2,   # 最近 N 份保留中等摘要
    "max_one_liner_count": 10,   # 最多保留 N 条一句话摘要
    "include_active_guides": True,  # 是否包含所有未执行指南
    "max_dynamic_intels": 20,    # 动态情报最多注入条数
    "max_in_progress_guides": 2,
    "max_paused_guides": 2,
    "max_pending_guides": 3,
    "max_completed_guides": 5,
    "max_cancelled_guides": 2,
    "max_expired_guides": 2,
}

# Layer 3 默认配置
LAYER3_DEFAULT_CONFIG = {
    "max_recent_turns": 25,      # 完整保留的最近轮次
    "include_summaries": True,   # 是否包含历史摘要
    "max_summary_count": 5,      # 最多包含的摘要条数
    "reasoning_limit": 8,        # 推理笔记保留条数
}


# ============================================================
# 核心组装函数
# ============================================================

def build_context(
    state: "AgentState",
    target_agent: Literal["main_agent", "status_agent", "plan_agent", "guide_agent"] = "main_agent",
    include_layer0: bool = False,
) -> str:
    """
    组装完整上下文
    
    通过 ExtractionPipeline 显式执行提取策略
    """
    pipeline = ExtractionPipeline(
        extract_layer1=extract_layer1,
        extract_layer2=extract_layer2,
        extract_layer3=extract_layer3,
        build_layer0=_build_layer0_system,
    )
    return pipeline.build_text(state, target_agent=target_agent, include_layer0=include_layer0)


def build_context_dict(state: "AgentState", target_agent: str = "main_agent") -> dict:
    """
    构建上下文字典（用于 Prompt 模板变量替换）
    
    组装顺序按 context_assembly_spec.md：
    Layer 0 → Layer 1 → Layer 2.a → 输出格式 → Layer 2.b → 任务系统 → Layer 3
    """
    pipeline = ExtractionPipeline(
        extract_layer1=extract_layer1,
        extract_layer2=extract_layer2,
        extract_layer3=extract_layer3,
        build_layer0=_build_layer0_system,
        build_context_dict=_build_context_dict_payload,
    )
    return pipeline.build_dict(state, target_agent=target_agent)


def _build_context_dict_payload(state: "AgentState", target_agent: str = "main_agent") -> dict:
    """构建上下文字典"""
    layer1_memory = state.get("layer1_memory", {})
    layer2_memory = state.get("layer2_memory", {})
    layer3_memory = state.get("layer3_memory", {})
    task_registry = _get_task_registry_from_state(state)
    
    user_context = layer1_memory.get("full_data") if layer1_memory else {}
    
    # Layer 3 配置
    layer3_config = layer3_memory.get("extraction_config", LAYER3_DEFAULT_CONFIG) if isinstance(layer3_memory, dict) else LAYER3_DEFAULT_CONFIG
    max_recent_turns = layer3_config.get("max_recent_turns", 25)
    max_summary_count = layer3_config.get("max_summary_count", 5)

    # 当前任务
    current_task_id = _get_current_task_id(state, target_agent)
    active_task = get_active_task(task_registry.get(target_agent, []) or []) if isinstance(task_registry.get(target_agent, []), list) else None
    scratchpad_notes = []
    scratchpad_summary = ""
    if isinstance(active_task, dict):
        scratchpad_notes = _get_task_reasoning_notes(active_task)
        scratchpad_summary = str(active_task.get("summary") or "")

    # 对话历史
    messages = state.get("messages", [])
    current_message_id = str(state.get("current_message_id") or "").strip()
    summaries = layer3_memory.get("conversation_summaries", []) if isinstance(layer3_memory, dict) else []
    conversation_history = _format_interleaved_history(
        messages=messages,
        current_message_id=current_message_id,
        current_task_id=current_task_id,
        max_turns=max_recent_turns,
        summaries=summaries[:max_summary_count] if isinstance(summaries, list) else None,
        scratchpad_task_id=current_task_id,
        scratchpad_notes=scratchpad_notes,
        scratchpad_summary=scratchpad_summary,
    ) or "无历史对话"

    # 任务系统
    task_list = get_task_list_for_agent(state, target_agent)
    task_index = format_task_index(task_list)
    active_task_for_payload = get_active_task_from_list(task_list)
    active_task_payload = format_active_task_payload(active_task_for_payload)

    return {
        # Layer 1: 静态情报
        "user_context": extract_layer1(state) or "暂无用户信息",

        # Layer 2.a: 稳定工作上下文
        "status_report": _extract_current_status_report(state),
        "action_plan": _extract_current_action_plan(state),

        # Layer 2.b: 动态工作上下文
        "dynamic_intel": _extract_dynamic_intel(state),
        "action_guides": _extract_action_guides(state),
        "history_summaries": _extract_layer2_history_summaries(state),

        # 任务系统
        "task_index": task_index,
        "active_task_payload": json.dumps(active_task_payload, ensure_ascii=False),
        "bound_contexts": _format_bound_contexts(active_task_for_payload),

        # Layer 3: 对话历史
        "conversation_history": conversation_history,
        "current_task_id": current_task_id,

        # Main Agent → 专家 Brief
        "instruction": str(state.get("instruction") or ""),
    }


# ============================================================
# Layer 1: 静态情报提取（原子记忆结构）
# ============================================================

def extract_layer1(state: "AgentState") -> str:
    """
    从 Layer 1 长期记忆中提取静态情报
    
    输出格式：紧凑列表 [时间/来源] 内容
    """
    layer1_memory = state.get("layer1_memory")
    
    if not layer1_memory:
        return ""
    
    full_data = layer1_memory.get("full_data", {})
    config = layer1_memory.get("extraction_config", LAYER1_DEFAULT_CONFIG)
    
    if not full_data:
        return ""
    
    mode = config.get("mode", "full")
    
    if mode == "compressed":
        max_tokens = config.get("max_tokens", 15000)
        return _build_layer1_compressed(full_data, max_tokens)
    
    return _build_layer1_static_intel(full_data)


def _build_layer1_static_intel(user_context: UserContext) -> str:
    """
    Layer 1: 静态情报区（原子记忆结构）
    
    输出紧凑列表格式：[时间/来源] 内容
    """
    if not user_context:
        return ""

    sections: list[str] = [
        "## 情报概览",
        "> 信息可靠性：事实 > AI分析 > 用户提供。当信息冲突时，以高可靠性信息为准。",
        "",
    ]

    user_info = user_context.get("user_info", {})
    if _has_atomic_content(user_info):
        sections.append("### 用户")
        sections.extend(_format_atomic_info_block(user_info))
        sections.append("")

    crush_info = user_context.get("crush_info", {})
    crush_name = ""
    if isinstance(crush_info, dict):
        crush_name = str(crush_info.get("crush_name") or "").strip()
    if _has_atomic_content(crush_info) or crush_name:
        title = f"### Crush（{crush_name}）" if crush_name else "### Crush"
        sections.append(title)
        sections.extend(_format_atomic_info_block(crush_info))
        sections.append("")

    both_info = user_context.get("both_info", {})
    if _has_atomic_content(both_info):
        sections.append("### 双方关系")
        sections.extend(_format_atomic_info_block(both_info))
        sections.append("")

    content = "\n".join([line for line in sections if line is not None]).strip()
    
    if content == "## 情报概览\n> 信息可靠性：事实 > AI分析 > 用户提供。当信息冲突时，以高可靠性信息为准.":
        return "暂无详细信息，需要进一步了解。"
    
    return content or "暂无详细信息，需要进一步了解。"


def _has_atomic_content(info: dict) -> bool:
    """检查是否有原子记忆内容"""
    if not isinstance(info, dict):
        return False
    return any(isinstance(info.get(k), list) and info.get(k) for k in ("user_provide", "fact", "ai_provide"))


def _format_atomic_info_block(info: dict) -> list[str]:
    """按规范格式化原子记忆列表"""
    items: list[tuple[str, str, str]] = []
    source_priority = {"fact": 0, "ai_provide": 1, "user_provide": 2}
    source_label = {"fact": "事实", "ai_provide": "AI", "user_provide": "用户"}

    for source_key in ("fact", "ai_provide", "user_provide"):
        records = info.get(source_key, [])
        if not isinstance(records, list):
            continue
        for rec in records:
            if not isinstance(rec, dict):
                continue
            created_at = str(rec.get("created_at") or "")
            content = str(rec.get("content") or "").strip()
            if not content:
                continue
            items.append((created_at, source_key, content))

    def _sort_key(item: tuple[str, str, str]) -> tuple[int, int]:
        created_at, source_key, _ = item
        ts = _safe_parse_iso(created_at)
        time_key = int(ts.timestamp()) if ts else 0
        return (-time_key, source_priority.get(source_key, 9))

    items.sort(key=_sort_key)

    lines: list[str] = []
    for created_at, source_key, content in items:
        time_text = _format_display_time(created_at)
        label = source_label.get(source_key, "用户")
        lines.append(f"- [{time_text}/{label}] {content}")

    return lines


def _build_layer1_compressed(user_context: UserContext, max_tokens: int) -> str:
    """Layer 1: 静态情报区 - 压缩模式（待实现）"""
    return _build_layer1_static_intel(user_context)


# ============================================================
# Layer 2: 工作上下文提取
# ============================================================

def extract_layer2(state: "AgentState") -> str:
    """
    从 Layer 2 长期记忆中提取工作上下文
    
    按 context_assembly_spec.md 顺序：
    - Layer 2.a: 现状报告 + 行动规划（稳定）
    - Layer 2.b: 动态情报板 + 行动指南列表 + 历史摘要（动态）
    """
    layer2_memory = state.get("layer2_memory")
    
    if not layer2_memory:
        return ""
    
    config = layer2_memory.get("extraction_config", LAYER2_DEFAULT_CONFIG)
    
    sections = []
    has_content = False
    
    # Layer 2.a: 稳定部分
    
    # 1. 当前现状分析报告
    current_report = layer2_memory.get("current_status_report")
    if current_report:
        has_content = True
        sections.append("## 现状分析")
        sections.append("### 当前报告")
        sections.append(_format_status_report_item(current_report))
    
    # 2. 当前行动规划
    current_plan = layer2_memory.get("current_action_plan")
    if current_plan:
        has_content = True
        sections.append("## 行动规划")
        sections.append("### 当前规划")
        sections.append(_format_action_plan_item(current_plan))
    
    # Layer 2.b: 动态部分
    
    # 3. 动态情报板
    intel_section = _build_dynamic_intel_board(layer2_memory, config)
    if intel_section:
        has_content = True
        sections.append(intel_section)

    # 4. 行动指南
    all_guides = layer2_memory.get("action_guides", [])
    if all_guides and config.get("include_active_guides", True):
        has_content = True
        sections.append("## 行动指南")
        sections.append(_format_action_guide_items(all_guides, config))

    # 5. 历史摘要
    history_section = _build_layer2_history_summaries(layer2_memory, config)
    if history_section:
        has_content = True
        sections.append(history_section)
    
    if not has_content:
        return ""
    
    return "\n\n".join(sections)


def _build_dynamic_intel_board(layer2_memory: Layer2Memory, config: dict | None = None) -> str:
    """构建动态情报板"""
    intels = get_valid_dynamic_intels(layer2_memory)
    if not intels:
        return ""
    config = config or LAYER2_DEFAULT_CONFIG
    max_count = config.get("max_dynamic_intels", 20)

    # 按 subject 分组
    user_intels = []
    crush_intels = []

    def _sort_key(item: dict) -> str:
        return item.get("expire_at") or item.get("created_at") or ""

    intels = sorted(intels, key=_sort_key)
    if isinstance(max_count, int) and max_count > 0:
        intels = intels[:max_count]
    
    for intel in intels:
        subject = intel.get("subject", "user")
        created_at = intel.get("created_at", "")
        time_text = _format_display_time(created_at)
        content = intel.get("content", "")
        confidence = intel.get("confidence", 0.8)
        confidence_reason = intel.get("confidence_reason", "")
        
        line = f"- [{time_text}] {content} (置信度: {confidence:.2f} - {confidence_reason})"
        
        if subject == "crush":
            crush_intels.append(line)
        else:
            user_intels.append(line)

    parts = ["## 动态情报板", "> 以下是近期的时效性信息，请务必参考。置信度说明：越高越可信。", ""]
    
    if user_intels:
        parts.append("### 用户")
        parts.extend(user_intels)
        parts.append("")
    
    if crush_intels:
        parts.append("### Crush")
        parts.extend(crush_intels)
        parts.append("")

    return "\n".join(parts)


def _build_layer2_history_summaries(layer2_memory: Layer2Memory, config: dict) -> str:
    """构建 Layer 2 历史摘要"""
    recent_count = config.get("recent_summary_count", 2)
    max_one_liner = config.get("max_one_liner_count", 10)
    
    sections = []
    
    # 历史报告摘要
    history_reports = layer2_memory.get("status_report_history", [])
    if history_reports:
        report_section = _format_layer2_history_items(
            history_reports, "近期报告", recent_count, max_one_liner
        )
        if report_section:
            sections.append(report_section)
    
    # 历史行动指南摘要（已完成的）
    completed_guides = get_completed_action_guides(layer2_memory)
    if completed_guides:
        guide_section = _format_completed_guides(completed_guides[:5], recent_count)
        if guide_section:
            sections.append(guide_section)
    
    if not sections:
        return ""
    
    return "## 历史摘要\n\n" + "\n\n".join(sections)


def _format_layer2_history_items(
    items: list,
    title: str,
    recent_count: int,
    max_one_liner: int
) -> str:
    """格式化 Layer 2 历史项"""
    if not items:
        return ""
    
    parts = [f"### {title}"]
    
    for i, item in enumerate(items[:recent_count + max_one_liner]):
        if i < recent_count:
            summary = item.get("summary", item.get("one_liner", ""))
            created_at = item.get("created_at", "")
            date_str = _format_display_time(created_at)[:5] if created_at else ""
            if summary:
                parts.append(f"- **[{date_str}]** {summary}")
        else:
            one_liner = item.get("one_liner", "")
            created_at = item.get("created_at", "")
            date_str = _format_display_time(created_at)[:5] if created_at else ""
            if one_liner:
                parts.append(f"- [{date_str}] {one_liner}")
    
    return "\n".join(parts) if len(parts) > 1 else ""


def _format_completed_guides(guides: list[ActionGuideItem], recent_count: int = 2) -> str:
    """格式化已完成指南"""
    if not guides:
        return ""
    
    parts = ["### 已完成"]
    
    status_map = {
        "success": "成功",
        "partial": "部分完成",
        "failed": "失败",
        "abandoned": "放弃",
        "other": "其他",
    }

    for i, guide in enumerate(guides):
        guide_id = guide.get("id", "")
        title = guide.get("title", "未命名指南")
        completed_at = guide.get("completed_at", "")
        date_str = _format_display_time(completed_at)[:5] if completed_at else ""
        
        # 上下文策略：前 recent_count 条用 summary（优先）或 one_liner（fallback），后面的只用 one_liner
        if i < recent_count:
            summary = guide.get("summary") or guide.get("one_liner") or ""
        else:
            summary = guide.get("one_liner") or ""
        
        feedback_data = guide.get("feedback_data") or {}
        feedback_status = feedback_data.get("completion_status") or ""
        feedback_summary = feedback_data.get("feedback_summary") or guide.get("user_feedback", "")
        
        parts.append(f"#### 【{guide_id}】{title}")
        parts.append(f"> 完成于: {date_str}")
        
        if summary:
            parts.append(f"**原计划**: {summary}")
        if feedback_status:
            parts.append(f"**反馈状态**: {status_map.get(feedback_status, feedback_status)}")
        if feedback_summary:
            parts.append(f"**反馈总结**: {feedback_summary}")
        parts.append("")
    
    return "\n".join(parts)


# ============================================================
# Layer 3: 对话历史提取
# ============================================================

def extract_layer3(state: "AgentState") -> str:
    """
    从 Layer 3 长期记忆中提取对话历史
    
    包含：
    1) 历史摘要（最多 5 条）
    2) 任务笔记（最多 8 条）
    3) 最近对话（25 轮）
    
    输出格式：Markdown + 时间戳（内容中不再标注 U/A/S）
    """
    messages = state.get("messages", [])
    layer3_memory = state.get("layer3_memory", {}) or {}
    summaries = layer3_memory.get("conversation_summaries", []) if isinstance(layer3_memory, dict) else []

    config = layer3_memory.get("extraction_config", LAYER3_DEFAULT_CONFIG) if isinstance(layer3_memory, dict) else LAYER3_DEFAULT_CONFIG
    max_recent_turns = config.get("max_recent_turns", 25)
    max_summary_count = config.get("max_summary_count", 5)

    target_agent = state.get("current_agent") or "main_agent"
    current_task_id = _get_current_task_id(state, target_agent)

    task_registry = _get_task_registry_from_state(state)
    active_task = get_active_task(task_registry.get(target_agent, []) or []) if isinstance(task_registry.get(target_agent, []), list) else None
    scratchpad_notes = []
    scratchpad_summary = ""
    if isinstance(active_task, dict):
        scratchpad_notes = _get_task_reasoning_notes(active_task)
        scratchpad_summary = str(active_task.get("summary") or "")

    history = _format_interleaved_history(
        messages=messages,
        current_message_id=str(state.get("current_message_id") or "").strip(),
        current_task_id=current_task_id,
        max_turns=max_recent_turns,
        summaries=summaries[:max_summary_count] if isinstance(summaries, list) else None,
        scratchpad_task_id=current_task_id,
        scratchpad_notes=scratchpad_notes,
        scratchpad_summary=scratchpad_summary,
    )
    return history or "无历史对话"


def _apply_pre_model_history_filter(messages: list, current_message_id: str) -> list:
    """
    统一的 pre_model_hook：避免本轮用户消息在历史中重复出现。
    只影响"传给模型的历史"，不修改原始 messages 存储。
    
    [FIX-2026-01-19] 增强版：
    - 按消息 ID 去重，不按内容去重
    - 保留同 ID 的“最新一条”，避免误删当前消息
    """
    safe_messages = list(messages) if isinstance(messages, list) else []
    if not safe_messages:
        return safe_messages

    from graph.state import get_message_id

    # 按 ID 去重：保留同 ID 的最后一条
    seen_ids = set()
    filtered_reversed = []
    for msg in reversed(safe_messages):
        msg_id = get_message_id(msg)
        if msg_id:
            if msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)
        filtered_reversed.append(msg)

    return list(reversed(filtered_reversed))

def _format_interleaved_history(
    messages: list,
    current_task_id: str,
    current_message_id: str = "",
    max_turns: int = 25,
    summaries: list | None = None,
    scratchpad_task_id: str = "",
    scratchpad_notes: list | None = None,
    scratchpad_summary: str = "",
) -> str:
    """
    构建对话历史（Markdown + 时间戳）
    
    格式：[时间戳] 内容
    """
    lines: list[str] = []

    messages = _apply_pre_model_history_filter(messages, current_message_id)

    # 历史摘要
    if summaries:
        lines.append("## 历史摘要")
        for s in summaries:
            if not isinstance(s, dict):
                continue
            text = (s.get("summary") or "").strip()
            topics = s.get("topics", "")
            created_at = str(s.get("created_at") or "")
            time_text = _format_display_time(created_at)
            
            if text:
                if topics:
                    lines.append(f"- [{time_text}/{topics}] {text}")
                else:
                    lines.append(f"- [{time_text}] {text}")
        lines.append("")

    # 任务笔记
    if scratchpad_task_id and (scratchpad_notes or scratchpad_summary):
        title = scratchpad_summary or scratchpad_task_id
        lines.append(f"## 任务笔记「{title}」")
        if scratchpad_notes:
            for note in scratchpad_notes:
                note_content, note_time = _normalize_reasoning_note(note)
                time_text = _format_display_time(note_time)
                if note_content:
                    if time_text:
                        lines.append(f"- [{time_text}] {note_content}")
                    else:
                        lines.append(f"- {note_content}")
        lines.append("")

    # 最近对话
    lines.append("## 对话")
    
    if not messages:
        lines.append("（无近期对话）")
        return "\n".join(lines).strip()

    # 保留最近 N 个用户轮次
    start_idx = 0
    user_turns = 0
    for i in range(len(messages) - 1, -1, -1):
        role, _ = get_msg_role_and_content(messages[i])
        if role == "user":
            user_turns += 1
            if user_turns >= max_turns:
                start_idx = i
                break
    recent_msgs = messages[start_idx:]

    for msg in recent_msgs:
        role, content = get_msg_role_and_content(msg)
        if role == "tool":
            continue
        if role not in ("user", "assistant", "ai", "system"):
            continue
        if role in ("assistant", "ai"):
            content = _format_assistant_message_for_history(content)
        time_text = _format_display_time(_extract_message_time(msg)) or _format_display_time(datetime.now().isoformat())
        if content:
            lines.append(f"[{time_text}] {content}")

    return "\n".join(lines).strip()


def _format_assistant_message_for_history(content: str) -> str:
    """格式化 assistant 消息"""
    if not content:
        return ""
    
    content = content.strip()
    
    # 简短系统通知
    if content.startswith("（") and content.endswith("）"):
        return content
    
    # 尝试解析 JSON
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        elif content.startswith("{"):
            start = content.find("{")
            end = content.rfind("}") + 1
            json_str = content[start:end]
        else:
            return content
        
        data = json.loads(json_str)
        parts = []
        
        # 提取 response
        response = data.get("response", data.get("assistant_response", ""))
        if response:
            parts.append(response)
        
        # 提取提问
        inquiry_card = data.get("inquiry_card")
        if inquiry_card and inquiry_card.get("questions"):
            questions = inquiry_card.get("questions", [])
            if questions:
                question_texts = []
                for idx, q in enumerate(questions, 1):
                    if isinstance(q, dict):
                        q_text = q.get("question", "")
                        if q_text:
                            question_texts.append(f"Q{idx}: {q_text}")
                    elif isinstance(q, str):
                        question_texts.append(f"Q{idx}: {q}")
                
                if question_texts:
                    parts.append("【提问】\n" + "\n".join(question_texts))
        
        if parts:
            return "\n".join(parts)
        
        return content
        
    except (json.JSONDecodeError, KeyError, IndexError):
        return content


# ============================================================
# Layer 0: 系统指令
# ============================================================

def _build_layer0_system() -> str:
    """Layer 0: 系统指令区"""
    return """## 信任优先级说明

在分析用户和 Crush 的信息时，请遵守以下信任优先级：

1. **最高可信 - 客观事实**：聊天记录、截图内容、时间戳等直接证据。这是真理。
2. **中等可信 - AI分析**：基于证据的推断。如无新证据反驳，保持沿用。
3. **最低可信 - 用户提供**：用户可能美化自己或误读对方。需用客观事实修正。

> 部分用户口述信息虽无直接证据，但客观性强（如"crush是同班同学"），可视为高可信度信息。"""


# ============================================================
# 格式化函数
# ============================================================

def _extract_current_status_report(state: "AgentState") -> str:
    """提取当前现状分析报告"""
    layer2_memory = state.get("layer2_memory")
    if layer2_memory:
        current = layer2_memory.get("current_status_report")
        if current:
            return _format_status_report_item(current)
    legacy_report = state.get("status_report")
    if isinstance(legacy_report, str) and legacy_report.strip():
        return legacy_report
    if isinstance(legacy_report, dict) and legacy_report:
        if legacy_report.get("report_content"):
            return str(legacy_report.get("report_content") or "")
        return _format_status_report_item(legacy_report)
    return "暂无现状分析报告"


def _extract_current_action_plan(state: "AgentState") -> str:
    """提取当前行动规划"""
    layer2_memory = state.get("layer2_memory")
    if layer2_memory:
        current = layer2_memory.get("current_action_plan")
        if current:
            return _format_action_plan_item(current)
    legacy_plan = state.get("action_plan")
    if isinstance(legacy_plan, str) and legacy_plan.strip():
        return legacy_plan
    if isinstance(legacy_plan, dict) and legacy_plan:
        return _format_action_plan_item(legacy_plan)
    return "暂无行动规划"


def _extract_dynamic_intel(state: "AgentState") -> str:
    """提取动态情报"""
    layer2_memory = state.get("layer2_memory")
    if layer2_memory:
        return _build_dynamic_intel_board(layer2_memory)
    return ""


def _extract_action_guides(state: "AgentState") -> str:
    """提取行动指南"""
    layer2_memory = state.get("layer2_memory")
    if layer2_memory:
        all_guides = layer2_memory.get("action_guides", [])
        if all_guides:
            config = layer2_memory.get("extraction_config", LAYER2_DEFAULT_CONFIG)
            return _format_action_guide_items(all_guides, config)
    legacy_guides = state.get("action_guides")
    if isinstance(legacy_guides, list) and legacy_guides:
        return _format_legacy_action_guides(legacy_guides)
    return "暂无行动指南"


def _extract_layer2_history_summaries(state: "AgentState") -> str:
    """提取 Layer 2 历史摘要"""
    layer2_memory = state.get("layer2_memory")
    if layer2_memory:
        config = layer2_memory.get("extraction_config", LAYER2_DEFAULT_CONFIG)
        return _build_layer2_history_summaries(layer2_memory, config)
    return ""


def _format_bound_contexts(task: Optional[dict]) -> str:
    """格式化当前任务绑定的上下文"""
    if not task or not isinstance(task, dict):
        return ""
    
    bound_contexts = task.get("bound_contexts", [])
    if not bound_contexts or not isinstance(bound_contexts, list):
        return ""
    
    # 按 type 分组
    grouped: dict[str, list[dict]] = {}
    for ctx in bound_contexts:
        if not isinstance(ctx, dict):
            continue
        ctx_type = ctx.get("type", "custom")
        grouped.setdefault(ctx_type, []).append(ctx)
    
    type_labels = {
        "action_guide": "行动指南",
        "status_report": "现状报告",
        "action_plan": "行动规划",
        "crush_chat": "Crush 聊天记录",
        "history_snippet": "历史对话片段",
        "dynamic_intel": "动态情报",
        "custom": "自定义",
    }
    
    sections = ["## 任务绑定上下文", ""]
    
    for ctx_type, items in grouped.items():
        label = type_labels.get(ctx_type, ctx_type)
        sections.append(f"### {label} ({len(items)})")
        for ctx in items:
            bound_at = ctx.get("bound_at", "")
            time_text = _format_display_time(bound_at)
            title = ctx.get("title", "未命名")
            sections.append(f"- [{time_text}] {title}")
        sections.append("")
    
    return "\n".join(sections).strip() if len(sections) > 2 else ""


def _format_status_report_item(item: StatusReportItem) -> str:
    """格式化现状分析报告项"""
    report_id = item.get("report_id", "")
    version = item.get("version", 1)
    created_at = item.get("created_at", "")
    time_text = _format_display_time(created_at)
    
    header = f"> 更新时间: {time_text} | 版本: {version}"
    
    if item.get("report_content"):
        content = item["report_content"]
        return f"{header}\n\n\"\"\"\n{content}\n\"\"\""
    
    parts = [header]
    if item.get("stage"):
        parts.append(f"**关系阶段**: {item['stage']}")
    if item.get("stage_description"):
        parts.append(f"**阶段描述**: {item['stage_description']}")
    if item.get("key_issues"):
        issues = "\n".join(f"- {issue}" for issue in item["key_issues"])
        parts.append(f"**核心问题**:\n{issues}")
    
    return "\n\n".join(parts) if parts else "暂无现状分析报告"


def _format_action_plan_item(item: ActionPlanItem) -> str:
    """格式化行动规划项"""
    plan_id = item.get("plan_id", "")
    version = item.get("version", 1)
    created_at = item.get("created_at", "")
    time_text = _format_display_time(created_at)
    
    header = f"> 更新时间: {time_text} | 版本: {version}"
    
    if item.get("plan_content"):
        content = item["plan_content"]
        return f"{header}\n\n\"\"\"\n{content}\n\"\"\""
    
    parts = [header]
    if item.get("goal"):
        parts.append(f"**阶段性目标**: {item['goal']}")
    if item.get("strategy"):
        parts.append(f"**核心策略**: {item['strategy']}")
    if item.get("key_principles"):
        principles = "\n".join(f"- {p}" for p in item["key_principles"])
        parts.append(f"**关键原则**:\n{principles}")
    
    return "\n\n".join(parts) if parts else "暂无行动规划"


def _format_action_guide_items(items: list[ActionGuideItem], config: dict | None = None) -> str:
    """格式化行动指南列表（渐进式披露）"""
    if not items:
        return "暂无行动指南"
    config = config or LAYER2_DEFAULT_CONFIG
    
    def _escape_cell(val: str) -> str:
        return (val or "").replace("|", "\\|").replace("\n", " ")

    def _sort_by_time(g: dict, key: str) -> str:
        return str(g.get(key) or "")

    in_progress = sorted(
        [g for g in items if g.get("status") == "in_progress"],
        key=lambda g: _sort_by_time(g, "created_at"),
        reverse=True,
    )[: config.get("max_in_progress_guides", 2)]
    paused = sorted(
        [g for g in items if g.get("status") == "paused"],
        key=lambda g: _sort_by_time(g, "created_at"),
        reverse=True,
    )[: config.get("max_paused_guides", 2)]
    pending = sorted(
        [g for g in items if g.get("status") == "pending"],
        key=lambda g: _sort_by_time(g, "expected_start_at") or _sort_by_time(g, "created_at"),
    )[: config.get("max_pending_guides", 3)]
    completed = sorted(
        [g for g in items if g.get("status") == "completed"],
        key=lambda g: _sort_by_time(g, "completed_at") or _sort_by_time(g, "created_at"),
        reverse=True,
    )[: config.get("max_completed_guides", 5)]
    cancelled = sorted(
        [g for g in items if g.get("status") == "cancelled"],
        key=lambda g: _sort_by_time(g, "created_at"),
        reverse=True,
    )[: config.get("max_cancelled_guides", 2)]
    expired = sorted(
        [g for g in items if g.get("status") == "expired"],
        key=lambda g: _sort_by_time(g, "expire_at") or _sort_by_time(g, "created_at"),
        reverse=True,
    )[: config.get("max_expired_guides", 2)]

    sections: list[str] = [
        "> 需要查看某条指南的完整内容时，调用 context_loader(action=\"load\", context_type=\"action_guide\", context_id=\"指南ID\")"
    ]

    # 🔥 进行中：完整展开
    if in_progress:
        sections.append(f"### 🔥 当前进行中 ({len(in_progress)})")
        for guide_item in in_progress:
            guide = guide_item.get("guide", {}) or {}
            guide_id = guide_item.get("id", "")
            title = guide_item.get("title") or guide.get("current_task") or "未命名指南"
            created_at = guide_item.get("created_at", "")
            expire_at = guide_item.get("expire_at", "")
            
            header = f"#### 【{guide_id}】{title}"
            meta = f"> 创建: {_format_display_time(created_at)[:11]}"
            if expire_at:
                meta += f" | 预计过期: {_format_display_time(expire_at)[:5]}"
            sections.append(header)
            sections.append(meta)
            sections.append("")

            guide_content = guide.get("guide_content", "")
            if guide_content:
                sections.append(f"\"\"\"\n{guide_content}\n\"\"\"")
            else:
                if guide.get("steps"):
                    steps = "\n".join(f"{j}. {step}" for j, step in enumerate(guide["steps"], 1))
                    sections.append(f"**步骤**:\n{steps}")
                if guide.get("talking_points"):
                    tps = "\n".join(f"- {tp}" for tp in guide["talking_points"])
                    sections.append(f"**话术要点**:\n{tps}")
            sections.append("---")

    # 非进行中：元数据表格展示
    other_guides = list(paused) + list(pending) + list(completed) + list(cancelled) + list(expired)
    if other_guides:
        sections.append("### 📋 其他指南")
        sections.append("| id | title | status | summary |")
        sections.append("|:---|:------|:-------|:--------|")
        for guide_item in other_guides:
            guide_id = guide_item.get("id", "")
            title = guide_item.get("title") or "未命名指南"
            status = guide_item.get("status", "")
            summary = guide_item.get("summary") or guide_item.get("one_liner") or "暂无"
            if status == "completed":
                feedback_data = guide_item.get("feedback_data") or {}
                feedback_summary = feedback_data.get("feedback_summary") or guide_item.get("user_feedback") or ""
                if feedback_summary:
                    summary = f"{summary} → 反馈: {feedback_summary}"
            sections.append(
                f"| {guide_id} | {_escape_cell(title)} | {status} | {_escape_cell(summary)} |"
            )

    return "\n\n".join(sections) if sections else "暂无行动指南"


def _format_legacy_action_guides(items: list[dict]) -> str:
    """格式化旧版 action_guides（兼容直接注入完整内容）"""
    parts: list[str] = []
    for guide_item in items:
        if not isinstance(guide_item, dict):
            continue
        content = ""
        if isinstance(guide_item.get("guide_content"), str) and guide_item.get("guide_content"):
            content = guide_item.get("guide_content") or ""
        else:
            nested = guide_item.get("guide") if isinstance(guide_item.get("guide"), dict) else {}
            if isinstance(nested.get("guide_content"), str) and nested.get("guide_content"):
                content = nested.get("guide_content") or ""
        if content:
            parts.append(content)
            continue
        title = guide_item.get("title") or guide_item.get("id") or "未命名指南"
        summary = guide_item.get("summary") or guide_item.get("one_liner") or ""
        if summary:
            parts.append(f"## {title}\n\n{summary}")
        else:
            parts.append(f"## {title}")
    return "\n\n".join(parts) if parts else "暂无行动指南"


# ============================================================
# 辅助函数
# ============================================================

def _safe_parse_iso(value: str):
    """解析 ISO 格式时间"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _format_display_time(value: str) -> str:
    """格式化显示时间"""
    dt = _safe_parse_iso(value)
    if not dt:
        return ""
    now = datetime.now()
    if dt.year == now.year:
        return dt.strftime("%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d %H:%M")


def _get_task_registry_from_state(state: "AgentState") -> AgentTaskRegistry:
    """获取 task_registry"""
    merged: dict = {}
    layer3 = state.get("layer3_memory", {}) or {}
    layer3_registry = layer3.get("task_registry", {}) if isinstance(layer3, dict) else {}
    if isinstance(layer3_registry, dict):
        merged.update(layer3_registry)
    return merged  # type: ignore[return-value]


def _get_current_task_id(state: "AgentState", target_agent: str) -> str:
    """获取指定 Agent 的当前活跃任务 ID"""
    task_registry = _get_task_registry_from_state(state)
    task_list = task_registry.get(target_agent, []) or []
    active = get_active_task(task_list) if isinstance(task_list, list) else None
    return active.get("task_id", "") if isinstance(active, dict) else ""


def _get_task_reasoning_notes(task: dict) -> list:
    """获取任务推理笔记"""
    if not isinstance(task, dict):
        return []
    notes = task.get("reasoning_notes")
    if isinstance(notes, list) and notes:
        return list(notes)
    return []


def _normalize_reasoning_note(note: object) -> tuple[str, str]:
    """标准化推理笔记"""
    if isinstance(note, dict):
        return str(note.get("content") or ""), str(note.get("created_at") or "")
    return str(note or ""), ""


def _extract_message_time(msg: dict | object) -> str:
    """提取消息时间"""
    if isinstance(msg, dict):
        return str(msg.get("created_at") or msg.get("timestamp") or "")
    return str(getattr(msg, "created_at", "") or getattr(msg, "timestamp", "") or "")


# ============================================================
# Token 估算和压缩判断
# ============================================================

def estimate_tokens(text: str) -> int:
    """估算文本的 token 数量"""
    if not text:
        return 0
    return len(text) // 2


def estimate_state_tokens(state: "AgentState") -> int:
    """估算整个状态的 token 数量"""
    context = build_context(state, include_layer0=True)
    return estimate_tokens(context)


def should_compress_layer3(state: "AgentState") -> bool:
    """判断 Layer 3 是否需要触发压缩"""
    layer3_memory = state.get("layer3_memory")
    if layer3_memory:
        config = layer3_memory.get("extraction_config", LAYER3_DEFAULT_CONFIG)
        max_turns = config.get("max_recent_turns", 25)
        all_messages = layer3_memory.get("all_messages", [])
        return len(all_messages) > max_turns + 5
    
    messages = state.get("messages", [])
    return len(messages) > LAYER3_DEFAULT_CONFIG["max_recent_turns"] + 5


def check_and_compress_if_needed(state: "AgentState") -> dict:
    """检查并执行压缩（如果需要）"""
    from graph.archive_manager import (
        check_layer3_compression_needed,
        compress_layer3,
    )
    
    if check_layer3_compression_needed(state):
        print(f"[ContextBuilder] Layer 3 compression triggered")
        return compress_layer3(state)
    
    return {}


def get_context_stats(state: "AgentState") -> dict:
    """获取上下文统计信息"""
    layer1_output = extract_layer1(state)
    layer2_output = extract_layer2(state)
    layer3_output = extract_layer3(state)
    
    layer3_memory = state.get("layer3_memory", {})
    all_messages = layer3_memory.get("all_messages", state.get("messages", []))
    
    return {
        "total_messages": len(all_messages),
        "estimated_tokens": estimate_state_tokens(state),
        "compression_needed": should_compress_layer3(state),
        "layers": {
            "layer1_static_intel": estimate_tokens(layer1_output),
            "layer2_working": estimate_tokens(layer2_output),
            "layer3_conversation": estimate_tokens(layer3_output),
        },
    }
