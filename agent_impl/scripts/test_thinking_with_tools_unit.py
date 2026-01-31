"""
单元测试：验证 DeepSeek 思考模式 + 工具调用代码逻辑（不实际调用 API）

用法:
  python3 scripts/test_thinking_with_tools_unit.py

验证点:
  1. 配置函数能正确读取环境变量
  2. thinking_tool_loop 的代码逻辑正确
  3. 消息格式转换正确
"""

import os
import sys
from unittest.mock import Mock, MagicMock

# 确保能从 agent_impl 根目录导入
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import (
    is_thinking_with_tools_enabled,
    get_thinking_max_rounds,
)
from graph.thinking_tool_loop import (
    extract_reasoning_content,
    _normalize_messages,
    _build_assistant_message,
    clear_reasoning_content_from_messages,
)


def test_config_functions():
    """测试配置函数"""
    print("\n" + "=" * 60)
    print("测试 1: 配置函数")
    print("=" * 60)
    
    # 测试默认值
    enabled = is_thinking_with_tools_enabled()
    max_rounds = get_thinking_max_rounds()
    
    print(f"DEEPSEEK_THINKING_WITH_TOOLS: {enabled}")
    print(f"DEEPSEEK_THINKING_MAX_ROUNDS: {max_rounds}")
    
    assert isinstance(enabled, bool), "enabled 应该是布尔值"
    assert isinstance(max_rounds, int) and max_rounds > 0, "max_rounds 应该是正整数"
    assert max_rounds == 15, f"默认 max_rounds 应该是 15，实际是 {max_rounds}"
    
    print("✓ 测试通过")


def test_extract_reasoning_content():
    """测试 reasoning_content 提取"""
    print("\n" + "=" * 60)
    print("测试 2: reasoning_content 提取")
    print("=" * 60)
    
    # 测试有 reasoning_content 的情况
    mock_response = Mock()
    mock_response.additional_kwargs = {"reasoning_content": "这是推理内容"}
    reasoning = extract_reasoning_content(mock_response)
    assert reasoning == "这是推理内容", f"应该提取到推理内容，实际: {reasoning}"
    print(f"✓ 提取到推理内容: {reasoning[:50]}...")
    
    # 测试没有 reasoning_content 的情况
    mock_response2 = Mock()
    mock_response2.additional_kwargs = {}
    reasoning2 = extract_reasoning_content(mock_response2)
    assert reasoning2 is None, f"应该返回 None，实际: {reasoning2}"
    print("✓ 无推理内容时返回 None")
    
    # 测试 additional_kwargs 为 None 的情况
    mock_response3 = Mock()
    mock_response3.additional_kwargs = None
    reasoning3 = extract_reasoning_content(mock_response3)
    assert reasoning3 is None, f"应该返回 None，实际: {reasoning3}"
    print("✓ additional_kwargs 为 None 时返回 None")
    
    print("✓ 测试通过")


def test_normalize_messages():
    """测试消息格式转换"""
    print("\n" + "=" * 60)
    print("测试 3: 消息格式转换")
    print("=" * 60)
    
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
    
    # 测试各种格式的消息
    messages = [
        ("system", "你是助手"),
        ("user", "你好"),
        {"role": "assistant", "content": "你好！"},
        {"role": "tool", "content": "工具结果", "tool_call_id": "call_123"},
        HumanMessage(content="直接传入的消息"),
    ]
    
    normalized = _normalize_messages(messages)
    
    assert len(normalized) == 5, f"应该有 5 条消息，实际: {len(normalized)}"
    assert isinstance(normalized[0], SystemMessage), "第一条应该是 SystemMessage"
    assert isinstance(normalized[1], HumanMessage), "第二条应该是 HumanMessage"
    assert isinstance(normalized[2], AIMessage), "第三条应该是 AIMessage"
    assert isinstance(normalized[3], ToolMessage), "第四条应该是 ToolMessage"
    assert isinstance(normalized[4], HumanMessage), "第五条应该是 HumanMessage"
    
    print(f"✓ 成功转换 {len(normalized)} 条消息")
    print("✓ 测试通过")


def test_build_assistant_message():
    """测试构建 assistant 消息"""
    print("\n" + "=" * 60)
    print("测试 4: 构建 assistant 消息")
    print("=" * 60)
    
    from langchain_core.messages import AIMessage
    
    # 创建模拟响应
    mock_response = AIMessage(content="回答内容")
    mock_response.tool_calls = [{"name": "get_date", "args": {}, "id": "call_123"}]
    
    reasoning_content = "这是推理过程"
    msg = _build_assistant_message(mock_response, reasoning_content)
    
    assert msg.content == "回答内容", "内容应该一致"
    assert len(msg.tool_calls) == 1, "应该有 1 个工具调用"
    assert msg.additional_kwargs.get("reasoning_content") == reasoning_content, "应该包含 reasoning_content"
    
    print(f"✓ 成功构建 assistant 消息，包含 {len(msg.tool_calls)} 个工具调用")
    print(f"✓ reasoning_content: {msg.additional_kwargs.get('reasoning_content')[:50]}...")
    print("✓ 测试通过")


def test_clear_reasoning_content():
    """测试清除 reasoning_content"""
    print("\n" + "=" * 60)
    print("测试 5: 清除 reasoning_content")
    print("=" * 60)
    
    from langchain_core.messages import AIMessage, HumanMessage
    
    # 创建包含 reasoning_content 的消息
    msg_with_reasoning = AIMessage(content="回答")
    msg_with_reasoning.additional_kwargs = {"reasoning_content": "推理内容"}
    
    messages = [
        HumanMessage(content="用户消息"),
        msg_with_reasoning,
    ]
    
    cleaned = clear_reasoning_content_from_messages(messages)
    
    assert len(cleaned) == 2, "消息数量应该不变"
    assert cleaned[0].content == "用户消息", "用户消息应该不变"
    assert cleaned[1].content == "回答", "回答内容应该保留"
    assert "reasoning_content" not in cleaned[1].additional_kwargs, "reasoning_content 应该被清除"
    
    print("✓ 成功清除 reasoning_content")
    print("✓ 测试通过")


def main():
    print("\n" + "=" * 60)
    print("DeepSeek 思考模式 + 工具调用 单元测试")
    print("=" * 60)
    
    try:
        test_config_functions()
        test_extract_reasoning_content()
        test_normalize_messages()
        test_build_assistant_message()
        test_clear_reasoning_content()
        
        print("\n" + "=" * 60)
        print("✓ 所有单元测试通过！")
        print("=" * 60)
        print("\n注意：这些测试只验证代码逻辑，不实际调用 API。")
        print("要测试实际 API 调用，请确保：")
        print("1. 网络连接正常")
        print("2. DEEPSEEK_API_KEY 已设置")
        print("3. 运行 test_thinking_with_tools.py")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
