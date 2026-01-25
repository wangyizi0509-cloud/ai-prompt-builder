# Skills 系统设计文档

> **最后更新**：2026-01-20  
> **设计理念**：基于 Anthropic Agent Skills 的渐进式披露（Progressive Disclosure）架构

---

## 一、设计理念

### 1.1 核心问题

传统做法是把所有 Skill 的完整指令都塞进 System Prompt，这会导致：
- **Token 浪费**：大部分 Skill 在单次对话中用不到
- **扩展困难**：新增 Skill 需要修改多处代码
- **上下文污染**：模型被无关指令干扰

### 1.2 解决方案：渐进式披露

采用 Anthropic 的 **Progressive Disclosure** 架构：

```
┌─────────────────────────────────────────────────────────────┐
│  Level 1: Metadata（元数据）                                 │
│  - 内容：name + description                                  │
│  - 加载时机：始终加载到 System Prompt                         │
│  - 作用：帮助模型判断"要不要用这个 Skill"                     │
└─────────────────────────────────────────────────────────────┘
                              ↓ 模型判断需要时
┌─────────────────────────────────────────────────────────────┐
│  Level 2: Instructions（完整指令）                           │
│  - 内容：SKILL.md 正文                                       │
│  - 加载时机：模型调用 load_skill(skill_id)                  │
│  - 作用：提供具体的执行方法和输出格式                         │
└─────────────────────────────────────────────────────────────┘
                              ↓ 执行时按需
┌─────────────────────────────────────────────────────────────┐
│  Level 3: Resources（额外资源）                              │
│  - 内容：scripts/、resources/ 目录下的文件                   │
│  - 加载时机：Skill 执行过程中按需读取                        │
│  - 作用：提供模板、脚本、参考资料等                          │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 两个关键设计决策

**1）单一工具接口**

不为每个 Skill 创建单独的工具函数，统一使用：
```python
load_skill(skill_id: str) -> str
```

好处：
- 新增 Skill 无需修改代码
- 减少 bind_tools 的维护成本

**2）执行指令由 Skill 自己携带**

主 Prompt 只说明"如何调用"，不说明"调用后怎么做"。

每个 SKILL.md 正文第一行必须是**执行触发提示**：
```markdown
# [执行触发] 你已加载「XXX」Skill，请立即按以下指令执行。
```

好处：
- 主 Prompt 保持简洁
- Skill 完全自包含，便于独立维护

---

## 二、目录结构

```
skills/
├── README.md           # 本文档
├── __init__.py         # 模块导出
├── base.py             # 基础数据结构（SkillMetadata）
├── registry.py         # Skill 注册中心（自动扫描发现）
├── tool.py             # 单一工具函数
└── definitions/        # Skill 定义目录
    ├── inquiry/
    │   └── SKILL.md
    ├── consult_answer/
    │   └── SKILL.md
    └── emotion_support/
        └── SKILL.md
```

---

## 三、如何新增 Skill

**只需 1 步**：在 `definitions/` 下创建文件夹和 SKILL.md

### 3.1 创建目录

```bash
mkdir -p skills/definitions/my_new_skill
```

### 3.2 编写 SKILL.md

```markdown
---
name: 我的新技能
description: 当用户需要 XXX 时使用此 Skill。简要说明触发条件。
---

# [执行触发] 你已加载「我的新技能」Skill，请立即按以下指令执行。

## 1. 核心原则
...

## 2. 输出格式
...
```

### 3.3 完成

系统启动时会自动扫描发现新 Skill，无需修改任何代码。

---

## 四、SKILL.md 格式规范

### 4.1 YAML Frontmatter（必需）

```yaml
---
name: 技能名称（中文，用于展示）
description: 触发条件描述（越具体越好，帮助模型判断何时使用）
---
```

| 字段 | 要求 | 说明 |
|-----|------|-----|
| name | 必填，≤64 字符 | 展示给模型的名称 |
| description | 必填，建议 50-200 字符 | 明确说明"什么情况下使用" |

### 4.2 正文结构

```markdown
# [执行触发] 你已加载「XXX」Skill，请立即按以下指令执行。

## 1. 核心原则
（这个 Skill 的指导思想）

## 2. 执行步骤 / 输出格式
（具体怎么做，输出什么格式）

## 3. 注意事项
（边界情况、禁止事项等）
```

**第一行必须是执行触发提示**，告诉模型：
- 现在是执行阶段
- 不要再调用工具
- 按下面的指令生成输出

---

## 五、调用方式

### 5.1 Agent Prompt 中的说明

各 Agent 的 Prompt 模板中会自动注入：

```markdown
## 可用 Skills

- **提问引导** (`inquiry`)：当信息不足时使用...
- **解答情感疑惑** (`consult_answer`)：当用户提问时使用...
- **情感陪伴** (`emotion_support`)：当用户需要情绪支持时使用...

### 调用方式

需要使用 Skill 时，调用 `load_skill(skill_id)` 工具。
```

### 5.2 调用流程

```
模型判断需要 Skill
       ↓
调用 load_skill("inquiry")
       ↓
工具返回 SKILL.md 完整内容
       ↓
模型看到"[执行触发]"提示
       ↓
按 Skill 指令生成输出
```

---

## 六、API 参考

### 6.1 registry.py

```python
from skills.registry import get_skill_registry

registry = get_skill_registry()

# 获取所有 Skill 元数据
metadata_list = registry.get_all_metadata()

# 获取指定 Skill 的完整指令
instructions = registry.get_skill_instructions("inquiry")

# 生成元数据 Prompt（用于注入 System Prompt）
prompt = registry.generate_metadata_prompt()

# 获取所有可用的 Skill ID
skill_ids = registry.get_skill_ids()
```

### 6.2 tool.py

```python
from skills import create_all_skills_loader

# 作为 LangChain Tool 使用
tool = create_all_skills_loader()
result = tool.invoke({"skill_id": "inquiry"})
```

---

## 七、现有 Skill 列表

| Skill ID | 名称 | 用途 |
|----------|------|------|
| `inquiry` | 提问引导 | 生成结构化问题卡片（inquiry_card） |
| `consult_answer` | 解答情感疑惑 | 回答用户的情感问题 |
| `emotion_support` | 情感陪伴 | 提供情绪支持和共情 |

---

## 八、设计参考

- [Anthropic: Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Claude Docs: Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
