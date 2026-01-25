"""
Skill 基础数据结构

用于 Skill Registry 和对外导出统一的元数据模型。
"""

from dataclasses import dataclass


@dataclass
class SkillMetadata:
    """Skill 元数据（用于主 Agent 的简短提示）"""
    skill_id: str
    name: str
    description: str
