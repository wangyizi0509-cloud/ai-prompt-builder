"""
Pytest 配置和 Fixtures
用于上下文工程集成测试
"""

import os
import sys
import pytest
from pathlib import Path

if not os.getenv("LLM_PROVIDER"):
    os.environ["LLM_PROVIDER"] = "mock"

# 添加 agent_impl 到 Python 路径
AGENT_IMPL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(AGENT_IMPL_DIR))

from graph.workflow import get_workflow
from graph.state import create_initial_state, AgentState, convert_message_to_dict
from graph.crush_chat_storage import CrushChatManager, create_crush_chat_manager


# ============================================================
# Test User ID (用于隔离测试数据)
# ============================================================

TEST_USER_ID = "test_context_engineering"


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def workflow():
    """获取 LangGraph 工作流实例，默认注入 thread_id，并统一 messages 为 dict。"""
    wf = get_workflow()
    original_invoke = wf.invoke

    def _normalize_state(state: dict) -> dict:
        msgs = state.get("messages", [])
        if msgs:
            normalized = []
            for m in msgs:
                try:
                    normalized.append(convert_message_to_dict(m))
                except Exception:
                    if isinstance(m, dict):
                        normalized.append(m)
                    elif hasattr(m, "content"):
                        normalized.append({"role": getattr(m, "type", getattr(m, "role", "assistant")), "content": m.content})
            state["messages"] = normalized
        return state

    def invoke_with_default_thread(state, config=None, *args, **kwargs):
        cfg = config or {}
        configurable = cfg.get("configurable", {})
        if "thread_id" not in configurable:
            configurable = {**configurable, "thread_id": "test_thread"}
        cfg = {**cfg, "configurable": configurable}
        result = original_invoke(state, config=cfg, *args, **kwargs)
        return _normalize_state(result)

    # 包装 stream 以避免缺失 thread_id
    original_stream = wf.stream
    def stream_with_default_thread(state, config=None, *args, **kwargs):
        cfg = config or {}
        configurable = cfg.get("configurable", {})
        if "thread_id" not in configurable:
            configurable = {**configurable, "thread_id": "test_thread"}
        cfg = {**cfg, "configurable": configurable}
        return original_stream(state, config=cfg, *args, **kwargs)

    wf.invoke = invoke_with_default_thread  # type: ignore
    wf.stream = stream_with_default_thread  # type: ignore
    return wf


@pytest.fixture
def initial_state():
    """创建初始状态（不带消息）"""
    return create_initial_state("")


@pytest.fixture
def test_user_id():
    """测试用户 ID"""
    return TEST_USER_ID


@pytest.fixture
def clean_test_user(test_user_id):
    """返回隔离的测试用户 ID（占位清理逻辑）"""
    return test_user_id


@pytest.fixture
def crush_chat_manager():
    """创建空的 Crush 聊天管理器"""
    return create_crush_chat_manager()


# ============================================================
# Helper Functions (可在测试中直接导入使用)
# ============================================================

def run_workflow_turn(workflow, state: dict, user_message: str) -> dict:
    """
    执行一轮工作流
    
    Args:
        workflow: LangGraph 工作流实例
        state: 当前状态
        user_message: 用户消息
    
    Returns:
        更新后的状态
    """
    # 更新状态
    state["user_message"] = user_message
    state["messages"].append({"role": "user", "content": user_message})
    
    # 清理上一轮的临时数据
    state["debug_log"] = []
    state["inquiry_card"] = None
    state["pending_responses"] = []
    state["last_response_for_continuity"] = None
    
    # 执行工作流并规范化消息
    result = workflow.invoke(state, config={"configurable": {"thread_id": "test_thread"}})
    msgs = result.get("messages", [])
    if msgs:
        normalized = []
        for m in msgs:
            try:
                msg = convert_message_to_dict(m)
                role = msg.get("role")
                if role == "human":
                    msg["role"] = "user"
                elif role == "ai":
                    msg["role"] = "assistant"
                normalized.append(msg)
            except Exception:
                if isinstance(m, dict):
                    role = m.get("role")
                    if role == "human":
                        m["role"] = "user"
                    elif role == "ai":
                        m["role"] = "assistant"
                    normalized.append(m)
                elif hasattr(m, "content"):
                    role = getattr(m, "type", getattr(m, "role", "assistant"))
                    if role == "human":
                        role = "user"
                    elif role == "ai":
                        role = "assistant"
                    normalized.append({"role": role, "content": m.content})
        result["messages"] = normalized
    return result


def print_state_summary(state: dict, label: str = "State Summary"):
    """
    打印状态摘要（调试用）
    """
    print(f"\n{'='*60}")
    print(f"📊 {label}")
    print(f"{'='*60}")
    
    # 消息数
    messages = state.get("messages", [])
    print(f"📝 消息数: {len(messages)}")
    
    # Layer 1
    user_context = state.get("user_context", {})
    user_info = user_context.get("user_info", {})
    crush_info = user_context.get("crush_info", {})
    both_info = user_context.get("both_info", {})
    
    print(f"\n🟢 Layer 1 - 静态情报:")
    print(f"  - user_info.user_provide: {'✅' if user_info.get('user_provide') else '❌'}")
    print(f"  - crush_info.user_provide: {'✅' if crush_info.get('user_provide') else '❌'}")
    print(f"  - both_info.user_provide: {'✅' if both_info.get('user_provide') else '❌'}")
    
    # Layer 2
    print(f"\n🟣 Layer 2 - 工作上下文:")
    print(f"  - status_report: {'✅' if state.get('status_report') else '❌'}")
    print(f"  - action_plan: {'✅' if state.get('action_plan') else '❌'}")
    print(f"  - action_guides: {len(state.get('action_guides', []))} 个")
    
    # Layer 4
    history_archive = state.get("history_archive", {})
    print(f"\n🟡 Layer 4 - 历史归档:")
    print(f"  - status_history: {len(history_archive.get('status_history', []))} 条")
    print(f"  - guide_history: {len(history_archive.get('guide_history', []))} 条")
    print(f"  - conversation_archive: {len(history_archive.get('conversation_archive', []))} 条")
    
    # Crush Chat
    crush_chat = state.get("crush_chat_storage")
    if crush_chat:
        print(f"\n💜 Crush 聊天:")
        print(f"  - metadata: {crush_chat.get('metadata', {})}")
    
    print(f"{'='*60}\n")


def get_ai_response(state: dict) -> str:
    """
    从状态中提取 AI 回复
    """
    pending_responses = state.get("pending_responses", [])
    if pending_responses:
        return "\n\n".join([r.get("content", "") for r in pending_responses if r.get("content")])
    return ""


def create_test_state(user_message: str = "测试消息", **kwargs) -> dict:
    """
    创建测试状态
    
    Args:
        user_message: 用户消息
        **kwargs: 其他状态字段
    
    Returns:
        测试状态字典
    """
    state = create_initial_state(user_message)
    # 测试场景默认跳过 Onboarding，直达主流程
    if "onboarding_completed" not in kwargs:
        state["onboarding_completed"] = True
        state["route_to"] = "main_agent"
    state.update(kwargs)
    return state


def assert_state_valid(state: dict):
    """
    验证状态有效性
    
    Args:
        state: 状态字典
    
    Raises:
        AssertionError: 如果状态无效
    """
    assert "user_message" in state, "状态必须包含 user_message"
    assert "messages" in state, "状态必须包含 messages"
    assert isinstance(state["messages"], list), "messages 必须是列表"
    assert "layer1_memory" in state, "状态必须包含 layer1_memory"
    assert "layer2_memory" in state, "状态必须包含 layer2_memory"
    assert "layer3_memory" in state, "状态必须包含 layer3_memory"


def assert_agent_output(state: dict, expected_fields: list = None):
    """
    验证 Agent 输出
    
    Args:
        state: 状态字典
        expected_fields: 期望的字段列表
    
    Raises:
        AssertionError: 如果输出不符合预期
    """
    if expected_fields is None:
        expected_fields = []
    
    for field in expected_fields:
        assert field in state, f"状态必须包含 {field}"
    
    # 旧字段兼容：如果有 next_action，不做强校验


@pytest.fixture
def mock_llm_response():
    """
    Mock LLM 响应的 fixture
    
    使用方式：
        def test_xxx(mock_llm_response):
            mock_llm_response.return_value = "测试响应"
    """
    from unittest.mock import MagicMock
    return MagicMock()
