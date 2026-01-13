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
def load_skill_instructions(skill_id: str) -> str:
    """
    获取指定技能的完整执行指令。
    当需要提问、咨询回复或情感陪伴时调用此工具。
    
    Args:
        skill_id: 技能ID，可选值：
            - inquiry_skill: 提问引导技能，生成结构化的引导性问题
            - consult_answer_skill: 解答情感疑惑技能，提供专业分析和解答
            - emotion_support_skill: 情感陪伴技能，提供情感支持和陪伴
    
    Returns:
        技能的完整执行指令（Markdown 格式）
    """
    if skill_id not in AVAILABLE_SKILLS:
        return f"错误：未知的技能 ID '{skill_id}'。可用技能：{', '.join(AVAILABLE_SKILLS)}"
    
    try:
        return load_prompt(skill_id)
    except FileNotFoundError:
        return f"错误：找不到技能 '{skill_id}' 的指令文件"
    except Exception as e:
        return f"错误：加载技能 '{skill_id}' 时发生异常：{str(e)}"


def get_skill_tool():
    """
    获取 Skill 加载工具实例
    
    Returns:
        load_skill_instructions 工具
    """
    return load_skill_instructions

