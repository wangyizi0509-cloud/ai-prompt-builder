# AI 军师 Agent 上下文工程 - 技术实现文档

> 本文档面向工程团队，详细说明上下文工程的技术实现细节。

---

## 目录

1. [架构总览](#一架构总览)
2. [P0 实现详解 - 核心功能](#二p0-实现详解---核心功能)
3. [P1 实现详解 - 整理与归档](#三p1-实现详解---整理与归档)
4. [P2 设计方案 - 长期记忆](#四p2-设计方案---长期记忆)
5. [配置参数说明](#五配置参数说明)
6. [后续待办（P3）](#六后续待办p3)

---

## 一、架构总览

### 1.1 分层上下文架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 0: 系统指令区（只读常驻）                                  │
│  ├─ 角色定义（小话人设）                                          │
│  ├─ 核心法则（ACR模型、L/T坐标系）                                │
│  └─ 工具定义、安全边界                                            │
│  预估大小：~3-4K tokens（固定）                                   │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: 静态情报区（常驻，高优）                                 │
│  └─ 3×3 情报矩阵（用户/Crush/双方 × 用户提供/事实/AI分析）         │
│  预估大小：~5-15K tokens                                          │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: 工作上下文（当前任务相关）                               │
│  ├─ 现状分析报告（status_report）                                 │
│  ├─ 行动规划（action_plan）                                       │
│  └─ 未执行的行动指南列表（action_guides）                          │
│  预估大小：~10-20K tokens                                         │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: 滚动对话区（FIFO）                                      │
│  ├─ 最近 40 轮完整对话                                            │
│  └─ 超出阈值 → 触发压缩归档                                       │
│  预估大小：~15-20K tokens                                         │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: 外部长期记忆（按需检索）                                 │
│  ├─ 历史报告/指南摘要（分级存储）                                  │
│  ├─ 历史对话归档（压缩摘要）                                       │
│  └─ Crush聊天记录库（P2实现）                                     │
│  常驻摘要：~2-3K tokens                                           │
└─────────────────────────────────────────────────────────────────┘

总预算：70K tokens | 可用输入：60-65K | 压缩触发阈值：55-60K
```

### 1.2 核心文件清单

| 文件路径 | 职责 |
|---------|------|
| `graph/context_types.py` | 类型定义：3×3矩阵、历史摘要、对话归档等数据结构 |
| `graph/state.py` | AgentState 状态定义，包含所有上下文字段 |
| `graph/context_builder.py` | 上下文组装器，构建各层内容输入到 Agent |
| `graph/archive_manager.py` | 归档管理器，处理压缩触发和历史摘要分级 |
| `graph/nodes/organize_agent.py` | 整理 Agent，提取高价值信息并生成摘要 |

### 1.3 数据流图

```
                            ┌─────────────────┐
                            │   用户输入      │
                            └────────┬────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                        AgentState                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │user_context │  │status_report│  │    action_guides        │  │
│  │  (Layer 1)  │  │action_plan  │  │    (Layer 2)            │  │
│  │  3×3 矩阵   │  │  (Layer 2)  │  │  未执行的指南列表        │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│  ┌─────────────┐  ┌───────────────────────────────────────────┐ │
│  │  messages   │  │          history_archive                  │ │
│  │  (Layer 3)  │  │  (Layer 4) status_history/guide_history   │ │
│  │  对话历史   │  │            conversation_archive           │ │
│  └─────────────┘  └───────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
         │                              ▲
         │ context_builder.py           │ archive_manager.py
         ▼                              │
┌─────────────────┐            ┌────────┴────────┐
│  组装后的上下文  │            │   整理 Agent    │
│  (Prompt 输入)   │            │ organize_agent  │
└────────┬────────┘            └─────────────────┘
         │                              ▲
         ▼                              │ 归档触发
┌─────────────────┐            ┌────────┴────────┐
│   LLM 调用      │            │  压缩/完成事件  │
└─────────────────┘            └─────────────────┘
```

---

## 二、P0 实现详解 - 核心功能

### 2.1 3×3 静态情报矩阵

#### 数据结构定义

```python
# graph/context_types.py

class InfoSource(TypedDict, total=False):
    """信息来源三元组"""
    user_provide: str  # 用户口述的信息
    fact: str          # 客观事实（截图、记录等直接证据）
    ai_provide: str    # AI军师分析得出的信息

class CrushInfo(TypedDict, total=False):
    """Crush 信息（含名称）"""
    crush_name: str     # Crush 名称或昵称
    user_provide: str   # 用户描述的 Crush
    fact: str           # 聊天记录/社媒截图提取的信息
    ai_provide: str     # AI 分析（如性格特征）

class UserContext(TypedDict, total=False):
    """3×3 静态情报矩阵"""
    user_info: InfoSource   # 用户自身信息
    crush_info: CrushInfo   # Crush 信息
    both_info: InfoSource   # 双方相处信息
```

#### 矩阵结构说明

| 归属维度 ↓ \ 来源维度 → | user_provide | fact | ai_provide |
|------------------------|--------------|------|------------|
| **user_info** | 用户口述的自我描述 | 用户朋友圈等 | AI推断（如依恋类型） |
| **crush_info** | 用户描述的Crush | 聊天记录/截图 | AI推断（如性格特征） |
| **both_info** | 用户描述的相处情况 | 互动记录/证据 | AI推断（如关系阶段） |

#### 信任优先级

```
1. 最高可信 - fact: 客观事实（聊天记录、截图等直接证据）
2. 中等可信 - ai_provide: AI分析（基于证据的推断）
3. 最低可信 - user_provide: 用户口述（可能美化或误读）
```

### 2.2 分层上下文组装

#### 核心函数

```python
# graph/context_builder.py

def build_context(
    state: AgentState,
    target_agent: str = "main_agent",
    include_layer0: bool = False,
) -> str:
    """
    组装完整上下文，返回格式化的字符串
    """

def build_context_dict(state: AgentState) -> dict:
    """
    构建上下文字典，用于 Prompt 模板变量替换
    
    返回:
    {
        "user_context": "Layer 1 内容",
        "status_report": "现状分析报告",
        "action_plan": "行动规划",
        "action_guides": "行动指南列表",
        "conversation_history": "对话历史",
        "history_summaries": "历史摘要",
    }
    """
```

#### 使用示例

```python
# 在 Agent 节点中使用
from graph.context_builder import build_context_dict

def my_agent_node(state: AgentState) -> dict:
    context_dict = build_context_dict(state)
    
    prompt = prompt_template.format(
        user_context=context_dict["user_context"],
        status_report=context_dict["status_report"],
        conversation_history=context_dict["conversation_history"],
    )
    
    response = llm.invoke(prompt)
    # ...
```

### 2.3 AgentState 新增字段

```python
# graph/state.py

class AgentState(TypedDict, total=False):
    # === Layer 1: 静态情报 ===
    user_context: UserContext  # 3×3 静态情报矩阵
    
    # === Layer 2: 工作上下文 ===
    status_report: Optional[StatusReport]
    action_plan: Optional[ActionPlan]
    action_guides: list[ActionGuideItem]  # 支持多个未执行指南
    
    # === Layer 3: 对话历史 ===
    messages: Annotated[list[Message], add]
    
    # === Layer 4: 历史存档 ===
    history_archive: HistoryArchive
    
    # === Crush 聊天记录（P2 预留）===
    crush_chat_storage: Optional[CrushChatStorage]
```

#### 初始化状态

```python
from graph.state import create_initial_state

# 创建新会话的初始状态
state = create_initial_state(user_message="我喜欢一个女生...")
```

---

## 三、P1 实现详解 - 整理与归档

### 3.1 整理 Agent

#### 职责

在信息**从高优变低优**的时刻，提取高价值信息并生成摘要：
1. 提取高价值信息 → 写入 3×3 矩阵的 `ai_provide` 字段
2. 生成压缩摘要 → 写入对应的历史存档

#### 三种输入类型处理

```python
# graph/nodes/organize_agent.py

ArchiveType = Literal[
    "action_guide",      # 行动指南归档 → guide_history
    "status_report",     # 现状分析归档 → status_history
    "conversation",      # 对话压缩归档 → conversation_archive
]

def organize_and_archive(
    content: Any,
    content_type: ArchiveType,
    existing_user_context: Optional[UserContext] = None,
) -> dict:
    """
    返回:
    {
        "summary": HistorySummary 或 ConversationArchive,
        "extracted_info": {
            "user_info": "提取的用户信息",
            "crush_info": "提取的Crush信息",
            "both_info": "提取的双方关系信息",
        },
        "archive_type": "guide_history" | "status_history" | "conversation_archive",
    }
    """
```

#### 快捷调用函数

```python
# 归档已完成的行动指南
from graph.nodes.organize_agent import archive_completed_guide

result = archive_completed_guide(guide, existing_context)
# result = {
#     "guide_summary": HistorySummary,
#     "updated_context": UserContext,
# }

# 归档被替换的现状分析
from graph.nodes.organize_agent import archive_replaced_status_report

result = archive_replaced_status_report(old_report, existing_context)

# 归档对话批次
from graph.nodes.organize_agent import archive_conversation_batch

result = archive_conversation_batch(messages_to_archive, existing_context)
```

### 3.2 归档管理器

#### 对话压缩触发机制

```python
# graph/archive_manager.py

ARCHIVE_CONFIG = {
    "max_recent_turns": 40,         # 保留最近 40 轮完整对话
    "compression_batch_size": 5,    # 每超出 5 轮集中压缩一次
    "compression_threshold": 45,    # 超过 45 轮开始检查
}
```

**触发逻辑**：
- 对话轮次 ≤ 45：不压缩
- 对话轮次 = 50：触发压缩（超出 5 轮）
- 对话轮次 = 51-54：不压缩
- 对话轮次 = 55：触发压缩（超出 10 轮）

```python
def check_conversation_compression_needed(state: AgentState) -> bool:
    """检查是否需要触发对话压缩"""
    messages = state.get("messages", [])
    current_turns = len(messages)
    
    if current_turns <= ARCHIVE_CONFIG["compression_threshold"]:
        return False
    
    excess_turns = current_turns - ARCHIVE_CONFIG["compression_threshold"]
    return excess_turns > 0 and excess_turns % ARCHIVE_CONFIG["compression_batch_size"] == 0
```

#### 历史摘要分级策略

```python
ARCHIVE_CONFIG = {
    "recent_summary_count": 2,      # 最近 2 份保留中等摘要
    "max_one_liner_count": 10,      # 最多保留 10 条一句话摘要
}
```

**分级规则**：

| 时间距离 | 摘要级别 | 长度 | 常驻上下文 |
|---------|---------|-----|-----------|
| 最近 2 份 | 中等摘要 | 100-200字 | 是 |
| 更早的 | 一句话摘要 | 20-30字 | 是 |
| 完整内容 | full_content | 原文 | 否（抽屉式调用） |

### 3.3 调用时机

| 触发场景 | 调用方式 | 说明 |
|---------|---------|------|
| 行动指南完成 | `archive_guide_on_completion(guide, state)` | **工程层面自动触发**：<br>1. 前端按钮：用户点击完成按钮 → `/api/complete_guide` → 自动调用<br>2. Agent主动发现：主Agent检测到完成 → 自动调用 |
| 现状分析替换 | `archive_status_on_replacement(old_report, state)` | **Status Agent自动判断**：<br>生成新报告时判断微调/大改，只有大改才归档<br>微调：只更新细节，关系阶段/核心问题不变<br>大改：关系阶段变化、核心问题重新诊断 |
| 对话超出阈值 | `compress_conversation(state)` | **工程层面自动触发**：<br>每超出 5 轮集中压缩一次，在 workflow 执行后自动检查 |

#### 统一入口

```python
from graph.context_builder import check_and_compress_if_needed

# 在每轮结束时调用
updates = check_and_compress_if_needed(state)
if updates:
    state.update(updates)
```

### 3.4 数据结构

```python
# 历史摘要项
class HistorySummary(TypedDict, total=False):
    id: str                 # 唯一标识
    summary: str            # 中等长度摘要（100-200字）
    one_liner: str          # 一句话摘要（20-30字）
    created_at: str         # 创建时间
    full_content: str       # 完整内容（抽屉式存储）

# 对话归档项
class ConversationArchive(TypedDict, total=False):
    id: str                 # 唯一标识
    summary: str            # 压缩摘要
    start_time: str         # 对话开始时间
    end_time: str           # 对话结束时间
    turn_count: int         # 对话轮次
    key_topics: list[str]   # 关键话题
    extracted_info: dict    # 提取的高价值信息

# 历史存档
class HistoryArchive(TypedDict, total=False):
    status_history: list[HistorySummary]        # 历史现状分析
    plan_history: list[HistorySummary]          # 历史行动规划
    guide_history: list[HistorySummary]         # 历史行动指南
    conversation_archive: list[ConversationArchive]  # 对话归档
```

---

## 四、P2 实现详解 - 长期记忆

### 4.0 本地持久化存储（已实现）

为方便开发测试，实现了本地 JSON 文件存储方案。

#### 文件位置

```
agent_impl/
└── data/
    ├── users/           # 用户状态存储
    │   ├── user_001.json
    │   └── user_002.json
    └── images/          # 用户上传的图片
        ├── user_001/
        └── user_002/
```

#### 核心 API

```python
# graph/state_storage.py

# 保存用户状态
save_state(user_id: str, state: dict) -> None

# 加载用户状态
load_state(user_id: str) -> Optional[dict]

# 获取或创建状态
get_or_create_state(user_id: str, initial_message: str = "") -> dict

# 自动保存包装器
with AutoSaveState("user_001") as state:
    state["messages"].append({"role": "user", "content": "你好"})
    # 退出 with 时自动保存

# 列出所有用户
list_users() -> list[str]

# 保存图片
save_image(user_id: str, image_data: bytes, filename: str) -> str
```

### 4.1 Crush 聊天记录分层存储（L1-L3 已实现）

#### 四层结构设计

```
┌─────────────────────────────────────────────────────────────┐
│  L1: 元数据层（常驻上下文）✅ 已实现                          │
│  - 总消息数、聊天频率、时间跨度、最后聊天时间                  │
│  预估大小：~100 tokens                                       │
├─────────────────────────────────────────────────────────────┤
│  L2: 结构化摘要层（常驻上下文）✅ 已实现                      │
│  - 关键事件、情感转折点、主要话题                             │
│  预估大小：~500 tokens                                       │
├─────────────────────────────────────────────────────────────┤
│  L3: 关键片段层（按需调用）✅ 已实现                          │
│  - 最近 N 条消息原文                                         │
│  - 标记为"重要"的对话原文                                    │
│  预估大小：~2-5K tokens                                      │
├─────────────────────────────────────────────────────────────┤
│  L4: 全量存储层（语义检索）⏳ 待实现                          │
│  - 完整聊天记录（向量化存储）                                 │
│  - 通过语义检索获取相关片段                                   │
│  存储位置：向量数据库（需工程团队对接）                       │
└─────────────────────────────────────────────────────────────┘
```

#### 核心实现：CrushChatManager

```python
# graph/crush_chat_storage.py

from graph.crush_chat_storage import CrushChatManager, create_crush_chat_manager

# 创建管理器
manager = create_crush_chat_manager()

# 添加消息（从截图提取后调用）
manager.add_message(
    content="今天天气真好",
    sender="crush",  # "user" 或 "crush"
    timestamp="2024-12-19T10:30:00",
    source_image="/path/to/screenshot.png",
)

# 批量添加（从一张截图提取多条消息）
manager.add_messages_batch([
    {"content": "在干嘛", "sender": "crush"},
    {"content": "刚下班", "sender": "user"},
], source_image="/path/to/screenshot.png")

# 标记重要消息
manager.mark_as_important(message_id, reason="表白时刻")

# 获取 L1+L2 上下文（常驻）
context_l1_l2 = manager.build_context_l1_l2()

# 获取 L3 上下文（按需调用）
context_l3 = manager.build_context_l3(include_recent=10)

# 搜索消息（关键词，L4 实现后可用语义搜索）
results = manager.search_messages("约会")

# 序列化/反序列化（用于存储）
data = manager.to_dict()
manager = CrushChatManager.from_dict(data)
```

#### 配置参数

```python
CRUSH_CHAT_CONFIG = {
    "recent_messages_count": 20,    # L3: 保留最近 N 条消息
    "max_important_messages": 10,   # L3: 最多保留 N 条重要消息
    "summary_update_threshold": 10, # 每新增 N 条消息更新一次 L2 摘要
}
```

### 4.2 抽屉式完整信息调用工具（已实现）

#### 工具类

```python
# graph/tools/drawer_tools.py

from graph.tools import DrawerTools

# 创建工具实例
drawer = DrawerTools(state, crush_chat_manager)

# 获取历史报告完整内容
full_status = drawer.get_full_history("status", index=0)  # 最近一份
full_guide = drawer.get_full_history("guide", index=1)    # 次近一份

# 列出所有历史摘要
summaries = drawer.list_history("all")  # 或 "status" / "guide"

# 获取 Crush 聊天记录
recent_chat = drawer.get_crush_chat("recent", count=20)
important_chat = drawer.get_crush_chat("important")
search_result = drawer.get_crush_chat("search", keyword="约会")
```

#### 独立函数（不需要实例化）

```python
from graph.tools import (
    get_full_status_history,
    get_full_guide_history,
    list_history_summaries,
    get_recent_crush_messages,
    get_important_crush_messages,
    search_crush_messages,
)

# 获取历史现状分析完整内容
full_content = get_full_status_history(state, index=0)

# 搜索 Crush 聊天记录
results = search_crush_messages(crush_chat_manager, "约会")
```

#### LangChain 工具集成（可选）

```python
from graph.tools import create_drawer_tools_for_langchain

# 创建 LangChain 格式的工具列表
tools = create_drawer_tools_for_langchain(state, crush_chat_manager)
# 返回 [Tool(name="get_full_history", ...), Tool(name="get_crush_chat", ...), ...]
```

### 4.3 L4 语义检索（待实现）

> **状态**：待工程团队对接向量数据库后实现

#### 设计方案

```python
# 待实现：graph/tools/semantic_search.py

class SemanticSearchTool:
    """
    语义检索工具
    
    功能：
    1. 将聊天记录向量化存储
    2. 根据查询语义检索相关片段
    3. 返回最相关的 Top-K 结果
    """
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
        self.embeddings = get_embeddings_model()
    
    def index_messages(self, messages: list[dict], user_id: str) -> None:
        """索引聊天记录"""
        pass
    
    def search(self, query: str, user_id: str, top_k: int = 5) -> list[dict]:
        """语义检索"""
        pass
```

#### 依赖的外部服务

| 服务 | 用途 | 推荐方案 |
|-----|------|---------|
| 向量数据库 | 存储和检索向量 | Pinecone / Qdrant / Chroma |
| Embedding 模型 | 文本向量化 | OpenAI text-embedding-3-small |

### 4.4 实现状态总结

| 功能 | 状态 | 文件位置 |
|-----|------|---------|
| 本地 JSON 持久化 | ✅ 已实现 | `graph/state_storage.py` |
| L1 元数据 | ✅ 已实现 | `graph/crush_chat_storage.py` |
| L2 结构化摘要 | ✅ 已实现 | `graph/crush_chat_storage.py` |
| L3 关键片段 | ✅ 已实现 | `graph/crush_chat_storage.py` |
| L4 语义检索 | ⏳ 待实现 | 需向量数据库 |
| 抽屉工具 | ✅ 已实现 | `graph/tools/drawer_tools.py` |

---

## 五、配置参数说明

### 5.1 Token 预算配置

```python
# graph/context_builder.py

TOKEN_BUDGET = {
    "total": 70000,              # 总预算
    "output_reserve": 8000,      # 预留给模型输出
    "layer0_system": 4000,       # 系统指令区
    "layer1_static": 15000,      # 静态情报区
    "layer2_working": 20000,     # 工作上下文
    "layer3_conversation": 20000, # 滚动对话区
    "layer4_summaries": 3000,    # 历史摘要
    "compression_threshold": 55000,  # 压缩触发阈值
}
```

### 5.2 对话压缩参数

```python
# graph/context_builder.py

CONVERSATION_CONFIG = {
    "max_recent_turns": 40,      # 最大保留轮次
    "tokens_per_turn": 450,      # 每轮估算 token
    "compression_trigger_turns": 50,  # 触发压缩的轮次阈值
}
```

### 5.3 归档管理参数

```python
# graph/archive_manager.py

ARCHIVE_CONFIG = {
    # 历史摘要分级
    "recent_summary_count": 2,      # 最近 N 份保留中等摘要
    "max_one_liner_count": 10,      # 最多保留 N 条一句话摘要
    "max_total_history": 20,        # 每类历史最多保留条数
    
    # 对话压缩
    "max_recent_turns": 40,         # 保留最近 N 轮完整对话
    "compression_batch_size": 5,    # 每超出 5 轮集中压缩一次
    "compression_threshold": 45,    # 超过此轮次开始检查
}
```

---

## 六、后续待办（P3）

### 6.1 对话压缩额外触发条件

当前只实现了基于轮次的触发，以下条件需要前端/后端配合：

| 触发条件 | 需要的信号 | 实现方式 |
|---------|-----------|---------|
| 用户切换聊天窗口 | 前端事件 | API 调用时传入 `window_changed=true` |
| 用户 2 小时无交互 | 后端定时任务 | Cron Job 检查 + 调用压缩 API |
| 语义检测到话题切换 | NLP 模型 | 实现 `detect_topic_change()` 函数 |

### 6.2 持久化存储方案

当前所有数据都存在 AgentState 中，需要持久化的内容：

| 数据 | 存储位置 | 说明 |
|-----|---------|------|
| UserContext (3×3) | 用户表 | 随用户持久化 |
| HistoryArchive | 独立表 | 关联用户 ID |
| CrushChatStorage | 独立表 + 向量库 | L1-L3 关系型，L4 向量化 |
| 当前会话状态 | Redis/Session | 短期缓存 |

### 6.3 上下文 Token 动态预警

```python
# 待实现
def get_context_health(state: AgentState) -> dict:
    """
    返回上下文健康状态
    
    {
        "total_tokens": 45000,
        "budget_usage": 0.75,
        "warning_level": "normal",  # normal/warning/critical
        "recommendations": ["建议压缩对话历史"],
    }
    """
```

---

## 附录：快速参考

### 常用导入

```python
# 类型定义
from graph.context_types import (
    UserContext, InfoSource, CrushInfo,
    ActionGuideItem, HistoryArchive, HistorySummary,
)

# 状态管理
from graph.state import (
    AgentState, create_initial_state,
    get_active_action_guides, get_completed_action_guides,
)

# 上下文组装
from graph.context_builder import (
    build_context, build_context_dict,
    check_and_compress_if_needed, get_context_stats,
)

# 归档管理
from graph.archive_manager import (
    archive_guide_on_completion,
    archive_status_on_replacement,
    compress_conversation,
)
```

### 监控和调试

```python
# 获取上下文统计
from graph.context_builder import get_context_stats
stats = get_context_stats(state)
# {"total_messages": 35, "estimated_tokens": 42000, "compression_needed": False, ...}

# 获取归档统计
from graph.archive_manager import get_archive_stats
stats = get_archive_stats(state)
# {"conversation_turns": 35, "status_history_count": 2, ...}
```

---

*文档版本: v1.0 | 更新日期: 2024-12-19*
