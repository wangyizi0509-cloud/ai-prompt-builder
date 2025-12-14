#!/usr/bin/env python3
"""
自动更新 prompt_builder.html 中的 PROMPTS 内容
"""
import re
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 定义各模块的源文件路径
PROMPT_SOURCES = {
    'emotional_compass': 'Strategy_Library/01_Modules/Status_Analysis/Emotional_Compass/prompts.md',
    'action_guide': 'Strategy_Library/01_Modules/Action_Guide/Action_Guide_Gen/prompts.md',
    'chat_analysis': 'Strategy_Library/01_Modules/Chat_Analysis/prompts.md',
    'seek_answer': 'Strategy_Library/01_Modules/Consultation/seek_answer/prompt.md',
    'seek_support': 'Strategy_Library/01_Modules/Consultation/seek_support/prompt.md',
    'pre_question': 'Strategy_Library/01_Modules/Action_Guide/Pre_Question_Gen/prompts.md',
}

def extract_code_block(content: str) -> str:
    """提取 markdown 中第一个 ``` 代码块的内容"""
    # 匹配 ```xxx ... ``` 代码块
    match = re.search(r'```[^\n]*\n(.*?)```', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""

def extract_seek_prompt(content: str) -> str:
    """提取咨询类 prompt（System + User Template）"""
    blocks = re.findall(r'```[^\n]*\n(.*?)```', content, re.DOTALL)
    if len(blocks) >= 2:
        # System Prompt + User Template
        return blocks[0].strip() + "\n\n" + blocks[1].strip()
    elif len(blocks) == 1:
        return blocks[0].strip()
    return ""

def escape_for_js_template(text: str) -> str:
    """转义 JavaScript 模板字符串中的特殊字符"""
    # 转义反引号
    text = text.replace('`', '\\`')
    # 转义 ${} 模板插值语法
    text = text.replace('${', '\\${')
    return text

def read_prompt(module_name: str) -> str:
    """读取指定模块的 prompt 内容"""
    file_path = os.path.join(BASE_DIR, PROMPT_SOURCES[module_name])
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 咨询类模块特殊处理
    if module_name in ['seek_answer', 'seek_support']:
        return extract_seek_prompt(content)
    else:
        return extract_code_block(content)

def update_html():
    """更新 prompt_builder.html"""
    html_path = os.path.join(BASE_DIR, 'prompt_builder.html')
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 读取所有 prompt
    prompts = {}
    for module_name in PROMPT_SOURCES:
        raw_prompt = read_prompt(module_name)
        prompts[module_name] = escape_for_js_template(raw_prompt)
        print(f"✅ 读取 {module_name}: {len(raw_prompt)} 字符")
    
    # 构建新的 PROMPTS 对象
    prompts_js = """const PROMPTS = {
            emotional_compass: `""" + prompts['emotional_compass'] + """`,

            action_guide: `""" + prompts['action_guide'] + """`,

            chat_analysis: `""" + prompts['chat_analysis'] + """`,

            seek_answer: `""" + prompts['seek_answer'] + """`,

            seek_support: `""" + prompts['seek_support'] + """`,

            pre_question: `""" + prompts['pre_question'] + """`
        };"""
    
    # 替换 HTML 中的 PROMPTS 对象
    # 使用正则匹配 const PROMPTS = { ... };
    pattern = r'const PROMPTS = \{[\s\S]*?\n        \};'
    
    if re.search(pattern, html_content):
        new_html = re.sub(pattern, prompts_js, html_content)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(new_html)
        
        print(f"\n🎉 成功更新 prompt_builder.html!")
        print(f"📊 共更新 {len(prompts)} 个模块的 prompt")
    else:
        print("❌ 未找到 PROMPTS 对象，请检查 HTML 文件结构")

if __name__ == '__main__':
    update_html()
