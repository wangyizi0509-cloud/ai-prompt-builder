"""
Onboarding v2 · 题库（路径 A · 有截图主流路径）

只包含路径 A 的 A1-A5 五道题。路径 B（没加微信）本期不做，
不在题库中出现。题目文案**严格照抄**需求文档 2.3 节「路径 A」。

结构说明：
- `id` / `type` / `question`：题的元信息
- `options`：选项列表，每条含 `id`（字母）、`label`（文案）、
  `is_exclusive`（选中后清空其他，如「以上都没有」）、
  `allow_free_input`（选中后露一个自由输入框，如「其他」）
- `allow_multi`：False=单选，True=多选
- `required`：当前全部题目都必答（但可以被筛题跳过）
- `rewrite_mapping`：「带槽位」替换规则。key 是从自由描述里抽出的关键词
  （或短语），value 含 `preselect`（预选）和 `rewrite`（重写题干）。
  Agent B 的 vision 模型判断用户自由描述命中哪个 key 后，会把对应
  `SkipRule` 返回给前端。

⚠️ 题目文案和选项字母对应关系冻结后不得修改，否则下游钩子、
    筛题、诊断报告全部错位。新增选项只能加到选项末尾。
"""

from __future__ import annotations

QUESTION_BANK: dict[str, dict] = {
    "A0": {
        "id": "A0",
        "type": "single_choice",
        "question": "先问你一个小问题 — 你是？",
        "options": [
            {"id": "A", "label": "男生", "is_exclusive": False, "allow_free_input": False},
            {"id": "B", "label": "女生", "is_exclusive": False, "allow_free_input": False},
            {"id": "C", "label": "不想说", "is_exclusive": False, "allow_free_input": False},
        ],
        "allow_multi": False,
        "required": True,
        "rewrite_mapping": {},  # 性别题不做筛题
    },
    "A1": {
        "id": "A1",
        "type": "single_choice",
        "question": "你们是怎么认识的？",
        "options": [
            {
                "id": "A",
                "label": "同事（同公司/同团队）",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "B",
                "label": "同学（同校/同班/同社团）",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "C",
                "label": "网友（社交软件/游戏/兴趣社群）",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "D",
                "label": "朋友介绍/相亲",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "E",
                "label": "线下偶遇（健身房/咖啡店/活动等）",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "F",
                "label": "其他",
                "is_exclusive": False,
                "allow_free_input": True,
            },
        ],
        "allow_multi": False,
        "required": True,
        "rewrite_mapping": {
            # 用户自由描述已明确提到关系性质 → 直接跳过
            "同事": {"skip": True, "reason": "用户自述已是同事关系"},
            "同学": {"skip": True, "reason": "用户自述已是同学关系"},
            "网友": {"skip": True, "reason": "用户自述是线上认识"},
            "相亲": {"skip": True, "reason": "用户自述是朋友介绍/相亲"},
            "朋友介绍": {"skip": True, "reason": "用户自述是朋友介绍"},
        },
    },
    "A2": {
        "id": "A2",
        "type": "single_choice",
        "question": "你们认识多久了？",
        "options": [
            {
                "id": "A",
                "label": "不到 1 个月",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "B",
                "label": "1-3 个月",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "C",
                "label": "3-6 个月",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "D",
                "label": "半年到 1 年",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "E",
                "label": "1 年以上",
                "is_exclusive": False,
                "allow_free_input": False,
            },
        ],
        "allow_multi": False,
        "required": True,
        "rewrite_mapping": {
            # 自由描述里已说了具体时长 → 跳过
            "一个月": {"skip": True, "reason": "用户已说明时长（1 个月内）"},
            "三个月": {"skip": True, "reason": "用户已说明时长"},
            "半年": {"skip": True, "reason": "用户已说明时长"},
            "一年": {"skip": True, "reason": "用户已说明时长"},
            "两年": {"skip": True, "reason": "用户已说明时长（>1 年）"},
        },
    },
    "A3": {
        "id": "A3",
        "type": "multiple_choice",
        "question": "到目前为止，你有没有做过下面这些事？（可多选）",
        "options": [
            {
                "id": "A",
                "label": "主动表白 / 说过喜欢 TA",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "B",
                "label": "送过比较贵重的礼物",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "C",
                "label": "频繁主动找 TA 聊天（每天主动开话题）",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "D",
                "label": "约过 TA 单独出来（成功）",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "E",
                "label": "约过 TA 单独出来（被拒绝/被放鸽子）",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "F",
                "label": "在社交场合对 TA 表现出明显不同（当众特别照顾）",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "G",
                "label": "以上都没有，一直没敢有明显动作",
                "is_exclusive": True,
                "allow_free_input": False,
            },
            {
                "id": "H",
                "label": "其他",
                "is_exclusive": False,
                "allow_free_input": True,
            },
        ],
        "allow_multi": True,
        "required": True,
        "rewrite_mapping": {
            # 自由描述里提到表白过 → 预选 A，改问 TA 的反应
            "表白": {
                "skip": False,
                "preselect": ["A"],
                "rewrite": "TA 当时怎么回应的？之后你们相处有变化吗？",
                "reason": "用户已提到表白过，改问反应细节",
            },
            "告白": {
                "skip": False,
                "preselect": ["A"],
                "rewrite": "TA 当时怎么回应的？之后你们相处有变化吗？",
                "reason": "用户已提到告白过",
            },
            "送礼物": {
                "skip": False,
                "preselect": ["B"],
                "reason": "用户已提到送礼物",
            },
        },
    },
    "A4": {
        "id": "A4",
        "type": "multiple_choice",
        "question": "下面这些情况，有发生在你身上的吗?（可多选）",
        "options": [
            {
                "id": "A",
                "label": "TA 回消息越来越慢 / 经常不回",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "B",
                "label": "TA 聊天时很敷衍（嗯、哦、哈哈）",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "C",
                "label": "TA 拒绝过单独见面",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "D",
                "label": "TA 提过\"我们就是朋友\" / \"你是好人\"之类的话",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "E",
                "label": "TA 跟别人互动明显比跟你热情",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "F",
                "label": "TA 会主动找你，但只在需要帮忙的时候",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "G",
                "label": "以上都没有，TA 对我还行",
                "is_exclusive": True,
                "allow_free_input": False,
            },
            {
                "id": "H",
                "label": "其他",
                "is_exclusive": False,
                "allow_free_input": True,
            },
        ],
        "allow_multi": True,
        "required": True,
        "rewrite_mapping": {
            "已读不回": {
                "skip": False,
                "preselect": ["A"],
                "rewrite": "在这之前 TA 是怎么回你消息的？",
                "reason": "用户已提到被已读不回",
            },
            "不回消息": {
                "skip": False,
                "preselect": ["A"],
                "rewrite": "在这之前 TA 是怎么回你消息的？",
                "reason": "用户已提到 TA 不回消息",
            },
            "好人卡": {
                "skip": False,
                "preselect": ["D"],
                "reason": "用户已提到收到好人卡",
            },
            "工具人": {
                "skip": False,
                "preselect": ["F"],
                "reason": "用户已提到被当工具人",
            },
        },
    },
    "A5": {
        "id": "A5",
        "type": "single_choice",
        "question": "你现在最想解决的是什么？",
        "options": [
            {
                "id": "A",
                "label": "想确认关系 / 在一起",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "B",
                "label": "想先拉近距离 / 让对方对我更有好感",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "C",
                "label": "想知道对方到底什么态度 / 有没有机会",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "D",
                "label": "关系倒退了，想挽回 / 修复",
                "is_exclusive": False,
                "allow_free_input": False,
            },
            {
                "id": "E",
                "label": "不确定该不该继续追 / 想听听专业判断",
                "is_exclusive": False,
                "allow_free_input": False,
            },
        ],
        "allow_multi": False,
        "required": True,
        "rewrite_mapping": {
            "该不该继续": {
                "skip": False,
                "preselect": ["E"],
                "reason": "用户已提及是否继续的犹豫",
            },
            "挽回": {
                "skip": False,
                "preselect": ["D"],
                "reason": "用户已提及挽回意图",
            },
            "想在一起": {
                "skip": False,
                "preselect": ["A"],
                "reason": "用户已明确想确认关系",
            },
        },
    },
}


def get_question(qid: str) -> dict:
    """通过题号取单题（复制一份，避免外部修改）。"""

    import copy

    return copy.deepcopy(QUESTION_BANK[qid])


def list_question_ids() -> list[str]:
    """按题号顺序返回题号列表。"""

    return list(QUESTION_BANK.keys())
