---
name: changelog-creator
description: 自动化创建和管理项目变更日志（Changelog）。当代码重构、API 变更、功能添加等需要记录变更时使用此技能。适用于需要记录变更摘要、影响范围、技术细节等场景。使用时机：每次完成重要代码变更后、API 接口修改后、架构调整后。
---

# Changelog Creator

## Overview

自动化创建和管理项目变更日志（Changelog）的工具，帮助开发者规范地记录代码变更历史。

## Quick Start

当需要记录变更时，使用以下步骤：

1. **创建变更日志文件**：在 `agent_impl/changelogs/` 目录下创建 `YYYY-MM-DD-变更主题.md` 文件
2. **填写变更摘要**：包含概述、变更内容、技术细节等
3. **标记影响范围**：明确影响哪些模块、API 或功能
4. **补齐测试清单与用例沉淀**：测试用例文件写到 `agent_impl/testcases/YYYY-MM-DD-变更主题.md`（可从 `agent_impl/testcases/TEMPLATE.md` 复制），并在日志中链接该文件

## Task 1: 创建变更日志

### 触发条件

以下情况应创建变更日志：

- API 接口新增/修改/删除
- 代码架构重构（模块拆分、合并、重命名）
- 依赖库升级或降级
- 数据库结构变更
- 配置项修改
- 重大 bug 修复
- 新功能添加

### 创建步骤

1. **创建目录**（如不存在）
   ```bash
   mkdir -p agent_impl/changelogs
   ```

2. **创建文件**，命名格式：`YYYY-MM-DD-变更主题.md`
   - 使用连字符分隔
   - 日期为变更完成日期
   - 主题简洁描述变更内容

3. **填写内容模板**：

```markdown
# [变更主题] - YYYY-MM-DD

## 概述
简要描述变更的目的和内容（1-2 句话）

## 变更内容

### 新增文件结构
列出新增/修改的文件和目录

### 模块划分
按功能模块描述变更

### 精简/重构内容
描述代码简化和优化内容

## 技术细节

### 实现要点
关键的技术实现细节

### 兼容性说明
说明向后兼容性、API 路径变化、数据格式变化等

## 验证结果

列出已通过的测试和验证项

## 测试清单（必须）

用可执行、可复用的方式沉淀测试覆盖，优先落到代码仓库：

### 变更关联用例文件

- 用例文档：`agent_impl/testcases/YYYY-MM-DD-变更主题.md`（若已有同主题文件则追加）
- 模板：`agent_impl/testcases/TEMPLATE.md`
- 说明：`agent_impl/testcases/README.md`
- 自动化用例：尽量补齐/新增到项目现有测试框架（单测/集成/E2E）

### Checklist

- [ ] 核心路径：覆盖主流程与关键分支（至少 3 条）
- [ ] 失败路径：至少 1 条错误/异常场景（含期望提示/错误码）
- [ ] 兼容性：老接口/老数据/灰度场景是否覆盖（如适用）
- [ ] 回归范围：列出需要回归的模块/页面/API（可按路径枚举）
- [ ] 观测性：关键日志/指标/告警是否验证（如适用）
- [ ] 安全与权限：鉴权/越权/数据隔离是否验证（如适用）
- [ ] 性能与资源：关键接口耗时、缓存命中、资源占用是否验证（如适用）

## 后续优化建议

未来可以改进的方向

## 影响范围

明确影响的代码文件、API 接口、部署方式等
```

## Task 2: 维护变更日志

### 更新现有日志

如果变更是渐进式的，可以更新已有日志文件：

1. 在现有日志中添加新的变更条目
2. 更新验证结果和影响范围
3. 标注更新日期

### 归档旧日志

- 将超过 6 个月的日志移动到 `agent_impl/changelogs/archive/` 目录
- 在根目录创建 `CHANGELOG.md` 汇总重要变更

## Task 3: 生成汇总日志

### 创建 CHANGELOG.md

从 `agent_impl/changelogs/` 目录生成项目总体变更摘要：

```markdown
# 项目变更日志

## [版本号] - YYYY-MM-DD

### 新增
- ...

### 修改
- ...

### 删除
- ...

### 优化
- ...
```

## Examples

### 示例 1: API 模块化重构

**场景**：将集中的 API 接口按功能拆分为独立模块

```markdown
# API 模块化重构 - 2026-01-17

## 概述
将原本集中在 `server.py` 中的所有 API 接口按功能点拆分为独立模块，提升代码可维护性和可扩展性。

## 变更内容

### 新增文件结构
```
agent_impl/
├── api/                          # 新增 API 模块目录
│   ├── __init__.py               # 统一路由导出
│   ├── auth.py                  # 认证相关接口
│   ├── upload.py                # 图片上传接口
│   ├── chat.py                  # 聊天接口
│   ├── stream.py                # 流式聊天接口
│   ├── guide.py                 # 指南管理接口
│   └── debug.py                # 调试接口
└── server.py                    # 精简后的主文件
```

### 模块划分

#### 1. 认证模块 (`api/auth.py`)
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/me` - 获取当前用户信息

...

## 兼容性

### API 路径保持不变
所有 API 路径与重构前完全一致，无需修改前端代码。

### 数据格式保持不变
请求和响应的数据格式完全兼容原有实现。

## 验证结果

- ✅ 所有 API 模块通过 Python 编译检查
- ✅ `server.py` 通过 Python 编译检查
- ✅ 路由结构正确加载

## 影响范围

- 代码文件：新增 7 个文件，重构 1 个文件
- API 接口：无变化（路径和行为完全兼容）
- 部署方式：无变化（`python server.py` 仍然可用）
```

### 示例 2: 依赖升级

```markdown
# LangGraph SDK 升级 - 2026-01-10

## 概述
将 LangGraph SDK 从 v0.2.12 升级到 v0.2.15，以获取最新的 Bug 修复和性能优化。

## 变更内容

### 依赖更新
- LangGraph SDK: v0.2.12 → v0.2.15
- LangChain: v0.1.5 → v0.1.7

### 兼容性调整
- 更新 `graph/workflow.py` 中的状态管理逻辑
- 调整 ToolNode 初始化方式

## 技术细节

### 破坏性变更
- `workflow.update_state()` 现在需要显式传递 `config` 参数
- 移除了 `StateGraph.compile()` 中的 `checkpointer` 选项

### 新增功能
- 支持流式状态更新
- 优化 checkpoint 读写性能

## 兼容性

### API 兼容性
所有 API 接口保持不变，仅内部实现调整。

### 部署兼容性
需要重新安装依赖：`pip install -r requirements.txt`

## 影响范围

- 受影响模块：`graph/workflow.py`, `graph/nodes/*.py`
- 需要重启服务
```

## Best Practices

### 命名规范

- 日期格式：ISO 8601 (`YYYY-MM-DD`)
- 文件名：小写、连字符分隔
- 主题：简洁、描述性（如 `api-refactor`, `dependency-upgrade`）

### 内容组织

1. **概述**：让读者快速了解变更目的
2. **变更内容**：详细列出具体修改
3. **技术细节**：开发者需要知道的技术要点
4. **兼容性**：对下游的影响说明
5. **影响范围**：明确哪些部分受影响
6. **测试清单**：把“已验证什么、如何复现、如何回归”写成可执行的 checklist，并将关键用例沉淀到仓库

### 版本管理

- 如果有版本号，在概述中标注
- 关联相关的 issue 或 PR 编号
- 标注依赖的变更（如需要先完成其他变更）

### 测试用例沉淀规范

- 用例文件建议放在 `agent_impl/testcases/`（或项目既有文档目录），并在变更日志的“测试清单”中给出相对路径
- 用例应可复用：包含前置条件、步骤、预期结果、覆盖范围（接口/页面/模块）
- 若已有自动化测试框架：优先补充自动化用例；手工用例用于补足验收与回归清单

## References

### 相关工具

- [Semantic Versioning](https://semver.org/) - 版本号规范
- [Keep a Changelog](https://keepachangelog.com/) - Changelog 最佳实践

### 项目资源

- `agent_impl/changelogs/` - 详细变更日志目录
- `agent_impl/testcases/` - 关键测试用例沉淀目录
- `CHANGELOG.md` - 项目总体变更摘要
- `.gitignore` - 确保 `agent_impl/changelogs/` 与 `agent_impl/testcases/` 被提交到版本控制
