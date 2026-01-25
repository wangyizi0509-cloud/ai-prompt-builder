"""
Skill 加载工具 (Skill Loader Tool)

提供给 Agent 按需调用的工具，用于动态加载技能的完整执行指令。
实现渐进式披露机制：模型按需加载 Skill 指令。

重要：各 Agent 的 Skill 权限不同，必须使用 create_skill_loader() 创建定制工具
- status_agent, plan_agent, guide_agent: 只能用 inquiry
- main_agent: 可以用全部 skills
"""

from typing import List

from langchain_core.tools import StructuredTool

from graph.tools.schemas import LoadSkillInput
from skills.registry import get_skill_registry


# ============================================================
# 权限定制的工具工厂
# ============================================================

def create_skill_loader(allowed_skills: List[str]) -> StructuredTool:
    """
    创建指定权限的 load_skill 工具
    - 权限仅在工具挂载层控制（不做内部校验）
    """
    skill_list = ", ".join(allowed_skills)

    def _load_skill(skill_id: str) -> str:
        registry = get_skill_registry()
        return registry.get_skill_instructions(skill_id)

    description = (
        "获取 Skill 的执行指令。\n"
        "工具仅返回执行规则与格式要求，不会直接给出问题或回复内容。\n"
        "调用后请根据返回指令自行生成 inquiry_card 或回复。\n"
        "Args:\n"
        f"    skill_id: Skill ID，可选值：{skill_list}\n"
        "Returns:\n"
        "    完整的 Skill 执行指令（Markdown）"
    )

    return StructuredTool.from_function(
        func=_load_skill,
        name="load_skill",
        description=description,
        args_schema=LoadSkillInput,
    )


# ============================================================
# 预置的定制工具（便于导入）
# ============================================================

def create_inquiry_only_loader() -> StructuredTool:
    """创建只允许 inquiry skill 的工具（子 agent）"""
    return create_skill_loader(["inquiry"])


def create_all_skills_loader() -> StructuredTool:
    """创建允许全部 skills 的工具（main_agent）"""
    return create_skill_loader(["inquiry", "consult_answer", "emotion_support"])
