"""
提问工具 (Ask Tool) - 状态驱动的两阶段版本

渐进式披露设计：
- ask_mode=False 时：工具只能设置为 enable（进入提问模式）
- ask_mode=True 时：工具变为完整的提问 schema，模型可以生成 inquiry_card
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field
from langchain_core.tools import tool, StructuredTool


# =============================================================================
# 提问策略常量（从 SKILL.md 提取核心内容）
# =============================================================================

ASK_MODE_STRATEGY = """## 提问策略

### 高效提问法则
1. **最小化输入成本**：能让用户点选的，绝不让用户打字
2. **证据优先**：涉及对方态度、潜台词、动态分析时，优先索要**截图**而非口述
3. **逻辑减法**：在生成问题前，必须扫描上下文，**严禁**重复询问已知信息

### 题型选择
| 意图场景 | 推荐题型 (`type`) |
| :--- | :--- |
| 定时间/地点/预算/二选一 | `single_choice` / `multiple_choice` |
| 分析聊天记录/朋友圈 | `private_chat_screenshot` / `moments_screenshot` / `group_chat_screenshot` |
| 复杂情感/开放式描述 | `free_input_question`（保底手段）|
| 其他社媒分析 | `other_social_media_screenshot` |

### 输出格式
问题数量：1-3 个，保持轻量。每个问题必须包含：
- `id`: 唯一标识
- `question`: 问题文案（简练、直接）
- `type`: 题型
- `options`: 选项（仅 choice 类必填，文字请精简）
- `is_required`: 是否必填
- `purpose`: 该问题的意图

**立即行动**：根据你判断的信息缺口，生成 1-3 个问题。"""

ASK_MODE_SIMPLE = "已进入提问模式。"


# =============================================================================
# 版本1：Enable-Only（ask_mode=False 时使用）
# =============================================================================

class AskEnableInput(BaseModel):
    """进入提问模式的输入 schema"""
    action: Literal["enable"] = Field(
        description="设置为 'enable' 以进入提问模式"
    )


def _ask_enable(action: str) -> str:
    """进入提问模式的实现"""
    return json.dumps({"action": "enable_ask_mode"}, ensure_ascii=False)


# 创建 enable 版本的工具（名字为 "ask"）
ask_enable = StructuredTool.from_function(
    func=_ask_enable,
    name="ask",
    description="进入提问模式。当你判断需要向用户提问以收集关键信息时，调用此工具。",
    args_schema=AskEnableInput,
)


# =============================================================================
# 版本2：Full-Schema（ask_mode=True 时使用）
# =============================================================================

class AskQuestionsInput(BaseModel):
    """完整提问的输入 schema"""
    questions: list[dict[str, Any]] = Field(
        description="问题列表，每个元素包含 id/type/question/options/is_required/purpose 字段"
    )
    intro: str = Field(
        default="",
        description="引导语，简短的过渡文案，自然衔接上文"
    )
    reasoning: str = Field(
        default="",
        description="内部原因说明，确保每个问题都有明确的战术价值"
    )


def _ask_questions(
    questions: list[dict[str, Any]],
    intro: str = "",
    reasoning: str = "",
) -> str:
    """执行提问的实现"""
    return json.dumps(
        {
            "action": "ask_user",
            "inquiry_card": {
                "questions": questions,
                "intro": intro,
                "reasoning": reasoning,
            },
        },
        ensure_ascii=False,
    )


# 创建完整版本的工具（名字为 "ask"）
ask_questions = StructuredTool.from_function(
    func=_ask_questions,
    name="ask",
    description="向用户提问以收集关键信息。根据提问策略生成结构化问题卡片。",
    args_schema=AskQuestionsInput,
)


# =============================================================================
# 工具工厂函数
# =============================================================================

def get_ask_tool(ask_mode: bool) -> StructuredTool:
    """
    根据 ask_mode 状态返回对应版本的 ask 工具
    
    Args:
        ask_mode: 提问模式状态
            - False: 返回 enable-only 版本（只能进入提问模式）
            - True: 返回 full-schema 版本（可以生成完整的 inquiry_card）
    
    Returns:
        StructuredTool: 对应版本的 ask 工具（名字都是 "ask"）
    """
    if ask_mode:
        return ask_questions
    else:
        return ask_enable


