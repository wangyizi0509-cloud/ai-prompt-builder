from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig


def sanitize_runtime_config(config: RunnableConfig | None) -> dict[str, Any]:
    """
    Return a shallow-copied RunnableConfig with safe metadata.

    LangGraph checkpointers will serialize checkpoint metadata and may fail when
    metadata contains framework/runtime objects (e.g. auth user objects).
    Keep only scalar metadata values for nested graph/tool invocations.
    """
    cfg = dict(config or {})

    metadata = cfg.get("metadata")
    if isinstance(metadata, dict):
        clean_metadata: dict[str, Any] = {}
        for key, value in metadata.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, str):
                clean_metadata[key] = value.replace("\u0000", "")
            elif isinstance(value, (int, float, bool)) or value is None:
                clean_metadata[key] = value
        if clean_metadata:
            cfg["metadata"] = clean_metadata
        else:
            cfg.pop("metadata", None)
    else:
        cfg.pop("metadata", None)

    return cfg


def resolve_runtime_checkpointer(config: RunnableConfig | None) -> Any:
    """Extract runtime checkpointer from top-level or configurable payload."""
    cfg = dict(config or {})
    checkpointer = cfg.get("checkpointer")
    if checkpointer is not None:
        return checkpointer

    configurable = cfg.get("configurable")
    if isinstance(configurable, dict):
        nested = configurable.get("checkpointer")
        if nested is None:
            nested = configurable.get("__pregel_checkpointer")
        if nested is not None:
            return nested
    return None


def sanitize_nested_runtime_config(config: RunnableConfig | None) -> dict[str, Any]:
    """
    Return a config suitable for nested graph/tool invoke.

    Nested invoke should never receive checkpointer objects in config payload,
    otherwise checkpoint metadata serialization may fail.
    """
    cfg = sanitize_runtime_config(config)
    cfg.pop("checkpointer", None)

    configurable = cfg.get("configurable")
    if isinstance(configurable, dict):
        configurable_copy = dict(configurable)
        configurable_copy.pop("checkpointer", None)
        configurable_copy.pop("__pregel_checkpointer", None)
        if configurable_copy:
            cfg["configurable"] = configurable_copy
        else:
            cfg.pop("configurable", None)
    else:
        cfg.pop("configurable", None)

    return cfg
