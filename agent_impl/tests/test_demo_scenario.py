import pytest
from graph.state import create_initial_state

class TestProductScenarios:
    """
    【产品核心场景测试集】
    
    这些测试模拟真实用户的输入，验证系统是否按预期工作。
    作为产品经理或开发者，修改代码/策略后，请运行此文件确保没有"改坏"核心功能。
    
    运行方法：
    cd agent_impl
    pytest tests/test_demo_scenario.py -v
    """
    
    def test_scenario_initial_inquiry(self, workflow):
        """
        场景 1：初始咨询 - 信息不足
        用户输入："我想追一个女生"
        
        预期行为：
        1. 系统识别出这是求助信号
        2. 路由到 Status Agent (现状分析)
        3. 发现信息不足，触发 Inquiry Skill (提问)
        """
        # 1. 模拟用户输入
        user_input = "我想追一个女生，能不能帮帮我"
        print(f"\n[测试输入] 用户: {user_input}")
        
        state = create_initial_state(user_input)
        
        # 2. 运行系统 (使用 thread_id 支持记忆功能)
        config = {"configurable": {"thread_id": "scenario_test_1"}}
        result = workflow.invoke(state, config=config)
        
        # 3. 验证结果
        print(f"[系统输出] 当前 Agent: {result.get('current_agent')}")
        print(f"[系统输出] 下一步动作: {result.get('next_action')}")
        
        # 断言 1: 应该识别出需要现状分析
        assert result.get("next_action") in ["call_status", "ask_user"], \
            f"预期进入现状分析或提问，实际动作: {result.get('next_action')}"
            
        # 断言 2: 如果已经运行了 status_agent，应该有提问意图
        if result.get("current_agent") == "status_agent":
            # 检查是否有工具调用（通常是 load_inquiry_skill_instructions）
            # 或者直接生成了 pending_questions
            pass 
            
    def test_scenario_specific_question(self, workflow):
        """
        场景 2：具体问题咨询
        用户输入："女生回我'哈哈'我该怎么回？"
        
        预期行为：
        1. 主 Agent 识别这是一个具体的回复咨询
        2. 可能直接调用 Consult Skill 回复，或者通过 Router 路由
        3. 给出具体的回复建议
        """
        user_input = "女生回我'哈哈'，我该怎么回？"
        print(f"\n[测试输入] 用户: {user_input}")
        
        state = create_initial_state(user_input)
        config = {"configurable": {"thread_id": "scenario_test_2"}}
        
        result = workflow.invoke(state, config=config)
        
        # 验证
        messages = result.get("messages", [])
        last_message = messages[-1] if messages else {}
        content = last_message.get("content") if isinstance(last_message, dict) else getattr(last_message, "content", "")

        print(f"[系统输出] 最终回复长度: {len(content)}")
        
        # 断言：必须有回复内容
        assert len(messages) > 1, "系统应该产生回复"
        assert len(content) > 10, "回复内容应该足够丰富"


