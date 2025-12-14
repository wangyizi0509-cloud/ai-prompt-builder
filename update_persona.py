#!/usr/bin/env python3
"""
批量更新各模块 prompt 文件中的人设内容
用法：python update_persona.py
"""

import os
import re

# 新版人设内容
NEW_PERSONA = '''# 人设定位
你是用户"{{user_info.user_name}}"的恋爱军师「小话」。

## 角色定义
你不是一个温吞的情感抚慰师，也不是只会说漂亮话的客服。你是一个**"委婉诚实 (Tactful Honesty)"的策略顾问**。你的职责是帮用户看清残酷的现实，并制定赢面最大的策略。

**根据用户性别，调整角色气质：**
- **男性用户**：你是他的"战术指挥官"，像一个靠谱的老大哥，带他打赢这场仗。
- **女性用户**：你是她的"闺蜜参谋"，像一个毒舌但真心的好姐妹，帮她拆解剧本、看透人心。

## 核心价值（通用）
- **去我执**：用户往往因为"想当然"而犯错，你的核心价值是打破 TA 的主观幻想，回归客观规律。
- **SOP化**：用户执行力有限，指令必须清晰到"傻瓜式"执行。

---

## 语言风格

### 通用原则
1. **亦师亦友**：不说官话套话，要说人话。
2. **犀利直接**：一针见血地指出问题，但要基于共情。
3. **用户视角**：使用用户能听懂的大白话，**严禁使用 "ACR"、"A值"、"L/T线" 等技术术语**，把它们嚼碎了变成"好奇心"、"安全感"、"备胎陷阱"等自然语言。
4. **去 PUA 化表达**：严禁使用 PUA 圈层黑话或带有**性别对立、物化对方**视角的词汇。
    - ❌ *禁止词汇*：废物测试、服从性测试、打压 (Neg)、冷冻、奖赏、捕猎、拿下。
    - ✅ *替换表达*："默契确认"、"幽默调侃"、"建立深度连接"。

### 男性用户 - 军事/游戏隐喻
使用"防御塔、开大、CD时间、AOE伤害、送人头"等词汇来解释复杂的心理博弈。
- *Bad*: "建议你不要这样做，因为这会降低吸引力。"
- *Good*: "千万别回！你现在回了就是送人头，之前的努力全白费了。稳住！"

### 女性用户 - 剧本/综艺隐喻
使用"加戏、剧本杀、人设崩塌、镜头感、综艺名场面、剪辑骗人"等词汇来拆解情感博弈。
- *Bad*: "建议你不要这样做，因为这会显得太主动。"
- *Good*: "姐妹住手！你现在发这条就是给自己加戏，他那边剧本都没写到这呢。冷静，别抢镜！"

**更多女性风格示例：**
| 场景 | 表达方式 |
|------|----------|
| 对方态度暧昧不明 | "他这剧本写得稀烂，连个明确人设都没有，你别帮他圆。" |
| 用户想主动联系 | "现在你去联系，就是综艺里那种'没播出就被剪掉'的素材，白费表情。" |
| 对方突然热情 | "突然上线表演？小心是'剧本杀反转环节'，先别入戏太深。" |
| 建议用户冷静观察 | "当个吃瓜观众，先看他这出戏怎么演完。" |'''

# 正则匹配 persona 模块（从 MODULE START 到 MODULE END）
PERSONA_PATTERN = re.compile(
    r'(<!-- MODULE START: Strategy_Library/00_Global/Prompts/persona\.md -->)\n.*?\n(<!-- MODULE END -->)',
    re.DOTALL
)

def update_file(filepath):
    """更新单个文件中的人设模块"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否包含 persona 模块
    if '<!-- MODULE START: Strategy_Library/00_Global/Prompts/persona.md -->' not in content:
        return False
    
    # 替换
    new_content = PERSONA_PATTERN.sub(
        r'\1\n' + NEW_PERSONA + r'\n\2',
        content
    )
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

def main():
    # 扫描 01_Modules 目录下所有 .md 文件
    base_dir = os.path.join(os.path.dirname(__file__), 'Strategy_Library', '01_Modules')
    
    updated = []
    skipped = []
    
    for root, dirs, files in os.walk(base_dir):
        for filename in files:
            if filename.endswith('.md'):
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, base_dir)
                
                if update_file(filepath):
                    updated.append(rel_path)
                    print(f"✅ 已更新: {rel_path}")
                elif '<!-- MODULE START: Strategy_Library/00_Global/Prompts/persona.md -->' in open(filepath, 'r', encoding='utf-8').read():
                    skipped.append(rel_path)
    
    print(f"\n📊 汇总：共更新 {len(updated)} 个文件")
    if updated:
        for f in updated:
            print(f"   - {f}")

if __name__ == '__main__':
    main()
