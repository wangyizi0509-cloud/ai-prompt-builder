"""
Skill 系统简化测试

直接测试 Skill 组件，不走完整 workflow。

运行方式：
cd agent_impl
python3 test_skill_simple.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


def test_skill_discovery():
    """测试 1: Skill 发现"""
    print("\n" + "="*60)
    print("测试 1: Skill 发现")
    print("="*60)
    
    from skills.registry import get_skill_registry
    
    registry = get_skill_registry()
    metadata = registry.get_all_metadata()
    
    print(f"\n发现 {len(metadata)} 个 Skill:")
    for m in metadata:
        print(f"  - {m.name} ({m.skill_id})")
        print(f"    {m.description}")
    
    assert len(metadata) == 3, f"应有 3 个 Skill，实际 {len(metadata)}"
    print("\n✅ 通过")


def test_skill_instructions_loading():
    """测试 2: Skill 指令加载"""
    print("\n" + "="*60)
    print("测试 2: Skill 指令加载")
    print("="*60)
    
    from skills.registry import get_skill_registry
    
    registry = get_skill_registry()
    
    for skill_id in ["inquiry", "consult_answer", "emotion_support"]:
        print(f"\n加载 {skill_id}...")
        instructions = registry.get_skill_instructions(skill_id)
        
        # 检查执行触发提示
        has_trigger = "[执行触发]" in instructions
        print(f"  - 长度: {len(instructions)} 字符")
        print(f"  - 包含执行触发提示: {'✅' if has_trigger else '❌'}")
        print(f"  - 前 100 字符: {instructions[:100]}...")
        
        assert has_trigger, f"{skill_id} 缺少执行触发提示"
    
    print("\n✅ 通过")


def test_tool_invocation():
    """测试 3: 工具调用"""
    print("\n" + "="*60)
    print("测试 3: 工具调用 (load_skill)")
    print("="*60)
    
    from skills import create_all_skills_loader
    
    # 测试调用
    tool = create_all_skills_loader()
    result = tool.invoke({"skill_id": "inquiry"})
    
    print(f"\n调用 load_skill('inquiry'):")
    print(f"  - 返回类型: {type(result).__name__}")
    print(f"  - 返回长度: {len(result)} 字符")
    print(f"  - 包含执行触发: {'✅' if '[执行触发]' in result else '❌'}")
    
    assert isinstance(result, str), "返回应为字符串"
    assert len(result) > 100, "返回内容应超过 100 字符"
    assert "[执行触发]" in result, "应包含执行触发提示"
    
    print("\n✅ 通过")


def test_metadata_prompt_generation():
    """测试 4: 元数据 Prompt 生成"""
    print("\n" + "="*60)
    print("测试 4: 元数据 Prompt 生成")
    print("="*60)
    
    from skills.registry import get_skill_registry
    
    registry = get_skill_registry()
    prompt = registry.generate_metadata_prompt()
    
    print(f"\n生成的元数据 Prompt:\n")
    print(prompt)
    
    assert "inquiry" in prompt, "应包含 inquiry"
    assert "consult_answer" in prompt, "应包含 consult_answer"
    assert "emotion_support" in prompt, "应包含 emotion_support"
    
    print("\n✅ 通过")


def test_llm_skill_call():
    """测试 5: LLM 调用 Skill（真实 API）"""
    print("\n" + "="*60)
    print("测试 5: LLM 调用 Skill（真实 API）")
    print("="*60)
    
    from config import get_llm
    from skills import create_all_skills_loader
    from skills.registry import get_skill_registry
    
    # 检查 API Key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("\n⚠️ 跳过：未设置 DEEPSEEK_API_KEY")
        return
    
    # 创建 LLM 并绑定工具
    llm = get_llm(temperature=0)
    skill_tool = create_all_skills_loader()
    llm_with_tools = llm.bind_tools([skill_tool])
    
    # 构造 prompt
    registry = get_skill_registry()
    skills_metadata = registry.generate_metadata_prompt()
    
    prompt = f"""你是一个助手。

## 可用 Skills

{skills_metadata}

### 调用方式

需要使用 Skill 时，调用 `load_skill(skill_id)` 工具。

---

用户说：我不知道她喜不喜欢我，好焦虑

请根据用户需求，决定是否需要调用 Skill。如果需要情绪支持，调用 emotion_support Skill。
"""
    
    print("\n发送请求到 LLM...")
    response = llm_with_tools.invoke(prompt)
    
    print(f"\nLLM 响应:")
    print(f"  - 内容: {response.content[:100] if response.content else '(无)'}")
    print(f"  - 工具调用: {response.tool_calls}")
    
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        print(f"\n✅ LLM 调用了工具: {tool_call['name']}({tool_call['args']})")
        
        # 第二阶段：加载 Skill 指令并让模型执行
        skill_id = tool_call["args"].get("skill_id")
        instructions = skill_tool.invoke({"skill_id": skill_id})
        
        second_prompt = f"""你是一个助手。

你刚刚调用了 Skill，现在已获得完整指令。请直接执行指令并给出最终回复。

## Skill 指令
{instructions}

---

用户说：我不知道她喜不喜欢我，好焦虑
"""
        print("\n开始第二阶段执行...")
        second_response = llm.invoke(second_prompt)
        print(f"  - 第二阶段输出: {second_response.content[:120] if second_response.content else '(无)'}")
        
        assert second_response.content, "第二阶段应产生输出"
    else:
        print("\n⚠️ LLM 没有调用工具（可能直接回复了）")
    
    print("\n✅ 通过")


def main():
    print("="*60)
    print("Skill 系统简化测试")
    print("="*60)
    
    tests = [
        ("Skill 发现", test_skill_discovery),
        ("指令加载", test_skill_instructions_loading),
        ("工具调用", test_tool_invocation),
        ("元数据生成", test_metadata_prompt_generation),
        ("LLM Skill 调用", test_llm_skill_call),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            test_fn()
            results.append((name, True))
        except Exception as e:
            print(f"\n❌ {name} 失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
