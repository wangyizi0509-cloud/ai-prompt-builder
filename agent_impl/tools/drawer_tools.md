## 抽屉式工具：`DrawerTools`（历史/聊天的按需拉取）

`DrawerTools` 的定位是“抽屉”：

> 当系统默认上下文里只放摘要，但某一刻你需要看完整内容，就临时打开抽屉把那段内容拉出来用。

它的代码在 `agent_impl/graph/tools/drawer_tools.py`。

---

## 1. 重要现状：它目前不会被模型自动调用

当前工作流统一执行工具的入口是 `agent_impl/graph/workflow.py:skill_tools_node`，其 ToolNode 列表里 **没有** `DrawerTools`/`create_drawer_tools_for_langchain()`。

这意味着：

- **LLM 在正常对话中不会自动 tool_call 到这些抽屉工具**
- 它更多是给开发/调试/兼容旧链路使用

如果未来希望模型可调用，需要显式把相关 Tool 加入到 tool_list / ToolNode。

---

## 2. DrawerTools 能做什么

`drawer_tools.py` 提供两大块能力：

### 2.1 历史报告/指南的完整内容（旧结构兼容为主）

- `get_full_status_history(state, index=0)`
- `get_full_guide_history(state, index=0)`
- `list_history_summaries(state, history_type="all")`
- `get_conversation_archive(state, index=0)`

它主要读取：

- `state.history_archive`（旧版结构：`status_history/guide_history/plan_history/conversation_archive` 等）

并在缺少 full_content 时回退到 summary。

### 2.2 Crush 聊天记录片段（依赖 CrushChatManager）

需要传入 `crush_chat_manager: CrushChatManager`：

- `get_recent_crush_messages(crush_chat_manager, count=20)`
- `get_important_crush_messages(crush_chat_manager)`
- `search_crush_messages(crush_chat_manager, keyword)`

---

## 3. 统一封装类：`DrawerTools`

`DrawerTools` 把上述函数包装成面向对象接口：

- `drawer.get_full_history(history_type, index=0)`
  - `history_type`: `status|guide|conversation`
- `drawer.list_history(history_type="all")`
- `drawer.get_crush_chat(action="recent", count=20, keyword="")`

---

## 4. `create_drawer_tools_for_langchain` 是什么

`create_drawer_tools_for_langchain(state, crush_chat_manager)` 会尝试返回 `langchain.tools.Tool` 列表：

- `get_full_history`
- `list_history`
- `get_crush_chat`

注意它是“LangChain Tool（字符串入参解析）”风格，并且有运行时依赖：

- 如果环境里没有 `langchain`，会返回空列表

---

## 5. 为什么说它“偏旧链路兼容”

本项目的最新版上下文架构是 Layered Memory（Layer0-4）：

- 报告/规划/指南等主要落在 `state.layer2_memory`
- 历史摘要落在 `state.layer3_memory`

但 `DrawerTools` 仍大量读取 `history_archive`（旧字段），因此存在天然局限：

- 可能读不到最新版数据（如果新链路不再同步写入旧字段）
- 输出格式与新链路的 `context_loader` 不一致

---

## 6. 推荐替代方案（新链路）

如果你的目标是“拿到完整内容并供模型使用”，优先用新链路：

- **行动指南详情**：`context_loader(action="load", context_type="action_guide", context_id="<guide_id>")`
- **现状报告**：`context_loader(action="load", context_type="status_report", context_id="current" 或 "<report_id>")`
- **行动规划**：`context_loader(action="load", context_type="action_plan", context_id="current" 或 "<plan_id>")`
- **历史摘要片段**：`context_loader(action="load", context_type="history_snippet", context_id="<id或索引>")`

如果你是在后端/调试代码里需要完整历史内容，也可以用：

- `agent_impl/graph/archive_manager.py:get_full_history_content(state, layer, item_type, index)`

---

## 7. 你应该如何在文档/功能里提到它

新人文档中建议把 `DrawerTools` 定位成：

- **一个仍在仓库里的“抽屉式兼容工具集”**
- **当前不参与模型自动调用链路**
- **新功能/新链路优先使用 `context_loader` 与 Layer2/Layer3 数据结构**

这样能避免新人误以为“模型随时会调用 get_full_history/get_crush_chat”，从而在排查行为时走错方向。

