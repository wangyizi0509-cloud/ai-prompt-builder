# LangChain Agents + Subgraphs 子 agent 技术方案（建议版）

本文给出一个面向“子 agent 状态可持久化（尤其是 interrupt/resume 场景）”的重构方案：将 plan/status/guide 从“tool 里的子 agent runnable”升级为“带私有状态的子图（subgraph）”，父图在节点/工具内部调用子图，并原样透传 `config`，以共享同一 `thread_id` 的 checkpoint。

## 背景与问题

当前实现中，子 agent 以 tool 的形式被主 agent 调用，读取/写回的都是同一份 ParentState（通过 `state_patch` 合并）。这能保证产品态一致，但有一个天然缺陷：

- 子 agent 没有“私有可持久化的过程态”（例如 private messages / tool traces）
- 一旦子 agent 内部触发 `interrupt()`，恢复需要依赖“当时的对话痕迹/工具痕迹”才能正确续跑；如果这些痕迹被写进 ParentState.messages，会污染主对话；如果不写进 state，又无法在 checkpoint 中持久化

因此，引入“不同 schema 的子图”来承载子 agent 的私有过程态，是更干净的方式（LangGraph 官方支持：父图节点内部 invoke 子图、子图可采用完全不同的 state schema）。

## 设计目标

- 父图保持稳定：`router -> onboarding -> main_agent(create_agent) -> post_finalize`
- plan/status/guide 各自是一个子图（subgraph），子图内部跑一个 `create_agent`（tool-loop）
- 子图允许 `interrupt()`（例如 `ask_human`），并且中断/恢复时私有过程态可以被 checkpoint 持久化
- 父图与子图共享同一 thread：父图 invoke 子图时 `config` 原样透传
- 结果策略：父图只 merge 子图返回的 `state_patch`（面向 ParentState 的增量）；子图的 `private_messages` 仅用于“中断恢复/调试”，子图结束即清理

## 总体架构

### Parent Graph（保持现有主流程）

- `router`：输入归一化/风控/写入 `messages` 与 `layer*_memory`
- `onboarding`：保留子图（已存在）
- `main_agent`：Supervisor（`create_agent` 工具循环）
- `post_turn_finalize`：收尾/压缩/维护队列

关键变化：`main_agent` 不再直接“跑子 agent runnable”，而是通过 3 个工具去调用 3 个子图：

- `call_status_subgraph(...)`
- `call_plan_subgraph(...)`
- `call_guide_subgraph(...)`

工具本质上是“在 tool 内部 invoke 对应子图，并返回 state_patch 的 ToolResult”。

### Subgraphs（plan/status/guide 各自一套）

每个子图具备独立 schema（不和 ParentState 共享 keys），核心目的：

- 让子 agent 拥有自己的 `private_messages`（只用于子图内部）
- 在 `interrupt()` 发生时，子图的 state 会被 checkpoint 保存，恢复后能从 `private_messages` 继续推理与工具循环

子图内部可非常简化：一个 run 节点 + 一个 cleanup 节点。

## 状态模型（推荐）

### ParentState（产品态 + 主对话）

保持你现有字段即可（示意）：

- `messages`（主对话消息流）
- `layer2_memory` / `layer3_memory`（长期记忆）
- `pending_responses` / `inquiry_card`
- `runtime` / `tool_patch_log`

原则：ParentState 只承载“对用户可见/产品契约必须”的状态，不承载 plan/status/guide 的过程对话痕迹。

### SubState（子 agent 私有态）

建议最小化：

- `task_spec`: dict（父→子映射产物，子任务输入）
- `private_messages`: list（子 agent 自己的对话/工具痕迹；仅用于中断恢复，不回传父图）
- `final`: dict（可选：结构化最终结果，便于调试/测试）
- `state_patch`: dict（统一契约：对子图认为需要回写 ParentState 的增量）

## 关键机制说明

### 1) create_agent 如何嵌套（主/子都用 tool-loop）

事实约束：`create_agent(...)` 返回的是一个基于 LangGraph 的 agent runtime（图 / runnable），内部会做工具循环直到 stop condition。

因此可以按如下方式嵌套：

- 主 agent：父图 `main_agent` 节点里运行 `main_agent_runnable = create_agent(...)`
- 子 agent：子图的 `run` 节点里运行 `sub_agent_runnable = create_agent(...)`

子图 run 节点负责：

1. 把 `SubState.task_spec + SubState.private_messages` 转成 `create_agent` 期望的输入（通常就是 `{"messages": ...}`）
2. 执行 `sub_agent_runnable.invoke(agent_input, config=config)`（透传 config）
3. 从输出提取 `state_patch` / `final`，写回子图 state

### 2) 共享 thread 的调用链（中断持久化的关键）

父图节点（或工具）调用子图时必须：

```python
subgraph.invoke(sub_input, config=config)
```

只要 `config` 原样透传（其中包含 `configurable.thread_id` 等必要信息），并且运行环境启用了 checkpointer，那么：

- 子图内部触发 `interrupt()` 时，checkpoint 会以同一个 `thread_id` 写入
- 运行会向上返回 `__interrupt__`
- 下一次请求使用 `Command(resume=...)` + 同 `thread_id`，即可从子图中断点恢复继续执行

这意味着：不需要为每个 subagent 单独建 thread；共享 thread 就够了。

### 3) “过程态只用于中断恢复/调试，结束即清理”

子图的 `private_messages` 应当：

- 在“正常结束”后清空，避免长期膨胀
- 在“interrupt 暂停”时保留（因为下一次要靠它续跑）

实现方式：子图增加一个 `cleanup` 节点，只有在 run 节点正常返回且未中断时才会走到 cleanup。

## 子图示例代码（方案草图）

```python
from __future__ import annotations

from typing_extensions import TypedDict
from langgraph.graph.state import StateGraph, START, END
from langgraph.prebuilt import create_agent


class SubState(TypedDict, total=False):
    task_spec: dict
    private_messages: list
    final: dict
    state_patch: dict


sub_plan_agent = create_agent(
    model=...,
    tools=[...],   # 子 agent 白名单工具（含 ask_human -> interrupt）
    prompt=...,
)


def run_plan_agent(state: SubState, config) -> dict:
    agent_input = {
        "messages": (state.get("private_messages") or [])
        + [{"role": "user", "content": state["task_spec"]["instruction"]}],
    }

    out = sub_plan_agent.invoke(agent_input, config=config)

    patch = out.get("state_patch", {}) if isinstance(out, dict) else {}
    final = out.get("final") if isinstance(out, dict) else None

    # 关键：把子 agent 的 messages 回写到 private_messages，确保 interrupt 可恢复
    new_private_messages = out.get("messages") if isinstance(out, dict) else None

    update: dict = {"state_patch": patch, "final": final or {"raw": out}}
    if new_private_messages is not None:
        update["private_messages"] = new_private_messages
    return update


def cleanup_substate(state: SubState) -> dict:
    return {"private_messages": []}


builder = StateGraph(SubState)
builder.add_node("run", run_plan_agent)
builder.add_node("cleanup", cleanup_substate)
builder.add_edge(START, "run")
builder.add_edge("run", "cleanup")
builder.add_edge("cleanup", END)
plan_subgraph = builder.compile()
```

父图侧调用（以 tool 形式暴露给 main_agent）：

```python
def call_plan_subgraph(parent_state: dict, config) -> dict:
    sub_in: SubState = {
        "task_spec": {
            "instruction": "基于 layer2/layer3 给出行动计划 ...",
            "layer2": parent_state.get("layer2_memory", {}),
            "layer3": parent_state.get("layer3_memory", {}),
            "messages_tail": (parent_state.get("messages") or [])[-25:],
        },
        "private_messages": [],
    }

    sub_out: SubState = plan_subgraph.invoke(sub_in, config=config)
    return sub_out.get("state_patch", {}) or {}
```

## 对现有工程的落地改造点

### 代码形态建议（最小侵入）

- 保持 `graph/workflow.py` 主图形态不变
- 仍然用 `main_agent` 作为唯一 LLM 节点（Supervisor）
- 将“call_plan/status/guide”的实现从“直接跑子 agent runnable”替换为“invoke 子图”

### 目录结构建议

- `agent_impl/graph/subgraphs/plan.py`
- `agent_impl/graph/subgraphs/status.py`
- `agent_impl/graph/subgraphs/guide.py`

每个文件暴露一个 `compile_*_subgraph()` 或 `*_subgraph` runnable。

### 工具与结果契约

- 沿用 `ToolResult = { ok, output, state_patch }`
- `call_*_subgraph` 工具只返回 `state_patch`（让主 agent 统一 merge 到 ParentState）
- 子图内部如果需要直接调用写状态工具，也应产出 `state_patch`，最终由父图 merge

### interrupt/resume 协议

- 子图内部继续复用 `ask_human(inquiry_card=...)`（payload 沿用前端可渲染的 `inquiry_card`）
- API 侧继续使用 `Command(resume=resume_payload)` 恢复（同 thread_id）

## 风险与对策

1. 子图 invoke 的输出结构：`create_agent.invoke()` 的返回形态需在本仓库真实验证（是否返回 dict、是否包含 messages）。需要加一个最小集成测试覆盖 plan 子图的“正常结束 + interrupt/resume”两条路径。
2. `private_messages` 膨胀：必须只在子图中断等待时保留，结束就清理；并建议限制最大长度（例如只保留最近 N 条）。
3. 可观测性：子图过程不回传父图，调试时应提供一个开关（例如 `runtime.debug_subgraph_traces=true`）来选择性保留 `final/raw` 或子图事件。
4. 与 onboarding 子图叠加：父图已有 onboarding 子图，新增 plan/status/guide 子图时要保证 config 透传一致，避免 thread_id 丢失。

## 参考

- LangGraph Subgraphs：父图节点内部 invoke 子图、子图可使用不同 schema，并可保留私有 history（适用于多 agent 系统与私有消息历史隔离）。
