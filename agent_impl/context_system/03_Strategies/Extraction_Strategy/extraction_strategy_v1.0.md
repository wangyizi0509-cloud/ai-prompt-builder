# 上下文提取策略 (Extraction Strategy) v1.1

## 1. 核心理念：动态组装，信噪比最大化

提取策略的目标是在有限的 Context Window (Token 预算) 内，根据当前 Agent 的**意图 (Intent)**，动态组装最相关的信息。我们不追求"全量记忆"，而是追求"当前最有用"。

---

## 2. Token 预算分配

> 总预算基准：~70,000 tokens（适用于 Claude 3.5 / GPT-4o 等主流模型）
> 
> 与 `context_assembly_spec.md` 保持一致。

| 模块 | 预估 Tokens | 说明 |
| :--- | :--- | :--- |
| **Layer 0 (System)** | ~4k | 人设、核心理论 (ACR/LT)、基础指令 (固定) |
| **Layer 1 (Profile)** | ~15k | 3×3 矩阵核心画像 (懂用户、懂Crush) |
| **Layer 2 (Working)** | ~20k | 现状报告、规划、**动态情报**、未完成指南 |
| **Layer 3 (Chat)** | ~15k | 最近 25 轮对话 + 历史摘要 |
| **预留输出** | ~8k | 模型生成空间 |
| **弹性空间** | ~8k | 工具结果、OCR内容、临时推理 |
| **总计** | ~70k | 总预算基准 |

---

## 3. 通用提取流水线 (General Pipeline)

所有 Agent 的 Context 组装都遵循以下基础顺序（优先级从高到低）：

1.  **System Prompts (L0)**: 
    *   注入 `Role Persona` (小话)。
    *   注入 `Core Theory` (ACR/LT 坐标系)。
    *   注入当前时间。

2.  **Working Context (L2)**:
    *   **必选**: 最新N条的**完整** `StatusReport` (现状分析报告)。
    *   **必选**: 最新N条的**完整** `ActionPlan` (行动规划书)。
    *   **必选 (High Priority)**: **`Dynamic Intel` (动态情报板)** —— *确保 AI 知道当下的紧急日程或状态。*
    *   **必选（渐进式披露）**:
        *   `status="in_progress"`：完整展开（当前执行中的指南）。
        *   其他状态（pending/paused/completed/cancelled/expired）：仅注入元数据表格（id/title/status/one_liner），需要详情时通过工具按需加载。
    *   **历史回溯 (History Fallback)**:
        *   除当前最新的 N 条外，历史最近的 M 条 `StatusReport`/`ActionPlan`/`ActionGuide` 使用 `Summary` (中等摘要)。
        *   更早的历史记录使用 `one_liner` (一句话摘要)。
        *   *注: N和M支持配置化。*

3.  **Static Profile (L1)**:
    *   **注入 Layer 1 的 3×3 矩阵全部内容** (User/Crush/Both × Fact/User/AI)。

4.  **Conversation History (L3)**:
    *   注入最近 N 轮对话。
    *   注入相关的 `ConversationSummary`。

---

## 4. [Pending] 场景化提取配置 (Agent-Specific Profiles)
> **注意**: 以下场景化逻辑为未来规划，当前版本暂不实现，统一使用通用流水线。

### 4.1 场景 A：日常陪伴 / 咨询 (Chat/Inquiry)
*   **目标**: 情感共鸣、建立信任、信息收集。
*   **策略调整**:
    *   **Layer 2 侧重**: 重点读取 **`Dynamic Intel`** (如"昨晚刚吵架")，确保回复不踩雷。
    *   **Layer 3 权重增加**: 拉取更多历史对话 (25+ 轮)，确保聊天不"断片"。
    *   **Layer 1 侧重**: 重点加载 `Both Info` (相处细节) 和 `User Provide` (用户感受)。

### 4.2 场景 B：深度分析 / 规划 (Analysis/Plan)
*   **目标**: 准确诊断、制定战略。
*   **策略调整**:
    *   **Layer 1 权重增加**: **全量加载** `Fact` 列 (截图、硬证据) 和 `CrushChatSummary`。
    *   **Layer 2 侧重**: 加载所有历史报告的 `Summary` (由 `Archiver` 提供的历史脉络)。
    *   **工具结果**: 预留较大空间给 `Search` 或 `OCR` 的原始结果。

### 4.3 场景 C：行动指南生成 (Guide)
*   **目标**: 具体、可执行、符合人设。
*   **策略调整**:
    *   **Layer 2 核心**: 严格对齐 `ActionPlan` (大战略) 和 **`Dynamic Intel`** (避开对方忙碌时间/利用对方心情好的时机)。
    *   **Layer 1 过滤**: 重点读取 `User Info` 中的性格/能力 (判断是激进派还是保守派)，确保建议可执行。
    *   **Layer 3 精简**: 仅需最近 5 轮对话确认当前意图，节省空间给 Prompt 的 Few-Shot 示例。

---

## 5. 提取与组装机制

### 5.1 组装器 (Context Builder)
`Context Builder` 是执行上述策略的代码模块。

*   **输入**: `Target Agent`, `Current State`, `Token Limit`
*   **过程**:
    1.  加载 Layer 0。
    2.  根据 Agent 类型选择 L1/L2/L3 的提取配置 (`ExtractionConfig`)。
    3.  并行获取各层数据。
    4.  **动态情报注入**: 检查 L2 `Dynamic Intel`，过滤已过期条目，将有效条目置顶注入 Context。
    5.  按优先级裁剪 (Trimming)。
*   **输出**: 最终送入 LLM 的标准 `messages` 列表（SystemMessage + Context XML + History）。

### 5.2 检索增强 (RAG) - 规划中
对于超出 Context Window 的长期记忆（如半年前的聊天细节）：
*   不直接加载到 Context。
*   通过 `Tool Call` (如 `search_memory(query)`) 按需调取，调取结果作为 `Tool Message` 插入当前对话流。

