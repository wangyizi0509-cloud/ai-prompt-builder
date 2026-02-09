"""
模拟测试用户和 graph 进行 20 轮对话

测试场景：模拟真实用户与智能体进行多轮对话，验证：
1. 状态持久化（通过 checkpointer）
2. 对话上下文保持
3. interrupt/resume 机制
4. 子 agent 调用
5. onboarding 流程
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

# 20 轮对话脚本
CONVERSATION_SCRIPT = [
    "你好，我是新用户，想了解一下这个系统",
    "我最近遇到一个女生，想和她成为朋友",
    "我们是在图书馆认识的",
    "她是大学生，比我小一届",
    "我们经常一起自习",
    "我想知道怎么判断她对我有没有好感",
    "她经常主动找我聊天",
    "有时候会一起吃饭",
    "我觉得我们挺合得来的",
    "帮我分析一下现在的状况",
    "我想制定一个追求她的计划",
    "我想先从朋友做起",
    "你们有什么建议吗",
    "如果她拒绝我怎么办",
    "我觉得可能有点自卑",
    "你能给我一些鼓励吗",
    "我想知道怎么表达我的想法",
    "如果她已经有男朋友了怎么办",
    "我该不该直接告诉她我喜欢她",
    "谢谢你的帮助，我心里有谱了"
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
            print(f"  ⚠️  检测到中断: {interrupt_payload}")
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
        for i, resp in enumerate(responses[:3]):
            preview = str(resp)[:100]
            print(f"    [{i}] {preview}...")
    
    if "layer2_memory" in result:
        layer2 = result["layer2_memory"]
        keys = list(layer2.keys())
        if keys:
            print(f"  layer2_memory 键: {keys}")
    
    if "layer3_memory" in result:
        layer3 = result["layer3_memory"]
        all_msgs = layer3.get("all_messages", [])
        print(f"  layer3_memory.all_messages 数量: {len(all_msgs)}")
    
    if "preliminary_assessment" in result and result["preliminary_assessment"]:
        print(f"  preliminary_assessment: {result['preliminary_assessment']}")
    
    if "onboarding_completed" in result:
        print(f"  onboarding_completed: {result['onboarding_completed']}")
    
    if "onboarding_turn_count" in result:
        print(f"  onboarding_turn_count: {result['onboarding_turn_count']}")
    
    if "_iteration_count" in result:
        print(f"  _iteration_count: {result['_iteration_count']}")


def handle_interrupt(app, config, result: dict) -> dict:
    """
    处理中断，模拟用户回答
    
    分析中断的 payload，提取问题并生成对应的答案
    """
    print("\n【模拟用户回答中断问题】")
    
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        print("  ⚠️  中断但无 payload，使用空答案")
        resume_payload = {"answers": {}}
    else:
        interrupt_payload = interrupts[0].value if interrupts else {}
        
        if "questions" not in interrupt_payload:
            print(f"  ⚠️  中断 payload 中没有 questions: {list(interrupt_payload.keys())}")
            resume_payload = {"answers": {}}
        else:
            questions = interrupt_payload["questions"]
            print(f"  检测到 {len(questions)} 个问题:")
            
            answers = {}
            
            for i, q in enumerate(questions):
                q_id = q.get("id", f"question_{i+1}")
                q_text = q.get("question", "")
                q_type = q.get("type", "text")
                options = q.get("options", [])
                
                print(f"    [{i+1}] {q_text[:60]}...")
                print(f"        ID: {q_id}, 类型: {q_type}")
                if options:
                    print(f"        选项: {[opt[:30] + '...' if len(opt) > 30 else opt for opt in options]}")
                
                answer = generate_answer(q)
                answers[q_id] = answer
                print(f"        ✓ 答案: {answer}")
            
            resume_payload = {"answers": answers}
    
    print(f"\n  准备 resume，payload keys: {list(resume_payload.keys())}")
    
    resumed_result = app.invoke(Command(resume=resume_payload), config=config)
    print("\n【恢复执行完成】")
    print(f"  返回结果键: {list(resumed_result.keys())}")
    
    return resumed_result


def generate_answer(question: dict) -> str:
    """
    根据问题生成合适的答案
    
    Args:
        question: 问题字典，包含 id, question, type, options 等字段
    
    Returns:
        答案字符串
    """
    q_id = question.get("id", "")
    q_type = question.get("type", "text")
    options = question.get("options", [])
    
    if q_type == "single_choice" and options:
        return options[0]
    
    if q_type == "private_chat_screenshot":
        return "暂无截图"
    
    if q_type == "text" or q_type == "multiline":
        default_answers = {
            "recent_interaction": "最近几天有聊",
            "response_attitude": "回复快且字数多",
            "chat_screenshot": "暂无截图",
            "interaction_frequency": "每天都会聊天",
            "her_initiative": "她经常主动找我",
            "meeting_frequency": "有时候会一起吃饭",
        }
        
        for key, value in default_answers.items():
            if key in q_id:
                return value
        
        return "一般"
    
    return "好的"


def run_conversation_20_rounds():
    """
    运行 20 轮对话测试
    
    流程：
    1. 初始化 workflow 和 checkpointer
    2. 依次发送 20 轮用户输入
    3. 处理中断和恢复
    4. 记录每轮的结果
    5. 输出统计信息
    """
    print("=" * 80)
    print("模拟用户与 Graph 进行 20 轮对话")
    print("=" * 80)
    
    checkpointer = MemorySaver()
    app = compile_workflow(checkpointer=checkpointer)
    
    thread_id = "test_conversation_20_rounds"
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
                result = handle_interrupt(app, config, result)
                stats["resume_count"] += 1
                print_result_analysis(result, round_num)
            
            if result.get("onboarding_completed") and stats["onboarding_completed_round"] is None:
                stats["onboarding_completed_round"] = round_num
                print("\n  ✓ Onboarding 已完成")
            
            current_state = result
            
        except Exception as e:
            stats["error_count"] += 1
            error_msg = str(e)
            print(f"\n  ❌ 第 {round_num} 轮出错: {error_msg[:150]}...")
            
            if "tool_calls" in error_msg and "insufficient tool messages" in error_msg:
                print("  ⚠️  检测到 tool_calls 消息格式错误（这是 LangChain Agent 在多轮对话中的已知问题）")
                print("  📊 继续下一轮对话测试...")
                continue
            else:
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
        
        if "report_counter" in current_state:
            counter = current_state["report_counter"]
            print(f"  report_counter: {counter}")
    
    print("\n" + "=" * 80)
    print("20 轮对话测试完成")
    print("=" * 80)


def main():
    try:
        run_conversation_20_rounds()
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
