import os
import sys

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent_impl"))

from graph.nodes.main_agent import _run_langchain_supervisor


class ToolCallingFakeChatModel(BaseChatModel):
    def __init__(self, responses: list[AIMessage]):
        super().__init__()
        self._responses = list(responses)
        self._i = 0

    @property
    def _llm_type(self) -> str:
        return "tool_calling_fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self._i >= len(self._responses):
            msg = AIMessage(content="")
        else:
            msg = self._responses[self._i]
        self._i += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])


def test_create_agent_tool_loop_collects_patches_and_tool_messages():
    def my_tool(x: str) -> dict:
        return {"output": f"echo:{x}", "state_patch": {"tool_ran": True, "x": x}}

    my_tool_struct = StructuredTool.from_function(func=my_tool, name="my_tool", description="test")

    first = AIMessage(content="", tool_calls=[{"name": "my_tool", "args": {"x": "hello"}, "id": "call_1"}])
    second = AIMessage(content="done")
    llm = ToolCallingFakeChatModel([first, second])

    result = _run_langchain_supervisor(
        llm=llm,
        tools=[my_tool_struct],
        initial_messages=[HumanMessage(content="start")],
        max_rounds=5,
    )

    assert result["patches"] == [{"tool_ran": True, "x": "hello"}]
    assert result["final"].content == "done"

    tool_messages = [m for m in result["new_messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert tool_messages[0].content == "echo:hello"
    assert tool_messages[0].tool_call_id == "call_1"

