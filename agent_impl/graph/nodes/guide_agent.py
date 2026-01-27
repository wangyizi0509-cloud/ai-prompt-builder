"""
行动指南 Agent 节点 (Action Guide Agent)
负责生成具体的 SOP 任务包

上下文架构更新 (v2.0)：
- 使用分层上下文架构（Layer 0-4）
- 通过 context_builder 统一组装上下文
- 支持多个未执行的行动指南（action_guides 列表）

任务管理更新 (v2.1)：
- 任务边界：被调用时开始新任务，产出指南时结束
- 思考过程：同一任务内保留，任务结束时归档
- 报告编号：每次产出指南分配递增编号
"""

import json
from typing import Any
from datetime import datetime

from graph.state import AgentState, ActionGuide
from graph.message_builder import build_messages_for_model
from graph.context_types import create_new_task
from utils.message_utils import get_msg_role_and_content
from graph.tools.ask_tool import get_ask_tool
from graph.tools.submit_tools import (
    submit_action_guide,
    update_guide_status,
    update_guide_content,
    return_to_main,
)
from config import get_llm


# ============================================================
# 任务管理辅助函数
# ============================================================

def _get_next_task_id(task_list: list) -> str:
    """生成下一个任务 ID（格式：task_001, task_002, ...）"""
    if not task_list:
        return "task_001"
    
    max_num = 0
    for task in task_list:
        task_id = task.get("task_id", "")
        if task_id.startswith("task_"):
            try:
                num = int(task_id.split("_")[1])
                max_num = max(max_num, num)
            except (ValueError, IndexError):
                pass
    
    return f"task_{max_num + 1:03d}"


def _start_new_task(state: AgentState) -> dict:
    """开始新任务"""
    task_registry = state.get("task_registry", {})
    task_list = list(task_registry.get("guide_agent", []))
    
    for task in task_list:
        task["is_active"] = False
    
    new_task_id = _get_next_task_id(task_list)
    new_task = create_new_task(new_task_id)
    task_list.append(new_task)
    
    print(f"[DEBUG] GuideAgent: Started new task {new_task_id}")
    
    return {
        "task_registry": {
            **task_registry,
            "guide_agent": task_list,
        }
    }


def _complete_current_task(state: AgentState) -> dict:
    """完成当前任务"""
    task_registry = state.get("task_registry", {})
    task_list = list(task_registry.get("guide_agent", []))
    
    for task in task_list:
        if task.get("is_active", False):
            task["is_active"] = False
            task["completed_at"] = datetime.now().isoformat()
            print(f"[DEBUG] GuideAgent: Completed task {task.get('task_id')}")
            break
    
    return {
        "task_registry": {
            **task_registry,
            "guide_agent": task_list,
        }
    }

def guide_agent_node(state: AgentState) -> dict[str, Any]:
    """
    行动指南 Agent 节点
    
    职责：
    1. 基于行动规划生成具体 SOP
    2. 明确当前任务和步骤
    3. 提供话术要点
    4. 给出 Do's 和 Don'ts
    5. 如果信息不足，通过工具获取提问技能指令
    
    任务边界：
    - 新任务触发：被调用时（非恢复执行）
    - 任务结束：产出指南（completion_status=COMPLETED）
    
    Args:
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    # 提问节流（同一 agent 连续提问 <= max_question_streak；中间发生非提问动作则清零）
    streak_agent = state.get("question_streak_agent")
    streak_count = int(state.get("question_streak_count", 0) or 0)
    max_streak = int(state.get("max_question_streak", 3) or 3)

    # 向后兼容：旧字段仍可能被外部依赖（日志/测试）
    question_count = int(state.get("question_count", 0) or 0)
    max_questions = int(state.get("max_questions", 3) or 3)
    
    # === 任务边界判定 ===
    is_resuming = (state.get("current_agent") == "guide_agent" and 
                   state.get("agent_resume_point") == "continue_guide")
    
    task_updates = {}
    if not is_resuming:
        task_updates = _start_new_task(state)
    
    # 工具调用返回检查（增强版）
    messages = state.get("messages", [])
    last_msg_role = ""
    last_tool_content = None
    if messages:
        last_msg_role, last_tool_content = get_msg_role_and_content(messages[-1])
    
    from_tool_call = (state.get("_tool_caller") == "guide_agent" or last_msg_role == "tool")
    
    if from_tool_call:
        print(f"[DEBUG] GuideAgent: Continuing after tool call (last_role={last_msg_role})")
    
    # 准备 LLM（工具绑定在决策后进行）
    base_llm = get_llm(temperature=0.6)
    if from_tool_call:
        print("[DEBUG] GuideAgent: Second stage (from_tool_call), tools disabled to prevent loop")
    
    # 注入 tool 输出（如果刚从工具返回）。
    if from_tool_call and not last_tool_content:
        # [FIX] 优先检查 _last_tool_content（skill_tools_node 直接设置的，最可靠）
        cached_content = state.get("_last_tool_content")
        if cached_content:
            last_tool_content = cached_content
        
        # 其次回溯 messages 查找 tool 消息
        if not last_tool_content:
            for msg in reversed(messages or []):
                r, c = get_msg_role_and_content(msg)
                if r == "tool" and c:
                    last_tool_content = c
                    break
        
        # 最后从 _last_tool_outputs 列表中提取
        if not last_tool_content:
            cached_tool_outputs = state.get("_last_tool_outputs")
            if isinstance(cached_tool_outputs, list):
                for item in reversed(cached_tool_outputs):
                    if not isinstance(item, dict):
                        continue
                    cached_content = item.get("content") or item.get("tool_output") or ""
                    if cached_content:
                        last_tool_content = cached_content
                        break

    # [FIX] 当从工具调用返回时，不应该再次添加用户的上一条输入
    # 否则模型会看到错误的消息栈，误以为用户已确认，跳过提问
    current_input = "" if from_tool_call else state.get("user_message", "")
    
    model_messages = build_messages_for_model(
        state=state,
        agent_name="guide_agent",
        current_input=current_input,
    )
    prompt_source = "message_builder"
    prompt_fallback = False
    
    # === 调用 LLM（工具驱动）===
    ask_mode = state.get("ask_mode", False)
    print(f"[DEBUG] GuideAgent: Invoking LLM (from_tool_call={from_tool_call}, ask_mode={ask_mode})")
    response = None
    pending_action = state.get("_pending_action") or ""
    
    # Phase 2: ask_mode=True 后强制调用 ask 工具生成 inquiry_card
    if from_tool_call and pending_action == "ask":
        ask_full_tool = get_ask_tool(True)
        llm_with_tools = base_llm.bind_tools(
            [ask_full_tool],
            tool_choice={"type": "function", "function": {"name": "ask"}},
        )
        response = llm_with_tools.invoke(model_messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print("[DEBUG] GuideAgent: Forced ask tool call (Phase 2: generate inquiry_card)")
            if hasattr(response, "name"):
                response.name = "guide_agent"
            return {
                "messages": [response],
                "current_agent": "guide_agent",
                "_tool_caller": "guide_agent",
                "debug_log": [{
                    "node": "guide_agent",
                    "step": "Tool Call Requested (ask forced, Phase 2)",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }],
            }
    
    elif from_tool_call:
        # 允许在委派后继续发起 ask/submit/update 工具调用
        ask_tool = get_ask_tool(False)
        llm_with_tools = base_llm.bind_tools(
            [ask_tool, submit_action_guide, update_guide_status, update_guide_content, return_to_main],
            parallel_tool_calls=True,
        )
        response = llm_with_tools.invoke(model_messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"[DEBUG] GuideAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
            if hasattr(response, "name"):
                response.name = "guide_agent"
            return {
                "messages": [response],
                "current_agent": "guide_agent",
                "_tool_caller": "guide_agent",
                "debug_log": [{
                    "node": "guide_agent",
                    "step": "Tool Call Requested",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }],
            }
    else:
        # 使用定制工具：guide_agent 只允许使用 inquiry skill
        # 允许子 Agent 直接进入 ask 两阶段提问（Phase 1: ask(action="enable")）
        ask_tool = get_ask_tool(False)
        llm_with_tools = base_llm.bind_tools(
            [ask_tool, submit_action_guide, update_guide_status, update_guide_content, return_to_main],
            parallel_tool_calls=True,
        )
        response = llm_with_tools.invoke(model_messages)
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"[DEBUG] GuideAgent: Model requested tool call: {[tc['name'] for tc in response.tool_calls]}")
            if hasattr(response, "name"):
                response.name = "guide_agent"
            return {
                "messages": [response],
                "current_agent": "guide_agent",
                "_tool_caller": "guide_agent",
                "debug_log": [{
                    "node": "guide_agent",
                    "step": "Tool Call Requested",
                    "tool_calls": [tc["name"] for tc in response.tool_calls],
                }],
            }
    
    # 未触发工具调用，视为失败（硬切）
    err_msg = "系统异常：未调用 submit_action_guide 或 update_guide_status 工具提交行动指南结果。请重试。"
    result = {
        "action_guide": None,
        "inquiry_card": None,
        "pending_questions": [],
        "pending_responses": state.get("pending_responses", []) + [{
            "from": "guide_agent",
            "content": err_msg,
            "phase": "after_guide",
        }],
        "messages": [{"role": "assistant", "name": "guide_agent", "content": err_msg}],
        "current_agent": "guide_agent",
        "agent_resume_point": "continue_guide",
        "completion_status": None,
        "result_summary": None,
        "_tool_caller": None,
        "_submit_result": None,
        "_last_tool_outputs": None,
        "_last_tool_content": None,
    }
    if task_updates and "task_registry" not in result:
        result["task_registry"] = task_updates.get("task_registry", state.get("task_registry", {}))
    return result


def _format_history(messages: list) -> str:
    """格式化对话历史，包含工具调用结果"""
    if not messages:
        return "无历史对话"
    
    recent = messages[-10:]
    formatted = []
    for msg in recent:
        msg_role, msg_content = get_msg_role_and_content(msg)
        if msg_role == "user":
            role = "用户"
        elif msg_role == "assistant" or msg_role == "ai":
            role = "小话"
        elif msg_role == "tool":
            role = "工具输出"
        else:
            continue
            
        formatted.append(f"{role}: {msg_content}")
    
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
            "task_id": "",
            "thought": "",
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
2. 如果信息不足，使用 `ask` 两阶段提问（先 `ask(action="enable")`，再 `ask(questions=[...], intro=..., reasoning=...)`）
3. 如果信息足够，输出完整的行动指南

## 输出格式
请以 JSON 格式输出：
```json
{{
  "task_id": "当前任务ID（例如 task_001）。",
  "thought": "本轮内部思考（给系统看的，不给用户看）。要求：简短、决策导向。",
  "response": "如果需要提问，这里写你要对用户说的话",
  "guide_content": "如果信息足够，这里输出完整的 Markdown 格式行动指南",
  "inquiry_card": null
}}
```

**重要说明**：
- 仅当需要提问时才生成完整的 `inquiry_card`（包含 questions 数组、intro、reasoning）
- 其他情况下，`inquiry_card` 设为 `null`

当 guide_content 需要输出时，必须包含以下结构：

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

