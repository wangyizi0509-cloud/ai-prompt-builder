# Onboarding v2 · Team 手册

> 全新的销售漏斗式 onboarding,**完全独立于 LangGraph**。Splash → 自由描述+截图 → 规则题库+钩子 → 免费诊断报告 → 付费闸门。3 个独立 LLM 节点,前端 localStorage 全量存进度。

**这份 README 是你加入项目第一天应该读的文件。**

---

## 一、我是哪个 agent,应该读什么、能改什么

| Agent | 角色 | 必读文件 | 产出归属 | 只读引用 |
| :--- | :--- | :--- | :--- | :--- |
| **A**(已完成) | 契约定义者 | 需求文档 v2 | `schemas.py` / `question_bank.py` / `hooks.py` / `API_CONTRACT.md` / `LOCAL_STORAGE_PROTOCOL.md` / `question_bank.frontend.json` / `export_frontend_json.py` / `README.md` | - |
| **B** | 筛题 + 第一个钩子 LLM 节点 | `API_CONTRACT.md §2` / `schemas.py`(`AnalyzeRequest` / `AnalyzeResponse`) / `question_bank.py` | `agent_impl/onboarding_v2/nodes/analyze.py` | A 的全部产出 |
| **C** | 诊断报告 LLM 节点 | `API_CONTRACT.md §3` / `schemas.py`(`ReportRequest` / `DiagnosisReport` 及其子类) | `agent_impl/onboarding_v2/nodes/report.py` | A 的全部产出 |
| **D** | FastAPI REST 路由 + 关闭登录中间件 | `API_CONTRACT.md §2/§3` / `schemas.py`(全部) / `server.py`(挂路由 + DISABLE_AUTH 默认开 + 首页路由到 splash.html) | `agent_impl/api/onboarding_analyze.py` + `agent_impl/api/onboarding_report.py` + `agent_impl/server.py`(挂路由 + auth 中间件) + `agent_impl/start_dev.sh`(注入 DISABLE_AUTH=1) | B/C 的节点函数 |
| **E** | 前端 Splash + 自由描述 + 题库 | `LOCAL_STORAGE_PROTOCOL.md` / `question_bank.frontend.json` / `API_CONTRACT.md §2`(调 analyze) | `agent_impl/frontend/splash.html` + `agent_impl/frontend/onboarding.html` 及关联 JS/CSS/图片资源 | A 的前端 JSON |
| **F** | 前端 报告页 + 付费闸门 | `LOCAL_STORAGE_PROTOCOL.md` / `API_CONTRACT.md §3`(调 report) / `schemas.py`(`DiagnosisReport` 参考字段) | `agent_impl/frontend/report.html` 及关联 JS/CSS | A 的前端 JSON |
| **G** | main_agent 衔接(首轮把 onboarding_payload 渲染成模板消息) | `API_CONTRACT.md §4`(onboarding_payload 结构 + 模板行为) / `schemas.py`(`DiagnosisReport` 仅供埋点,首轮不再消费 `collected_summary`) | `agent_impl/api/chat.py` + `agent_impl/api/stream.py`(接收 `onboarding_payload`、首轮判定、渲染入 thread) + `agent_impl/api/onboarding_handoff_prompt.py`(`OnboardingPayload` / `OnboardingOcr` / `render_onboarding_first_turn_message`) + `agent_impl/graph/state.py`(`create_initial_state` 默认 `onboarding_completed=True`;v2.1 已移除 `onboarding_handoff` 字段及 `onboarding_refine` 维护链路) + `agent_impl/graph/nodes/router.py`(冗余校验) | - |
| **I** | 前端主入口改造 + localStorage 共享层 | `LOCAL_STORAGE_PROTOCOL.md` / `API_CONTRACT.md §4` | `agent_impl/frontend/scripts/onboarding_storage.js`(共享工具,E/F/I 共用) + `agent_impl/frontend/index.html`(最小改动:移除 auth.html 跳转,加入 localStorage 检查) | A 的前端 JSON |
| **H** | 端到端测试(P2) | 全部文档 | `agent_impl/tests/e2e/test_onboarding_v2_journey.spec.ts` | 全部 |

**冻结原则**:A 产出的所有文件一经本手册交付即冻结,B-H 任何想改动都必须通过 A 走协商流程,避免下游多个 agent 同时踩 schema 漂移。

---

## 二、关键决策 FAQ

### Q1:为什么不用 LangGraph?

A:
- Onboarding 的核心流程是「三段线性 LLM 调用 + 前端状态机」,不需要节点路由、interrupt/resume、checkpoint 等 LangGraph 核心能力
- 本期无登录、无对话历史,没什么可 checkpoint 的
- 独立 REST 让前端能走 CDN/边缘节点,响应更快,无需启动 LangGraph Dev
- 主对话沿用 LangGraph,两者通过 `/api/chat` 的结构化 `onboarding_payload` 字段衔接——前端付费后 onMounted 自动触发首轮,后端 `api/onboarding_handoff_prompt.py` 把 payload 渲染为模板消息(见 `API_CONTRACT.md §4`)

### Q2:为什么是 3 个独立 LLM 节点,不是 1 个大的 prompt?

A:
- 3 个节点职责清晰:筛题 + 第一个钩子 vision / 第一个钩子 vision(同上一个合并) / 诊断报告
- 实际实现是 **2 个** REST 端点 + 1 个前端规则引擎:
  - `/analyze` = 一个 vision 调用(筛题 + 第一个钩子一起出),Agent B 负责
  - `/report` = 一个文本调用(看 free_text + OCR + answers,生成诊断),Agent C 负责
  - 中间的题后钩子 = **前端规则触发**(`hooks.py` 的本地副本),不走网络
- 拆开好处:每个 prompt 都短、可以独立 eval、降级策略独立

### Q3:为什么前端驱动题库循环?

A:
- 题库是固定骨架(A1-A5),只有筛题结果是 LLM 动态产的;拿到筛题结果后,后续循环完全规则化
- 前端做状态机 → 响应快(秒出)、刷新可恢复、用户没联网也能继续
- 后端不用维护 session 状态,极简

### Q4:为什么 localStorage 一个 key 存全部,不分多个 key?

A:
- 原子性:一次读/一次写不会出现"只更新一半"的错乱
- 清理简单:重置 onboarding 只需 `removeItem` 一次
- 大小不是问题(<100KB)
- 见 `LOCAL_STORAGE_PROTOCOL.md §六`

### Q5:为什么没做路径 B(没加微信)?

A:
- 需求文档 §2.3 明确标注「路径 B 本期暂不实现」
- 当前题库只含 A1-A5(路径 A)。后续迭代要做路径 B 再加 B1-B7,新增选项而非改现有选项
- 前端在自由描述页**不展示**「还没加微信」选项(见需求文档 §1.2)

### Q6:3 个 LLM 节点都是什么模型?

A:由 Agent B/C 自己在 `nodes/analyze.py` / `nodes/report.py` 里决定。约定:
- `/analyze`:必须是 **vision 模型**(要看截图),默认用 `qwen3-vl-plus`(参考 commit b283d8e 的策略)
- `/report`:可以是纯文本模型(截图已 OCR 过了)
- 失败时统一走 `API_CONTRACT.md` 定义的降级行为

---

## 三、Schema 漂移 Playbook(出了 bug 怎么办)

### 症状识别

| 现象 | 可能原因 |
| :--- | :--- |
| 前端报错"skip_rules 缺某题" | Agent B 的 LLM 输出没覆盖全部 5 道题 → 修 B 的 prompt 让它必须返回 A1-A5 |
| 后端 422 "extra fields" | 有 agent 传了多余字段 → schema 是 `extra="forbid"`,检查最近提交 |
| 前端渲染钩子时某选项没对应文案 | `hooks.py` 漏加了某选项 → 照需求文档 §2.3 补回 |
| JSON 文件和 .py 对不上 | 有人改了 .py 没跑 `export_frontend_json.py` → CI 应该会报,手动跑一次就好 |
| 诊断报告标题展示乱码 | `StateLabel.name` 不在 6 个枚举里 → 修 C 的 prompt 约束输出 |
| main_agent 第一轮重复问用户关系性质 | Agent G 首轮模板没落地 → 依次检查:index.html 是否在付费后 onMounted 发出 `onboarding_payload`、`api/chat.py`/`api/stream.py` 首轮判定是否命中、`api/onboarding_handoff_prompt.py:render_onboarding_first_turn_message` 是否把 payload 渲染进 messages |

### 标准处理流程

1. **先 reproduce**:记下触发步骤,最好带 `session_id` 和时间点
2. **定位 Owner**:查本文"文件归属表"找对应 agent
3. **不要自己改 schemas.py / question_bank.py / hooks.py**:这三个是 A 冻结的契约,改了等于全员返工
4. **如果确实需要改契约**:在 `ITERATION_LOG.md` 里开一条精简的项目级记录,召集全部受影响的 agent 评审
5. **修复完跑一次 `_self_check.py`** 确认自测没有回归

---

## 四、文件清单

| 文件 | 类型 | 作用 |
| :--- | :--- | :--- |
| `schemas.py` | Pydantic v2 | 三个端点的请求/响应 schema 定义 |
| `question_bank.py` | 常量 | A1-A5 五道题的题干、选项、筛题规则 |
| `hooks.py` | 常量 + 辅助函数 | 每题钩子文案、多选组合匹配规则 |
| `API_CONTRACT.md` | 文档 | 三个 REST 端点的完整契约(请求/响应/降级) |
| `LOCAL_STORAGE_PROTOCOL.md` | 文档 | 前端本地存储协议(key、字段、stage、状态机) |
| `question_bank.frontend.json` | 自动生成 | 前端 fetch 用的题库+钩子合并副本 |
| `export_frontend_json.py` | 脚本 | 从 .py 导出上面的 JSON(CI 可用来做一致性校验) |
| `_self_check.py` | 脚本 | Schema 跑通、JSON 一致性校验 |
| `README.md` | 文档 | 本文件,team 手册 |

---

## 五、自测与 CI

```bash
# 任何时候都可以跑(不需要服务)
python3 agent_impl/onboarding_v2/_self_check.py
```

预期输出最后一行:`Agent A contracts ready ✅`

CI 建议:在 `.github/workflows/ci.yml` 的 lint 阶段后新增一步

```yaml
- name: Onboarding v2 schema self-check
  run: python3 agent_impl/onboarding_v2/_self_check.py
```

---

## 六、变更记录

| 日期 | 作者 | 变更 |
| :--- | :--- | :--- |
| 2026-04-21 | Agent A | 初版冻结(schemas / 题库 / 钩子 / API 契约 / localStorage 协议 / 前端 JSON / 自测) |
