#!/usr/bin/env python3
"""
复现“复杂链路真实 API 调用”并导出完整 prompt trace（写入项目根目录）。

约束：
- 不打印/不泄露任何 .env 内容或 API key
- trace 文档必须写入项目根目录（不写到 agent_impl/）
"""

from __future__ import annotations

import os
import sys
import json
import datetime as dt
from dataclasses import dataclass, asdict
from typing import Any, Optional


ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
AGENT_DIR = os.path.join(ROOT_DIR, "agent_impl")


TURN1 = (
    "我现在就想要一个可执行的行动方案，但我故意不给背景信息。"
    "你必须先用提问技能问我关键问题（以 inquiry_card 的形式），我答完后你再给我行动指南。"
)

TURN2 = (
    "补充信息：男，25，北京。对方：女同事，认识3个月。目标：今晚发朋友圈让她更想互动，并引出她主动私聊。"
    "现状：她会回但不太主动。限制：不油、不暴露需求感。现在请不要再问了，直接给我行动指南（需要的话就 call_guide）。"
)


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"_repr": repr(obj)}, indent=2, ensure_ascii=False)


def _tool_name(t: Any) -> str:
    # langchain tools 通常有 name 属性；否则退化为函数名/类名
    name = getattr(t, "name", None)
    if isinstance(name, str) and name:
        return name
    fn = getattr(t, "__name__", None)
    if isinstance(fn, str) and fn:
        return fn
    return t.__class__.__name__


@dataclass
class InvokeRecord:
    idx: int
    agent: str
    model: str
    provider: str
    bound_tools: list[str]
    response_tool_calls: list[dict]
    prompt: str


class TracedLLM:
    """
    最薄的 LLM 包装器：
    - 捕获每次 invoke 的 prompt
    - 捕获 bind_tools 的工具名（用于 trace）
    """

    def __init__(self, llm: Any, *, agent: str, records: list[InvokeRecord], bound_tools: Optional[list[str]] = None):
        self._llm = llm
        self._agent = agent
        self._records = records
        self._bound_tools = bound_tools or []

    def bind_tools(self, tools: list[Any], *args: Any, **kwargs: Any) -> "TracedLLM":
        bound = self._llm.bind_tools(tools, *args, **kwargs)
        names = [_tool_name(t) for t in (tools or [])]
        return TracedLLM(bound, agent=self._agent, records=self._records, bound_tools=names)

    def invoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        # prompt 预期是 str；但也兼容其它类型（转 str 记录）
        prompt_text = prompt if isinstance(prompt, str) else str(prompt)

        resp = self._llm.invoke(prompt, *args, **kwargs)

        # tool_calls 兼容（LangChain AIMessage）
        tool_calls = getattr(resp, "tool_calls", None) or []
        if isinstance(tool_calls, list):
            tool_calls_norm = []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tool_calls_norm.append(tc)
                else:
                    tool_calls_norm.append({"_repr": repr(tc)})
        else:
            tool_calls_norm = [{"_repr": repr(tool_calls)}]

        model = getattr(self._llm, "model_name", None) or getattr(self._llm, "model", "") or ""
        provider = os.getenv("LLM_PROVIDER", "") or ""

        rec = InvokeRecord(
            idx=len(self._records) + 1,
            agent=self._agent,
            model=str(model),
            provider=str(provider),
            bound_tools=list(self._bound_tools),
            response_tool_calls=tool_calls_norm,
            prompt=prompt_text,
        )
        self._records.append(rec)
        return resp

    def __getattr__(self, item: str) -> Any:
        return getattr(self._llm, item)


def _patch_get_llm(records: list[InvokeRecord]) -> None:
    """
    把各 node 模块里 `from config import get_llm` 的引用替换成带 trace 的版本。
    这样无需改业务代码即可捕获 prompt。
    """

    # 延迟 import，确保 sys.path 已指向 agent_impl
    from config import get_llm as real_get_llm  # type: ignore

    def make(agent_name: str):
        def _get_llm(temperature: float = 0.7):
            return TracedLLM(real_get_llm(temperature=temperature), agent=agent_name, records=records)
        return _get_llm

    # patch nodes
    from graph.nodes import main_agent as mod_main  # type: ignore
    from graph.nodes import status_agent as mod_status  # type: ignore
    from graph.nodes import plan_agent as mod_plan  # type: ignore
    from graph.nodes import guide_agent as mod_guide  # type: ignore
    from graph.nodes import organize_agent as mod_org  # type: ignore

    mod_main.get_llm = make("main_agent")  # type: ignore[attr-defined]
    mod_status.get_llm = make("status_agent")  # type: ignore[attr-defined]
    mod_plan.get_llm = make("plan_agent")  # type: ignore[attr-defined]
    mod_guide.get_llm = make("guide_agent")  # type: ignore[attr-defined]
    mod_org.get_llm = make("organize_agent")  # type: ignore[attr-defined]

    # onboarding 也可能触发（保险起见）
    try:
        from onboarding import onboarding_agent as mod_onb  # type: ignore
        mod_onb.get_llm = make("onboarding_agent")  # type: ignore[attr-defined]
    except Exception:
        pass


def _run_turn(workflow: Any, state: dict, user_message: str, *, thread_id: str) -> dict:
    # 更新状态
    state["user_message"] = user_message
    state["messages"] = (state.get("messages", []) or []) + [{"role": "user", "content": user_message}]

    # 清理上一轮临时字段（避免污染）
    state["debug_log"] = []
    state["inquiry_card"] = None
    state["pending_questions"] = []
    state["pending_responses"] = []
    state["last_response_for_continuity"] = None

    return workflow.invoke(state, config={"configurable": {"thread_id": thread_id}})


def main() -> int:
    # 让 agent_impl 作为 import root
    sys.path.insert(0, AGENT_DIR)

    # 显式加载 agent_impl/.env（不打印内容）
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(AGENT_DIR, ".env"))

    records: list[InvokeRecord] = []
    _patch_get_llm(records)

    from graph.workflow import get_workflow  # type: ignore
    from graph.state import create_initial_state  # type: ignore

    workflow = get_workflow()

    # 固定 thread_id，确保 memory/checkpointer 行为一致
    thread_id = f"complex_real_api_trace_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Turn 1
    state = create_initial_state(TURN1)
    # 测试/调试默认跳过 onboarding，直达主流程
    state["onboarding_completed"] = True
    state["route_to"] = "main_agent"
    result1 = workflow.invoke(state, config={"configurable": {"thread_id": thread_id}})

    # Turn 2
    result2 = _run_turn(workflow, result1, TURN2, thread_id=thread_id)

    # 关键检查：prompt 中不应该再出现 <tool_output>
    tool_output_hits = [r.idx for r in records if "<tool_output>" in r.prompt]

    out_path = os.path.join(
        ROOT_DIR,
        f"prompt_trace_complex_case_real_api_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# 复杂链路 Prompt Trace（真实 API + 工具调用 + 路由到 Guide Agent）\n\n")
        f.write(f"生成时间：{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("说明：包含本次链路中每一次 `llm.invoke(prompt)` 的完整 Prompt，以及工具调用与关键状态摘要。\n\n")

        f.write("## 用户两轮输入\n\n")
        f.write(f"- Turn1: {TURN1}\n\n")
        f.write(f"- Turn2: {TURN2}\n\n")

        f.write("## 关键检查（本次关注点）\n\n")
        if tool_output_hits:
            f.write(f"- ❌ 发现 `<tool_output>` 出现在 Prompt 中：Invoke {tool_output_hits}\n")
        else:
            f.write("- ✅ 本次所有 Prompt 中均未出现 `<tool_output>`（符合“tool 输出不进历史”预期）\n")
        f.write("\n")

        f.write("## Prompt 捕获（按时间顺序）\n\n---\n\n")
        for rec in records:
            f.write(f"### Invoke {rec.idx}: {rec.agent}\n\n")
            f.write(f"- provider: {rec.provider}\n\n")
            f.write(f"- model: {rec.model}\n\n")
            f.write(f"- bound_tools: {', '.join(rec.bound_tools) if rec.bound_tools else '无'}\n\n")
            if rec.response_tool_calls:
                # 只记录调用名 + id，避免臃肿
                compact = []
                for tc in rec.response_tool_calls:
                    if isinstance(tc, dict):
                        compact.append({"name": tc.get("name"), "id": tc.get("id")})
                    else:
                        compact.append(tc)
                f.write(f"- response_tool_calls: {_safe_json(compact)}\n\n")
            else:
                f.write("- response_tool_calls: []\n\n")

            f.write("完整 Prompt：\n\n")
            f.write("```\n")
            f.write(rec.prompt)
            if not rec.prompt.endswith("\n"):
                f.write("\n")
            f.write("```\n\n---\n\n")

        f.write("## 关键状态摘要（仅供核对）\n\n")
        # 这里不要输出任何环境变量；只输出 state 的关键字段
        snap = {
            "turn1": {
                "next_action": result1.get("next_action"),
                "current_agent": result1.get("current_agent"),
                "agent_resume_point": result1.get("agent_resume_point"),
                "pending_questions": result1.get("pending_questions", []),
            },
            "turn2": {
                "next_action": result2.get("next_action"),
                "current_agent": result2.get("current_agent"),
                "agent_resume_point": result2.get("agent_resume_point"),
                "pending_questions": result2.get("pending_questions", []),
            },
        }
        f.write("```json\n")
        f.write(_safe_json(snap))
        f.write("\n```\n")

    # 控制台只打印输出路径（不泄露敏感信息）
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())








