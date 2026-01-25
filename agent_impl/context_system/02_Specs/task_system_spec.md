# 任务系统规范 v1.0

> **定位**：任务系统是 Agent 按需获取额外上下文的工具层，通过"任务"维度管理额外上下文的生命周期。

---

## 1. 核心概念

### 1.1 任务的定义

**一个任务 = 一个用户意图的完整解决过程**

任务是额外上下文的生命周期边界：
- 任务进行中 → 检索的上下文持续注入
- 任务切换 → 上下文卸载（不注入，但后台保留）
- 任务回来 → 上下文恢复注入

### 1.2 任务归属

**各 Agent 独立维护任务列表**，互不干扰：
- `main_agent`
- `status_agent`
- `plan_agent`
- `guide_agent`

存储位置：`layer3_memory.task_registry.{agent_name}`

---

## 2. 数据结构

### 2.1 TaskState（单个任务）

```python
TaskState = {
    # === 标识 ===
    "task_id": str,           # 唯一标识（短 UUID，如 "a1b2c3d4"）
    "title": str,             # 语义化标题（如 "判断Crush是否喜欢用户"）
    "summary": str,           # 摘要（20-30字，用于列表展示）
    
    # === 状态 ===
    "status": Literal["pending", "active", "completed"],
    
    # === 内容 ===
    "reasoning": list[str],   # 思考笔记（最多 8 条）
    "bound_contexts": list[BoundContext],  # 绑定的上下文
    
    # === 时间 ===
    "started_at": str,        # 开始时间 ISO
    "completed_at": str | None,  # 完成时间
    
    # === 归档 ===
    "completion_summary": str | None,  # 任务完成时的结论摘要（50-100字）
}
```

### 2.2 BoundContext（绑定的上下文）

通用结构，支持任意类型的上下文绑定。

```python
BoundContext = {
    # === 标识 ===
    "id": str,              # 绑定记录的唯一 ID（短 UUID）
    "type": str,            # 上下文类型（字符串，可扩展）
    "ref_id": str | None,   # 引用的资源 ID（用于去重，可选）
    
    # === 内容 ===
    "title": str,           # 标题（20-30字，用于列表展示）
    "content_md": str,      # Markdown 格式内容（注入 Prompt 用）
    
    # === 来源追溯 ===
    "source": str,          # 来源标识（格式：{方式}:{具体来源}）
    
    # === 生命周期 ===
    "bound_at": str,        # 绑定时间 ISO
    "expire_at": str | None,  # 可选过期时间（到期不注入，但保留）
}
```

#### 预定义 type 及上限

| type | 说明 | 上限 |
|:----|:----|:-----|
| `action_guide` | 行动指南 | 3 |
| `status_report` | 现状报告 | 1 |
| `action_plan` | 行动规划 | 1 |
| `crush_chat` | Crush 聊天记录片段 | 3 |
| `history_snippet` | 历史对话片段 | 3 |
| `dynamic_intel` | 动态情报 | 5 |
| `custom` | 自定义 | 3 |
| **默认** | 未定义 type | 3 |

#### source 格式约定

```
{触发方式}:{具体来源}
```

| 触发方式 | 说明 | 示例 |
|:--------|:----|:----|
| `tool` | Agent 调用工具绑定 | `tool:bind_action_guide` |
| `auto` | 系统自动提取绑定 | `auto:extract_from_screenshot` |
| `user` | 用户明确要求 | `user:remember_this` |

---

## 3. 任务状态机

```
pending ──→ active ──→ completed
   ↑           │
   └───────────┘
      (切换时)
```

| 状态 | 含义 | 触发条件 |
|:----|:----|:--------|
| `pending` | 创建但未激活 | 被其他任务切走时 |
| `active` | 当前活跃 | task_manager(action="create"/"switch") |
| `completed` | 已完成 | Agent 显式完成 |

**注意**：同一时刻只有一个 `active` 任务。

---

## 4. 任务颗粒度规则

### 4.1 判断流程

```
用户发来新消息
    │
    ▼
是否属于当前活跃任务的延续？
    │
    ├── 是 → 继续当前任务（不调用工具）
    │
    └── 否 → 是否与某个历史任务相似？
                │
                ├── 是 → task_manager(action="switch") 切回旧任务
                │
                └── 否 → task_manager(action="create") 创建新任务
```

### 4.2 判断标准

| 场景 | 判断 | 动作 |
|:----|:----|:----|
| 用户在**同一话题追问** | 继续 | 无需调用工具 |
| 用户**提出新问题/新需求** | 新任务 | `task_manager(action="create")` |
| 用户**回到之前聊过的话题** | 切回 | `task_manager(action="switch")` |
| Agent **主动推进**（生成报告/指南） | 继续 | 无需调用工具 |

### 4.3 颗粒度参考

```
✅ 好的颗粒度：
- "判断Crush对用户的态度"
- "帮用户准备周末约会"
- "分析用户被冷落的原因"

❌ 太细（会导致频繁切换）：
- "回答用户的第3个问题"
- "解读Crush的某条消息"

❌ 太粗（上下文会膨胀）：
- "帮助用户追到Crush"
- "解决用户的感情问题"
```

### 4.4 切回旧任务的匹配

Agent 自行判断，基于任务列表的 `title` 和 `summary`。

---

## 5. BoundContext 管理

### 5.1 去重与更新逻辑

```
当 Agent 绑定新的 BoundContext 时：

1. 如果 ref_id 为空 → 直接追加（不去重）
2. 如果 ref_id 不为空：
   - 检查现有列表是否有 同 type + 同 ref_id 的记录
   - 有 → 覆盖（更新 content_md、bound_at）
   - 没有 → 追加
3. 检查该 type 是否超过上限
   - 超过 → FIFO 淘汰最早绑定的（expire_at 不为空的优先淘汰）
```

### 5.2 expire_at 到期处理

**保留但不注入**：
- 到期的上下文不注入 Prompt，但后台保留
- 可手动续期恢复注入
- 不自动删除

### 5.3 注入时的排序

**按 type 分组 + 组内按 bound_at 倒序**

```markdown
## 任务绑定上下文

### 行动指南 (2)
- [01-15 14:00] 约会邀请话术指南
- [01-14 10:00] 破冰聊天指南

### Crush 聊天记录 (1)
- [01-15 13:00] 1月10日-1月14日的聊天片段
```

---

## 6. 任务列表展示

### 6.1 注入 Prompt 的限制

| 类别 | 数量 | 展示内容 |
|:----|:----|:--------|
| 非 completed 任务 | 最近 5 个 | title + summary |
| completed 任务 | 最近 3 个 | title + completion_summary |

### 6.2 展示格式

```markdown
## 任务列表

### 当前任务
- **判断Crush是否喜欢用户** [active]
  摘要：分析Crush最近的行为，判断对用户的态度

### 其他任务
| title | status | summary |
|-------|--------|---------|
| 周末约会准备 | pending | 准备周末约她吃饭的话术 |
| 破冰聊天 | completed | 结论：成功建立初步联系 |
```

---

## 7. 任务完成与归档

### 7.1 completion_summary

任务变成 `completed` 时，生成结论摘要（50-100字）：

```python
{
    "task_id": "a1b2c3d4",
    "title": "判断Crush是否喜欢用户",
    "status": "completed",
    "completion_summary": "结论：Crush 对用户有好感但比较被动，建议用户主动创造更多互动机会。关键证据：回复速度快但很少主动发起话题。"
}
```

### 7.2 存储策略

**后台永久保留，不清理**：
- 存储成本低
- 注入 Prompt 已有数量限制
- 历史任务可供参考

---

## 8. 工具清单

### 8.1 任务管理工具

| 工具 | 功能 | 参数 |
|:----|:----|:----|
| `task_manager` | 创建/切换/完成/追加笔记 | `action`, `task_id`, `title`, `summary`, `note` |

### 8.2 上下文绑定工具

| 工具 | 功能 | 参数 |
|:----|:----|:----|
| `context_loader` | load/bind/unbind/refresh 上下文 | `action`, `context_type`, `context_id`, `expire_at?` |

---

## 9. 变更记录

| 日期 | 版本 | 变更内容 |
|:----|:-----|:--------|
| 2026-01-15 | v1.0 | 初版规范，基于讨论确定核心设计 |

---

*最后更新: 2026-01-15*

