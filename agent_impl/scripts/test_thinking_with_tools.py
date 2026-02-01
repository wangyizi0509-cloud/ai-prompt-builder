"""
测试脚本：验证 DeepSeek 思考模式 + 工具调用

用法:
  # 1. 设置环境变量
  export DEEPSEEK_THINKING_WITH_TOOLS=true
  
  # 2. 运行测试
  python scripts/test_thinking_with_tools.py

验证点:
  1. 思考模式 LLM 能正确初始化
  2. 工具调用能正常工作
  3. reasoning_content 能被正确提取
  4. 多轮工具调用能正常执行
"""

import os
import sys
import json

from dotenv import load_dotenv

# 确保能从 agent_impl 根目录导入
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from pydantic import BaseModel, Field
from langchain_core.tools import tool

from config import (
    get_thinking_llm,
    is_thinking_with_tools_enabled,
    get_thinking_max_rounds,
)
from graph.thinking_tool_loop import (
    run_thinking_tool_loop,
    extract_reasoning_content,
)


# ============================================================
# 定义测试工具
# ============================================================

class GetDateInput(BaseModel):
    """获取当前日期的输入"""
    pass


class GetWeatherInput(BaseModel):
    """获取天气的输入"""
    location: str = Field(description="城市名称，如：杭州")
    date: str = Field(description="日期，格式：YYYY-MM-DD")


@tool(args_schema=GetDateInput)
def get_date() -> str:
    """获取当前日期"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


@tool(args_schema=GetWeatherInput)
def get_weather(location: str, date: str) -> str:
    """获取指定城市和日期的天气"""
    # Mock 天气数据
    return json.dumps({
        "location": location,
        "date": date,
        "weather": "多云",
        "temperature": "7°C ~ 13°C",
    }, ensure_ascii=False)


# ============================================================
# 测试函数
# ============================================================

def test_thinking_llm_basic():
    """测试 1: 思考模式 LLM 基础调用"""
    print("\n" + "=" * 60)
    print("测试 1: 思考模式 LLM 基础调用")
    print("=" * 60)
    
    llm = get_thinking_llm(temperature=0.3)
    response = llm.invoke("2+2 等于几？请简短回答。")
    
    content = response.content
    reasoning = extract_reasoning_content(response)
    
    print(f"回答: {content}")
    print(f"有推理内容: {bool(reasoning)}")
    if reasoning:
        print(f"推理内容预览: {reasoning[:200]}...")
    
    assert content, "回答内容不应为空"
    print("✓ 测试通过")


def test_thinking_llm_with_tools():
    """测试 2: 思考模式 LLM + 工具绑定"""
    print("\n" + "=" * 60)
    print("测试 2: 思考模式 LLM + 工具绑定")
    print("=" * 60)
    
    llm = get_thinking_llm(temperature=0.3)
    llm_with_tools = llm.bind_tools([get_date, get_weather])
    
    response = llm_with_tools.invoke("今天是几号？")
    
    content = response.content
    tool_calls = getattr(response, "tool_calls", [])
    reasoning = extract_reasoning_content(response)
    
    print(f"回答: {content}")
    print(f"工具调用: {[tc.get('name') for tc in tool_calls] if tool_calls else '无'}")
    print(f"有推理内容: {bool(reasoning)}")
    if reasoning:
        print(f"推理内容预览: {reasoning[:200]}...")
    
    # 应该调用 get_date 工具
    assert tool_calls, "应该有工具调用"
    assert any(tc.get("name") == "get_date" for tc in tool_calls), "应该调用 get_date 工具"
    print("✓ 测试通过")


def test_thinking_tool_loop():
    """测试 3: 完整的思考+工具循环"""
    print("\n" + "=" * 60)
    print("测试 3: 完整的思考+工具循环")
    print("=" * 60)
    
    messages = [
        ("user", "杭州明天天气怎么样？帮我查一下。")
    ]
    
    tools = [get_date, get_weather]
    
    # 记录回调
    tool_calls_log = []
    tool_results_log = []
    
    def on_tool_call(tc):
        tool_calls_log.append(tc.get("name"))
        print(f"  → 调用工具: {tc.get('name')} args={tc.get('args')}")
    
    def on_tool_result(name, result):
        tool_results_log.append((name, result))
        print(f"  ← 工具结果: {name} = {result[:100]}...")
    
    result = run_thinking_tool_loop(
        messages=messages,
        tools=tools,
        temperature=0.3,
        max_rounds=5,
        on_tool_call=on_tool_call,
        on_tool_result=on_tool_result,
    )
    
    print(f"\n最终回答: {result.content}")
    print(f"工具调用次数: {result.tool_call_count}")
    print(f"循环轮次: {result.round_count}")
    print(f"推理内容数量: {len(result.reasoning_contents)}")
    
    if result.last_reasoning_content:
        print(f"最后一轮推理预览: {result.last_reasoning_content[:200]}...")
    
    # 验证
    assert result.content, "最终回答不应为空"
    assert result.tool_call_count >= 1, "应该至少调用一次工具"
    print("✓ 测试通过")


def test_config_flags():
    """测试 4: 配置开关"""
    print("\n" + "=" * 60)
    print("测试 4: 配置开关")
    print("=" * 60)
    
    enabled = is_thinking_with_tools_enabled()
    max_rounds = get_thinking_max_rounds()
    
    print(f"DEEPSEEK_THINKING_WITH_TOOLS: {enabled}")
    print(f"DEEPSEEK_THINKING_MAX_ROUNDS: {max_rounds}")
    
    # 如果运行测试，应该设置 DEEPSEEK_THINKING_WITH_TOOLS=true
    if not enabled:
        print("⚠ 警告: DEEPSEEK_THINKING_WITH_TOOLS=false，部分测试可能使用普通模式")
    
    assert isinstance(max_rounds, int) and max_rounds > 0, "max_rounds 应该是正整数"
    print("✓ 测试通过")


def main():
    load_dotenv()
    
    print("\n" + "=" * 60)
    print("DeepSeek 思考模式 + 工具调用 测试")
    print("=" * 60)
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("❌ 错误: 缺少 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)
    
    print(f"API Key: {api_key[:8]}...")
    print(f"Base URL: {os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')}")
    
    try:
        test_config_flags()
        test_thinking_llm_basic()
        test_thinking_llm_with_tools()
        test_thinking_tool_loop()
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
