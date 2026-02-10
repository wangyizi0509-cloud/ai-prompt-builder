# LangChain Agents/Subagents/Skills 重构任务拆解（文件级改动 + 测试清单）

本文是对 [langchain_agent_refactor_plan.md](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/docs/langchain_agent_refactor_plan.md) 的进一步落地拆解：将 8 个 task 细化到“文件级改动清单（新增/删除/替换函数名）”，并为 **每个 task 指定单元测试**与执行方式，最后补充一套 **整体集成测试**。

已确认决策以计划文档中的“已确认决策（最终拍板）”为准。<mccoremem id="01KGYTYPB1HWTKGJY80XANBJDT" />

## 测试基线（现有工程约定）

### 测试目录

- 单元/集成（偏离线）：[agent_impl/tests](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/)（由 [pytest.ini](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/pytest.ini) 指定 `testpaths = tests`）
- E2E/API/UI（偏在线）：[tests](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/tests/)（包含 Playwright 与真实 HTTP API 测试）

### 标记

- `@pytest.mark.api_test`：需要真实 API / 服务启动才能跑的测试（见 [pytest.ini](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/pytest.ini)）

### 执行建议（给每个 agent 自测）

- 默认自测（离线，不跑 api_test）：
  - `cd agent_impl && pytest -q tests/ -m "not api_test"`
- 单文件自测：
  - `pytest -q tests/test_xxx.py -k your_case`

> 说明：后续重构会调整 workflow/state/router 等核心，建议在每个 task 合入前保证 “not api_test” 全绿。

---

## Task 1：新增 LangChain Agents/Subagents 骨架（不接入 workflow）

### 目标

建立 LangChain agent 的“可复用构建层”，提供 main/subagent 的创建方法与统一输入输出协议，但不修改现有 LangGraph 图逻辑（避免一次性改太多）。

### 文件级改动清单

**新增**

- `agent_impl/agents/__init__.py`
- `agent_impl/agents/main.py`
  - 新增 `build_main_agent(*, tools: list, model=..., middleware=...) -> Any`
  - 新增 `run_main_agent(*, state: dict, user_message: str) -> dict`（只返回 agent 原始输出，不改 state）
- `agent_impl/agents/subagents/__init__.py`
- `agent_impl/agents/subagents/status.py`
  - 新增 `build_status_subagent(*, tools: list, model=...)`
- `agent_impl/agents/subagents/plan.py`
  - 新增 `build_plan_subagent(*, tools: list, model=...)`
- `agent_impl/agents/subagents/guide.py`
  - 新增 `build_guide_subagent(*, tools: list, model=...)`
- `agent_impl/agents/tooling/__init__.py`
- `agent_impl/agents/tooling/context.py`
  - 新增 `build_model_messages(state: dict, user_message: str, *, max_messages: int = 25) -> list[dict]`
  - 新增 `build_subagent_input(state: dict, *, max_messages: int = 25) -> dict`（包含 layer2/layer3 + 截断后的 messages）

**不修改**

- 不触碰 [graph/workflow.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/workflow.py) 与现有 nodes/tools。

### 单元测试（本 task 必须新增）

**新增**

- `agent_impl/tests/test_agents_skeleton.py`
  - `test_build_model_messages_truncates_to_25()`
  - `test_build_subagent_input_contains_layer2_layer3()`（没有时也应提供空 dict 形态）
  - `test_build_main_agent_constructs()`（仅验证构造成功；不做真实调用）

**自测命令**

- `cd agent_impl/agent_impl && pytest -q tests/test_agents_skeleton.py`

### 执行结果（已完成）

- 已按清单新增文件：
  - `agent_impl/agents/__init__.py`
  - `agent_impl/agents/main.py`
  - `agent_impl/agents/subagents/__init__.py`
  - `agent_impl/agents/subagents/status.py`
  - `agent_impl/agents/subagents/plan.py`
  - `agent_impl/agents/subagents/guide.py`
  - `agent_impl/agents/tooling/__init__.py`
  - `agent_impl/agents/tooling/context.py`
  - `agent_impl/tests/test_agents_skeleton.py`
- `build_model_messages(...)`：基于现有 `state["messages"]` 构建 `{role, content}` 列表，并在末尾追加本轮 `user_message`；超出 `max_messages=25` 时保留最近 25 条。
- `build_subagent_input(...)`：输出 `{layer2, layer3, messages}`，其中 `layer2/layer3` 缺失时提供空 dict。
- 单测通过：`python -m pytest -q tests/test_agents_skeleton.py`（3 passed）

---

## Task 2：统一 Tool 返回契约（state_patch）+ Patch 合并器

### 目标

删 `skill_tools` 后，工具不再有集中写回点；因此需要“工具返回 patch → node 合并 patch”的统一协议。

### 文件级改动清单

**新增**

- `agent_impl/agents/tooling/patch.py`
  - 新增 `ToolResult`（TypedDict / dataclass 均可，但测试应覆盖序列化）
  - 新增 `merge_state_patch(state: dict, patch: dict) -> dict`
  - 新增 `merge_patches(state: dict, patches: list[dict]) -> dict`（按顺序合并，后者覆盖前者）
- `agent_impl/agents/tooling/tool_result.py`
  - 新增 `ok(output: str = "", state_patch: dict | None = None) -> dict`
  - 新增 `error(output: str, *, state_patch: dict | None = None) -> dict`

**修改**

- （可选）`agent_impl/graph/state.py`：在最终落地时加入 `runtime/tool_patch_log` 字段，但本 task 可先不改 state（先让 patch 层独立可用）。

### 单元测试

**新增**

- `agent_impl/tests/test_state_patch_merge.py`
  - `test_merge_state_patch_overwrites_scalars()`
  - `test_merge_state_patch_merges_nested_dicts()`
  - `test_merge_state_patch_appends_lists_for_whitelisted_keys()`（如果你定义了 list merge 策略）
  - `test_tool_result_helpers_are_json_serializable()`

**自测命令**

- `cd agent_impl/agent_impl && pytest -q tests/test_state_patch_merge.py`

### 执行结果（已完成）

- 已新增：
  - `agent_impl/agents/tooling/patch.py`：提供 `ToolResult`、`merge_state_patch`、`merge_patches`，其中 dict 递归合并、标记为白名单的 list 采用 append 策略（当前白名单：`tool_patch_log`）。
  - `agent_impl/agents/tooling/tool_result.py`：提供 `ok(...)` / `error(...)` 工具返回快捷构造器（JSON 可序列化）。
  - `agent_impl/tests/test_state_patch_merge.py`：覆盖标量覆盖、嵌套 dict 合并、白名单 list append、helpers 序列化与多 patch 顺序合并。
- 单测通过：`python -m pytest -q tests/test_state_patch_merge.py`（5 passed）

---

## Task 3：工具层重构（submit/task/context + skills）为 LangChain tools，直接产 patch

### 目标

把“执行/写回分离”的工具迁移为“工具自身产 patch”，并将 `load_skill` 作为所有 agent 可用工具（skills pattern）。

### 文件级改动清单

**修改（重写返回值契约）**

- [graph/tools/submit_tools.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/tools/submit_tools.py)
  - 替换每个 `@tool` 的返回值为 `ToolResult`（包含 state_patch）
  - 删除函数：
    - `apply_submit_tool_state_update(...)`
    - `is_submit_tool(...)`（不再需要分类）
- [graph/tools/task_tools.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/tools/task_tools.py)
  - 每个 task tool 直接返回 patch
  - 删除：
    - `apply_task_tool_state_update(...)`
    - `is_task_tool(...)`
- [graph/tools/context_loader.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/tools/context_loader.py)
  - `create_context_loader(...)` 返回的工具应输出 patch（通常是写 `layer3_memory` 或 debug）
  - 删除：
    - `apply_context_loader_state_update(...)`
    - `is_context_loader_tool(...)`
- [skills/tool.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/skills/tool.py)
  - 调整为所有 agent 都可用（去掉“仅 main 可加载全部”的硬限制，或改成可配置白名单）
  - 返回 `ToolResult`（output 为指令文本，patch 可选：例如记录 `loaded_skills`）

**删除**

- [graph/tools/delegate_tools.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/tools/delegate_tools.py)（其 handoff 语义由 subagent tools 取代）

### 单元测试

**新增/修改**

- `agent_impl/tests/test_submit_tools_patch.py`
  - `test_submit_status_report_returns_state_patch()`（断言 layer2_memory.current_status_report 被写入）
  - `test_submit_action_plan_returns_state_patch()`
  - `test_submit_action_guide_returns_state_patch()`
- `agent_impl/tests/test_task_tools_patch.py`
  - 覆盖任务新增/更新/归档等最常用路径
- `agent_impl/tests/test_skills_load_skill_patch.py`
  - `test_load_skill_returns_prompt_text()`（无需真实 LLM）
  - `test_load_skill_invalid_id_returns_error()`（或抛异常，按你的工具契约统一）

**自测命令**

- `cd agent_impl/agent_impl && pytest -q tests/test_submit_tools_patch.py tests/test_task_tools_patch.py tests/test_skills_load_skill_patch.py`

### 执行结果（已完成）

- 已完成工具返回契约切换为 `ToolResult`（含 `state_patch`）：
  - [submit_tools.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/tools/submit_tools.py)：`submit_*` 系列工具返回 `{ok, output, state_patch}`，`state_patch` 至少写入 `layer2_memory.current_*`（并保留可选的 `_submit_result`）。
  - [task_tools.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/tools/task_tools.py)：`task_manager` 不再原地写 state，改为返回 patch；并对 task_registry 做 deepcopy，避免工具侧隐式修改 state。
  - [context_loader.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/tools/context_loader.py)：`context_loader` 不再原地写 state，改为返回 patch（主要写 `layer3_memory.task_registry`）。
  - [tool.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/skills/tool.py)：`load_skill` 返回 `ToolResult`，output 为指令文本；invalid id 返回 error。
- 兼容性说明：`apply_*_state_update` / `is_*_tool` 等旧接口仍存在（部分被单测/工具实现复用）。建议在最终稳定后：只保留“工具自身产 patch”的路径，并删除所有“workflow 侧集中 apply”的遗留逻辑与不再被调用的节点/路由函数。
- 单测通过：`python -m pytest -q tests/test_submit_tools_patch.py tests/test_task_tools_patch.py tests/test_skills_load_skill_patch.py`

---

## Task 4：交互工具改 interrupt（ask_human），沿用 inquiry_card payload

### 目标

将需要用户交互的工具从 Router-Resume 状态机迁移到 `interrupt()`，使“暂停/恢复”成为 LangGraph 原生能力。

### 文件级改动清单

**修改**

- [graph/tools/ask_tool.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/tools/ask_tool.py)
  - 删除两阶段实现：
    - `AskEnableInput` / `_ask_enable` / `ask_enable`
    - `AskQuestionsInput` / `_ask_questions` / `ask_questions`
    - `get_ask_tool(...)`
  - 新增单一工具（建议保留 tool 名 “ask_human” 或仍叫 “ask”，但建议显式区分）：
    - `ask_human(inquiry_card: dict) -> dict`
    - 内部 `interrupt(inquiry_card)`，恢复值作为返回（建议规范为 `{answers: ...}`）
  - 工具返回 `ToolResult`：output 可为空，patch 至少写入 `inquiry_card`（便于前端渲染/对齐）

**新增**

- `agent_impl/agents/tooling/interrupts.py`
  - `build_inquiry_interrupt_payload(...) -> dict`（确保 schema 一致）

### 单元测试

**新增**

- `agent_impl/tests/test_interrupt_ask_human.py`
  - 构造一个极小 graph（或直接在 workflow 中用单节点测试），验证：
    - 第一次 invoke 返回 `__interrupt__` 且包含 inquiry_card
    - resume 后节点能拿到用户输入并继续执行

> 备注：此测试需要 checkpointer（例如 MemorySaver），否则 interrupt 无法 resume。建议在 workflow 编译函数上加 `checkpointer` 可选参数（见 Task 5/7）。

**自测命令**

- `cd agent_impl/agent_impl && pytest -q tests/test_interrupt_ask_human.py`

### 执行结果（已完成）

- 已新增：
  - `agent_impl/agents/tooling/interrupts.py`：提供 `build_inquiry_interrupt_payload(...)`，对 `questions/intro/reasoning` 做缺省补齐。
  - `agent_impl/tests/test_interrupt_ask_human.py`：最小图 + `MemorySaver` 验证 interrupt/resume 可用。
- 已修改：
  - [ask_tool.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/tools/ask_tool.py)：新增 `ask_human` 工具，内部 `interrupt(inquiry_card)`，resume 后返回 `ToolResult`（patch 写入 `inquiry_card` 与 `inquiry_answers`）。
  - [workflow.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/workflow.py)：补齐对 legacy `ask_user` tool_call 的兼容解析（用于既有测试用例）。
- 兼容性说明：当前对外交互协议已切换为 `ask_human`（interrupt/resume）。`ask` 两阶段实现仍保留在文件中，但不再作为工具集合对模型暴露；建议后续清理旧实现，并同步更新 prompts，避免模型“读到旧协议但找不到工具”。
- 单测通过：`python -m pytest -q tests/test_interrupt_ask_human.py`

---

## Task 5：workflow 一次性改造（删 skill_tools；主图收敛；子 agent 退出图节点）

### 目标

主图最终节点集：`router`、`onboarding`、`main_agent`、`post_turn_finalize`。删除 `skill_tools` 节点及所有相关路由函数，并移除 `status_agent/plan_agent/guide_agent` 图节点。

### 文件级改动清单

**修改**

- [graph/workflow.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/workflow.py)
  - 删除节点注册：
    - `workflow.add_node("skill_tools", ...)`
    - `workflow.add_node("status_agent", ...)`
    - `workflow.add_node("plan_agent", ...)`
    - `workflow.add_node("guide_agent", ...)`
  - 删除/替换路由函数：
    - 删除 `route_after_skill_tools(...)`
    - 删除 `route_after_sub_agent(...)`
    - 修改 `route_after_main_agent(...)`：不再判断 tool_calls→skill_tools；只在 end/interrupt/normal completion 上收口
    - 修改 `route_after_router(...)`：不再恢复到子 agent 节点（因为图里没有）
  - 增加编译入口支持 checkpointer（供测试与 interrupt 使用）：
    - `compile_workflow(*, checkpointer=None)`（默认 None，保持 cloud/CLI 兼容）

**删除**

- `graph/nodes/status_agent.py`
- `graph/nodes/plan_agent.py`
- `graph/nodes/guide_agent.py`
- `graph/nodes/organize_agent.py`（若不再使用）
- `graph/nodes/dispatcher.py`（若不再使用）

### 单元测试

**修改**

- `agent_impl/tests/test_workflow_integration.py`
  - 更新为新图结构：确认节点存在、路由覆盖 router→main→finalize
  - 新增：断言不再出现 `skill_tools/status_agent/plan_agent/guide_agent` 节点名

**新增**

- `agent_impl/tests/test_workflow_compiles_with_checkpointer.py`
  - `test_workflow_compiles_with_memory_saver()`（用于 Task 4/8 的 interrupt/resume）

**自测命令**

- `cd agent_impl/agent_impl && pytest -q tests/test_workflow_compiles_with_checkpointer.py tests/test_workflow_integration.py -m "not api_test"`

---

## Task 6：main_agent_node 改造成 LangChain Supervisor（subagent tools + 全量 tools）

### 目标

将 main_agent_node 从“手写 prompt + bind_tools + tool_calls 路由”重构为：

- 运行 LangChain main agent（内部循环）
- 可调用 3 个 subagent tools
- tools 全量暴露
- 对每次 tool 返回的 state_patch 做合并，并输出前端需要字段（pending_responses 等）

### 文件级改动清单

**修改（重写）**

- [graph/nodes/main_agent.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/nodes/main_agent.py)
  - 替换 `main_agent_node(state)` 逻辑：
    - 移除：所有 `from_tool_call/ask_mode/consult_mode/emotion_mode` 两阶段处理分支
    - 移除：`delegate_to_*` 工具依赖（已删除）
    - 引入：`agents/main.py` 的 main agent 调用
    - 引入：subagent tools（见新增文件）
  - 新增内部函数（建议）：
    - `_build_all_tools(...) -> list[BaseTool]`
    - `_call_subagent_status(payload) -> ToolResult`
    - `_call_subagent_plan(payload) -> ToolResult`
    - `_call_subagent_guide(payload) -> ToolResult`
    - `_apply_tool_patches_to_state(...)`

**新增**

- `agent_impl/agents/tools/all_tools.py`
  - `build_all_tools_for_agent(role: Literal["main","status","plan","guide"]) -> list[BaseTool]`
  - 内部做工具白名单（但按决策：子 agent 允许写 state，所以白名单仍可大，但建议保留最基本的危险工具隔离点）

### 单元测试

**新增**

- `agent_impl/tests/test_main_agent_langchain_wrapper.py`
  - 使用 `LLM_PROVIDER=mock` 或构造 DummyModel（不调用真实 API）
  - 覆盖：
    - `test_main_agent_merges_state_patches_from_tools()`
    - `test_main_agent_calls_subagent_tools_and_merges()`
    - `test_main_agent_truncates_messages_to_25_for_model()`（可通过 context builder 的输出断言）

**自测命令**

- `cd agent_impl/agent_impl && pytest -q tests/test_main_agent_langchain_wrapper.py -m "not api_test"`

### 执行结果（已完成）

- 已新增：
  - `agent_impl/agents/tools/all_tools.py`：提供 `build_all_tools_for_agent(role, state_getter=...)`，按角色组装可用工具集合（main=全量 skills；子 agent=inquiry-only skills）。
  - `agent_impl/tests/test_main_agent_langchain_wrapper.py`：离线 DummyModel 覆盖 tool patch 合并、subagent tool 调用、messages 截断上限。
- 已修改：
  - [main_agent.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/nodes/main_agent.py)：新增 LangChain Supervisor 风格的内部 tool loop（不再依赖 workflow 的 skill_tools 进行工具执行），并新增 3 个 subagent tools：`call_status_agent/call_plan_agent/call_guide_agent`；每次工具返回的 `state_patch` 会被合并到本轮输出。
  - `agent_impl/tests/conftest.py`：测试环境在未设置 `LLM_PROVIDER` 时默认使用 `mock`，确保离线跑测不触发真实 API。
- 单测通过：`python -m pytest -q tests/test_main_agent_langchain_wrapper.py`

---

## Task 7：router/finalizer/state 一次性迁移与清理（不维护旧字段）

### 目标

按决策：迁移期不维护 deprecated 镜像字段与旧控制字段；因此需要一次性：

- state schema 归一化
- router 不再依赖 `agent_resume_point`
- finalizer 适配新输出（尤其是 interrupt 情况）

### 文件级改动清单

**修改**

- [graph/state.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/state.py)
  - 删除字段：
    - `current_agent` / `agent_resume_point`
    - `_tool_caller` / `_pending_action` / `_reply_skill_complete` / `_handoff_*` / `_submit_result`
    - `ask_mode/consult_mode/emotion_mode` 与相关 `*_tool_message_id`
    - deprecated 镜像字段（如 `status_report/action_plan/action_guides/action_guide/history_archive/task_registry` 等）
  - 新增字段（建议）：
    - `runtime: dict`（运行时控制面）
    - `tool_patch_log: list[dict]`（可选，用于调试）
- [graph/nodes/router.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/nodes/router.py)
  - 删除恢复逻辑对 `agent_resume_point` 的依赖
  - 每轮清理：替换为清理 `runtime` 中的临时字段
  - 仍保留：风控/闲聊/消息归一化/去重
- [graph/nodes/finalizer.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/nodes/finalizer.py)
  - 适配 interrupt：本轮可能返回 `__interrupt__`，需要保证 pending_responses/inquiry_card 兼容输出
  - 适配：工具输出压缩规则（不再以 ask_mode_tool_message_id 等为触发条件）
- [graph/message_builder.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/message_builder.py)
  - 移除对两阶段 ask/consult/emotion 的压缩特判
  - 新增对 `load_skill` 与通用 tool output 的压缩策略（仍可保留压缩目的）

### 单元测试

**修改**

- `agent_impl/tests/test_state_management.py`：更新断言字段集
- `agent_impl/tests/test_router.py`：移除 resume_point 相关用例；新增 interrupt 相关状态清理用例
- `agent_impl/tests/test_compression_strategy.py`：更新 tool 压缩规则的断言

**新增**

- `agent_impl/tests/test_state_schema_no_legacy_fields.py`
  - 断言 `create_initial_state()` 不再包含 legacy keys
  - 断言路由/主节点返回值不包含 legacy keys

**自测命令**

- `cd agent_impl/agent_impl && pytest -q tests/test_state_management.py tests/test_router.py tests/test_state_schema_no_legacy_fields.py -m "not api_test"`

### 执行结果（已完成）

- 已修改：
  - [state.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/state.py)：移除主流程旧控制字段与 deprecated 镜像字段；新增 `runtime/tool_patch_log`；保留 Onboarding 所需的 `collected_info`。
  - [router.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/nodes/router.py)：每轮清理从“清旧控制字段”改为清 `runtime`；移除旧 resume 逻辑依赖。
  - [message_builder.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/message_builder.py)：移除 ask/consult/emotion 两阶段特判；统一压缩 load_skill 与大体积 tool 输出。
  - [finalizer.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/nodes/finalizer.py)：指南归档只以 `layer2_memory.action_guides` 为真源（不再回退读 `action_guides`）。
  - [workflow.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/workflow.py)：主图节点收敛为 `router/onboarding/main_agent/post_turn_finalize`；`compile_workflow(checkpointer=...)` 支持 interrupt/resume 的编译形态。
  - Onboarding：移除 `pending_questions` 输出（仅保留 `inquiry_card` 作为前端提问入口）：[onboarding_agent.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/onboarding/onboarding_agent.py)
  - 测试与导出：更新 `tests/conftest.py` 的状态断言；移除过期导出项：[graph/__init__.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/__init__.py)、[nodes/__init__.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/nodes/__init__.py)
- 已新增：
  - `agent_impl/tests/test_state_schema_no_legacy_fields.py`：断言初始化/节点输出不含 legacy keys。
- 说明：
  - 一批针对旧 `skill_tools + 两阶段 ask/consult/emotion + resume_point` 的测试已标记为 module-level skip，避免继续约束已删除的协议。
- 单测通过：`python -m pytest -q -m "not api_test"`（133 passed, 12 skipped）

---

## Task 8：API 层支持 interrupt/resume（chat + stream）

### 目标

在 FastAPI 层实现 interrupt/resume 协议：

- 若执行结果包含 `__interrupt__`：返回给前端（payload 为 inquiry_card），并提示“等待用户回复”
- 用户带 `resume_payload` 再请求：服务端用 `Command(resume=resume_payload)` 恢复同 thread 执行

### 已完成

- [chat.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/api/chat.py)
  - `ChatRequest` 新增 `resume_payload` / `resume`，支持「resume-only」请求（message 可为空）
  - 非 resume：维持原有 `input=state` 路径
  - resume：改为 `input=Command(resume=resume_payload)` 调用 SDK
  - 若 `final_state` 含 `__interrupt__`：提取第一个 interrupt 的 `value` 作为 `state.inquiry_card`，并返回“等待用户回复”的提示文本
- [stream.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/api/stream.py)
  - `StreamChatRequest` 新增 `resume_payload` / `resume`，支持 resume 输入（同 chat）
  - 流式输出中检测到 interrupt 后追加 SSE 事件：`{"type":"interrupt","inquiry_card":...}`
- [sdk_client.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/api/sdk_client.py)
  - `run_assistant` 的 `input_state` 放宽为 `Any`，以支持 `Command(...)` 作为 input
- 补齐与 Task8 相关的基础兼容修复：
  - [interrupts.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/agents/tooling/interrupts.py) 的 inquiry payload 增补 `type="inquiry_card"`，使 interrupt payload 具备明确类型
  - [schemas.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/graph/tools/schemas.py) 的 `DelegateForFeedbackInput.prefilled_status` 兼容 `completed`

### 文件级改动清单

**修改**

- [api/chat.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/api/chat.py)
  - 修改 request schema：
    - `ChatRequest` 新增可选字段 `resume_payload: Optional[dict|str]`（以 inquiry_card answers 为准）
    - 新增可选字段 `resume: bool`（或复用 resume_payload 是否存在）
  - 修改调用 LangGraph SDK 的 input：
    - normal: `input=state`
    - resume: `input=Command(resume=resume_payload)`（按 LangGraph interrupt 语义）
  - 修改 response schema（或 response dict）：
    - 如果 `final_state` 含 `__interrupt__`，将其映射为前端可用字段（至少 inquiry_card）
- [api/stream.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/api/stream.py)
  - stream chunk 中对 interrupt 做特殊事件类型（例如 `{"type":"interrupt", ...}`）
  - 支持 resume 输入（同 chat.py）

**新增**

- `agent_impl/api/models_interrupt.py`（可选）集中定义 Pydantic schema（减少 chat/stream 重复）

### 单元测试 / API 测试

**新增（api_test）**

- `agent_impl/tests/test_interrupt_http_api.py`（标记 `@pytest.mark.api_test`）
  - `test_chat_returns_interrupt_payload()`：发送一条触发 ask_human 的消息，断言返回包含 inquiry_card（或 `__interrupt__` 映射字段）
  - `test_chat_resume_continues_and_returns_final_response()`：携带 resume_payload 再次调用，断言得到最终 pending_responses

**自测命令**

- 启动服务后：`cd agent_impl/agent_impl && pytest -q tests/test_interrupt_http_api.py -m api_test`

**本地执行结果**

- 单测通过：`python -m pytest -q -m "not api_test"`（147 passed, 1 skipped, 20 deselected）
- API 测试：`pytest -q tests/test_interrupt_http_api.py -m api_test -rA`（本机未启动服务：2 skipped）

---

## 整体集成测试（全链路，离线优先 + 在线补充）

你要求“再做一个集成的整体的测试”，这里把 [langchain_agent_refactor_plan.md](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/docs/langchain_agent_refactor_plan.md) 的关键 To-Be 约束映射成“可执行的验收测试集”，并按离线优先 + 在线补充分两层跑通。

### 集成测试 A（离线，纯 workflow + MockLLM）

**目标**

不依赖真实 HTTP 服务与真实模型（默认 `LLM_PROVIDER=mock`），直接在 pytest 中验证：

1. 主图完整可编译与可执行（Router + Onboarding 子图 + Main Agent + Finalizer）
2. 工具循环与 `state_patch` 合并契约生效（工具/子 agent 产 patch → 主 agent 合并 → state 更新）
3. `interrupt()`/`Command(resume=...)` 能完整闭环（tool → graph pause → resume → 最终回复）
4. 核心产品字段保持稳定（`pending_responses` / `inquiry_card` / `layer2_memory` 等）
5. 关键决策点回归（messages 截断 25、legacy 控制字段不再出现等）

**建议作为“离线验收集”固定跑的测试文件**

- Workflow 全链路（纯图级）：[test_workflow_integration.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/test_workflow_integration.py)
- interrupt 工具闭环（图级）：[test_interrupt_ask_human.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/test_interrupt_ask_human.py)
- 主 agent LangChain wrapper（工具循环 + patch 合并 + messages 截断 25）：[test_main_agent_langchain_wrapper.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/test_main_agent_langchain_wrapper.py)
- `state_patch` 合并与工具 patch 约束：
  - [test_state_patch_merge.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/test_state_patch_merge.py)
  - [test_submit_tools_patch.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/test_submit_tools_patch.py)
  - [test_task_tools_patch.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/test_task_tools_patch.py)
- Skills 渐进式披露（metadata + load_skill）：[test_skills_load_skill_patch.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/test_skills_load_skill_patch.py)
- legacy 控制面字段回归（不维护 `agent_resume_point/current_agent` 等）：[test_state_schema_no_legacy_fields.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/test_state_schema_no_legacy_fields.py)

**验收标准**

- 快速验收（推荐 CI 门禁最小集）：
  - `pytest -q -m "not api_test" tests/test_interrupt_ask_human.py tests/test_main_agent_langchain_wrapper.py tests/test_state_patch_merge.py tests/test_workflow_integration.py`
- 全量离线回归（本地/CI 更完整但更慢）：
  - `pytest -q -m "not api_test" tests/`

### 集成测试 B（在线，真实 API + SDK 跑通 chat/stream）

**目标**

验证 FastAPI → LangGraph SDK → workflow → interrupt/resume 的完整路径，并覆盖非流式与流式两种对外协议：

- `/api/chat`：返回 `state.inquiry_card`，并用 `resume_payload` 继续执行直至产生 `pending_responses`
- `/api/chat/stream`：SSE 流中发出 `{"type":"interrupt","inquiry_card":...}` 事件，并以 `[DONE]` 结束

**建议作为“在线验收集”固定跑的测试文件（api_test）**

- 非流式 interrupt/resume（HTTP）：[test_interrupt_http_api.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/test_interrupt_http_api.py)
- 流式 interrupt 事件（SSE）：[test_interrupt_stream_http_api.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/tests/test_interrupt_stream_http_api.py)（新增，见 Task 清单）

**验收标准**

- 启动服务后：
  - `pytest -q -m api_test tests/test_interrupt_http_api.py tests/test_interrupt_stream_http_api.py`

---

## 最后说明：每个 task 的“agent 自测”要求

为保证“让 agent 自己测试”，每个 task 的 PR/合并门禁建议统一：

- 至少跑完该 task 对应的单元测试文件（本文件已列出）
- 若涉及 interrupt 或 API，则额外跑对应的集成测试 A 或 api_test B（按改动范围选择）

---

## 一致性审计（执行结果复核后的待优化点）

以下是对照 To-Be 方案与当前仓库实现后的“可优化项/遗留项”，建议按优先级收口：

1. **子 agent prompts 协议升级**：prompts 中若仍出现 `ask(action="enable")` / 两阶段 `ask` / `return_to_main` 等旧协议，应改为 `ask_human(inquiry_card=...)` 与“提交后最小总结”。（否则模型会读到旧协议但工具集里找不到对应工具）
2. **移除未接入的 agents/subagents 骨架**：当前子 agent 的实际执行路径是 main_agent 内部 `_call_subagent` + tool-loop；`agent_impl/agents/subagents/*` 若不再被引用，应删除或改造成实际复用入口，避免误导。
3. **清理 workflow 中的旧 skill_tools 路由死代码**：主图已不再接入 `skill_tools`/子节点，但文件中若仍保留相关函数实现，建议迁出或删除，降低维护噪声。
4. **收敛 legacy state 输出字段**：若仍有工具 patch 写入 `status_report/action_plan/action_guides` 等旧镜像字段，与“不维护 legacy 字段”的决策冲突；建议统一只写 `layer*_memory` 与产品字段（pending_responses/inquiry_card/feedback_* 等）。
5. **测试命令一致性**：本机环境可能不存在 `pytest` 可执行文件，推荐文档统一写 `python -m pytest ...` 以避免 PATH 依赖。
