"""
端到端测试：验证 DeepSeek 思考模式的完整流程

测试流程：
1. 新对话开始 -> reasoning_content 被清理
2. 工具调用 -> reasoning_content 被保留
3. 下一轮对话开始 -> reasoning_content 再次被清理
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from utils.reasoning_content import clear_reasoning_content, extract_reasoning_content


def test_e2e_reasoning_flow():
    """端到端测试 reasoning_content 流程"""
    print("\n" + "=" * 60)
    print("端到端测试：reasoning_content 流程")
    print("=" * 60)
    
    load_dotenv()
    
    # 模拟第一轮对话
    print("\n--- 第一轮对话 ---")
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！", "reasoning_content": "思考：用户打招呼"},
        {"role": "user", "content": "2+2 等于几？"},
        {"role": "assistant", "content": "4", "additional_kwargs": {"reasoning_content": "思考：简单的加法"}},
    ]
    
    print(f"消息数: {len(messages)}")
    for i, msg in enumerate(messages):
        rc = extract_reasoning_content(msg)
        print(f"  消息 {i} ({msg['role']}): reasoning_content = {rc is not None}")
    
    # 模拟新对话开始（Router 清理）
    print("\n--- 新对话开始（清理 reasoning_content）---")
    cleaned_messages = clear_reasoning_content(messages)
    
    print(f"清理后消息数: {len(cleaned_messages)}")
    for i, msg in enumerate(cleaned_messages):
        rc = extract_reasoning_content(msg)
        print(f"  消息 {i} ({msg['role']}): reasoning_content = {rc is not None}")
    
    # 验证所有 reasoning_content 都被清理
    for i, msg in enumerate(cleaned_messages):
        rc = extract_reasoning_content(msg)
        assert rc is None, f"消息 {i} 的 reasoning_content 应该被清理"
    
    print("✓ 所有 reasoning_content 已被清理")
    
    # 模拟工具调用场景（保留 reasoning_content）
    print("\n--- 工具调用场景（保留 reasoning_content）---")
    tool_call_messages = [
        {"role": "user", "content": "今天天气怎么样？"},
        {"role": "assistant", "content": "", "tool_calls": [{"name": "get_weather"}], "reasoning_content": "思考：需要获取天气"},
    ]
    
    print(f"工具调用消息数: {len(tool_call_messages)}")
    for i, msg in enumerate(tool_call_messages):
        rc = extract_reasoning_content(msg)
        print(f"  消息 {i} ({msg['role']}): reasoning_content = {rc is not None}")
    
    # 验证 reasoning_content 被保留
    rc = extract_reasoning_content(tool_call_messages[1])
    assert rc == "思考：需要获取天气", "工具调用时 reasoning_content 应该被保留"
    print("✓ 工具调用时 reasoning_content 已被保留")
    
    # 再次清理
    print("\n--- 再次清理 ---")
    cleaned_again = clear_reasoning_content(tool_call_messages)
    for i, msg in enumerate(cleaned_again):
        rc = extract_reasoning_content(msg)
        assert rc is None, f"再次清理后，消息 {i} 不应有 reasoning_content"
    print("✓ 再次清理成功")
    
    print("\n" + "=" * 60)
    print("✓ 端到端测试通过！")
    print("=" * 60)
    return True


def test_message_builder_integration():
    """测试 message_builder 与 reasoning_content 的集成"""
    print("\n" + "=" * 60)
    print("测试：message_builder 集成")
    print("=" * 60)
    
    from graph.message_builder import _convert_to_base_message
    
    test_cases = [
        {
            "msg": {"role": "assistant", "content": "回答", "reasoning_content": "思考..."},
            "expected_reasoning": "思考...",
            "desc": "基础 reasoning_content",
        },
        {
            "msg": {"role": "assistant", "content": "回答", "additional_kwargs": {"reasoning_content": "思考2..."}},
            "expected_reasoning": "思考2...",
            "desc": "additional_kwargs 中的 reasoning_content",
        },
        {
            "msg": {"role": "assistant", "content": "回答"},
            "expected_reasoning": None,
            "desc": "无 reasoning_content",
        },
    ]
    
    for i, case in enumerate(test_cases):
        print(f"\n测试用例 {i+1}: {case['desc']}")
        
        msg_obj = _convert_to_base_message(case["msg"], "assistant", case["msg"]["content"])
        
        reasoning = extract_reasoning_content(msg_obj)
        print(f"  期望 reasoning_content: {case['expected_reasoning']}")
        print(f"  实际 reasoning_content: {reasoning}")
        
        if case["expected_reasoning"] is None:
            assert reasoning is None, f"测试用例 {i+1}: 不应该有 reasoning_content"
        else:
            assert reasoning == case["expected_reasoning"], f"测试用例 {i+1}: reasoning_content 不匹配"
        
        print(f"  ✓ 测试用例 {i+1} 通过")
    
    print("\n✓ message_builder 集成测试通过")
    return True


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("DeepSeek Reasoning 模式端到端测试")
    print("=" * 60)
    
    all_passed = True
    
    try:
        test_e2e_reasoning_flow()
    except Exception as e:
        print(f"\n✗ 端到端测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    try:
        test_message_builder_integration()
    except Exception as e:
        print(f"\n✗ message_builder 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("所有端到端测试通过 ✓")
    else:
        print("部分测试失败 ✗")
    print("=" * 60)
