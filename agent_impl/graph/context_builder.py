"""
上下文组装器
实现分层长期记忆架构，从各层长期记忆中提取信息输入到 Agent

基于 context_strategy.md v3.0 策略文档

分层长期记忆架构：
- Layer 0: 系统指令区（只读常驻）
- Layer 1: 静态情报（长期记忆 -> 提取策略 -> 输出）
- Layer 2: 工作上下文（长期记忆 -> 提取策略 -> 输出）
- Layer 3: 对话历史（长期记忆 -> 提取策略 -> 输出）
"""

import json
from typing import TYPE_CHECKING, Optional, Literal, Any

if TYPE_CHECKING:
    from graph.state import AgentState

from graph.context_types import (
    # Layer 1
    UserContext,
    Layer1Memory,
    Layer1ExtractionConfig,
    # Layer 2
    Layer2Memory,
    Layer2ExtractionConfig,
    ActionGuideItem,
    StatusReportItem,
    ActionPlanItem,
    get_current_status_report,
    get_current_action_plan,
    get_active_action_guides,
    get_history_status_reports,
    get_history_action_plans,
    get_completed_action_guides,
    get_valid_dynamic_intels,
    # Layer 3
    Layer3Memory,
    Layer3ExtractionConfig,
    ConversationSummary,
    # 其他
    AgentTaskRegistry,
    TaskState,
    HistoryArchive,
    get_active_task,
    create_empty_user_context,
    # 处理状态
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
# 任务思考过程配置
# ============================================================

TASK_REASONING_CONFIG = {
    "max_reasoning_notes": 10,   # 每个任务最多保留的思考记录数
}


# ============================================================
# Token 预算常量
# ============================================================

TOKEN_BUDGET = {
    "total": 70000,              # 总预算
    "output_reserve": 8000,      # 预留给模型输出
    "layer0_system": 4000,       # 系统指令区
    "layer1_static": 15000,      # 静态情报区
    "layer2_working": 20000,     # 工作上下文
    "layer3_conversation": 15000, # 对话历史（25轮 + 摘要）
    "compression_threshold": 55000,  # 压缩触发阈值
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
}

# Layer 3 默认配置
LAYER3_DEFAULT_CONFIG = {
    "max_recent_turns": 25,      # 完整保留的最近轮次
    "include_summaries": True,   # 是否包含历史摘要
    "max_summary_count": 5,      # 最多包含的摘要条数
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
    
    使用 ExtractionPipeline 包裹，便于后续策略切换
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
    """
    原有的上下文字典构建逻辑，供 ExtractionPipeline 复用
    """
    # 获取各层长期记忆
    layer1_memory = state.get("layer1_memory", {})
    layer2_memory = state.get("layer2_memory", {})
    layer3_memory = state.get("layer3_memory", {})
    task_registry = _get_task_registry_from_state(state)
    
    # 向后兼容：如果没有新版字段，使用旧版
    user_context = layer1_memory.get("full_data") if layer1_memory else state.get("user_context", {})
    
    # Layer 3 配置（用于历史截断）
    layer3_config = layer3_memory.get("extraction_config", LAYER3_DEFAULT_CONFIG) if isinstance(layer3_memory, dict) else LAYER3_DEFAULT_CONFIG
    max_recent_turns = layer3_config.get("max_recent_turns", 25)
    max_summary_count = layer3_config.get("max_summary_count", 5)

    # 当前任务 ID（用于按任务过滤 thought）
    current_task_id = _get_current_task_id(state, target_agent)
    active_task = get_active_task(task_registry.get(target_agent, []) or []) if isinstance(task_registry.get(target_agent, []), list) else None
    scratchpad_notes = []
    scratchpad_summary = ""
    if isinstance(active_task, dict):
        scratchpad_notes = list(active_task.get("reasoning", []) or [])
        scratchpad_summary = str(active_task.get("summary") or "")

    # 交错式对话历史（XML）
    messages = state.get("messages", [])
    summaries = layer3_memory.get("conversation_summaries", []) if isinstance(layer3_memory, dict) else []
    conversation_history = _format_interleaved_history(
        messages=messages,
        current_task_id=current_task_id,
        max_turns=max_recent_turns,
        summaries=summaries[:max_summary_count] if isinstance(summaries, list) else None,
        scratchpad_task_id=current_task_id,
        scratchpad_notes=scratchpad_notes,
        scratchpad_summary=scratchpad_summary,
    ) or "无历史对话"

    # 任务系统：获取任务列表和活跃任务
    task_list = get_task_list_for_agent(state, target_agent)
    task_index = format_task_index(task_list)
    active_task_for_payload = get_active_task_from_list(task_list)
    active_task_payload = format_active_task_payload(active_task_for_payload)

    return {
        # Layer 1: 静态情报
        "user_context": extract_layer1(state) or "暂无用户信息",
        "user_info": _format_info_source(user_context.get("user_info", {}), "用户"),
        "crush_info": _format_crush_info(user_context.get("crush_info", {})),
        "both_info": _format_info_source(user_context.get("both_info", {}), "双方相处"),
        
        # Main Agent -> 专家 Brief（v3.0: OODA）
        # 说明：这是"临时指令"，通常只在 call_status/plan/guide 的当轮有效；
        # 但在子 Agent 需要提问并 resume 的情况下，也应保留以保证任务连贯。
        "instruction": str(state.get("instruction") or ""),
        
        # Layer 2: 工作上下文
        "status_report": _extract_current_status_report(state),
        "action_plan": _extract_current_action_plan(state),
        "action_guides": _extract_active_guides(state),
        "bound_action_guides": _format_bound_action_guides(active_task_for_payload),
        "history_summaries": _extract_layer2_history_summaries(state),
        
        # Layer 3: 对话历史（交错式 XML）
        "conversation_history": conversation_history,
        "current_task_id": current_task_id,
        
        # 任务系统（Task System）
        "task_index": task_index,  # 任务列表（最近5个 + 活跃标记）
        "active_task_payload": json.dumps(active_task_payload, ensure_ascii=False),  # 当前任务信息
        
        # 任务思考过程（Rolling Scratchpad）- 保留向后兼容
        "task_reasoning": _build_task_reasoning(task_registry, target_agent),
        
        # 兼容旧版变量名
        "user_profile": json.dumps(state.get("user_profile", {}), ensure_ascii=False, indent=2),
        "action_guide": _format_legacy_action_guide(state.get("action_guide")),
    }


# ============================================================
# Layer 1: 静态情报提取
# ============================================================

def extract_layer1(state: "AgentState") -> str:
    """
    从 Layer 1 长期记忆中提取静态情报
    
    提取策略：
    - mode="full": 完整输出所有 3×3 矩阵内容
    - mode="compressed": 对冗长内容做轻量摘要（待实现）
    """
    layer1_memory = state.get("layer1_memory")
    
    # 向后兼容：如果没有新版字段，使用旧版
    if not layer1_memory:
        user_context = state.get("user_context")
        if user_context:
            return _build_layer1_static_intel(user_context)
        return ""
    
    # 获取全量数据和提取配置
    full_data = layer1_memory.get("full_data", {})
    config = layer1_memory.get("extraction_config", LAYER1_DEFAULT_CONFIG)
    
    if not full_data:
        return ""
    
    # 根据模式提取
    mode = config.get("mode", "full")
    
    if mode == "full":
        return _build_layer1_static_intel(full_data)
    elif mode == "compressed":
        # TODO: 实现压缩模式
        max_tokens = config.get("max_tokens", 15000)
        return _build_layer1_compressed(full_data, max_tokens)
    
    return _build_layer1_static_intel(full_data)


def _build_layer1_static_intel(user_context: UserContext) -> str:
    """
    Layer 1: 静态情报区（3×3 矩阵）- 完整模式
    
    完整输入，是 Agent 的"长期记忆核心"
    """
    if not user_context:
        return ""
    
    sections = []
    
    # 用户信息
    user_info = user_context.get("user_info", {})
    if _has_content(user_info):
        sections.append(_format_info_source(user_info, "用户"))
    
    # Crush 信息
    crush_info = user_context.get("crush_info", {})
    if _has_content(crush_info) or crush_info.get("crush_name"):
        sections.append(_format_crush_info(crush_info))
    
    # 双方相处信息
    both_info = user_context.get("both_info", {})
    if _has_content(both_info):
        sections.append(_format_info_source(both_info, "双方相处"))
    
    # 如果所有信息都为空，返回提示
    if not sections:
        return "暂无详细信息，需要进一步了解。"
    
    return "\n\n".join(sections)


def _build_layer1_compressed(user_context: UserContext, max_tokens: int) -> str:
    """
    Layer 1: 静态情报区 - 压缩模式
    
    对冗长内容做轻量摘要，控制在 max_tokens 以内
    TODO: 实现智能压缩逻辑
    """
    # 暂时使用完整模式
    return _build_layer1_static_intel(user_context)


# ============================================================
# Layer 2: 工作上下文提取
# ============================================================

def extract_layer2(state: "AgentState") -> str:
    """
    从 Layer 2 长期记忆中提取工作上下文
    
    提取策略：
    - 当前版本：完整输出
    - 历史版本：摘要分级（最近2份中等摘要，更早的一句话摘要）
    - 行动指南：仅 in_progress 完整展开，其余状态输出元数据（可通过工具按需加载详情）
    """
    layer2_memory = state.get("layer2_memory")
    
    # 向后兼容：如果没有新版字段，使用旧版
    if not layer2_memory:
        return _build_layer2_working_legacy(state)
    
    # 获取提取配置
    config = layer2_memory.get("extraction_config", LAYER2_DEFAULT_CONFIG)
    
    sections = []
    has_content = False
    
    # 1. 当前现状分析报告（完整）
    current_report = get_current_status_report(layer2_memory)
    if current_report:
        has_content = True
        sections.append("### 现状分析报告")
        sections.append(_format_status_report_item(current_report))
    
    # 2. 当前行动规划（完整）
    current_plan = get_current_action_plan(layer2_memory)
    if current_plan:
        has_content = True
        sections.append("### 行动规划")
        sections.append(_format_action_plan_item(current_plan))
    
    # 3. 行动指南（渐进式披露）
    all_guides = layer2_memory.get("all_action_guides", [])
    if all_guides and config.get("include_active_guides", True):
        has_content = True
        sections.append("### 行动指南")
        sections.append(_format_action_guide_items(all_guides))
    
    # 3.5 动态情报板（高优先级）
    intel_section = _build_dynamic_intel_board(layer2_memory)
    if intel_section:
        has_content = True
        sections.append(intel_section)

    # 4. 历史摘要
    history_section = _build_layer2_history_summaries(layer2_memory, config)
    if history_section:
        has_content = True
        sections.append(history_section)
    
    if not has_content:
        return ""
    
    return "\n\n".join(sections)


def _build_layer2_working_legacy(state: "AgentState") -> str:
    """
    Layer 2: 工作上下文 - 旧版兼容
    
    从旧版字段构建工作上下文
    """
    sections = []
    has_content = False
    
    # 现状分析报告
    status_report = state.get("status_report")
    if status_report:
        has_content = True
        sections.append("### 现状分析报告")
        sections.append(_format_status_report(status_report))
    
    # 行动规划
    action_plan = state.get("action_plan")
    if action_plan:
        has_content = True
        sections.append("### 行动规划")
        sections.append(_format_action_plan(action_plan))
    
    # 行动指南
    action_guides = state.get("action_guides", [])
    active_guides = [g for g in action_guides if g.get("status") in ("pending", "in_progress", "paused")]
    if active_guides:
        has_content = True
        sections.append("### 行动指南")
        sections.append(_format_action_guides(active_guides))
    else:
        action_guide = state.get("action_guide")
        if action_guide:
            has_content = True
            sections.append("### 行动指南")
            sections.append(_format_legacy_action_guide(action_guide))
    
    # 历史摘要（从旧版 history_archive）
    history_archive = state.get("history_archive")
    if history_archive:
        history_section = _build_layer4_summaries(history_archive)
        if history_section:
            has_content = True
            sections.append(history_section)
    
    if not has_content:
        return ""
    
    return "\n\n".join(sections)


def _build_layer2_history_summaries(layer2_memory: Layer2Memory, config: dict) -> str:
    """
    构建 Layer 2 历史摘要
    
    摘要分级：
    - 最近 N 份：中等摘要
    - 更早的：一句话摘要
    """
    recent_count = config.get("recent_summary_count", 2)
    max_one_liner = config.get("max_one_liner_count", 10)
    
    sections = []
    
    # 历史现状分析摘要
    history_reports = get_history_status_reports(layer2_memory)
    if history_reports:
        report_section = _format_layer2_history_items(
            history_reports, "历史现状分析", recent_count, max_one_liner
        )
        if report_section:
            sections.append(report_section)
    
    # 历史行动指南摘要（已完成的）
    completed_guides = get_completed_action_guides(layer2_memory)
    if completed_guides:
        guide_section = _format_layer2_history_items(
            completed_guides, "历史行动指南", recent_count, max_one_liner
        )
        if guide_section:
            sections.append(guide_section)
    
    if not sections:
        return ""
    
    return "### 历史档案摘要\n\n" + "\n\n".join(sections)


def _build_dynamic_intel_board(layer2_memory: Layer2Memory) -> str:
    """构建动态情报板"""
    intels = get_valid_dynamic_intels(layer2_memory)
    if not intels:
        return ""

    label_map = {
        "schedule": "日程",
        "mood": "心情",
        "status": "状态",
        "intent": "意图",
    }

    grouped: dict[str, list[str]] = {}
    for intel in intels:
        cat = intel.get("category", "status")
        label = label_map.get(cat, cat)
        expire_at = intel.get("expire_at")
        subject = intel.get("subject", "user")
        prefix = "用户" if subject == "user" else "Crush"
        line = f"- {prefix}: {intel.get('content','')}"
        if expire_at:
            line += f"（有效期至 {expire_at}）"
        grouped.setdefault(label, []).append(line)

    parts = ["### 动态情报板 (请务必参考)"]
    for label, items in grouped.items():
        parts.append(f"#### {label}")
        parts.extend(items)

    return "\n".join(parts)


def _format_layer2_history_items(
    items: list,
    title: str,
    recent_count: int,
    max_one_liner: int
) -> str:
    """格式化 Layer 2 历史项"""
    if not items:
        return ""
    
    parts = [f"#### {title}"]
    
    for i, item in enumerate(items[:recent_count + max_one_liner]):
        if i < recent_count:
            # 最近的用中等摘要
            summary = item.get("summary", item.get("one_liner", ""))
            label = "[最近]" if i == 0 else "[次近]"
        else:
            # 更早的用一句话摘要
            summary = item.get("one_liner", "")
            label = "[更早]"
        
        if summary:
            parts.append(f"- {label} {summary}")
    
    return "\n".join(parts) if len(parts) > 1 else ""


# ============================================================
# Layer 3: 对话历史提取（简化版）
# ============================================================

def extract_layer3(state: "AgentState") -> str:
    """
    从单一数据源 state.messages 提取对话历史：
    1) 历史摘要（layer3_memory.conversation_summaries，最多5条）
    2) 最近对话（默认保留最近25条）
    不再排除当前用户消息，也不做并发降级合并。
    """
    messages = state.get("messages", [])
    layer3_memory = state.get("layer3_memory", {}) or {}
    summaries = layer3_memory.get("conversation_summaries", []) if isinstance(layer3_memory, dict) else []

    config = layer3_memory.get("extraction_config", LAYER3_DEFAULT_CONFIG) if isinstance(layer3_memory, dict) else LAYER3_DEFAULT_CONFIG
    max_recent_turns = config.get("max_recent_turns", 25)
    max_summary_count = config.get("max_summary_count", 5)

    # 尝试用当前 agent 的任务作为过滤目标；如果缺失则退化为 main_agent
    target_agent = state.get("current_agent") or "main_agent"
    current_task_id = _get_current_task_id(state, target_agent)

    task_registry = _get_task_registry_from_state(state)
    active_task = get_active_task(task_registry.get(target_agent, []) or []) if isinstance(task_registry.get(target_agent, []), list) else None
    scratchpad_notes = []
    scratchpad_summary = ""
    if isinstance(active_task, dict):
        scratchpad_notes = list(active_task.get("reasoning", []) or [])
        scratchpad_summary = str(active_task.get("summary") or "")

    history = _format_interleaved_history(
        messages=messages,
        current_task_id=current_task_id,
        max_turns=max_recent_turns,
        summaries=summaries[:max_summary_count] if isinstance(summaries, list) else None,
        scratchpad_task_id=current_task_id,
        scratchpad_notes=scratchpad_notes,
        scratchpad_summary=scratchpad_summary,
    )
    return history or "无历史对话"


def _build_layer3_conversation_legacy(messages: list, max_turns: int = None) -> str:
    """
    Layer 3: 对话历史 - 旧版兼容
    
    保留最近 N 轮完整对话
    """
    if not messages:
        return "无历史对话"
    
    if max_turns is None:
        max_turns = LAYER3_DEFAULT_CONFIG["max_recent_turns"]
    
    # 过滤并格式化消息
    valid_messages = []
    for msg in messages:
        msg_role, msg_content = get_msg_role_and_content(msg)
        if msg_role in ("user", "assistant", "ai"):
            if msg_role in ("assistant", "ai"):
                msg_content = _format_assistant_message_for_history(msg_content)
            valid_messages.append((msg_role, msg_content))
    
    # 只保留最近 N 条有效消息
    recent = valid_messages[-max_turns:] if len(valid_messages) > max_turns else valid_messages
    
    formatted = []
    for msg_role, msg_content in recent:
        if msg_role == "user":
            role = "用户"
        elif msg_role in ("assistant", "ai"):
            role = "小话"
        else:
            continue
        
        if not msg_content or not msg_content.strip():
            continue
            
        formatted.append(f"**{role}**: {msg_content}")
    
    return "\n\n".join(formatted)


def _format_conversation_summaries(summaries: list[ConversationSummary]) -> str:
    """格式化对话摘要列表"""
    if not summaries:
        return ""
    
    parts = ["#### 历史对话摘要"]
    for summary in summaries:
        text = summary.get("summary", "")
        topics = summary.get("key_topics", [])
        if text:
            topic_str = f"（话题：{', '.join(topics)}）" if topics else ""
            parts.append(f"- {text}{topic_str}")
    
    return "\n".join(parts) if len(parts) > 1 else ""


def _format_recent_messages(messages: list, max_turns: int) -> str:
    """格式化最近的消息"""
    if not messages:
        return ""
    
    # 过滤并格式化消息
    valid_messages = []
    for msg in messages:
        msg_role, msg_content = get_msg_role_and_content(msg)
        if msg_role in ("user", "assistant", "ai"):
            if msg_role in ("assistant", "ai"):
                msg_content = _format_assistant_message_for_history(msg_content)
            valid_messages.append((msg_role, msg_content))
    
    # 只保留最近 N 条
    recent = valid_messages[-max_turns:] if len(valid_messages) > max_turns else valid_messages
    
    parts = ["#### 最近对话"]
    for msg_role, msg_content in recent:
        if msg_role == "user":
            role = "用户"
        elif msg_role in ("assistant", "ai"):
            role = "小话"
        else:
            continue
        
        if not msg_content or not msg_content.strip():
            continue
            
        parts.append(f"**{role}**: {msg_content}")
    
    return "\n\n".join(parts) if len(parts) > 1 else ""


def _format_assistant_message_for_history(content: str) -> str:
    """
    格式化 assistant 消息用于对话历史
    
    处理规则：
    1. 如果是 JSON 格式，提取 response 字段
    2. 如果包含 inquiry_card，提取问题文本（不含选项）
    3. 如果是报告产出通知（如"报告N已生成"），保持原样
    """
    if not content:
        return ""
    
    content = content.strip()
    
    # 如果是简短的系统通知（如报告产出），直接返回
    if content.startswith("（") and content.endswith("）"):
        return content
    
    # 尝试解析 JSON
    try:
        # 提取 JSON 部分
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
        
        # 1. 提取 response
        response = data.get("response", data.get("assistant_response", ""))
        if response:
            parts.append(response)
        
        # 2. 如果有 inquiry_card，提取问题文本
        inquiry_card = data.get("inquiry_card")
        if inquiry_card and inquiry_card.get("questions"):
            questions = inquiry_card.get("questions", [])
            if questions:
                question_texts = []
                for q in questions:
                    if isinstance(q, dict):
                        q_text = q.get("question", "")
                        if q_text:
                            question_texts.append(f"- {q_text}")
                    elif isinstance(q, str):
                        question_texts.append(f"- {q}")
                
                if question_texts:
                    parts.append("【提问】\n" + "\n".join(question_texts))
        
        if parts:
            return "\n".join(parts)
        
        return content
        
    except (json.JSONDecodeError, KeyError, IndexError):
        return content


# ============================================================
# 交错式对话历史（XML，按任务过滤 thought）
# ============================================================

def _xml_escape(text: str) -> str:
    """最小化 XML 转义，避免 <thought> 等结构被破坏。"""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _try_parse_llm_json(content: str) -> dict | None:
    """
    从 LLM 输出中尽量提取 JSON 对象（兼容 ```json fenced``` / 裸 JSON / 夹杂文本）。
    失败返回 None。
    """
    if not content:
        return None

    content = content.strip()
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
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                json_str = content[start:end]
            else:
                return None

        return json.loads(json_str)
    except Exception:
        return None


def _get_task_registry_from_state(state: "AgentState") -> AgentTaskRegistry:
    """
    获取 task_registry（兼容两种存放位置）：
    - legacy: state.task_registry
    - v3.x: state.layer3_memory.task_registry
    """
    merged: dict = {}
    legacy = state.get("task_registry", {}) or {}
    if isinstance(legacy, dict):
        merged.update(legacy)

    layer3 = state.get("layer3_memory", {}) or {}
    layer3_registry = layer3.get("task_registry", {}) if isinstance(layer3, dict) else {}
    if isinstance(layer3_registry, dict):
        merged.update(layer3_registry)

    return merged  # type: ignore[return-value]


def _get_current_task_id(state: "AgentState", target_agent: str) -> str:
    """获取指定 Agent 的当前活跃任务 ID。"""
    task_registry = _get_task_registry_from_state(state)
    task_list = task_registry.get(target_agent, []) or []
    active = get_active_task(task_list) if isinstance(task_list, list) else None
    return active.get("task_id", "") if isinstance(active, dict) else ""


def _format_interleaved_history(
    messages: list,
    current_task_id: str,
    max_turns: int = 25,
    summaries: list | None = None,
    scratchpad_task_id: str = "",
    scratchpad_notes: list[str] | None = None,
    scratchpad_summary: str = "",
) -> str:
    """
    构建交错式对话历史（XML），并按任务过滤 thought：
    - 如果某条 assistant 消息的 task_id != current_task_id，则不输出 thought
    - 如果 task_id 缺失，则默认不输出 thought
    """
    if not messages:
        return ""

    # 仅保留最近 N 个“用户轮次”相关的消息（比简单截 N 条 message 更稳定）
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

    turns: list[dict] = []
    current_turn: dict | None = None

    def _ensure_turn():
        nonlocal current_turn
        if current_turn is None:
            current_turn = {
                "user": "",
                "assistant": "",
                "thought": "",
                "task_id": "",
                "tool_outputs": [],
            }
            turns.append(current_turn)

    for msg in recent_msgs:
        role, content = get_msg_role_and_content(msg)

        if role == "user":
            # 开启新 turn
            current_turn = {
                "user": content or "",
                "assistant": "",
                "thought": "",
                "task_id": "",
                "tool_outputs": [],
            }
            turns.append(current_turn)
            continue

        if role == "tool":
            # 重要：tool 输出只对“当次二阶段”有效，不应写入对话历史（否则上下文会爆炸）
            # tool 返回内容仍保留在 state.messages 中，供各 Agent 的 from_tool_call 逻辑读取。
            continue

        if role in ("assistant", "ai"):
            _ensure_turn()

            meta_task_id = ""
            meta_thought = ""
            if isinstance(msg, dict):
                md = msg.get("metadata", {}) or {}
                if isinstance(md, dict):
                    meta_task_id = str(md.get("task_id") or "")
                    meta_thought = str(md.get("thought") or "")

            parsed = _try_parse_llm_json(content) if content else None
            msg_task_id = ""
            msg_thought = ""
            if isinstance(parsed, dict):
                msg_task_id = str(parsed.get("task_id") or "")
                msg_thought = str(parsed.get("thought") or "")
                task_update = parsed.get("task_update", {}) if isinstance(parsed.get("task_update"), dict) else {}
                if not msg_thought and isinstance(task_update, dict):
                    msg_thought = str(task_update.get("reasoning_note") or "")
                if not msg_task_id and isinstance(task_update, dict) and task_update.get("action") == "new":
                    msg_task_id = str(task_update.get("task_id") or "")

            if not msg_task_id:
                msg_task_id = meta_task_id
            if not msg_thought:
                msg_thought = meta_thought

            assistant_text = _format_assistant_message_for_history(content) if content else ""
            if assistant_text and not current_turn.get("assistant"):
                current_turn["assistant"] = assistant_text
            elif assistant_text:
                # 同一 user 后出现多个 assistant（可能来自子 Agent），拆成新的 turn
                current_turn = {
                    "user": "",
                    "assistant": assistant_text,
                    "thought": "",
                    "task_id": "",
                    "tool_outputs": [],
                }
                turns.append(current_turn)

            # 记录 task_id（用于 turn 属性）
            if msg_task_id and not current_turn.get("task_id"):
                current_turn["task_id"] = msg_task_id

            # 仅同任务输出 thought
            if msg_task_id and current_task_id and msg_task_id == current_task_id and msg_thought:
                # 如果已有 thought，拼接（多条 assistant 连续 thought）
                if current_turn.get("thought"):
                    current_turn["thought"] = f"{current_turn['thought']}\n{msg_thought}"
                else:
                    current_turn["thought"] = msg_thought

    if not turns:
        return ""

    lines = ["<conversation_history>"]

    if summaries:
        lines.append("  <conversation_summaries>")
        for i, s in enumerate(summaries, 1):
            if not isinstance(s, dict):
                continue
            text = (s.get("summary") or "").strip()
            topics = s.get("key_topics", []) or []
            topic_str = ""
            if isinstance(topics, list) and topics:
                topic_str = f" topics=\"{_xml_escape(','.join([str(t) for t in topics if t]))}\""
            if text:
                lines.append(f'    <summary index="{i}"{topic_str}>{_xml_escape(text)}</summary>')
        lines.append("  </conversation_summaries>")

    # 任务级滚动思考（Rolling Scratchpad）——只注入“当前任务”
    if scratchpad_task_id and (scratchpad_notes or scratchpad_summary):
        lines.append(f'  <task_scratchpad task="{_xml_escape(scratchpad_task_id)}">')
        if scratchpad_summary:
            lines.append(f"    <summary>{_xml_escape(str(scratchpad_summary))}</summary>")
        if scratchpad_notes:
            for i, note in enumerate(scratchpad_notes, 1):
                note = (note or "").strip()
                if note:
                    lines.append(f'    <note index="{i}">{_xml_escape(note)}</note>')
        lines.append("  </task_scratchpad>")

    lines.append("  <recent_turns>")
    for idx, t in enumerate(turns, 1):
        task_attr = _xml_escape(str(t.get("task_id", "") or ""))
        lines.append(f'    <turn index="{idx}" task="{task_attr}">')

        user_text = (t.get("user") or "").strip()
        if user_text:
            lines.append(f"      <user>{_xml_escape(user_text)}</user>")

        thought_text = (t.get("thought") or "").strip()
        if thought_text:
            lines.append(f"      <thought>{_xml_escape(thought_text)}</thought>")

        assistant_text = (t.get("assistant") or "").strip()
        if assistant_text:
            lines.append(f"      <assistant>{_xml_escape(assistant_text)}</assistant>")

        # 重要：不在对话历史中渲染 tool 输出，避免跨轮次累计导致上下文膨胀。

        lines.append("    </turn>")

    lines.append("  </recent_turns>")
    lines.append("</conversation_history>")
    return "\n".join(lines)


# ============================================================
# Layer 0: 系统指令
# ============================================================

def _build_layer0_system() -> str:
    """
    Layer 0: 系统指令区
    
    通常这部分在 Prompt 模板文件中定义，这里提供信任优先级说明
    """
    return """## 信任优先级说明

在分析用户和 Crush 的信息时，请遵守以下信任优先级：

1. **最高可信 - 客观事实**：聊天记录、截图内容、时间戳等直接证据。这是真理。
2. **中等可信 - AI分析**：基于证据的推断。如无新证据反驳，保持沿用。
3. **最低可信 - 用户提供**：用户可能美化自己或误读对方。需用客观事实修正。

> 部分用户口述信息虽无直接证据，但客观性强（如"crush是同班同学"），可视为高可信度信息。"""


# ============================================================
# 任务思考过程
# ============================================================

def _build_task_reasoning(task_registry: AgentTaskRegistry, target_agent: str) -> str:
    """
    构建当前任务的思考过程（Rolling Scratchpad）
    """
    if not task_registry:
        return ""
    
    task_list = task_registry.get(target_agent, [])
    if not task_list:
        return ""
    
    active_task = get_active_task(task_list)
    if not active_task:
        return ""
    
    task_id = active_task.get("task_id", "未命名任务")
    reasoning = active_task.get("reasoning", [])
    
    if not reasoning:
        return ""
    
    max_notes = TASK_REASONING_CONFIG["max_reasoning_notes"]
    recent_reasoning = reasoning[-max_notes:]
    
    lines = [
        f"## 当前任务思考过程",
        f"**任务**: {task_id}",
        "",
        "**思考记录**（仅你可见，用户看不到）:",
    ]
    
    for i, note in enumerate(recent_reasoning, 1):
        lines.append(f"{i}. {note}")
    
    return "\n".join(lines)


# ============================================================
# 格式化辅助函数
# ============================================================

def _format_info_source(info: dict, label: str) -> str:
    """格式化信息来源三元组"""
    parts = [f"#### {label}信息"]
    
    user_provide = info.get("user_provide", "").strip()
    fact = info.get("fact", "").strip()
    ai_provide = info.get("ai_provide", "").strip()
    
    if user_provide:
        parts.append(f"##### 由用户提供的信息\n{user_provide}")
    if fact:
        parts.append(f"##### 客观事实\n{fact}")
    if ai_provide:
        parts.append(f"##### 军师分析得出的信息\n{ai_provide}")
    
    if len(parts) == 1:
        parts.append("暂无信息")
    
    return "\n\n".join(parts)


def _format_crush_info(crush_info: dict) -> str:
    """格式化 Crush 信息"""
    parts = ["#### Crush 信息"]
    
    crush_name = crush_info.get("crush_name", "").strip()
    if crush_name:
        parts.append(f"##### Crush 名称或昵称\n{crush_name}")
    
    user_provide = crush_info.get("user_provide", "").strip()
    fact = crush_info.get("fact", "").strip()
    ai_provide = crush_info.get("ai_provide", "").strip()
    
    if user_provide:
        parts.append(f"##### 由用户提供的信息\n{user_provide}")
    if fact:
        parts.append(f"##### 客观事实\n{fact}")
    if ai_provide:
        parts.append(f"##### 军师分析得出的信息\n{ai_provide}")
    
    if len(parts) == 1:
        parts.append("暂无 Crush 信息")
    
    return "\n\n".join(parts)


def _has_content(info: dict) -> bool:
    """检查信息源是否有内容"""
    return bool(
        info.get("user_provide", "").strip() or
        info.get("fact", "").strip() or
        info.get("ai_provide", "").strip()
    )


# ============================================================
# Layer 2 格式化函数
# ============================================================

def _extract_current_status_report(state: "AgentState") -> str:
    """提取当前现状分析报告"""
    layer2_memory = state.get("layer2_memory")
    if layer2_memory:
        current = get_current_status_report(layer2_memory)
        if current:
            return _format_status_report_item(current)
    
    # 向后兼容
    status_report = state.get("status_report")
    if status_report:
        return _format_status_report(status_report)
    
    return "暂无现状分析报告"


def _extract_current_action_plan(state: "AgentState") -> str:
    """提取当前行动规划"""
    layer2_memory = state.get("layer2_memory")
    if layer2_memory:
        current = get_current_action_plan(layer2_memory)
        if current:
            return _format_action_plan_item(current)
    
    # 向后兼容
    action_plan = state.get("action_plan")
    if action_plan:
        return _format_action_plan(action_plan)
    
    return "暂无行动规划"


def _extract_active_guides(state: "AgentState") -> str:
    """提取行动指南（渐进式披露）"""
    layer2_memory = state.get("layer2_memory")
    if layer2_memory:
        all_guides = layer2_memory.get("all_action_guides", [])
        if all_guides:
            return _format_action_guide_items(all_guides)
    
    # 向后兼容
    action_guides = state.get("action_guides", [])
    active_guides = [g for g in action_guides if g.get("status") in ("pending", "in_progress", "paused")]
    if active_guides:
        # 旧版结构缺少 title/one_liner 等字段，这里仍走旧版格式化，避免展示异常
        return _format_action_guides(active_guides)
    
    action_guide = state.get("action_guide")
    if action_guide:
        return _format_legacy_action_guide(action_guide)
    
    return "暂无行动指南"


def _extract_layer2_history_summaries(state: "AgentState") -> str:
    """提取 Layer 2 历史摘要"""
    layer2_memory = state.get("layer2_memory")
    if layer2_memory:
        config = layer2_memory.get("extraction_config", LAYER2_DEFAULT_CONFIG)
        return _build_layer2_history_summaries(layer2_memory, config)
    
    # 向后兼容
    history_archive = state.get("history_archive")
    if history_archive:
        return _build_layer4_summaries(history_archive)
    
    return ""


def _format_bound_action_guides(task: Optional[dict]) -> str:
    """
    格式化当前任务绑定的行动指南详情
    
    仅对当前活跃任务的 bound_action_guides 进行格式化
    用于跨轮次持久注入上下文
    
    Args:
        task: 当前活跃任务（TaskState）
    
    Returns:
        Markdown 格式的绑定指南详情区块
    """
    if not task or not isinstance(task, dict):
        return ""
    
    bound_guides = task.get("bound_action_guides", [])
    if not bound_guides or not isinstance(bound_guides, list):
        return ""
    
    sections = ["### 任务绑定的行动指南详情（仅当前任务可见）", ""]
    
    for bg in bound_guides:
        if not isinstance(bg, dict):
            continue
        
        guide_id = bg.get("guide_id", "")
        title = bg.get("title", "未命名指南")
        status = bg.get("status", "pending")
        content_md = bg.get("content_md", "")
        bound_at = bg.get("bound_at", "")
        
        # 标题行
        header = f"#### 指南 {guide_id}: {title} ({status})"
        if bound_at:
            header += f" [绑定于 {bound_at[:10]}]"
        sections.append(header)
        sections.append("")
        
        # 内容
        if content_md:
            sections.append(content_md)
        else:
            sections.append("（无详细内容）")
        
        sections.append("")  # 空行分隔
    
    return "\n".join(sections).strip() if len(sections) > 2 else ""


def _format_status_report_item(item: StatusReportItem) -> str:
    """格式化现状分析报告项（新版）"""
    report_id = item.get("report_id", "")
    header = f"【报告{report_id}】" if report_id else ""
    
    if item.get("report_content"):
        content = item["report_content"]
        if header:
            return f"{header}\n\n{content}"
        return content
    
    parts = []
    if header:
        parts.append(header)
    if item.get("stage"):
        parts.append(f"**关系阶段**: {item['stage']}")
    if item.get("stage_description"):
        parts.append(f"**阶段描述**: {item['stage_description']}")
    if item.get("key_issues"):
        issues = "\n".join(f"- {issue}" for issue in item["key_issues"])
        parts.append(f"**核心问题**:\n{issues}")
    
    return "\n\n".join(parts) if parts else "暂无现状分析报告"


def _format_action_plan_item(item: ActionPlanItem) -> str:
    """格式化行动规划项（新版）"""
    plan_id = item.get("plan_id", "")
    header = f"【规划{plan_id}】" if plan_id else ""
    
    if item.get("plan_content"):
        content = item["plan_content"]
        if header:
            return f"{header}\n\n{content}"
        return content
    
    parts = []
    if header:
        parts.append(header)
    if item.get("goal"):
        parts.append(f"**阶段性目标**: {item['goal']}")
    if item.get("strategy"):
        parts.append(f"**核心策略**: {item['strategy']}")
    if item.get("key_principles"):
        principles = "\n".join(f"- {p}" for p in item["key_principles"])
        parts.append(f"**关键原则**:\n{principles}")
    
    return "\n\n".join(parts) if parts else "暂无行动规划"


def _format_action_guide_items(items: list[ActionGuideItem]) -> str:
    """格式化行动指南列表（新版：渐进式披露）"""
    if not items:
        return "暂无行动指南"
    
    def _escape_cell(val: str) -> str:
        # Markdown 表格里需要转义竖线
        return (val or "").replace("|", "\\|").replace("\n", " ")

    in_progress = [g for g in items if g.get("status") == "in_progress"]
    others = [g for g in items if g.get("status") != "in_progress"]

    sections: list[str] = []

    # 进行中：完整展开
    if in_progress:
        sections.append("#### 当前进行中")
        for guide_item in in_progress:
            guide = guide_item.get("guide", {}) or {}
            guide_id = guide_item.get("guide_id")
            header = f"【指南{guide_id}】" if guide_id else ""

            title = (
                guide_item.get("title")
                or guide.get("current_task")
                or (f"指南{guide_id}" if guide_id else "未命名指南")
            )
            display = f"{header} {title}".strip()

            guide_content = guide.get("guide_content", "")
            if guide_content:
                sections.append(f"**{display}**\n\n{guide_content}")
                continue

            # 降级：结构化字段
            sections.append(f"**{display}**")
            if guide.get("steps"):
                steps = "\n".join(f"{j}. {step}" for j, step in enumerate(guide["steps"], 1))
                sections.append(f"**步骤**:\n{steps}")
            if guide.get("talking_points"):
                tps = "\n".join(f"- {tp}" for tp in guide["talking_points"])
                sections.append(f"**话术要点**:\n{tps}")
            if guide.get("next_milestone"):
                sections.append(f"**下一里程碑**: {guide['next_milestone']}")

    # 其他状态：只展示元数据（表格）
    if others:
        sections.append("#### 其他指南（可通过 `load_action_guide_detail` 工具按需加载详情）")
        sections.append("| ID | 标题 | 状态 | 摘要 |")
        sections.append("|-----|------|------|------|")
        for guide_item in others:
            gid = _escape_cell(str(guide_item.get("id", "")))
            guide = guide_item.get("guide", {}) or {}
            guide_id = guide_item.get("guide_id")
            title = (
                guide_item.get("title")
                or guide.get("current_task")
                or (f"指南{guide_id}" if guide_id else "未命名指南")
            )
            status = str(guide_item.get("status", "pending"))
            one_liner = (
                guide_item.get("one_liner")
                or guide_item.get("summary")
                or "暂无摘要"
            )
            sections.append(
                f"| {gid} | {_escape_cell(title)} | {_escape_cell(status)} | {_escape_cell(one_liner)} |"
            )

    return "\n\n".join(sections) if sections else "暂无行动指南"


# ============================================================
# 旧版兼容格式化函数
# ============================================================

def _format_status_report(status_report) -> str:
    """格式化现状分析报告（旧版兼容，支持 string 和 dict）"""
    if not status_report:
        return "暂无现状分析报告"
    
    # 新版：status_report 是 Markdown string
    if isinstance(status_report, str):
        return status_report
    
    # 旧版兼容：status_report 是 dict
    report_id = status_report.get("report_id", "")
    header = f"【报告{report_id}】" if report_id else ""
    
    if status_report.get("report_content"):
        content = status_report["report_content"]
        if header:
            return f"{header}\n\n{content}"
        return content
    
    parts = []
    if header:
        parts.append(header)
    if status_report.get("stage"):
        parts.append(f"**关系阶段**: {status_report['stage']}")
    if status_report.get("stage_description"):
        parts.append(f"**阶段描述**: {status_report['stage_description']}")
    if status_report.get("summary"):
        parts.append(f"**总结**: {status_report['summary']}")
    if status_report.get("key_issues"):
        issues = "\n".join(f"- {issue}" for issue in status_report["key_issues"])
        parts.append(f"**核心问题**:\n{issues}")
    if status_report.get("risk_points"):
        risks = "\n".join(f"- {risk}" for risk in status_report["risk_points"])
        parts.append(f"**风险点**:\n{risks}")
    
    return "\n\n".join(parts) if parts else "暂无现状分析报告"


def _format_action_plan(action_plan) -> str:
    """格式化行动规划（旧版兼容，支持 string 和 dict）"""
    if not action_plan:
        return "暂无行动规划"
    
    # 新版：action_plan 是 Markdown string
    if isinstance(action_plan, str):
        return action_plan
    
    # 旧版兼容：action_plan 是 dict
    plan_id = action_plan.get("plan_id", "")
    header = f"【规划{plan_id}】" if plan_id else ""
    
    parts = []
    if header:
        parts.append(header)
    if action_plan.get("goal"):
        parts.append(f"**阶段性目标**: {action_plan['goal']}")
    if action_plan.get("strategy"):
        parts.append(f"**核心策略**: {action_plan['strategy']}")
    if action_plan.get("summary"):
        parts.append(f"**总结**: {action_plan['summary']}")
    if action_plan.get("key_principles"):
        principles = "\n".join(f"- {p}" for p in action_plan["key_principles"])
        parts.append(f"**关键原则**:\n{principles}")
    
    return "\n\n".join(parts) if parts else "暂无行动规划"


def _format_action_guides(action_guides: list) -> str:
    """格式化行动指南列表（支持新旧两种格式）"""
    if not action_guides:
        return "暂无行动指南"
    
    parts = []
    for i, item in enumerate(action_guides, 1):
        status = item.get("status", "pending")
        status_emoji = {
            "pending": "⏳",
            "in_progress": "🔄",
            "paused": "⏸️",
            "completed": "✅",
            "cancelled": "🚫",
            "expired": "⌛",
        }.get(status, "")
        
        # 新版格式：guide_content 直接在 item 中
        guide_content = item.get("guide_content", "")
        guide_id = item.get("id", "") or item.get("guide_id", "")
        
        # 旧版兼容：guide_content 在嵌套的 guide 对象中
        if not guide_content:
            guide = item.get("guide", {})
            if isinstance(guide, dict):
                guide_content = guide.get("guide_content", "")
                guide_id = guide_id or guide.get("guide_id", "")
        
        id_label = f"【指南{guide_id}】" if guide_id else f"#### 指南 {i}"
        
        if guide_content:
            parts.append(f"{id_label} {status_emoji}\n{guide_content}")
        else:
            # 兜底：尝试从旧格式获取任务信息
            guide = item.get("guide", {}) if isinstance(item.get("guide"), dict) else {}
            current_task = guide.get("current_task", "未命名任务")
            parts.append(f"{id_label} {status_emoji}: {current_task}")
            if guide.get("steps"):
                steps = "\n".join(f"{j}. {step}" for j, step in enumerate(guide["steps"], 1))
                parts.append(f"**步骤**:\n{steps}")
    
    return "\n\n".join(parts)


def _format_legacy_action_guide(action_guide) -> str:
    """格式化旧版单个行动指南（支持 string 和 dict）"""
    if not action_guide:
        return "暂无行动指南"
    
    # 新版：action_guide 是 Markdown string
    if isinstance(action_guide, str):
        return action_guide
    
    # 旧版兼容：action_guide 是 dict
    if action_guide.get("guide_content"):
        return action_guide["guide_content"]
    
    parts = []
    if action_guide.get("current_task"):
        parts.append(f"**当前任务**: {action_guide['current_task']}")
    if action_guide.get("steps"):
        steps = "\n".join(f"{i}. {step}" for i, step in enumerate(action_guide["steps"], 1))
        parts.append(f"**具体步骤**:\n{steps}")
    if action_guide.get("next_milestone"):
        parts.append(f"**下一个里程碑**: {action_guide['next_milestone']}")
    
    return "\n\n".join(parts) if parts else "暂无行动指南"


def _build_layer4_summaries(history_archive: HistoryArchive) -> str:
    """
    旧版 Layer 4 历史摘要（向后兼容）
    """
    if not history_archive:
        return ""
    
    sections = []
    
    # 历史现状分析摘要
    status_history = history_archive.get("status_history", [])
    if status_history:
        status_section = _format_history_summaries(status_history, "历史现状分析")
        if status_section:
            sections.append(status_section)
    
    # 历史行动指南摘要
    guide_history = history_archive.get("guide_history", [])
    if guide_history:
        guide_section = _format_history_summaries(guide_history, "历史行动指南")
        if guide_section:
            sections.append(guide_section)
    
    # 对话归档摘要
    conversation_archive = history_archive.get("conversation_archive", [])
    if conversation_archive:
        conv_section = _format_conversation_archive(conversation_archive)
        if conv_section:
            sections.append(conv_section)
    
    if not sections:
        return ""
    
    return "### 历史档案摘要\n\n" + "\n\n".join(sections)


def _format_history_summaries(history_list: list, title: str) -> str:
    """格式化历史摘要列表（旧版）"""
    if not history_list:
        return ""
    
    parts = [f"#### {title}"]
    recent_count = LAYER2_DEFAULT_CONFIG["recent_summary_count"]
    
    for i, item in enumerate(history_list):
        if i < recent_count:
            summary = item.get("summary", item.get("one_liner", ""))
            label = "[最近]" if i == 0 else "[次近]"
        else:
            summary = item.get("one_liner", "")
            label = "[更早]"
        
        if summary:
            parts.append(f"- {label} {summary}")
    
    return "\n".join(parts) if len(parts) > 1 else ""


def _format_conversation_archive(archive_list: list) -> str:
    """格式化对话归档（旧版）"""
    if not archive_list:
        return ""
    
    parts = ["#### 历史对话归档"]
    for item in archive_list[:5]:
        summary = item.get("summary", "")
        if summary:
            parts.append(f"- {summary}")
    
    return "\n".join(parts) if len(parts) > 1 else ""


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
    """
    判断 Layer 3 是否需要触发压缩
    
    触发条件：对话轮次超过 max_recent_turns + 5
    """
    layer3_memory = state.get("layer3_memory")
    if layer3_memory:
        config = layer3_memory.get("extraction_config", LAYER3_DEFAULT_CONFIG)
        max_turns = config.get("max_recent_turns", 25)
        all_messages = layer3_memory.get("all_messages", [])
        return len(all_messages) > max_turns + 5
    
    # 向后兼容
    messages = state.get("messages", [])
    return len(messages) > LAYER3_DEFAULT_CONFIG["max_recent_turns"] + 5


def get_compression_priority() -> list[str]:
    """
    获取压缩优先级（从先到后）
    """
    return [
        "layer3_conversation",
        "layer2_history_summaries",
        "layer2_completed_guides",
        "layer1_static_intel",
    ]


# ============================================================
# 压缩触发集成
# ============================================================

def check_and_compress_if_needed(state: "AgentState") -> dict:
    """
    检查并执行压缩（如果需要）
    
    压缩策略：
    - Layer 3: 超出 30 轮后（25 + 5），每超出 5 轮压缩一次
    - 压缩后保留最近 25 轮完整对话
    - 被压缩的对话生成摘要存入 layer3_memory.conversation_summaries
    """
    from graph.archive_manager import (
        check_layer3_compression_needed,
        compress_layer3,
    )
    
    if check_layer3_compression_needed(state):
        print(f"[ContextBuilder] Layer 3 compression triggered")
        return compress_layer3(state)
    
    return {}


def get_context_stats(state: "AgentState") -> dict:
    """获取上下文统计信息（用于监控和调试）"""
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
