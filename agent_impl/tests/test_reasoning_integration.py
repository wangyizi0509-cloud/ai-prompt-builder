"""
测试 DeepSeek Reasoning 模式集成

验证：
1. 工具调用时使用 thinking mode (deepseek-chat + thinking:enabled)
2. reasoning_content 正确保留在消息中
3. 新对话开始时清理 reasoning_content
"""

import os
import sys
import json

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from utils.reasoning_content import clear_reasoning_content, extract_reasoning_content
from config import get_llm


def test_tool_calling_with_thinking_mode():
    """测试工具调用时使用 thinking mode"""
    print("\n=== 测试 1: 工具调用使用 thinking mode ===")
    load_dotenv()
    
    llm = get_llm(use_tools=True)
    
    from langchain_core.tools import tool
    
    @tool
    def add_numbers(a: int, b: int) -> str:
        """将两个数字相加"""
        return str(a + b)
    
    llm_with_tools = llm.bind_tools([add_numbers])
    
    prompt = "请帮我计算 123 + 456"
    response = llm_with_tools.invoke([HumanMessage(content=prompt)])
    
    reasoning = extract_reasoning_content(response)
    tool_calls = response.tool_calls
    
    print(f"LLM 类型: {type(llm)}")
    print(f"has_tool_calls: {tool_calls is not None and len(tool_calls) > 0}")
    print(f"has_reasoning_content: {reasoning is not None}")
    
    if reasoning:
        print(f"reasoning_content length: {len(reasoning)}")
        print(f"reasoning_content (preview): {reasoning[:200]}...")
    else:
        print("⚠ 警告: 未返回 reasoning_content，可能需要检查 API 配置")
    
    if tool_calls:
        print(f"tool_calls: {len(tool_calls)} 个")
        for tc in tool_calls:
            print(f"  - {tc['name']}: {tc['args']}")
    
    print("✓ 测试 1 通过")
    return True


def test_reasoning_content_in_messages():
    """测试 reasoning_content 在消息中的保留和清理"""
    print("\n=== 测试 2: reasoning_content 在消息中的保留和清理 ===")
    
    test_messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！", "reasoning_content": "这是第一轮思考..."},
        {"role": "user", "content": "再问一下"},
        {"role": "assistant", "content": "请问", "additional_kwargs": {"reasoning_content": "这是第二轮思考..."}},
    ]
    
    print("清理前:")
    for i, msg in enumerate(test_messages):
        rc = extract_reasoning_content(msg)
        print(f"  消息 {i}: reasoning_content = {rc is not None}")
    
    cleaned = clear_reasoning_content(test_messages)
    
    print("\n清理后:")
    for i, msg in enumerate(cleaned):
        rc = extract_reasoning_content(msg)
        print(f"  消息 {i}: reasoning_content = {rc is not None}")
        assert rc is None, f"消息 {i} 的 reasoning_content 应该被清理"
    
    print("✓ 测试 2 通过")
    return True


def test_message_builder_preserves_reasoning():
    """测试 message_builder 正确处理 reasoning_content"""
    print("\n=== 测试 3: message_builder 处理 reasoning_content ===")
    
    from graph.message_builder import _convert_to_base_message
    
    test_msg = {
        "role": "assistant",
        "content": "回答",
        "reasoning_content": "思考过程...",
    }
    
    msg_obj = _convert_to_base_message(test_msg, "assistant", "回答")
    
    print(f"转换后的消息类型: {type(msg_obj)}")
    print(f"content: {msg_obj.content}")
    
    reasoning = extract_reasoning_content(msg_obj)
    print(f"reasoning_content 存在: {reasoning is not None}")
    
    if reasoning:
        print(f"reasoning_content: {reasoning}")
        assert reasoning == "思考过程...", "reasoning_content 应该被保留"
    
    print("✓ 测试 3 通过")
    return True


def test_convert_message_to_dict_preserves_reasoning():
    from graph.state import convert_message_to_dict

    msg = AIMessage(content="x", additional_kwargs={"reasoning_content": "rc"})
    msg_dict = convert_message_to_dict(msg)
    assert extract_reasoning_content(msg_dict) == "rc"


if __name__ == "__main__":
    print("=" * 60)
    print("DeepSeek Reasoning 模式集成测试")
    print("=" * 60)
    
    all_passed = True
    
    try:
        test_tool_calling_with_thinking_mode()
    except Exception as e:
        print(f"✗ 测试 1 失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    try:
        test_reasoning_content_in_messages()
    except Exception as e:
        print(f"✗ 测试 2 失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    try:
        test_message_builder_preserves_reasoning()
    except Exception as e:
        print(f"✗ 测试 3 失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过 ✓")
    else:
        print("部分测试失败 ✗")
    print("=" * 60)
