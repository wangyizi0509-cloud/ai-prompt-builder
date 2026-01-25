"""
Skill 注册表 (Skill Registry)

实现 Anthropic 渐进式披露架构的核心组件。
自动扫描 definitions/ 目录，管理所有 Skill 的元数据和指令加载。

架构说明：
1. Metadata Level：name + description，平时只加载这些到 prompt
2. Instruction Level：完整的 skill prompt，需要时才通过工具加载
"""

from pathlib import Path
from typing import Dict, List, Optional

from utils.prompt_loader import parse_frontmatter
from skills.base import SkillMetadata


# Skill 定义目录路径
DEFINITIONS_DIR = Path(__file__).parent / "definitions"


class SkillRegistry:
    """
    Skill 注册表
    
    负责：
    1. 自动扫描 definitions/ 目录发现所有 Skill
    2. 提供元数据查询（用于注入 prompt）
    3. 提供完整指令加载（用于工具调用）
    """
    
    def __init__(self):
        self._skills: Dict[str, SkillMetadata] = {}
        self._scan_skills()
    
    def _scan_skills(self) -> None:
        """
        扫描 definitions/ 目录，自动发现所有 Skill
        
        目录结构要求：
        definitions/
        ├── skill_id_1/
        │   └── SKILL.md
        ├── skill_id_2/
        │   └── SKILL.md
        └── ...
        """
        if not DEFINITIONS_DIR.exists():
            return
        
        for skill_dir in DEFINITIONS_DIR.iterdir():
            if not skill_dir.is_dir():
                continue
            
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            
            skill_id = skill_dir.name
            
            try:
                with open(skill_file, "r", encoding="utf-8") as f:
                    content = f.read()
                
                frontmatter, _ = parse_frontmatter(content)
                
                if frontmatter and "name" in frontmatter and "description" in frontmatter:
                    self._skills[skill_id] = SkillMetadata(
                        skill_id=skill_id,
                        name=frontmatter["name"],
                        description=frontmatter["description"]
                    )
            except Exception as e:
                # 跳过无法解析的 Skill 文件
                print(f"Warning: 无法解析 Skill 文件 {skill_file}: {e}")
    
    def get_all_metadata(self) -> List[SkillMetadata]:
        """
        返回所有 Skill 的元数据列表
        
        Returns:
            SkillMetadata 对象列表
        """
        return list(self._skills.values())
    
    def get_skill_instructions(self, skill_id: str) -> str:
        """
        返回指定 Skill 的完整指令
        
        Args:
            skill_id: Skill ID（文件夹名）
        
        Returns:
            完整的 Skill 指令内容（去除 frontmatter）
        
        Raises:
            ValueError: 如果 skill_id 不存在
        """
        if skill_id not in self._skills:
            available = ", ".join(self._skills.keys())
            raise ValueError(f"未知的 Skill ID: {skill_id}。可用的 Skill: {available}")
        
        skill_file = DEFINITIONS_DIR / skill_id / "SKILL.md"
        
        with open(skill_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        _, instructions = parse_frontmatter(content)
        return instructions.strip()
    
    def generate_metadata_prompt(self) -> str:
        """
        生成元数据列表字符串（用于注入 prompt）
        
        返回格式：
        - **Skill名称**：描述
        - **Skill名称**：描述
        ...
        
        Returns:
            格式化的元数据字符串
        """
        if not self._skills:
            return "（暂无可用 Skill）"
        
        lines = []
        for skill in self._skills.values():
            lines.append(f"- **{skill.name}** (`{skill.skill_id}`)：{skill.description}")
        
        return "\n".join(lines)
    
    def get_skill_ids(self) -> List[str]:
        """
        获取所有可用的 Skill ID
        
        Returns:
            Skill ID 列表
        """
        return list(self._skills.keys())


# 全局单例
_registry_instance: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """
    获取全局 SkillRegistry 单例
    
    Returns:
        SkillRegistry 实例
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = SkillRegistry()
    return _registry_instance
