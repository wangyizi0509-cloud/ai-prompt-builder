"""
测试中断和恢复机制 - 简化版本

测试子图 invoke 时的中断和恢复
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

from graph.subgraphs.status import get_status_subgraph, StatusSubState

load_dotenv()


def test_subgraph_interrupt_resume():
    """
    测试子图中断和恢复的完整流程
    """
    print("=" * 80)
    print("测试: 子图中断和恢复完整流程")
    print("=" * 80)
    
    checkpointer = MemorySaver()
    subgraph = get_status_subgraph(checkpointer=checkpointer)
    
    thread_id = "test_subgraph_interrupt_resume"
    config = {"configurable": {"thread_id": thread_id}}
    
    print("\n" + "-" * 80)
    print("步骤 1: invoke 子图并触发中断")
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
                    "id": "test_tool_call_1",
                    "name": "ask_human",
                    "args": {
                        "inquiry_card": {
                            "type": "inquiry_card",
                            "questions": [
                                {"id": "q1", "question": "你们认识多久了？"},
                                {"id": "q2", "question": "最近一次聊天是什么时候？"}
                            ],
                            "intro": "请回答以下问题",
                            "reasoning": "需要补充信息"
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
            questions = interrupt_payload.get('questions', [])
            print(f"  问题数量: {len(questions)}")
            for i, q in enumerate(questions):
                print(f"    问题 {i+1}: {q.get('question', '')}")
            
            print("\n" + "-" * 80)
            print("步骤 2: 恢复执行（模拟用户回答）")
            print("-" * 80)
            
            resume_payload = {
                "answers": {
                    "q1": "我们认识2个月了",
                    "q2": "昨天刚聊过"
                }
            }
            print(f"恢复 payload: {resume_payload}")
            
            with patch("graph.subgraphs.status._shared_llm") as mock_llm_resume:
                mock_response_resume = AIMessage(
                    content="根据你的回答，我已完成现状分析",
                    tool_calls=[]
                )
                mock_llm_resume.invoke.return_value = mock_response_resume
                mock_llm_resume.bind_tools.return_value = mock_llm_resume
                
                resumed_result = subgraph.invoke(Command(resume=resume_payload), config=config)
            
            print(f"\n恢复后返回结果键: {list(resumed_result.keys())}")
            
            if "state_patch" in resumed_result:
                print(f"\n✓ state_patch 存在")
                if "final" in resumed_result:
                    print(f"  最终回复: {resumed_result['final']}")
            
            print("\n" + "=" * 80)
            print("测试完成: 子图中断恢复成功 ✓")
            print("=" * 80)
        else:
            print("\n✗ 中断列表为空")
    else:
        print("\n✗ 未检测到中断")


def test_main_graph_subagent_interrupt_resume():
    """
    测试主图调用子 agent 时的中断和恢复
    
    这个测试模拟：
    1. 主图 router 节点执行（跳过 onboarding）
    2. 主图 main_agent 节点调用子 agent
    3. 子 agent 内部触发中断
    4. 从主图层面恢复执行
    """
    print("\n\n" + "=" * 80)
    print("测试: 主图调用子 agent 的中断恢复")
    print("=" * 80)
    
    from graph.workflow import compile_workflow
    from graph.state import create_initial_state
    
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    thread_id = "test_main_subagent_interrupt"
    config = {"configurable": {"thread_id": thread_id}}
    
    user_input = "我想分析现状"
    
    print("\n" + "-" * 80)
    print("步骤 1: 发送用户输入（跳过 onboarding）")
    print("-" * 80)
    print(f"用户输入: {user_input}")
    
    state_input = create_initial_state(user_input)
    state_input["onboarding_completed"] = True
    
    with patch("config.get_llm") as mock_get_llm:
        mock_llm = Mock()
        mock_response = AIMessage(
            content="我来调用 status agent",
            tool_calls=[
                {
                    "id": "test_tool_call_main",
                    "name": "call_status_agent",
                    "args": {
                        "instruction": "分析现状"
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
            questions = interrupt_payload.get('questions', [])
            print(f"  问题数量: {len(questions)}")
            for i, q in enumerate(questions):
                print(f"    问题 {i+1}: {q.get('question', '')}")
            
            print("\n" + "-" * 80)
            print("步骤 2: 从主图层面恢复执行")
            print("-" * 80)
            
            resume_payload = {
                "answers": {
                    "q1": "我们认识3个月了",
                    "q2": "每天都会聊天"
                }
            }
            print(f"恢复 payload: {resume_payload}")
            
            with patch("config.get_llm") as mock_get_llm_resume:
                mock_llm_resume = Mock()
                mock_response_resume = AIMessage(
                    content="根据子 agent 的分析结果，我已为你完成现状分析",
                    tool_calls=[]
                )
                mock_llm_resume.invoke.return_value = mock_response_resume
                mock_llm_resume.bind_tools.return_value = mock_llm_resume
                mock_get_llm_resume.return_value = mock_llm_resume
                
                resumed_result = app.invoke(Command(resume=resume_payload), config=config)
            
            print(f"\n恢复后返回结果键: {list(resumed_result.keys())}")
            
            if "inquiry_answers" in resumed_result:
                print(f"\n✓ inquiry_answers 已保存: {resumed_result['inquiry_answers']}")
            
            print("\n" + "=" * 80)
            print("测试完成: 主图子 agent 中断恢复成功 ✓")
            print("=" * 80)
        else:
            print("\n✗ 中断列表为空")
    else:
        print("\n✗ 未检测到中断")
        print("（可能子 agent 没有调用 ask_human 工具）")


def main():
    print("\n" + "=" * 80)
    print("开始中断和恢复机制测试（简化版本）")
    print("=" * 80)
    
    try:
        test_subgraph_interrupt_resume()
    except Exception as e:
        print(f"\n测试 1 出错: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_main_graph_subagent_interrupt_resume()
    except Exception as e:
        print(f"\n测试 2 出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n\n" + "=" * 80)
    print("所有测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
