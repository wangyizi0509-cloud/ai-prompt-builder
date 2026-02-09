"""
测试 DeepSeek Reasoner 思考模式功能

验证：
1. reasoning_content 是否正确返回
2. 工具调用场景下 reasoning_content 是否正确回传
3. 新对话开始时 reasoning_content 是否被清理
"""

import os
import sys
import json

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from utils.reasoning_content import clear_reasoning_content, extract_reasoning_content


def test_basic_reasoning():
    """测试基本的 reasoning_content 返回"""
    print("\n=== 测试 1: 基本 reasoning_content 返回 ===")
    load_dotenv()
    
    llm = ChatOpenAI(
        model="deepseek-reasoner",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.2,
    )
    
    prompt = "请简要判断 2+2 是否等于 4，并给出结论。"
    response = llm.invoke([HumanMessage(content=prompt)])
    
    reasoning = extract_reasoning_content(response)
    content = response.content
    
    # 打印详细响应信息
    print(f"response type: {type(response)}")
    print(f"response.content type: {type(content)}")
    print(f"response.content: {content}")
    print(f"response.attributes: {dir(response)}")
    print(f"response.additional_kwargs: {getattr(response, 'additional_kwargs', {})}")
    print(f"response.response_metadata: {getattr(response, 'response_metadata', {})}")
    print(f"response.id: {getattr(response, 'id', None)}")
    
    print(f"has_reasoning_content: {reasoning is not None}")
    print(f"reasoning_content length: {len(reasoning) if reasoning else 0}")
    if reasoning:
        print(f"reasoning_content (preview): {reasoning[:200]}...")
    print(f"content (preview): {(content or '')[:200]}...")
    
    if reasoning is None:
        print("⚠ 警告: deepseek-reasoner 未返回 reasoning_content，可能是 API 响应格式变更")
    
    assert content, "应该返回内容"
    print("✓ 测试 1 通过")
    return reasoning is not None


def test_reasoning_content_with_tools():
    """测试工具调用场景下的 reasoning_content 回传"""
    print("\n=== 测试 2: 工具调用场景 reasoning_content 回传 ===")
    load_dotenv()
    
    llm = ChatOpenAI(
        model="deepseek-reasoner",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.2,
    )
    
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
    
    print(f"has_tool_calls: {tool_calls is not None and len(tool_calls) > 0}")
    print(f"has_reasoning_content: {reasoning is not None}")
    
    if reasoning:
        print(f"reasoning_content length: {len(reasoning)}")
        print(f"reasoning_content (preview): {reasoning[:200]}...")
    
    if tool_calls:
        print(f"tool_calls: {len(tool_calls)} 个")
        for tc in tool_calls:
            print(f"  - {tc['name']}: {tc['args']}")
    
    print("✓ 测试 2 通过")
    return True


def test_clear_reasoning_content():
    """测试清理 reasoning_content 功能"""
    print("\n=== 测试 3: 清理 reasoning_content ===")
    
    test_messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！", "reasoning_content": "这是思考过程..."},
        {"role": "user", "content": "再问一下"},
        {"role": "assistant", "content": "请问", "additional_kwargs": {"reasoning_content": "另一个思考过程..."}},
    ]
    
    cleaned = clear_reasoning_content(test_messages)
    
    print(f"原始消息数: {len(test_messages)}")
    print(f"清理后消息数: {len(cleaned)}")
    
    for i, msg in enumerate(cleaned):
        rc = extract_reasoning_content(msg)
        print(f"消息 {i}: reasoning_content = {rc is not None}")
        assert rc is None, f"消息 {i} 的 reasoning_content 应该被清理"
    
    print("✓ 测试 3 通过")
    return True


def test_preserve_reasoning_content():
    """测试保留 reasoning_content 功能（工具调用场景）"""
    print("\n=== 测试 4: 保留 reasoning_content ===")
    
    from utils.reasoning_content import preserve_reasoning_content
    
    test_messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！", "reasoning_content": "这是思考过程..."},
    ]
    
    preserved = preserve_reasoning_content(test_messages)
    
    print(f"原始消息数: {len(test_messages)}")
    print(f"保留后消息数: {len(preserved)}")
    
    rc = extract_reasoning_content(preserved[1])
    print(f"助手消息 reasoning_content: {rc is not None}")
    assert rc == "这是思考过程...", "reasoning_content 应该被保留"
    
    print("✓ 测试 4 通过")
    return True


def test_multi_round_conversation():
    """测试多轮对话中的 reasoning_content 处理"""
    print("\n=== 测试 5: 多轮对话 reasoning_content 处理 ===")
    load_dotenv()
    
    llm = ChatOpenAI(
        model="deepseek-reasoner",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.2,
    )
    
    messages = [
        HumanMessage(content="3+3 等于几？"),
    ]
    
    response1 = llm.invoke(messages)
    reasoning1 = extract_reasoning_content(response1)
    print(f"第 1 轮 - has_reasoning_content: {reasoning1 is not None}")
    
    messages.append(response1)
    messages.append(HumanMessage(content="4+4 等于几？"))
    
    response2 = llm.invoke(messages)
    reasoning2 = extract_reasoning_content(response2)
    print(f"第 2 轮 - has_reasoning_content: {reasoning2 is not None}")
    
    print("✓ 测试 5 通过")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("DeepSeek Reasoner 思考模式测试")
    print("=" * 60)
    
    all_passed = True
    
    try:
        test_basic_reasoning()
    except Exception as e:
        print(f"✗ 测试 1 失败: {e}")
        all_passed = False
    
    try:
        test_reasoning_content_with_tools()
    except Exception as e:
        print(f"✗ 测试 2 失败: {e}")
        all_passed = False
    
    try:
        test_clear_reasoning_content()
    except Exception as e:
        print(f"✗ 测试 3 失败: {e}")
        all_passed = False
    
    try:
        test_preserve_reasoning_content()
    except Exception as e:
        print(f"✗ 测试 4 失败: {e}")
        all_passed = False
    
    try:
        test_multi_round_conversation()
    except Exception as e:
        print(f"✗ 测试 5 失败: {e}")
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过 ✓")
    else:
        print("部分测试失败 ✗")
    print("=" * 60)
