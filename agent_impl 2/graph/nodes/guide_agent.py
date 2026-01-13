"""
行动指南 Agent 节点 (Action Guide Agent)
负责生成具体的 SOP 任务包

采用 Tool-based 渐进式加载模式：
- 系统提示只包含 Skills 的元数据
- 模型通过 load_skill_instructions 工具按需加载完整指令

上下文架构更新 (v2.0)：
- 使用分层上下文架构（Layer 0-4）
- 通过 context_builder 统一组装上下文
- 支持多个未执行的行动指南（action_guides 列表）
"""

import json
from typing import Any

from graph.state import AgentState, ActionGuide
from graph.context_builder import build_context_dict
from graph.context_types import ActionGuideItem, ActionGuideContent, create_action_guide_item
from skills.inquiry import get_inquiry_skill
from skills import load_skill_instructions
from utils.prompt_loader import load_prompt
from config import get_llm


def guide_agent_node(state: AgentState) -> dict[str, Any]:
    """
    行动指南 Agent 节点
    
    职责：
    1. 基于行动规划生成具体 SOP
    2. 明确当前任务和步骤
    3. 提供话术要点
    4. 给出 Do's 和 Don'ts
    5. 如果信息不足，通过工具获取提问技能指令
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    # 绑定 Skill 加载工具
    llm = get_llm(temperature=0.6).bind_tools([load_skill_instructions])
    
    # === 恢复执行检查 ===
    is_resuming = (state.get("current_agent") == "guide_agent" and 
                   state.get("agent_resume_point") == "continue_guide")
    question_count = state.get("question_count", 0)
    max_questions = state.get("max_questions", 3)
    collected_info = state.get("collected_info", {})
    
    # 工具调用返回检查
    from_tool_call = state.get("_tool_caller") == "guide_agent"
    
    if is_resuming:
        print(f"[DEBUG] GuideAgent resuming from question {question_count}")
    elif from_tool_call:
        print(f"[DEBUG] GuideAgent: Continuing after tool call")
    
    # 加载 Prompt
    try:
        prompt_template = load_prompt("guide_agent")
    except FileNotFoundError:
        prompt_template = _get_default_prompt()
    
    # 获取主 Agent 刚说的话（用于保持对话连贯）
    last_response = state.get("last_response_for_continuity", "")
    
    # 构建上下文（使用新的分层上下文架构）
    context_dict = build_context_dict(state)
    
    # 获取 InquirySkill 元数据 + 工具使用说明
    inquiry_skill = get_inquiry_skill()
    inquiry_metadata = f"""
---

## 📚 可用 Skill（通过工具按需加载）

{inquiry_skill.get_metadata_prompt()}

### 如何使用

如果信息不足需要提问，请调用 `load_skill_instructions(skill_id="inquiry_skill")` 获取完整的提问指令。

---
"""
    
    # 填充 Prompt
    prompt = prompt_template.format(
        # 新版：使用分层上下文
        user_context=context_dict.get("user_context", "暂无用户信息"),
        status_report=context_dict.get("status_report", "暂无"),
        action_plan=context_dict.get("action_plan", "暂无"),
        conversation_history=context_dict.get("conversation_history", "无历史对话"),
        last_response=last_response if last_response else "无",
        # 向后兼容
        user_profile=context_dict.get("user_profile", "{}"),
        # Skills 元数据
        inquiry_skill_metadata=inquiry_metadata,
    )
    
    # === 调用 LLM（模型自主决定是否需要工具）===
    print(f"[DEBUG] GuideAgent: Invoking LLM with tool binding")
    response = llm.invoke(prompt)
    
    # 检查是否有工具调用
    if hasattr(response, "tool_calls") and response.tool_calls:
        # 模型决定调用工具，返回消息让 workflow 路由到 skill_tools
        print(f"[DEBUG] GuideAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
        return {
            "messages": [response],
            "current_agent": "guide_agent",  # 标记调用来源
            "debug_log": [{
                "node": "guide_agent",
                "step": "Tool Call Requested",
                "tool_calls": [tc["name"] for tc in response.tool_calls],
            }]
        }
    
    # 没有工具调用，解析响应
    parsed = _parse_response(response.content)
    
    result = {
        "next_action": "end_turn",
        "debug_log": [{
            "node": "guide_agent",
            "step": "Response Generated" + (" (resumed)" if is_resuming else ""),
            "prompt": prompt,
            "response": response.content,
            "parsed_result": parsed,
            "question_count": question_count,
        }],
    }
    
    # 检查是否需要提问
    need_questions = parsed.get("need_questions", False)
    inquiry_card = parsed.get("inquiry_card")
    
    if need_questions and inquiry_card and inquiry_card.get("questions") and question_count < max_questions:
        print(f"[DEBUG] GuideAgent: Generated {len(inquiry_card.get('questions', []))} questions")
        
        result["inquiry_card"] = inquiry_card
        result["pending_questions"] = [q.get("question", "") if isinstance(q, dict) else str(q) for q in inquiry_card.get("questions", [])]
        
        # === 设置恢复状态 ===
        result["current_agent"] = "guide_agent"
        result["agent_resume_point"] = "continue_guide"
        result["question_count"] = question_count + 1
        result["collected_info"] = collected_info
        
        # 信息不足时，不生成指南，等待用户回答
        result["action_guide"] = None
        response_content = parsed.get("response", "")
        # 如果 Agent 没有生成回复，使用 intro 作为引导语
        if not response_content.strip() and inquiry_card.get("intro"):
            response_content = inquiry_card.get("intro")
        elif not response_content.strip():
            response_content = "为了给你更具体的行动建议，我需要再了解一些细节～"
        # 累积到 pending_responses（不覆盖之前的消息）
        existing_responses = state.get("pending_responses", [])
        result["pending_responses"] = existing_responses + [{
            "from": "guide_agent", 
            "content": response_content,
            "phase": "after_guide"  # 行动指南阶段的提问
        }]
        result["messages"] = [{"role": "assistant", "content": response_content}]
        # 未完成，不设置完成信号
        result["completion_status"] = None
        result["result_summary"] = None
    else:
        # 不需要提问，生成指南
        result["action_guide"] = _build_action_guide(parsed)
        # === 清除恢复状态 ===
        result["current_agent"] = None
        result["agent_resume_point"] = None
        result["question_count"] = 0
        result["collected_info"] = {}
        # 显式清除 inquiry_card，避免残留上一轮的问题
        result["inquiry_card"] = None
        result["pending_questions"] = []
        
        # === 设置完成信号 ===
        result["completion_status"] = "COMPLETED"
        result["result_summary"] = f"行动指南完成：{parsed.get('guide_content', '')[:50]}..."
        
        # 子 Agent 完成时不发送对话消息，完整报告在看板（action_guide）中展示
        # 保留现有的 pending_responses，不覆盖
        existing_responses = state.get("pending_responses", [])
        result["pending_responses"] = existing_responses
        result["messages"] = []
    
    return result


def _format_history(messages: list) -> str:
    """格式化对话历史"""
    if not messages:
        return "无历史对话"
    
    recent = messages[-10:]
    formatted = []
    for msg in recent:
        role = "用户" if msg["role"] == "user" else "小话"
        formatted.append(f"{role}: {msg['content']}")
    
    return "\n".join(formatted)


def _parse_response(content: str) -> dict:
    """解析 LLM 输出，返回原始字典"""
    try:
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end > start:
                json_str = content[start:end]
            else:
                json_str = content
        
        return json.loads(json_str)
    
    except (json.JSONDecodeError, KeyError, IndexError):
        # 解析失败，返回默认值
        return {
            "need_questions": False,
            "guide_content": content.strip() if content else "暂时无法生成指南，请提供更多信息。",
        }


def _build_action_guide(data: dict) -> ActionGuide:
    """从解析的数据构建 ActionGuide"""
    return ActionGuide(
        current_task=data.get("current_task", ""),
        steps=data.get("steps", []),
        talking_points=data.get("talking_points", []),
        dos=data.get("dos", []),
        donts=data.get("donts", []),
        next_milestone=data.get("next_milestone", ""),
        guide_content=data.get("guide_content", ""),  # Markdown 格式的完整指南
    )


def _generate_response(action_guide: ActionGuide) -> str:
    """根据指南结果生成回复"""
    current_task = action_guide.get("current_task", "")
    steps = action_guide.get("steps", [])
    talking_points = action_guide.get("talking_points", [])
    dos = action_guide.get("dos", [])
    donts = action_guide.get("donts", [])
    next_milestone = action_guide.get("next_milestone", "")
    
    response_parts = [
        f"好的，这是你接下来的行动指南：\n",
        f"\n**当前任务**: {current_task}\n",
    ]
    
    if steps:
        response_parts.append("\n**具体步骤**:")
        for i, step in enumerate(steps[:5], 1):
            response_parts.append(f"\n{i}. {step}")
    
    if talking_points:
        response_parts.append("\n\n**话术要点**:")
        for point in talking_points[:3]:
            response_parts.append(f"\n• {point}")
    
    if dos:
        response_parts.append("\n\n✅ **该做的**:")
        for do in dos[:3]:
            response_parts.append(f"\n• {do}")
    
    if donts:
        response_parts.append("\n\n❌ **不该做的**:")
        for dont in donts[:3]:
            response_parts.append(f"\n• {dont}")
    
    if next_milestone:
        response_parts.append(f"\n\n**下一个里程碑**: {next_milestone}")
    
    response_parts.append("\n\n有任何问题随时问我，执行过程中遇到情况也可以来找我商量！")
    
    return "".join(response_parts)


def _get_default_prompt() -> str:
    """获取默认 Prompt - 迁移自 Strategy_Library/Action_Guide_Gen"""
    return """# 人设定位
你是用户的恋爱军师「小话」。

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

---

# 核心底层法则
**注意**：本系统不使用通用的恋爱心理学汤水，而是严格基于以下【实战派物理法则】进行诊断。

## 1. 核心度量衡：ACR 情感物理学
(这是你的**底层思考逻辑**，但在**输出给用户看的内容中**，必须将这些术语翻译成大白话，**禁止**直接出现 "A/C/R" 字母或 "ACR" 字样)
* **A (Attraction - 吸引力)**：硬价值与繁衍价值。
* **C (Comfort - 舒适感)**：安全感与信任。
* **R (Romance/Tension - 张力)**：暧昧博弈与不可得性。

## 2. 关系坐标系：L/T 模型判定矩阵

#### 🟢 L 线 (主线 - The Logic of Passing)
* **L1 初识期**: A(无) + C(无) + R(无)
* **L2 吸引期**: **A(中/高)** + C(低) + R(低)
* **L3 暧昧期**: A(高) + C(中/高) + **R(上升)**
* **L4 确立期**: A(高) + C(高) + R(高)

#### 🔴 T 线 (陷阱线 - The Logic of Stuck)
* **T1 备胎/供养者**: A(低/无) + **C(溢出)** + R(无)
* **T2 兄弟/死党**: A(中) + **C(极高)** + **R(负/无)**
* **T3 短择/炮友**: A(高) + **C(低/阻断)** + **R(高)**

## 3. 🚨 术语翻译协议
**严禁在最终输出中出现 "ACR"、"A值"、"C高"、"L/T线" 等技术术语！**
* **A (Attraction)** -> 翻译为：**"吸引力"、"好奇心"、"想了解你的欲望"、"异性魅力"**
* **C (Comfort)** -> 翻译为：**"信任感"、"相处氛围"、"安全感"、"像朋友一样"**
* **R (Romance)** -> 翻译为：**"张力"、"火花"、"心跳的感觉"、"暧昧气氛"**

---

# 当前任务上下文

## 对话连贯性
你刚刚对用户说过："{last_response}"
如果需要向用户提问，请保持对话连贯，不要重复开场白，自然地接着上面的话继续说。

## 用户画像
{user_profile}

## 情感罗盘（现状分析报告）
{status_report}

## 行动规划
{action_plan}

## 对话历史
{conversation_history}

---

# 任务
根据提供的【情感罗盘】和【行动规划】，为用户生成一份原子化、保姆级的《行动指南》。

## 要求
1. **不劝退原则**：除非遇到法律/道德底线（如对方已婚），否则**坚决不建议用户放弃**。哪怕是备胎，也要给出"置之死地而后生"的逆转策略。

# 撰写原则与注意事项

1. **绝对服从战术决策**：检查用户是否有抗拒情绪或试图偏离行动规划。如果用户试图偏离，你必须在指南中强硬地纠正他的心态。

2. **细节填充**：必须将用户反馈中的具体名词（物品、时间、地点）填入任务步骤中。

3. **产品功能联动引导**：
   - **聊天引导**：如果涉及"回复对方"，不要在行动指南里写具体话术，引导用户使用【聊天分析】
   - **咨询引导**：如果任务复杂，引导用户使用【咨询】

---

# 判断信息是否足够

## 你的任务
1. 首先判断信息是否足够生成具体的行动指南
2. 如果信息不足，设置 `need_questions=true`（不需要填写 `question_goal`，目标在你心中即可）
   - 如果设置了 `need_questions=true`，系统会自动加载「提问引导 Skill」的完整指令，你需要生成完整的 `inquiry_card`
3. 如果信息足够，输出完整的行动指南

## 输出格式
请以 JSON 格式输出：
```json
{{
  "need_questions": false,
  "response": "如果需要提问，这里写你要对用户说的话",
  "guide_content": "如果信息足够，这里输出完整的 Markdown 格式行动指南",
  "inquiry_card": null
}}
```

**重要说明**：
- 如果 `need_questions=true`，必须生成完整的 `inquiry_card`（包含 questions 数组、intro、reasoning）
- 如果 `need_questions=false`，`inquiry_card` 设为 `null`

如果 need_questions=false，guide_content 必须包含以下结构：

## 📋 任务卡片：[任务名称]
> [一句话核心意图]

### 🏷️ 军师简报
- **任务目标**: 一句话讲清楚要做什么，以及*为什么要这么做*
- **难度等级**: ⭐ ~ ⭐⭐⭐⭐⭐
- **最佳执行时机**: 给出建议

### 👣 执行步骤
原子化的 Step 1, Step 2, Step 3...
如果是发消息/朋友圈，提供简要的文案参考
如果是约会/见面，分阶段描写

### 🔮 预案推演
- 🟢 **顺利**: 对方反应热烈 -> 策略
- ⚪ **平淡**: 对方反应一般 -> 策略
- 🔴 **恶劣**: 对方无视/冷淡 -> 策略

### 🚩 反馈触发点
明确告诉用户，做到哪一步需要回来汇报

### 🧠 军师锦囊
针对用户的信息和战略红线，给出强心针或镇定剂
"""

