"""
测试中断和恢复机制 - 直接测试版本

使用 mock LLM 强制触发中断，测试：
1. 主 agent 节点触发中断并恢复
2. 子 agent 节点触发中断并恢复
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from unittest.mock import Mock, patch
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from langchain_core.messages import AIMessage, ToolMessage

from graph.workflow import compile_workflow
from graph.state import create_initial_state

load_dotenv()


def create_mock_llm_with_tool_call(tool_name: str, tool_args: dict, content: str = ""):
    """
    创建一个会调用指定工具的 mock LLM
    
    Args:
        tool_name: 要调用的工具名称
        tool_args: 工具调用参数
        content: 模型回复内容
    
    Returns:
        Mock LLM 对象
    """
    mock_llm = Mock()
    mock_response = AIMessage(
        content=content,
        tool_calls=[
            {
                "id": "test_tool_call_id",
                "name": tool_name,
                "args": tool_args,
            }
        ]
    )
    mock_llm.invoke.return_value = mock_response
    mock_llm.bind_tools.return_value = mock_llm
    return mock_llm


def test_main_agent_direct_interrupt():
    """
    测试主 agent 节点触发中断并恢复（使用 mock LLM 强制触发）
    """
    print("=" * 80)
    print("测试 1: 主 agent 节点直接触发中断并恢复（使用 mock LLM）")
    print("=" * 80)
    
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    thread_id = "test_main_agent_direct_interrupt"
    config = {"configurable": {"thread_id": thread_id}}
    
    user_input = "测试中断功能"
    
    print("\n" + "-" * 80)
    print("步骤 1: 发送用户输入（使用 mock LLM 强制调用 ask_human）")
    print("-" * 80)
    print(f"用户输入: {user_input}")
    
    state_input = create_initial_state(user_input)
    
    with patch("config.get_llm") as mock_get_llm:
        mock_llm = Mock()
        mock_response = AIMessage(
            content="我需要更多信息",
            tool_calls=[
                {
                    "id": "test_tool_call_id_1",
                    "name": "ask_human",
                    "args": {
                        "inquiry_card": {
                            "type": "inquiry_card",
                            "questions": [
                                {"id": "q1", "question": "问题1"},
                                {"id": "q2", "question": "问题2"}
                            ],
                            "intro": "请回答以下问题",
                            "reasoning": "需要更多信息"
                        }
                    }
                }
            ]
        )
        mock_llm.invoke.return_value = mock_response
        mock_llm.bind_tools.return_value = mock_llm
        mock_get_llm.return_value = mock_llm
        
        result = app.invoke(state_input, config=config)
    
    print(f"\n返回结果键: {list(result.keys())}")
    
    if "__interrupt__" in result:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            interrupt_payload = interrupts[0].value if interrupts else {}
            print(f"\n✓ 检测到中断")
            print(f"  payload 类型: {interrupt_payload.get('type')}")
            print(f"  问题数量: {len(interrupt_payload.get('questions', []))}")
            
            print("\n" + "-" * 80)
            print("步骤 2: 恢复执行（模拟用户回答）")
            print("-" * 80)
            
            resume_payload = {
                "answers": {
                    "q1": "这是第一个问题的回答",
                    "q2": "这是第二个问题的回答"
                }
            }
            print(f"恢复 payload: {resume_payload}")
            
            resumed_result = app.invoke(Command(resume=resume_payload), config=config)
            
            print(f"\n恢复后返回结果键: {list(resumed_result.keys())}")
            
            if "inquiry_answers" in resumed_result:
                print(f"\n✓ inquiry_answers 已保存: {resumed_result['inquiry_answers']}")
            
            print("\n" + "=" * 80)
            print("测试 1 完成: 主 agent 中断恢复成功 ✓")
            print("=" * 80)
        else:
            print("\n✗ 中断列表为空")
    else:
        print("\n✗ 未检测到中断")


def test_subagent_direct_interrupt():
    """
    测试子 agent 节点触发中断并恢复（使用 mock LLM 强制触发）
    """
    print("\n\n" + "=" * 80)
    print("测试 2: 子 agent 节点直接触发中断并恢复（使用 mock LLM）")
    print("=" * 80)
    
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    thread_id = "test_subagent_direct_interrupt"
    config = {"configurable": {"thread_id": thread_id}}
    
    user_input = "测试子 agent 中断功能"
    
    print("\n" + "-" * 80)
    print("步骤 1: 发送用户输入（使用 mock LMP 强制主 agent 调用子 agent）")
    print("-" * 80)
    print(f"用户输入: {user_input}")
    
    state_input = create_initial_state(user_input)
    
    with patch("config.get_llm") as mock_get_llm:
        mock_llm = Mock()
        
        mock_response_main = AIMessage(
            content="我来调用 status agent",
            tool_calls=[
                {
                    "id": "test_tool_call_id_main",
                    "name": "call_status_agent",
                    "args": {
                        "instruction": "分析现状"
                    }
                }
            ]
        )
        mock_llm.invoke.return_value = mock_response_main
        mock_llm.bind_tools.return_value = mock_llm
        mock_get_llm.return_value = mock_llm
        
        result = app.invoke(state_input, config=config)
    
    print(f"\n返回结果键: {list(result.keys())}")
    
    if "__interrupt__" in result:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            interrupt_payload = interrupts[0].value if interrupts else {}
            print(f"\n✓ 检测到中断")
            print(f"  payload 类型: {interrupt_payload.get('type')}")
            print(f"  问题数量: {len(interrupt_payload.get('questions', []))}")
            
            print("\n" + "-" * 80)
            print("步骤 2: 恢复执行（模拟用户回答）")
            print("-" * 80)
            
            resume_payload = {
                "answers": {
                    "q1": "子 agent 中断恢复的回答 1",
                    "q2": "子 agent 中断恢复的回答 2"
                }
            }
            print(f"恢复 payload: {resume_payload}")
            
            resumed_result = app.invoke(Command(resume=resume_payload), config=config)
            
            print(f"\n恢复后返回结果键: {list(resumed_result.keys())}")
            
            if "inquiry_answers" in resumed_result:
                print(f"\n✓ inquiry_answers 已保存: {resumed_result['inquiry_answers']}")
            
            print("\n" + "=" * 80)
            print("测试 2 完成: 子 agent 中断恢复成功 ✓")
            print("=" * 80)
        else:
            print("\n✗ 中断列表为空")
    else:
        print("\n✗ 未检测到中断")


def test_subgraph_invoke_with_interrupt():
    """
    测试子图 invoke 时的中断和恢复
    
    直接调用子图，不经过主图
    """
    print("\n\n" + "=" * 80)
    print("测试 3: 子图直接 invoke 时的中断和恢复")
    print("=" * 80)
    
    from graph.subgraphs.status import get_status_subgraph, StatusSubState
    
    checkpointer = MemorySaver()
    subgraph = get_status_subgraph(checkpointer=checkpointer)
    
    thread_id = "test_subgraph_direct_interrupt"
    config = {"configurable": {"thread_id": thread_id}}
    
    print("\n" + "-" * 80)
    print("步骤 1: invoke 子图（使用 mock LLM 强制调用 ask_human）")
    print("-" * 80)
    
    sub_input: StatusSubState = {
        "task_spec": {
            "instruction": "测试子图中断",
            "parent_state": {}
        },
        "private_messages": [],
    }
    
    with patch("graph.subgraphs.status._shared_llm") as mock_llm:
        mock_response = AIMessage(
            content="需要更多信息",
            tool_calls=[
                {
                    "id": "test_tool_call_id_subgraph",
                    "name": "ask_human",
                    "args": {
                        "inquiry_card": {
                            "type": "inquiry_card",
                            "questions": [
                                {"id": "sq1", "question": "子图问题 1"},
                                {"id": "sq2", "question": "子图问题 2"}
                            ],
                            "intro": "请回答子图问题",
                            "reasoning": "子图需要更多信息"
                        }
                    }
                }
            ]
        )
        mock_llm.invoke.return_value = mock_response
        mock_llm.bind_tools.return_value = mock_llm
        
        result = subgraph.invoke(sub_input, config=config)
    
    print(f"\n返回结果键: {list(result.keys())}")
    
    if "__interrupt__" in result:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            interrupt_payload = interrupts[0].value if interrupts else {}
            print(f"\n✓ 检测到中断")
            print(f"  payload 类型: {interrupt_payload.get('type')}")
            print(f"  问题数量: {len(interrupt_payload.get('questions', []))}")
            
            print("\n" + "-" * 80)
            print("步骤 2: 恢复执行（模拟用户回答）")
            print("-" * 80)
            
            resume_payload = {
                "answers": {
                    "sq1": "子图回答 1",
                    "sq2": "子图回答 2"
                }
            }
            print(f"恢复 payload: {resume_payload}")
            
            resumed_result = subgraph.invoke(Command(resume=resume_payload), config=config)
            
            print(f"\n恢复后返回结果键: {list(resumed_result.keys())}")
            
            if "state_patch" in resumed_result:
                print(f"\n✓ state_patch: {resumed_result['state_patch']}")
            
            print("\n" + "=" * 80)
            print("测试 3 完成: 子图中断恢复成功 ✓")
            print("=" * 80)
        else:
            print("\n✗ 中断列表为空")
    else:
        print("\n✗ 未检测到中断")


def main():
    print("\n" + "=" * 80)
    print("开始中断和恢复机制测试（直接测试版本）")
    print("=" * 80)
    
    try:
        test_main_agent_direct_interrupt()
    except Exception as e:
        print(f"\n测试 1 出错: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_subagent_direct_interrupt()
    except Exception as e:
        print(f"\n测试 2 出错: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_subgraph_invoke_with_interrupt()
    except Exception as e:
        print(f"\n测试 3 出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n\n" + "=" * 80)
    print("所有测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
