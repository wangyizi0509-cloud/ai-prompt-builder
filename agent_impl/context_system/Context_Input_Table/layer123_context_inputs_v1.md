# 上下文工程输入总表（Layer 1/2/3）v1

> 目标：把**每一次喂给模型的上下文**拆到“字段级”，便于你做 **删减 / 压缩 / 按需召回**决策。  
> 范围：只覆盖 Layer1/Layer2/Layer3（不含 Layer0 系统指令区）。  
> 代码依据（实现口径）：`agent_impl/graph/context_builder.py`、`agent_impl/graph/context_types.py`、`agent_impl/graph/archive_manager.py`、`agent_impl/prompts/*.md`

---

## 0. 重要口径（你在做删减前必须先知道的）

- **真正进入模型 Prompt 的入口**：由 `build_context_dict(state, target_agent)` 生成一组模板变量，然后在 `prompts/*.md` 里通过 `{变量名}` 注入。
- **Layer3 真正注入的“对话历史”变量**：`{conversation_history}`（XML 结构）。它由 `_format_interleaved_history()` 组装。
- **关键事实**：`{conversation_history}` **不会渲染 tool 输出**（role=tool 被直接跳过），避免 tool 返回跨轮累计导致上下文爆炸。
- **关键事实**：`<thought>` **按任务过滤**——只有“同任务”的 thought 才会进入 `<turn><thought>`，同时当前任务还会有 `<task_scratchpad>` 注入 reasoning notes。

---

## 1) Layer 1（静态情报区）输入总表

> 入口变量：`{user_context}`（主 Agent、Status/Plan/Guide 都会用）  
> 数据源：`state.layer1_memory.full_data`（向后兼容：`state.user_context`）  
> 结构定义：`UserContext` / `InfoSource` / `CrushInfo`（见 `graph/context_types.py`）

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入prompt逻辑 | 基于最佳实践的迭代建议 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| layer1 | 用户信息（User Info） | - user_info.user_provide<br>- user_info.fact<br>- user_info.ai_provide | - #### 用户信息<br>- ##### 由用户提供的信息：…<br>- ##### 客观事实：…<br>- ##### 军师分析得出的信息：… | - 位置：主/子 Agent Prompt 的 `{user_context}`<br>- 抽取：`extract_layer1()` → `_build_layer1_static_intel()`<br>- 规则：字段非空就输出；无内容则回“暂无详细信息” | - **从“全量注入”改为“按需注入”**：基于当前任务/用户最新消息，召回最相关的 Top-K facts（参考 LangGraph Store + semantic search）。<br>- **实现 compressed 模式**：当前 `_build_layer1_compressed` 是 TODO，建议：优先保留 fact，其次 ai_provide，user_provide 做压缩/去噪。<br>- **把 3×3 大块文本拆为细粒度“原子记忆”**（每条 fact 独立 id、source、时间），便于召回与过期。 |
| layer1 | Crush 信息（Crush Info） | - crush_info.crush_name<br>- crush_info.user_provide<br>- crush_info.fact<br>- crush_info.ai_provide | - #### Crush 信息<br>- ##### Crush 名称或昵称：…<br>- ##### 客观事实：… | - 同上：`extract_layer1()` 输出的一部分<br>- 只要 crush_name 或三列有任一非空，就会输出该段 | - **强制结构化“关键属性”**：如年龄/关系/城市/接触频率等，用 key-value 而非长段落，降低 token 干扰。<br>- **冲突处理**：你已经定义 Fact > AI > User，但当前仅是“展示规则”，建议在整理/写入时增加 conflict 标注或覆盖策略。 |
| layer1 | 双方相处信息（Both Info） | - both_info.user_provide<br>- both_info.fact<br>- both_info.ai_provide | - #### 双方相处信息<br>- ##### 客观事实：… | - 同上：`extract_layer1()` 输出的一部分 | - **把“关系阶段/关键里程碑/致命伤”从叙述性文本中拆出来**，让下游 Agent 直接引用结构字段（减少重复解释）。<br>- **增加有效期**：很多“双方相处”是时效信息，应下沉到 Layer2 动态情报或可过期记忆，避免长期污染。 |

---

## 2) Layer 2（工作上下文）输入总表

> 入口变量（主 Agent）：`{status_report}` / `{action_plan}` / `{action_guides}` / `{bound_action_guides}` / `{history_summaries}`  
> 数据源：`state.layer2_memory`（向后兼容：`state.status_report` / `state.action_plan` / `state.action_guides` 等）  
> 结构定义：`Layer2Memory` / `StatusReportItem` / `ActionPlanItem` / `ActionGuideItem` / `DynamicIntelItem`

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入prompt逻辑 | 基于最佳实践的迭代建议 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| layer2 | 当前现状分析报告（Current Status Report） | - StatusReportItem.report_content（优先）<br>- 或 stage/stage_description/key_issues…（降级）<br>- report_id（展示） | - ### 现状分析报告<br>- 【报告N】<br><br>{report_content} | - 位置：主 Agent `{status_report}`；子 Agent Prompt 也会注入同名变量<br>- 抽取：`_extract_current_status_report()`（dict payload）或 `extract_layer2()`（纯文本版）<br>- 规则：当前版本全量输出 report_content | - **加入“摘要优先”档位**：当用户仅闲聊/轻问答时，不必注入全量报告，改注入 one_liner + 关键结论 3 条。<br>- **把报告拆成结构字段并在 Prompt 中按需引用**（例如只给 Plan/Guide 需要的段落）。 |
| layer2 | 当前行动规划（Current Action Plan） | - ActionPlanItem.plan_content（优先）<br>- 或 goal/strategy/key_principles…（降级）<br>- plan_id（展示） | - ### 行动规划<br>- 【规划N】<br><br>{plan_content} | - 位置：主 Agent `{action_plan}`；Plan/Guide 也会强依赖<br>- 抽取：`_extract_current_action_plan()`<br>- 规则：当前版本全量输出 | - **分层注入**：Guide 只需要“当前 Phase + 关键原则 + 禁止项”，不需要整篇 plan_content。<br>- **加入“计划版本号/更新时间”**：避免模型用旧计划误判（轻量字段，低 token）。 |
| layer2 | 行动指南列表（Progressive Disclosure） | - ActionGuideItem.id / guide_id<br>- title / status<br>- one_liner / summary<br>- guide.guide_content（仅 in_progress 展开） | - #### 当前进行中：<br>【指南1】…<br>{guide_content}<br>- #### 其他指南（表格）：<br>\|ID\|标题\|状态\|摘要\| | - 位置：主/子 Agent `{action_guides}`<br>- 抽取：`_format_action_guide_items()`<br>- 规则：仅 status=in_progress 的指南全文展开；其它状态只输出元数据表格 | - **对表格做 token 上限**：限制“其他指南”最多展示 K 条（如 5），其余用“有更多，需工具加载”。<br>- **对 pending 的特殊处理**：如果当前任务马上要执行 pending 指南，建议自动触发 bind（或临时展开 1 条），否则模型无法“按表格元信息”高质量执行。 |
| layer2 | 任务绑定的行动指南详情（Bound Guides） | - TaskState.bound_action_guides[*].guide_id<br>- title / status<br>- content_md（完整 Markdown 快照） | - ### 任务绑定的行动指南详情（仅当前任务可见）<br>- #### 指南 xxx：标题 (in_progress)<br>{content_md} | - 位置：主/子 Agent `{bound_action_guides}`<br>- 抽取：`_format_bound_action_guides(active_task)`<br>- 规则：只对“当前活跃任务”注入，跨轮次持续可见 | - **严格控制绑定数量 K**：你代码里默认 K=3（很好），建议再加“每条 content_md token 上限”，过长则生成“可执行摘要 + 关键话术块”。<br>- **把绑定详情从 Layer2 挪到 Layer3（任务区）**：从语义上它更像“短期执行记忆”，方便清理。 |
| layer2 | 动态情报板（Dynamic Intels） | - DynamicIntelItem.content<br>- category(schedule/mood/status/intent)<br>- subject(user/crush)<br>- expire_at<br>- confidence | - ### 动态情报板（请务必参考）<br>- #### 日程<br>- 用户：…（有效期至 …） | - 位置：Layer2 文本区里“动态情报板”小节<br>- 抽取：`_build_dynamic_intel_board()` → `get_valid_dynamic_intels()`<br>- 规则：只过滤过期，不做数量/置信度/相关性限制 | - **加“上限 + 排序”**：按 confidence 倒序取 Top-N（如 5）。<br>- **加“任务相关性”**：给 intel 增加 related_task_id 或 tags，仅在相关任务注入。<br>- **过期策略**：过期后应清理或降级为 Layer1 的长期事实（如果它变成长期规律）。 |
| layer2 | 历史档案摘要（History Summaries） | - 历史 status_report：summary/one_liner<br>- 历史 completed guides：summary/one_liner<br>- （规划历史目前未在 extract_layer2 中展示） | - ### 历史档案摘要<br>- #### 历史现状分析<br>- [最近] …<br>- [更早] … | - 位置：主 Agent `{history_summaries}`（dict payload）或 Layer2 文本尾部<br>- 抽取：`_build_layer2_history_summaries()`<br>- 规则：最近 N 条中等摘要，其余一句话 | - **按 Agent 选择性注入**：Main Agent 可能需要，Guide 多数时候不需要。<br>- **计划历史补齐**：目前 `get_history_action_plans()` 没被用于历史摘要输出，建议统一口径。 |

---

## 3) Layer 3（对话历史与推理）输入总表（重点）

> 入口变量：`{conversation_history}`（主 Agent、Status/Plan/Guide 都会注入）  
> 数据源（提取时）：**`state.messages`**（工作区消息，可能已裁剪）+ `state.layer3_memory.conversation_summaries` + `state.layer3_memory.task_registry`  
> 注意：`layer3_memory.all_messages` 是全量存档，但在 `{conversation_history}` 生成时**不直接使用**。

### 3.1 `{conversation_history}` 的总体结构（你会在 Prompt 里看到）

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入prompt逻辑 | 基于最佳实践的迭代建议 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| layer3 | 历史摘要区（conversation_summaries） | - ConversationSummary.summary<br>- key_topics（topics 属性） | - `<conversation_summaries>`<br>- `<summary index="1" topics="约会,冷淡">…</summary>` | - 位置：`{conversation_history}` 内部<br>- 来源：`layer3_memory.conversation_summaries[:max_summary_count]`（默认 5）<br>- 用于：给模型“远古对话脉络”，避免全量对话撑爆 | - **按任务切片摘要**：现在摘要是全局混在一起，建议把 summary 增加 task_id 或 topic_namespace，按当前任务只注入相关摘要。<br>- **topics 规范化**：用受控词表（如“邀约/冷淡/复盘/情绪”），减少噪音。 |
| layer3 | 当前任务滚动思考（task_scratchpad） | - TaskState.task_id<br>- TaskState.summary（作为 scratchpad `<summary>`）<br>- TaskState.reasoning[*]（作为 `<note>`） | - `<task_scratchpad task="判断crush是否喜欢用户">`<br>- `<summary>…</summary>`<br>- `<note index="1">…</note>` | - 位置：`{conversation_history}` 内部<br>- 来源：当前 agent 的活跃任务（由 task_registry 推断）<br>- 规则：只注入“当前任务”的 reasoning notes | - **把 reasoning notes 限制为“决策结论 + 下一步”**，避免长推理污染（官方建议：保留决策导向摘要）。<br>- **压缩触发改为 token-based**：你现在 reasoning 压缩阈值是条数，建议改为 token 阈值更稳定。 |
| layer3 | 最近对话区（recent_turns） | - turn.user（用户消息）<br>- turn.assistant（AI 对用户输出的“可执行文本”）<br>- turn.thought（同任务才会输出）<br>- turn.task_id（作为 turn 的 task 属性） | - `<recent_turns>`<br>- `<turn index="1" task="...">`<br>- `<user>…</user>`<br>- `<thought>…</thought>`<br>- `<assistant>…</assistant>` | - 位置：`{conversation_history}` 内部<br>- 来源：`state.messages`<br>- 截断：按“用户轮次”向后保留 max_turns（默认 25） | - **标签瘦身**：XML 标签本身占 token，建议改更短或改 Markdown（同样可结构化）。<br>- **只保留“必要的 assistant 文本”**：你已经把 assistant JSON 抽取为 response/提问文本（很好），继续严格执行。 |

### 3.2 Layer3 消息类型穷举（你关心的“哪些该保留/该去掉”）

> 下表按“消息在系统中出现的形态”拆解：用户消息、AI 回复用户、AI 内部字段、AI↔AI、提问卡、工具调用、工具输出等。  
> 其中“是否进入 `{conversation_history}`”非常关键：它决定 Token 预算与模型行为。

| 层级 | 输入信息 | 输入字段 | 输入格式示例 | 输入prompt逻辑 | 基于最佳实践的迭代建议 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| layer3 | 用户消息（User → System） | - role=user<br>- content<br>-（可能含图片/多段文本） | `<user>我现在该怎么回？</user>` | - 位置：`{conversation_history}` / `<recent_turns>`<br>- 抽取：`get_msg_role_and_content(msg)`<br>- 排序：按 `state.messages` 原顺序进入 turn | - **对超长用户输入做“结构化摘要”**：例如用户粘贴长聊天记录时，只保留“关键片段+结论”，全量放抽屉/文件。<br>- **图片信息分流**：图片解析结果不要直接混入对话历史，改写入 Layer2/按需工具读取。 |
| layer3 | AI 回复用户（Assistant → User 的自然语言 response） | - role=assistant/ai<br>- content（可能是 JSON、可能夹杂 fenced code） | `<assistant>我建议你先别急着追问…</assistant>` | - 位置：`{conversation_history}` / `<assistant>`<br>- 抽取：`_format_assistant_message_for_history()`<br>- 规则：如果 content 是 JSON，会优先抽取 `response` 字段 | - **强制“对话历史只存 response”**：其它结构字段不要重复进 history，避免“同一信息多处出现”。<br>- **去重**：同一轮多次 assistant 输出（子 Agent 回来）会拆成新 turn，建议做合并规则（保留最终回复）。 |
| layer3 | AI 内部 thought（模型输出中的 thought 字段） | - JSON: thought<br>- 或 metadata.thought | `<thought>用户还缺一个关键证据…</thought>` | - 位置：`{conversation_history}` / `<turn><thought>`<br>- 过滤：只有 msg_task_id == current_task_id 才注入<br>- 来源：优先从 JSON 解析，其次 metadata | - **最小化 thought**：只保留“任务进度标记 + 下一步”两行，不要保留长推理链（官方建议避免长上下文干扰）。<br>- **安全与一致性**：避免把不该暴露给用户的内容写入可见层；你现在只注入模型侧 OK，但仍应做敏感词清洗。 |
| layer3 | AI 的 task_id / task_update（任务管理字段） | - JSON: task_id<br>- JSON: task_update.action/task_id/reasoning_note<br>- metadata.task_id | `<turn task="判断crush是否喜欢用户">…</turn>` | - 位置：`{conversation_history}` 的 `<turn task="...">` 属性<br>- 用途：用于 thought 过滤与任务连贯性 | - **保持 task_id 语义化、短且稳定**：避免动辄几百字；否则 turn 属性本身就浪费 token。<br>- **把 task_update 仅留在结构化状态，不进 history**：目前不直接注入（很好），继续保持。 |
| layer3 | AI 提问卡片（Inquiry Card）—作为“对用户输出的一部分” | - JSON: inquiry_card.questions[*].question<br>- intro/reasoning（可能存在） | - `<assistant>【提问】`<br>- `- 你们最近一次线下见面是什么时候？` | - 位置：`{conversation_history}` / `<assistant>`<br>- 抽取：`_format_assistant_message_for_history()` 会从 JSON 的 inquiry_card.questions 提取为“【提问】+问题列表”<br>- 注意：不会把选项/结构全部注入，只注入问题文本 | - **提问卡要“可复用、可追踪”**：建议在 state 里保存 inquiry_card_id + 问题 id，history 只保留“问题文本+目的一句话”。<br>- **防重复提问**：对话历史里存在已问问题时，后续模型应优先“引用用户回答”，建议加 answered 状态（结构化）。 |
| layer3 | AI ↔ AI（子 Agent 输出被 Main 消化前的中间内容） | - assistant 消息可能来自 status/plan/guide 节点<br>- 常见为 JSON（report_content/guide_content 等） | `<assistant>（报告N已生成）</assistant>` 或 `<assistant>{response抽取后的文本}</assistant>` | - 位置：仍在 `state.messages` 队列里<br>- 进入 history：会作为 `<assistant>` 注入，但经过 `_format_assistant_message_for_history()` 抽取/降噪<br>- 特殊：形如 `（…）` 的通知会原样保留 | - **中间产物不要进对话历史**：最理想是“子 Agent 输出只写入 Layer2 结构字段”，history 只保留最终给用户看的口吻。<br>- **系统通知最小化**：像“报告已生成”这类，如果没有帮助，可不进 history（仅留在状态）。 |
| layer3 | AI 的结构化 JSON 输出（除 response 外的字段） | - decision_rationale<br>- intent_type / next_action<br>- instruction<br>- report_content / guide_content（在子Agent输出里） | （不会直接出现在 `<assistant>`，除非抽取失败） | - 逻辑：`_format_assistant_message_for_history()` 尝试只抽 response + 提问文本；抽取失败时可能整段 JSON 泄漏进 history | - **加强“JSON 抽取失败兜底”**：抽取失败时也应尽量只保留 response，否则一次泄漏就会把上下文撑爆。<br>- **把 instruction 等字段坚决排除出 history**：它属于控制指令，应只存在结构化字段。 |
| layer3 | 工具调用信息（Tool Call） | - role=tool（工具返回）<br>- assistant.tool_calls（请求） | （在 `{conversation_history}` 中默认不展示） | - 逻辑：`_format_interleaved_history()` 遇到 role=tool 直接 continue<br>- 目的：防止 tool 输出跨轮次累计爆 token | - **保留“工具调用摘要”而非原文**：例如“已读取用户上传的截图并抽取3条事实”，1 行即可，让模型知道发生过什么但不吃 token。<br>- **大 tool 输出落盘引用**：借鉴 LangChain 的 FilesystemMiddleware（大结果写文件，history 只放引用）。 |
| layer3 | 工具输出信息（Tool Result / Observation） | - tool message content（可能很大） | （默认不进入 `{conversation_history}`） | - 逻辑：同上，被过滤掉<br>- 注意：虽然不进 history，但仍在 state.messages 中存在，供节点逻辑使用 | - **监控“工具输出仍在 state.messages 的体积”**：即使不进 history，也会影响其它地方的 token 估算/调试；建议对 tool message 做 TTL 或落盘。 |
| layer3 | AI 的“报告/规划/指南”正文（作为业务产物） | - Status: report_content<br>- Plan: plan_content<br>- Guide: guide_content | （应主要注入 Layer2，而非进入 history） | - 正确位置：Layer2 的 `{status_report}` / `{action_plan}` / `{action_guides}`<br>- 风险：如果这些正文以 assistant 消息形式出现且抽取失败，可能进入 history | - **强制：业务正文不进 history**（只进 Layer2 结构字段）。<br>- **把“已生成”通知改为结构字段**：减少历史污染。 |
| layer3 | “AI 对用户说过的话 last_response” | - last_response（用于子 Agent 连贯性） | `你刚刚对用户说过：“{last_response}”` | - 位置：status/plan/guide prompt 的“对话连贯性”段<br>- 来源：由 workflow 传入（不在 `{conversation_history}`） | - **避免重复**：既有 `{conversation_history}` 又注入 `{last_response}` 可能信息重复；建议只保留其一（通常保留 history 即可）。 |

---

## 4) 你可以直接用的“删减决策清单”（按收益排序）

> 这是把行业最佳实践落到你当前架构的“先做什么”。

1. **P0：严格保证对话历史只包含**：用户原话 + AI 的最终 response + 同任务的极短 thought + 极少量摘要  
   - 任何结构化 JSON、报告/指南正文、工具输出，尽量不要进入 `{conversation_history}`。
2. **P0：给 Layer2 的动态情报板加上限**（Top-N + 置信度排序 + 任务相关性），避免它悄悄变成“第二个对话历史”。
3. **P1：把 Layer1 从“全量注入”改为“按需召回”**（Top-K facts）——这会显著降低 token 并减少模型分心。
4. **P1：XML 结构瘦身**（或改 Markdown 结构），减少标签 token。
5. **P2：统一 token 预算触发为 token-based**（而不是轮次/条数），更符合 LangChain 官方 SummarizationMiddleware 的思路。

---

## 5) 下一步（需要你确认 2 个问题，我再把 v2 做成可执行规范）

1. 你希望 **Layer3 的对话历史**在“产品体验”上更偏：  
   - A) 更像聊天（保留更多用户原话）  
   - B) 更像任务管理（保留更少原话、更多结构摘要）
2. 你希望 **thought** 的策略是：  
   - A) 完全不进 `{conversation_history}`（只留 task_scratchpad）  
   - B) 仍保留，但每轮最多 1 句“下一步提示”

