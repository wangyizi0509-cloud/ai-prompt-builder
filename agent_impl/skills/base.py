"""
Skill 基类
基于 Anthropic 的 Agent Skills 设计理念：渐进式披露（Progressive Disclosure）

三层架构：
1. Metadata Level：name + description，平时只加载这些到 prompt
2. Instruction Level：完整的 skill prompt，需要时才加载
3. Resource Level：额外资源（可选）

Skill 类型：
- PromptSkill：通过动态扩展主 Agent 的 prompt 来增强能力（如咨询 Skills、提问 Skill）
- 所有 Skills 都采用渐进式披露：第一阶段只加载元数据，第二阶段根据判断结果动态加载完整 prompt

符合 Anthropic 官方方法：
- 元数据存储在 markdown 文件的 YAML frontmatter 中
- 从文件读取而不是硬编码在 Python 代码中
"""

from abc import ABC, abstractmethod
from typing import Optional, Any
from dataclasses import dataclass

from utils.prompt_loader import load_prompt_metadata


@dataclass
class SkillMetadata:
    """Skill 元数据（用于主 Agent 的简短提示）
    
    符合 Anthropic 官方规范：只包含 name 和 description
    """
    name: str
    description: str


class BaseSkill(ABC):
    """
    Skill 基类
    
    符合 Anthropic 官方方法：
    - 元数据从 markdown 文件的 YAML frontmatter 读取
    - 所有 Skill 需要设置 _prompt_name 属性（对应 prompts/ 目录下的文件名）
    
    所有 Skill 都需要实现：
    1. _prompt_name: 属性，指定对应的 prompt 文件名（不含 .md 后缀）
    2. get_full_prompt(): 返回完整的 skill prompt
    """
    
    # 子类必须设置此属性
    _prompt_name: str = None
    
    def get_metadata(self) -> SkillMetadata:
        """
        获取 Skill 元数据（从文件读取）
        
        符合 Anthropic 官方方法：从 markdown 文件的 YAML frontmatter 读取
        这些信息会被加载到主 Agent 的 system prompt 中，
        用于帮助主 Agent 判断何时使用这个 Skill
        
        Returns:
            SkillMetadata 对象，包含 name 和 description
        
        Raises:
            ValueError: 如果 _prompt_name 未设置或文件缺少必需的字段
        """
        if not self._prompt_name:
            raise ValueError(f"{self.__class__.__name__} 必须设置 _prompt_name 属性")
        
        try:
            metadata_dict = load_prompt_metadata(self._prompt_name)
            
            if not metadata_dict:
                # 向后兼容：如果文件没有 frontmatter，使用默认值
                return SkillMetadata(
                    name=self.__class__.__name__,
                    description="Skill 描述未找到"
                )
            
            return SkillMetadata(
                name=metadata_dict["name"],
                description=metadata_dict["description"]
            )
        except (FileNotFoundError, ValueError) as e:
            # 向后兼容：如果文件不存在或解析失败，使用默认值
            return SkillMetadata(
                name=self.__class__.__name__,
                description="Skill 描述未找到"
            )
    
    @abstractmethod
    def get_full_prompt(self, **kwargs) -> str:
        """
        获取完整的 Skill Prompt
        
        当主 Agent 决定使用这个 Skill 时，
        会调用此方法获取完整 prompt 并动态加载到上下文中
        
        Args:
            **kwargs: 上下文参数，如 user_message, user_profile 等
        """
        pass
    
    def get_metadata_prompt(self) -> str:
        """
        生成用于主 Agent prompt 的元数据描述
        
        符合 Anthropic 官方格式：只包含 name 和 description
        格式：简短的一行描述，用于渐进式披露
        """
        meta = self.get_metadata()
        return f"- **{meta.name}**：{meta.description}"


class PromptSkill(BaseSkill):
    """
    Prompt 增强型 Skill
    
    通过动态扩展主 Agent 的 prompt 来增强能力
    不需要独立的 LLM 调用，在主 Agent 的同一次调用中完成
    
    适用场景：回复生成类任务（如情感咨询、情感陪伴）
    """
    
    def apply_to_prompt(self, base_prompt: str, **kwargs) -> str:
        """
        将 Skill 的完整 prompt 应用到基础 prompt 上
        
        Args:
            base_prompt: 主 Agent 的基础 prompt
            **kwargs: 上下文参数
            
        Returns:
            增强后的 prompt
        """
        skill_prompt = self.get_full_prompt(**kwargs)
        
        # 在基础 prompt 后追加 skill prompt
        return f"""{base_prompt}

## 📚 当前激活的 Skill：{self.get_metadata().name}

{skill_prompt}
"""


class GeneratorSkill(BaseSkill):
    """
    生成器型 Skill
    
    需要独立调用 LLM 生成结构化输出
    适用场景：需要特定格式输出的任务（如问题卡片生成）
    """
    
    @abstractmethod
    def generate(self, **kwargs) -> Any:
        """
        执行 Skill，生成结构化输出
        
        这个方法会调用 LLM 并返回解析后的结果
        """
        pass
