"""
Skills 模块 - 共享能力模块

基于 Anthropic Agent Skills 设计理念：渐进式披露（Progressive Disclosure）
- PromptSkill: 动态扩展主 Agent 的 prompt（如咨询 Skills）
- GeneratorSkill: 独立调用 LLM 生成结构化输出（如提问 Skill）
- load_skill_instructions: 工具函数，供 Agent 自主调用加载技能指令
"""

from .base import BaseSkill, PromptSkill, GeneratorSkill, SkillMetadata
from .inquiry import InquirySkill, get_inquiry_skill
from .consult import (
    ConsultAnswerSkill, 
    EmotionSupportSkill,
    get_consult_answer_skill,
    get_emotion_support_skill,
)
from .tool import (
    load_skill_instructions, 
    load_inquiry_skill_instructions,
    load_consult_answer_skill_instructions,
    load_emotion_support_skill_instructions,
    get_skill_tool, 
    AVAILABLE_SKILLS
)

__all__ = [
    # 基类
    "BaseSkill",
    "PromptSkill", 
    "GeneratorSkill",
    "SkillMetadata",
    # 提问 Skill
    "InquirySkill",
    "get_inquiry_skill",
    # 咨询 Skills
    "ConsultAnswerSkill",
    "EmotionSupportSkill",
    "get_consult_answer_skill",
    "get_emotion_support_skill",
    # 工具函数（用于 Tool-based 加载）
    "load_skill_instructions",
    "load_inquiry_skill_instructions",
    "load_consult_answer_skill_instructions",
    "load_emotion_support_skill_instructions",
    "get_skill_tool",
    "AVAILABLE_SKILLS",
]

