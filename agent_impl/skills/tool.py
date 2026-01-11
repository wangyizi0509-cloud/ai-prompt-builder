"""
Skill 加载工具 (Skill Loader Tool)

提供给 Agent 按需调用的工具，用于动态加载技能的完整执行指令。
实现 Anthropic 渐进式披露机制的"模型自主加载"模式。

工作流程：
1. Agent 在系统提示中只看到 Skill 的元数据（name + description）
2. 当 Agent 判断需要使用某个 Skill 时，主动调用此工具
3. 工具返回完整的 Skill 指令，Agent 在同一轮对话中继续执行
"""

from langchain.tools import tool
from utils.prompt_loader import load_prompt


# 可用技能 ID 列表（用于验证和提示）
AVAILABLE_SKILLS = [
    "inquiry_skill",           # 提问引导
    "consult_answer_skill",    # 解答情感疑惑
    "emotion_support_skill",   # 情感陪伴
]


@tool
def load_inquiry_skill_instructions() -> str:
    """获取『提问引导』技能的完整执行指令。
    当你需要通过结构化的问题收集用户信息（如现状信息、对话截图等）时，请调用此工具。
    """
    return load_prompt("inquiry_skill")


@tool
def load_consult_answer_skill_instructions() -> str:
    """获取『解答情感疑惑』技能的完整执行指令。
    当用户提出具体的情感问题（如"她这样是喜欢我吗？"）需要你进行专业分析和解答时，请调用此工具。
    """
    return load_prompt("consult_answer_skill")


@tool
def load_emotion_support_skill_instructions() -> str:
    """获取『情感陪伴』技能的完整执行指令。
    当用户正在表达或宣泄情绪（如沮丧、焦虑、开心等），需要你提供情感支持、共情和陪伴时，请调用此工具。
    """
    return load_prompt("emotion_support_skill")


def get_skill_tool(skill_id: str):
    """
    获取指定 ID 的 Skill 加载工具（用于主 Agent）
    """
    if skill_id == "inquiry_skill":
        return load_inquiry_skill_instructions
    elif skill_id == "consult_answer_skill":
        return load_consult_answer_skill_instructions
    elif skill_id == "emotion_support_skill":
        return load_emotion_support_skill_instructions
    return None


@tool
def load_skill_instructions(skill_id: str) -> str:
    """
    [已废弃] 获取指定技能的完整执行指令。请改用专门的工具。
    
    Args:
        skill_id: 技能ID (inquiry_skill/consult_answer_skill/emotion_support_skill)
    """
    return load_prompt(skill_id)


def get_skill_tool():
    """
    获取 Skill 加载工具实例
    
    Returns:
        load_skill_instructions 工具
    """
    return load_skill_instructions

