# 前端展示技术方案（执行版）

> 需求文档：`agent_impl/docs/frontend_display_requirements_spec.md`  
> 版本：v3.0  
> 日期：2026-04-17  
> 适用对象：前后端开发、测试、项目负责人、0 上下文执行 AI  
> 执行要求：本文件定义本次改造的范围、阶段、技术约束和验收标准，执行时以本文件为准

---

## 一、项目目标

本次改造解决聊天区的 3 个核心问题：

1. 过程节点展示不全，或展示不完整
2. 节点顺序和实际生成顺序不一致，用户感知为乱序
3. 页面刷新、重新登录后，聊天区内容丢失，或与刷新前最终态不一致

本次改造完成后，聊天区必须具备以下能力：

1. 该展示的过程节点都能展示出来
2. 节点顺序稳定，不乱序
3. 刷新后与刷新前的最终态一致
4. 报告卡片与右侧面板联动一致
5. 输入锁定逻辑统一，在处理中或待回答提问时不能继续发送新消息

---

## 二、范围与阶段

## 2.1 本期必须完成

本期目标是先把主链路做稳定，必须完成：

1. Reasoning 节点展示
2. Tool Call 节点展示，并支持 `loading -> done/error` 原地更新
3. Subgraph Thinking 节点展示，本期允许桥接补发，不要求严格实时
4. Report Card 展示，并支持 `loading -> done` 原地更新
5. Inquiry Card 展示，并支持未答、已提交两种状态
6. AI Intermediate 节点展示
7. Final Response 展示
8. 所有节点有统一排序依据
9. 页面刷新或重新进入后，最终态与刷新前一致
10. 输入锁定逻辑统一
11. 报告卡片点击后跳到正确面板
12. 工具名称展示用户友好的中文或统一兜底文案
13. 聊天区展示收口到统一模型
14. 卡片状态更新采用原地更新，不跳位

## 2.2 本期明确不要求完成

本期不要求：

1. 子图思考逐条严格实时发射
2. 轮次折叠
3. Loading 动态轮播文案
4. 一次性删除所有旧兼容逻辑

## 2.3 下一期完成

下一期在本期稳定基础上继续做：

1. 子图思考逐条严格实时展示
2. 轮次折叠
3. Loading 动态文案等体验增强

下一期只能在本期展示模型、排序模型、持久化模型上继续演进，不允许推翻重做。

---

## 三、关键定义

## 3.1 新模型

新模型指统一展示节点模型。无论一个内容来自：

1. 实时流式事件
2. 最终返回结果
3. 历史恢复数据

都必须先转换成同一种“展示节点”结构，再进入前端渲染、排序和状态升级逻辑。

## 3.2 旧逻辑

旧逻辑指不同来源数据各走各的处理路径，例如：

1. `process_event` 直接往 `messages` 里插
2. `final.pending_responses` 再补一批
3. 历史恢复时走另一套映射和去重
4. 依赖文案截断、字符串猜测做去重

本次改造允许旧逻辑作为兼容层存在，但聊天区展示主逻辑必须收口到新模型。

## 3.3 原地更新，不跳位

对以下节点：

1. Tool Call 卡片
2. Report Card 卡片
3. Inquiry Card 卡片

它们第一次出现在聊天流中的位置就是固定位置。后续状态变化时，只允许更新同一张卡片本身，不允许重新插入到其他位置。

---

## 四、产品与技术硬决策

## 4.1 子图思考本期采用桥接方案，不做严格实时

这里的子图思考指：

- `status`
- `plan`
- `guide`

子图 Agent 执行过程中的中间 AI 消息。

本期采用桥接方案：

1. 子图执行结束后，把本轮产生的 `intermediate_messages` 转为 `subgraph_thinking` 展示节点
2. 节点写入统一展示模型
3. 节点进入持久化链路
4. 刷新后不丢失

本期不要求：

- 子图每产出一条中间消息，就立刻在聊天区实时出现

本期的桥接方案必须满足：

1. 基于最终统一展示模型实现
2. 不新增一套临时拼接逻辑
3. 下一期可以直接把“子图思考的发射方式”从补发切换为严格实时，而不推翻展示层和持久化层

## 4.2 刷新后必须与刷新前的最终态完全一致

这里的“最终态完全一致”包括：

1. 节点类型一致
2. 节点顺序一致
3. 节点最终状态一致
4. 已完成卡片仍可点击、可查看
5. 已回答提问卡片保留已提交状态和答案
6. reasoning、tool_call 等折叠卡片刷新后仍保留，只是不恢复动画

不要求恢复：

1. 打字机效果
2. loading 动画过程
3. 字符级流式变化

## 4.3 报告卡片完成态必须与右侧面板就绪绑定

聊天区的报告卡片一旦显示“已完成”，必须同时满足：

1. 右侧面板已有对应完整内容
2. 点击卡片能跳到正确的 Tab 或对应区域
3. 不会出现“卡片已完成，但点开面板没有内容”

如果右侧面板内容还未准备好，聊天区不能先显示完成态，只能保持生成中状态。

## 4.4 本期允许兼容旧逻辑，但展示层必须在本期收口到新模型

允许：

1. 旧字段、旧接口、旧链路继续存在
2. `pending_responses` 等兼容字段继续保留
3. 旧前端逻辑继续存在作为兜底

不允许：

1. 新需求继续直接叠加到旧逻辑上
2. `process_event`、`pending_responses`、历史恢复三套逻辑继续各自直接修改 `messages`
3. 继续把文案截断、字符串猜测作为主去重策略

本期上线时，必须达到：

1. 前端展示层有统一入口
2. 实时事件、最终结果、历史恢复都先进入统一展示节点模型
3. 排序、去重、状态升级、刷新恢复都围绕统一模型完成

## 4.5 invoke / stream 决策

这一条必须严格执行。

### 本期

本期不把外层子图调用简单从 `invoke()` 改成 `stream()`。

保留以下调用方式不变：

1. `_status_tool` 中的 `subgraph.invoke(...)`
2. `_plan_tool` 中的 `subgraph.invoke(...)`
3. `_guide_tool` 中的 `subgraph.invoke(...)`

本期原因：

1. 外层简单改成 `stream()` 不能自动获得真正的子图中间 AI 消息实时输出
2. 当前子图包装层围绕 `invoke + handle_interrupt` 设计，用来保证 interrupt/resume 的确定性
3. 本期目标是先稳定主链路，不把高风险点绑进同一版

### 下一期

如果下一期要完成“子图思考严格实时”，改的是子图内部 inner agent 的调用方式：

- 从 `agent_graph.invoke(...)`
- 演进为 `agent_graph.stream(..., stream_mode="updates")`

并在子图内部逐条消费 `AIMessage`，逐条发出 `subgraph_thinking` 展示节点。

禁止的做法：

- 只把外层 `_status_tool/_plan_tool/_guide_tool` 改成 `stream`，就宣称已完成子图严格实时

---

## 五、统一展示节点模型

## 5.1 DisplayNode

前后端统一使用如下结构：

```ts
type DisplayNode = {
  seq: number
  turnId: string
  nodeId: string
  nodeType:
    | 'user_message'
    | 'reasoning'
    | 'subgraph_thinking'
    | 'tool_call'
    | 'report_card'
    | 'inquiry_card'
    | 'inquiry_receipt'
    | 'ai_intermediate'
    | 'final_response'
  status?: 'loading' | 'done' | 'error' | 'new' | 'submitted'
  source?: string
  payload: Record<string, any>
}
```

## 5.2 节点类型

本期聊天区必须支持以下节点类型：

| nodeType | 用途 |
|----------|------|
| `user_message` | 用户消息 |
| `reasoning` | 推理过程 |
| `subgraph_thinking` | 子图思考 |
| `tool_call` | 工具调用 |
| `report_card` | 报告卡片 |
| `inquiry_card` | 提问卡片 |
| `inquiry_receipt` | 提问提交回执 |
| `ai_intermediate` | 中间 AI 文本 |
| `final_response` | 最终回复 |

## 5.3 稳定主键

以下节点必须具备稳定 `nodeId`，用于原地更新：

1. `tool_call`
2. `report_card`
3. `inquiry_card`

推荐规则：

| nodeType | `nodeId` 规则 |
|----------|---------------|
| `reasoning` | `reasoning:${turn_id}:${part_index}` |
| `subgraph_thinking` | `subgraph:${source}:${turn_id}:${part_index}` |
| `tool_call` | `tool:${tool_call_id}`；没有 `tool_call_id` 时退化为 `tool:${tool_name}:${local_counter}` |
| `report_card` | `report:${report_type}:${report_key}` |
| `inquiry_card` | `inquiry:${taskKey or turn_id}` |
| `inquiry_receipt` | `inquiry_receipt:${taskKey or turn_id}` |
| `ai_intermediate` | `ai:${turn_id}:${part_index}` |
| `final_response` | `final:${turn_id}` |

其中：

- `report_key` 本期可使用 `tool_call_id`、`report_id` 或业务唯一键
- 只要能稳定表达“这是同一张报告卡”，即可

## 5.4 卡片位置稳定规则

对 `tool_call`、`report_card`、`inquiry_card`：

1. 首次出现时分配 `nodeId`
2. 首次出现时分配 `seq`
3. 后续状态变化复用相同 `nodeId`
4. 后续状态变化不改变该节点的排序位置

即：

- `tool_call loading -> done/error` 是原地更新
- `report_card loading -> done` 是原地更新
- `inquiry_card new -> submitted` 是原地更新

---

## 六、排序与状态规则

## 6.1 统一排序依据

实时 SSE、最终态、历史恢复必须共享同一套排序基准：

```text
seq = turn_seq * 1000 + part_index
```

要求：

1. 流式阶段使用同一 `seq`
2. `final.display_nodes` 使用同一 `seq`
3. 持久化写库使用同一 `seq`
4. 历史恢复读取后仍按同一 `seq` 排序

## 6.2 禁止做法

禁止实时阶段只按“收到就 push”决定最终顺序。  
禁止实时阶段使用一套排序、刷新后再换另一套排序。

## 6.3 状态升级规则

### Tool Call

- 初次出现：`status=loading`
- 完成：`status=done`
- 失败：`status=error`
- 使用同一 `nodeId`
- 保持原位置不变

### Report Card

- 初次出现：`status=loading`
- 右侧面板内容就绪后：`status=done`
- 使用同一 `nodeId`
- 保持原位置不变

### Inquiry Card

- 初次出现：`status=new`
- 提交后：`status=submitted`
- 使用同一 `nodeId`
- 保持原位置不变

---

## 七、SSE 协议

## 7.1 顶层协议

本期继续保留当前顶层类型：

1. `process_event`
2. `interrupt`
3. `final`

不要求本期重命名顶层事件类型，但内部语义必须统一为展示节点模型。

## 7.2 `process_event` payload

`process_event.payload` 必须至少补齐：

1. `seq`
2. `turn_id`
3. `node_id`
4. `node_type`
5. `status`
6. `source`
7. `payload`

为兼容旧逻辑，本期允许继续保留：

- `event_type`

示例：

```json
{
  "type": "process_event",
  "payload": {
    "event_type": "tool_call",
    "seq": 12003,
    "turn_id": "turn_xxx",
    "node_id": "tool:tc_001",
    "node_type": "tool_call",
    "status": "loading",
    "source": "main_agent",
    "payload": {
      "tool_name": "call_status_agent",
      "tool_label": "分析感情现状",
      "args_preview": "..."
    }
  }
}
```

## 7.3 `final` payload

`final` 必须新增：

1. `turn_id`
2. `turn_seq`
3. `display_nodes`

示例：

```json
{
  "type": "final",
  "turn_id": "turn_xxx",
  "turn_seq": 12,
  "display_nodes": [...],
  "pending_responses": [...],
  "state": {...}
}
```

要求：

- `pending_responses` 本期继续保留，仅做兼容层
- `display_nodes` 作为展示主语义

---

## 八、后端实现方案

## 8.1 新增统一构造器

新增文件：

- `agent_impl/api/display_events.py`

职责：

1. 定义所有 `nodeType`
2. 生成 `seq / nodeId / status / source`
3. 统一工具中文名映射
4. 统一报告卡片字段
5. 提供内部事件到 `DisplayNode` 的转换 helper

建议至少提供：

1. `build_display_event(...)`
2. `build_tool_call_node(...)`
3. `build_report_card_node(...)`
4. `build_subgraph_thinking_node(...)`
5. `build_inquiry_node(...)`
6. `build_final_response_node(...)`
7. `get_tool_label(tool_name)`

## 8.2 `agent_impl/api/stream.py`

本期必须改：

1. 流开始时预留 `turn_id` 和 `turn_seq`
2. 创建统一 `next_seq()` 分配器
3. 所有 `process_event` 注入统一展示字段
4. 构建 `display_nodes`
5. `final` 输出 `display_nodes`

要求：

1. `process_events` 可以继续保留给兼容逻辑使用
2. 但新的展示主语义必须来自 `display_nodes`
3. `display_nodes` 中对同一逻辑卡片只保留一个最终节点对象，状态变化通过 upsert 体现

## 8.3 `agent_impl/graph/nodes/main_agent.py`

### 主 Agent

主 Agent 的 tool loop 已经使用 `stream`。这一层保持不变，不退回 `invoke`。

### Reasoning / AI Intermediate

在 `_emit_ai_events()` 中，把：

1. reasoning 统一为 `nodeType=reasoning`
2. 中间文本统一为 `nodeType=ai_intermediate`

### Tool Call

在 `_emit_ai_events()` 和 `_emit_tool_done_from_message()` 中：

1. loading 和 done/error 必须复用同一个 `nodeId`
2. done/error 事件必须补齐：
   - `tool_name`
   - `tool_label`
   - `tool_call_id`
   - `result_summary`

### Report Card

不能再只依赖 `pending_responses` 最终补卡。

要求：

1. 报告开始生成时创建 `report_card loading`
2. 只有右侧面板数据已可用时，才能把同一张卡更新为 `done`
3. done 卡必须带：
   - `report_type`
   - `panel_target`
   - `report_id`
   - `nodeId`

### 子图思考桥接

在：

1. `_status_tool`
2. `_plan_tool`
3. `_guide_tool`

中保留当前 `subgraph.invoke(...)`，但对返回的 `intermediate_messages` 做两件事：

1. 写入 `working_state["_subgraph_intermediates"]`
2. 转换为 `subgraph_thinking` 展示节点并发给统一展示链路

注意：

- 本期桥接方案允许“子图结束后补发”
- 但补发结果必须进入统一展示模型，不允许单独拼接 UI

## 8.4 `agent_impl/graph/subgraphs/status.py` / `plan.py` / `guide.py`

### 本期

保留：

1. `run_node()` 中的 `agent_graph.invoke(...)`
2. `handle_interrupt_node()` 中的 `agent_graph.invoke(...)`

不在本期内改成 `stream()`。

### 下一期

若要实现严格实时子图思考展示，则在下一期修改：

1. `run_node()` 内部 `agent_graph.invoke(...)`
2. `handle_interrupt_node()` 内部 `agent_graph.invoke(...)`

改为：

- `agent_graph.stream(..., stream_mode="updates")`

并且：

1. 在子图内部逐条提取 `AIMessage`
2. 逐条发出 `subgraph_thinking`
3. 保持 interrupt/resume 语义不变
4. 保持 `private_messages` 合并不变
5. 保持 `tool_patches` 收集不变

## 8.5 `agent_impl/api/conversation_persist.py`

必须新增统一归一化函数，例如：

- `build_display_nodes_for_persistence(...)`

输入至少包括：

1. `process_events`
2. `pending_responses`
3. `final_state`
4. `inquiry_card`
5. `inquiry_receipt_payload`
6. `display_nodes`

输出：

- 一份已经按最终顺序排好的 `display_nodes`

然后再由 `display_nodes` 映射到 `conversation_messages`。

要求：

1. 不再按“process_events 一段 + pending_responses 一段”分别决定聊天展示语义
2. metadata 中统一补：
   - `node_id`
   - `node_type`
   - `status`
   - `source`
   - `tool_label`
   - `report_type`
   - `panel_target`
3. 新增 `kind = subgraph_thinking`

## 8.6 持久化写入原则

以下节点刷新后只需要保留最终态：

1. `tool_call`
2. `report_card`
3. `inquiry_card`

但它们在持久化中的排序位置必须保留首次出现时的顺序。

这意味着：

1. 首次出现时分配的 `seq` 不能因完成态而改变
2. 刷新恢复时仍按该 `seq` 排序
3. 不能因“完成得更晚”而把卡片重新排到更后面

---

## 九、前端实现方案

## 9.1 展示层必须收口到统一入口

前端当前有三类数据来源：

1. `process_event`
2. `final.pending_responses`
3. 历史恢复消息

本期要求：

这三类来源都不能再直接各自操作最终展示结果。  
它们必须先进入统一展示节点入口，再由统一展示层输出给聊天 UI。

## 9.2 `agent_impl/frontend/index.html`

本期不强制拆分文件，但必须在文件内建立统一适配层。

新增函数：

1. `normalizeProcessEventToDisplayNode(event)`
2. `normalizePendingResponseToDisplayNode(resp)`
3. `normalizeHistoryMessageToDisplayNode(msg)`
4. `upsertDisplayNode(node)`
5. `buildMessagesViewFromDisplayNodes()`

要求：

1. 不允许新增逻辑继续直接 `messages.value.push(...)`
2. 新增展示逻辑全部先走 `DisplayNode`
3. 旧逻辑若保留，必须调用统一入口，不得再作为主路线单独渲染

## 9.3 DisplayStore

前端必须有统一 Store。第一阶段可以实现在 `index.html` 内部，不强制拆文件。

推荐结构：

```ts
displayNodeMap: Map<string, DisplayNode>
orderedNodeIds: string[]
turnGroupMap: Map<string, TurnGroup>
```

其中：

```ts
type TurnGroup = {
  turnId: string
  userNode?: DisplayNode
  intermediateNodes: DisplayNode[]
  finalNode?: DisplayNode
  collapsed: boolean
}
```

## 9.4 历史恢复

历史恢复不能继续依赖单独猜测重建。  
要求：

1. 优先从持久化记录恢复统一展示节点
2. 恢复后结构、顺序、状态与实时最终态一致
3. 不允许出现“实时时一种结构，刷新后换一种结构”

## 9.5 卡片渲染与原地更新

### Tool Call

- 第一次出现显示 loading 卡
- 完成后原地更新为 done 或 error
- 刷新后保留最终状态

### Report Card

- 生成中显示 loading 卡
- 面板数据可用后原地更新为 done 卡
- 点击后跳转到正确面板
- 刷新后仍可点击查看

### Inquiry Card

- 出现后可交互
- 未回答时输入框禁用
- 提交后原地更新为已提交状态
- 刷新后已提交状态和答案保留

## 9.6 输入锁定

前端统一计算：

```ts
const inputLockReason = computed(() => {
  if (streamActive.value) return 'streaming'
  if (hasPendingInquiry.value) return 'pending_inquiry'
  return null
})
```

规则：

1. 后端处理中，不能发新消息
2. 存在未回答 Inquiry Card 时，不能发新消息
3. 条件解除后恢复可发送

输入框、发送按钮、图片上传按钮必须统一锁定。

## 9.7 报告卡片与右侧面板跳转

当前前端已有：

1. `currentTab: 'chat' | 'plan'`
2. `currentPlanTab: 'status' | 'plan'`

统一跳转规则：

| `report_type` | 跳转 |
|---------------|------|
| `status` | `currentTab='plan'`，`currentPlanTab='status'` |
| `plan` | `currentTab='plan'`，`currentPlanTab='status'`，滚动到 `#plan-analysis` |
| `guide` | `currentTab='plan'`，`currentPlanTab='plan'`，如有 `guide_id` 则选中对应 guide |

要求：

1. 聊天卡片显示完成态时，面板必须已可查看
2. 点击卡片必须稳定落到正确位置

## 9.8 工具名称展示

工具名展示优先级：

1. 后端返回 `tool_label`
2. 前端本地映射表兜底
3. 未匹配显示“执行操作”

禁止展示裸英文技术名。

---

## 十、本期与下期的技术边界

## 10.1 本期

本期完成后，系统必须达到：

1. 所有关键节点可见
2. 顺序稳定
3. 刷新恢复一致
4. 报告卡与面板一致
5. 输入锁定统一
6. 卡片原地更新不跳位
7. 展示层由统一展示模型主导

本期允许暂时接受：

- 子图思考不是严格实时，只要最终能看到、能持久化、刷新不丢

## 10.2 下一期

下一期只在本期模型上继续增强：

1. 子图思考严格实时
2. 轮次折叠
3. Loading 动态文案

下一期不允许推翻：

1. 展示模型
2. 排序模型
3. 持久化模型

---

## 十一、验收标准

本期验收按以下标准执行。

## 11.1 节点完整性

用户发起一次完整分析流程后，聊天区能看到：

1. `reasoning`
2. `tool_call`
3. `subgraph_thinking`
4. `report_card`
5. `inquiry_card`
6. `ai_intermediate`
7. `final_response`

## 11.2 顺序稳定

要求：

1. 不出现明显乱序
2. 不出现刷新前后顺序不一致
3. 同一卡片状态变化时不跳位

## 11.3 Tool Call 卡片

要求：

1. 开始调用时出现 loading 卡
2. 完成后原地变成 done 或 error
3. 刷新后保留最终状态

## 11.4 Report Card

要求：

1. 生成中出现 loading 卡
2. 完成后原地变成可点击完成卡
3. 点击后跳到右侧正确面板
4. 刷新后仍可点击查看
5. 聊天区卡片显示完成时，面板内容已经就绪

## 11.5 Inquiry Card

要求：

1. 出现后可交互
2. 未回答时输入框禁用
3. 提交后卡片变成已提交状态
4. 刷新后已提交状态和答案仍保留

## 11.6 输入锁定

要求：

1. 后端处理中不能发新消息
2. 存在未回答提问卡片时不能发新消息
3. 条件解除后恢复可发送

## 11.7 工具名称

要求：

1. 用户看不到裸英文技术名
2. 展示为中文名称，或统一兜底“执行操作”

## 11.8 刷新恢复

要求：

1. 刷新后聊天区最终态与刷新前一致
2. 不要求恢复动画
3. 必须恢复结果

## 11.9 子图思考本期验收标准

本期只要求：

1. 子图思考最终能看到
2. 子图思考可持久化
3. 刷新后不丢失

本期不要求：

1. 子图执行过程中逐条实时出现

如果实现仍然是“子图结束后统一补发”，只要满足上述三条，本期可视为通过。  
但该实现必须基于统一展示模型，不得写成一次性旁路死逻辑。

---

## 十二、测试要求

## 12.1 后端测试

至少补以下测试：

1. `seq` 单调递增测试
2. `tool_call loading -> done/error` 同 `nodeId` 更新测试
3. `report_card loading -> done` 测试
4. `subgraph_thinking` 持久化测试
5. `display_nodes` 排序写库测试
6. 刷新恢复顺序一致性测试

## 12.2 前端 / E2E 测试

至少补以下场景：

1. 主流程
   - reasoning -> tool_call -> report_card -> final_response 顺序稳定

2. 子图流程
   - status/plan/guide 的子图思考可见

3. inquiry 流程
   - 提问卡出现后输入区禁用
   - 回答后恢复可发送

4. 刷新恢复
   - 刷新前后节点类型、顺序、状态一致

5. 报告跳转
   - status / plan / guide 卡点击后跳到正确面板

6. 卡片位置稳定
   - 同一工具卡、报告卡、提问卡状态变化时不跳位

---

## 十三、实施约束

1. 本期不做数据库 schema migration
2. 本期不强制拆分 `agent_impl/frontend/index.html`
3. 本期不把外层子图调用直接改成 `stream`
4. 本期允许旧兼容逻辑存在，但新展示主流程必须由统一模型主导
5. 不允许继续把文案截断、字符串猜测作为主去重方案
6. 不允许卡片完成后重新插到新位置

---

## 十四、执行结论

本次改造的执行主线如下：

1. 建立统一展示节点模型
2. 建立统一排序依据
3. 让实时流、最终态、历史恢复全部收口到统一展示模型
4. 用稳定主键支持卡片原地更新不跳位
5. 保证刷新后最终态与刷新前一致
6. 本期对子图思考采用桥接补发
7. 下一期仅把子图思考发射方式升级为严格实时，不推翻本期模型

执行时严格遵守以下一句话：

- **本期先把聊天区改造成统一、稳定、可持久化的展示体系；子图严格实时留到下一期增量升级。**
