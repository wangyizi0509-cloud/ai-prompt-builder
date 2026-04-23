"""
Unit tests for _run_langchain_supervisor stream + side-channel events.

Tests that:
1. agent_graph.stream() is used instead of invoke()
2. Intermediate events are emitted via the writer
3. __interrupt__ is captured and returned in the result dict
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure agent_impl is on the path
AGENT_IMPL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(AGENT_IMPL_DIR))

if not os.getenv("LLM_PROVIDER"):
    os.environ["LLM_PROVIDER"] = "mock"

from langchain_core.messages import AIMessage, ToolMessage

from graph.nodes.main_agent import _run_langchain_supervisor


# ---------------------------------------------------------------------------
# Fake agent graph that yields a controlled sequence of stream chunks
# ---------------------------------------------------------------------------

def _make_fake_agent_graph():
    """Return a MagicMock whose .stream() yields a pre-defined sequence."""
    chunks = [
        # Step 1: agent produces a text AI message
        {"agent": {"messages": [AIMessage(content="好的，我先分析", id="msg1")]}},
        # Step 2: agent issues a tool call
        {
            "agent": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "ask_human", "id": "tc1", "args": {"questions": []}}],
                        id="msg2",
                    )
                ]
            }
        },
        # Step 3: tool result arrives
        {
            "tools": {
                "messages": [
                    ToolMessage(content='{"inquiry_card": {}}', tool_call_id="tc1", id="tm1")
                ]
            }
        },
        # Step 4: interrupt signal
        {"__interrupt__": [{"value": {"inquiry_card": {}}}]},
    ]

    fake_graph = MagicMock()
    fake_graph.stream.return_value = iter(chunks)
    return fake_graph


# ---------------------------------------------------------------------------
# Helper to build minimal args for _run_langchain_supervisor
# ---------------------------------------------------------------------------

def _build_supervisor_args(fake_graph, writer):
    llm = MagicMock()
    initial_messages = [AIMessage(content="用户消息", id="seed_msg")]
    return dict(
        llm=llm,
        tools=[],
        initial_messages=initial_messages,
        max_rounds=3,
        config=None,
        live_state=None,
        writer=writer,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunLangchainSupervisorStream:
    """Tests for the .stream()-based _run_langchain_supervisor."""

    def test_stream_called_not_invoke(self):
        """Verify agent_graph.stream() is called, not invoke()."""
        fake_graph = _make_fake_agent_graph()
        writer = MagicMock()

        with patch("graph.nodes.main_agent.create_agent", return_value=fake_graph):
            _run_langchain_supervisor(**_build_supervisor_args(fake_graph, writer))

        fake_graph.stream.assert_called_once()
        fake_graph.invoke.assert_not_called()

    def test_ai_message_event_emitted(self):
        """Writer receives an ai_message event for the text-only AIMessage."""
        fake_graph = _make_fake_agent_graph()
        writer = MagicMock()

        with patch("graph.nodes.main_agent.create_agent", return_value=fake_graph):
            _run_langchain_supervisor(**_build_supervisor_args(fake_graph, writer))

        calls = [c.args[0] for c in writer.call_args_list]
        ai_message_events = [c for c in calls if c.get("event_type") in ("ai_message", "ai_intermediate")]
        assert ai_message_events, "Expected at least one ai_message event"

    def test_tool_call_calling_event_emitted(self):
        """Writer receives a tool_call/calling event when AIMessage has tool_calls."""
        fake_graph = _make_fake_agent_graph()
        writer = MagicMock()

        with patch("graph.nodes.main_agent.create_agent", return_value=fake_graph):
            _run_langchain_supervisor(**_build_supervisor_args(fake_graph, writer))

        calls = [c.args[0] for c in writer.call_args_list]
        calling_events = [
            c for c in calls
            if c.get("event_type") == "tool_call" and c.get("status") in ("calling", "loading")
        ]
        assert calling_events, "Expected at least one tool_call/calling event"
        assert calling_events[0]["tool_name"] == "ask_human"

    def test_tool_done_event_emitted(self):
        """Writer receives a tool_call/done event for the ToolMessage."""
        fake_graph = _make_fake_agent_graph()
        writer = MagicMock()

        with patch("graph.nodes.main_agent.create_agent", return_value=fake_graph):
            _run_langchain_supervisor(**_build_supervisor_args(fake_graph, writer))

        calls = [c.args[0] for c in writer.call_args_list]
        done_events = [
            c for c in calls
            if c.get("event_type") == "tool_call" and c.get("status") == "done"
        ]
        assert done_events, "Expected at least one tool_call/done event"

    def test_interrupt_captured_in_result(self):
        """__interrupt__ chunk is captured and returned in the result dict."""
        fake_graph = _make_fake_agent_graph()
        writer = MagicMock()

        with patch("graph.nodes.main_agent.create_agent", return_value=fake_graph):
            out = _run_langchain_supervisor(**_build_supervisor_args(fake_graph, writer))

        assert "__interrupt__" in out, "Expected __interrupt__ in result"
        assert out["__interrupt__"] is not None

    def test_new_messages_contain_ai_and_tool_messages(self):
        """new_messages should include the AIMessage and ToolMessage produced during streaming."""
        fake_graph = _make_fake_agent_graph()
        writer = MagicMock()

        with patch("graph.nodes.main_agent.create_agent", return_value=fake_graph):
            out = _run_langchain_supervisor(**_build_supervisor_args(fake_graph, writer))

        new_msgs = out["new_messages"]
        assert any(isinstance(m, AIMessage) for m in new_msgs), "Expected AIMessage in new_messages"
        assert any(isinstance(m, ToolMessage) for m in new_msgs), "Expected ToolMessage in new_messages"

    def test_no_duplicate_initial_messages(self):
        """Initial messages should not appear twice in new_messages (id dedup)."""
        fake_graph = _make_fake_agent_graph()
        writer = MagicMock()

        with patch("graph.nodes.main_agent.create_agent", return_value=fake_graph):
            out = _run_langchain_supervisor(**_build_supervisor_args(fake_graph, writer))

        ids_in_new = [getattr(m, "id", None) for m in out["new_messages"]]
        assert "seed_msg" not in ids_in_new, "Initial message should not appear in new_messages"

    def test_writer_none_does_not_raise(self):
        """When writer=None, the function still runs without errors."""
        fake_graph = _make_fake_agent_graph()

        with patch("graph.nodes.main_agent.create_agent", return_value=fake_graph):
            out = _run_langchain_supervisor(**_build_supervisor_args(fake_graph, writer=None))

        assert "final" in out
        assert "new_messages" in out
