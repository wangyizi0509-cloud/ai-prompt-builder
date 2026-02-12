# Onboarding 模块说明

> 用户首次使用时的信息收集与初步诊断流程

---

## 一、模块定位

Onboarding 是用户进入产品后的**第一道关卡**，目标是：

1. **极速收集关键信息**：用户是谁、Crush 是谁、当前关系状态、核心痛点
2. **建立专业信任**：通过"局势初判卡"展示产品价值
3. **无缝过渡到主流程**：信息收集完成后，移交给 Main Agent

---

## 二、核心概念

### 2.1 MAS (Minimum Alert Set)

**最小预警信息集**——判断是否可以进行初步诊断的最低信息门槛：

| 维度 | 要求 |
|:----|:----|
| **数据量** | 至少 3-5 轮有实质内容的对话截图，或详细描述 |
| **关系基调** | 能判断是"陌生/熟人"以及"追求/被追求"的基本态势 |

- ❌ 不满足 MAS → 继续追问（索要更多截图或信息）
- ✅ 满足 MAS → 生成《局势初判卡》，移交 Main Agent

### 2.2 《局势初判卡》

当 MAS 满足后生成的初步诊断结果，包含：

| 字段 | 说明 |
|:----|:----|
| **verdict** | 风险/机会定级：🔴高危 / 🟡迷雾 / 🟢机会 |
| **evidence** | 核心证据锚点：引用用户提供的具体表象特征 |
| **projection** | 走势预演：基于当前趋势的短期预测 |
| **call_to_action** | 诱导动作：引导用户进入深度诊断 |

---

## 三、执行流程

```
用户首次输入
    │
    ▼
┌─────────────────────────────────────┐
│  Step 1: MAS 校验                    │
│  判断信息是否满足最小预警信息集        │
└─────────────────────────────────────┘
    │
    ├── ❌ 不满足 ──────────────────────────────────┐
    │                                              │
    ▼                                              ▼
┌─────────────────────────────────────┐    ┌─────────────────────────────────────┐
│  Step 2: 追问 (The Chase)            │    │  Step 3: 初判与过渡 (The Hook)       │
│  索要更多截图/信息                    │    │  生成《局势初判卡》                   │
│  参考 onboarding_logic.md 的问题库   │    │  移交 Main Agent                     │
└─────────────────────────────────────┘    └─────────────────────────────────────┘
    │                                              │
    └──────────── 循环直到满足 MAS ────────────────┘
```

### 轮次限制

- 最多 `onboarding_max_turns` 轮（可配置）
- 超过轮次仍未满足 MAS，也会强制移交

---

## 四、与上下文工程的关系

Onboarding 完成后，会触发**上下文系统的初始化**：

```
Onboarding 完成
    │
    ▼
┌─────────────────────────────────────┐
│  触发 Organize Agent                 │
│  从 Onboarding 对话中提取信息         │
└─────────────────────────────────────┘
    │
    ├── 用户画像（姓名、性别、年龄等）
    │       ↓
    │   写入 Layer 1 (user_info.user_provide)
    │
    ├── Crush 画像（描述、特征等）
    │       ↓
    │   写入 Layer 1 (crush_info.user_provide)
    │
    ├── 关系背景（认识方式、时长等）
    │       ↓
    │   写入 Layer 1 (both_info.user_provide)
    │
    └── 短期动态（最近发生的事、当前痛点）
            ↓
        写入 Layer 2 (dynamic_intels)
```

**关键点**：
- Onboarding 收集的信息是 **Layer 1 的初始数据源**
- 这是用户画像的"第一桶金"，后续通过对话提取持续积累

---

## 五、文件结构

```
onboarding/
├── README.md                    ← 你正在看的这个
├── onboarding_agent.py          ← Onboarding Agent 核心逻辑
├── onboarding_logic.md          ← 追问问题库（MAS 缺失时使用）
├── workflow.py                  ← LangGraph 工作流定义
├── state.py                     ← 状态定义（OnboardingState, OnboardingHandoff）
```

```
prompts/
└── onboarding_agent.md          ← Onboarding Agent 的 System Prompt（全局统一目录）
```

### Message Stack 注入说明

Onboarding 与主 Agent 使用同构的消息栈输入：
1. `SystemMessage`（`prompts/onboarding_agent.md`）
2. `HumanMessage`（`<dossier>` 上下文）
3. `AIMessage`（Virtual Ack）
4. 历史消息窗口（message list）
5. Onboarding 运行时上下文（轮次 + 参考问题）
6. 当前用户输入

---

## 六、配置项

| 配置 | 说明 | 默认值 |
|:----|:----|:------|
| `onboarding_max_turns` | 最大追问轮次 | 10 |

---

## 七、移交机制

当 Onboarding 完成（满足 MAS 或达到轮次上限），会生成 `OnboardingHandoff` 对象：

```python
OnboardingHandoff = {
    "collected_info": {
        "user_profile": { ... },      # 用户画像
        "crush_profile": { ... },     # Crush 画像
        "pain_points": [ ... ],       # 核心痛点
    },
    "preliminary_assessment": { ... }, # 局势初判卡
    "suggested_action": "...",         # 给 Main Agent 的建议
    "recommendation": "...",           # 移交备注
}
```

Main Agent 收到后：
1. 将 `collected_info` 写入 Layer 1/2
2. 根据 `suggested_action` 决定下一步（通常是调用 Status Agent 进行深度诊断）

---

## 八、相关文档

| 文档 | 说明 |
|:----|:----|
| `context_system/01_Overview/System_Overview.md` | 上下文系统全景图 |
| `context_system/02_Specs/layer1_spec_v1.0.md` | Layer 1 规范（Onboarding 信息写入目标） |
| `context_system/03_Strategies/refining_strategy_v1.0.md` | 提纯策略（含 Onboarding 触发说明） |

---

*最后更新：2026-01-15*
