* [ ] 前端当前消息列表来源已明确：来自 `/api/chat` 与 `/api/chat/history` 返回的 `messages`

* [ ] Supabase 新增会话表与消息表（含必要索引、唯一约束、外键）可成功迁移

* [ ] `/api/chat` 与 `/api/chat/stream` 在成功对话后会把新增消息幂等写入 Supabase

* [ ] interrupt（inquiry\_card）下发时会把中断事件写入 Supabase，并能在历史加载时回放

* [ ] system\_task（status/plan/guide/inquiry 卡）与 inquiry\_receipt（问卷回执）会作为事件写入 Supabase，并能在历史加载时回放

* [ ] 登录态读取历史：thread 归属校验生效，不匹配返回 403

* [ ] 未登录读取历史：返回 401，不提供历史消息

* [ ] Supabase 为空时能从 LangGraph thread state 回填一次并正常返回

* [ ] 前端已适配新的历史消息体数据结构，可正确渲染 system\_task/inquiry\_receipt/interrupt 回放

* [ ] 历史返回顺序严格一致：后端按 seq 排序，前端按顺序渲染无错乱

* [ ] 分页加载可用：历史接口支持 limit/before\_seq，前端滚动顶部可加载更多且不乱序

* [ ] 新语义化接口可用：/api/conversations/default 与 /api/conversations/{id}/messages

* [ ] state 可独立拉取：/api/conversations/{id}/state（首屏之外按需拉取）

* [ ] 删除与保留可用：删除会话历史、注销账号物理删除、30 天自动清理

* [ ] 默认会话规则生效：基于 user\_threads 绑定的 thread 标记为 is\_default=true

* [ ] 现有前端页面加载与发送消息流程不回归（手测或 e2e 覆盖）

* [ ] 自动化测试覆盖：幂等去重、未登录历史 401/403、403 场景、回填场景

