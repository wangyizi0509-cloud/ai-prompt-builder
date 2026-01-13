"""
上下文组装器
实现分层上下文架构，组装各层信息输入到 Agent

基于 context_strategy.md 策略文档

分层架构：
- Layer 0: 系统指令区（只读常驻）
- Layer 1: 静态情报区（3×3 矩阵）
- Layer 2: 工作上下文（报告/规划/未执行指南）
- Layer 3: 滚动对话区（最近 N 轮）
- Layer 4: 外部长期记忆（历史摘要）
"""

import json
from typing import TYPE_CHECKING, Optional, Literal

if TYPE_CHECKING:
    from graph.state import AgentState

from graph.context_types import (
    UserContext,
    HistoryArchive,
    ActionGuideItem,
)


# ============================================================
# Token 预算常量
# ============================================================

TOKEN_BUDGET = {
    "total": 70000,              # 总预算
    "output_reserve": 8000,      # 预留给模型输出
    "layer0_system": 4000,       # 系统指令区
    "layer1_static": 15000,      # 静态情报区（前期不压缩）
    "layer2_working": 20000,     # 工作上下文
    "layer3_conversation": 20000, # 滚动对话区（30-50轮）
    "layer4_summaries": 3000,    # 历史摘要（常驻部分）
    "compression_threshold": 55000,  # 压缩触发阈值
}

# 对话参数
CONVERSATION_CONFIG = {
    "max_recent_turns": 40,      # 最大保留轮次
    "tokens_per_turn": 450,      # 每轮估算 token
    "compression_trigger_turns": 50,  # 触发压缩的轮次阈值
}

# 历史摘要参数
HISTORY_CONFIG = {
    "recent_summary_count": 2,   # 最近 N 份保留中等摘要
    "max_one_liner_count": 10,   # 最多保留 N 条一句话摘要
}


# ============================================================
# 核心组装函数
# ============================================================

def build_context(
    state: "AgentState",
    target_agent: Literal["main_agent", "status_agent", "plan_agent", "guide_agent"] = "main_agent",
    include_layer0: bool = False,  # Layer 0 通常在 Prompt 模板中定义
) -> str:
    """
    组装完整上下文
    
    Args:
        state: Agent 状态
        target_agent: 目标 Agent（可根据 Agent 调整上下文）
        include_layer0: 是否包含 Layer 0 系统指令
    
    Returns:
        格式化的上下文字符串
    """
    sections = []
    
    # Layer 0: 系统指令（通常在 Prompt 模板中，这里可选包含）
    if include_layer0:
        layer0 = _build_layer0_system()
        if layer0:
            sections.append(layer0)
    
    # Layer 1: 静态情报（3×3 矩阵）
    user_context = state.get("user_context")
    if user_context:
        layer1 = _build_layer1_static_intel(user_context)
        if layer1:
            sections.append(layer1)
    
    # Layer 2: 工作上下文
    layer2 = _build_layer2_working(state)
    if layer2:
        sections.append(layer2)
    
    # Layer 3: 滚动对话区
    messages = state.get("messages", [])
    layer3 = _build_layer3_conversation(messages)
    if layer3:
        sections.append(layer3)
    
    # Layer 4: 历史摘要（常驻部分）
    history_archive = state.get("history_archive")
    if history_archive:
        layer4 = _build_layer4_summaries(history_archive)
        if layer4:
            sections.append(layer4)
    
    return "\n\n---\n\n".join(sections)


def build_context_dict(state: "AgentState") -> dict:
    """
    构建上下文字典（用于 Prompt 模板变量替换）
    
    返回分离的各层内容，方便在 Prompt 模板中灵活使用
    
    Args:
        state: Agent 状态
    
    Returns:
        包含各层内容的字典
    """
    user_context = state.get("user_context", {})
    history_archive = state.get("history_archive", {})
    
    return {
        # Layer 1: 静态情报
        "user_context": _build_layer1_static_intel(user_context) if user_context else "暂无用户信息",
        "user_info": _format_info_source(user_context.get("user_info", {}), "用户"),
        "crush_info": _format_crush_info(user_context.get("crush_info", {})),
        "both_info": _format_info_source(user_context.get("both_info", {}), "双方相处"),
        
        # Layer 2: 工作上下文
        "status_report": _format_status_report(state.get("status_report")),
        "action_plan": _format_action_plan(state.get("action_plan")),
        "action_guides": _format_action_guides(state.get("action_guides", [])),
        
        # Layer 3: 对话历史
        "conversation_history": _build_layer3_conversation(state.get("messages", [])),
        
        # Layer 4: 历史摘要
        "history_summaries": _build_layer4_summaries(history_archive) if history_archive else "",
        
        # 兼容旧版变量名
        "user_profile": json.dumps(state.get("user_profile", {}), ensure_ascii=False, indent=2),
        "action_guide": _format_legacy_action_guide(state.get("action_guide")),
    }


# ============================================================
# Layer 构建函数
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


def _build_layer1_static_intel(user_context: UserContext) -> str:
    """
    Layer 1: 静态情报区（3×3 矩阵）
    
    完整输入，是 Agent 的"长期记忆核心"
    """
    if not user_context:
        return ""
    
    sections = ["## 用户和 Crush 的所有信息"]
    
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
    if len(sections) == 1:
        return "## 用户和 Crush 的所有信息\n\n暂无详细信息，需要进一步了解。"
    
    return "\n\n".join(sections)


def _build_layer2_working(state: "AgentState") -> str:
    """
    Layer 2: 工作上下文
    
    包含：现状分析报告、行动规划、所有未执行的行动指南、最近聊天记录
    """
    sections = ["## 当前工作上下文"]
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
    
    # 行动指南（新版：支持多个）
    action_guides = state.get("action_guides", [])
    active_guides = [g for g in action_guides if g.get("status") in ("pending", "in_progress")]
    if active_guides:
        has_content = True
        sections.append("### 行动指南")
        sections.append(_format_action_guides(active_guides))
    else:
        # 兼容旧版单个 action_guide
        action_guide = state.get("action_guide")
        if action_guide:
            has_content = True
            sections.append("### 行动指南")
            sections.append(_format_legacy_action_guide(action_guide))
    
    # 最近聊天记录（工作上下文中显示最近 10 条）
    messages = state.get("messages", [])
    if messages:
        has_content = True
        sections.append("### 最近聊天记录")
        recent_messages = messages[-10:] if len(messages) > 10 else messages
        chat_lines = []
        for msg in recent_messages:
            role = "用户" if msg.get("role") == "user" else "小话"
            content = msg.get("content", "")
            chat_lines.append(f"**{role}**: {content}")
        sections.append("\n\n".join(chat_lines))
    
    if not has_content:
        return ""
    
    return "\n\n".join(sections)


def _build_layer3_conversation(messages: list, max_turns: int = None) -> str:
    """
    Layer 3: 滚动对话区
    
    保留最近 N 轮完整对话
    """
    if not messages:
        return "## 对话历史\n\n无历史对话"
    
    if max_turns is None:
        max_turns = CONVERSATION_CONFIG["max_recent_turns"]
    
    # 只保留最近 N 条消息
    recent = messages[-max_turns:] if len(messages) > max_turns else messages
    
    formatted = ["## 对话历史"]
    for msg in recent:
        role = "用户" if msg.get("role") == "user" else "小话"
        content = msg.get("content", "")
        formatted.append(f"**{role}**: {content}")
    
    return "\n\n".join(formatted)


def _build_layer4_summaries(history_archive: HistoryArchive) -> str:
    """
    Layer 4: 历史摘要（常驻部分）
    
    摘要分级：
    - 最近 2 份：中等摘要
    - 更早的：一句话摘要
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
    
    return "## 历史档案摘要\n\n" + "\n\n".join(sections)


# ============================================================
# 格式化辅助函数
# ============================================================

def _format_info_source(info: dict, label: str) -> str:
    """格式化信息来源三元组"""
    parts = [f"### {label}信息"]
    
    user_provide = info.get("user_provide", "").strip()
    fact = info.get("fact", "").strip()
    ai_provide = info.get("ai_provide", "").strip()
    
    if user_provide:
        parts.append(f"#### 由用户提供的信息\n{user_provide}")
    if fact:
        parts.append(f"#### 客观事实\n{fact}")
    if ai_provide:
        parts.append(f"#### 军师分析得出的信息\n{ai_provide}")
    
    if len(parts) == 1:
        parts.append("暂无信息")
    
    return "\n\n".join(parts)


def _format_crush_info(crush_info: dict) -> str:
    """格式化 Crush 信息"""
    parts = ["### Crush 信息"]
    
    crush_name = crush_info.get("crush_name", "").strip()
    if crush_name:
        parts.append(f"#### Crush 名称或昵称\n{crush_name}")
    
    user_provide = crush_info.get("user_provide", "").strip()
    fact = crush_info.get("fact", "").strip()
    ai_provide = crush_info.get("ai_provide", "").strip()
    
    if user_provide:
        parts.append(f"#### 由用户提供的信息\n{user_provide}")
    if fact:
        parts.append(f"#### 客观事实\n{fact}")
    if ai_provide:
        parts.append(f"#### 军师分析得出的信息\n{ai_provide}")
    
    if len(parts) == 1:
        parts.append("暂无 Crush 信息")
    
    return "\n\n".join(parts)


def _format_status_report(status_report: Optional[dict]) -> str:
    """格式化现状分析报告"""
    if not status_report:
        return "暂无现状分析报告"
    
    # 如果有完整的 Markdown 内容，直接返回
    if status_report.get("report_content"):
        return status_report["report_content"]
    
    # 否则从结构化数据构建
    parts = []
    
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


def _format_action_plan(action_plan: Optional[dict]) -> str:
    """格式化行动规划"""
    if not action_plan:
        return "暂无行动规划"
    
    parts = []
    
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


def _format_action_guides(action_guides: list[ActionGuideItem]) -> str:
    """格式化行动指南列表（新版）"""
    if not action_guides:
        return "暂无行动指南"
    
    parts = []
    for i, item in enumerate(action_guides, 1):
        guide = item.get("guide", {})
        status = item.get("status", "pending")
        status_emoji = {"pending": "⏳", "in_progress": "🔄", "completed": "✅"}.get(status, "")
        
        guide_content = guide.get("guide_content", "")
        if guide_content:
            parts.append(f"#### 指南 {i} {status_emoji}\n{guide_content}")
        else:
            current_task = guide.get("current_task", "未命名任务")
            parts.append(f"#### 指南 {i} {status_emoji}: {current_task}")
            if guide.get("steps"):
                steps = "\n".join(f"{j}. {step}" for j, step in enumerate(guide["steps"], 1))
                parts.append(f"**步骤**:\n{steps}")
    
    return "\n\n".join(parts)


def _format_legacy_action_guide(action_guide: Optional[dict]) -> str:
    """格式化旧版单个行动指南"""
    if not action_guide:
        return "暂无行动指南"
    
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


def _format_history_summaries(history_list: list, title: str) -> str:
    """格式化历史摘要列表"""
    if not history_list:
        return ""
    
    parts = [f"### {title}"]
    recent_count = HISTORY_CONFIG["recent_summary_count"]
    
    for i, item in enumerate(history_list):
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


def _format_conversation_archive(archive_list: list) -> str:
    """格式化对话归档"""
    if not archive_list:
        return ""
    
    parts = ["### 历史对话归档"]
    for item in archive_list[:5]:  # 最多显示 5 条
        summary = item.get("summary", "")
        if summary:
            parts.append(f"- {summary}")
    
    return "\n".join(parts) if len(parts) > 1 else ""


def _has_content(info: dict) -> bool:
    """检查信息源是否有内容"""
    return bool(
        info.get("user_provide", "").strip() or
        info.get("fact", "").strip() or
        info.get("ai_provide", "").strip()
    )


# ============================================================
# Token 估算和压缩判断
# ============================================================

def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量
    
    使用简单的字符/token 比例估算（中英文混合约 2:1）
    如需精确计算，可接入 tiktoken
    """
    if not text:
        return 0
    # 粗略估算：中文约 1.5 字符/token，英文约 4 字符/token
    # 综合估算约 2 字符/token
    return len(text) // 2


def estimate_state_tokens(state: "AgentState") -> int:
    """估算整个状态的 token 数量"""
    context = build_context(state, include_layer0=True)
    return estimate_tokens(context)


def should_compress(state: "AgentState") -> bool:
    """
    判断是否需要触发压缩
    
    压缩触发条件（满足任一）：
    1. 总上下文 tokens > compression_threshold
    2. 对话轮次 > compression_trigger_turns
    """
    # 检查对话轮次
    messages = state.get("messages", [])
    if len(messages) > CONVERSATION_CONFIG["compression_trigger_turns"]:
        return True
    
    # 检查 token 数量
    total_tokens = estimate_state_tokens(state)
    if total_tokens > TOKEN_BUDGET["compression_threshold"]:
        return True
    
    return False


def get_compression_priority() -> list[str]:
    """
    获取压缩优先级（从先到后）
    
    1. Layer 3 对话区：最先压缩
    2. Layer 4 历史摘要：将中等摘要降级为一句话
    3. Layer 2 已执行指南：强制归档
    4. Layer 1 静态情报：最后才压缩
    """
    return [
        "layer3_conversation",
        "layer4_summaries",
        "layer2_completed_guides",
        "layer1_static_intel",
    ]


# ============================================================
# 压缩触发集成（调用 archive_manager）
# ============================================================

def check_and_compress_if_needed(state: "AgentState") -> dict:
    """
    检查并执行压缩（如果需要）
    
    整合 archive_manager 的压缩逻辑，作为统一入口供 workflow 调用
    
    压缩策略：
    - 每超出 5 轮对话集中压缩一次（避免每轮压缩效果差）
    - 压缩后保留最近 40 轮完整对话
    - 被压缩的对话生成摘要存入 conversation_archive
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典，如果没有压缩则返回空字典
    """
    # 延迟导入避免循环依赖
    from graph.archive_manager import (
        check_conversation_compression_needed,
        compress_conversation,
    )
    
    if check_conversation_compression_needed(state):
        print(f"[ContextBuilder] Compression triggered at {len(state.get('messages', []))} messages")
        return compress_conversation(state)
    
    return {}


def get_context_stats(state: "AgentState") -> dict:
    """
    获取上下文统计信息（用于监控和调试）
    
    Returns:
        {
            "total_messages": 当前消息数,
            "estimated_tokens": 估算的 token 数,
            "compression_needed": 是否需要压缩,
            "layers": {各层的大小估算},
        }
    """
    messages = state.get("messages", [])
    user_context = state.get("user_context", {})
    history_archive = state.get("history_archive", {})
    
    # 计算各层大小
    layer1 = _build_layer1_static_intel(user_context) if user_context else ""
    layer2 = _build_layer2_working(state)
    layer3 = _build_layer3_conversation(messages)
    layer4 = _build_layer4_summaries(history_archive) if history_archive else ""
    
    return {
        "total_messages": len(messages),
        "estimated_tokens": estimate_state_tokens(state),
        "compression_needed": should_compress(state),
        "layers": {
            "layer1_static_intel": estimate_tokens(layer1),
            "layer2_working": estimate_tokens(layer2),
            "layer3_conversation": estimate_tokens(layer3),
            "layer4_summaries": estimate_tokens(layer4),
        },
    }
