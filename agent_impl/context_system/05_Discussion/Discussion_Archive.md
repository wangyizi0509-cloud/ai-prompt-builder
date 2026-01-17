# Layer Specs 讨论记录归档

> 历史讨论与决策记录，仅供参考。部分字段名称可能与最新规范不一致，**请以最新规范为准**。

---

## 📊 各层讨论进度

| Layer | 状态 | 规范文档 | 待讨论项 |
|:------|:-----|:--------|:--------|
| **Layer 1** | ✅ 基本完成 | `../02_Specs/layer1_spec_v1.0.md` | 无（可开始实现） |
| **Layer 2** | ✅ 基本完成 | `../02_Specs/layer2_spec_v1.0.md` | 无（可开始实现） |
| **Layer 3** | ✅ 基本完成 | `../02_Specs/layer3_spec_v1.0.md` | 无（可开始实现） |
| **任务系统** | ✅ 基本完成 | `../02_Specs/task_system_spec.md` | 无（可开始实现） |
| **上下文组装** | ✅ 基本完成 | `../02_Specs/context_assembly_spec.md` | 无（可开始实现） |

---

## 📋 Layer 1 讨论记录

### 已确定的设计决策

#### 存储结构
1. 从"字符串拼接"改为"**原子记忆列表**"
2. 每条原子记忆独立存储，带有 `id`、`content`、`created_at`、`source_type`、`confidence`

#### 原子记忆粒度（按来源类型区分）
- **用户提供**：按属性拆分（一个属性一条）
- **客观事实**：按事件拆分（一个事件一条）
- **AI分析**：按结论拆分（一个推断一条）

#### 时间处理
- 存储精度：年-月-日-时（如 `2026-01-13T14`）
- 输出精度：省略年（如 `01-13 14:00`），除非跨年

#### 输出格式
紧凑列表格式，顶部有可靠性说明：
```markdown
## 情报概览
> 信息可靠性：事实 > AI分析 > 用户提供。

### 用户
- [01-12 09:00/AI] 依恋类型：焦虑型
- [01-10 14:00/事实] 朋友圈发了健身照
- [01-10 10:00/用户] 姓名：小明
```

#### 排序规则
时间倒序，同时间按来源优先级（事实 > AI > 用户）

#### 写入逻辑（重点）

| 规则 | 决策 |
|:----|:----|
| **去重规则** | 用 LLM 做语义判断，相似则不写入 |
| **用户提供更新** | 直接覆盖（LLM 判断同属性） |
| **AI 分析更新** | 同维度覆盖（LLM 判断同维度） |
| **客观事实** | 全量追加，不覆盖 |

#### 长短期分流（关键设计）

客观事实写入时，LLM 判断是长期还是短期：
- **长期事实**（如"Crush 是独生女"）→ 写入 **Layer 1**
- **短期事实**（如"下周要出差"）→ 写入 **Layer 2 动态情报板**

#### AI 分析排除列表

以下分析维度**不写入 Layer 1**（避免与现状报告重复）：
- 关系阶段（L1-L4/T1-T3）
- ACR 三维分析
- 核心问题/风险点

### Layer 1 讨论状态：✅ 完成

详细规范见 `../02_Specs/layer1_spec_v1.0.md`

---

## 📋 Layer 2 讨论记录

### 已确定的设计决策

#### 动态情报板 (DynamicIntel)
- 存储永不删除，提取时过滤过期
- 提取 Top-20，按过期时间排序
- 输出：创建时间 + 内容 + 置信度（含原因）
- 数据来源：与 Layer 1 共享分流节点（对话提取）

#### 现状报告 (StatusReport) & 行动规划 (ActionPlan)
- 存储：全量保留
- 写入：修改不归档，新建则归档
- 提取：当前完整 + 2份 summary + 3份 one_liner
- 输出：报告正文用 `"""` 包围，避免 Markdown 层级冲突
- 归档：由 Organize Agent 生成 summary 和 one_liner

#### 行动指南 (ActionGuide)
- 状态机：pending / in_progress / paused / completed / cancelled / expired
- 创建时默认 in_progress
- 提取限制：in_progress≤2, paused≤2, pending≤3, completed≤5, cancelled/expired各≤2
- 用户完成时：触发 Organize Agent 生成摘要 + 提取 Layer 1 信息
- 输出：in_progress 完整展开，paused/pending/completed 展示 summary，其他 one_liner

### Layer 2 讨论状态：✅ 完成

详细规范见 `../02_Specs/layer2_spec_v1.0.md`

---

## 📋 Layer 3 讨论记录

### 已确定的设计决策

#### 整体架构
- **历史摘要**: 压缩后的远古对话，最多 5 条
- **任务笔记**: 当前任务的推理结论，最多 8 条
- **最近对话**: 滑动窗口 25 轮

#### 砍掉 thought，强化 reasoning notes
- **thought**: ❌ 不进对话历史
- **reasoning notes**: ✅ 保留，硬性截断最新 8 条
- **写入触发**: 重要推断 / 策略决策 / 阶段进展 / 排除假设

#### 用户消息处理
- **普通文本**: 原样保留
- **聊天记录**: 全量保留 → 压缩时提取到 Layer 1/2
- **图片上传**: 全量 + 标注 `【图片解析】`
- **回答提问**: `Q1: xxx / Q2: xxx` 格式 + 补充拼接

#### AI 消息处理
- **普通回复**: 只抽取 `response` 字段
- **提问卡片**: 只保留问题文本（极简格式）
- **子 Agent 产物**: 不进历史，只存 Layer 2
- **系统通知**: 保留，用 `[S]` 标记

#### 输出格式
- **格式**: Markdown + 时间戳（比 XML 省 ~100 tokens）
- **角色标记**: `[U]` 用户 / `[A]` AI / `[S]` 系统
- **时间戳**: `MM-DD HH:mm`，跨年补年份

#### 其他决策
- **压缩触发**: 按轮次（25 轮）
- **摘要数量**: 最多 5 条
- **topics**: 自由文本
- **任务切片**: 不做，全局摘要

### Layer 3 讨论状态：✅ 完成

详细规范见 `../02_Specs/layer3_spec_v1.0.md`

---

## 📋 任务系统讨论记录

> **状态**：✅ 已完成，详见 `../02_Specs/task_system_spec.md`

### 🔴 新窗口必读（上下文加载清单）

开始讨论任务系统前，请先读取以下文件了解现状：

#### 1. 核心类型定义（必读）

| 文件 | 重点内容 | 行号参考 |
|:----|:--------|:--------|
| `agent_impl/graph/context_types.py` | `TaskState`、`AgentTaskRegistry`、`BoundActionGuide` | 284-336 |

**现有 TaskState 字段**：
```python
TaskState = {
    "task_id": str,           # 任务标识
    "summary": str,           # 任务摘要
    "status": "pending" | "active" | "completed",
    "reasoning": list[str],   # 思考笔记（已在 Layer 3 规范中调整为最多 8 条）
    "started_at": str,
    "completed_at": str,
    "is_active": bool,        # 向后兼容
    "bound_action_guides": list[BoundActionGuide],  # 绑定的行动指南
}
```

#### 2. 现有任务工具实现（必读）

| 文件 | 说明 |
|:----|:----|
| `agent_impl/graph/tools/task_tools.py` | 任务管理工具：`switch_task`、`create_task`、`append_task_note` |
| `agent_impl/graph/tools/guide_bind_tools.py` | 行动指南绑定工具 |

**现有工具**：
- `switch_task`: 切换到已存在的任务
- `create_task`: 创建新任务并设为活跃
- `append_task_note`: 追加思考笔记

#### 3. 上下文注入逻辑（参考）

| 文件 | 说明 |
|:----|:----|
| `agent_impl/graph/context_builder.py` | 查看 `_get_task_registry_from_state()`、`_get_current_task_id()` |

#### 4. 相关策略文档（参考）

| 文件 | 说明 |
|:----|:----|
| `../03_Strategies/Storage_Strategy/storage_schema_v1.0.md` | 4.4-4.5 节有 TaskState 存储 schema |
| `../02_Specs/layer3_spec_v1.0.md` | Layer 3 规范（与任务系统紧密相关） |

---

### 任务系统定位

任务系统是「工具/服务」层，不是数据层。它的作用是：
- **被 Agent 调用**：Agent 决定当前任务是什么、需要哪些上下文
- **管理任务状态**：创建/切换/完成任务
- **动态加载上下文**：根据 Agent 指令，从 Layer 2/3 拉取对应数据

### 架构位置

```
Agent（决策者）
    │
    │ 调用：当前任务是 X，需要指南 A、笔记 B
    ▼
任务系统（服务层）
    │
    │ 读取/写入
    ▼
存储层（Task Store + Layer 2/3）
```

### 已确认的设计决策

| 维度 | 决策 |
|:----|:----|
| **任务归属** | 各 Agent 独立维护任务列表 |
| **任务状态机** | 保持 `pending / active / completed`，不增加 |
| **BoundContext** | 通用绑定结构，支持任意 type，按 type 分别设上限 |
| **task_id** | 改为短 UUID + title 字段 |
| **任务颗粒度** | 一个任务 = 一个用户意图的完整解决过程 |
| **切回匹配** | Agent 自行判断（看任务列表 title） |
| **任务列表展示** | 最近 5 个非 completed + 3 个 completed |
| **completion_summary** | 任务完成时生成结论摘要 |
| **清理策略** | 后台永久保留，不清理（注入有数量限制即可） |

### 规范文档位置

`../02_Specs/task_system_spec.md`

---

## ⚠️ 重要注意事项

### 用户偏好
- 用户是 AI 产品经理，**不太懂代码**，用产品语言沟通
- 用户希望你在不确定时**先反问确认**，确保理解需求后再执行
- 用户重视**省 Token**，输出格式要尽可能紧凑

### 设计原则
- **最小颗粒**：原子记忆不要合并，保持独立
- **时间追溯**：每条信息都要有时间戳
- **可靠性透明**：输出时要让模型知道信息的可靠性

### 代码位置
- 类型定义：`agent_impl/graph/context_types.py`
- 上下文组装：`agent_impl/graph/context_builder.py`
- 归档管理：`agent_impl/graph/archive_manager.py`
- 存储策略：`agent_impl/graph/storage_strategy.py`

---

## 📁 相关文档

| 文档 | 说明 |
|:----|:----|
| `../99_Deprecated/context_architecture.md` | 整体数据流架构 |
| `../99_Deprecated/context_engineering_v3.1.md` | 旧版工程细节 |
| `../99_Deprecated/context_strategy_v3.1.md` | 旧版策略总览 |

---

## 📝 变更记录

| 日期 | 变更内容 |
|:----|:--------|
| 2026-01-14 | 创建 README，完成 Layer 1 基础规范 |
| 2026-01-14 | 完成 Layer 2 规范（动态情报板/现状报告/行动规划/行动指南） |
| 2026-01-14 | Layer 1 增加 confidence_reason 字段 |
| 2026-01-14 | 添加任务系统待讨论清单（Layer 3 后讨论） |
| 2026-01-15 | 完成 Layer 3 规范（对话历史/任务笔记/输出格式） |
| 2026-01-15 | 完成任务系统规范（BoundContext/颗粒度规则/状态机/归档策略） |
| 2026-01-15 | 完成上下文组装规范（组装顺序/KV Cache优化/格式规范） |

---

*最后更新: 2026-01-15*

