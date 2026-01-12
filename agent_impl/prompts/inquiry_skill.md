---
name: 提问引导
description: 提供生成结构化引导性问题的规范与协议。指导 Agent 如何高效收集信息。
---

# Inquiry Skill Protocol (提问能力协议)

本模块定义了生成 `inquiry_card` 的标准协议。当 Agent 决定需要向用户提问时，请遵循本协议构建 JSON 数据。

## 1. 核心原则 (Core Principles)

本 Skill 不做决策，只提供**提问方法论**。请基于你（Agent）当前上下文中的**提问目标**和**已知信息**，利用本工具生成最高效的问题卡片。

### 高效提问法则
1.  **最小化输入成本**：能让用户点选的，绝不让用户打字。
2.  **证据优先**：涉及对方态度、潜台词、动态分析时，优先索要**截图**而非口述。
3.  **逻辑减法**：在生成问题前，必须扫描上下文，**严禁**重复询问已知信息。

---

## 2. 题型定义 (Question Types)

请根据你的提问意图，严格选择以下题型：

| 意图场景 | 推荐题型 (`type`) | 优势 |
| :--- | :--- | :--- |
| **定时间/地点/预算/二选一** | `single_choice` / `multiple_choice` | 降低认知负荷，快速锁定参数 |
| **分析聊天记录/朋友圈/回复** | `private_chat_screenshot` / `moments_screenshot` / `group_chat_screenshot` | 获取客观事实，避免主观偏差 |
| **复杂情感/开放式描述** | `free_input_question` | 捕捉细腻情绪（作为保底手段） |
| **其他社媒分析** | `other_social_media_screenshot` | 覆盖小红书/Instagram等场景 |

---

## 3. 输出协议 (Schema)

请在你的主输出 JSON 中的 `inquiry_card` 字段中，填充符合以下规范的对象。

### JSON 结构
```json
{
  "questions": [
    {
      "id": "unique_id_1",
      "question": "问题文案（简练、直接，不要包含选项内容）",
      "type": "single_choice",
      "options": ["选项A", "选项B", "选项C"],
      "is_required": true,
      "purpose": "该问题的意图（用于调试）"
    }
  ],
  "intro": "引导语（简短的过渡文案）",
  "reasoning": "为什么需要问这些问题（你的思考过程）"
}
```

### 字段详解
*   **questions** (Array): 问题列表，建议 **1-3 个**，保持轻量。
    *   **options** (Array<str>): 仅 `_choice` 类题型必填。**注意：前端卡片长度有限，选项文字请精简。**
*   **intro** (string): 展示给用户的引导话术。应自然衔接上文，说明提问目的。
*   **reasoning** (string): 你的内部逻辑自查。确保每个问题都有明确的战术价值。
