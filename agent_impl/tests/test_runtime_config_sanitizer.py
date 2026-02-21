from __future__ import annotations

from graph.runtime_config import (
    resolve_runtime_checkpointer,
    sanitize_nested_runtime_config,
    sanitize_runtime_config,
)


class _Obj:
    pass


class ProxyUser:
    """Simulates LangChain Cloud-injected user; not JSON-serializable."""

    pass


def test_sanitize_runtime_config_removes_proxy_user():
    """ProxyUser in configurable is dropped to avoid JSON serialization errors in LangChain Cloud."""
    cfg = {"configurable": {"thread_id": "t1", "user": ProxyUser(), "foo": "bar"}}
    out = sanitize_runtime_config(cfg)
    assert out.get("configurable") == {"thread_id": "t1", "foo": "bar"}


def test_sanitize_runtime_config_removes_non_scalar_metadata_values():
    cfg = {
        "configurable": {"thread_id": "t1", "__pregel_checkpointer": object()},
        "metadata": {
            "ok_str": "v",
            "ok_int": 1,
            "ok_bool": True,
            "drop_obj": _Obj(),
            "drop_lambda": lambda: 1,
        },
    }

    out = sanitize_runtime_config(cfg)
    assert out.get("configurable") == cfg["configurable"]
    assert out.get("metadata") == {"ok_str": "v", "ok_int": 1, "ok_bool": True}


def test_sanitize_runtime_config_drops_non_dict_metadata():
    cfg = {"configurable": {"thread_id": "t1"}, "metadata": _Obj()}
    out = sanitize_runtime_config(cfg)
    assert "metadata" not in out


def test_sanitize_nested_runtime_config_strips_checkpointer_keys():
    cp = object()
    cfg = {
        "checkpointer": cp,
        "configurable": {"thread_id": "t1", "__pregel_checkpointer": cp, "foo": "bar"},
        "metadata": {"m": "ok"},
    }

    out = sanitize_nested_runtime_config(cfg)
    assert "checkpointer" not in out
    assert out.get("configurable") == {"thread_id": "t1", "foo": "bar"}
    assert out.get("metadata") == {"m": "ok"}


def test_resolve_runtime_checkpointer_supports_nested_configurable():
    cp = object()
    cfg = {"configurable": {"thread_id": "t1", "__pregel_checkpointer": cp}}
    assert resolve_runtime_checkpointer(cfg) is cp
