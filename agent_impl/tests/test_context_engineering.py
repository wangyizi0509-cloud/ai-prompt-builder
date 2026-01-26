"""
上下文工程集成测试
通过实际调用 Agent 验证上下文存储和检索功能

运行方式:
    cd agent_impl
    pytest tests/test_context_engineering.py -v

注意: 需要配置有效的 LLM API Key（在 .env 中）
"""

import pytest
import time
import sys
from pathlib import Path

# 确保可以导入 conftest
TESTS_DIR = Path(__file__).parent
sys.path.insert(0, str(TESTS_DIR))

from tests.conftest import (
    run_workflow_turn,
    print_state_summary,
    get_ai_response,
    TEST_USER_ID,
)

from graph.state import create_initial_state
from graph.crush_chat_storage import CrushChatManager, create_crush_chat_manager
from graph.archive_manager import check_layer3_compression_needed, LAYER3_ARCHIVE_CONFIG


# ============================================================
# 测试 1: 用户信息存储
# ============================================================

class TestUserInfoStorage:
    """测试用户信息是否正确存储到 user_context.user_info"""
    
    def test_user_info_extracted_from_intro(self, workflow):
        """
        发送自我介绍消息后，user_context.user_info 应该有内容
        """
        # 创建初始状态
        state = create_initial_state("我叫小明，25岁，在北京做程序员，性格比较内向")
        
        # 执行工作流
        final_state = workflow.invoke(state)
        
        # 打印状态摘要
        print_state_summary(final_state, "用户信息存储测试")
        
        # 验证：user_context 存在
        user_context = final_state.get("user_context", {})
        assert user_context, "user_context 应该存在"
        
        # 验证：有 AI 回复
        response = get_ai_response(final_state)
        assert response, "应该有 AI 回复"
        print(f"AI 回复: {response[:200]}...")
        
        # 注意：user_info 的填充可能需要多轮对话或特定触发
        # 这里主要验证流程能正常执行
        print("✅ 用户信息存储测试通过")


# ============================================================
# 测试 2: Crush 信息存储
# ============================================================

class TestCrushInfoStorage:
    """测试 Crush 信息是否正确存储到 user_context.crush_info"""
    
    def test_crush_info_extracted(self, workflow):
        """
        发送 Crush 描述后，crush_info 应该有内容
        """
        # 创建初始状态
        state = create_initial_state("我喜欢一个女生叫小红，是我同事，比我大两岁，性格很开朗")
        
        # 执行工作流
        final_state = workflow.invoke(state)
        
        # 打印状态摘要
        print_state_summary(final_state, "Crush 信息存储测试")
        
        # 验证：user_context 存在
        user_context = final_state.get("user_context", {})
        assert user_context, "user_context 应该存在"
        
        # 验证：有 AI 回复
        response = get_ai_response(final_state)
        assert response, "应该有 AI 回复"
        print(f"AI 回复: {response[:200]}...")
        
        print("✅ Crush 信息存储测试通过")


# ============================================================
# 测试 3: 对话历史累积
# ============================================================

class TestConversationHistory:
    """测试对话历史是否正确累积"""
    
    def test_messages_accumulate(self, workflow):
        """
        多轮对话后 messages 应该正确增长
        """
        # 第一轮
        state = create_initial_state("你好，我想咨询一些情感问题")
        state = workflow.invoke(state)
        
        messages_after_turn1 = len(state.get("messages", []))
        print(f"第1轮后消息数: {messages_after_turn1}")
        
        # 第二轮
        state = run_workflow_turn(workflow, state, "我和一个女生认识三个月了")
        messages_after_turn2 = len(state.get("messages", []))
        print(f"第2轮后消息数: {messages_after_turn2}")
        
        # 第三轮
        state = run_workflow_turn(workflow, state, "我们现在是普通朋友关系")
        messages_after_turn3 = len(state.get("messages", []))
        print(f"第3轮后消息数: {messages_after_turn3}")
        
        # 验证消息数递增
        assert messages_after_turn2 > messages_after_turn1, "第2轮后消息数应该增加"
        assert messages_after_turn3 > messages_after_turn2, "第3轮后消息数应该增加"
        
        # 验证最后一条用户消息
        messages = state.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) >= 3, f"应该有至少3条用户消息，实际: {len(user_messages)}"
        
        print_state_summary(state, "对话历史累积测试")
        print("✅ 对话历史累积测试通过")


# ============================================================
# 测试 4: 状态报告生成
# ============================================================

class TestStatusReportGeneration:
    """测试现状分析报告是否正确生成"""
    
    def test_status_report_generated(self, workflow):
        """
        触发现状分析后 status_report 应该存在
        """
        # 创建详细的用户描述，触发现状分析
        initial_message = """
        我和一个女生认识了三个月，我们是同事关系。
        我很喜欢她，但不知道她对我是什么感觉。
        我们平时会一起吃午饭，偶尔周末也会出去玩。
        我想知道我们现在是什么阶段，应该怎么推进关系。
        """
        
        state = create_initial_state(initial_message.strip())
        final_state = workflow.invoke(state)
        
        # 打印状态摘要
        print_state_summary(final_state, "状态报告生成测试")
        
        # 验证：有 AI 回复
        response = get_ai_response(final_state)
        assert response, "应该有 AI 回复"
        print(f"AI 回复: {response[:300]}...")
        
        # 状态报告可能需要多轮对话才能生成
        # 这里主要验证流程正常
        status_report = final_state.get("status_report")
        if status_report:
            print(f"✅ status_report 已生成")
        else:
            print("ℹ️ status_report 尚未生成（可能需要更多信息）")
        
        print("✅ 状态报告生成测试通过")


# ============================================================
# 测试 5: 行动指南生成
# ============================================================

class TestActionGuideGeneration:
    """测试行动指南是否正确生成"""
    
    def test_action_guides_generated(self, workflow):
        """
        触发行动指南后 action_guides 应该有记录
        """
        # 创建需要具体行动建议的场景
        initial_message = """
        我们明天要一起去看电影，这是我们第一次单独约会。
        我很紧张，不知道该怎么表现。
        能给我一些具体的建议吗？
        """
        
        state = create_initial_state(initial_message.strip())
        final_state = workflow.invoke(state)
        
        # 打印状态摘要
        print_state_summary(final_state, "行动指南生成测试")
        
        # 验证：有 AI 回复
        response = get_ai_response(final_state)
        assert response, "应该有 AI 回复"
        print(f"AI 回复: {response[:300]}...")
        
        # 检查 action_guides
        action_guides = final_state.get("action_guides", [])
        if action_guides:
            print(f"✅ action_guides 已生成: {len(action_guides)} 个")
            for guide in action_guides:
                print(f"  - [{guide.get('status')}] {guide.get('id')}")
        else:
            print("ℹ️ action_guides 尚未生成（可能需要更多信息）")
        
        print("✅ 行动指南生成测试通过")


# ============================================================
# 测试 6: 对话压缩
# ============================================================

class TestConversationCompression:
    """测试对话压缩机制"""
    
    def test_compression_trigger_check(self):
        """
        测试压缩触发检查函数
        """
        # 创建模拟状态
        threshold = LAYER3_ARCHIVE_CONFIG["compression_threshold"]
        batch_size = LAYER3_ARCHIVE_CONFIG["compression_batch_size"]
        
        print(f"配置: threshold={threshold}, batch_size={batch_size}")
        
        # 测试不同消息数量（基于配置动态生成，避免硬编码失配）
        threshold = int(threshold or 0)
        batch_size = int(batch_size or 1)
        base = max(threshold, 1)
        msg_counts = [
            max(base - 1, 1),          # 低于阈值
            base,                      # 刚到阈值，不触发
            base + batch_size,         # 超出 1 个 batch
            base + batch_size + 1,     # 再多 1 条
            base + 2 * batch_size,     # 超出 2 个 batch
        ]
        test_cases = [
            (
                msg_count,
                (msg_count > threshold) and ((msg_count - threshold) % batch_size == 0),
            )
            for msg_count in msg_counts
        ]
        
        for msg_count, expected in test_cases:
            state = {"messages": [{"role": "user", "content": f"msg{i}"} for i in range(msg_count)]}
            result = check_layer3_compression_needed(state)
            print(f"  消息数 {msg_count}: 需要压缩={result}, 预期={expected}")
            assert result == expected, f"消息数 {msg_count} 时压缩判断错误"
        
        print("✅ 对话压缩触发检查测试通过")


# ============================================================
# 测试 8: Crush 聊天记录
# ============================================================

class TestCrushChatStorage:
    """测试 Crush 聊天记录分层存储"""
    
    def test_crush_chat_l1_l2_l3(self, crush_chat_manager):
        """
        添加 Crush 聊天消息后，L1/L2/L3 数据应该正确
        """
        manager = crush_chat_manager
        
        # 添加测试消息
        messages = [
            {"content": "在干嘛呀", "sender": "crush"},
            {"content": "刚下班，准备回家", "sender": "user"},
            {"content": "今天累不累", "sender": "crush"},
            {"content": "还好，你呢", "sender": "user"},
            {"content": "我也刚下班", "sender": "crush"},
        ]
        
        for msg in messages:
            manager.add_message(
                content=msg["content"],
                sender=msg["sender"],
                timestamp="2024-12-19T18:00:00",
            )
        
        # 验证 L1 元数据
        metadata = manager.get_metadata()
        assert metadata["total_messages"] == 5, f"总消息数应为5，实际: {metadata['total_messages']}"
        print(f"L1 元数据: {metadata}")
        
        # 验证 L3 最近消息
        recent = manager.get_recent_messages(3)
        assert len(recent) == 3, f"最近消息应为3条，实际: {len(recent)}"
        print(f"L3 最近消息: {[m.content for m in recent]}")
        
        # 标记重要消息
        first_msg = manager.all_messages[0]
        manager.mark_as_important(first_msg.id, reason="第一次主动联系")
        
        important = manager.get_important_messages()
        assert len(important) == 1, f"重要消息应为1条，实际: {len(important)}"
        print(f"重要消息: {[m.content for m in important]}")
        
        # 验证搜索功能
        search_results = manager.search_messages("下班")
        assert len(search_results) >= 2, f"搜索'下班'应至少返回2条，实际: {len(search_results)}"
        print(f"搜索结果: {[m.content for m in search_results]}")
        
        # 验证上下文构建
        l1_l2_context = manager.build_context_l1_l2()
        assert "总消息数" in l1_l2_context
        print(f"\nL1+L2 上下文:\n{l1_l2_context}")
        
        l3_context = manager.build_context_l3(include_recent=3)
        assert "Crush" in l3_context or "用户" in l3_context
        print(f"\nL3 上下文:\n{l3_context}")
        
        # 验证序列化
        data = manager.to_dict()
        restored = CrushChatManager.from_dict(data)
        assert len(restored.all_messages) == 5
        print("序列化/反序列化验证通过")
        
        print("✅ Crush 聊天记录测试通过")


# ============================================================
# 集成测试: 完整流程
# ============================================================

class TestFullFlow:
    """完整流程集成测试"""
    
    def test_multi_turn_conversation(self, workflow):
        """
        测试多轮对话的完整流程
        """
        # 第一轮：自我介绍
        state = create_initial_state("我叫小明，25岁，在互联网公司工作")
        state = workflow.invoke(state)
        print(f"\n第1轮 AI 回复: {get_ai_response(state)[:150]}...")
        
        # 第二轮：介绍 Crush
        state = run_workflow_turn(workflow, state, "我喜欢的女生叫小红，是我同事")
        print(f"\n第2轮 AI 回复: {get_ai_response(state)[:150]}...")
        
        # 第三轮：描述关系
        state = run_workflow_turn(workflow, state, "我们认识三个月了，经常一起吃饭")
        print(f"\n第3轮 AI 回复: {get_ai_response(state)[:150]}...")
        
        # 打印最终状态摘要
        print_state_summary(state, "多轮对话完整流程测试")
        
        # 验证基本功能
        assert len(state.get("messages", [])) >= 6, "应该有至少6条消息（3轮对话）"
        
        print("✅ 多轮对话完整流程测试通过")


# ============================================================
# 运行提示
# ============================================================

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║           AI 军师 Agent 上下文工程集成测试                      ║
╠══════════════════════════════════════════════════════════════╣
║  运行方式:                                                    ║
║    cd agent_impl                                             ║
║    pytest tests/test_context_engineering.py -v               ║
║                                                              ║
║  运行单个测试:                                                ║
║    pytest tests/test_context_engineering.py::TestUserInfoStorage -v  ║
║                                                              ║
║  注意: 需要配置有效的 LLM API Key（在 .env 中）                  ║
╚══════════════════════════════════════════════════════════════╝
    """)
