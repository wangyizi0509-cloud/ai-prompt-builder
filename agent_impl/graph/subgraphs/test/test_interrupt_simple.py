"""
简单测试中断机制

直接测试 interrupt 和 Command(resume=...) 的基本功能
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict


class SimpleState(TypedDict):
    messages: list[str]
    question: str
    answer: str


def node_with_interrupt(state: SimpleState) -> SimpleState:
    """
    会触发中断的节点
    """
    payload = {
        "type": "inquiry_card",
        "questions": [{"id": "q1", "question": "请输入你的名字"}],
        "intro": "需要获取用户信息",
        "reasoning": "需要用户回答"
    }
    
    answer = interrupt(payload)
    
    return {
        "messages": state.get("messages", []) + ["用户回答: " + str(answer.get("q1", ""))],
        "question": "请输入你的名字",
        "answer": str(answer.get("q1", ""))
    }


def test_simple_interrupt():
    """
    测试简单的中断和恢复流程
    """
    print("=" * 80)
    print("测试: 简单中断和恢复")
    print("=" * 80)
    
    builder = StateGraph(SimpleState)
    builder.add_node("ask", node_with_interrupt)
    builder.add_edge(START, "ask")
    builder.add_edge("ask", END)
    
    checkpointer = MemorySaver()
    app = builder.compile(checkpointer=checkpointer)
    
    thread_id = "test_simple_interrupt"
    config = {"configurable": {"thread_id": thread_id}}
    
    print("\n" + "-" * 80)
    print("步骤 1: 执行（预期触发中断）")
    print("-" * 80)
    
    state_input: SimpleState = {
        "messages": [],
        "question": "",
        "answer": ""
    }
    
    result = app.invoke(state_input, config=config)
    
    print(f"\n返回结果键: {list(result.keys())}")
    
    if "__interrupt__" in result:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            interrupt_payload = interrupts[0].value if interrupts else {}
            print(f"\n✓ 检测到中断")
            print(f"  payload 类型: {interrupt_payload.get('type')}")
            print(f"  问题: {interrupt_payload.get('questions', [{}])[0].get('question', '')}")
            
            print("\n" + "-" * 80)
            print("步骤 2: 恢复执行")
            print("-" * 80)
            
            resume_payload = {"q1": "张三"}
            print(f"恢复 payload: {resume_payload}")
            
            resumed_result = app.invoke(Command(resume=resume_payload), config=config)
            
            print(f"\n恢复后返回结果键: {list(resumed_result.keys())}")
            print(f"  messages: {resumed_result.get('messages', [])}")
            print(f"  question: {resumed_result.get('question', '')}")
            print(f"  answer: {resumed_result.get('answer', '')}")
            
            print("\n" + "=" * 80)
            print("测试完成: 简单中断恢复成功 ✓")
            print("=" * 80)
        else:
            print("\n✗ 中断列表为空")
    else:
        print("\n✗ 未检测到中断")


class SubgraphState(TypedDict):
    task: str
    result: str


def subgraph_node_with_interrupt(state: SubgraphState) -> SubgraphState:
    """
    子图中会触发中断的节点
    """
    payload = {
        "type": "inquiry_card",
        "questions": [{"id": "sub_q1", "question": "子图问题：请确认任务"}],
        "intro": "子图需要确认",
        "reasoning": "子图执行需要用户确认"
    }
    
    answer = interrupt(payload)
    
    return {
        "task": state.get("task", ""),
        "result": f"任务确认: {answer.get('sub_q1', '')}"
    }


def create_subgraph():
    """
    创建子图
    """
    builder = StateGraph(SubgraphState)
    builder.add_node("sub_task", subgraph_node_with_interrupt)
    builder.add_edge(START, "sub_task")
    builder.add_edge("sub_task", END)
    return builder


class MainState(TypedDict):
    messages: list[str]
    subgraph_task: str
    subgraph_result: str


def call_subgraph_node(state: MainState) -> MainState:
    """
    主图节点：调用子图
    """
    subgraph = create_subgraph().compile()
    
    sub_input: SubgraphState = {
        "task": state.get("subgraph_task", ""),
        "result": ""
    }
    
    sub_output = subgraph.invoke(sub_input)
    
    if isinstance(sub_output, dict) and "__interrupt__" in sub_output:
        interrupts = sub_output.get("__interrupt__", [])
        payload = interrupts[0].value if interrupts else {}
        
        answer = interrupt(payload)
        
        sub_output = subgraph.invoke(Command(resume=answer))
    
    return {
        "messages": state.get("messages", []) + [f"子图结果: {sub_output.get('result', '')}"],
        "subgraph_task": state.get("subgraph_task", ""),
        "subgraph_result": sub_output.get("result", "")
    }


def test_subgraph_interrupt():
    """
    测试子图中的中断和恢复（通过主图调用）
    """
    print("\n\n" + "=" * 80)
    print("测试: 子图中断和恢复（通过主图调用）")
    print("=" * 80)
    
    builder = StateGraph(MainState)
    builder.add_node("call_subgraph", call_subgraph_node)
    builder.add_edge(START, "call_subgraph")
    builder.add_edge("call_subgraph", END)
    
    checkpointer = MemorySaver()
    app = builder.compile(checkpointer=checkpointer)
    
    thread_id = "test_subgraph_interrupt"
    config = {"configurable": {"thread_id": thread_id}}
    
    print("\n" + "-" * 80)
    print("步骤 1: 执行（预期子图触发中断）")
    print("-" * 80)
    
    state_input: MainState = {
        "messages": [],
        "subgraph_task": "执行任务",
        "subgraph_result": ""
    }
    
    result = app.invoke(state_input, config=config)
    
    print(f"\n返回结果键: {list(result.keys())}")
    
    if "__interrupt__" in result:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            interrupt_payload = interrupts[0].value if interrupts else {}
            print(f"\n✓ 检测到中断（来自子图）")
            print(f"  payload 类型: {interrupt_payload.get('type')}")
            print(f"  问题: {interrupt_payload.get('questions', [{}])[0].get('question', '')}")
            
            print("\n" + "-" * 80)
            print("步骤 2: 恢复执行")
            print("-" * 80)
            
            resume_payload = {"sub_q1": "任务已确认"}
            print(f"恢复 payload: {resume_payload}")
            
            resumed_result = app.invoke(Command(resume=resume_payload), config=config)
            
            print(f"\n恢复后返回结果键: {list(resumed_result.keys())}")
            print(f"  messages: {resumed_result.get('messages', [])}")
            print(f"  subgraph_task: {resumed_result.get('subgraph_task', '')}")
            print(f"  subgraph_result: {resumed_result.get('subgraph_result', '')}")
            
            print("\n" + "=" * 80)
            print("测试完成: 子图中断恢复成功 ✓")
            print("=" * 80)
        else:
            print("\n✗ 中断列表为空")
    else:
        print("\n✗ 未检测到中断")


def main():
    print("\n" + "=" * 80)
    print("开始简单中断机制测试")
    print("=" * 80)
    
    try:
        test_simple_interrupt()
    except Exception as e:
        print(f"\n测试 1 出错: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        test_subgraph_interrupt()
    except Exception as e:
        print(f"\n测试 2 出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n\n" + "=" * 80)
    print("所有测试完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
