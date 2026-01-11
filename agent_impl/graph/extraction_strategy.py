"""
提取策略层
提供统一的提取流水线封装，便于在上下文组装时显式使用「提取策略」

设计思路：
- 将具体的 Layer 提取逻辑以回调方式注入，避免循环依赖
- Pipeline 负责组装流程、顺序和空值处理
"""

from typing import Callable, Optional, Literal


class ExtractionPipeline:
    """
    提取流水线封装

    注入式设计：具体提取函数由调用方传入，方便后续切换/扩展
    """

    def __init__(
        self,
        *,
        extract_layer1: Callable,
        extract_layer2: Callable,
        extract_layer3: Callable,
        build_layer0: Optional[Callable] = None,
        build_context_dict: Optional[Callable] = None,
    ):
        self.extract_layer1 = extract_layer1
        self.extract_layer2 = extract_layer2
        self.extract_layer3 = extract_layer3
        self.build_layer0 = build_layer0
        self.build_context_dict_fn = build_context_dict

    def build_text(
        self,
        state: dict,
        target_agent: Literal["main_agent", "status_agent", "plan_agent", "guide_agent"] = "main_agent",
        include_layer0: bool = False,
    ) -> str:
        """构建多层上下文文本"""
        sections = []

        if include_layer0 and self.build_layer0:
            layer0 = self.build_layer0()
            if layer0:
                sections.append(layer0)

        layer1_output = self.extract_layer1(state)
        if layer1_output:
            sections.append(layer1_output)

        layer2_output = self.extract_layer2(state)
        if layer2_output:
            sections.append(layer2_output)

        layer3_output = self.extract_layer3(state)
        if layer3_output:
            sections.append(layer3_output)

        return "\n\n---\n\n".join(sections)

    def build_dict(
        self,
        state: dict,
        target_agent: Literal["main_agent", "status_agent", "plan_agent", "guide_agent"] = "main_agent",
    ) -> dict:
        """构建上下文字典（用于模板化填充）"""
        if not self.build_context_dict_fn:
            return {}
        return self.build_context_dict_fn(state, target_agent)

