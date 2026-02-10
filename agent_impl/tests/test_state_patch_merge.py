import json

from agents.tooling.patch import merge_patches, merge_state_patch
from agents.tooling.tool_result import error, ok


def test_merge_state_patch_overwrites_scalars():
    state = {"a": 1, "b": 2}
    merged = merge_state_patch(state, {"b": 3})
    assert merged["a"] == 1
    assert merged["b"] == 3


def test_merge_state_patch_merges_nested_dicts():
    state = {"layer2_memory": {"current_status_report": {"id": "r1", "stage": "L1"}, "x": 1}}
    patch = {"layer2_memory": {"current_status_report": {"stage": "L2"}, "y": 2}}
    merged = merge_state_patch(state, patch)
    assert merged["layer2_memory"]["current_status_report"]["id"] == "r1"
    assert merged["layer2_memory"]["current_status_report"]["stage"] == "L2"
    assert merged["layer2_memory"]["x"] == 1
    assert merged["layer2_memory"]["y"] == 2


def test_merge_state_patch_appends_lists_for_whitelisted_keys():
    state = {"tool_patch_log": [{"i": 1}]}
    patch = {"tool_patch_log": [{"i": 2}]}
    merged = merge_state_patch(state, patch)
    assert merged["tool_patch_log"] == [{"i": 1}, {"i": 2}]


def test_tool_result_helpers_are_json_serializable():
    payload_ok = ok("hello", state_patch={"a": 1})
    payload_err = error("bad", state_patch={"b": 2})
    json.dumps(payload_ok, ensure_ascii=False)
    json.dumps(payload_err, ensure_ascii=False)


def test_merge_patches_applies_in_order():
    state = {"a": 1, "layer": {"x": 1}}
    patches = [{"a": 2}, {"layer": {"y": 2}}, {"a": 3}]
    merged = merge_patches(state, patches)
    assert merged["a"] == 3
    assert merged["layer"] == {"x": 1, "y": 2}

