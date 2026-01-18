"""
存储策略层
负责将获取到的内容路由到对应的长期记忆层，并提供统一的写入助手

目标：
- 显式化「存储策略」为一等公民，集中路由规则
- 提供可复用的写入辅助，减少各处重复的 upsert 代码
"""

from typing import TypedDict, Literal, Optional
from datetime import datetime

from graph.context_types import (
    Layer1Memory,
    Layer2Memory,
    Layer3Memory,
    UserContext,
    ActionGuideItem,
    StatusReportItem,
    ActionPlanItem,
    ConversationSummary,
    DynamicIntelItem,
    filter_expired_intels,
)


# ============================================================
# 类型定义
# ============================================================


class IncomingContent(TypedDict, total=False):
    """
    获取层产生的原始输入
    """

    type: str  # 例如：user_message, assistant_message, status_report, action_guide, conversation_summary
    payload: dict
    metadata: dict


class StorageDecision(TypedDict, total=False):
    """
    存储决策结果
    """

    target_layer: Literal["layer1", "layer2", "layer3", "crush"]
    format: Literal["raw", "structured", "summary"]
    priority: Literal["high", "medium", "low"]
    tags: list[str]


# ============================================================
# 路由器
# ============================================================


class StorageRouter:
    """
    存储路由器：根据内容类型决定落盘位置
    """

    def route(self, content: IncomingContent) -> StorageDecision:
        content_type = content.get("type", "")

        # 静态情报
        if content_type in ("fact", "analysis", "insight"):
            return StorageDecision(target_layer="layer1", format="structured", priority="high", tags=["intel"])

        # 工作产出
        if content_type in ("status_report", "action_plan", "action_guide"):
            return StorageDecision(target_layer="layer2", format="structured", priority="high", tags=["work"])

        # 动态情报
        if content_type == "dynamic_intel":
            return StorageDecision(target_layer="layer2", format="structured", priority="high", tags=["intel", "dynamic"])

        # 对话
        if content_type in ("user_message", "assistant_message", "conversation_summary"):
            return StorageDecision(target_layer="layer3", format="summary" if "summary" in content_type else "raw", priority="medium", tags=["dialog"])

        # Crush 聊天
        if content_type == "crush_chat":
            return StorageDecision(target_layer="crush", format="raw", priority="high", tags=["crush_chat"])

        # 默认兜底：放入 Layer 3
        return StorageDecision(target_layer="layer3", format="raw", priority="low", tags=["fallback"])


# ============================================================
# 写入助手
# ============================================================


class StorageProcessor:
    """
    统一的写入助手，封装 Layer1/2/3 的通用 upsert 逻辑
    """

    @staticmethod
    def save_layer1(
        updated_context: UserContext,
        layer1_memory: Layer1Memory,
        *,
        increment_version: bool = True,
    ) -> Layer1Memory:
        """更新 Layer1 静态情报"""
        return Layer1Memory(
            full_data=updated_context,
            extraction_config=layer1_memory.get("extraction_config", {}),
            processing_status=None,
            last_updated=datetime.now().isoformat(),
            update_count=layer1_memory.get("update_count", 0) + 1,
            version=layer1_memory.get("version", 1) + (1 if increment_version else 0),
        )

    @staticmethod
    def append_conversation_summary(
        layer3_memory: Layer3Memory,
        new_summary: ConversationSummary,
        *,
        max_summaries: int,
        total_turns_delta: int = 0,
    ) -> Layer3Memory:
        """在 Layer3 追加对话摘要，并控制保留数量"""
        summaries = list(layer3_memory.get("conversation_summaries", []))
        summaries.insert(0, new_summary)
        if len(summaries) > max_summaries:
            summaries = summaries[:max_summaries]

        return Layer3Memory(
            all_messages=layer3_memory.get("all_messages", []),
            conversation_summaries=summaries,
            task_registry=layer3_memory.get("task_registry", {}),
            extraction_config=layer3_memory.get("extraction_config", {}),
            processing_status=None,
            last_updated=datetime.now().isoformat(),
            total_turns=layer3_memory.get("total_turns", 0) + total_turns_delta,
            version=layer3_memory.get("version", 1) + 1,
        )

    @staticmethod
    def upsert_completed_guide(
        layer2_memory: Layer2Memory,
        guide: ActionGuideItem,
        *,
        recent_count: int,
        max_one_liner: int,
    ) -> Layer2Memory:
        """在 Layer2 中更新已归档（终态）的行动指南并做摘要降级

        兼容 v3.1 状态机：
        - 活跃（可继续执行/可恢复）：pending / in_progress / paused
        - 终态（历史）：completed / cancelled / expired
        """
        all_guides = list(layer2_memory.get("action_guides", []))
        for i, g in enumerate(all_guides):
            if g.get("id") == guide.get("id"):
                all_guides[i] = guide
                break
        else:
            all_guides.append(guide)

        terminal_statuses = {"completed", "cancelled", "expired"}
        archived = [g for g in all_guides if g.get("status") in terminal_statuses]
        archived = downgrade_layer2_summaries(archived, recent_count=recent_count, max_one_liner=max_one_liner)

        active = [g for g in all_guides if g.get("status") in ("pending", "in_progress", "paused")]
        merged = active + archived

        return Layer2Memory(
            current_status_report=layer2_memory.get("current_status_report"),
            status_report_history=layer2_memory.get("status_report_history", []),
            current_action_plan=layer2_memory.get("current_action_plan"),
            action_plan_history=layer2_memory.get("action_plan_history", []),
            action_guides=merged,
            extraction_config=layer2_memory.get("extraction_config", {}),
            processing_status=None,
            last_updated=datetime.now().isoformat(),
            version=layer2_memory.get("version", 1) + 1,
        )

    @staticmethod
    def upsert_status_report(
        layer2_memory: Layer2Memory,
        report: StatusReportItem,
        *,
        recent_count: int,
        max_one_liner: int,
    ) -> Layer2Memory:
        """在 Layer2 中更新现状报告并做摘要降级"""
        # 更新历史报告列表中的报告
        history = list(layer2_memory.get("status_report_history", []))
        for i, r in enumerate(history):
            if r.get("id") == report.get("id"):
                history[i] = report
                break
        else:
            # 如果不在历史中，添加到历史列表
            history.insert(0, report)

        history = downgrade_layer2_summaries(history, recent_count=recent_count, max_one_liner=max_one_liner)

        return Layer2Memory(
            current_status_report=layer2_memory.get("current_status_report"),
            status_report_history=history,
            current_action_plan=layer2_memory.get("current_action_plan"),
            action_plan_history=layer2_memory.get("action_plan_history", []),
            action_guides=layer2_memory.get("action_guides", []),
            dynamic_intels=layer2_memory.get("dynamic_intels", []),
            extraction_config=layer2_memory.get("extraction_config", {}),
            processing_status=None,
            last_updated=datetime.now().isoformat(),
            version=layer2_memory.get("version", 1) + 1,
        )

    @staticmethod
    def upsert_action_plan(
        layer2_memory: Layer2Memory,
        plan: ActionPlanItem,
        *,
        recent_count: int,
        max_one_liner: int,
    ) -> Layer2Memory:
        """在 Layer2 中更新行动规划并做摘要降级"""
        # 更新历史规划列表中的规划
        history = list(layer2_memory.get("action_plan_history", []))
        for i, p in enumerate(history):
            if p.get("id") == plan.get("id"):
                history[i] = plan
                break
        else:
            # 如果不在历史中，添加到历史列表
            history.insert(0, plan)

        history = downgrade_layer2_summaries(history, recent_count=recent_count, max_one_liner=max_one_liner)

        return Layer2Memory(
            current_status_report=layer2_memory.get("current_status_report"),
            status_report_history=layer2_memory.get("status_report_history", []),
            current_action_plan=layer2_memory.get("current_action_plan"),
            action_plan_history=history,
            action_guides=layer2_memory.get("action_guides", []),
            dynamic_intels=layer2_memory.get("dynamic_intels", []),
            extraction_config=layer2_memory.get("extraction_config", {}),
            processing_status=None,
            last_updated=datetime.now().isoformat(),
            version=layer2_memory.get("version", 1) + 1,
        )

    @staticmethod
    def upsert_dynamic_intel(
        layer2_memory: Layer2Memory,
        intel: DynamicIntelItem,
        *,
        max_items: int = 200,
    ) -> Layer2Memory:
        """
        在 Layer2 中新增/更新动态情报
        - 去重规则：优先用 id；若无 id，则用 (content, category, subject) 作为键
        - 过滤已过期情报
        """
        intels = list(layer2_memory.get("dynamic_intels", []))

        def _key(item: DynamicIntelItem) -> str:
            return item.get("id") or f"{item.get('content','')}-{item.get('category','')}-{item.get('subject','')}"

        incoming_key = _key(intel)
        replaced = False
        for i, item in enumerate(intels):
            if _key(item) == incoming_key:
                intels[i] = intel
                replaced = True
                break
        if not replaced:
            intels.append(intel)

        # 过滤过期并裁剪长度
        # filter_expired_intels 返回 (valid, expired)，这里只需要 valid
        valid_intels, _expired = filter_expired_intels(intels)
        intels = valid_intels
        if len(intels) > max_items:
            intels = intels[-max_items:]

        return Layer2Memory(
            current_status_report=layer2_memory.get("current_status_report"),
            status_report_history=layer2_memory.get("status_report_history", []),
            current_action_plan=layer2_memory.get("current_action_plan"),
            action_plan_history=layer2_memory.get("action_plan_history", []),
            action_guides=layer2_memory.get("action_guides", []),
            dynamic_intels=intels,
            extraction_config=layer2_memory.get("extraction_config", {}),
            processing_status=None,
            last_updated=datetime.now().isoformat(),
            version=layer2_memory.get("version", 1) + 1,
        )


# ============================================================
# 摘要降级
# ============================================================


def downgrade_layer2_summaries(
    items: list,
    *,
    recent_count: int = 2,
    max_one_liner: int = 10,
) -> list:
    """
    对 Layer2 历史条目做摘要降级：
    - 最近 recent_count 条：保留 summary
    - 更早的最多 max_one_liner 条：只保留 one_liner，清空 summary
    """
    max_total = recent_count + max_one_liner

    sorted_items = sorted(
        items,
        key=lambda x: x.get("created_at", ""),
        reverse=True,
    )

    processed = []
    for i, item in enumerate(sorted_items[:max_total]):
        if i < recent_count:
            processed.append(item)
        else:
            downgraded = dict(item)
            if not downgraded.get("one_liner") and downgraded.get("summary"):
                downgraded["one_liner"] = downgraded["summary"][:30] + "..."
            downgraded["summary"] = ""
            processed.append(downgraded)

    return processed

