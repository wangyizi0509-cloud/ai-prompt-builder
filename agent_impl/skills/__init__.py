"""
Skills 模块 - 入口导出

当前架构：
- Skill 元数据由 registry 自动扫描 definitions/ 目录
- 各 Agent 使用 create_skill_loader() 创建定制工具（限制可用 skills）

重要：不同 Agent 有不同的 Skill 权限
- status_agent, plan_agent, guide_agent: 只能用 inquiry
- main_agent: 可以用全部 skills
"""

from .base import SkillMetadata
from .registry import get_skill_registry
from .tool import (
    create_skill_loader,         # 工厂函数：创建定制工具
    create_inquiry_only_loader,  # 便捷函数：只允许 inquiry
    create_all_skills_loader,    # 便捷函数：允许全部
)

__all__ = [
    "SkillMetadata",
    "get_skill_registry",
    "create_skill_loader",
    "create_inquiry_only_loader",
    "create_all_skills_loader",
]
