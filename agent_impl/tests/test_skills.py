"""
Skills 测试
验证 registry 与指令加载流程
"""

import pytest
from skills import get_skill_registry, create_all_skills_loader, SkillMetadata


class TestSkillRegistry:
    """Skill 注册表测试"""
    
    def test_registry_contains_core_skills(self):
        """核心 Skill 必须被发现"""
        registry = get_skill_registry()
        skill_ids = registry.get_skill_ids()
        
        assert "inquiry" in skill_ids
        assert "consult_answer" in skill_ids
        assert "emotion_support" in skill_ids
    
    def test_registry_metadata_fields(self):
        """元数据字段完整"""
        registry = get_skill_registry()
        metadata_list = registry.get_all_metadata()
        
        assert metadata_list, "应至少包含一个 Skill 元数据"
        inquiry_meta = next((m for m in metadata_list if m.skill_id == "inquiry"), None)
        
        assert inquiry_meta is not None, "应包含 inquiry 元数据"
        assert isinstance(inquiry_meta, SkillMetadata)
        assert inquiry_meta.name, "应包含名称"
        assert inquiry_meta.description, "应包含描述"


class TestSkillLoader:
    """Skill 指令加载测试"""
    
    @pytest.mark.parametrize("skill_id", ["inquiry", "consult_answer", "emotion_support"])
    def test_load_skill_returns_content(self, skill_id):
        """指令应能成功加载且非空"""
        tool = create_all_skills_loader()
        content = tool.invoke({"skill_id": skill_id})
        
        assert isinstance(content, str)
        assert content.strip()