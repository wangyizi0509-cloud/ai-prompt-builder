from skills.tool import create_skill_loader


def test_load_skill_returns_prompt_text():
    tool = create_skill_loader(["inquiry"])
    out = tool.invoke({"skill_id": "inquiry"})
    assert out["ok"] is True
    assert isinstance(out.get("output"), str)
    assert out["output"].strip()


def test_load_skill_invalid_id_returns_error():
    tool = create_skill_loader(["inquiry"])
    out = tool.invoke({"skill_id": "not_a_real_skill"})
    assert out["ok"] is False

