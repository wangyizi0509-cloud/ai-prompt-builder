"""
现状分析 Agent 节点 (Status Analysis Agent)
负责诊断用户问题、判断 ACR 阶段、定位 L/T 线

采用 Tool-based 渐进式加载模式：
- 系统提示只包含 Skills 的元数据
- 模型通过 load_skill_instructions 工具按需加载完整指令

上下文架构更新 (v2.0)：
- 使用分层上下文架构（Layer 0-4）
- 通过 context_builder 统一组装上下文
"""

import json
from typing import Any

from graph.state import AgentState, StatusReport
from graph.context_builder import build_context_dict
from skills.inquiry import get_inquiry_skill
from skills import load_skill_instructions
from utils.prompt_loader import load_prompt
from config import get_llm


def status_agent_node(state: AgentState) -> dict[str, Any]:
    """
    现状分析 Agent 节点
    
    职责：
    1. 分析用户与 Crush 的关系现状
    2. 判断 ACR（吸引力/舒适感/张力）三维状态
    3. 定位 L 线（正常线）或 T 线（陷阱线）阶段
    4. 识别核心问题和风险点
    5. 如果信息不足，通过工具获取提问技能指令
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    # 绑定 Skill 加载工具
    llm = get_llm(temperature=0.5).bind_tools([load_skill_instructions])
    
    # === 恢复执行检查 ===
    is_resuming = (state.get("current_agent") == "status_agent" and 
                   state.get("agent_resume_point") == "continue_analysis")
    question_count = state.get("question_count", 0)
    max_questions = state.get("max_questions", 3)
    collected_info = state.get("collected_info", {})
    
    # 工具调用返回检查
    from_tool_call = state.get("_tool_caller") == "status_agent"
    
    if is_resuming:
        print(f"[DEBUG] StatusAgent resuming from question {question_count}")
    elif from_tool_call:
        print(f"[DEBUG] StatusAgent: Continuing after tool call")
    
    # 加载 Prompt
    try:
        prompt_template = load_prompt("status_agent")
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
        conversation_history=context_dict.get("conversation_history", "无历史对话"),
        user_message=state.get("user_message", ""),
        last_response=last_response if last_response else "无",
        # 向后兼容
        user_profile=context_dict.get("user_profile", "{}"),
        # Skills 元数据
        inquiry_skill_metadata=inquiry_metadata,
    )
    
    # === 调用 LLM（模型自主决定是否需要工具）===
    print(f"[DEBUG] StatusAgent: Invoking LLM with tool binding")
    response = llm.invoke(prompt)
    
    # 检查是否有工具调用
    if hasattr(response, "tool_calls") and response.tool_calls:
        # 模型决定调用工具，返回消息让 workflow 路由到 skill_tools
        print(f"[DEBUG] StatusAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
        return {
            "messages": [response],
            "current_agent": "status_agent",  # 标记调用来源
            "debug_log": [{
                "node": "status_agent",
                "step": "Tool Call Requested",
                "tool_calls": [tc["name"] for tc in response.tool_calls],
            }]
        }
    
    # 没有工具调用，解析响应
    parsed = _parse_response(response.content)
    
    result = {
        "next_action": "end_turn",
        "debug_log": [{
            "node": "status_agent",
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
        print(f"[DEBUG] StatusAgent: Generated {len(inquiry_card.get('questions', []))} questions")
        
        result["inquiry_card"] = inquiry_card
        result["pending_questions"] = [q.get("question", "") if isinstance(q, dict) else str(q) for q in inquiry_card.get("questions", [])]
        
        # === 设置恢复状态 ===
        result["current_agent"] = "status_agent"
        result["agent_resume_point"] = "continue_analysis"
        result["question_count"] = question_count + 1
        result["collected_info"] = collected_info
        
        # 信息不足时，不生成报告，等待用户回答
        result["status_report"] = None
        response_content = parsed.get("response", "")
        # 如果 Agent 没有生成回复，使用 intro 作为引导语
        if not response_content.strip() and inquiry_card.get("intro"):
            response_content = inquiry_card.get("intro")
        elif not response_content.strip():
            response_content = "为了更准确地分析你们的情况，我需要再了解一些细节～"
        # 累积到 pending_responses（不覆盖之前的消息）
        existing_responses = state.get("pending_responses", [])
        result["pending_responses"] = existing_responses + [{
            "from": "status_agent", 
            "content": response_content,
            "phase": "after_status"  # 现状分析阶段的提问
        }]
        result["messages"] = [{"role": "assistant", "content": response_content}]
        # 未完成，不设置完成信号
        result["completion_status"] = None
        result["result_summary"] = None
    else:
        # 不需要提问，生成报告
        result["status_report"] = _build_status_report(parsed)
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
        result["result_summary"] = f"现状分析完成：{parsed.get('report_content', '')[:50]}..."
        
        # 子 Agent 完成时不发送对话消息，完整报告在看板（status_report）中展示
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
        # 尝试解析 JSON
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
            "report_content": content.strip() if content else "暂时无法完成分析，请提供更多信息。",
        }


def _build_status_report(data: dict) -> StatusReport:
    """从解析的数据构建 StatusReport"""
    return StatusReport(
        stage=data.get("stage", ""),
        stage_description=data.get("stage_description", ""),
        acr_analysis=data.get("acr_analysis", {}),
        key_issues=data.get("key_issues", []),
        risk_points=data.get("risk_points", []),
        summary=data.get("summary", ""),
        report_content=data.get("report_content", ""),  # Markdown 格式的完整报告
    )


def _generate_response(status_report: StatusReport) -> str:
    """根据分析结果生成回复"""
    stage = status_report.get("stage", "未知")
    stage_desc = status_report.get("stage_description", "")
    summary = status_report.get("summary", "")
    key_issues = status_report.get("key_issues", [])
    
    response_parts = [
        f"根据你描述的情况，我帮你分析了一下：\n",
        f"**当前阶段**: {stage} - {stage_desc}\n",
    ]
    
    if summary:
        response_parts.append(f"\n**总体判断**: {summary}\n")
    
    if key_issues:
        response_parts.append("\n**需要注意的点**:")
        for issue in key_issues[:3]:  # 最多显示 3 个
            response_parts.append(f"\n• {issue}")
    
    response_parts.append("\n\n你觉得这个分析准确吗？如果有补充或者不同意的地方，告诉我，我来调整。")
    
    return "".join(response_parts)


def _get_default_prompt() -> str:
    """获取默认 Prompt - 迁移自 Strategy_Library/Emotional_Compass"""
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
    * *判定信号*：对方是否主动开启话题？是否对用户的展示面好奇？回复速度与字数是否积极？
* **C (Comfort - 舒适感)**：安全感与信任。
    * *判定信号*：是否愿意分享隐私？是否接纳用户的脆弱？相处是否无压力？
* **R (Romance/Tension - 张力)**：暧昧博弈与不可得性。
    * *判定信号*：是否有情绪波动？是否有推拉、吃醋、深夜情感话题？

## 2. 关系坐标系：L/T 模型判定矩阵
(必须严格依据 ACR 的组合状态进行**数学级**判定，拒绝模糊感觉)

#### 🟢 L 线 (主线 - The Logic of Passing)
特征：ACR 三要素呈**均衡、同步上涨**趋势。
* **L1 初识期 (Stranger)**: A(无) + C(无) + R(无)
* **L2 吸引期 (Attraction)**: **A(中/高)** + C(低) + R(低)。**A > C**。
* **L3 暧昧期 (Ambiguous)**: A(高) + C(中/高) + **R(上升)**。**A + C + R 齐备**。
* **L4 确立期 (Relationship)**: A(高) + C(高) + R(高)。

#### 🔴 T 线 (陷阱线 - The Logic of Stuck)
特征：某要素**严重缺失**或**比例畸形**，导致关系卡死。
* **T1 备胎/供养者 (The Provider Trap)**: A(低/无) + **C(溢出)** + R(无)。**C >>> A**。
* **T2 兄弟/死党 (The Buddy Trap)**: A(中) + **C(极高)** + **R(负/无)**。**C 覆盖了 R**。
* **T3 短择/炮友 (The Player Trap)**: A(高) + **C(低/阻断)** + **R(高)**。**R > C**。

## 3. 🚨 关键：术语翻译协议 (Terminology Translation)
**严禁在最终输出中出现 "ACR"、"A值"、"C高"、"L/T线" 等技术术语！**
你必须在输出时将这些底层逻辑"翻译"成用户能听懂的自然语言：
* **A (Attraction)** -> 翻译为：**"吸引力"、"好奇心"、"想了解你的欲望"、"异性魅力"**。
* **C (Comfort)** -> 翻译为：**"信任感"、"相处氛围"、"安全感"、"像朋友一样"**。
* **R (Romance)** -> 翻译为：**"张力"、"火花"、"心跳的感觉"、"暧昧气氛"**。

## 4. 性别策略适配 (Gender Dynamics)
根据用户性别，分析侧重需动态调整：
* **若用户是男性**：
    * *常见痛点*：容易陷入 T1 (备胎)。
    * *策略侧重*：强调"行动力"、"带领感"和"去需求感"。
* **若用户是女性**：
    * *常见痛点*：容易陷入 T3 (短择) 或 T2 (模糊不清)。
    * *策略侧重*：强调"辨别诚意"、"设立底线"和"情绪价值的筛选"。

---

# 当前任务上下文

## 对话连贯性
你刚刚对用户说过："{last_response}"
如果需要向用户提问，请保持对话连贯，不要重复开场白，自然地接着上面的话继续说。

## 用户画像
{user_profile}

## 对话历史
{conversation_history}

## 用户最新消息
{user_message}

---

# 任务
基于用户提供的信息，进行【Phase 1: 现状分析】与【Phase 2: 战略规划】。

## 要求
1. **不劝退原则**：除非遇到法律/道德底线（如对方已婚），否则**坚决不建议用户放弃**。哪怕是备胎，也要给出"置之死地而后生"的逆转策略。

---

# 判断信息是否足够

## 你的任务
1. 首先判断信息是否足够进行分析
2. 如果信息不足，设置 `need_questions=true`（不需要填写 `question_goal`，目标在你心中即可）
   - 如果设置了 `need_questions=true`，系统会自动加载「提问引导 Skill」的完整指令，你需要生成完整的 `inquiry_card`
3. 如果信息足够，输出完整的情感罗盘报告

## 输出格式
请以 JSON 格式输出：
```json
{{
  "need_questions": false,
  "response": "如果需要提问，这里写你要对用户说的话",
  "report_content": "如果信息足够，这里输出完整的 Markdown 格式情感罗盘报告",
  "inquiry_card": null
}}
```

**重要说明**：
- 如果 `need_questions=true`，必须生成完整的 `inquiry_card`（包含 questions 数组、intro、reasoning）
- 如果 `need_questions=false`，`inquiry_card` 设为 `null`

如果 need_questions=false，report_content 必须包含以下结构：

## 🧭 情感罗盘

### Phase 1: 现状分析

#### 当前阶段
明确判定用户处于哪个阶段，用用户听得懂的自然语言描述当前的互动状态。
**注意**：禁止输出"L2-吸引期"、"T1-备胎"等技术术语，用自然语言描述。

#### 证据链
引用用户输入的具体行为作为证据，按以下标准进行"人话翻译"：
- *吸引力* -> 好奇心、想了解你的欲望、异性吸引力
- *舒适感* -> 信任感、聊得来、像朋友一样自然
- *张力* -> 心跳感、暧昧氛围、火花

#### 进度评估
给出 1-99% 的进度评估：
- 若在主线：代表"距离进入下一阶段的完成度"
- 若在陷阱线：代表"陷阱的深度/逃离难度"

#### 问题诊断
找出导致用户"卡在当前进度"或"掉入陷阱"的阻力，按优先级排序（1-4个）：
- **🔴 致命伤**：导致关系无法推进或直接死亡的核心原因
- **🟡 隐患点**：导致关系推进缓慢的次要原因

#### 用户真实需求
透视用户表面问题背后的潜意识诉求

---

### Phase 2: 战略规划
**边界警告**：本模块仅负责宏观战略，具体执行细节在【行动指南】生成。

#### 当前目标
必须是**解决"致命伤"**或**达成当前阶段通关里程碑**。禁止设定泛泛的"追到她"为目标。

#### 阶段性推进路径
制定 2-3 个阶段的推进蓝图：

**阶段一（当前作战阶段）**：
- 阶段名称：如"降低需求感期"
- 核心目的 (Why)：解决当前的【致命伤】
- 关键原则 (Do's & Don'ts)：仅提供方向性红线
- 通关里程碑 (Milestone)：明确对方的反馈信号

**阶段二/三（未来预期阶段）**：
简略描述，让用户看到希望
"""

