# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 全过程指导&背景
1. 我是一个AI产品经理，对技术细节不是特别熟悉，在跟我对话时最好用我能听懂的语言
2. 若你的任务是debug，注意，需要通过各种证据找到问题根因而非绕过它，确认根因以后跟我说清楚修复方案和可能的影响
3. **迭代记录**：任务开始时就在 `ITERATION_LOG.md` 创建记录，执行过程中实时更新进度。所有工作都要记录——需求开发、Bug 修复、架构改造、方案讨论、评估跑测、文档梳理、部署操作等。未完成的任务必须写清**当前进度**和**待办项**，让产品经理打开这个文档就能知道"最近做了什么、做到哪了、接下来该做什么"。
   - **更新方式**：任务开始前先读 `ITERATION_LOG.md`，判断是否有同类任务可以续写（避免重复新增）。若发现历史记录与当前任务存在冲突或矛盾，主动指出后再继续。确认无同类任务时，将新记录插到文件底部 `<!-- 新记录请添加在此行上方 -->` 锚点前面。
4. 要善用子agent，对于无需知道详细上下文或对于最终任务无需知道过程的子任务，要尽量用子agent来节省上下文，避免子任务的过程过多污染上下文

## 项目简介

Crushe AI 是一款基于 LangGraph 的 AI 恋爱军师 Agent，帮助用户追到 Crush。核心是多 Agent 协作工作流，通过 Supabase 持久化用户数据，通过 FastAPI 对外提供 API。

## 常用命令

### 启动服务

```bash
# 开发模式（推荐）：LangGraph Dev + FastAPI，无需 Docker
python3 .trae/skills/service-manager/scripts/start_services.py --mode dev
# API: http://localhost:8000  Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024

# 生产验证模式：模拟生产，使用 Docker + Postgres
python3 .trae/skills/service-manager/scripts/start_services.py --mode up
# API: http://localhost:8000  Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:8123

# 停止所有服务
python3 .trae/skills/service-manager/scripts/stop_services.py
```

或直接用脚本：
```bash
# 从仓库根目录执行
cd agent_impl && bash start_dev.sh

# 或者已经在 agent_impl/ 目录时执行
bash start_dev.sh
```


### 环境配置

```bash
cp .env.example .env
# 填入: DEEPSEEK_API_KEY / OPENAI_API_KEY / DOUBAO_API_KEY + DOUBAO_ENDPOINT_ID
# LLM_PROVIDER=deepseek|openai|doubao|claude|mock
# SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY（可选，缺省则用本地文件存储）
```

调试时设置 `DEBUG=1` 或 `DEBUG_REASONING=true`（DeepSeek Reasoner 调试）。

## 架构概览

### 主图工作流（`agent_impl/graph/workflow.py`）

入口为 `langgraph.json` → `agent_impl/agent.py:graph`。**Onboarding v2 上线后，主图实际只跑付费后的主对话**：

```
router → main_agent → post_turn_finalize → END
```

- **router**：风控/闲聊过滤、消息归一化、feedback_mode 分流；`create_initial_state` 默认 `onboarding_completed=True`（`graph/state.py:239`），所以正常流量不会进入旧 onboarding 子图
- **main_agent**：主 Agent，内置 tool-loop，直接在节点内执行工具并写回状态
- **post_turn_finalize**：轮次收尾（maintenance queue 处理、状态清理）

旧的 `onboarding` 子图（`agent_impl/onboarding/`）仍被挂在 workflow 上作为兜底，但 router 只要发现 `go_onboarding=True` 就会打 warning（`graph/nodes/router.py:266-274`）——正常路径不应触发。新用户走的是下一节的 Onboarding v2 独立通道。

最大步数限制：`MAX_NODE_STEPS_PER_TURN = 18`。

### Onboarding v2（独立于 LangGraph，`agent_impl/onboarding_v2/`）

销售漏斗式 onboarding，**完全独立于 LangGraph**。3 段线性流程 + 前端状态机，不走 checkpoint、不走 interrupt。

```
splash.html → onboarding.html（自由描述+截图 → 筛题循环 A1-A5 → 收尾）→ report.html → 付费 → index.html（主对话）
```

**两个独立 REST 端点**（`agent_impl/api/onboarding_analyze.py`、`agent_impl/api/onboarding_report.py`，直接挂在 `server.py`）：
- `POST /api/onboarding/analyze`：vision 模型（默认 `qwen3-vl-plus`），用户提交自由描述+截图后调用，一次返回 `skip_rules`（A1-A5 筛题结果）+ `first_hook`（首发钩子文案）
- `POST /api/onboarding/report`：文本模型，题库循环完成后调用，生成 `DiagnosisReport`（分数 + 雷达图 + 核心问题 + 紧迫感 + `collected_summary`）
- 题后中间钩子 = **前端规则触发**（`onboarding_v2/hooks.py` 的前端副本），不走网络

**前端进度**：localStorage 单 key（`onboarding.state`）原子读写，刷新可恢复，见 `onboarding_v2/LOCAL_STORAGE_PROTOCOL.md`。

**本期无登录**：`server.py:129-139` 里 `DISABLE_AUTH` 缺省即视为 `"1"`，`start_dev.sh` 也会显式注入。

**衔接主对话**（`agent_impl/api/chat.py` + `agent_impl/api/stream.py` + `agent_impl/api/onboarding_handoff_prompt.py`，v2.1）：付费后 `index.html` 在 onMounted **自动触发**首轮 `/api/chat/stream`，`message=""` + 结构化 `onboarding_payload`（`{free_text, ocr_texts[], answers{}}`，由 localStorage 组装）。后端首轮调用 `render_onboarding_first_turn_message(payload)` 把 payload 渲染为固定模板 user 消息（含 `[系统指令 · 仅本轮]` 段命令 main_agent 立刻调 `call_status_agent`，加 `[诊断素材]` 段三栏素材），按普通 user turn 写入 `messages` → `layer3.all_messages`；status 子图与 main_agent 共享 parent_state 可直接读到原始素材，零信息损失。**非首轮 `onboarding_payload` 自动忽略**。用户第一条可见气泡是 AI 产出的状态报告卡。已废弃的旧字段：`onboarding_summary`（字符串前置）、`AgentState.onboarding_handoff`、`onboarding_refine` 维护任务链路。

任何改动契约的操作都必须先读 `agent_impl/onboarding_v2/API_CONTRACT.md`（标记为 frozen）+ `agent_impl/onboarding_v2/README.md`（Agent 分工与文件归属）。

### Human-in-the-Loop

**main_agent** 使用 LangGraph 原生 `interrupt()` + `Command(resume=...)` 机制（通过 `ask_human` 工具）。
**status / plan / guide 子图** 使用"延迟 interrupt"模式（`graph/subgraphs/deferred_human.py`）：子图内 `ask_human` 工具不直接触发 `interrupt()`，而是将 payload 写入 `deferred_interrupt`；main_agent 在调用子图前检测并 relay 上一轮的 pending interrupt，子图返回后统一触发。
不再使用旧的"Router 状态恢复"模式。**Onboarding v2 不走 interrupt**——它是独立 REST，进度靠前端 localStorage。

### AgentState 分层记忆（`agent_impl/graph/state.py`）

```
Layer 1  layer1_memory      静态情报（用户、crush、两者关系）
Layer 2  layer2_memory      工作上下文（状态报告、行动计划、行动指南）
Layer 3  layer3_memory      对话历史与推理（全量消息 + 滚动摘要）
         messages           LangGraph add_messages 工作区（当轮消息）
         pending_responses  当轮待推送响应队列（list[dict]），按序汇聚：
                            子图中间 AI 消息（phase=subgraph_thinking）、
                            status_brief 摘要（phase=status_brief）、
                            最终回复（phase=final）
```

`layer3_memory.all_messages` 是全量持久存储；`messages` 字段是当轮工作区。`pending_responses` 由 main_agent 在每轮结束时填充，FastAPI 流式推送给前端。

### LLM 配置（`agent_impl/config.py`）

支持 DeepSeek / OpenAI / Doubao / Claude，由 `LLM_PROVIDER` 环境变量控制，有自动 fallback 逻辑。工具调用场景（`use_tools=True`）自动切换到 `deepseek-reasoner`（带 `reasoning_content` 回传修复）。测试使用 `LLM_PROVIDER=mock` 注入确定性 `MockLLM`。

### Skills 渐进式披露（`agent_impl/skills/`）

两级加载：System Prompt 只注入 Skill 的 name+description（元数据），模型判断需要时调用 `load_skill(skill_id)` 工具，工具返回对应 `definitions/<skill_id>/SKILL.md` 的完整指令。新增 Skill 只需在 `definitions/` 下创建目录和 `SKILL.md`，系统自动发现。

### Tools（`agent_impl/tools/`）

工具不直接修改状态，而是通过 tool_call 返回结构化 `state_patch`，由 main_agent 的 tool-loop 合并写回 `AgentState`。工具分类见 `agent_impl/tools/README.md`。

### FastAPI 服务（`agent_impl/server.py`）

通过 `langgraph-sdk` 连接本地 LangGraph Dev 服务（端口 2024）。关键 API 模块：
- 主对话：`api/auth.py`、`api/chat.py`、`api/stream.py`、`api/conversations.py`
- Onboarding v2：`api/onboarding_analyze.py`、`api/onboarding_report.py`（独立挂载，不走 `api_router` 的 env_flag 机制，见 `server.py:175-191`）

### 持久化

- **LangGraph Checkpointer**：对话状态（AgentState）持久化，Dev 模式由 `langgraph dev` 本地管理，Up 模式由 Postgres（Docker）管理
- **Supabase**：用户账号、会话元数据；缺省时退回本地文件存储（`agent_impl/local_data/`）

## 文档索引

项目所有文档的统一入口见 `agent_impl/docs/INDEX.md`，按模块分类、标注状态（✅可用 / ⚠️部分过时 / ❌已过时）。**当文档间描述冲突时，以本文件（CLAUDE.md）和代码实现为准。**

**Onboarding v2 关键文档**（任何改动都要先读）：
- `agent_impl/onboarding_v2/README.md` — Team 手册 / Agent 分工 / 文件归属表
- `agent_impl/onboarding_v2/API_CONTRACT.md` — 3 个端点请求/响应契约（frozen）
- `agent_impl/onboarding_v2/LOCAL_STORAGE_PROTOCOL.md` — 前端 localStorage 协议（单 key、stage 状态机）
- `agent_impl/docs/onboarding/onboarding_requirements_v2.md` — 产品需求（销售漏斗四步框架）
- `agent_impl/docs/onboarding_design_brief.md` — 设计交付稿（页面元素、交互）

## CI/CD

PR 到 `develop` 或 `main` 时自动触发 GitHub Actions（`.github/workflows/ci.yml`）：
1. **Lint**：`ruff check`（配置见 `agent_impl/ruff.toml`）
2. **Unit Tests**：`LLM_PROVIDER=mock` 下运行 `pytest tests/ -m "not api_test"`

## 测试体系

> **给 Codex / 其他 Agent**：用户若说「帮我跑端到端测试」「跑销售漏斗」「跑 full journey」「跑 Playwright 全流程」等，应在**用户本机**执行下文命令（需已启动服务、可走真实 LLM）；**不要**指望 GitHub CI 自动跑此测试。默认跑「Onboarding v2 销售漏斗」主路径；用户明确要求验证主对话能力时再跑「旧路径 full_journey」。跑完后把终端输出与对应 `artifacts/e2e/<journey-name>/` 截图路径告知用户。

### 单元测试（自动，无需服务）
```bash
cd agent_impl && pytest tests/ -m "not api_test" --tb=short -q
```

### 端到端可视化测试（本地手动跑，需要服务运行）

**前提**：服务必须已启动（`bash agent_impl/start_dev.sh`），且已安装 Playwright：
```bash
cd agent_impl/tests/e2e && npm install && npx playwright install chromium
```

#### 主路径：Onboarding v2 销售漏斗（推荐，覆盖新流程）

```bash
cd agent_impl/tests/e2e
npx playwright test test_onboarding_v2 --reporter=list
```

流程：splash → 自由描述+截图 → analyze 真 LLM（筛题 A1-A5 + 首发钩子）→ 题库循环（含选项钩子）→ closing summary → report 真 LLM 生成 `DiagnosisReport` → 渲染付费报告 → mock 付费 → index.html onMounted 自动触发首轮 `/api/chat/stream`（`message=""` + 结构化 `onboarding_payload`），后端 `api/onboarding_handoff_prompt.py` 渲染模板入 thread，首条可见气泡为 AI 状态卡。

环境变量见 `test_onboarding_v2.spec.ts`：`E2E_BASE_URL` 默认 `http://127.0.0.1:8000`，无需登录态（v2 本期无登录）。

#### 旧路径：已付费用户主对话全流程（inquiry + status/plan/guide）

```bash
cd agent_impl/tests/e2e
npx playwright test test_full_journey --reporter=list
```

环境变量（与 `test_full_journey.spec.ts` 一致）：
- `E2E_BASE_URL`：默认 `http://127.0.0.1:8000`
- `E2E_USER_EMAIL` / `E2E_USER_PASSWORD`：默认见 `TEST_USERS.md`（如 test01）

测试流程：登录 → 点击"开启情感攻略" → 跟随小话填写 inquiry 卡片（含真实截图上传）→ 验证 status/plan/guide 报告产出 → 规划 Tab 截图 → 提交行动反馈。**这条旅程跳过了 v2 onboarding 漏斗**，用于回归已付费用户的主对话能力。

**测试产物**：
- 截图：`artifacts/e2e/<journey-name>/*.png`（按步骤编号，可直接查看前端展示问题）
- 报告：`artifacts/e2e/playwright-report/index.html`
- 摘要：`artifacts/e2e/<journey-name>/summary.json`

预计耗时 5～15 分钟（取决于 LLM 响应速度）。

## 分支管理

- `main`：生产基线，触发自动 CD，**只接受来自 `develop` 的 PR**，严禁直接 commit
- `develop`：集成/测试分支，所有 feature 合入此处
- `feature/*` / `fix/*`：从 `develop` 拉出，完成后 PR 回 `develop`
