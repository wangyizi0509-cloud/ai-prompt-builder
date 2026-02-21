from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig


def _is_proxy_user(value: Any) -> bool:
    """True if value is a ProxyUser (LangChain Cloud injects it; not JSON-serializable)."""
    return type(value).__name__ == "ProxyUser"


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

    # LangChain Cloud injects ProxyUser in configurable; it is not JSON-serializable
    # and causes TypeError when checkpoint/config is serialized (e.g. subgraph invoke).
    configurable = cfg.get("configurable")
    if isinstance(configurable, dict):
        configurable_copy = {
            k: v for k, v in configurable.items() if not _is_proxy_user(v)
        }
        if configurable_copy:
            cfg["configurable"] = configurable_copy
        else:
            cfg.pop("configurable", None)
    else:
        cfg.pop("configurable", None)

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


def build_inner_agent_config(
    config: RunnableConfig | None,
    *,
    namespace: str = "",
) -> dict[str, Any]:
    """Build a clean config for inner ``create_agent`` graphs.

    When a subgraph node (e.g. ``status.run_node``) creates a *separate*
    ``create_agent`` compiled graph and invokes it, the config from the outer
    graph must be thoroughly cleaned.  ``sanitize_nested_runtime_config`` only
    strips the checkpointer, but many other ``__pregel_*`` keys (``resuming``,
    ``send``, ``read``, ``task_id``, …) and checkpoint-context keys
    (``checkpoint_ns``, ``checkpoint_id``) leak through.  These can cause the
    inner agent's tool-loop routing to malfunction — e.g. the model returns
    ``finish_reason=tool_calls`` but the framework skips tool execution because
    the contaminated ``__pregel_resuming`` flag or stale ``checkpoint_ns``
    interferes with the inner graph's own execution.

    This helper:
    1. Sanitizes metadata (keeps only scalar values).
    2. Preserves **only** ``thread_id`` in ``configurable`` (optionally
       namespaced to avoid checkpoint collision with the outer graph).
    3. Strips *all* ``__pregel_*`` and ``checkpoint_*`` keys so the inner
       ``create_agent`` graph starts with a completely clean execution context.
    4. Preserves top-level non-configurable keys (``callbacks``, ``tags``, etc.)
       for LangSmith tracing.

    Args:
        config: The incoming ``RunnableConfig`` from the outer graph/node.
        namespace: Optional suffix appended to ``thread_id`` (e.g.
            ``"status_tool_loop"``) to create an isolated checkpoint space for
            the inner agent.
    """
    cfg = sanitize_runtime_config(config)
    cfg.pop("checkpointer", None)

    raw_configurable = (config or {}).get("configurable")
    if isinstance(raw_configurable, dict):
        thread_id = raw_configurable.get("thread_id")
    else:
        thread_id = None

    clean_configurable: dict[str, Any] = {}
    if thread_id:
        if namespace:
            clean_configurable["thread_id"] = f"{thread_id}:{namespace}"
        else:
            clean_configurable["thread_id"] = thread_id

    if clean_configurable:
        cfg["configurable"] = clean_configurable
    else:
        cfg.pop("configurable", None)

    return cfg
