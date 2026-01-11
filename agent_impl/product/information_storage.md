# 信息存储模块梳理 (Information Storage)

## 1. 核心存储理念：分层金字塔 (Layered Architecture)
采用 **"分层长期记忆架构"**，将用户信息划分为三个层级。每一层都有独立的数据结构、生命周期和更新策略。

---

## 2. 存储详情 (Storage Detail)

### 第一层：静态情报 (Layer 1 - Static Intelligence)
> **定位**：军师决策的"地基"。存储长期不变、高信度的属性数据。

#### 2.1 数据结构 (Schema)
采用 **3×3 矩阵结构**（3大对象 × 3种来源），支持信息来源追溯。

| 字段 (Root Field) | 类型 | 说明 | 内部结构 (Internal Structure) |
| :--- | :--- | :--- | :--- |
| `user_info` | Object | 我方情报 | `{ "user_provide": "...", "fact": "...", "ai_provide": "..." }` |
| `crush_info` | Object | 对方情报 | `{ "crush_name": "...", "user_provide": "...", "fact": "...", "ai_provide": "..." }` |
| `both_info` | Object | 关系情报 | `{ "user_provide": "...", "fact": "...", "ai_provide": "..." }` |

*注：每个情报对象内部都包含三个维度的来源字段（Source），构成了 3(对象) × 3(来源) 的矩阵。*

#### 2.2 更新策略 (Update Policy)
*   **分字段存储 (Field Segregation)**：每个情报单元都由 `user_provide` / `fact` / `ai_provide` 三个独立字段组成，不进行物理合并。
*   **使用逻辑 (Usage Logic)**：在决策时，系统按 **Fact > AI > User** 的优先级选用信息。例如：用户说自己"很幽默"(User)，但聊天记录显示"很尬"(Fact)，系统采信 Fact。
*   **冲突解决**：不同来源的数据并存，而非覆盖。

---

### 第二层：工作上下文 (Layer 2 - Working Context)
> **定位**：军师的"办公桌"。存储当前生效的战略、战术及反馈。

#### 2.1 现状与规划 (Status & Plan)
支持**版本回溯**与**原地微调**。

| 字段 (Field) | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | UUID | 唯一标识 |
| `is_current` | Bool | **是否当前生效** |
| `stage` | String | L/T 阶段 |
| `stage_description` | String | 阶段描述 |
| `report_content` / `plan_content` | Markdown | 完整分析报告/规划 |
| `acr_analysis` | Object | A/C/R 三维评分 (StatusReport 专用) *[Pending Implementation]* |
| `key_issues` / `risk_points` | List | 核心问题与风险点 (StatusReport 专用) *[Pending Implementation]* |
| `goal` / `strategy` | String | 目标与策略 (ActionPlan 专用) |
| `phases` | List | 分阶段计划 (ActionPlan 专用) |
| `one_liner` | String | 一句话摘要 |
| `summary` | String | 中等摘要 |

*   **更新策略 (Update Policy)**：
    1.  **换代 (Archive Mode)**：当战略阶段发生根本改变（如 L2 -> L3），原记录 `is_current` 置为 `False`，**新增**一条记录 `is_current` 置为 `True`。
    2.  **微调 (Patch Mode)**：当仅修正细节（如补充一个风险点），**原地更新**当前记录的内容字段，ID 不变。

#### 2.2 行动指南 (Action Guide)
拥有独立状态机的任务实体。

| 字段 (Field) | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | UUID | 任务ID |
| `title` | String | 任务标题 |
| `status` | Enum | **任务状态** (见下文) |
| `guide` | Object | **指南内容**：包含 `current_task`, `steps`, `talking_points`, `dos`, `donts` 等 |
| `created_at` | Timestamp | 生成时间 |

*   **任务状态机 (State Machine)**：
    *   `Pending` (待执行)
    *   `In_Progress` (执行中)
    *   `Paused` (已暂停) - *中途挂起，稍后继续*
    *   `Completed` (已完成) - *终态*
    *   `Cancelled` (已取消) - *终态*
    *   `Expired` (已过期) - *终态*

*   **更新策略**：由 Agent 决策修改 `status` 字段。非物理删除。

#### 2.3 动态情报 (Dynamic Intel)
短时效信息的公告板。

| 字段 | 说明 | 示例 |
| :--- | :--- | :--- |
| `content` | 情报内容 | "她本周五要出差去上海" |
| `expire_at` | **过期时间** | `2024-01-12 23:59:59` |
| `category` | 类型 | 日程 / 情绪 / 状态 / 意图 |

---

### 第三层：对话流 (Layer 3 - Conversation Stream)
> **定位**：军师的"流水账"。存储交互历史与思考过程。

#### 3.1 原始对话与摘要
*   **Raw Messages**: 存储 `User` 和 `Assistant` 的全量对话。
*   **Summaries**: 按轮次生成的压缩摘要，用于长期记忆检索。

#### 3.2 任务思考流 (Task Reasoning)
按**任务维度**切片的思考过程存储。

| 字段 (Field) | 类型 | 说明 |
| :--- | :--- | :--- |
| `task_id` | String | 任务唯一标识 (如 `analysis_20240109_01`) |
| `is_active` | Bool | **活跃状态**。`True` 表示当前聚焦的任务。 |
| `reasoning` | List[String] | 思考链列表 `[Step1, Step2...]`。用于记录 Chain-of-Thought。 |
| `summary` | String | (可选) 思考过程摘要 |

---

### 特殊存储：Crush 聊天记录库 (Evidence Base)
存储用户上传的证据，作为客观事实来源。

| 字段 | 说明 |
| :--- | :--- |
| `metadata` | 元数据：`{ "total_messages": 50, "chat_frequency": "high", ... }` |
| `summary` | 结构化摘要：`{ "key_events": [...], "main_topics": [...] }` |

*注：L1/L2 仅存储元数据和摘要。原始记录（如图片或文本）通常存储在外部系统或文件存储中，此处仅保留索引或引用。*
