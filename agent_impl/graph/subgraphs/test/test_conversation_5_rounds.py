"""
模拟测试用户和 graph 进行 5 轮对话（快速验证版）
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from graph.workflow import compile_workflow
from graph.state import create_initial_state, convert_message_to_dict
from utils.reasoning_content import extract_reasoning_content

load_dotenv()

# 5 轮对话脚本
CONVERSATION_SCRIPT = [
    "你好，我是新用户，想了解一下这个系统",
    "我最近遇到一个女生，想和她成为朋友",
    "我们是在图书馆认识的",
    "她是大学生，比我小一届",
    "我们经常一起自习"
]


def print_round_header(round_num: int, total_rounds: int):
    """打印轮次头部"""
    print("\n" + "=" * 80)
    print(f"第 {round_num}/{total_rounds} 轮对话")
    print("=" * 80)


def print_user_input(user_input: str):
    """打印用户输入"""
    print("\n【用户输入】")
    print(f"  {user_input}")


def print_result_analysis(result: dict, round_num: int):
    """打印结果分析"""
    print("\n【结果分析】")
    
    print(f"  返回结果键: {list(result.keys())}")
    
    if "__interrupt__" in result:
        interrupts = result.get("__interrupt__", [])
        if interrupts:
            interrupt_payload = interrupts[0].value if interrupts else {}
            print(f"  ⚠️  检测到中断")
            if "questions" in interrupt_payload:
                questions = interrupt_payload["questions"]
                print(f"  问题数: {len(questions)}")
                for i, q in enumerate(questions[:2]):
                    print(f"    [{i+1}] {q.get('question', '')[:60]}...")
        else:
            print("  ⚠️  检测到中断但 payload 为空")
    
    if "messages" in result:
        msgs = result["messages"]
        print(f"  消息数: {len(msgs)}")
        
        reasoning_count = 0
        for msg in msgs:
            msg_dict = convert_message_to_dict(msg)
            reasoning = extract_reasoning_content(msg_dict)
            if reasoning:
                reasoning_count += 1
        
        if reasoning_count > 0:
            print(f"  包含 reasoning_content 的消息: {reasoning_count} 条")
    
    if "pending_responses" in result:
        responses = result["pending_responses"]
        print(f"  pending_responses 数量: {len(responses)}")
        for i, resp in enumerate(responses[:2]):
            preview = str(resp.get("content", "")[:80])
            print(f"    [{i}] {preview}...")
    
    if "layer3_memory" in result:
        layer3 = result["layer3_memory"]
        all_msgs = layer3.get("all_messages", [])
        print(f"  layer3_memory.all_messages 数量: {len(all_msgs)}")
    
    if "preliminary_assessment" in result and result["preliminary_assessment"]:
        verdict = result["preliminary_assessment"].get("verdict", "")
        print(f"  preliminary_assessment.verdict: {verdict}")
    
    if "onboarding_completed" in result:
        print(f"  onboarding_completed: {result['onboarding_completed']}")
    
    if "onboarding_turn_count" in result:
        print(f"  onboarding_turn_count: {result['onboarding_turn_count']}")
    
    if "_iteration_count" in result:
        print(f"  _iteration_count: {result['_iteration_count']}")


def handle_interrupt(app, config, result: dict, round_num: int) -> dict:
    """处理中断，模拟用户回答"""
    print("\n【模拟用户回答中断问题】")
    
    resume_payload = {
        "answers": {
            "recent_interaction": "最近几天有聊",
            "response_attitude": "回复快且字数多",
            "chat_screenshot": "暂无截图"
        }
    }
    print(f"  resume_payload: {resume_payload}")
    
    resumed_result = app.invoke(Command(resume=resume_payload), config=config)
    print("\n【恢复执行完成】")
    print(f"  返回结果键: {list(resumed_result.keys())}")
    
    return resumed_result


def run_conversation_5_rounds():
    """运行 5 轮对话测试"""
    print("=" * 80)
    print("模拟用户与 Graph 进行 5 轮对话")
    print("=" * 80)
    
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    thread_id = "test_conversation_5_rounds"
    config = {"configurable": {"thread_id": thread_id}}
    
    total_rounds = len(CONVERSATION_SCRIPT)
    stats = {
        "total_rounds": total_rounds,
        "interrupt_count": 0,
        "resume_count": 0,
        "onboarding_completed_round": None,
        "error_count": 0
    }
    
    current_state = None
    
    for round_num, user_input in enumerate(CONVERSATION_SCRIPT, 1):
        print_round_header(round_num, total_rounds)
        print_user_input(user_input)
        
        try:
            if current_state is None:
                state_input = create_initial_state(user_input)
            else:
                state_input = {
                    **current_state,
                    "user_message": user_input,
                }
            
            print("\n【调用 workflow】")
            result = app.invoke(state_input, config=config)
            
            print_result_analysis(result, round_num)
            
            if "__interrupt__" in result:
                stats["interrupt_count"] += 1
                result = handle_interrupt(app, config, result, round_num)
                stats["resume_count"] += 1
                print_result_analysis(result, round_num)
            
            if result.get("onboarding_completed") and stats["onboarding_completed_round"] is None:
                stats["onboarding_completed_round"] = round_num
                print("\n  ✓ Onboarding 已完成")
            
            current_state = result
            
        except Exception as e:
            stats["error_count"] += 1
            print(f"\n  ❌ 第 {round_num} 轮出错: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print("\n" + "=" * 80)
    print("对话统计")
    print("=" * 80)
    print(f"  总轮数: {stats['total_rounds']}")
    print(f"  中断次数: {stats['interrupt_count']}")
    print(f"  恢复次数: {stats['resume_count']}")
    print(f"  Onboarding 完成轮次: {stats['onboarding_completed_round']}")
    print(f"  错误次数: {stats['error_count']}")
    
    if current_state:
        print("\n【最终状态快照】")
        if "messages" in current_state:
            msgs = current_state["messages"]
            print(f"  最终消息数: {len(msgs)}")
        
        if "layer3_memory" in current_state:
            layer3 = current_state["layer3_memory"]
            all_msgs = layer3.get("all_messages", [])
            print(f"  layer3_memory.all_messages 数量: {len(all_msgs)}")
        
        if "layer2_memory" in current_state:
            layer2 = current_state["layer2_memory"]
            print(f"  layer2_memory 键: {list(layer2.keys())}")
    
    print("\n" + "=" * 80)
    print("5 轮对话测试完成")
    print("=" * 80)


def main():
    try:
        run_conversation_5_rounds()
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
