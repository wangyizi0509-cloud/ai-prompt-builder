"""
解答情感疑惑工具 (Consult Answer Tool) - 状态驱动的两阶段版本

渐进式披露设计：
- consult_mode=False 时：工具只能设置为 enable（进入解答模式）
- consult_mode=True 时：工具变为 complete 版本，模型输出 content + tool_call(complete)
"""

import json
from typing import Literal

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool


# =============================================================================
# 解答策略常量（从 SKILL.md 提取核心内容）
# =============================================================================

CONSULT_MODE_STRATEGY = """## 解答情感疑惑策略

### 核心定位
* **深情死党**：当用户问"什么是XX"时，先"站位"提供情绪支撑，再提供降维打击式的认知
* **底层逻辑拆解师**：拒绝教科书式定义，用"人性、博弈、需求"解构对方行为

### 话术策略：三维流式回复
根据上下文灵活组合以下元素：

* **元素 A：情绪接纳** - 先感知用户情绪，焦虑先宽慰，愤怒先吐槽
  * 话术示例："啧，这话听着就憋屈"、"哎，我就知道他得来这一出"
  
* **元素 B：认知降维** - 用大白话拆解术语
  * 禁止说"XX是指"，改用"其实这事儿本质上就是..."、"说白了，这哥们儿就是..."
  
* **元素 C：战略留白/钩子** - 只有需要更多信息才反问，情况明朗则直接定性

### 交互红线
1. **拒绝强制模式**：严禁每段都以反问结尾
2. **句式随机化**：用语气助词（嘛、呢、哈、啊、喔），模拟真人打字
3. **禁止列表与标题**：严禁 1.2.3. 或【本质】【建议】等结构化符号
4. **字数动态调节**：简单吐槽 10-40 字，深度解惑 60-120 字
5. **静默手柄**：用户只是好奇时，禁止主动要求上传截图

### 任务触发逻辑
* **场景 1：用户纯好奇** → 执行 A+B，输出即止
* **场景 2：用户在受难** → 执行 A+B+C，C 是共情式确认
* **场景 3：用户展现求助信号** → 引导 Call Status/Plan

**立即行动**：根据上下文判断用户场景，按策略输出回复。回复完成后，调用 consult_answer(action="complete") 关闭解答模式。"""

CONSULT_MODE_SIMPLE = "已开启解答模式，解答完成。"


# =============================================================================
# 版本1：Enable-Only（consult_mode=False 时使用）
# =============================================================================

class ConsultEnableInput(BaseModel):
    """进入解答模式的输入 schema"""
    action: Literal["enable"] = Field(
        description="设置为 'enable' 以进入解答模式"
    )


def _consult_enable(action: str) -> str:
    """进入解答模式的实现"""
    return json.dumps({"action": "enable_consult_mode"}, ensure_ascii=False)


# 创建 enable 版本的工具（名字为 "consult_answer"）
consult_enable = StructuredTool.from_function(
    func=_consult_enable,
    name="consult_answer",
    description="进入解答模式。当用户提问情感相关问题（如'什么是推拉'、'他这是什么意思'），需要分析解答时，调用此工具。",
    args_schema=ConsultEnableInput,
)


# =============================================================================
# 版本2：Complete-Only（consult_mode=True 时使用）
# =============================================================================

class ConsultCompleteInput(BaseModel):
    """完成解答的输入 schema"""
    action: Literal["complete"] = Field(
        description="设置为 'complete' 以完成解答并关闭解答模式"
    )


def _consult_complete(action: str) -> str:
    """完成解答的实现"""
    return json.dumps({"action": "complete_consult_mode"}, ensure_ascii=False)


# 创建 complete 版本的工具（名字为 "consult_answer"）
consult_complete = StructuredTool.from_function(
    func=_consult_complete,
    name="consult_answer",
    description="完成解答并关闭解答模式。在你输出回复内容后，必须调用此工具来关闭解答模式。",
    args_schema=ConsultCompleteInput,
)


# =============================================================================
# 工具工厂函数
# =============================================================================

def get_consult_tool(consult_mode: bool) -> StructuredTool:
    """
    根据 consult_mode 状态返回对应版本的 consult_answer 工具
    
    Args:
        consult_mode: 解答模式状态
            - False: 返回 enable-only 版本（只能进入解答模式）
            - True: 返回 complete-only 版本（只能完成解答）
    
    Returns:
        StructuredTool: 对应版本的 consult_answer 工具（名字都是 "consult_answer"）
    """
    if consult_mode:
        return consult_complete
    else:
        return consult_enable
