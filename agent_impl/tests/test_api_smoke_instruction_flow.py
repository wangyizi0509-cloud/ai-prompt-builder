"""
最小化真实 API 冒烟测试（避免跑全量）

目标：
1) 验证 Main Agent 新增字段 instruction/decision_rationale 不会破坏解析与状态流转
2) 验证 Main Agent -> Status Agent 的链路在真实 API 下可跑通
3) 验证 Status Agent 能接收到 instruction（至少不因 prompt 缺变量报错，且产出 report）

注意：
- 该测试需要真实 API Key（由环境变量决定 provider）
- 该测试刻意只跑 1 条路径，避免内存/成本爆炸
"""

import pytest

from graph.state import create_initial_state
from graph.workflow import get_workflow
from tests.conftest import run_workflow_turn


@pytest.mark.api_test
def test_main_to_status_instruction_smoke():
    wf = get_workflow()

    # 通过强约束提示，尽量让 Main Agent 稳定委派 Status Agent
    state = create_initial_state(
        "你现在是 Main Agent。请严格只输出 JSON，不要输出多余文本。\n"
        "要求：\n"
        '- 必须调用 delegate_to_status 工具\n'
        '- instruction 必须为一句明确的 Brief（>=20字），例如：请优先判断关系阶段是否发生变化，并列出关键证据链。\n'
        '- decision_rationale 必须为一句 OODA 决策理由（>=20字）\n'
        "背景：我和一个女生认识三个月，同事，经常一起吃饭，最近她主动约我周末看电影。\n"
        "我想知道我们现在是什么阶段，有什么风险点。"
    )

    # 测试环境：跳过 onboarding，直接进主流程
    state["onboarding_completed"] = True
    state["route_to"] = "main_agent"
    # 不强行把子 Agent 推入“无法提问只能硬出报告”的路径（真实模型可能返回 report_content=null）
    # 允许 Status Agent 走一次提问分支也可以接受（本测试的目标是链路不崩溃 + 关键字段可用）。
    state["max_questions"] = 1

    # 1) 先跑到 Main Agent（会产生真实 API 调用）
    out1 = wf.invoke(state, config={"configurable": {"thread_id": "api_smoke_instruction"}})

    # 允许 Main Agent 在真实场景下先 ask_user 一轮
    if out1.get("pending_questions"):
        out1 = run_workflow_turn(
            wf,
            out1,
            "补充关键信息：我们聊天频率每天1-2次，她会主动开启话题；电影是她提的，时间地点她也给了两个选项。\n"
            "最近一次互动：我说周末有空，她回“好呀，那你更想看哪部？”并加了一个笑哭表情。\n"
            "我的目标：想判断她是不是对我有明确兴趣，以及我该怎么稳住推进。",
        )

    out2 = out1

    # instruction 应当在 Main 调度专家时写入 state（如果 Main 选择只提问并未调度，这里会为空）
    assert isinstance(out2.get("instruction"), str), "instruction 字段应存在且为 string（允许为空）"

    # 关键：必须实际执行过 Status Agent（产出报告或提问等待用户回答）
    status_ran = (
        out2.get("current_agent") == "status_agent"
        or out2.get("completion_status") == "COMPLETED"
        or (isinstance(out2.get("status_report"), str) and len(out2.get("status_report", "")) > 0)
        or bool(out2.get("pending_questions"))
    )
    assert status_ran, "未观察到 Status Agent 的执行结果（completion/status_report/pending_questions）"

    # Status Agent 正常产出（不要求一定完成整套链路，只验证核心产物与字段类型）
    if out2.get("completion_status") == "COMPLETED":
        assert isinstance(out2.get("status_report"), str) and len(out2["status_report"]) > 0

