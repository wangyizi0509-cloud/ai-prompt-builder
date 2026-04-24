# 项目变更记录

> 这个文件只记录仍有接力价值的项目级事实：跨模块变更、接口/契约调整、部署问题、产品/工程决策、未完成事项。
>
> 不再记录日常流水、一次性调试过程、重复跑测细节、已闭环的小修小补。细节优先放在对应代码、测试、artifact、PR 或 memory 中。

---

## 记录规则

只有满足以下任一条件时才新增或更新本文件：

- 改动跨越多个模块或影响后续 agent 协作。
- API、schema、localStorage、部署流程、分支流程等契约发生变化。
- 有尚未闭环的线上/部署/回归风险，需要明确 owner、下一步和验收口径。
- 产品或工程做了关键取舍，后续接手者不能只靠 git diff 理解。
- 某个详细 artifact 已经产生，需要在这里放一个稳定入口。

每条记录控制在 10-20 行内，保留结论、状态、影响范围、验证方式、详细资料位置。已完成事项只留摘要；未完成事项必须写清下一步。

---

## 当前未闭环事项

### 2026-04-24 | deploy | LangChain Cloud `ExecutionInfo` ImportError

**状态**：待执行修复。

**问题**：LangChain Cloud 部署时报 `ImportError: cannot import name 'ExecutionInfo' from 'langgraph.runtime'`。调用链是 `main_agent.py` 模块级导入 `langgraph.prebuilt.create_react_agent`，再进入 `langgraph-prebuilt` 的 `tool_node.py`。

**根因判断**：平台层固定 `langgraph-api=0.8.1`，其约束下实际 `langgraph` 版本没有 `runtime.ExecutionInfo`；但 pip 又解析到了较新的 `langgraph-prebuilt`，该版本模块级导入 `ExecutionInfo/ServerInfo`，导致启动即崩。

**推荐路径**：
1. 先在 `langgraph.json` 用 `dockerfile_lines` 钉住兼容的 `langgraph-prebuilt<1.0.9`，触发部署验证。
2. 如果平台 constraints 仍覆盖依赖，再评估从 `main_agent.py` 移除 `create_react_agent`，改手写 tool-loop。

**影响范围**：方案 A 只动 `langgraph.json`；方案 B 会动 `agent_impl/graph/nodes/main_agent.py`。

**验收**：部署日志不再出现 `ExecutionInfo` ImportError，线上 graph 能正常 import 并启动。

---

## 关键已完成变更

### 2026-04-23 | onboarding_v2 | Onboarding 到 Main Agent 衔接重构

**状态**：已完成。

**结论**：废弃 `/api/chat` 的 `onboarding_summary` 字符串透传，改为结构化 `onboarding_payload: {free_text, ocr_texts[], answers}`；付费后进入主聊天页自动触发首轮 `/api/chat/stream`，用户无需先输入。

**核心变更**：
- 新增 `api/onboarding_handoff_prompt.py`，统一把 onboarding payload 渲染为首轮系统素材。
- `api/chat.py` / `api/stream.py` 接收 payload，首轮渲染，非首轮静默忽略。
- 清理 v1 遗留 `onboarding_refine` 维护链路和 `onboarding_handoff` state 字段。
- `frontend/index.html` 从 localStorage 组装 payload，付费后自动首轮触发，发送成功后推进 stage。
- 同步 onboarding v2 API 契约、localStorage 协议、KNOWN_ISSUES、CLAUDE/AGENT 说明和相关测试。

**验证**：新增/改造的 onboarding handoff 单测通过；本机 e2e 跑通 splash → onboarding → report → mock pay → 主聊天自动首轮，首轮请求体含 `message === ""` 和完整 `onboarding_payload`。

**影响范围**：`agent_impl/api/*`、`agent_impl/graph/*`、`agent_impl/frontend/index.html`、onboarding v2 文档和测试。

### 2026-04-22 | onboarding_v2 | PM 全流程走查与前端发布修复

**状态**：已完成，另有非阻塞运营事项。

**结论**：PM 从手机视口完整走查 onboarding v2 销售漏斗，修复 6 类发布阻塞问题：上传接口路径错误、OCR 失败阻塞提交、题目编号错乱、A5 后空洞中间页、主聊天 Vue 模板字面量暴露、相关视觉/流程偏差。

**关键结果**：
- `agent_impl/frontend/scripts/onboarding_flow.js`：修上传路径、OCR 降级、题号展示、A5 直出报告。
- `agent_impl/frontend/index.html`：加 `v-cloak`，避免 Vue 模板字面量闪烁。
- report/mock pay/main chat 全链路可走通，localStorage 付费后状态能衔接主聊天。

**非阻塞待办**：
- DashScope OCR 在本机/网络层存在 ConnectError 风险，代码已有降级；长期可切豆包或 OpenAI vision。
- 功能预览卡仍需要替换为真实产品截图。

**证据入口**：`artifacts/pm-walkthrough/BUGS.md` 和同目录截图/快照。

### 2026-04-22 | prompt/eval | Onboarding analyze prompt 瘦身与模型对比

**状态**：已完成。

**结论**：GLM-4.6V analyze 节点不稳定的主要原因是 system prompt 过长，瘦身后 tool_call 成功率从约 30% 提升到真 API 跑测 3/3 成功；未切豆包。

**关键数据**：
- `agent_impl/onboarding_v2/prompts/analyze.md` 从约 5075 字压到约 2447 字含题库。
- `pytest tests/test_onboarding_v2_analyze.py -m "not api_test"` 通过。
- GLM vs 豆包对比：豆包文案证据更工整，但延迟约 2.2 倍，且现有 function calling 兼容成本更高。

**后续判断**：如果产品强要求豆包质量，需要先改 analyze 的 JSON/function-call 兼容逻辑并重新跑回归；默认继续用 GLM。

### 2026-04-22 | onboarding_v2 | 钩子策略、A0 性别题与功能预览卡

**状态**：已完成。

**结论**：onboarding v2 的 opening/card hook 文案、A0 性别题、功能预览卡完成一轮产品化改造。P0 opening hook 已通过真实 LLM 迭代落地；card hook 和需求文档同步了 hooks.py 的最新内容。

**影响范围**：`agent_impl/onboarding_v2/*`、onboarding 需求文档、前端 onboarding 流程。

**详细资料**：`agent_impl/docs/onboarding/hook_model_strategy.md`、`agent_impl/docs/onboarding/hook_strategy_iteration.md`。

### 2026-04-21 | onboarding_v2 | 独立 REST + 前端状态机 + mock 付费架构

**状态**：已完成。

**结论**：Onboarding v2 从旧 LangGraph onboarding 子图切到独立 REST 编排和前端状态机：自由描述/截图 → analyze → 题库循环 → report → mock pay → 主聊天衔接。

**核心模块**：
- 后端：`agent_impl/onboarding_v2/*`、REST 挂载、analyze/report LLM 节点。
- 前端：`splash.html`、`onboarding.html`、`report.html`、`scripts/onboarding_flow.js`、`scripts/report_page.js`。
- 状态：localStorage 承担 onboarding 前端状态共享，后续由主聊天页消费。

**注意**：旧 `agent_impl/onboarding/` 属于历史遗留，不再作为 v2 主路径。

### 2026-04-17 | frontend_display | DisplayNode 全链路统一展示

**状态**：已完成。

**结论**：聊天流展示从多套临时消息逻辑统一到 DisplayNode 模型，解决节点丢失、乱序、刷新恢复不一致等核心问题。

**核心变更**：
- 新增 `agent_impl/api/display_events.py`，定义 DisplayNode、seq 分配和节点构造。
- `api/stream.py`、`api/conversation_persist.py`、`graph/nodes/main_agent.py` 注入 `seq/turn_id/node_id/node_type/status` 等展示字段。
- `frontend/index.html` 增加 DisplayStore、normalizer、tool_call/reasoning/report_card/inquiry_card 等渲染。

**验证**：后端单测和浏览器渲染冒烟均通过；刷新恢复仍以 `/messages` 作为聊天真相源，`/state` 只承担面板/工作流状态。

### 2026-04-17 | bugfix | ultrareview 三处问题修复

**状态**：已完成。

**结论**：修复三类独立问题：
- `agent_impl/api/sdk_client.py`：已有 DB thread 绑定时，LangGraph thread 访问失败后应沿用同一 thread_id 重建，避免用户刷新读到旧 thread 空历史。
- `agent_impl/utils/image_processor.py`：长图 OCR 不再临时改写单例实例字段，改用 override 参数透传，避免并发请求串 key/model。
- `.trae/skills/langsmith-trace-analyzer/scripts/list_recent_traces.py`：修复 `IndentationError`。

**验证**：相关 ast/import 检查和长图测试通过。

### 2026-04-10 | infra | 基础工程治理

**状态**：已完成。

**结论**：建立基础 CI/test/docs 体系，包括 GitHub Actions、ruff 配置、pytest/e2e 入口、Playwright 全流程测试、文档索引和测试账号维护方式。

**当前注意**：分支流程以后以 `CLAUDE.md` / `AGENT.md` 的最新描述为准；`ITERATION_LOG.md` 不再作为每次提交必须更新的流水账。

---

## 已清理的信息

本次整理删除了以下低价值内容：

- 已闭环任务的逐步操作流水、重复验收截图说明和中间 agent 分工记录。
- 已被代码、测试或专门 artifact 承载的详细 bug 复盘。
- 已失效的“所有工作都要实时记录”规则。
- 测试账号批量生成、Claude 本机配置等不适合作为项目级长期记录的环境流水。

<!-- 新记录请添加在此行上方，保持时间倒序 -->
