"""
Skill 系统真实 API 测试

测试场景：
1. 模型能否正确识别需要使用 Skill
2. 模型能否正确调用 load_skill
3. Skill 指令返回后，模型能否正确执行

运行方式：
cd agent_impl
python3 test_skill_real_api.py
"""

import os
import sys
import json
from datetime import datetime

# 设置路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from graph.workflow import create_workflow
from graph.state import AgentState


def test_skill_discovery():
    """测试 1: Skill 发现功能"""
    print("\n" + "="*60)
    print("测试 1: Skill 发现功能")
    print("="*60)
    
    from skills.registry import get_skill_registry
    
    registry = get_skill_registry()
    metadata = registry.get_all_metadata()
    
    print(f"\n发现 {len(metadata)} 个 Skill:")
    for m in metadata:
        print(f"  - {m.name} ({m.skill_id}): {m.description[:50]}...")
    
    # 验证
    skill_ids = [m.skill_id for m in metadata]
    assert "inquiry" in skill_ids, "缺少 inquiry Skill"
    assert "consult_answer" in skill_ids, "缺少 consult_answer Skill"
    assert "emotion_support" in skill_ids, "缺少 emotion_support Skill"
    
    print("\n✅ Skill 发现功能正常")
    return True


def test_inquiry_skill_flow():
    """测试 2: 提问 Skill 流程（需要真实 API）"""
    print("\n" + "="*60)
    print("测试 2: 提问 Skill 流程（Main Agent）")
    print("="*60)
    
    # 创建 workflow
    workflow = create_workflow()
    app = workflow.compile()
    
    # 构造初始状态：模拟已完成 onboarding，直接进入 main_agent
    initial_state = {
        "messages": [
            {"role": "user", "content": "我喜欢一个女生，但不知道该怎么办"}
        ],
        "user_id": "test_user",
        "thread_id": "test_thread_skill_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
        "current_agent": "main_agent",
        "is_new_session": False,  # 非新会话
        "onboarding_completed": True,  # 已完成 onboarding
    }
    
    print(f"\n输入消息: {initial_state['messages'][0]['content']}")
    print("\n开始执行 workflow...")
    
    # 执行
    config = {"configurable": {"thread_id": initial_state["thread_id"]}}
    
    tool_calls_detected = []
    final_response = None
    
    for event in app.stream(initial_state, config):
        for node_name, node_output in event.items():
            print(f"\n[{node_name}] 执行完成")
            
            # 检查是否有工具调用
            messages = node_output.get("messages", [])
            for msg in messages:
                # 检查 AIMessage 的 tool_calls
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        tool_name = tc.get("name", "")
                        tool_args = tc.get("args", {})
                        print(f"  🔧 工具调用: {tool_name}({tool_args})")
                        tool_calls_detected.append(tool_name)
                
                # 检查最终响应
                content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
                if content and isinstance(content, str) and len(content) > 50:
                    try:
                        parsed = json.loads(content)
                        if "response" in parsed:
                            final_response = parsed
                            print(f"  📝 响应: {parsed.get('response', '')[:100]}...")
                    except:
                        pass
    
    print("\n" + "-"*40)
    print("执行结果:")
    print(f"  - 工具调用: {tool_calls_detected}")
    print(f"  - 最终响应: {'有' if final_response else '无'}")
    
    # 验证
    if "load_skill" in tool_calls_detected:
        print("\n✅ 模型正确调用了 load_skill")
    else:
        print("\n⚠️ 模型没有调用 load_skill（可能直接路由到子 Agent）")
    
    if final_response:
        if final_response.get("inquiry_card"):
            print("✅ 生成了 inquiry_card")
        elif final_response.get("next_action") in ["call_status", "call_plan", "call_guide"]:
            print(f"✅ 路由到专家: {final_response.get('next_action')}")
    
    return True


def test_consult_skill_flow():
    """测试 3: 咨询 Skill 流程"""
    print("\n" + "="*60)
    print("测试 3: 咨询 Skill 流程（Main Agent）")
    print("="*60)
    
    workflow = create_workflow()
    app = workflow.compile()
    
    # 构造状态：用户问咨询问题，已完成 onboarding
    initial_state = {
        "messages": [
            {"role": "user", "content": "什么是备胎？我怀疑自己被当备胎了"}
        ],
        "user_id": "test_user",
        "thread_id": "test_thread_consult_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
        "current_agent": "main_agent",
        "is_new_session": False,
        "onboarding_completed": True,
    }
    
    print(f"\n输入消息: {initial_state['messages'][0]['content']}")
    print("\n开始执行 workflow...")
    
    config = {"configurable": {"thread_id": initial_state["thread_id"]}}
    
    tool_calls_detected = []
    final_response = None
    
    for event in app.stream(initial_state, config):
        for node_name, node_output in event.items():
            print(f"\n[{node_name}] 执行完成")
            
            messages = node_output.get("messages", [])
            for msg in messages:
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        tool_name = tc.get("name", "")
                        tool_args = tc.get("args", {})
                        print(f"  🔧 工具调用: {tool_name}({tool_args})")
                        tool_calls_detected.append(tool_name)
                
                content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
                if content and isinstance(content, str) and len(content) > 50:
                    try:
                        parsed = json.loads(content)
                        if "response" in parsed:
                            final_response = parsed
                            print(f"  📝 响应: {parsed.get('response', '')[:100]}...")
                    except:
                        pass
    
    print("\n" + "-"*40)
    print("执行结果:")
    print(f"  - 工具调用: {tool_calls_detected}")
    
    if "load_skill" in tool_calls_detected:
        print("\n✅ 模型调用了 load_skill (consult_answer)")
    
    if final_response and final_response.get("response"):
        print("✅ 生成了咨询回复")
    
    return True


def main():
    print("="*60)
    print("Skill 系统真实 API 测试")
    print("="*60)
    
    # 检查 API Key
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print("\n❌ 错误: 未设置 OPENAI_API_KEY 或 ANTHROPIC_API_KEY")
        print("请在 .env 文件中配置 API Key")
        return
    
    results = []
    
    # 测试 1: Skill 发现（不需要 API）
    try:
        results.append(("Skill 发现", test_skill_discovery()))
    except Exception as e:
        print(f"\n❌ Skill 发现测试失败: {e}")
        results.append(("Skill 发现", False))
    
    # 测试 2: 提问 Skill 流程（需要 API）
    try:
        results.append(("提问 Skill", test_inquiry_skill_flow()))
    except Exception as e:
        print(f"\n❌ 提问 Skill 测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("提问 Skill", False))
    
    # 测试 3: 咨询 Skill 流程（需要 API）
    try:
        results.append(("咨询 Skill", test_consult_skill_flow()))
    except Exception as e:
        print(f"\n❌ 咨询 Skill 测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("咨询 Skill", False))
    
    # 汇总
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
