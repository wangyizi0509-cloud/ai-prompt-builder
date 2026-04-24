# 文档索引 (Documentation Index)

> 本索引是项目所有文档的统一入口。AI Agent 和开发者都应通过此文件按需查找文档。
>
> **权威源**：当文档间描述冲突时，以 `CLAUDE.md`（根目录）和代码实现为准。

---

## 快速导航

| 你想了解… | 看这个文档 |
|-----------|-----------|
| 项目是做什么的、产品定位 | [产品全景图](#产品与业务) |
| 怎么启动服务、跑起来 | [CLAUDE.md](#项目入口) / [快速开始调试](#开发与调试) |
| 技术架构、主图节点、子图 | [CLAUDE.md](#项目入口) / [重构方案](#架构与设计) |
| 怎么写测试、跑测试 | [验收文档](#开发与调试) |
| 怎么提交代码、分支管理 | [贡献指南](#项目入口) |
| Skill 技能系统怎么用 | [Skills 系统设计](#技能系统) |
| LangSmith Studio 怎么配 | [Studio 配置](#开发与调试) |
| Benchmark 评估怎么跑 | [Benchmark README](#评估与测试) |

---

## 项目入口

| 文档 | 路径 | 说明 |
|------|------|------|
| **CLAUDE.md** | `/CLAUDE.md` | **核心参考**。启动命令、架构概览、分层记忆、分支策略。与代码实现保持同步。 |
| **AGENT.md** | `/AGENT.md` | 与 CLAUDE.md 完全一致的副本（供非 Claude Agent 使用），内容同步更新。 |
| **README** | `/README.md` | 项目简介与目录结构入口。 |
| **贡献指南** | `/CONTRIBUTING.md` | 分支策略（main/develop/feature）、PR 流程。 |
| **测试账号** | `/TEST_USERS.md` | 测试用邮箱和密码清单。 |
| **项目变更记录** | `/ITERATION_LOG.md` | 高信噪比变更登记册，只记录跨模块变更、契约变化、部署问题、关键决策和未完成事项。 |

---

## 产品与业务

| 文档 | 路径 | 说明 | 状态 |
|------|------|------|------|
| 产品全景图 | `agent_impl/docs/product_overview.md` | 产品定位、用户画像、Agent 角色分工、用户旅程。 | ⚠️ 技术架构章节仍描述旧 Router 模式，以 CLAUDE.md 为准 |
| 研发流程 v1 | `agent_impl/docs/Crushe AI 研发流程 v1.md` | 研发流程与协作规范。 | ✅ |

---

## 架构与设计

| 文档 | 路径 | 说明 | 状态 |
|------|------|------|------|
| ~~架构设计 v2.1~~ | `agent_impl/docs/architecture.md` | v2.1 Router 状态恢复架构。 | ❌ **已过时**，当前使用 interrupt+resume 架构，见 CLAUDE.md |
| 重构方案 | `agent_impl/docs/langchain_agent_refactor_plan.md` | LangChain Agents + Subgraphs 技术方案。子图私有 messages、interrupt、state_patch。 | ✅ 与当前实现方向一致 |
| 重构执行记录 | `agent_impl/docs/langchain_agent_refactor_tasks_breakdown.md` | Task1-8 执行结果与历史记录。 | 📋 历史归档，含旧路径 |
| 前端展示技术方案（执行版） | `agent_impl/docs/frontend_display_recommended_solution.md` | 基于产品拍板结论的执行版方案。明确本期范围、下期范围、统一展示模型、排序规则和实施约束。 | ✅ 当前推荐 |
| 前端展示技术方案（候选 A） | `agent_impl/docs/frontend_display_tech_spec.md` | 偏增量改造、文件级施工清单的方案。 | 📋 候选参考 |
| 前端展示技术方案（候选 B） | `agent_impl/docs/frontend_display_technical_solution.md` | 偏统一事件模型与 Store 收敛的方案。 | 📋 候选参考 |
| 上下文审计 | `agent_impl/docs/context_engineering_callsite_audit.md` | 上下文工程调用链审计 v3.1。 | ⚠️ 审计快照，需对照最新代码 |
| 多 AI 协作 SOP | `agent_impl/docs/multi_ai_collaboration_sop.md` | 多 AI 分工、阶段模板、检查清单。 | ✅ |

---

## 开发与调试

| 文档 | 路径 | 说明 | 状态 |
|------|------|------|------|
| 快速开始调试 | `agent_impl/docs/quick_start.md` | verify 脚本、curl 调试、LangSmith 配置。 | ⚠️ 启动方式以 CLAUDE.md 为准 |
| 调试指南 | `agent_impl/docs/debug_guide.md` | Studio 调试、SSE 流调试、示例代码。 | ⚠️ 部分节点名称已变更 |
| 非流式验收 | `agent_impl/docs/acceptance_non_stream.md` | One-Click 非流式验收流程与范围。 | ✅ |
| Studio 配置 | `agent_impl/docs/studio_setup.md` | LangSmith Studio 环境变量与端口配置。 | ✅ |
| Studio README | `agent_impl/docs/readme_studio.md` | Studio 启动链接速查。 | ✅ |

---

## 技能系统

| 文档 | 路径 | 说明 | 状态 |
|------|------|------|------|
| Skills 系统设计 | `agent_impl/skills/README.md` | 渐进式披露机制、目录结构、SKILL.md 规范。 | ✅ |
| Skill 演示 | `agent_impl/docs/skill_demo.md` | load_skill 工具用法演示。 | ⚠️ 工作流集成图仍是旧结构 |

---

## 评估与测试

| 文档 | 路径 | 说明 | 状态 |
|------|------|------|------|
| Benchmark README | `Benchmark/README.md` | 评估用例分类、scope 选测、测试账号段。 | ✅ |
| Benchmark AGENT | `Benchmark/AGENT.md` | Benchmark Agent 指引。 | ✅ |

---

## 子目录 README

| 文档 | 路径 | 说明 | 状态 |
|------|------|------|------|
| agent_impl README | `agent_impl/README.md` | 目录结构与架构说明。 | ❌ **已过时**，仍描述 Router 恢复与旧节点结构 |

---

## 状态标记说明

- ✅ = 与当前代码实现一致，可直接参考
- ⚠️ = 部分内容已过时，核心思路可参考但需注意具体细节
- ❌ = 主体内容与当前实现冲突，仅作历史参考
- 📋 = 历史执行记录/归档
