"""
消息构建器 (Message Builder)
实现"结构化状态注入模式 (Structured State Injection Pattern)"

架构说明：
- 将上下文以 XML 格式注入到标准消息栈中
- 消息栈结构：SystemMessage → HumanMessage(XML) → AIMessage(Ack) → History → HumanMessage(当前输入)
- 支持 DeepSeek V3 / Claude 3.5 / GPT-4o 的 KV Cache 优化

参考文档：
- agent_impl/docs/plan_消息结构标准化.md
"""

from typing import TYPE_CHECKING, Optional
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    BaseMessage,
)

from graph.context_builder import build_context_dict
from graph.tools.ask_tool import ASK_MODE_SIMPLE
from graph.tools.consult_answer_tool import CONSULT_MODE_SIMPLE
from graph.tools.emotion_support_tool import EMOTION_MODE_SIMPLE
from utils.prompt_loader import load_prompt
from utils.message_utils import get_msg_role_and_content

if TYPE_CHECKING:
    from graph.state import AgentState


# ============================================================
# 常量定义
# ============================================================

# Virtual Ack 消息内容（用于语义隔离"阅读资料"和"开始对话"）
# [FIX] 2026-01-26: 改用系统标记格式，避免模型模仿输出
VIRTUAL_ACK_MESSAGE = "[SYS:DOSSIER_LOADED]"

# Context Injection 消息前缀（用于识别和过滤）
CONTEXT_INJECTION_PREFIX = "<dossier"

# 默认历史轮次
DEFAULT_MAX_TURNS = 10

# submit_* 工具历史压缩标记（用于 AIMessage.tool_calls.args）
SUBMIT_TOOL_COMPRESSION_FIELDS = {
    "submit_status_report": ["report_markdown"],
    "submit_action_plan": ["phases", "key_principles", "summary"],
    "submit_action_guide": ["guide_markdown", "steps", "talking_points", "dos", "donts"],
    "update_guide_content": ["guide_markdown", "steps", "talking_points", "dos", "donts"],
    "ask": ["questions", "intro", "reasoning"],
}


# ============================================================
# 核心函数
# ============================================================

def build_messages_for_model(
    state: "AgentState",
    agent_name: str,
    current_input: str,
) -> list[BaseMessage]:
    """
    构建标准消息列表，用于模型调用
    
    消息栈结构：
    [1] SystemMessage     - 角色人设 + 输出格式 + 核心规则
    [2] HumanMessage      - XML 格式的上下文档案 (Context Injection)
    [3] AIMessage         - Virtual Ack: "收到，已阅档案。请问有什么需要帮助的？"
    [4~N] History         - HumanMessage / AIMessage / ToolMessage
    [End] HumanMessage    - 用户当前输入
    
    Args:
        state: AgentState 状态对象
        agent_name: Agent 名称（main_agent / status_agent / plan_agent / guide_agent）
        current_input: 用户当前输入
    
    Returns:
        标准 BaseMessage 列表
    """
    messages: list[BaseMessage] = []
    
    # [1] System Prompt: 人设 + 规则（无动态数据）
    system_prompt = load_system_prompt(agent_name)
    messages.append(SystemMessage(content=system_prompt))
    
    # [2] Context Injection: XML 包裹的档案
    context_xml = build_context_xml(state, agent_name)
    messages.append(HumanMessage(content=context_xml))
    
    # [3] Virtual Ack: AI 确认收到（语义隔离）
    messages.append(AIMessage(content=VIRTUAL_ACK_MESSAGE, name=agent_name))
    
    # [4~N] History: 真实对话历史（滑动窗口）
    history = build_conversation_history(state, max_turns=DEFAULT_MAX_TURNS)
    messages.extend(history)
    
    # [End] Current Input: 用户当前输入
    if current_input and current_input.strip():
        messages.append(HumanMessage(content=current_input))
    
    return messages


def load_system_prompt(agent_name: str) -> str:
    """
    加载 Agent 的 System Prompt
    
    说明：
    - 不再注入 skills 列表，工具指令由 tool message 提供
    
    Args:
        agent_name: Agent 名称（对应 prompts/{agent_name}.md）
    
    Returns:
        System Prompt 内容
    """
    try:
        # 加载 Prompt 文件
        prompt_content = load_prompt(agent_name)
        
        return prompt_content
        
    except FileNotFoundError:
        # 文件不存在时返回默认提示
        return f"你是 {agent_name}，请根据用户输入提供帮助。"


def build_context_xml(state: "AgentState", agent_name: str) -> str:
    """
    构建 XML 格式的上下文档案
    
    来源标注（source 属性）沿用信任层级规则：
    - layer1: 静态情报（用户信息、Crush 信息）
    - layer2: 工作上下文（报告、规划、指南）
    
    Args:
        state: AgentState 状态对象
        agent_name: 目标 Agent 名称
    
    Returns:
        XML 格式字符串
    """
    # 调用现有 context_builder 获取上下文数据
    context_dict = build_context_dict(state, target_agent=agent_name)
    
    # 构建 XML
    xml_parts = [f'<dossier agent="{agent_name}">']
    
    # Layer 1: 静态情报
    user_context = context_dict.get("user_context", "暂无")
    xml_parts.append(f'  <user_context source="layer1">')
    xml_parts.append(f'    {_escape_xml_content(user_context)}')
    xml_parts.append(f'  </user_context>')
    
    # Layer 2.a: 稳定工作上下文
    status_report = context_dict.get("status_report", "暂无")
    xml_parts.append(f'  <status_report source="layer2">')
    xml_parts.append(f'    {_escape_xml_content(status_report)}')
    xml_parts.append(f'  </status_report>')
    
    action_plan = context_dict.get("action_plan", "暂无")
    xml_parts.append(f'  <action_plan source="layer2">')
    xml_parts.append(f'    {_escape_xml_content(action_plan)}')
    xml_parts.append(f'  </action_plan>')
    
    # Layer 2.b: 动态工作上下文
    action_guides = context_dict.get("action_guides", "暂无")
    xml_parts.append(f'  <action_guides source="layer2">')
    xml_parts.append(f'    {_escape_xml_content(action_guides)}')
    xml_parts.append(f'  </action_guides>')
    
    dynamic_intel = context_dict.get("dynamic_intel", "")
    if dynamic_intel:
        xml_parts.append(f'  <dynamic_intel source="layer2">')
        xml_parts.append(f'    {_escape_xml_content(dynamic_intel)}')
        xml_parts.append(f'  </dynamic_intel>')
    
    history_summaries = context_dict.get("history_summaries", "")
    if history_summaries:
        xml_parts.append(f'  <history_summaries source="layer2">')
        xml_parts.append(f'    {_escape_xml_content(history_summaries)}')
        xml_parts.append(f'  </history_summaries>')
    
    # 任务系统
    task_index = context_dict.get("task_index", "暂无")
    active_task_payload = context_dict.get("active_task_payload", "{}")
    xml_parts.append(f'  <task_context>')
    xml_parts.append(f'    <task_index>{_escape_xml_content(task_index)}</task_index>')
    xml_parts.append(f'    <active_task>{_escape_xml_content(active_task_payload)}</active_task>')
    xml_parts.append(f'  </task_context>')
    
    # 任务绑定上下文
    bound_contexts = context_dict.get("bound_contexts", "")
    if bound_contexts:
        xml_parts.append(f'  <bound_contexts>')
        xml_parts.append(f'    {_escape_xml_content(bound_contexts)}')
        xml_parts.append(f'  </bound_contexts>')
    
    # 专家指令（Main Agent 给专家的 Brief）
    instruction = context_dict.get("instruction", "")
    if instruction:
        xml_parts.append(f'  <instruction source="main_agent">')
        xml_parts.append(f'    {_escape_xml_content(instruction)}')
        xml_parts.append(f'  </instruction>')
    
    xml_parts.append('</dossier>')
    xml_parts.append('')
    xml_parts.append('请阅读以上档案，准备开始咨询。')
    
    return '\n'.join(xml_parts)


def build_conversation_history(
    state: "AgentState",
    max_turns: int = DEFAULT_MAX_TURNS,
) -> list[BaseMessage]:
    """
    从 state["messages"] 提取历史对话，转换为标准 Message 类型
    
    过滤规则：
    - 跳过 Context Injection 消息（以 <dossier 开头的 HumanMessage）
    - 跳过 Virtual Ack 消息（固定文本的 AIMessage）
    - 保留真实对话：HumanMessage / AIMessage / ToolMessage
    
    动态简化规则（渐进式披露）：
    - 当 ask_mode=False 且存在 ask_mode_tool_message_id 时，
      将 Phase 1 的详细策略 ToolMessage 简化为简短版本
    
    Args:
        state: AgentState 状态对象
        max_turns: 最大保留轮次（按用户消息计数）
    
    Returns:
        标准 BaseMessage 列表
    """
    messages = state.get("messages", [])
    if not messages:
        return []
    
    # 获取 ask_mode 相关状态（用于动态简化）
    ask_mode = state.get("ask_mode", False)
    ask_mode_tool_message_id = state.get("ask_mode_tool_message_id")
    # 只有当 ask_mode=False 且有 tool_message_id 时才需要简化
    should_simplify_ask_tool_msg = (not ask_mode) and bool(ask_mode_tool_message_id)
    
    # 获取 consult_mode 相关状态（用于动态简化）
    consult_mode = state.get("consult_mode", False)
    consult_mode_tool_message_id = state.get("consult_mode_tool_message_id")
    # 只有当 consult_mode=False 且有 tool_message_id 时才需要简化
    should_simplify_consult_tool_msg = (not consult_mode) and bool(consult_mode_tool_message_id)
    
    # 获取 emotion_mode 相关状态（用于动态简化）
    emotion_mode = state.get("emotion_mode", False)
    emotion_mode_tool_message_id = state.get("emotion_mode_tool_message_id")
    # 只有当 emotion_mode=False 且有 tool_message_id 时才需要简化
    should_simplify_emotion_tool_msg = (not emotion_mode) and bool(emotion_mode_tool_message_id)
    
    # 预计算工具调用映射（用于 tool message 关联）
    tool_call_map: dict[str, dict] = {}
    for i, msg in enumerate(messages):
        tool_calls = None
        if isinstance(msg, dict):
            tool_calls = msg.get("tool_calls")
        else:
            tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            continue
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            tc_id = str(tc.get("id") or "")
            if tc_id:
                tool_call_map[tc_id] = tc

    last_tool_idx = -1
    last_tool_call_id = ""
    last_tool_name = ""
    for i in range(len(messages) - 1, -1, -1):
        role, _ = get_msg_role_and_content(messages[i])
        if role == "tool":
            last_tool_idx = i
            last_tool_call_id = _get_tool_call_id(messages[i])
            last_tool_name = _get_tool_name(messages[i])
            break

    feedback_compressions = state.get("feedback_compressions") or []
    compression_ranges = _build_feedback_compression_ranges(messages, feedback_compressions)

    # 过滤并转换消息
    filtered_messages: list[BaseMessage] = []
    
    for i, msg in enumerate(messages):
        role, content = get_msg_role_and_content(msg)

        if _should_skip_feedback_message(i, content or "", compression_ranges):
            continue
        
        # 跳过无效消息
        if not role:
            continue
        
        tool_calls = None
        if isinstance(msg, dict):
            tool_calls = msg.get("tool_calls")
        else:
            tool_calls = getattr(msg, "tool_calls", None)
        
        if content is None or content == "":
            if not tool_calls:
                continue
            content = ""
        
        # 跳过 Context Injection 消息
        if _is_context_injection(role, content):
            continue
        
        # 跳过 Virtual Ack 消息
        if _is_virtual_ack(role, content):
            continue
        
        # ToolMessage 处理：用完即焚 + 动态简化
        if role == "tool":
            tool_name = _get_tool_name(msg)
            tool_call_id = _get_tool_call_id(msg)
            msg_id = _get_message_id(msg)
            
            # 1. load_skill 输出压缩（除当前轮次外）
            if tool_name == "load_skill":
                is_current_tool_turn = bool(state.get("_tool_caller")) and (i == last_tool_idx)
                if not is_current_tool_turn:
                    skill_id = ""
                    tc = tool_call_map.get(tool_call_id or "", {})
                    if isinstance(tc, dict):
                        args = tc.get("args") or {}
                        skill_id = str(args.get("skill_id") or "")
                    content = f"[已加载 {skill_id} skill]" if skill_id else "[已加载 skill 指令]"
            
            # 2. ask 工具 Phase 1 ToolMessage 动态简化
            # 当 ask_mode=False 时，将详细策略简化为简短版本
            elif tool_name == "ask" and should_simplify_ask_tool_msg:
                if msg_id and msg_id == ask_mode_tool_message_id:
                    # 简化为简短版本，去掉详细策略
                    content = ASK_MODE_SIMPLE
            
            # 3. consult_answer 工具 Phase 1 ToolMessage 动态简化
            # 当 consult_mode=False 时，将详细策略简化为简短版本
            elif tool_name == "consult_answer" and should_simplify_consult_tool_msg:
                if msg_id and msg_id == consult_mode_tool_message_id:
                    # 简化为简短版本，去掉详细策略
                    content = CONSULT_MODE_SIMPLE
            
            # 4. emotion_support 工具 Phase 1 ToolMessage 动态简化
            # 当 emotion_mode=False 时，将详细策略简化为简短版本
            elif tool_name == "emotion_support" and should_simplify_emotion_tool_msg:
                if msg_id and msg_id == emotion_mode_tool_message_id:
                    # 简化为简短版本，去掉详细策略
                    content = EMOTION_MODE_SIMPLE

        # AIMessage 中的 submit_* tool_calls.args 压缩（仅历史消息）
        if role in ("assistant", "ai") and tool_calls:
            is_current_tool_turn = bool(state.get("_tool_caller")) and bool(last_tool_call_id)
            if is_current_tool_turn:
                is_current_tool_turn = any(
                    isinstance(tc, dict) and str(tc.get("id") or "") == last_tool_call_id
                    for tc in tool_calls
                )
            if not is_current_tool_turn:
                tool_calls = _compress_submit_tool_calls(tool_calls)
                if isinstance(msg, dict):
                    msg = dict(msg)
                    msg["tool_calls"] = tool_calls

        # 转换为标准 Message 类型
        base_message = _convert_to_base_message(msg, role, content)
        if base_message:
            filtered_messages.append(base_message)
    
    # 应用滑动窗口：保留最近 N 轮用户消息及其响应
    return _apply_sliding_window(filtered_messages, max_turns)


# ============================================================
# 辅助函数
# ============================================================

def _escape_xml_content(content: str) -> str:
    """
    转义 XML 特殊字符
    
    注意：保留换行符以保持格式
    """
    if not content:
        return ""
    
    # 基本 XML 转义
    content = content.replace("&", "&amp;")
    content = content.replace("<", "&lt;")
    content = content.replace(">", "&gt;")
    
    return content


def _is_context_injection(role: str, content: str) -> bool:
    """
    判断是否为 Context Injection 消息
    
    特征：HumanMessage + 内容以 <dossier 开头
    """
    if role not in ("user", "human"):
        return False
    
    content_stripped = content.strip()
    return content_stripped.startswith(CONTEXT_INJECTION_PREFIX)


def _is_virtual_ack(role: str, content: str) -> bool:
    """
    判断是否为 Virtual Ack 消息
    
    特征：AIMessage + 内容为固定 ack 文本
    """
    if role not in ("assistant", "ai"):
        return False
    
    content_stripped = content.strip()
    return content_stripped == VIRTUAL_ACK_MESSAGE


def _compress_submit_tool_calls(tool_calls: list) -> list:
    """
    压缩历史 AIMessage 中的 tool_calls.args
    
    压缩对象：
    - submit_* 工具：压缩大字段，减少 token 消耗
    - ask 工具：压缩问题列表，只保留调用信号
    """
    if not tool_calls:
        return tool_calls

    changed = False
    compressed_calls = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            compressed_calls.append(tc)
            continue

        tool_name = str(tc.get("name") or "")
        if not tool_name and isinstance(tc.get("function"), dict):
            tool_name = str(tc["function"].get("name") or "")

        if tool_name in SUBMIT_TOOL_COMPRESSION_FIELDS:
            new_tc = dict(tc)
            new_tc["args"] = {"_compressed": True, "tool": tool_name}
            compressed_calls.append(new_tc)
            changed = True
        elif tool_name == "ask":
            # ask 工具：压缩 questions/intro/reasoning，只保留调用信号
            new_tc = dict(tc)
            new_tc["args"] = {"_compressed": True, "tool": "ask"}
            compressed_calls.append(new_tc)
            changed = True
        else:
            compressed_calls.append(tc)

    return compressed_calls if changed else tool_calls


def _convert_to_base_message(
    msg: dict,
    role: str,
    content: str,
) -> Optional[BaseMessage]:
    """
    将消息转换为标准 BaseMessage 类型
    
    Args:
        msg: 原始消息（dict 或 LangChain Message）
        role: 角色（user/assistant/tool/system）
        content: 内容
    
    Returns:
        对应的 BaseMessage 子类实例，或 None
    """
    if role in ("user", "human"):
        return HumanMessage(content=content)
    
    elif role in ("assistant", "ai"):
        # 检查是否有 tool_calls
        tool_calls = None
        name = None
        reasoning_content = None
        if isinstance(msg, dict):
            tool_calls = msg.get("tool_calls")
            name = msg.get("name")
            reasoning_content = msg.get("reasoning_content")
            if reasoning_content is None:
                reasoning_content = (msg.get("additional_kwargs") or {}).get("reasoning_content")
        else:
            tool_calls = getattr(msg, "tool_calls", None)
            name = getattr(msg, "name", None)
            reasoning_content = getattr(msg, "reasoning_content", None)
            if reasoning_content is None:
                reasoning_content = (getattr(msg, "additional_kwargs", {}) or {}).get("reasoning_content")
        
        additional_kwargs = {"reasoning_content": reasoning_content} if reasoning_content else None
        if tool_calls:
            if additional_kwargs:
                return AIMessage(content=content, tool_calls=tool_calls, name=name, additional_kwargs=additional_kwargs)
            return AIMessage(content=content, tool_calls=tool_calls, name=name)
        if additional_kwargs:
            return AIMessage(content=content, name=name, additional_kwargs=additional_kwargs)
        return AIMessage(content=content, name=name)
    
    elif role == "tool":
        # 提取 tool_call_id
        tool_call_id = None
        name = None
        if isinstance(msg, dict):
            tool_call_id = msg.get("tool_call_id")
            name = msg.get("name")
        else:
            tool_call_id = getattr(msg, "tool_call_id", None)
            name = getattr(msg, "name", None)
        
        return ToolMessage(
            content=content,
            tool_call_id=tool_call_id or "",
            name=name,
        )
    
    elif role == "system":
        name = None
        if isinstance(msg, dict):
            name = msg.get("name")
        else:
            name = getattr(msg, "name", None)
        return AIMessage(content=content, name=name or "system_notice")
    
    # 未知角色，跳过
    return None


def _apply_sliding_window(
    messages: list[BaseMessage],
    max_turns: int,
) -> list[BaseMessage]:
    """
    应用滑动窗口，保留最近 N 轮用户消息及其响应
    
    Args:
        messages: 过滤后的消息列表
        max_turns: 最大轮次（按 HumanMessage 计数）
    
    Returns:
        截取后的消息列表
    """
    if not messages or max_turns <= 0:
        return []
    
    # 从后往前找到第 N 个 HumanMessage 的位置
    user_turn_count = 0
    start_idx = 0
    
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            user_turn_count += 1
            if user_turn_count >= max_turns:
                start_idx = i
                break
    
    return messages[start_idx:]


def _build_feedback_compression_ranges(messages: list, compressions: list) -> list[dict]:
    ranges: list[dict] = []
    if not messages or not compressions:
        return ranges
    for comp in compressions:
        if not isinstance(comp, dict):
            continue
        start_id = str(comp.get("start_message_id") or "")
        keep_tag = str(comp.get("keep_tag") or "")
        if not start_id:
            continue
        start_idx = -1
        for i, msg in enumerate(messages):
            if _get_message_id(msg) == start_id:
                start_idx = i
                break
        if start_idx < 0:
            continue
        keep_idx = None
        for i in range(start_idx, len(messages)):
            _, content = get_msg_role_and_content(messages[i])
            if keep_tag and content and keep_tag in content:
                keep_idx = i
        if keep_idx is None:
            for i in range(len(messages) - 1, start_idx - 1, -1):
                role, content = get_msg_role_and_content(messages[i])
                if role in ("assistant", "ai") and content:
                    keep_idx = i
                    break
        if keep_idx is None:
            keep_idx = start_idx
        ranges.append({"start_idx": start_idx, "keep_idx": keep_idx, "keep_tag": keep_tag})
    return ranges


def _should_skip_feedback_message(index: int, content: str, ranges: list[dict]) -> bool:
    for r in ranges:
        start_idx = r.get("start_idx", -1)
        keep_idx = r.get("keep_idx", -1)
        keep_tag = r.get("keep_tag") or ""
        if start_idx <= index < keep_idx:
            if keep_tag and content and keep_tag in content:
                return False
            return True
        if index == keep_idx:
            return False
    return False


def _get_tool_name(msg: dict | object) -> str:
    if isinstance(msg, dict):
        return str(msg.get("name") or "")
    return str(getattr(msg, "name", "") or "")


def _get_tool_call_id(msg: dict | object) -> str:
    if isinstance(msg, dict):
        return str(msg.get("tool_call_id") or "")
    return str(getattr(msg, "tool_call_id", "") or "")


def _get_message_id(msg: dict | object) -> str:
    """获取消息的唯一 ID"""
    if isinstance(msg, dict):
        return str(msg.get("id") or "")
    return str(getattr(msg, "id", "") or "")
