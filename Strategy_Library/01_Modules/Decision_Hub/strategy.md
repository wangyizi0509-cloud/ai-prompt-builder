# 决策中枢策略文档 (Decision Hub Strategy)

## 1. 模块定义 (Module Definition)

### 1.1 定位
决策中枢 (Decision Hub) 是 Crushe 系统的**调度核心与神经中枢**。

### 1.2 核心机制
*   **纯旁路监听 (Pure Side-channel Listener)**：
    *   模块**不响应**用户的显式指令（如“帮我分析”、“下一步怎么做”）。
    *   模块**仅监听**用户在其他功能模块（如聊天分析、咨询、情报中心）中的输入流与交互数据。
*   **事件驱动 (Event-Driven)**：仅当输入流中出现具有战略意义的“变量 (Variables)”时被激活。
*   **最小干扰 (Minimal Intervention)**：
    *   默认状态：静默 (Output Null)。
    *   激活状态：仅在需要触发系统级变更时输出指令。

## 2. 核心职责 (Core Responsibilities)

### 2.1 监测 (Monitor)
作为后台哨兵，实时分析 User Input + System Context 的动态匹配度。

### 2.2 评估 (Evaluate)
基于信息增量，计算当前输入对系统状态的**冲击等级**。判断是维持现状、局部修补，还是推倒重来。

### 2.3 路由 (Route) - 4+1 卫星架构
根据评估结果，将指令分发至不同层级的处理单元。

#### A. 状态与档案 (Status & Profile)
1.  **Status Refiner (情感罗盘微调)**: 负责 L/T 坐标和状态描述的微调。
2.  **Profile Tweaker (全维档案微调)**: 负责用户/Crush 画像事实的增量补充。
3.  **Status Analysis (主模块)**: *仅在 Level 1 颠覆性变化时调用，进行全量重写。*

#### B. 行动指南 (Action Guide)
1.  **Action Refiner (行动指南微调)**: 负责当前 SOP **内容**的修补（改时间、插队临时任务），**不推进进度**。
2.  **Next Step Decider (下一步行动决策)**:
    *   *特殊机制*: **工程强制路由**。
    *   当 `next_action = true` 时（用户反馈结果或强制推进），直接路由至此模块，决策下一步意图。
3.  **Action Guide Gen (主模块)**: 接收 Next Step Decider 的意图，生成完整 SOP。

## 3. 决策逻辑模型 (The Logic Model)

### 3.1 判断流程表 (Decision Matrix)

| 维度 | 场景示例 | 判定 (Impact) | 路由 (Route) | 触发指令 |
| :--- | :--- | :--- | :--- | :--- |
| **Status (L/T)** | 关系升温/降温、误会解除。 | 状态微调 | **Status Refiner** | `status_update: REFINE` |
| **Profile (Info)** | 发现新爱好、生日、雷点。 | 事实补充 | **Profile Tweaker** | `profile_update: TRUE` |
| **Action (Content)** | 改时间、临时问答、客观受阻。 | 内容修补 | **Action Refiner** | `action_update: REFINE` |
| **Critical** | 拉黑、非单身、表白失败。 | 战略重置 | **Status Analysis** | `status_update: REWRITE` |
| **Noise** | 纯情绪发泄、无关闲聊。 | 无效信息 | **Null** | `null` |

> *注：Next Step Decider 不在上述逻辑中，它由 `next_action` 参数独立控制。*

## 4. 接口定义 (Interface Specification)

### 4.1 Input Schema
```json
{
  "user_id": "string",
  "crush_id": "integer",
  "new_info": "string", // 用户最新输入
  "next_action": "boolean" // 工程信号：是否强制触发下一步决策
}
```

### 4.2 Output Schema
```json
{
  "analysis": "string", // 思考链
  "routing": {
    "status_route": {
      "target": "NONE" | "MAIN_MODULE" | "SATELLITE_REFINER",
      "action": "REWRITE" | "REFINE",
      "payload": "string" // 变更点摘要
    },
    "profile_route": {
      "target": "NONE" | "SATELLITE_TWEAKER",
      "action": "UPDATE",
      "payload": "string" // 新事实摘要
    },
    "action_route": {
      "target": "NONE" | "SATELLITE_REFINER", // 注意：Next Step Decider 由工程接管，不在此路由
      "action": "REFINE",
      "payload": "string" // 修补指令摘要
    }
  }
}
```

## 5. 待解决问题 (Issues)
*   [ ] **并发冲突**：如果 Profile 更新和 Status 更新同时发生，如何确保数据一致性？（目前由工程层并行处理）。
*   [ ] **Next Action 逻辑**：确认工程层是否会在调用 Decision Hub 之前或之后处理 `next_action`。目前设计假定：如果 `next_action=true`，工程会**同时**调用 Next Step Decider 和 Decision Hub（用于检查其他副作用），或者 Decision Hub 的 Output 中不需要包含 Next Step 的路由，只需关注其他 Side Effects。
