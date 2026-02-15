# Tasks

- [ ] Task 1: 梳理现有数据流并定义落库边界
  - [ ] 确认前端消息来源（LangGraph thread state）与退出登录后 thread 切换点
  - [ ] 定义“需要持久化”的消息/事件类型与归一化格式（包含 interrupt/inquiry）
  - [ ] 定义“前端可直接渲染的 messages[]”目标结构（system_task 1:1、inquiry_receipt 含详情/图片）

- [ ] Task 2: 新增 Supabase migrations（会话表与消息表）
  - [ ] 设计 `conversations` / `conversation_turns` / `conversation_messages`（字段、索引、唯一约束、外键）
  - [ ] 引入严格顺序键 `seq`（turn_seq + part_index）以保证顺序严格一致
  - [ ] 设计 30 天保留与删除策略（必要索引：created_at、user_id、thread_id、seq）
  - [ ] 如启用 RLS：补充基础策略（后端走 service role 也需可写）

- [ ] Task 3: 扩展 supabase_service，提供会话/消息 CRUD
  - [ ] `upsert_conversation(user_id, thread_id)`
  - [ ] `get_or_create_turn(conversation_id, turn_id)`（返回 turn_seq，幂等）
  - [ ] `append_messages(thread_id, turn_id, messages[])`（幂等写入 + 生成 seq）
  - [ ] `get_messages_by_thread(thread_id, limit, before_seq)`（分页游标：seq）
  - [ ] `delete_conversation(conversation_id)`（物理删除）
  - [ ] `purge_old_data(days=30)`（清理任务：按 created_at）

- [ ] Task 4: 后端写入链路（/api/chat 与 /api/chat/stream）
  - [ ] 从每轮请求确定 `turn_id=current_message_id`
  - [ ] 提取并归一化本轮 user/assistant 消息（分段写入，含图片 URL 等 metadata）
  - [ ] 在 interrupt 下发时落库 interrupt 事件（含 inquiry_card）
  - [ ] 在 status/plan/guide 更新时落库 system_task 事件
  - [ ] 在问卷提交后落库 inquiry_receipt 事件
  - [ ] 以后台任务方式写入，失败不影响主响应（但要记录 error）

- [ ] Task 5: 历史读取链路（优先 Supabase，缺失回填）
  - [ ] 登录态：强制 thread 归属校验，不匹配 403
  - [ ] 未登录：直接返回 401，不提供历史
  - [ ] 支持分页参数（limit/before_seq）与 page 元数据返回
  - [ ] 回填：Supabase 空且 LangGraph 有历史时，批量写入后再返回
  - [ ] 回放：包含 interrupt 事件时，历史响应需能恢复问卷卡展示与可继续提交流程
  - [ ] 按页回填：仅回填当前请求页所需范围，不做全量回填

- [ ] Task 6: 新增对话语义化接口（并保留旧接口兼容）
  - [ ] `GET /api/conversations/default`（固定 default 标记）
  - [ ] `GET /api/conversations/{id}/messages`（分页：limit/before_seq）
  - [ ] `GET /api/conversations/{id}/state`（仅首屏/按需拉取）
  - [ ] `DELETE /api/conversations/{id}`（物理删除历史）
  - [ ] 旧接口 `/api/chat/history/{thread_id}` 不支持（前端迁移到 `/api/conversations/*`）

- [ ] Task 7: 前端适配新的历史消息体数据结构
  - [ ] 支持历史消息渲染 `system_task` / `inquiry_receipt` / `interrupt_inquiry` 回放
  - [ ] 确保 `state.inquiry_card` 恢复后可继续提交流程（resume）
  - [ ] 支持滚动加载更多（分页：before_seq），并在顶部合并历史不乱序

- [ ] Task 8: 验证与测试
  - [ ] 单元测试：消息归一化、hash/幂等去重
  - [ ] API 测试：未登录历史读取 401；登录态历史读取；403 安全场景；回填/按页回填；分页
  - [ ] 端到端：登录对话→退出登录后无法查看→重新登录可查看

# Task Dependencies
- Task 3 depends on Task 2
- Task 4 depends on Task 3
- Task 5 depends on Task 3
- Task 6 depends on Task 5
- Task 7 depends on Task 6
- Task 8 depends on Task 4 and Task 7
