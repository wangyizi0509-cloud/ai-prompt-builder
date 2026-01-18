# 2026-01-18-langgraph-local-dev-skill 测试用例

## 概述
验证 `langgraph-local-dev` 技能的有效性及其对 `workflow.py` 逻辑简化的回归测试。

## 场景 1: 技能有效性验证
**前置条件**: 已安装 `langgraph-cli`。

**测试步骤**:
1. 检查 `.trae/skills/langgraph-local-dev/SKILL.md` 的 YAML 前门信息。
2. 运行打包脚本：`python3 .trae/skills/skill-creator/scripts/package_skill.py .trae/skills/langgraph-local-dev`。
3. 检查生成的 `langgraph-local-dev.skill` 文件。

**预期结果**:
- 打包脚本应成功退出且无错误。
- `langgraph-local-dev.skill` 文件应存在于项目根目录。

## 场景 2: `workflow.py` 编译验证
**前置条件**: 已安装 `langgraph` 依赖。

**测试步骤**:
1. 运行 `agent_impl/graph/workflow.py`（或调用其 `get_workflow` 方法）。
2. 观察是否能正常生成编译后的 graph 实例。

**预期结果**:
- Graph 编译成功，不再抛出关于 Postgres 或 Sqlite 连接池缺失的错误。

## 场景 3: 文档链接验证
**测试步骤**:
1. 在支持 Markdown 预览的编辑器中打开 `SKILL.md`。
2. 点击指向 `references/` 目录下文件的链接。

**预期结果**:
- 链接应能正确跳转到对应的参考文档。
