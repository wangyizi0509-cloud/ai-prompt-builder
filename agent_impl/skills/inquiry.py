"""
提问 Skill (Inquiry Skill)
可被所有 Agent 调用的共享能力模块

基于 Anthropic Agent Skills 设计：
- 属于 PromptSkill 类型（在主 Agent 的同一次调用中完成）
- 采用渐进式披露：平时只加载元数据，需要时才加载完整 prompt
- 通过两阶段调用实现：第一阶段判断，第二阶段加载完整 prompt 生成结果
"""

import json
from typing import Optional, Literal
from pydantic import BaseModel, Field

from skills.base import PromptSkill
from utils.prompt_loader import load_prompt


# ============ 输入输出数据结构 ============

# 题目类型枚举（与策略库 Pre_Question_Gen 保持一致）
QuestionType = Literal[
    # 基础题型
    "single_choice",           # 单选题
    "multiple_choice",         # 多选题
    "free_input_question",     # 自由输入题
    # 证据上传类（截图会经过多模态模型转文本）
    "private_chat_screenshot",       # 私聊截图
    "group_chat_screenshot",         # 群聊截图
    "moments_screenshot",            # 朋友圈截图
    "other_social_media_screenshot", # 其他社媒截图
    "universal_screenshot_analysis",  # 通用截图分析
]

class InquiryInput(BaseModel):
    """提问 Skill 输入"""
    goal: str = Field(description="提问目标，说明需要了解什么信息")
    known_info: dict = Field(default_factory=dict, description="已知信息")
    max_questions: int = Field(default=2, ge=1, le=4, description="最多生成几个问题（1-4个）")
    style: str = Field(default="casual", description="提问风格: casual/formal")
    avoid_topics: list[str] = Field(default_factory=list, description="需要避免的话题")


class Question(BaseModel):
    """单个问题（与策略库 Pre_Question_Gen 输出格式对齐）"""
    id: str = Field(description="问题唯一标识")
    question: str = Field(description="问题内容，只写问题，不要包含选项内容")
    type: QuestionType = Field(description="题目类型，7种枚举之一")
    options: Optional[list[str]] = Field(default=None, description="选项列表，最多4个。仅 single_choice 或 multiple_choice 需要填写")
    is_required: bool = Field(default=True, description="是否必填")
    purpose: str = Field(default="", description="问这个问题的目的（内部分析用）")


class InquiryOutput(BaseModel):
    """提问 Skill 输出 - 用于前端渲染问题卡片"""
    questions: list[Question] = Field(description="问题列表，1-4个问题")
    intro: str = Field(default="", description="引导语（简短、有角色感）")
    reasoning: str = Field(default="", description="内部分析（为什么问这些问题）")


# ============ Skill 实现 ============

class InquirySkill(PromptSkill):
    """
    提问 Skill
    
    根据目标和已知信息，生成引导性问题
    可被主 Agent 和所有子 Agent 调用
    
    属于 PromptSkill：在主 Agent 的同一次调用中完成
    采用渐进式披露：第一阶段只加载元数据，第二阶段加载完整 prompt
    
    符合 Anthropic 官方方法：元数据从 prompts/inquiry_skill.md 的 YAML frontmatter 读取
    """
    
    _prompt_name = "inquiry_skill"
    
    def get_full_prompt(self, **kwargs) -> str:
        """
        获取完整的 Skill Prompt（第二阶段加载）
        
        注意：现在 InquirySkill 是 PromptSkill，完整 prompt 会在第二阶段加载到主 Agent 的 prompt 中
        """
        try:
            return load_prompt("inquiry_skill")
        except FileNotFoundError:
            return self._get_default_prompt()
    
    def _parse_inquiry_card(self, data: dict) -> dict:
        """
        解析 inquiry_card 数据（用于验证和格式化）
        
        注意：现在由主 Agent 直接生成 inquiry_card，这个方法仅用于辅助验证
        """
        # 验证和格式化 inquiry_card 数据
        if not data or not isinstance(data, dict):
            return None
        
        questions = data.get("questions", [])
        if not questions:
            return None
        
        # 确保问题格式正确
        formatted_questions = []
        for q in questions:
            if isinstance(q, dict) and "question" in q:
                formatted_questions.append(q)
        
        if not formatted_questions:
            return None
        
        return {
            "questions": formatted_questions,
            "intro": data.get("intro", ""),
            "reasoning": data.get("reasoning", ""),
        }
    
    def _get_default_prompt(self) -> str:
        """获取默认 Prompt - 对应 inquiry_skill.md 的简化版"""
        return """# Inquiry Skill Protocol (提问能力协议)

本模块定义了生成 `inquiry_card` 的标准协议。

## 1. 核心原则
本 Skill 不做决策，只提供**提问方法论**。请基于你（Agent）当前上下文中的**提问目标**和**已知信息**，利用本工具生成最高效的问题卡片。

## 2. 题型定义
- **定时间/地点/预算**: 使用 `single_choice` / `multiple_choice`
- **分析证据**: 使用 `_screenshot` 类
- **开放描述**: 使用 `free_input_question`

## 3. 输出协议 (Schema)
请在 `inquiry_card` 字段中填充以下 JSON：

```json
{
  "questions": [
    {
      "id": "unique_id",
      "question": "问题文案",
      "type": "single_choice|free_input_question|...",
      "options": ["选项A", "选项B"],
      "is_required": true,
      "purpose": "意图"
    }
  ],
  "intro": "引导语",
  "reasoning": "思考过程"
}
```
"""

# 创建全局实例
_inquiry_skill_instance = None


def get_inquiry_skill() -> InquirySkill:
    """获取提问 Skill 实例（单例模式）"""
    global _inquiry_skill_instance
    if _inquiry_skill_instance is None:
        _inquiry_skill_instance = InquirySkill()
    return _inquiry_skill_instance
