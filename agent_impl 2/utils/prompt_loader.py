"""
Prompt 加载工具
从 prompts/ 目录加载 Markdown 格式的 Prompt 文件
支持 YAML frontmatter（符合 Anthropic Agent Skills 规范）
"""

import os
import re
from pathlib import Path
from typing import Optional, Dict, Tuple

# Prompt 目录路径
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def get_prompt_path(prompt_name: str) -> Path:
    """
    获取 Prompt 文件路径
    
    Args:
        prompt_name: Prompt 名称（不含 .md 后缀）
    
    Returns:
        Prompt 文件的完整路径
    """
    return PROMPTS_DIR / f"{prompt_name}.md"


def parse_frontmatter(content: str) -> Tuple[Optional[Dict[str, str]], str]:
    """
    解析 Markdown 文件的 YAML frontmatter
    
    符合 Anthropic Agent Skills 规范：
    - frontmatter 位于文件开头，用 --- 包围
    - 包含 name 和 description 字段
    
    Args:
        content: 文件内容
    
    Returns:
        (frontmatter_dict, content_without_frontmatter) 元组
        - frontmatter_dict: 如果存在 frontmatter，返回字典；否则返回 None
        - content_without_frontmatter: 去除 frontmatter 后的内容
    """
    # 匹配 YAML frontmatter（--- 开头和结尾）
    frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(frontmatter_pattern, content, re.DOTALL)
    
    if not match:
        # 没有 frontmatter，返回原内容
        return None, content
    
    frontmatter_text = match.group(1)
    content_without_frontmatter = content[match.end():]
    
    # 解析 YAML（简单解析，只支持 name 和 description）
    frontmatter_dict = {}
    for line in frontmatter_text.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # 匹配 key: value 格式
        colon_pos = line.find(':')
        if colon_pos > 0:
            key = line[:colon_pos].strip()
            value = line[colon_pos + 1:].strip()
            # 去除引号（如果有）
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            frontmatter_dict[key] = value
    
    return frontmatter_dict if frontmatter_dict else None, content_without_frontmatter


def load_prompt_metadata(prompt_name: str) -> Dict[str, str]:
    """
    只加载 Prompt 文件的 YAML frontmatter 元数据（第一阶段：Metadata Level）
    
    符合 Anthropic Agent Skills 渐进式披露机制：
    - 第一阶段只加载元数据（name + description）
    - 用于帮助 Agent 判断何时使用该 Skill
    
    Args:
        prompt_name: Prompt 名称（不含 .md 后缀）
    
    Returns:
        包含 name 和 description 的字典
    
    Raises:
        FileNotFoundError: 如果 Prompt 文件不存在
        ValueError: 如果 frontmatter 缺少必需的字段
    """
    prompt_path = get_prompt_path(prompt_name)
    
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {prompt_path}")
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    frontmatter_dict, _ = parse_frontmatter(content)
    
    if not frontmatter_dict:
        # 没有 frontmatter，返回空字典（向后兼容）
        return {}
    
    # 验证必需字段
    if "name" not in frontmatter_dict or "description" not in frontmatter_dict:
        raise ValueError(f"Prompt {prompt_name} 的 frontmatter 缺少必需的字段 (name 或 description)")
    
    return {
        "name": frontmatter_dict["name"],
        "description": frontmatter_dict["description"]
    }


def load_prompt_content(prompt_name: str, variables: Optional[dict] = None) -> str:
    """
    加载 Prompt 文件内容，去除 frontmatter（第二阶段：Instruction Level）
    
    符合 Anthropic Agent Skills 渐进式披露机制：
    - 第二阶段加载完整指令（去除 frontmatter）
    - 用于实际执行 Skill
    
    Args:
        prompt_name: Prompt 名称（不含 .md 后缀）
        variables: 可选的变量字典，用于替换 Prompt 中的 {variable} 占位符
    
    Returns:
        Prompt 文本内容（已去除 frontmatter）
    
    Raises:
        FileNotFoundError: 如果 Prompt 文件不存在
    """
    prompt_path = get_prompt_path(prompt_name)
    
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {prompt_path}")
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 去除 frontmatter，只返回内容部分
    _, content_without_frontmatter = parse_frontmatter(content)
    
    # 如果提供了变量，进行替换
    if variables:
        for key, value in variables.items():
            content_without_frontmatter = content_without_frontmatter.replace(f"{{{key}}}", str(value))
    
    return content_without_frontmatter


def load_prompt(prompt_name: str, variables: Optional[dict] = None) -> str:
    """
    加载 Prompt 文件内容（向后兼容方法）
    
    注意：为了保持向后兼容，此方法默认去除 frontmatter。
    如果需要完整内容（包含 frontmatter），请直接读取文件。
    
    Args:
        prompt_name: Prompt 名称（不含 .md 后缀）
        variables: 可选的变量字典，用于替换 Prompt 中的 {variable} 占位符
    
    Returns:
        Prompt 文本内容（已去除 frontmatter）
    
    Raises:
        FileNotFoundError: 如果 Prompt 文件不存在
    """
    return load_prompt_content(prompt_name, variables)


def list_prompts() -> list[str]:
    """
    列出所有可用的 Prompt
    
    Returns:
        Prompt 名称列表
    """
    if not PROMPTS_DIR.exists():
        return []
    
    return [f.stem for f in PROMPTS_DIR.glob("*.md")]

