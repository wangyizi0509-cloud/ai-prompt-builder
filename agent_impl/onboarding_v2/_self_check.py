"""
Onboarding v2 · 契约自测脚本

作用:
1. 用 `model_validate` 把几个 mock 的 `DiagnosisReport` / `AnalyzeResponse` /
   `AnalyzeRequest` / `ReportRequest` 跑一遍,确保 schema 定义没写错,
   并覆盖关键枚举、边界值。
2. 调 `export_frontend_json.py` 重新导出一次 JSON,与仓库里的
   `question_bank.frontend.json` 做字节级比对(hash),防止 .py 改了
   没同步 JSON。
3. 打印一行 `Agent A contracts ready ✅` 表示自测通过。

运行:
    python3 agent_impl/onboarding_v2/_self_check.py

如果任何一项失败,脚本以非 0 退出码退出,CI 会拦住 PR。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# 依赖自己目录的模块(不要写成 from agent_impl.onboarding_v2.xxx import,
# 让本脚本能被任何 cwd 运行)
from hooks import HOOKS, resolve_multi_hook  # noqa: E402
from question_bank import QUESTION_BANK  # noqa: E402
from schemas import (  # noqa: E402
    AnalyzeRequest,
    AnalyzeResponse,
    CoreIssue,
    DiagnosisReport,
    LockedTeaser,
    ReportRequest,
    ScoreItem,
    Scores5D,
    SkipRule,
    StateLabel,
    TrendPrediction,
)


def _mock_analyze_request() -> AnalyzeRequest:
    return AnalyzeRequest(
        session_id="test-uuid-0001",
        free_text="他是我同事,认识快 3 个月了,我表白了 TA 说再想想,现在回消息变慢了。",
        image_urls=["https://example.com/chat-01.png"],
        ocr_texts=["[他] 嗯嗯 在忙"],
    )


def _mock_analyze_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        skip_rules={
            "A1": SkipRule(skip=True, reason="已提到同事", preselect=None, rewrite=None),
            "A2": SkipRule(skip=True, reason="已提到 3 个月", preselect=None, rewrite=None),
            "A3": SkipRule(
                skip=False,
                reason="提到表白过,改问反应",
                preselect=["A"],
                rewrite="TA 当时怎么回应的?",
            ),
            "A4": SkipRule(skip=False, reason=None, preselect=["A"], rewrite=None),
            "A5": SkipRule(skip=False, reason=None, preselect=None, rewrite=None),
        },
        first_hook={
            "verdict_tag": "信号暴露",
            "verdict_color": "amber",
            "title": "你提到 TA「回复变慢」——这不是冷淡，是在按暂停键。",
            "body": (
                "你说表白后 TA 回复变慢了，这种变慢通常不是「不喜欢」，"
                "而是 TA 还没想好怎么回应，又怕伤到你。"
                "接下来几个问题帮我确认细节，我才能分清现在是真冷淡还是你多虑。"
            ),
            "highlights": ["节奏变慢", "关系定义期", "暂停信号"],
            "evidences": [
                "你自己提到「表白完之后对方回复变慢」——这是最直接的行为信号。",
                "「再想想」三个字信息量很低，关键要看 TA 后面的动作——这是我的判断依据。",
            ],
            "call_to_action": "接下来 5 道题，每题不超过 15 秒——答完我就能给你确切的走向判断。",
        },
    )


def _mock_report_request() -> ReportRequest:
    return ReportRequest(
        session_id="test-uuid-0001",
        free_text="他是我同事,认识快 3 个月……",
        ocr_texts=["[他] 嗯嗯"],
        answers={"A3": ["A"], "A4": ["A", "C"], "A5": "C"},
    )


def _mock_diagnosis_report() -> DiagnosisReport:
    return DiagnosisReport(
        report_id="CR-DEMO0001",
        state_label=StateLabel(
            name="高危滑坡期",
            severity="danger",
            theme_color="#C00000",
        ),
        scores_5d=Scores5D(
            A=ScoreItem(score=52, note="吸引力残余尚可"),
            C=ScoreItem(score=68, note="同事接触维持了舒适感"),
            R=ScoreItem(score=18, note="张力几乎归零"),
            T=ScoreItem(score=40, note="信任被再想想压住"),
            E=ScoreItem(score=31, note="投入远大于回应"),
        ),
        core_issues=[
            CoreIssue(title="需求感暴露过早", evidence="第 3 个月就表白……"),
            CoreIssue(title="互动模式单一化", evidence="所有互动都在微信……"),
        ],
        trend_prediction=TrendPrediction(
            tone="urgent",
            text="2-3 周内 TA 大概率进一步拉开距离。",
        ),
        locked_teasers=[
            LockedTeaser(section="局势分析", teaser="TA 处于混合信号阶段……"),
            LockedTeaser(section="行动规划 · Phase 1", teaser="主动联系降到 40%……"),
            LockedTeaser(section="聊天指导", teaser="当 TA 用嗯嗯敷衍时,不要追问……"),
        ],
        urgency_text="窗口期约 2-3 周,越早调整扭转成本越低。",
        collected_summary=(
            "用户与 Crush 是同事(认识 3 个月),表白后 TA 回「再想想」,回复变慢。"
            "核心问题是需求感暴露过早,当前处于高危滑坡期。"
        ),
    )


def test_schemas() -> None:
    """跑所有 mock,确保 schema 不报错;并做几个负例。"""

    _mock_analyze_request().model_dump()
    _mock_analyze_response().model_dump()
    _mock_report_request().model_dump()
    report = _mock_diagnosis_report().model_dump()

    # 负例 1:score 超出范围
    try:
        ScoreItem(score=150, note="oops")
    except Exception:  # noqa: BLE001 - 这里就是要捕获验证错误
        pass
    else:
        raise AssertionError("ScoreItem.score=150 应该报错但没报错")

    # 负例 2:state_label.name 非枚举
    try:
        StateLabel(name="幸福期", severity="neutral", theme_color="#000000")
    except Exception:  # noqa: BLE001
        pass
    else:
        raise AssertionError("StateLabel.name=幸福期 应该报错但没报错")

    # 负例 3:extra field
    try:
        CoreIssue(title="x", evidence="y", extra_field="invalid")
    except Exception:  # noqa: BLE001
        pass
    else:
        raise AssertionError("额外字段应该触发 extra=forbid,但没有")

    # 负例 4:core_issues 只有 1 条(需求 >=2)
    try:
        DiagnosisReport(**{**_mock_diagnosis_report().model_dump(), "core_issues": [report["core_issues"][0]]})
    except Exception:  # noqa: BLE001
        pass
    else:
        raise AssertionError("core_issues=1 条应该报错但没报错")

    print(" ✓ schemas: 4 正例通过, 4 负例被正确拦截")


def test_question_bank_consistency() -> None:
    """题库结构正确性自查。"""

    assert list(QUESTION_BANK.keys()) == ["A1", "A2", "A3", "A4", "A5"], "题号顺序必须是 A1-A5"

    for qid, q in QUESTION_BANK.items():
        assert q["id"] == qid, f"{qid} id 字段不匹配"
        assert q["type"] in {"single_choice", "multiple_choice"}, f"{qid} type 非法"
        assert len(q["options"]) >= 4, f"{qid} 选项少于 4 个"
        option_ids = [o["id"] for o in q["options"]]
        assert len(option_ids) == len(set(option_ids)), f"{qid} 选项 id 有重复"
        for o in q["options"]:
            assert set(o.keys()) == {"id", "label", "is_exclusive", "allow_free_input"}, (
                f"{qid} 选项 {o['id']} 字段不完整"
            )

    # A3/A4 必须有 exclusive 选项(G 选项)
    for qid in ("A3", "A4"):
        has_ex = any(o["is_exclusive"] for o in QUESTION_BANK[qid]["options"])
        assert has_ex, f"{qid} 必须有至少一个 is_exclusive 选项"

    print(" ✓ question_bank: 5 题结构完整、选项 id 唯一、A3/A4 有 exclusive")


def test_hooks_coverage() -> None:
    """钩子覆盖自查。"""

    # A1 必须覆盖 A-E(F 是其他,不触发)
    for opt in ("A", "B", "C", "D", "E"):
        assert HOOKS["A1"]["single"][opt] is not None, f"A1 选项 {opt} 钩子缺失"
    assert HOOKS["A1"]["single"].get("F") is None, "A1 选项 F(其他)应为 None"

    # A2 必须覆盖 A-E
    for opt in ("A", "B", "C", "D", "E"):
        assert HOOKS["A2"]["single"][opt] is not None, f"A2 选项 {opt} 钩子缺失"

    # A3/A4 必须有 priority + multi_rules + fallback
    for qid in ("A3", "A4"):
        assert "priority" in HOOKS[qid], f"{qid} 缺 priority"
        assert "multi_rules" in HOOKS[qid], f"{qid} 缺 multi_rules"
        assert any(
            rule["match"].get("fallback") for rule in HOOKS[qid]["multi_rules"]
        ), f"{qid} 缺 fallback 多选规则"

    # A5 是 merged_into_summary
    assert HOOKS["A5"]["merged_into_summary"] is True

    # summary_template 存在且含 {definition} 占位符
    assert "{definition}" in HOOKS["summary_template"], "summary_template 必须含 {definition} 占位符"

    # resolve_multi_hook 抽测
    hook_ae = resolve_multi_hook("A3", ["A", "E"])
    assert hook_ae is not None and "表白" in hook_ae["text"], "A3 选 A+E 应该命中表白+被拒组合"
    hook_a_alone = resolve_multi_hook("A3", ["A"])
    assert hook_a_alone is not None and "明牌" in hook_a_alone["text"], (
        "A3 只选 A 应该按 priority 命中 single A"
    )
    hook_df = resolve_multi_hook("A4", ["D", "F"])
    assert hook_df is not None, "A4 选 D+F 应该命中 required=[D]+any_of 规则"

    print(" ✓ hooks: A1/A2 单选全覆盖、A3/A4 有 priority+fallback、resolve 抽测通过")


def test_frontend_json_sync() -> None:
    """跑 export 脚本,对比与仓库文件一致(hash 比较)。"""

    json_path = HERE / "question_bank.frontend.json"
    if not json_path.exists():
        raise AssertionError(f"{json_path} 不存在,先跑一次 export_frontend_json.py")

    existing_hash = hashlib.sha256(json_path.read_bytes()).hexdigest()

    # 重新跑 export
    result = subprocess.run(
        [sys.executable, "export_frontend_json.py"],
        cwd=HERE,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"export_frontend_json.py 执行失败:\n{result.stderr}")

    new_hash = hashlib.sha256(json_path.read_bytes()).hexdigest()
    if existing_hash != new_hash:
        raise AssertionError(
            "重新导出后 question_bank.frontend.json 发生变化——说明 .py 和 .json 不同步。\n"
            "请提交更新后的 JSON 到 git(`git add question_bank.frontend.json`)"
        )

    # 还要能正常 JSON 解析
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert set(payload["question_bank"].keys()) == {"A1", "A2", "A3", "A4", "A5"}

    print(f" ✓ frontend_json: 导出确定性验证通过 (sha256={new_hash[:10]}...)")


def main() -> None:
    print("Running Onboarding v2 self-check ...")
    test_schemas()
    test_question_bank_consistency()
    test_hooks_coverage()
    test_frontend_json_sync()
    print("\nAgent A contracts ready ✅")


if __name__ == "__main__":
    main()
