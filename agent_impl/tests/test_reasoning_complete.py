"""
完整测试：DeepSeek Reasoner 的 reasoning_content 处理

测试：
1. ChatDeepSeek + deepseek-reasoner 返回 reasoning_content
2. 工具调用场景下 reasoning_content 的回传
3. 新对话开始时 reasoning_content 的清理
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from config import get_llm
from utils.reasoning_content import clear_reasoning_content, extract_reasoning_content

load_dotenv()

print("=" * 60)
print("完整测试：DeepSeek Reasoner reasoning_content")
print("=" * 60)


def test_basic_reasoning():
    """测试 1: 基本 reasoning_content 返回"""
    print("\n--- 测试 1: 基本 reasoning_content 返回 ---")
    
    llm = ChatDeepSeek(
        model="deepseek-reasoner",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        temperature=0.2,
    )
    
    response = llm.invoke([HumanMessage(content="2+2 等于几？")])
    
    reasoning = extract_reasoning_content(response)
    print(f"has_reasoning_content: {reasoning is not None}")
    if reasoning:
        print(f"reasoning_content length: {len(reasoning)}")
        print(f"reasoning_content preview: {reasoning[:100]}...")
    
    assert reasoning is not None, "deepseek-reasoner 应该返回 reasoning_content"
    print("✓ 测试 1 通过")
    return True


def test_tool_calling_with_reasoning():
    """测试 2: 工具调用 + reasoning_content"""
    print("\n--- 测试 2: 工具调用 + reasoning_content ---")
    
    llm = ChatDeepSeek(
        model="deepseek-reasoner",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        temperature=0.2,
    )
    
    @tool
    def get_date() -> str:
        """获取当前日期"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d")
    
    llm_with_tools = llm.bind_tools([get_date])
    response = llm_with_tools.invoke([HumanMessage(content="今天是几号？")])
    
    reasoning = extract_reasoning_content(response)
    tool_calls = response.tool_calls
    
    print(f"has_tool_calls: {tool_calls is not None and len(tool_calls) > 0}")
    print(f"has_reasoning_content: {reasoning is not None}")
    
    if reasoning:
        print(f"reasoning_content length: {len(reasoning)}")
        print(f"reasoning_content preview: {reasoning[:100]}...")
    
    if tool_calls:
        print(f"tool_calls: {len(tool_calls)} 个")
        for tc in tool_calls:
            print(f"  - {tc['name']}: {tc['args']}")
    
    assert reasoning is not None, "工具调用时也应该返回 reasoning_content"
    print("✓ 测试 2 通过")
    return True


def test_reasoning_clearing():
    """测试 3: reasoning_content 清理"""
    print("\n--- 测试 3: reasoning_content 清理 ---")
    
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！", "reasoning_content": "思考1"},
        {"role": "user", "content": "2+2？"},
        {"role": "assistant", "content": "4", "additional_kwargs": {"reasoning_content": "思考2"}},
    ]
    
    print("清理前:")
    for i, msg in enumerate(messages):
        rc = extract_reasoning_content(msg)
        print(f"  消息 {i}: reasoning_content = {rc is not None}")
    
    cleaned = clear_reasoning_content(messages)
    
    print("\n清理后:")
    for i, msg in enumerate(cleaned):
        rc = extract_reasoning_content(msg)
        print(f"  消息 {i}: reasoning_content = {rc is not None}")
        assert rc is None, f"消息 {i} 的 reasoning_content 应该被清理"
    
    print("✓ 测试 3 通过")
    return True


def test_config_integration():
    """测试 4: config.py 集成"""
    print("\n--- 测试 4: config.py 集成 ---")
    
    llm = get_llm(use_tools=True)
    print(f"LLM 类型: {type(llm).__name__}")
    
    response = llm.invoke([HumanMessage(content="2+2 等于几？")])
    reasoning = extract_reasoning_content(response)
    
    print(f"has_reasoning_content: {reasoning is not None}")
    if reasoning:
        print(f"reasoning_content length: {len(reasoning)}")
    
    assert reasoning is not None, "config.py 的 get_llm(use_tools=True) 应该返回 reasoning_content"
    print("✓ 测试 4 通过")
    return True


if __name__ == "__main__":
    all_passed = True
    
    try:
        test_basic_reasoning()
    except Exception as e:
        print(f"✗ 测试 1 失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    try:
        test_tool_calling_with_reasoning()
    except Exception as e:
        print(f"✗ 测试 2 失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    try:
        test_reasoning_clearing()
    except Exception as e:
        print(f"✗ 测试 3 失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    try:
        test_config_integration()
    except Exception as e:
        print(f"✗ 测试 4 失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过 ✓")
    else:
        print("部分测试失败 ✗")
    print("=" * 60)
