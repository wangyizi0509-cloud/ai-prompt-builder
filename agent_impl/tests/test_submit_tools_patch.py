from graph.tools.submit_tools import submit_action_guide, submit_action_plan, submit_status_report


def test_submit_status_report_returns_state_patch():
    out = submit_status_report.invoke(
        {
            "report_markdown": "# Report\nhello",
            "stage": "L1",
            "stage_description": "desc",
            "acr_analysis": {},
            "key_issues": [],
            "risk_points": [],
        }
    )
    assert out["ok"] is True
    assert isinstance(out.get("state_patch"), dict)
    layer2 = out["state_patch"].get("layer2_memory") or {}
    assert layer2.get("current_status_report")


def test_submit_action_plan_returns_state_patch():
    out = submit_action_plan.invoke(
        {
            "goal": "g",
            "strategy": "s",
            "phases": [],
            "key_principles": [],
            "summary": "",
        }
    )
    assert out["ok"] is True
    layer2 = out["state_patch"].get("layer2_memory") or {}
    assert layer2.get("current_action_plan")


def test_submit_action_guide_returns_state_patch():
    out = submit_action_guide.invoke(
        {
            "title": "t",
            "one_liner": "o",
            "guide_markdown": "content",
            "current_task": "",
            "steps": [],
            "talking_points": [],
            "dos": [],
            "donts": [],
            "next_milestone": "",
        }
    )
    assert out["ok"] is True
    layer2 = out["state_patch"].get("layer2_memory") or {}
    guides = layer2.get("action_guides") or []
    assert isinstance(guides, list)
    assert guides

