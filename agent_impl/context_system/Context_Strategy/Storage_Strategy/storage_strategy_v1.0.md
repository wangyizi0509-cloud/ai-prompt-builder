# 上下文存储与提纯策略 (Storage & Refining Strategy) v1.4

## 1. 核心理念

我们采用 **"双模态处理"** 机制：
1.  **同步落库 (Sync Storage)**：追求**极速**。所有数据第一时间存入原生层级 (Native Layer)，确保交互不阻塞。
2.  **异步提纯 (Async Refining)**：追求**深度**。后台回路从原生数据中提取知识，沉淀为静态情报 (L1) 或动态情报 (L2)。

---

## 2. 详细存储与提纯策略 (Detailed Strategy by Source)

### 2.1 来源：交互信息流 (Interaction Stream)
> **定义**: 包括用户发送的文本、上传的图片(OCR)、回答的问题(Q&A) 以及 AI 的回复。

#### 【同步落库 (Sync Storage)】
*   **目标层级**: **Layer 3 (Conversation History)**
*   **目标字段**: `all_messages` (List)
*   **写入动作**: **Append (追加)**
*   **数据结构**: 
    *   保留 OpenAI Message 格式。
    *   **可选字段**: `source_type` (默认 "text", 可选 "ocr")。

#### 【异步提纯 (Async Refining)】
*   **触发时机**:
    1.  **对话压缩时 (On Compression)**: 当 L3 达到轮次上限，触发归档压缩时。
    2.  **初始流程结束时 (On Onboarding Finish)**: 用户完成首次信息录入流程时。
*   **执行角色**: **Organize Agent (整理员)**
*   **提纯逻辑**:
    *   **场景 A (压缩时)**: 读取 Layer 3 中**即将被压缩/移除**的那部分对话片段。
    *   **场景 B (初始流程结束时)**: 读取 Layer 3 中的**全量**对话记录。
    *   **通用动作**:
        *   **To Layer 1**: 提取长效画像 (User/Crush/Both) 和事实 (Fact)。有证据存 `Fact`，无证据存 `User Provide`，推断存 `AI 
        Provide`。*注: OCR 内容通常含高置信度 Fact。*
        *   **To Layer 2**: 提取时效性情报 (Dynamic Intel)，如"下周出差"。

---

### 2.2 来源：AI 报告 (Status Reports / Action Plans)
> **定义**: 系统生成的深度分析文档，如《现状分析报告》、《行动规划书》。

#### 【同步落库 (Sync Storage)】
*   **目标层级**: **Layer 2 (Working Context)**
*   **目标字段**: `status_reports` 或 `action_plans` (List)
*   **写入动作**: **New Version (新增版本)**
*   **数据结构**: 
    *   `content`: 完整 Markdown 内容
    *   `created_at`: 时间戳
    *   `is_current`: **True** (同时将列表里上一份报告设为 False)

#### 【异步提纯 (Async Refining)】
*   **触发时机**: **生成后立即触发**。
*   **执行角色 A**: **Archiver (归档员)**
    *   **逻辑**: 锁定**上一份**同类型报告，调用 LLM 生成 `summary` (150字) 和 `one_liner` (20字)。
    *   *Destination*: 更新旧报告对象的 `summary` 字段。
*   **执行角色 B**: **Organize Agent (整理员)**
    *   **逻辑**: 分析新报告的结论 (Conclusion)，提取关键的关系定性。
    *   *Destination*: **Layer 1 (3×3 矩阵)** -> `AI Provide` 列 (如"当前关系阶段: L2")。

---

### 2.3 来源：行动指南 (Action Guides)
> **定义**: AI 给出的具体任务建议 (To-Dos)，以及用户的执行反馈。

#### 【同步落库 (Sync Storage)】
*   **目标层级**: **Layer 2 (Working Context)**
*   **目标字段**: `action_guides` (List)
*   **写入动作**: 
    *   *生成时*: **Append** (状态为 `pending`)。
    *   *反馈时*: **Update Status** (状态改为 `completed`，并追加 `feedback` 字段)。

#### 【异步提纯 (Async Refining)】
*   **触发时机**: **用户标记完成 (Completed) 时**。
*   **执行角色**: **Organize Agent (整理员)**
*   **提纯逻辑**:
    1.  **分析执行力**: 用户是否照做了？做得怎么样？
        *   *Destination*: **Layer 1** -> `User Info` (如"执行力强"、"容易退缩")。
    2.  **分析对方反馈**: Crush 对这个行动有什么反应？
        *   *Destination*: **Layer 1** -> `Crush Info` -> `Fact` (如"Crush接受了邀约")。
    3.  **更新动态态势**:
        *   *Destination*: **Layer 2 (Dynamic Intel)** (如"刚刚完成破冰，气氛缓和")。

---

## 3. 端到端示例 (E2E Case Study)

**场景**: 用户上传了一张聊天截图，Crush 说 "下周三我去上海展会，票给你留一张？"。

**Step 1: 同步落库 (Sync)**
*   OCR 识别出文字。
*   `StorageRouter` 将消息存入 **Layer 3**:
    ```json
    {
      "role": "user",
      "content": "下周三我去上海展会，票给你留一张？",
      "source_type": "ocr"
    }
    ```
*   AI 回复: "这是个极好的机会！快答应..." (存入 Layer 3)

**Step 2: 对话继续 (积累轮次)**
*   用户继续聊了 20 轮，Layer 3 达到上限，触发**压缩**。

**Step 3: 异步提纯 (Refining)**
*   **Organize Agent** 被唤醒，读取包含上述截图的对话片段。
*   **提取动作**:
    1.  **Fact (L1)**: "Crush 工作涉及展会/出差" -> 存入 Layer 1 `Crush Info`.
    2.  **Dynamic Intel (L2)**: "下周三(具体日期) Crush 去上海展会，且邀请了用户" -> 存入 Layer 2 `Dynamic Intel Board` (设置有效期至下周四)。

**Step 4: 价值闭环 (Consumption)**
*   到了下周一，用户生成《行动指南》。
*   AI 读取 **Layer 2 Dynamic Intel**，发现 "周三有上海展会邀约"。
*   生成建议: "周三见面时，记得带上..."。
## 3. 提纯回路 (Refining Loop) 架构总结
### 3.1 核心原则
*   **副作用 (Side Effect Only)**: 提纯操作永远**只增加/更新** L1 和 L2 Intel，**
绝不删除** L2/L3 的原始记录。
*   **去重 (De-duplication)**: Organize Agent 在写入 L1 时，负责合并同类项，避免信
息冗余。
### 3.2 目标位置定义
*   **Layer 1 Static Info**: 所有的"属性"、"画像"、"历史事实"。 (User/Crush/
Both × Fact/User/AI)
*   **Layer 2 Dynamic Intel**: 所有的"日程"、"状态"、"短期态势"。 (必须带有效期)
*   **Layer 2 Archive**: 所有的"历史报告摘要"。