"""
情感陪伴工具 (Emotion Support Tool) - 状态驱动的两阶段版本

渐进式披露设计：
- emotion_mode=False 时：工具只能设置为 enable（进入陪伴模式）
- emotion_mode=True 时：工具变为 complete 版本，模型输出 content + tool_call(complete)
"""

import json
from typing import Literal

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool


# =============================================================================
# 情感陪伴策略常量（从 SKILL.md 提取核心内容）
# =============================================================================

EMOTION_MODE_STRATEGY = """## 情感陪伴策略

### 核心定位
* **角色属性**：用户的"情绪合伙人"与"心理嘴替"
* **核心任务**：接住用户从"日常碎碎念"到"深度崩溃"的任何情绪
* **最高准则**：**先站队，再开口。** 像真人一样聊天，拒绝机械式安抚

### 核心执行逻辑

**Step 1: 同步共情** - 拒绝废话
* 禁止定义用户情绪（严禁说"我能感觉到你很难受"）
* 使用感叹词（害、绝了、草、太真实了）直接切入
* 第一句话必须体现"我跟你是一伙的"

**Step 2: 交互路径判定**

* **【路径 A：纯回声模式】** 用户密集吐槽或表达结论（"懒得理他"）
  → 纯表态 + 情绪盖章，不提问不引导
  
* **【路径 B：互动钩子模式】** 用户输入极短（"好烦"）或表达模糊
  → 态度先行 + 极小切口提问
  
* **【路径 C：战术拦截模式】** 出现冲动决策（拉黑、对峙）或深度自我攻击
  → 强行介入 + 任务转移（"去找张他最丑的照片"）

### 交互红线
1. **去 AI 化**：禁止"首先/其次"、"我建议"、"我理解"等书面语
2. **反问频率**：严禁每轮都以问号结尾，连续三轮提问不超过 1 次
3. **禁止生理关怀**：严禁说"多喝热水/早点睡/去运动"
4. **字数高压线**：严格控制在 **20-60 字**，像发微信一样短促有力
5. **拒绝理中客**：哪怕用户有错，在倾诉阶段也要盲目护短

**立即行动**：根据上下文判断用户路径（A/B/C），按策略输出回复。回复完成后，调用 emotion_support(action="complete") 关闭陪伴模式。"""

EMOTION_MODE_SIMPLE = "已开启陪伴模式，陪伴完成。"


# =============================================================================
# 版本1：Enable-Only（emotion_mode=False 时使用）
# =============================================================================

class EmotionEnableInput(BaseModel):
    """进入陪伴模式的输入 schema"""
    action: Literal["enable"] = Field(
        description="设置为 'enable' 以进入陪伴模式"
    )


def _emotion_enable(action: str) -> str:
    """进入陪伴模式的实现"""
    return json.dumps({"action": "enable_emotion_mode"}, ensure_ascii=False)


# 创建 enable 版本的工具（名字为 "emotion_support"）
emotion_enable = StructuredTool.from_function(
    func=_emotion_enable,
    name="emotion_support",
    description="进入陪伴模式。当用户表达情绪、需要倾诉或安慰时（如'好烦'、'累了'、'算了'），调用此工具。",
    args_schema=EmotionEnableInput,
)


# =============================================================================
# 版本2：Complete-Only（emotion_mode=True 时使用）
# =============================================================================

class EmotionCompleteInput(BaseModel):
    """完成陪伴的输入 schema"""
    action: Literal["complete"] = Field(
        description="设置为 'complete' 以完成陪伴并关闭陪伴模式"
    )


def _emotion_complete(action: str) -> str:
    """完成陪伴的实现"""
    return json.dumps({"action": "complete_emotion_mode"}, ensure_ascii=False)


# 创建 complete 版本的工具（名字为 "emotion_support"）
emotion_complete = StructuredTool.from_function(
    func=_emotion_complete,
    name="emotion_support",
    description="完成陪伴并关闭陪伴模式。在你输出回复内容后，必须调用此工具来关闭陪伴模式。",
    args_schema=EmotionCompleteInput,
)


# =============================================================================
# 工具工厂函数
# =============================================================================

def get_emotion_tool(emotion_mode: bool) -> StructuredTool:
    """
    根据 emotion_mode 状态返回对应版本的 emotion_support 工具
    
    Args:
        emotion_mode: 陪伴模式状态
            - False: 返回 enable-only 版本（只能进入陪伴模式）
            - True: 返回 complete-only 版本（只能完成陪伴）
    
    Returns:
        StructuredTool: 对应版本的 emotion_support 工具（名字都是 "emotion_support"）
    """
    if emotion_mode:
        return emotion_complete
    else:
        return emotion_enable
