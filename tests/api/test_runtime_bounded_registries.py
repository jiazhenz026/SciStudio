"""#1551 / DSN-12: per-session registries must be LRU-bounded.

``ApiRuntime.data_catalog`` and ``ApiRuntime.workflow_runs`` previously grew
unboundedly for the lifetime of the process. They are now backed by
``_BoundedRegistry`` with LRU eviction. ``workflow_runs`` additionally pins
still-live runs so eviction never orphans an in-flight asyncio task.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from scistudio.api.runtime import _BoundedRegistry, _run_is_evictable


def test_bounded_registry_evicts_oldest_first() -> None:
    reg: _BoundedRegistry[str, int] = _BoundedRegistry(max_entries=3)
    for i in range(3):
        reg[f"k{i}"] = i
    assert len(reg) == 3

    reg["k3"] = 3  # over cap -> evict oldest (k0)
    assert "k0" not in reg
    assert set(reg.keys()) == {"k1", "k2", "k3"}
    assert len(reg) == 3


def test_bounded_registry_write_refreshes_recency() -> None:
    reg: _BoundedRegistry[str, int] = _BoundedRegistry(max_entries=3)
    for i in range(3):
        reg[f"k{i}"] = i
    # Re-write k0 so it is no longer the LRU entry (write refreshes recency).
    reg["k0"] = 99
    reg["k3"] = 3  # evicts the now-oldest (k1), not k0.
    assert "k0" in reg
    assert reg["k0"] == 99
    assert "k1" not in reg


def test_bounded_registry_read_does_not_reorder() -> None:
    """Reads must NOT reorder — a values()/items() loop must not mutate the
    dict mid-iteration (the lifespan shutdown iterates while cancelling)."""
    reg: _BoundedRegistry[str, int] = _BoundedRegistry(max_entries=10)
    for i in range(5):
        reg[f"k{i}"] = i
    # Reading every value then inserting must not have changed order, and
    # iterating values() while the dict is read is safe.
    assert list(reg.values()) == [0, 1, 2, 3, 4]
    _ = reg["k0"]
    assert list(reg.keys()) == ["k0", "k1", "k2", "k3", "k4"]


def test_bounded_registry_is_a_dict_subclass() -> None:
    """#1551: must subclass dict so ``isinstance(x, dict)`` consumers
    (api/ws.py, MCP tools, api/app.py) keep working unchanged."""
    reg: _BoundedRegistry[str, int] = _BoundedRegistry(max_entries=2)
    assert isinstance(reg, dict)


def test_bounded_registry_overwrite_does_not_grow() -> None:
    reg: _BoundedRegistry[str, int] = _BoundedRegistry(max_entries=2)
    reg["a"] = 1
    reg["a"] = 2
    reg["b"] = 3
    assert len(reg) == 2
    assert reg["a"] == 2


def test_bounded_registry_rejects_nonpositive_cap() -> None:
    with pytest.raises(ValueError):
        _BoundedRegistry(max_entries=0)


# ---------------------------------------------------------------------------
# workflow_runs live-run pinning
# ---------------------------------------------------------------------------


@dataclass
class _FakeTask:
    _done: bool

    def done(self) -> bool:
        return self._done


@dataclass
class _FakeRun:
    task: Any


def _run(done: bool) -> _FakeRun:
    return _FakeRun(task=_FakeTask(_done=done))


def test_run_is_evictable_predicate() -> None:
    assert _run_is_evictable("w", _run(done=True)) is True
    assert _run_is_evictable("w", _run(done=False)) is False


def test_workflow_runs_eviction_skips_live_runs() -> None:
    reg: _BoundedRegistry[str, Any] = _BoundedRegistry(max_entries=2, evictable=_run_is_evictable)
    # Two live runs fill the cap; neither may be evicted.
    reg["live0"] = _run(done=False)
    reg["live1"] = _run(done=False)
    # A third live run cannot evict the live ones -> overflow retained.
    reg["live2"] = _run(done=False)
    assert set(reg.keys()) == {"live0", "live1", "live2"}

    # A finished run is added; the oldest *finished* entry is the only
    # eviction candidate. With all live + one finished, adding another
    # finished run evicts the finished one, never a live one.
    reg2: _BoundedRegistry[str, Any] = _BoundedRegistry(max_entries=2, evictable=_run_is_evictable)
    reg2["live"] = _run(done=False)
    reg2["finished0"] = _run(done=True)
    reg2["finished1"] = _run(done=True)  # over cap -> evict finished0 (oldest evictable)
    assert "finished0" not in reg2
    assert "live" in reg2
    assert "finished1" in reg2


def test_real_runtime_uses_bounded_registries() -> None:
    """An ApiRuntime instance wires both registries as bounded maps."""
    from scistudio.api.runtime import ApiRuntime

    runtime = ApiRuntime()
    assert isinstance(runtime.data_catalog, _BoundedRegistry)
    assert isinstance(runtime.workflow_runs, _BoundedRegistry)


def test_project_reset_preserves_bounding() -> None:
    """#1551: ``data_catalog = {}`` / ``workflow_runs = {}`` resets (issued by
    the project-lifecycle code on open/switch) must keep the LRU bound, not
    revert to an unbounded plain dict."""
    from scistudio.api.runtime import ApiRuntime

    runtime = ApiRuntime()
    # Simulate the _projects reset on project open/switch.
    runtime.data_catalog = {}
    runtime.workflow_runs = {}
    assert isinstance(runtime.data_catalog, _BoundedRegistry)
    assert isinstance(runtime.workflow_runs, _BoundedRegistry)
    # The cap survives the reset.
    assert runtime.data_catalog._max == runtime_default_catalog_cap()  # type: ignore[attr-defined]


def runtime_default_catalog_cap() -> int:
    from scistudio.api.runtime import _DATA_CATALOG_MAX

    return _DATA_CATALOG_MAX


def test_env_int_override_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cap env-override helper parses positive ints and rejects bad input.

    Tested via ``_env_int`` directly (no ``importlib.reload``) to avoid
    replacing the module-level ``_BoundedRegistry`` class object, which would
    break ``isinstance`` for runtimes other tests already built.
    """
    from scistudio.api.runtime import _env_int

    monkeypatch.setenv("SCISTUDIO_X", "5")
    assert _env_int("SCISTUDIO_X", 99) == 5
    monkeypatch.setenv("SCISTUDIO_X", "not-an-int")
    assert _env_int("SCISTUDIO_X", 99) == 99
    monkeypatch.setenv("SCISTUDIO_X", "0")
    assert _env_int("SCISTUDIO_X", 99) == 99
    monkeypatch.delenv("SCISTUDIO_X", raising=False)
    assert _env_int("SCISTUDIO_X", 99) == 99


def test_run_event_loop_marker() -> None:
    """Sanity: a real asyncio task reports done() after completion."""

    async def _main() -> bool:
        task = asyncio.create_task(asyncio.sleep(0))
        await task
        return _run_is_evictable("w", _FakeRun(task=task))

    assert asyncio.run(_main()) is True
