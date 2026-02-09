from __future__ import annotations

from agents.tooling.patch import ToolResult


def ok(output: str = "", state_patch: dict | None = None) -> ToolResult:
    patch = state_patch or {}
    return {"ok": True, "output": output, "state_patch": patch}


def error(output: str, *, state_patch: dict | None = None) -> ToolResult:
    patch = state_patch or {}
    return {"ok": False, "output": output, "state_patch": patch}

