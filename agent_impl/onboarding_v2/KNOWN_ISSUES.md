# Onboarding v2 · 已知问题清单 & 回滚 Playbook

> **文档性质**：P2 集成阶段观察到的非 critical 遗留问题
> **Owner（整合）**：Agent H · 2026-04-21
> **面向读者**：产品经理 + 后续维护 agent
>
> 本清单聚合了 P0-P1-P2 各 agent 的边界缝隙与集成过程中发现的观察项，
> 不会阻塞销售漏斗跑通，但建议在灰度上线前逐条评估。

---

## 一、遗留问题（按推荐优先级排序）

### ISSUE-1 · `start_dev.sh` 无法 Ctrl+C 停服务

**问题描述**：
Agent D 把 `start_dev.sh` 改为 `nohup <cmd> &` 后台模式启动 LangGraph + FastAPI，
同时移除了原来的 `trap + wait` 组合。用户在终端按 Ctrl+C 不会传导到子进程，
需要手动 `pkill -f langgraph` + `pkill -f server.py` 才能清理。
脚本只在 stdout 打印 PID，没有写 `.pid` 文件，用户重开终端后无法用 `cat .pid` 精确 kill。

**复现步骤**：
1. `bash agent_impl/start_dev.sh`
2. 在终端按 `Ctrl+C`
3. 再起一个终端跑 `ps aux | grep -E "langgraph dev|server.py"` → 会看到 2 个进程仍在运行

**临时兜底**：
Agent H 新增 `agent_impl/stop_dev.sh`，提供一键 `pkill` 清理（SIGTERM + 2s + SIGKILL 兜底）：
```bash
bash agent_impl/stop_dev.sh
```

**推荐修复**：
- Owner：start_dev.sh 的原 owner（Agent D 或后续分支）
- 方案 A（推荐）：启动时把 PID 写入 `logs/langgraph_dev.pid` / `logs/fastapi_dev.pid`，
  `stop_dev.sh` 优先读 PID 文件再按进程名兜底
- 方案 B：恢复前台 + trap 模式，但用户反馈"开发时更方便切后台"，需再确认
- 时间线：建议灰度上线前处理，否则用户 onboarding 体验第一步就卡住

---

### ISSUE-2 · `/api/chat/stream` 对 `onboarding_payload` 的渲染未在服务端单测覆盖（v2.1 修订）

**现状(2026-04-23 更新)**:
v2.1 重构已把老的字符串 `onboarding_summary` 前置 + `state.onboarding_handoff` 写入链路彻底换成结构化 `onboarding_payload` + `render_onboarding_first_turn_message` 模板渲染。`/api/chat` 和 `/api/chat/stream` 共用同一份 `ChatRequest`/`StreamChatRequest`,首轮判定 `_is_first_turn_for_thread` 两边都命中,渲染后的 user 消息走正常 `messages` → `layer3.all_messages` 路径。

**保留关注点**:
目前 `StreamChatRequest` 路径的 `onboarding_payload` 端到端行为**没有服务端单测**覆盖,只靠 Playwright e2e(`test_onboarding_v2.spec.ts`)在浏览器层捕获首轮 `/api/chat/stream` 请求 body 做契约断言。如果后续改动 `api/stream.py` 的首轮注入逻辑或 `render_onboarding_first_turn_message` 的模板结构,单测回归网兜不住。

**推荐修复**:
- Owner:后续 Agent / 维护者
- 方案:在 `tests/test_stream_*.py` 补一条:用 TestClient 打 `/api/chat/stream`,mock run_assistant 返回空流,断言首轮 base_state.messages[0].content 包含 `[系统指令 · 仅本轮]` + `[诊断素材]` 两个段落头
- 时间线:下一次改 onboarding 衔接逻辑前补上

---

### ISSUE-3 · e2e 脚本依赖真实 LLM，本地跑约 5-10 分钟 + 存在单次 flaky 风险

**问题描述**：
`test_onboarding_v2.spec.ts` 不 mock LLM，跑 `/api/onboarding/analyze`（vision）
和 `/api/onboarding/report`（文本）两次真实 LLM 调用：
- analyze 最多 20s（服务端上限） + 降级逻辑
- report 最多 35s × 2 重试
- main_agent 首轮响应也会受 LLM 影响

**复现步骤**：
`bash agent_impl/start_dev.sh && cd tests/e2e && npx playwright test test_onboarding_v2 --reporter=list`
实测：5-15 分钟，取决于 DeepSeek/Doubao 响应速度。

**临时兜底**：
- 脚本设置了 90s report 超时 + 120s 主聊天首轮超时，单次失败（网络抖动）可直接重跑
- 失败时保留 trace（`retain-on-failure` 已在 playwright.config.ts 里配置）
- 截图全程保存到 `artifacts/e2e/onboarding-v2/`，便于排查

**推荐修复**：
- 方案 A：**不修复**（e2e 天生就是慢+真实，CI 里应跑 integration 的 6 项 TestClient 版本）
- 方案 B：如果产品希望 CI 里也跑 e2e，再建一个 `test_onboarding_v2.mock.spec.ts`，通过 Playwright 的 `page.route` 拦截
  `/api/onboarding/*` 返回固定 JSON，把 e2e 变成"纯前端流程测试"
- 时间线：按需

---

### ISSUE-4 · 钩子配图资源还是 placeholder

**问题描述**：
`hooks.py` 约定了 `assets/onboarding/局势分析.png`、`行动规划.png`、`聊天指导.png`、
`朋友圈指导.png`、`行动指南.png` 五张能力示意图。
当前 `agent_impl/frontend/assets/onboarding/` 下只有 `placeholder.svg` + `README.md`，
其他路径未填充真实图片，onError 时会回落到 placeholder。
前端体感上：钩子 → 功能预览图是银灰 placeholder，不是彩色 UI 截图。

**复现步骤**：
选 A3 选项 A（表白）→ 题后钩子页会在 `<img>` 加载 `局势分析.png` 失败后
显示 `placeholder.svg`。

**临时兜底**：
已 onError fallback 到 placeholder，不会崩页；视觉还能识别为"能力演示占位"。

**推荐修复**：
- Owner：设计/产品团队
- 方案：按 `agent_impl/frontend/assets/onboarding/README.md` 里列的 5 张能力示意图替换 PNG
- 时间线：灰度前或 UAT 反馈后

---

### ISSUE-5 · 老 onboarding 子图代码仍在 import 路径上（未清理）

**问题描述**：
Agent G 只改了 `create_initial_state` 的默认值 + Router 的 warning 日志，
`agent_impl/onboarding/*` 和 `graph/subgraphs/onboarding*` 的代码仍在模块图里可 import。
理论上 `onboarding_completed=False` 时（显式 overrides）仍可走老子图，
但产品侧已确认本期**不再使用老流程**。

**复现步骤**：
`grep -r "from onboarding" agent_impl/graph/` → 会看到老子图的 import 仍然存在。

**临时兜底**：
Router 节点在 `go_onboarding=True` 时会打 warning 日志，运维侧能观察到是否仍有流量走到老路径。

**推荐修复**：
- 方案 A（保守）：保留代码不删，仅在 `agent_impl/onboarding/__init__.py` 加 DeprecationWarning
- 方案 B（激进）：1 个 sprint 后确认老子图无流量，整个 `onboarding/` 目录归档到 `_deprecated/`
- 时间线：观察 2 周线上无 warning 日志后再决定

---

## 二、未发现 / 已确认正常的边界

- ✅ `/api/onboarding/analyze` LLM 失败 → 200 + 降级 payload，不阻断漏斗
- ✅ `/api/onboarding/report` LLM 连续失败 → 500 REPORT_GENERATION_FAILED，前端有重试按钮
- ✅ `/` 根路径 302 跳 splash.html，DISABLE_AUTH=1 时不被 AuthRedirectMiddleware 拦
- ✅ 非首轮 `onboarding_payload`(前端极端情况下重复传)服务端静默忽略,不会污染历史消息
- ✅ 前端 stage 协议：paid → done → 由 index.html onMounted 自动发首轮 `/api/chat/stream` 携带 `onboarding_payload`(v2.1 起不再由用户手动打字触发)
- ✅ Agent D 的惰性 import 在 B/C 产出后确实把两条路由挂上（`test_routes_mounted_after_p1` 坐实）

---

## 三、回滚 Playbook（如果 onboarding v2 整体要回滚）

### 3.1 优先方式：`git revert`

1. 找到 onboarding v2 相关的 commit（可通过 `git log --oneline --grep="onboarding.v2\|Onboarding v2"` 搜索）
2. `git revert <commit-hash>` 按反向顺序 revert 所有相关 commit
3. 如果 P0 冻结契约想保留（避免下次重写），可单独保留 `agent_impl/onboarding_v2/` 目录不 revert，
   只 revert server/chat/state/start_dev/frontend/index.html 的修改

### 3.2 手动兜底回滚（若 git revert 冲突严重）

在以下文件做最小改动：

1. **`agent_impl/graph/state.py`**：`create_initial_state` 里把 `onboarding_completed` 默认值改回 `False`
   （这样主图首次会再次进老 onboarding 子图）。
2. **`agent_impl/server.py`**：
   - `_auth_disabled` 默认值从 `"1"` 改回 `"0"`
   - 删除（或注释）`try: from api.onboarding_analyze import router` 两块新挂载代码
   - 删除（或注释）`@app.get("/")` 根路径 302 handler
3. **`agent_impl/start_dev.sh`**：删除 `export DISABLE_AUTH=1` 一行；如需恢复 Ctrl+C 停服务，
   把 nohup + `&` 替换回前台启动 + `trap 'kill ...' INT TERM EXIT; wait` 模式。
4. **`agent_impl/api/chat.py` + `agent_impl/api/stream.py` + `agent_impl/api/onboarding_handoff_prompt.py`**：
   - 从 `ChatRequest` / `StreamChatRequest` 移除 `onboarding_payload` 字段（或保留不报错）
   - 从首轮构造流程删掉 `render_onboarding_first_turn_message` 调用
   - 如需彻底回退,可删除 `onboarding_handoff_prompt.py`(无其他模块依赖)
   - `get_required_user_dep` 再用回（取消匿名依赖）
5. **`agent_impl/frontend/index.html`**：删除入口守卫的 onboarding_storage.js 加载 + setup() 顶部的 summary 注入逻辑。
6. **前端 onboarding v2 页面**：`splash.html` / `onboarding.html` / `report.html` 及对应 JS/CSS 可直接删除（它们没被其他页面引用）。

### 3.3 对 LangGraph 状态的影响

- v2.1 已移除 `AgentState.onboarding_handoff` 字段及整套 `onboarding_refine` 维护任务链路,老数据(v1/v2.0 时期写入的 `onboarding_handoff`)在 state 加载时会被当作未知字段忽略,不影响运行。
- LangGraph checkpointer 里 `onboarding_completed=True` 的旧 thread 不会再进老 onboarding 子图——**这是好事**,避免对老用户二次问卷。

---

## 四、给产品经理的 UAT 检查清单

接到本 PR 后建议按以下顺序走一次：

- [ ] 清空浏览器 localStorage，访问 `http://localhost:8000/` → 应 302 到 `/splash.html`
- [ ] 填「同事/3 个月/表白」+ 上传 1 张聊天截图 → 等 15-30s → 看到首发钩子 + A3/A4/A5 三道题（A1/A2 应被自动跳过）
- [ ] 答完题 → 看到总结页 → 点「生成完整诊断报告」→ `/report.html` 渲染五维雷达 + 核心问题 + 锁住 teaser
- [ ] 点「立即解锁」→ mock 付费 1s → 自动跳 `/index.html`
- [ ] **无需手动发消息**:index.html onMounted 会自动发首轮 `/api/chat/stream`,打开 DevTools Network 确认 body 的 `message` 为空字符串且 `onboarding_payload` 结构 = `{free_text, ocr_texts[], answers{}}`,第一条可见 AI 气泡是 status 子图产出的状态报告卡
- [ ] 手动再发一条消息 → 再看 body → 不应再携带 `onboarding_payload`(或即使携带,服务端也会静默忽略,不影响对话)
- [ ] 如果任一步失败，查看 `logs/fastapi_dev.log` + `logs/langgraph_dev.log` 报错行 + Chrome DevTools Console

---

## 五、变更记录

| 日期 | 作者 | 变更 |
| :--- | :--- | :--- |
| 2026-04-21 | Agent H | 初版 · P2 集成完成 |
