"""
Onboarding 子图：用于首次信息收集。

采用 Subgraph + 状态恢复模式：
- 独立 StateGraph，作为主图的一个节点
- 单节点循环，通过 Command(goto="onboarding_agent") 自己回到自己
"""

from langgraph.graph import StateGraph, START, END

from graph.state import AgentState, convert_message_to_dict, ensure_message_id, get_message_id
from onboarding.onboarding_agent import onboarding_agent_node


def _normalize_onboarding_input(state: AgentState) -> dict:
    """
    统一 Onboarding 子图入口的输入格式：
    - messages 统一为 dict + 标准角色
    - 若 user_message 为空，从 messages 回填
    - 若 user_message 有但 messages 缺失，则补一条
    - 维护 current_message_id（优先沿用已有）
    """
    raw_messages = state.get("messages", [])
    normalized: list[dict] = []
    for m in raw_messages:
        try:
            msg = convert_message_to_dict(m)
            role = msg.get("role")
            if role == "human":
                msg["role"] = "user"
            elif role == "ai":
                msg["role"] = "assistant"
            _, msg_dict = ensure_message_id(msg)
            normalized.append(msg_dict)
        except Exception:
            if isinstance(m, dict):
                role = m.get("role")
                if role == "human":
                    m["role"] = "user"
                elif role == "ai":
                    m["role"] = "assistant"
                _, msg_dict = ensure_message_id(m)
                normalized.append(msg_dict)
            elif hasattr(m, "content"):
                role = getattr(m, "type", getattr(m, "role", "assistant"))
                if role == "human":
                    role = "user"
                elif role == "ai":
                    role = "assistant"
                _, msg_dict = ensure_message_id({"role": role, "content": m.content})
                normalized.append(msg_dict)

    user_message = str(state.get("user_message") or "").strip()
    current_message_id = str(state.get("current_message_id") or "").strip()

    if not user_message:
        for msg in reversed(normalized):
            if msg.get("role") == "user":
                content = msg.get("content")
                content_str = content.strip() if isinstance(content, str) else str(content).strip() if content is not None else ""
                if content_str:
                    user_message = content_str
                    if not current_message_id:
                        current_message_id = get_message_id(msg)
                    break

    if user_message and not current_message_id:
        for msg in reversed(normalized):
            if msg.get("role") == "user":
                content = msg.get("content")
                content_str = content.strip() if isinstance(content, str) else ""
                if content_str == user_message:
                    current_message_id = get_message_id(msg)
                    break

    if user_message:
        existing_ids = {get_message_id(m) for m in normalized if get_message_id(m)}
        existing_user_contents = {
            (m.get("content") or "").strip()
            for m in normalized
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        }
        need_add = False
        if current_message_id:
            need_add = current_message_id not in existing_ids
        else:
            need_add = user_message not in existing_user_contents
        if need_add:
            msg_payload = {"role": "user", "content": user_message}
            if current_message_id:
                msg_payload["id"] = current_message_id
            _, msg_dict = ensure_message_id(msg_payload)
            normalized.append(msg_dict)
            if not current_message_id:
                current_message_id = msg_dict.get("id", current_message_id)

    updates: dict = {"messages": normalized}
    if user_message:
        updates["user_message"] = user_message
    if current_message_id:
        updates["current_message_id"] = current_message_id
    return updates


def create_onboarding_workflow() -> StateGraph:
    """创建并返回 Onboarding 子图（未编译）。"""
    builder = StateGraph(AgentState)
    builder.add_node("onboarding_input_router", _normalize_onboarding_input)
    builder.add_node("onboarding_agent", onboarding_agent_node)
    builder.add_edge(START, "onboarding_input_router")
    builder.add_edge("onboarding_input_router", "onboarding_agent")
    builder.add_edge("onboarding_agent", END)
    return builder


def compile_onboarding_workflow():
    """编译后的 Onboarding 子图，供主图引用。"""
    return create_onboarding_workflow().compile()

