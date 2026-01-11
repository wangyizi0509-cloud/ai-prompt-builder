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

# 信息归属类型枚举
InfoType = Literal[1, 2, 3, 4]
# 1: 用户信息
# 2: Crush信息
# 3: 双方相处信息
# 4: 行动专属动态信息

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
    info_type: InfoType = Field(description="信息归属类型：1=用户信息, 2=Crush信息, 3=双方相处信息, 4=行动专属动态信息")
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
    
    def _get_fallback_output(self) -> dict:
        """解析失败时的默认输出"""
        return {
            "questions": [
                {
                    "id": "q1",
                    "question": "你能简单说说你们目前的情况吗？",
                    "type": "free_input_question",
                    "info_type": 3,  # 双方相处信息
                    "is_required": True,
                    "purpose": "了解基本情况",
                }
            ],
            "intro": "为了更好地帮你，我需要了解一些情况～",
            "reasoning": "无法解析 LLM 输出，使用默认问题",
        }
    
    def _get_default_prompt(self) -> str:
        """获取默认 Prompt - 与策略库 Pre_Question_Gen 保持一致"""
        return """# 提问 Skill

你是恋爱军师「小话」的提问能力模块。你的任务是基于提问目标和已知信息，生成精准、高效的引导性问题。

---

## 提问目标
{goal}

## 已知信息
{known_info}

## 约束条件
- 最多生成 {max_questions} 个问题（严格控制在 1-4 个）
- 提问风格：{style}
- 需要避免的话题：{avoid_topics}

---

## 提问逻辑法则 (Gap Analysis)

在生成问题前，请进行以下逻辑推演：

1. **锁定变量**：根据提问目标，列出执行该动作所需的必要参数（时间、地点、预算、当前情绪窗口、对方最新动态等）。
2. **排除已知**：检查已知信息，如果某些参数已知，**严禁重复提问**。
3. **转化缺口**：将"缺失的必要参数"转化为具体问题。

### 场景化提问示例（思维链参考）：
* **场景 A：目标是"发起聊天破冰"**
    * *Gap*：不知道对方最近发了什么朋友圈（找话题钩子），也不知道上次聊完后的收尾状态。
    * *Question*：要求上传对方朋友圈截图 + 上次聊天结尾截图。
* **场景 B：目标是"线下邀约"**
    * *Gap*：不知道用户想约饭还是看展（偏好），不知道预算，不知道哪天有空。
    * *Question*：提供选项让用户选活动类型、预算范围、时间段。
* **场景 C：目标是"冷冻/断联"**
    * *Gap*：断联最大的阻碍是被动见面。
    * *Question*："未来 3 天你们在公司/学校会有不可避免的碰面机会吗？"

---

## 提问执行规范

### 可问的题目类型 (Type Enum)
请严格从以下 7 种类型中选择：
1. 基础题型：
    - 单选题："single_choice"
    - 多选题："multiple_choice"
    - 自由输入题："free_input_question"
2. 证据上传类（Evidence Upload）：
    - 私聊截图："private_chat_screenshot"
    - 群聊截图："group_chat_screenshot"
    - 朋友圈截图："moments_screenshot"
    - 其他社媒截图："other_social_media_screenshot"

### 形式与数量
* **数量限制**：严格控制在 **1-4 个**问题以内。如果缺口太大，优先问最影响下一步生死的关键信息。
* **语态风格**：
    * **角色感**：保持"小话"的口吻（机智、干练、像个老练的军师）
    * **UI 适配性**：文案必须**极度简练**。不要大段寒暄，直接切入重点。
    * *Bad*: "亲爱的用户，为了帮您更好地规划约会，请问您打算什么时候去呢？"
    * *Good*: "打算约哪天？选个你状态最好的时候。"

### 题型优先级 (Hierarchy)
1. **截图优先**：凡是涉及"对方态度"、"回复内容"、"社媒动态"的，**强制使用 `_screenshot` 类题目**。
2. **选项优先**：凡是涉及"时间"、"地点"、"预算"的，**优先提供 `_choice` 类题目**。
3. **保底策略**：只有无法穷举的信息，才使用 `free_input_question`。

---

## 输出格式
请以 JSON 格式输出：
```json
{{
  "questions": [
    {{
      "id": "q1",
      "question": "问题内容（简练、直接，只写问题，不要包含选项）",
      "type": "single_choice|multiple_choice|free_input_question|private_chat_screenshot|group_chat_screenshot|moments_screenshot|other_social_media_screenshot",
      "info_type": 1,
      "options": ["选项1", "选项2", "选项3"],
      "is_required": true,
      "purpose": "问这个问题的目的"
    }}
  ],
  "intro": "引导语（简短、有角色感）",
  "reasoning": "为什么问这些问题（内部分析）"
}}
```

### 字段说明
- **question** (string): 提问的具体文案。只写问题，不要包含选项内容。
- **type** (string): 题目类型，必须严格匹配上述 7 个枚举值之一。
- **info_type** (integer): 信息归属类型，枚举如下：
    - 1: 用户信息
    - 2: Crush信息
    - 3: 双方相处信息
    - 4: 行动专属动态信息
- **options** (Array<string>): 仅 `single_choice` / `multiple_choice` 需要，最多 4 个。
- **is_required** (boolean): 是否必填。
"""
    


# 创建全局实例
_inquiry_skill_instance = None


def get_inquiry_skill() -> InquirySkill:
    """获取提问 Skill 实例（单例模式）"""
    global _inquiry_skill_instance
    if _inquiry_skill_instance is None:
        _inquiry_skill_instance = InquirySkill()
    return _inquiry_skill_instance
