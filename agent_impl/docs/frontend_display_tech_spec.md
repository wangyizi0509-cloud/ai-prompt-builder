# 前端展示需求 — 技术方案

> 版本: v1.0 | 日期: 2026-04-17 | 需求文档: `frontend_display_requirements_spec.md`

---

## 一、背景与目标

Crushe AI 聊天流存在三个核心问题：部分节点不展示/展示不完整、节点展示乱序、刷新后内容丢失。本方案覆盖需求 R1-R8，按 P0→P1→P2 分三个阶段实施，实现**稳定、有序、可持久化**的前端展示体验。

### 涉及的关键文件

| 文件 | 职责 |
|------|------|
| `agent_impl/api/stream.py` | SSE 流式推送，seq 计数器，process_event 转发 |
| `agent_impl/graph/nodes/main_agent.py` | 子图中间消息发射（subgraph_thinking） |
| `agent_impl/frontend/index.html` | 前端渲染、事件处理、持久化恢复、交互控制 |
| `agent_impl/api/conversation_persist.py` | 消息持久化到 Supabase |

### 现有数据流

```
main_agent_node (tool loop → 产出消息)
    ↓ get_stream_writer()
    ↓ 实时发射 custom events: reasoning / ai_message / tool_call / report_ready
    ↓
stream.py (SSE generate_stream)
    ↓ 转发 process_event → 前端实时渲染
    ↓ 累积 pending_responses / accumulated_state_fields
    ↓ 发射 final event → 前端批量渲染 pending_responses
    ↓
conversation_persist.py (后台持久化)
    ↓ process_events → reasoning_event / tool_event / ai_intermediate
    ↓ pending_responses → chat_text / system_task
    ↓
Supabase conversation_messages 表
    ↓
前端刷新时 → _mapSupabaseMessageToUI() → 恢复到 messages 数组
```

---

## 二、数据模型设计

### 2.1 前端 messages 数组 — 7 种节点类型统一模型

| # | 节点类型 | `role` 值 | 关键字段 | 实时来源 | 持久化 `kind` |
|---|---------|-----------|---------|---------|--------------|
| 1 | 推理（Reasoning） | `reasoning` | `content, collapsed` | process_event.reasoning | `reasoning_event` |
| 2 | 子图思考（Subgraph Thinking） | `subgraph_thinking` | `content, from, label, collapsed` | process_event.subgraph_thinking | `subgraph_thinking`（**新增**） |
| 3 | 工具调用（Tool Call） | `system_task` | `taskType='tool_call', taskKey, taskState, title, desc` | process_event.tool_call | `tool_event` |
| 4 | 报告卡片（Report Card） | `system_task` | `taskType='status'\|'strategy'\|'plan', taskKey, taskState, title, desc` | final.pending_responses | `system_task` |
| 5 | 提问卡片（Inquiry Card） | `system_task` | `taskType='inquiry', taskKey, inquiryData` | interrupt event | `interrupt_inquiry` |
| 6 | AI 中间文本（AI Intermediate） | `assistant` | `content, isIntermediate=true` | process_event.ai_message | `ai_intermediate` |
| 7 | 最终回复（Final Response） | `assistant` | `content, isIntermediate=false/undefined` | final.pending_responses (phase=final) | `chat_text` |

### 2.2 SSE 协议变更

#### 变更 1：所有 `process_event` payload 增加 `seq` 字段

```json
{
  "type": "process_event",
  "payload": {
    "event_type": "reasoning",
    "content": "...",
    "seq": 3
  }
}
```

`seq` 为 per-stream（单轮）单调递增整数。SSE 本身保证到达顺序，`seq` 主要作为持久化恢复时的排序保底。

#### 变更 2：新增 `event_type: "subgraph_thinking"`

```json
{
  "type": "process_event",
  "payload": {
    "event_type": "subgraph_thinking",
    "from": "status_agent",
    "content": "子图中间 AI 消息文本",
    "seq": 5
  }
}
```

`from` 取值：`status_agent` / `plan_agent` / `guide_agent`。

#### 不变

`final` 事件和 `interrupt` 事件格式不变。

### 2.3 Supabase 持久化 kind 值

新增 `kind: "subgraph_thinking"`。其余 kind 值不变：`chat_text`, `system_task`, `reasoning_event`, `tool_event`, `ai_intermediate`, `interrupt_inquiry`, `inquiry_receipt`, `preliminary_assessment`。

排序公式不变：`seq = turn_seq * 1000 + part_index`。

---

## 三、阶段一：P0 需求实现

> R1 节点完整展示 + R2 实时按序展示 + R3 完整持久化 + R7 输入锁定

### 3.1 SSE 事件增加 `seq` 字段

**文件**: `agent_impl/api/stream.py` — `generate_stream()` 函数（行 590 起）

**改法**：

```python
# 在 generate_stream() 内部，process_events 初始化之后加：
_event_seq = 0

# 在 line 616-618 的 custom event 分支中，yield 之前加：
_event_seq += 1
chunk_data['seq'] = _event_seq
```

**原理**：`_event_seq` 是闭包内局部变量，每个 stream 请求独立计数。`seq` 注入到 `chunk_data` 字典中后，会被同一行的 `process_events.append(chunk_data)` 保存，最终透传给 `conversation_persist.py`。

**兼容性**：旧版前端忽略未知字段，无破坏。

### 3.2 实时发射子图中间思考事件

**文件**: `agent_impl/graph/nodes/main_agent.py`

**现状分析**：

`_status_tool`（行 793-801）在 `.invoke()` 返回后收集 `intermediate_messages`，追加到 `working_state["_subgraph_intermediates"]`。最终在行 1008-1011 批量写入 `pending_responses`。用户要等整个子图跑完才看到中间思考。

**方案**：在现有 `_subgraph_intermediates` 收集代码之后，通过 `get_stream_writer()` 逐条实时发射。保持 `.invoke()` 不改为 `.stream()`（降低风险，避免影响 interrupt 机制和 patch 合并逻辑）。

**`_status_tool` 修改示例**（行 801 之后）：

```python
# 现有代码保持不变：ws["_subgraph_intermediates"] = existing
# 新增实时发射：
_writer = get_stream_writer()
if _writer and intermediate:
    for msg in intermediate:
        if isinstance(msg, dict) and msg.get("text"):
            try:
                _writer({
                    "event_type": "subgraph_thinking",
                    "from": "status_agent",
                    "content": msg["text"],
                })
            except Exception:
                pass  # stream writer 失败不影响主流程
```

**同理修改**：
- `_plan_tool`：`"from": "plan_agent"`
- `_guide_tool`：`"from": "guide_agent"`

**前置检查**：需确认 `get_stream_writer()` 在这些工具函数的闭包作用域中可以调用。当前 `_emit_ai_events` 使用的 writer 是通过 `_run_langchain_supervisor` 传入的。若 `_status_tool` 等闭包中无法直接调用 `get_stream_writer()`，可通过 `_subagent_writer` 变量（已在工具注册时通过 ContextVar 传入）获取。

### 3.3 前端处理 `subgraph_thinking` 事件

**文件**: `agent_impl/frontend/index.html`

#### 3.3a `handleProcessEvent` 增加 case

**位置**：行 3673（`case 'reasoning'` 块结束后，`case 'report_ready'` 之前）

```javascript
case 'subgraph_thinking': {
    if (!event.content) break;
    const agentLabelMap = {
        'status_agent': '现状分析 Agent 思考中...',
        'plan_agent': '行动策略 Agent 思考中...',
        'guide_agent': '行动指南 Agent 思考中...',
    };
    const label = agentLabelMap[event.from] || '子图 Agent 思考中...';
    const sgKey = `sg_${event.from || 'agent'}_${String(event.content).substring(0, 60)}`;
    if (displayedMessageIds.value.has(sgKey)) break;
    displayedMessageIds.value.add(sgKey);
    messages.value.push({
        role: 'subgraph_thinking',
        content: event.content,
        from: event.from || 'agent',
        label,
        collapsed: true,
        seq: event.seq || 0,
    });
    scrollToBottom();
    break;
}
```

#### 3.3b 渲染模板

**位置**：在 `v-else-if="msg.role === 'reasoning'"` 模板块之后

```html
<!-- 子图 Agent 思考卡 -->
<div v-else-if="msg.role === 'subgraph_thinking'"
     class="mx-4 my-2 rounded-2xl overflow-hidden"
     style="background: #f0f7ff; border: 1px solid #d0e3f5;">
    <button @click="msg.collapsed = !msg.collapsed"
            class="w-full flex items-center justify-between px-4 py-2 text-sm"
            style="color: #1976d2;">
        <span>&#x1F4AD; {{ msg.label || '子图思考' }}</span>
        <span style="font-size: 12px; opacity: 0.7;">{{ msg.collapsed ? '展开' : '收起' }}</span>
    </button>
    <div v-show="!msg.collapsed"
         class="px-4 pb-3 text-xs leading-relaxed whitespace-pre-wrap"
         style="color: #555; max-height: 300px; overflow-y: auto;">
        {{ msg.content }}
    </div>
</div>
```

### 3.4 持久化 `subgraph_thinking`

**文件**: `agent_impl/api/conversation_persist.py`

**位置**：`process_events` 处理循环中，`elif event_type == "reasoning"` 块（行 194-204）之后

```python
elif event_type == "subgraph_thinking":
    content = pe.get("content", "").strip()
    if content:
        messages_to_write.append({
            "role": "assistant",
            "kind": "subgraph_thinking",
            "content": content,
            "metadata": {"from": pe.get("from", "")},
            "part_index": part_idx,
        })
        part_idx += 1
```

**兼容性**：Supabase `conversation_messages` 表的 `kind` 字段是文本类型，无需 migration。新增 kind 值对旧数据无影响。

### 3.5 从 Supabase 恢复 `subgraph_thinking`

**文件**: `agent_impl/frontend/index.html` — `_mapSupabaseMessageToUI` 函数

**位置**：`kind === 'reasoning_event'` 处理块（行 3346-3348）之后

```javascript
// Kind: subgraph_thinking - 子图 Agent 思考过程
if (kind === 'subgraph_thinking') {
    if (!content) return null;
    const fromAgent = metadata.from || 'agent';
    const agentLabelMap = {
        'status_agent': '现状分析 Agent 思考中...',
        'plan_agent': '行动策略 Agent 思考中...',
        'guide_agent': '行动指南 Agent 思考中...',
    };
    return {
        ...baseMessage,
        role: 'subgraph_thinking',
        content,
        from: fromAgent,
        label: agentLabelMap[fromAgent] || '子图 Agent 思考中...',
        collapsed: true,
    };
}
```

### 3.6 输入锁定

**文件**: `agent_impl/frontend/index.html`

#### 3.6a 增加计算属性

**位置**：`isLoading` ref 定义附近

```javascript
const hasPendingInquiry = computed(() => {
    return messages.value.some(
        m => m.role === 'system_task'
          && m.taskType === 'inquiry'
          && (m.taskState === 'new' || m.taskState === 'loading')
    );
});

const inputDisabled = computed(() =>
    isLoading.value || isProcessingImages.value || hasPendingInquiry.value
);

const inputPlaceholder = computed(() => {
    if (isLoading.value) return '正在处理中...';
    if (hasPendingInquiry.value) return '请先回答上方问题';
    return '请输入 您的情感问题...';
});
```

#### 3.6b 修改模板绑定

找到输入框的 `:disabled` 绑定（当前为 `isLoading || isProcessingImages`），替换为 `inputDisabled`。
发送按钮同理，在现有条件基础上追加 `|| inputDisabled`。
placeholder 绑定改为 `inputPlaceholder`。

---

## 四、阶段二：P1 需求实现

> R4 报告面板跳转 + R5 工具名称中文化

### 4.1 工具名称中文映射（R5）

**文件**: `agent_impl/frontend/index.html`

#### 4.1a 添加映射表

**位置**：script 区域 setup 内，常量定义区

```javascript
const TOOL_NAME_ZH = {
    'call_status_agent': '分析感情现状',
    'call_plan_agent': '制定行动策略',
    'call_guide_agent': '生成行动指南',
    'load_skill': '加载技能',
    'ask_human': '向你提问',
    'task_manager': '管理任务',
    'context_loader': '加载上下文',
    'submit_status_report': '提交现状分析',
    'submit_action_plan': '提交行动策略',
    'submit_action_guide': '提交行动指南',
    'update_guide_status': '更新指南状态',
    'update_guide_content': '更新指南内容',
    'return_to_main': '返回主流程',
};
const getToolZhName = (name) => TOOL_NAME_ZH[name] || '执行操作';
```

#### 4.1b 修改实时渲染

**位置**：`handleProcessEvent` → `case 'tool_call'` → `title` 赋值（行 3644）

```diff
- title: event.tool_name || '工具调用',
+ title: getToolZhName(event.tool_name),
```

#### 4.1c 修改历史恢复

**位置**：`_mapSupabaseMessageToUI` → `kind === 'tool_event'` → `title` 赋值（行 3338）

```diff
- title: toolName,
+ title: getToolZhName(toolName),
```

### 4.2 报告卡片面板跳转（R4）

**文件**: `agent_impl/frontend/index.html`

#### 4.2a 修改点击处理

找到 system_task 卡片的点击处理逻辑，增加报告类跳转：

```javascript
// 在 inquiry 处理分支之后增加：
if (['status', 'strategy', 'plan'].includes(msg.taskType) && msg.taskState === 'done') {
    currentTab.value = 'plan';
    // 可选：如果面板内有 sub-tab，根据 taskType 切换
    // const subTabMap = { status: 'status', strategy: 'plan', plan: 'guide' };
    // activePlanSubTab.value = subTabMap[msg.taskType];
    return;
}
```

#### 4.2b 报告卡片模板增加引导文案

确保 system_task 卡片（`taskType` 为 status/strategy/plan）模板中：
- loading 态显示旋转图标 + "正在生成现状分析..."
- done 态显示 "现状分析已完成 → 点击查看" + 手指 cursor
- 添加 `cursor-pointer` 和 hover 高亮样式

---

## 五、阶段三：P2 需求实现

> R6 轮次折叠 + R8 动态 Loading 文案

### 5.1 轮次折叠（R6）

**文件**: `agent_impl/frontend/index.html`

#### 5.1a 核心思路

将 `messages` 数组按"轮次"分组。每轮 = 一条 user 消息 + 后续所有 assistant 侧消息（直到下一条 user 消息）。中间过程节点（reasoning, subgraph_thinking, tool_call, ai_intermediate, report_card）可被折叠，折叠后只保留 user 消息 + 最终回复。

#### 5.1b 数据模型

```javascript
const turnFoldState = ref(new Map()); // turnIndex → boolean (true = 折叠)

const isIntermediateMsg = (msg) =>
    ['reasoning', 'subgraph_thinking'].includes(msg.role)
    || (msg.role === 'system_task' && ['tool_call', 'status', 'strategy', 'plan'].includes(msg.taskType))
    || (msg.role === 'assistant' && msg.isIntermediate);

const messageTurns = computed(() => {
    const turns = [];
    let current = { userMsg: null, intermediates: [], finalMsgs: [], startIdx: 0 };
    messages.value.forEach((msg, idx) => {
        if (msg.role === 'user') {
            if (current.userMsg || current.intermediates.length || current.finalMsgs.length) {
                turns.push(current);
            }
            current = { userMsg: msg, intermediates: [], finalMsgs: [], startIdx: idx };
        } else if (isIntermediateMsg(msg)) {
            current.intermediates.push(msg);
        } else {
            current.finalMsgs.push(msg);
        }
    });
    if (current.userMsg || current.intermediates.length || current.finalMsgs.length) {
        turns.push(current);
    }
    return turns;
});
```

#### 5.1c 模板改造

```html
<div v-for="(turn, tIdx) in messageTurns" :key="tIdx">
    <!-- 用户消息 -->
    <MessageBubble v-if="turn.userMsg" :msg="turn.userMsg" />

    <!-- 中间过程区域 -->
    <div v-if="turn.intermediates.length > 0">
        <button v-if="turn.intermediates.length > 0"
                @click="turnFoldState.set(tIdx, !turnFoldState.get(tIdx))"
                class="text-xs text-gray-400 mx-4 my-1 cursor-pointer hover:text-gray-600">
            {{ turnFoldState.get(tIdx) ? '展开中间过程' : '收起中间过程' }}
            ({{ turn.intermediates.length }} 步)
        </button>
        <template v-if="!turnFoldState.get(tIdx)">
            <div v-for="(msg, mIdx) in turn.intermediates" :key="mIdx">
                <!-- 复用现有的各类型渲染模板 -->
            </div>
        </template>
    </div>

    <!-- 最终回复和其他消息 -->
    <div v-for="(msg, mIdx) in turn.finalMsgs" :key="mIdx">
        <!-- 复用现有渲染模板 -->
    </div>
</div>
```

**注意**：折叠状态不持久化，刷新后恢复为展开（默认 `turnFoldState` 为空 Map，未设置值 = 展开）。

#### 5.1d 实施风险

这是改动最大的步骤，需将现有的平铺 `v-for` 消息循环改为嵌套的轮次循环。需仔细处理：
- 现有的 `key` 策略（避免 Vue diff 错误）
- 滚动到底部的逻辑
- 去重 Set `displayedMessageIds` 的交互
- inquiry 卡片等交互类消息的正确分组

建议在阶段一和阶段二稳定后再实施此步骤。

### 5.2 动态 Loading 文案（R8）

**文件**: `agent_impl/frontend/index.html`

#### 5.2a 数据与逻辑

```javascript
const LOADING_COPIES = [
    '正在分析你的情况...',
    '正在制定策略...',
    '快好了，再等一下...',
    '正在整理思路...',
    '正在综合各方面信息...',
    '马上就好...',
];
const loadingCopyIdx = ref(0);
let _loadingTimer = null;

watch(isLoading, (val) => {
    if (val) {
        loadingCopyIdx.value = 0;
        _loadingTimer = setInterval(() => {
            loadingCopyIdx.value = (loadingCopyIdx.value + 1) % LOADING_COPIES.length;
        }, 4000); // 每 4 秒轮播
    } else {
        if (_loadingTimer) clearInterval(_loadingTimer);
        _loadingTimer = null;
    }
});

const currentLoadingCopy = computed(() => LOADING_COPIES[loadingCopyIdx.value]);
```

#### 5.2b 模板

找到现有的 loading 指示器区域，替换为：

```html
<div v-if="isLoading" class="flex items-center gap-2 px-4 py-2 mx-4 text-sm text-gray-400">
    <div class="w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full animate-spin"></div>
    <span class="transition-opacity duration-300">{{ currentLoadingCopy }}</span>
</div>
```

---

## 六、风险评估与缓解

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| `get_stream_writer()` 在子图工具闭包中不可用 | 中 | 实施前 grep 确认 writer 在作用域中可访问；若不可用，通过 ContextVar 或参数传递 |
| 轮次折叠重构消息循环影响现有渲染 | 中 | 放在阶段三，阶段一二稳定后再做；充分测试去重、滚动、inquiry 交互 |
| 大量 subgraph_thinking 消息导致聊天流过长 | 低 | 默认折叠，且用户可通过轮次折叠（R6）批量收起 |
| 新增 Supabase kind 值的兼容性 | 低 | kind 是文本字段，无 enum 约束；旧数据无影响，前端 fallback 兜底 |
| SSE seq 字段对现有前端的影响 | 无 | 纯增量字段，旧前端自动忽略 |

---

## 七、实施计划

| 步骤 | 改动内容 | 涉及文件 | 风险 | 对应需求 |
|------|---------|---------|------|---------|
| 1 | SSE process_event 增加 seq 字段 | `stream.py` | 低 | R2 |
| 2 | 子图中间思考实时发射 | `main_agent.py` | 中 | R1 |
| 3 | 前端 subgraph_thinking 渲染 + 模板 | `index.html` | 低 | R1 |
| 4 | subgraph_thinking 持久化 | `conversation_persist.py` | 低 | R3 |
| 5 | subgraph_thinking 从 Supabase 恢复 | `index.html` | 低 | R3 |
| 6 | 输入锁定（processing + pending inquiry） | `index.html` | 低 | R7 |
| 7 | 工具名称中文映射 | `index.html` | 低 | R5 |
| 8 | 报告卡片点击跳转面板 | `index.html` | 低 | R4 |
| 9 | 轮次折叠 | `index.html` | 中 | R6 |
| 10 | 动态 Loading 文案 | `index.html` | 低 | R8 |

步骤 1-6 = P0（必做），步骤 7-8 = P1（体验优化），步骤 9-10 = P2（锦上添花）。

---

## 八、验证方案

### 8.1 单元测试

```bash
cd agent_impl && pytest tests/ -m "not api_test" --tb=short -q
```

确保不破坏现有逻辑。

### 8.2 手动功能验证

启动服务后（`bash agent_impl/start_dev.sh`），在浏览器中逐项验证：

| 验证项 | 操作 | 预期结果 |
|--------|------|---------|
| R1 完整展示 | 发送消息，触发完整分析流程 | reasoning → tool_call → subgraph_thinking → report_card → final_response 全部可见 |
| R2 按序展示 | 观察节点出现顺序 | 严格按生成顺序出现，无乱序 |
| R3 持久化 | 刷新页面 | 所有节点完整恢复，顺序一致，折叠卡片默认折叠 |
| R4 面板跳转 | 点击报告完成卡片 | 右侧面板切换到对应 Tab |
| R5 中文名 | 观察工具调用卡片 | 显示中文名，无英文技术名 |
| R6 轮次折叠 | 点击"收起中间过程" | 中间节点隐藏，只留 user + final |
| R7 输入锁定 | 处理中 / inquiry 未回答时 | 输入框禁用，显示提示文案 |
| R8 动态文案 | 等待处理期间 | 文案每 4 秒轮播切换 |

### 8.3 端到端测试

```bash
cd agent_impl/tests/e2e && npx playwright test test_full_journey --reporter=list
```

验证完整用户旅程，产物在 `artifacts/e2e/full-journey/`。
