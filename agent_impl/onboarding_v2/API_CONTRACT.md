# Onboarding v2 · API 契约

> **文档性质**：后端/前端跨端契约
> **Owner**：Agent A（契约定义者）
> **消费方**：Agent B（筛题 LLM）、Agent C（报告 LLM）、Agent D（REST 后端）、Agent E/F（前端）、Agent G（main_agent 衔接）
> **冻结状态**：✅ 冻结（任何变更需重新审批并通知全员）

---

## 一、总览

Onboarding v2 提供 **3 个 REST 端点**，全部走 JSON over HTTP/HTTPS，无 cookie/JWT（本期无登录）。

| 端点 | 方法 | 归属 | 触发时机 | 核心作用 |
| :--- | :--- | :--- | :--- | :--- |
| `/api/onboarding/analyze` | POST | 新增（Agent D） | 用户在「自由描述+截图」页点击"提交"后 | LLM 节点①：筛题 + 生成第一个钩子 |
| `/api/onboarding/report` | POST | 新增（Agent D） | 题库循环（A1-A5）全部完成后 | LLM 节点③:生成免费诊断报告 |
| `/api/chat` | POST | 修改（Agent G） | 用户付费后**由 index.html onMounted 自动触发**的首轮 | 把结构化 `onboarding_payload` 渲染为模板消息塞到 main_agent 上下文 |

**注意**：第一个钩子（analyze 的 `first_hook`）使用 **vision 模型**（需要看截图）；每道卡片题选完后的中间钩子是前端本地规则触发（`hooks.py`），不走网络。

---

## 二、`POST /api/onboarding/analyze`

### 用途

用户提交自由描述 + 截图后调用。后端：
1. 读取截图 + OCR 内容 + 自由文本 → 调用 vision LLM
2. 返回 5 道题（A1-A5）的 `SkipRule`，告诉前端哪些题跳过、哪些题预选、哪些题需要改写题干
3. 返回第一个钩子文案（用户看钩子的时候前端已经同步拿到筛题结果，体感无等待）

### 请求

```http
POST /api/onboarding/analyze HTTP/1.1
Content-Type: application/json
```

```json
{
  "session_id": "7c2f3b0a-5e8d-4e1a-b9f3-12345abcde01",
  "free_text": "他是我同事，认识快 3 个月了。上周我跟他表白了,他说再想想,现在回我消息明显变慢了,我想知道还有没有机会。",
  "image_urls": [
    "https://crushe.oss-cn-hangzhou.aliyuncs.com/onboarding/7c2f3b0a/chat-01.png",
    "https://crushe.oss-cn-hangzhou.aliyuncs.com/onboarding/7c2f3b0a/chat-02.png"
  ],
  "ocr_texts": [
    "[他] 嗯嗯\n[他] 在忙\n[我] 周六有空吗想约你看电影\n[他] 最近都忙,改天吧",
    "[他] 哈哈\n[我] 那个电影真的很好看\n[他] 嗯"
  ]
}
```

### 响应 200

```json
{
  "skip_rules": {
    "A1": {
      "skip": true,
      "reason": "用户自由描述已明确提到「同事」关系,无需再问",
      "preselect": null,
      "rewrite": null
    },
    "A2": {
      "skip": true,
      "reason": "用户已说「快 3 个月」,时长覆盖",
      "preselect": null,
      "rewrite": null
    },
    "A3": {
      "skip": false,
      "reason": "用户提到表白过,但没说 TA 具体反应,改问反应细节",
      "preselect": ["A"],
      "rewrite": "TA 当时怎么回应的?之后你们相处有变化吗?"
    },
    "A4": {
      "skip": false,
      "reason": "截图显示回复明显变慢,预选 A;但其他负面信号还需用户确认",
      "preselect": ["A"],
      "rewrite": null
    },
    "A5": {
      "skip": false,
      "reason": "用户问「还有没有机会」,指向 E 选项,但让用户自己确认",
      "preselect": ["C"],
      "rewrite": null
    }
  },
  "first_hook": "你提到表白完之后对方回复变慢了——这个信号我见过很多次。「再想想」这三个字本身没什么信息量,关键在 TA 后面的行为。接下来我需要你再帮我确认几个细节,我好判断现在是「真冷淡」还是「你过于紧张导致误判」。"
}
```

### 降级行为

| 场景 | 行为 |
| :--- | :--- |
| vision LLM 超时(>20s) | 返回 `{"skip_rules": {A1-A5 全部 skip=false,其他字段 null}, "first_hook": "我大概了解了你的情况,咱们先通过几个问题把细节说清楚,我再给你看专业的诊断。"}`——前端把 5 道题全部按默认流程渲染 |
| vision LLM 报错 | 同上,HTTP 状态仍返回 200(不阻断用户流程),日志记录错误 |
| OCR 全失败(`ocr_texts` 全是空字符串) | 仍调用 LLM,但在 prompt 里说明「只能依赖用户自由文本」 |
| `free_text` < 5 字 | HTTP 422,前端阻止提交 |

---

## 三、`POST /api/onboarding/report`

### 用途

用户答完所有没被 skip 的题后,前端把完整答卷回传。后端:
1. 把自由文本 + OCR + 答题结果组装成 prompt,调用 LLM 节点③
2. 返回一份完整的 `DiagnosisReport`(见 `schemas.py`)
3. 前端直接把 report 渲染到「诊断报告页」,用户看到后进入付费闸门

### 请求

```http
POST /api/onboarding/report HTTP/1.1
Content-Type: application/json
```

```json
{
  "session_id": "7c2f3b0a-5e8d-4e1a-b9f3-12345abcde01",
  "free_text": "他是我同事,认识快 3 个月了。上周我跟他表白了,他说再想想,现在回我消息明显变慢了,我想知道还有没有机会。",
  "ocr_texts": [
    "[他] 嗯嗯\n[他] 在忙\n[我] 周六有空吗想约你看电影\n[他] 最近都忙,改天吧",
    "[他] 哈哈\n[我] 那个电影真的很好看\n[他] 嗯"
  ],
  "answers": {
    "A3": ["A"],
    "A4": ["A", "C"],
    "A5": "C"
  }
}
```

> 注:A1/A2 被 skip 不在 answers 里。answers 的 key 是题号,值为单选 str 或多选 list。

### 响应 200

```json
{
  "report_id": "CR-428103A1",
  "state_label": {
    "name": "高危滑坡期",
    "severity": "danger",
    "theme_color": "#C00000"
  },
  "scores_5d": {
    "A": { "score": 52, "note": "表白后吸引力仍有剩余,但正在被需求感消耗" },
    "C": { "score": 68, "note": "日常同事接触维持了基本的舒适感" },
    "R": { "score": 18, "note": "张力几乎归零,互动以敷衍为主,见截图" },
    "T": { "score": 40, "note": "TA 没有拒绝过所有互动,但信任度被「再想想」压住" },
    "E": { "score": 31, "note": "你的投入远大于对方回应,近一周回复延迟 3 倍" }
  },
  "core_issues": [
    {
      "title": "需求感暴露过早",
      "evidence": "你在认识第 3 个月就表白了,此时 TA 对你的吸引力感知还没建立起来。从截图看,TA 此后进入了「被追的高位」,你的每一步动作都会被用「他又在示好」的滤镜过滤。"
    },
    {
      "title": "互动模式单一化",
      "evidence": "截图里所有互动都发生在微信文字聊天,话题集中在日常问候和邀约。TA 没有机会在不同场景下重新认识你,形象被锁死在「每天找我的同事」。"
    },
    {
      "title": "邀约被拒后的补救动作错位",
      "evidence": "看到 TA 说「最近都忙,改天吧」之后,你没有顺势后撤,反而继续主动聊电影,这反而强化了 TA 的「被追感」。"
    }
  ],
  "trend_prediction": {
    "tone": "urgent",
    "text": "按目前的趋势,如果不做调整,2-3 周内 TA 大概率会进一步拉开距离,给出明确的「朋友」定性。"
  },
  "locked_teasers": [
    {
      "section": "完整局势分析 · 对方心理画像",
      "teaser": "TA 目前对你处于「混合信号」阶段——行为上保留距离(邀约拒绝、回复延迟),但没有做出明确的关系定性……"
    },
    {
      "section": "专属行动规划 · Phase 1(第 1-2 周)",
      "teaser": "Week 1:主动联系降到现在的 40%。不主动追问状态,不发长段文字。你的任务是……"
    },
    {
      "section": "即时行动指南 · 下一条消息",
      "teaser": "当 TA 再次用「嗯嗯」敷衍回复时,不要追问、不要解释,直接……"
    }
  ],
  "urgency_text": "窗口期约 2-3 周。越早调整节奏,扭转成本越低——像你这种情况,每多等一周,「备胎」的心理定位就会被 TA 再强化一次。",
  "collected_summary": "用户与 Crush 是同事(认识约 3 个月),已主动表白且 TA 回「再想想」,随后出现回复变慢+邀约被拒(截图佐证)。用户目标是想确认 TA 的态度,5 维诊断中 R=18、E=31 偏低,核心问题是需求感暴露过早+互动模式单一化,当前处于「高危滑坡期」。"
}
```

### 降级行为

| 场景 | 行为 |
| :--- | :--- |
| LLM 超时/失败 | HTTP 503 `{"error": "report_unavailable", "message": "诊断报告生成失败,请重试"}`。前端显示重试按钮,不跳转到付费页 |
| LLM 返回不符合 schema | 后端 `model_validate` 会报错 → 触发一次重试(加温度修正),仍失败则走 503 |

---

## 四、`POST /api/chat` (v2.1 修订 · `onboarding_payload` 结构化衔接)

### 用途

用户付费成功进入主对话。**由 `index.html` 在 onMounted 自动触发**——用户 **不需要** 键入任何文字,前端把 localStorage 里的完整漏斗数据(自由描述 / OCR / 筛题答卷)组装成 `onboarding_payload`,以 `message=""` 发起首轮 `/api/chat/stream`。后端首轮检测到 payload 时,用固定模板把它渲染成一条 user 消息塞进 thread,main_agent 第一步就按指令去调 `call_status_agent`,用户看到的第一条气泡是 AI 产出的状态报告卡 + 建议。

> v2.1 之前的版本依赖 `DiagnosisReport.collected_summary` + `onboarding_summary` 字符串前置,已废弃。`collected_summary` 仍保留在 `DiagnosisReport` 里供分析/埋点使用,**不再**由前端发送给 `/api/chat`。

### 请求

```http
POST /api/chat/stream HTTP/1.1
Content-Type: application/json
```

```json
{
  "thread_id": "thread_20260421_001",
  "session_id": "7c2f3b0a-5e8d-4e1a-b9f3-12345abcde01",
  "message": "",
  "onboarding_payload": {
    "free_text": "他是我同事,认识快 3 个月了。上周我跟他表白了,他说再想想,现在回我消息明显变慢了。",
    "ocr_texts": [
      { "ocr_result": "[他] 嗯嗯\n[我] 周六有空吗想约你看电影\n[他] 最近都忙,改天吧", "ocr_failed": false },
      { "ocr_result": "", "ocr_failed": true }
    ],
    "answers": { "A1": "A", "A3": ["A", "C"], "A5": "C" }
  }
}
```

字段约束(`OnboardingPayload` · 见 `api/onboarding_handoff_prompt.py`):

- `free_text`:用户在自由描述页的原文,字符串(可空字符串)
- `ocr_texts`:`list[OnboardingOcr]`,每项 `{ ocr_result: str, ocr_failed: bool }`;按上传顺序保序
- `answers`:`dict[str, str | list[str]]`,key 为题号(A1-A5),value 为选项码或选项码列表;**被 skip 的题不出现**

### 后端行为(Agent G 实现,见 `api/chat.py` + `api/stream.py` + `api/onboarding_handoff_prompt.py`)

1. **首轮判定**:`_is_first_turn_for_thread(base_state)` 仍保留原语义——当 thread 的 `messages + layer3.all_messages` 都为空时视为首轮。
2. **模板渲染**:首轮且 `onboarding_payload` 存在时,调用 `render_onboarding_first_turn_message(payload)` 产出固定模板 user_message,结构为:
   - `[系统指令 · 仅本轮]` 段:命令 main_agent 立即调用 `call_status_agent`,只传 purpose 不传 summary(status 子图与 main_agent 共享 `parent_state` / `messages`,能直接读到下面的原始素材,零信息损失)
   - `[诊断素材]` 段:
     - `## 用户自由描述`:`free_text`(空则 `(用户未填写)`)
     - `## 截图 OCR`:逐张展开 `ocr_texts`(OCR 失败时标 `(OCR 失败)`)
     - `## 筛题答卷`:通过 `onboarding_v2/question_bank.py:QUESTION_BANK` 把题号+选项码映射成人话题干+人话选项
3. **走普通 user turn**:渲染后的消息按**普通用户消息**进入 thread → `messages` → `layer3.all_messages`,后续压缩由 layer3 常规逻辑处理。
4. **非首轮静默忽略**:若 thread 已有历史,`onboarding_payload` 即使被前端带上也直接忽略,不影响对话。

### 响应

响应体不变(沿用现有 SSE 流式格式)。首条可见 AI 气泡通常是 `call_status_agent` 产出的状态报告卡,其后是 main_agent 的建议。

### 降级

| 场景 | 行为 |
| :--- | :--- |
| `onboarding_payload` 缺失 / `null` | 按普通路径处理(正常情况下 `message` 也应非空——前端未拿到 payload 时不会触发 onMounted 自动发送) |
| `onboarding_payload` 存在但所有字段为空 | 仍走模板渲染,三段素材都会被写成 `(用户未填写)` 占位符;main_agent 收到后会按系统指令调 status,但因为没材料,状态子图会快速回落到澄清提问 |
| `onboarding_payload` 字段类型不符 | FastAPI/Pydantic 层直接 422(由 `OnboardingPayload` 严格校验) |

---

## 五、公共说明

### 请求超时策略

| 端点 | 客户端建议超时 | 服务端上限 |
| :--- | :--- | :--- |
| `/analyze` | 25s | 20s(超时返回降级响应) |
| `/report` | 40s | 35s(超时返回 503) |
| `/chat` | 参照现有 SSE 流策略 | 不变 |

### 鉴权

本期 `/analyze` 和 `/report` **不鉴权**(无登录),用 `session_id`(前端 UUID)做追踪。

`/chat` 维持原鉴权策略(虽然本期 DISABLE_AUTH 默认开,但字段行为不变)。

### 错误响应格式统一

```json
{
  "error": "machine_readable_code",
  "message": "给用户展示的人话",
  "detail": "可选:给开发者看的堆栈摘要"
}
```

---

## 六、变更记录

| 日期 | 作者 | 变更 |
| :--- | :--- | :--- |
| 2026-04-21 | Agent A | 初版冻结 |
| 2026-04-23 | Agent G | v2.1: onboarding_summary → onboarding_payload 结构化,首轮由前端自动触发,废弃 onboarding_handoff state 字段 |
