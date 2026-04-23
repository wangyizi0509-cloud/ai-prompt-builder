from __future__ import annotations

from typing_extensions import NotRequired, TypedDict


class ToolResult(TypedDict, total=False):
    ok: bool
    output: str
    state_patch: dict
    error: NotRequired[str]
    deferred_interrupt: NotRequired[dict]


LIST_APPEND_KEYS: set[str] = {"tool_patch_log"}


def merge_state_patch(state: dict, patch: dict) -> dict:
    if not patch:
        return dict(state)

    merged = dict(state)
    for key, patch_value in patch.items():
        if key in merged and isinstance(merged.get(key), dict) and isinstance(patch_value, dict):
            merged[key] = _merge_dicts(merged[key], patch_value)
            continue

        if key in LIST_APPEND_KEYS and isinstance(merged.get(key), list) and isinstance(patch_value, list):
            merged[key] = list(merged[key]) + list(patch_value)
            continue

        merged[key] = patch_value

    return merged


def merge_patches(state: dict, patches: list[dict]) -> dict:
    merged = dict(state)
    for p in patches or []:
        if not p:
            continue
        merged = merge_state_patch(merged, p)
    return merged


def _merge_dicts(base: dict, update: dict) -> dict:
    merged = dict(base)
    for key, value in update.items():
        if key in merged and isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(merged[key], value)
            continue
        if key in LIST_APPEND_KEYS and isinstance(merged.get(key), list) and isinstance(value, list):
            merged[key] = list(merged[key]) + list(value)
            continue
        merged[key] = value
    return merged
