# Supabase 对话消息持久化 Spec

## Why

当前前端聊天页面的历史消息来自 LangGraph 的 thread state（通过 `thread_id` 拉取）。我们希望把“用户↔小话”的对话消息单独落库到 Supabase，以便：与 LangGraph checkpointer 解耦、便于后续多端/数据分析/合规、并支持更严格的鉴权控制（仅登录态可看历史）。

## What Changes

新增 Supabase 表用于存储会话（conversation）与消息/事件（messages/events），并建立与 `thread_id`、`user_id` 的映射关系。

* 后端在每轮对话完成后，把新增的 user/assistant 消息增量写入 Supabase（非流式与 SSE 流式均覆盖）。
* 后端在发生 interrupt（问卷/中断卡 `inquiry_card`）时，同步把该“中断事件”写入 Supabase，用于历史回放与断点恢复。
* 后端把前端需要回放的 UI 事件一并落库：`system_task`（status/strategy/plan/inquiry 卡）与 `inquiry_receipt`（问卷回执）。
* 后端提供“按用户”读取历史消息的入口：仅登录态可访问，按用户绑定的 thread 返回历史。
* 历史读取优先走 Supabase；若 Supabase 尚无数据，则从 LangGraph thread state 回填后再返回（渐进式迁移）。
* 强化安全校验：登录态请求 thread 历史时必须校验 thread 归属，不匹配返回 403。
* 保持兼容：保留现有 `GET /api/chat/history/{thread_id}` 的返回结构（`{success,messages,state}`），但内部数据源与鉴权逻辑按新方案调整。
* 前端适配新的历史消息体：从仅 `{role, content}` 扩展为可承载 `system_task` / `inquiry_receipt` / `interrupt` 等事件回放所需字段，并保证历史回放能正确渲染与继续提交流程。
* 新增更语义化的对话接口（`/api/conversations/*`），并保留旧接口兼容。
* 支持分页加载（`limit/before_seq`），且顺序严格一致。
* 支持用户删除历史与注销账号后的物理删除；数据最长保留 30 天。

## Impact

* Affected specs: 对话历史加载、数据持久化与安全边界

* Affected code:

  * 前端：[agent\_impl/frontend/index.html](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/frontend/index.html)

  * 后端 API：[agent\_impl/api/chat.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/api/chat.py), [agent\_impl/api/sdk\_client.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/api/sdk_client.py), [agent\_impl/api/auth.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/api/auth.py), [agent\_impl/api/stream.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/api/stream.py)

  * Supabase：`supabase/migrations/*`，以及 [agent\_impl/supabase\_service/client.py](file:///Users/wuyu/Documents/trae_projects/agent_impl_1/agent_impl/agent_impl/supabase_service/client.py)

## ADDED Requirements

### Requirement: Supabase 会话与消息数据模型

系统 SHALL 在 Supabase 中提供用于存储 AI 对话历史的表结构，最少包含：

* 会话表：可通过 `user_id` 识别同一会话，并关联 `thread_id`

* 消息表：按会话归档 user/assistant 消息，并支持去重写入与顺序读取

#### Data Model (Minimum)

* `conversations`

  * `id` (uuid, pk)

  * `thread_id` (uuid/text, not null)

  * `user_id` (uuid, not null) —— 绑定登录用户

  * `title` (text, nullable) —— 会话标题（可后续补齐）

  * `is_default` (boolean, not null, default false) —— 是否默认会话（每个 user_id 仅 1 个 true）

  * `created_at`, `updated_at`, `last_message_at`

* `conversation_turns`

  * `id` (uuid, pk)

  * `conversation_id` (uuid, fk -> conversations.id)

  * `turn_id` (text, not null) —— 对应每轮请求的 `current_message_id`

  * `turn_seq` (bigint, not null) —— 会话内严格递增的轮次序号（由数据库原子自增/序列生成）

  * `created_at`

* `conversation_messages`

  * `id` (uuid, pk)

  * `conversation_id` (uuid, fk -> conversations.id)

  * `thread_id` (uuid/text, not null) —— 便于按 thread 过滤与回填

  * `turn_id` (text, not null) —— 取自每轮请求的 `current_message_id`

  * `turn_seq` (bigint, not null) —— 冗余存储，便于排序与查询

  * `part_index` (int, not null) —— 同一轮次内的分段序号（从 0 开始）

  * `seq` (bigint, not null) —— 严格排序键（`turn_seq*1000 + part_index`，每轮最多 1000 段）

  * `role` (text, not null) —— `user` / `assistant` / `system`

  * `kind` (text, not null) —— `chat_text` / `interrupt_inquiry` / `inquiry_receipt` / `system_task`（可扩展）

  * `content` (text, nullable) —— 非文本事件可为空

  * `content_hash` (text, not null) —— 去重用（如 sha256(content)）

  * `metadata` (jsonb, nullable) —— 图片 URL、inquiry_card、任务卡字段、模型信息等

  * `created_at`

#### Constraints (Minimum)
- 一个会话对应一个 thread：`conversations.thread_id` 对同一 `user_id` 唯一
- 允许未来多会话：同一 `user_id` 可对应多个 `thread_id`（多条 conversations）
- `conversations`: unique(user_id, thread_id)
- `conversations`: partial unique(user_id) where is_default = true
- `conversation_turns`: unique(conversation_id, turn_id), unique(conversation_id, turn_seq)
- `conversation_messages`: unique(conversation_id, seq)
- `conversation_messages`: 可选 unique(conversation_id, turn_id, kind, role, part_index) 用于幂等去重

#### Scenario: 创建或绑定会话（登录态）

* **WHEN** 用户携带 Bearer token 发送消息

* **THEN** 后端使用 `user_threads` 找到该用户的 `thread_id`

* **AND** 在 `conversations` 中 upsert 一条记录绑定 `user_id` + `thread_id`
* **AND** 将该会话标记为默认会话：`is_default=true`（并确保该用户仅一个默认会话）

### Requirement: 对话消息增量写入

系统 SHALL 在每次对话完成后把“新增的 user/assistant 消息”写入 Supabase，并做到幂等（重复执行不产生重复行）。

#### Scenario: 非流式对话写入（/api/chat）

* **WHEN** `/api/chat` 成功返回（无异常）

* **THEN** 后端从本轮 `turn_id=current_message_id` 以及 final state 提取本轮 user/assistant 消息

* **AND** 以 `(thread_id, turn_id, role, content_hash)` 或等价约束去重 upsert 到 `conversation_messages`

#### Scenario: SSE 流式对话写入（/api/chat/stream）

* **WHEN** SSE 流结束且已得到最终 assistant 输出

* **THEN** 后端同样按本轮 `turn_id` 把消息写入 Supabase

### Requirement: 中断（interrupt）事件落库
系统 SHALL 在发生 interrupt 时把中断信息写入 Supabase，并在历史加载时可回放到前端（至少能恢复出 “需要补充信息” 的问卷卡）。

#### Scenario: /api/chat 返回 interrupt
- **WHEN** `/api/chat` 返回的 state 中包含 `inquiry_card`
- **THEN** 后端写入一条 `conversation_messages.kind=interrupt_inquiry` 的事件
- **AND** `metadata.inquiry_card` SHALL 保存完整卡片内容（含 questions）

#### Scenario: /api/chat/stream 推送 interrupt
- **WHEN** SSE 流中推送 `{'type':'interrupt','inquiry_card':...}`
- **THEN** 后端写入一条 `conversation_messages.kind=interrupt_inquiry` 的事件
- **AND** 事件写入应不阻塞 SSE 推送（异步/后台写入）

### Requirement: 历史读取优先 Supabase，并可回填

系统 SHALL 在读取历史消息时优先从 Supabase 返回；当 Supabase 无数据时，允许从 LangGraph thread state 回填一次后返回。

#### Scenario: 登录态读取历史

* **WHEN** 登录用户请求历史

* **THEN** 后端校验 `thread_id` 归属当前用户

* **AND** 优先从 Supabase 读取并返回

* **AND** 若 Supabase 无数据且 LangGraph state 存在历史，则回填后返回

### Requirement: 分页加载（历史消息）
系统 SHALL 支持历史消息分页加载能力，避免一次性返回过多消息导致响应体过大与前端渲染卡顿。

#### Pagination Contract (Minimum)
- 历史接口支持参数：
  - `limit`：本次最多返回条数（默认 50）
  - `before_seq`：可选游标；仅返回 `seq < before_seq` 的更早消息
- 返回体中包含：
  - `messages[]`：按 `seq ASC` 排序的消息/事件列表（本页）
  - `page.next_before_seq`：用于下一页请求的游标（例如本页最小 `seq`）
  - `page.has_more`：是否还有更早消息

#### Scenario: 加载更多历史
- **WHEN** 前端滚动到顶部触发“加载更多”
- **THEN** 前端携带 `before_seq=page.next_before_seq` 请求下一页
- **AND** 后端返回更早的消息并与现有列表在前端合并，不改变原有顺序

#### Scenario: 按页回填（Supabase 为空）
- **WHEN** Supabase 尚无历史数据且前端请求某一页（携带 `limit/before_seq`）
- **THEN** 后端只回填该页所需的消息范围到 Supabase（不做全量回填）
- **AND** 返回该页 `messages/page`（顺序严格一致）

#### Scenario: 登录态历史回放中断
- **WHEN** 历史消息中包含 `interrupt_inquiry` 事件
- **THEN** 返回的 `messages[]` SHALL 包含可被前端渲染的中断/问卷提示消息（例如 system_task/inquiry）
- **AND** 返回的 `state` SHALL 包含 `inquiry_card`（或等价可恢复字段），以便前端打开问卷并提交 resume

### Requirement: 严格顺序与分段存储
系统 SHALL 使用严格递增的 `seq` 保证历史消息顺序与当时展示顺序一致，并支持“分段存储”（同一轮次的 assistant 回复可拆成多段写入）。

#### 说明：分段存储是什么意思
- 指同一轮 assistant 输出不强制拼接为一条长文本，而是允许按“段落/结构化块/多条 pending_responses”拆成多条 `conversation_messages`（同一 `turn_id` 下用 `part_index` 表示顺序）。

#### Scenario: 顺序必须严格一致
- **WHEN** 用户查看历史消息
- **THEN** 后端按 `seq ASC` 返回消息/事件
- **AND** 前端按返回顺序渲染，保证与实时对话时的顺序严格一致

### Requirement: 多会话支持（未来演进）
系统 SHALL 支持同一用户存在多个会话（多个 `thread_id` / conversations），并允许后续增加“会话列表/切换会话”的能力。

### Requirement: 对话 API（语义化接口 + 旧接口兼容）
系统 SHALL 提供语义化接口并保留旧接口兼容：
- `GET /api/conversations/default`：获取当前用户默认会话（若不存在则创建/选择）
- `GET /api/conversations/{conversation_id}/messages`：分页获取消息/事件（`limit/before_seq`）
- `GET /api/conversations/{conversation_id}/state`：获取会话 state（首屏之外按需拉取）
- `DELETE /api/conversations/{conversation_id}`：删除该会话全部历史（物理删除）
- 不支持旧接口：`GET /api/chat/history/{thread_id}`（前端迁移到 `/api/conversations/*`）

### Requirement: state 可单独拉取
系统 SHALL 支持前端通过独立接口获取 state，用于首屏并行加载或刷新状态面板。

#### Scenario: 先拉 state 再拉 messages
- **WHEN** 前端希望并行加载（或先渲染状态面板）
- **THEN** 前端可先调用 `/api/conversations/{conversation_id}/state`
- **AND** 再调用 `/api/conversations/{conversation_id}/messages` 加载首屏消息

### Requirement: 数据删除与保留（30 天）
系统 SHALL 支持用户主动删除历史与注销账号后的物理删除，并限制数据最长保留 30 天。

#### Scenario: 删除单个会话历史
- **WHEN** 用户删除某个会话
- **THEN** 后端物理删除该会话的 `conversation_messages` / `conversation_turns` / `conversations` 记录

#### Scenario: 用户注销（删除账号）
- **WHEN** 用户发起注销
- **THEN** 后端物理删除该用户所有会话与消息数据

#### Scenario: 自动清理超过 30 天的数据
- **WHEN** 系统执行清理任务
- **THEN** 先物理删除过期 `conversation_messages`，再清理空 `conversations`
 - **AND** 清理任务由后端定时任务触发

### Requirement: 前端历史消息体适配
系统 SHALL 让前端能够消费“历史消息 API”返回的扩展消息体，并在 UI 上正确渲染至少以下类型：
- `user` / `assistant` 文本对话
- `system_task`（status/strategy/plan/inquiry 卡片）
- `inquiry_receipt`（问卷提交回执）

#### Scenario: 历史消息渲染一致性
- **WHEN** 前端加载历史消息
- **THEN** 需要将历史消息映射/合并为前端现有 `messages[]` 的 UI 结构
- **AND** `system_task(taskType='inquiry')` 与 `state.inquiry_card` 联动，使用户可继续提交问卷

#### Scenario: system_task 1:1 复现
- **WHEN** 历史回放
- **THEN** `system_task` 事件 SHALL 以“前端可直接渲染的消息对象”形式返回
- **AND** 字段（如 taskType/title/desc/taskKey/taskState/disabled）需要能 1:1 复现当时展示效果

#### Scenario: inquiry_receipt 回放（含答案与图片）
- **WHEN** 历史回放包含 `inquiry_receipt`
- **THEN** 事件 SHALL 包含答案详情与图片列表信息，以便前端回放“可展开详情/图片预览/错误状态”
 - **AND** 图片字段使用 Supabase Storage 的公开 URL

### Requirement: 安全校验

系统 SHALL 防止登录用户读取非本人 thread 的历史消息。

#### Scenario: thread 归属不匹配

* **WHEN** 登录用户请求 `thread_id` 不属于自己

* **THEN** 返回 403（并记录安全日志）

## MODIFIED Requirements

### Requirement: 现有历史接口的数据源与鉴权

现有 `GET /api/chat/history/{thread_id}` SHALL 保持返回结构不变，但内部实现修改为：

* 登录态：强制 thread 归属校验；历史消息优先来自 Supabase

* 未登录：直接返回 401（或 403），不提供历史消息（即该接口必须登录）

## REMOVED Requirements

无
