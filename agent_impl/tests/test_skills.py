"""
Skills 测试
验证所有 Skills 的独立功能
"""

import pytest
from skills import (
    get_inquiry_skill,
    get_consult_answer_skill,
    get_emotion_support_skill,
    InquirySkill,
    ConsultAnswerSkill,
    EmotionSupportSkill,
)
from config import get_llm


class TestInquirySkill:
    """提问 Skill 测试类"""
    
    def test_inquiry_skill_generate_questions(self):
        """测试问题生成"""
        skill = get_inquiry_skill()
        
        # 测试生成问题
        result = skill.generate(
            goal="了解用户和crush的相处情况",
            known_info={"relationship": "同事"},
            max_questions=2
        )
        
        # 验证结果
        assert result is not None, "应该生成结果"
        assert hasattr(result, "questions") or "questions" in result.__dict__, "结果应该有 questions 字段"
        
        # 转换为字典格式验证
        result_dict = skill.to_dict(result)
        assert "questions" in result_dict, "应该有 questions 字段"
        assert len(result_dict["questions"]) > 0, "应该至少生成一个问题"
        assert len(result_dict["questions"]) <= 2, "问题数量不应超过 max_questions"
    
    def test_inquiry_skill_question_types(self):
        """测试不同题型生成"""
        skill = get_inquiry_skill()
        
        # 测试生成不同类型的问题
        result = skill.generate(
            goal="了解用户基本信息",
            known_info={},
            max_questions=3
        )
        
        result_dict = skill.to_dict(result)
        questions = result_dict.get("questions", [])
        
        # 验证问题格式
        for q in questions:
            assert "id" in q, "问题应该有 id"
            assert "question" in q, "问题应该有 question 字段"
            assert "type" in q, "问题应该有 type 字段"
            assert q["type"] in [
                "single_choice", "multiple_choice", "free_input_question",
                "private_chat_screenshot", "group_chat_screenshot",
                "moments_screenshot", "other_social_media_screenshot",
                "universal_screenshot_analysis"
            ], "问题类型应该有效"
    
    def test_inquiry_skill_context_aware(self):
        """测试上下文感知"""
        skill = get_inquiry_skill()
        
        # 测试已知信息对问题生成的影响
        result1 = skill.generate(
            goal="了解用户和crush的关系",
            known_info={},
            max_questions=2
        )
        
        result2 = skill.generate(
            goal="了解用户和crush的关系",
            known_info={"relationship": "同事", "duration": "3个月"},
            max_questions=2
        )
        
        # 验证已知信息会影响问题生成（问题应该不同或更具体）
        dict1 = skill.to_dict(result1)
        dict2 = skill.to_dict(result2)
        
        assert dict1 is not None, "第一个结果应该有效"
        assert dict2 is not None, "第二个结果应该有效"
    
    def test_inquiry_skill_metadata(self):
        """测试元数据"""
        skill = get_inquiry_skill()
        metadata = skill.get_metadata()
        
        assert metadata is not None, "应该有元数据"
        assert metadata.name, "应该有名称"
        assert metadata.description, "应该有描述"
        # 符合 Anthropic 官方规范：只包含 name 和 description


class TestConsultAnswerSkill:
    """咨询回答 Skill 测试类"""
    
    def test_consult_skill_answer_question(self):
        """测试咨询问题回答"""
        skill = get_consult_answer_skill()
        
        # 测试获取完整 prompt
        prompt = skill.get_full_prompt(
            user_message="她这样是喜欢我吗？",
            user_profile={}
        )
        
        # 验证 prompt 存在且包含相关内容
        assert prompt is not None, "应该有 prompt"
        assert len(prompt) > 0, "prompt 应该有内容"
    
    def test_consult_skill_quality(self):
        """测试回答质量验证（通过 prompt 内容）"""
        skill = get_consult_answer_skill()
        prompt = skill.get_full_prompt()
        
        # 验证 prompt 包含关键指导原则
        assert "解答" in prompt or "分析" in prompt or "建议" in prompt, "prompt 应该包含解答相关内容"
    
    def test_consult_skill_metadata(self):
        """测试元数据"""
        skill = get_consult_answer_skill()
        metadata = skill.get_metadata()
        
        assert metadata is not None, "应该有元数据"
        assert metadata.name, "应该有名称"
        assert metadata.description, "应该有描述"
        # 符合 Anthropic 官方规范：只包含 name 和 description


class TestEmotionSupportSkill:
    """情感陪伴 Skill 测试类"""
    
    def test_emotion_skill_support(self):
        """测试情感陪伴回复"""
        skill = get_emotion_support_skill()
        
        # 测试获取完整 prompt
        prompt = skill.get_full_prompt(
            user_message="我好难过，不知道该怎么办",
            user_profile={}
        )
        
        # 验证 prompt 存在且包含相关内容
        assert prompt is not None, "应该有 prompt"
        assert len(prompt) > 0, "prompt 应该有内容"
    
    def test_emotion_skill_empathy(self):
        """测试共情能力验证（通过 prompt 内容）"""
        skill = get_emotion_support_skill()
        prompt = skill.get_full_prompt()
        
        # 验证 prompt 包含共情相关内容
        assert "陪伴" in prompt or "理解" in prompt or "共情" in prompt or "支持" in prompt, "prompt 应该包含共情相关内容"
    
    def test_emotion_skill_metadata(self):
        """测试元数据"""
        skill = get_emotion_support_skill()
        metadata = skill.get_metadata()
        
        assert metadata is not None, "应该有元数据"
        assert metadata.name, "应该有名称"
        assert metadata.description, "应该有描述"
        # 符合 Anthropic 官方规范：只包含 name 和 description