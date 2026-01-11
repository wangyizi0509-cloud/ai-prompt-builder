# Agent 架构测试文档

## 测试结构

本测试套件基于 `agent_impl` 的完整架构设计，包含以下测试文件：

### 单元测试
- `test_router.py` - 路由节点测试（风控、闲聊、业务路由）
- `test_skills.py` - Skills 测试（Inquiry、Consult、Emotion）
- `test_state_management.py` - 状态管理测试

### 集成测试
- `test_main_agent.py` - 主 Agent 测试
- `test_sub_agents.py` - 子 Agent 测试（Status、Plan、Guide）
- `test_workflow_integration.py` - 工作流集成测试

### 端到端测试
- `test_e2e_scenarios.py` - 真实 API 调用的完整用户场景（需要 API Key）

### 已有测试
- `test_context_engineering.py` - 上下文工程集成测试

## 运行测试

### 运行所有测试（不包括 API 测试）
```bash
cd agent_impl
pytest tests/ -v -m "not api_test"
```

### 运行特定测试文件
```bash
pytest tests/test_router.py -v
pytest tests/test_state_management.py -v
```

### 运行 API 测试（需要配置 API Key）
```bash
pytest tests/test_e2e_scenarios.py -v -m api_test
```

### 运行并生成覆盖率报告
```bash
pytest tests/ --cov=graph --cov=skills --cov-report=html
```

## 测试数据

测试数据文件位于 `tests/fixtures/`：
- `test_messages.json` - 测试消息样本
- `test_contexts.json` - 测试上下文样本

## 测试覆盖范围

### 路由节点 (Router)
- ✅ 风控关键词拦截
- ✅ 闲聊消息识别和处理
- ✅ 业务消息正确路由
- ✅ 恢复执行时的路由

### 主 Agent
- ✅ 纯咨询场景直接回复
- ✅ 情绪发泄场景情感陪伴
- ✅ 主 Agent 提问功能
- ✅ 调用子 Agent 决策
- ✅ 提问后恢复执行
- ✅ 子 Agent 返回后再决策
- ✅ 用户信息提取和更新

### 子 Agent
- ✅ Status Agent：现状分析生成、提问、恢复执行、完成信号
- ✅ Plan Agent：行动规划生成、提问、恢复执行
- ✅ Guide Agent：行动指南生成、提问、恢复执行

### Skills
- ✅ Inquiry Skill：问题生成、题型、上下文感知、元数据
- ✅ Consult Answer Skill：咨询回答、质量验证、元数据
- ✅ Emotion Support Skill：情感陪伴、共情能力、元数据

### 工作流集成
- ✅ 简单咨询流程
- ✅ 完整首次进入流程
- ✅ Agent 链式调用
- ✅ 恢复执行机制
- ✅ 状态持久化
- ✅ 错误处理
- ✅ 多轮对话连贯性

### 状态管理
- ✅ 状态初始化
- ✅ 状态更新
- ✅ 状态持久化
- ✅ 状态恢复
- ✅ Agent 恢复执行状态
- ✅ 分层上下文管理
- ✅ 状态迁移（UserProfile -> UserContext）
- ✅ 行动指南过滤

### 端到端场景
- ✅ 首次进入完整流程（需要 API）
- ✅ 纯咨询场景（需要 API）
- ✅ 情感陪伴场景（需要 API）
- ✅ 信息更新场景（需要 API）
- ✅ 关系状态更新（需要 API）
- ✅ 多轮对话连贯性（需要 API）
- ✅ 上下文保持（需要 API）
- ✅ 性能测试（需要 API）

## 已知问题

1. **API 测试需要配置**：端到端测试需要有效的 LLM API Key（在 `.env` 中配置）
2. **测试执行时间**：API 测试可能需要较长时间（每个测试约 30-60 秒）
3. **测试稳定性**：由于使用真实 API，测试结果可能因模型响应变化而略有不同

## 测试工具函数

在 `conftest.py` 中提供了以下工具函数：
- `create_test_state()` - 创建测试状态
- `run_workflow_turn()` - 执行一轮工作流
- `assert_state_valid()` - 验证状态有效性
- `assert_agent_output()` - 验证 Agent 输出
- `print_state_summary()` - 打印状态摘要（调试用）
- `get_ai_response()` - 从状态中提取 AI 回复

## 贡献指南

添加新测试时：
1. 遵循现有测试结构
2. 使用 `conftest.py` 中的工具函数
3. 对于需要 API 的测试，使用 `@pytest.mark.api_test` 标记
4. 确保测试独立，不依赖其他测试的执行顺序
5. 添加适当的文档字符串说明测试目的







