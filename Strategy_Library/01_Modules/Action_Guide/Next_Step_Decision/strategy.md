# 下一步决策策略文档 (Next Step Decision Strategy)

## 1. 模块定位
*   **角色**：流量分发器 / 路由 (Router)
*   **职责**：基于用户的当前状态和反馈，决定立刻要做的动作。

## 2. 核心策略逻辑 (Core Logic)

### 2.1 决策路由 (Routing Logic)
基于当前信息完整度和任务状态进行判断：
1.  **信息不足** -> 调用 [Pre_Question_Gen]。
2.  **信息充足** -> 调用 [Action_Guide_Gen]。
3.  **任务结束/反馈阶段** -> 调用 [Post_Question_Gen]。

### 2.2 决策因子
*   **现状分析结果**：L/T 坐标。
*   **上一任务反馈**：成功/失败/意外。

