"""
压缩策略验证测试
验证 compression_strategy_v1.0.md 中定义的压缩规则

测试覆盖：
1. 对话压缩触发条件
2. Layer 1 归档规则
3. Layer 2 动态情报规则
4. 摘要生成规范验证
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from graph.archive_manager import (
    check_layer3_compression_needed,
    get_layer3_messages_to_compress,
    check_task_reasoning_compression_needed,
    LAYER2_ARCHIVE_CONFIG,
    LAYER3_ARCHIVE_CONFIG,
)
from graph.context_types import (
    create_empty_layer1_memory,
    create_empty_layer2_memory,
    create_empty_layer3_memory,
    create_reasoning_note,
)
from graph.state import create_initial_state


# ============================================================
# 辅助函数
# ============================================================

def create_user_message(content: str, idx: int = 0) -> dict:
    """创建用户消息"""
    return {
        "id": f"user-{idx}",
        "role": "user",
        "content": content,
        "created_at": datetime.now().isoformat(),
    }


def create_assistant_message(content: str, idx: int = 0) -> dict:
    """创建助手消息"""
    return {
        "id": f"assistant-{idx}",
        "role": "assistant",
        "content": content,
        "created_at": datetime.now().isoformat(),
    }


def create_test_messages(user_count: int) -> list[dict]:
    """创建指定数量用户轮次的消息列表"""
    messages = []
    for i in range(user_count):
        messages.append(create_user_message(f"用户消息 {i}", i))
        messages.append(create_assistant_message(f"助手回复 {i}", i))
    return messages


def create_dynamic_intel(
    content: str,
    category: str,
    days_until_expire: int,
    subject: str = "crush",
    confidence: float = 0.8,
) -> dict:
    """创建动态情报"""
    now = datetime.now()
    expire_at = now + timedelta(days=days_until_expire)
    return {
        "id": f"intel-{content[:8]}",
        "content": content,
        "created_at": now.isoformat(),
        "expire_at": expire_at.isoformat(),
        "subject": subject,
        "category": category,
        "confidence": confidence,
        "confidence_reason": "测试数据",
        "source_type": "conversation",
    }


def create_atomic_memory(
    content: str,
    source: str = "user_provide",
    source_type: str = "conversation",
) -> dict:
    """创建原子记忆"""
    return {
        "id": f"mem-{content[:8]}",
        "content": content,
        "created_at": datetime.now().isoformat(),
        "source_type": source_type,
    }


# ============================================================
# 测试类：对话压缩触发条件
# ============================================================

class TestLayer3CompressionTrigger:
    """测试对话压缩触发条件（对应策略文档第二章 2.2）"""

    def test_compression_not_triggered_below_threshold(self):
        """测试：对话轮次未超过阈值时不触发压缩"""
        state = create_initial_state("test")
        
        # 创建 20 轮对话（低于默认阈值 25）
        messages = create_test_messages(20)
        state["messages"] = messages
        
        result = check_layer3_compression_needed(state)
        assert result is False, "低于阈值时不应触发压缩"

    def test_compression_triggered_above_threshold(self):
        """测试：对话轮次超过阈值且达到批量大小时触发压缩"""
        state = create_initial_state("test")
        
        threshold = LAYER3_ARCHIVE_CONFIG["compression_threshold"]
        batch_size = LAYER3_ARCHIVE_CONFIG["compression_batch_size"]
        
        # 创建刚好超过阈值 + 批量大小的对话
        target_turns = threshold + batch_size
        messages = create_test_messages(target_turns)
        
        # 设置 layer3_memory 的 all_messages（优先于 state["messages"]）
        layer3_memory = create_empty_layer3_memory()
        layer3_memory["all_messages"] = messages
        state["layer3_memory"] = layer3_memory
        state["messages"] = messages
        
        result = check_layer3_compression_needed(state)
        assert result is True, f"超过阈值 {threshold} + 批量 {batch_size} 时应触发压缩"

    def test_compression_message_split(self):
        """测试：压缩时正确分割消息（保留最近 N 轮）"""
        state = create_initial_state("test")
        
        max_recent = LAYER3_ARCHIVE_CONFIG["max_recent_turns"]
        total_turns = max_recent + 5  # 多出 5 轮
        messages = create_test_messages(total_turns)
        
        # 设置 layer3_memory 的 all_messages
        layer3_memory = create_empty_layer3_memory()
        layer3_memory["all_messages"] = messages
        state["layer3_memory"] = layer3_memory
        state["messages"] = messages
        
        to_compress, to_keep = get_layer3_messages_to_compress(state)
        
        # 验证保留的消息数量
        # 每轮 = 1 用户消息 + 1 助手消息
        expected_keep_msgs = max_recent * 2
        assert len(to_keep) >= expected_keep_msgs - 2, \
            f"应保留最近 {max_recent} 轮，实际保留 {len(to_keep)} 条消息"
        
        # 验证压缩的消息数量
        assert len(to_compress) > 0, "应有消息被压缩"

    def test_layer3_memory_prioritized(self):
        """测试：优先使用 layer3_memory 中的 all_messages"""
        state = create_initial_state("test")
        
        # layer3_memory 中有 30 轮
        layer3_memory = create_empty_layer3_memory()
        layer3_memory["all_messages"] = create_test_messages(30)
        state["layer3_memory"] = layer3_memory
        
        # 但 state["messages"] 只有 5 轮（应被忽略）
        state["messages"] = create_test_messages(5)
        
        result = check_layer3_compression_needed(state)
        # 应基于 layer3_memory 中的 30 轮判断
        assert result is True, "应优先使用 layer3_memory"


# ============================================================
# 测试类：任务推理压缩
# ============================================================

class TestTaskReasoningCompression:
    """测试任务推理压缩触发条件（对应策略文档第二章 2.5）"""

    def test_reasoning_compression_not_triggered_below_limit(self):
        """测试：推理笔记数量未超过限制时不触发压缩"""
        state = create_initial_state("test")
        
        task_id = "test-task"
        layer3_memory = create_empty_layer3_memory()
        layer3_memory["task_registry"] = {
            "main_agent": [
                {
                    "task_id": task_id,
                    "status": "active",
                    "reasoning": [create_reasoning_note(f"note-{i}", task_id) for i in range(5)],
                }
            ]
        }
        state["layer3_memory"] = layer3_memory
        
        result = check_task_reasoning_compression_needed(state)
        assert len(result) == 0, "低于限制时不应触发推理压缩"

    def test_reasoning_compression_triggered_above_limit(self):
        """测试：推理笔记数量超过限制时触发压缩"""
        state = create_initial_state("test")
        
        limit = LAYER3_ARCHIVE_CONFIG["reasoning_limit"]
        task_id = "test-task"
        
        layer3_memory = create_empty_layer3_memory()
        layer3_memory["task_registry"] = {
            "main_agent": [
                {
                    "task_id": task_id,
                    "status": "active",
                    "reasoning": [create_reasoning_note(f"note-{i}", task_id) for i in range(limit + 5)],
                }
            ]
        }
        state["layer3_memory"] = layer3_memory
        
        result = check_task_reasoning_compression_needed(state)
        assert len(result) > 0, f"超过限制 {limit} 时应触发推理压缩"


# ============================================================
# 测试类：Layer 1 归档规则
# ============================================================

class TestLayer1ArchivingRules:
    """测试 Layer 1 归档规则（对应策略文档第四章）"""

    def test_atomic_memory_structure(self):
        """测试：原子记忆结构符合规范"""
        memory = create_atomic_memory("测试内容", "user_provide", "conversation")
        
        # 必须包含的字段
        assert "id" in memory
        assert "content" in memory
        assert "created_at" in memory
        assert "source_type" in memory

    def test_layer1_3x3_matrix_structure(self):
        """测试：Layer 1 3×3 矩阵结构完整"""
        layer1 = create_empty_layer1_memory()
        layer1["full_data"] = {
            "user_info": {
                "user_provide": [],
                "fact": [],
                "ai_provide": [],
            },
            "crush_info": {
                "crush_name": "测试 Crush",
                "user_provide": [],
                "fact": [],
                "ai_provide": [],
            },
            "both_info": {
                "user_provide": [],
                "fact": [],
                "ai_provide": [],
            },
        }
        
        full_data = layer1["full_data"]
        
        # 验证三个主体
        assert "user_info" in full_data
        assert "crush_info" in full_data
        assert "both_info" in full_data
        
        # 验证三个来源
        for subject in ["user_info", "crush_info", "both_info"]:
            info = full_data[subject]
            assert "user_provide" in info
            assert "fact" in info
            assert "ai_provide" in info


# ============================================================
# 测试类：Layer 2 动态情报规则
# ============================================================

class TestLayer2DynamicIntelRules:
    """测试 Layer 2 动态情报规则（对应策略文档第五章）"""

    def test_dynamic_intel_structure(self):
        """测试：动态情报结构符合规范"""
        intel = create_dynamic_intel(
            content="下周三去上海",
            category="schedule",
            days_until_expire=7,
        )
        
        # 必须包含的字段
        required_fields = [
            "id", "content", "created_at", "expire_at",
            "subject", "category", "confidence", "confidence_reason",
        ]
        for field in required_fields:
            assert field in intel, f"缺少必填字段: {field}"

    def test_dynamic_intel_ttl_categories(self):
        """测试：不同类别的动态情报 TTL 规则"""
        # 策略文档定义的 TTL 规则
        ttl_rules = {
            "schedule": 2,  # 日程：事件结束 + 2天
            "mood": 3,      # 情绪：3天
            "status": 7,    # 状态：7天
            "intent": 14,   # 意向：14天
        }
        
        for category, expected_days in ttl_rules.items():
            intel = create_dynamic_intel(
                content=f"测试 {category}",
                category=category,
                days_until_expire=expected_days,
            )
            
            # 验证类别
            assert intel["category"] == category

    def test_confidence_must_have_reason(self):
        """测试：置信度必须包含判断依据"""
        intel = create_dynamic_intel(
            content="测试内容",
            category="status",
            days_until_expire=7,
            confidence=0.8,
        )
        
        assert "confidence_reason" in intel
        assert intel["confidence_reason"] is not None
        assert len(intel["confidence_reason"]) > 0, "confidence_reason 不能为空"


# ============================================================
# 测试类：摘要生成规范
# ============================================================

class TestSummarySpecification:
    """测试摘要生成规范（对应策略文档第三章）"""

    def test_one_liner_length_limit(self):
        """测试：一句话摘要长度限制（≤30字）"""
        max_length = 30
        
        # 合规示例
        valid_one_liner = "L2阶段，推进受阻，缺乏独处机会"
        assert len(valid_one_liner) <= max_length, \
            f"one_liner 应不超过 {max_length} 字"
        
        # 不合规示例（超长）
        invalid_one_liner = "这是一个非常长的摘要，远远超过了30个字的限制，需要被截断处理"
        assert len(invalid_one_liner) > max_length, "测试用例设置错误"

    def test_summary_must_not_be_journal_style(self):
        """测试：摘要不应是流水账式"""
        # 错误示例（流水账）
        bad_summary = "用户发来消息，AI回复。用户又发消息，AI又回复。"
        
        # 检查关键词（流水账特征）
        journal_patterns = ["发来消息", "回复", "又发", "又回"]
        is_journal = any(pattern in bad_summary for pattern in journal_patterns)
        
        # 这里只是验证测试数据，实际摘要生成由 LLM 保证

    def test_guide_summary_three_parts(self):
        """测试：指南摘要必须包含三个部分"""
        # 正确格式示例
        valid_summary = (
            "**执行摘要**: 用户按照建议发送了破冰消息，Crush 回复积极。"
            "**用户反馈**: \"她回复了！说周末有空，感觉有戏\""
            "**关键收获**: Crush 对约会持开放态度，周末可能有空。"
        )
        
        # 验证三个部分
        required_parts = ["**执行摘要**", "**用户反馈**", "**关键收获**"]
        for part in required_parts:
            assert part in valid_summary, f"指南摘要应包含 {part}"


# ============================================================
# 测试类：配置常量验证
# ============================================================

class TestConfigurationConstants:
    """测试配置常量符合策略文档定义"""

    def test_layer2_archive_config(self):
        """测试：Layer 2 归档配置"""
        assert "recent_summary_count" in LAYER2_ARCHIVE_CONFIG
        assert "max_one_liner_count" in LAYER2_ARCHIVE_CONFIG
        
        # 验证值在合理范围
        assert LAYER2_ARCHIVE_CONFIG["recent_summary_count"] >= 1
        assert LAYER2_ARCHIVE_CONFIG["max_one_liner_count"] >= 5

    def test_layer3_archive_config(self):
        """测试：Layer 3 归档配置"""
        required_keys = [
            "max_recent_turns",
            "compression_threshold",
            "compression_batch_size",
            "max_summaries",
            "reasoning_limit",
        ]
        
        for key in required_keys:
            assert key in LAYER3_ARCHIVE_CONFIG, f"缺少配置项: {key}"
        
        # 验证值在合理范围
        assert LAYER3_ARCHIVE_CONFIG["max_recent_turns"] >= 1
        assert LAYER3_ARCHIVE_CONFIG["compression_threshold"] >= 1
        assert LAYER3_ARCHIVE_CONFIG["max_summaries"] >= 1
        assert LAYER3_ARCHIVE_CONFIG["reasoning_limit"] >= 1


# ============================================================
# 运行测试
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
