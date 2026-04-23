# Crushe AI Benchmark

每次迭代后，告诉 Claude Code："帮我用测试 agent 测试一下[功能/策略]"，Claude 会自动读取这里的测试说明，选 case、执行测试、生成报告。

## 快速开始

1. 确认服务已启动（如果没有先启动）：
   ```
   python3 .trae/skills/service-manager/scripts/start_services.py --mode dev
   ```

2. 告诉 Claude Code 你做了什么改动，让它帮你测：
   - "我改了 respond 的提示词，测试一下策略质量"
   - "我更新了 onboarding 流程，全测一下功能"
   - "发版前全量回归一遍"

3. Claude 会自动执行测试，把报告保存到 `reports/` 目录

---

## Cases 说明

### 场景级 Cases（scene_cases/）

每个 case = 某个具体场景的 3-5 轮对话，用于快速验证。

| Case | 场景 | 测试什么 |
|------|------|---------|
| scene_001 | 首次使用 onboarding | onboarding interrupt 流程是否正常 |
| scene_002 | 上传聊天截图分析 | 截图处理 + 分析是否利用 crush 画像 |
| scene_003 | 制定约饭行动计划 | plan_agent 是否被正确调用，计划是否具体可用 |
| scene_004 | 约会被拒后处理 | 情绪安慰是否先于策略，策略是否合理 |
| scene_005 | 多轮补充 crush 信息 | 分析是否随信息积累变得更准确 |
| scene_006 | 发消息没回的焦虑 | 情绪疏导 + 等待策略是否正确 |

### 旅程级 Cases（journey_cases/）

每个 case = 完整用户旅程，8-20 轮，耗时约 10-20 分钟。建议发版前才跑。

| Case | 场景 | 轮数 |
|------|------|------|
| journey_001 | 大学生暗恋同班同学（完整追求旅程） | 8 轮 |

### 真实用户 Cases（real_cases/）

基于真实用户数据构建，使用双 AI 模拟：**用户AI** 扮演真实用户使用产品，**crush AI** 模拟 crush 的反应。每个 case 包含完整的用户/crush 画像（从真实聊天记录推断），以及真实截图。

| Case | 用户 | 场景 | 核心考察 |
|------|------|------|---------|
| real_001 | 棒棒糖（18F） | 排球场认识，"兄弟式逼问"后 crush 退缩 | 分析逼问伤害 + 排球场景行动计划 |
| real_002 | Aliuman（15F） | 同班同学，需求感过强 | 识别"需求感过强"并给出降温策略 |
| real_003 | 14th/iiu14（19F） | 多次见面但被卡在友谊区 | 制造稀缺感 vs 继续追问的策略判断 |
| real_004 | 星月（24F） | 网恋对象发骚扰内容后消失一个月 | 保持框架 + 等待 vs 主动联系的判断 |

**双 AI 模拟机制**：
- `role: user_ai`：按用户画像和 `product_flow_guide` 指令扮演用户，上传真实截图，跟随小话的策略
- `role: crush_ai`：按 crush 画像扮演 crush，模拟用户执行策略后 crush 的实际反应
- 每个 real case 的 `product_flow_guide` 章节包含：产品操作流程说明 + 截图上传指引

---

## 按迭代类型选 Cases

| 改了什么 | 用 scope | 对应 cases |
|---------|---------|-----------|
| 提示词/策略 | strategy | scene_002, 003, 004, 005, 006, journey_001, real_001~004 |
| onboarding 流程 / interrupt | feature | scene_001, 003, real_001~004 |
| 工作流路由/节点 | workflow | scene_001, 003 |
| 发版前全量 | full | 全部 |

---

## 维护 Cases

Cases 是 YAML 格式，可以直接编辑，不需要改代码。

### 新增一个 case

1. 在 `cases/scene_cases/` 或 `cases/journey_cases/` 下新建文件
2. 参考已有 case 的格式，填写字段
3. `test_account` 从 TEST_USERS.md 里分配一个未被其他 case 使用的账号
4. `scope` 选 feature / strategy / workflow（可多选）

### 新增测试账号

当前分配规则：
- `test200-205`：scene_cases
- `test206-209`：real_cases（real_001=206, real_002=207, real_003=208, real_004=209）
- `test220-229`：journey_cases
- `test230+`：临时

密码统一：见 TEST_USERS.md（test200+ 批次为 `69779346`）

---

## 报告

测试报告自动保存到 `reports/` 目录，Markdown 格式，可直接在 IDE 或 GitHub 查看。

文件名格式：`report_YYYYMMDD_HHMMSS.md`
