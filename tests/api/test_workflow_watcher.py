"""Unit tests for :mod:`scieasy.api.routes.workflow_watcher` (ADR-034 Phase 2).

The watcher's contract surface is small:

* Recognise ``.yaml``/``.yml`` events under the project's ``workflows/``
  directory and broadcast ``workflow.changed`` payloads with the right
  ``kind`` (modified / created / deleted / moved).
* Filter out other file types.
* Suppress events whose ``(normalised_path, mtime, size)`` matches a
  recent canvas-originated write registered via ``mark_self_write``.
* Debounce rapid bursts of events per path at 200 ms.

These tests instantiate the watcher directly and synthesise watchdog
events so they exercise the handler logic deterministically without
relying on the filesystem-event timing of the host OS (which is flaky
on Windows under CI).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from scieasy.api.routes import workflow_watcher as watcher_module
from scieasy.api.routes.workflow_watcher import (
    _DEBOUNCE_SECONDS,
    WorkflowWatcher,
    _WorkflowFileHandler,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handler(project_dir: Path) -> tuple[_WorkflowFileHandler, list[dict[str, Any]]]:
    """Return ``(handler, captured)`` where ``captured`` accumulates payloads.

    Loop is ``None`` so the handler dispatches synchronously — easier to
    assert against in unit tests.
    """
    captured: list[dict[str, Any]] = []

    def broadcast(payload: dict[str, Any]) -> None:
        captured.append(payload)

    handler = _WorkflowFileHandler(project_dir=project_dir, broadcast=broadcast, loop=None)
    return handler, captured


def _write_yaml(path: Path, body: str = "id: w\nnodes: []\nedges: []\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Modified-event happy path
# ---------------------------------------------------------------------------


def test_modified_yaml_emits_event(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    workflows = project / "workflows"
    workflows.mkdir(parents=True)
    yaml_path = workflows / "demo.yaml"
    _write_yaml(yaml_path)

    handler, captured = _make_handler(project)
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))

    assert len(captured) == 1
    payload = captured[0]
    assert payload["type"] == "workflow.changed"
    assert payload["kind"] == "modified"
    assert payload["workflow_id"] == "demo"
    # Path is project-relative with forward slashes regardless of host OS.
    assert payload["path"] == "workflows/demo.yaml"


# ---------------------------------------------------------------------------
# Self-write suppression
# ---------------------------------------------------------------------------


def test_self_write_suppressed(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    yaml_path = project / "workflows" / "demo.yaml"
    _write_yaml(yaml_path)

    handler, captured = _make_handler(project)
    handler.mark_self_write(yaml_path)
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))

    assert captured == []


def test_self_write_does_not_suppress_subsequent_change(tmp_path: Path) -> None:
    """Once the file changes again after a self-write, we must emit."""
    project = tmp_path / "proj"
    yaml_path = project / "workflows" / "demo.yaml"
    _write_yaml(yaml_path)

    handler, captured = _make_handler(project)
    handler.mark_self_write(yaml_path)
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))
    assert captured == []

    # Mutate the file — mtime + size change so the self-write tuple no
    # longer matches.
    time.sleep(_DEBOUNCE_SECONDS + 0.05)
    _write_yaml(yaml_path, body="id: w\nnodes: []\nedges: []\n# extra line\n")
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))
    assert len(captured) == 1
    assert captured[0]["kind"] == "modified"


# ---------------------------------------------------------------------------
# Debounce
# ---------------------------------------------------------------------------


def test_debounce_coalesces_rapid_modifies(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    yaml_path = project / "workflows" / "demo.yaml"
    _write_yaml(yaml_path)

    handler, captured = _make_handler(project)
    for _ in range(5):
        handler.on_any_event(FileModifiedEvent(str(yaml_path)))

    # Five rapid events within the 200 ms window collapse to one.
    assert len(captured) == 1


def test_debounce_admits_event_after_window_elapses(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    yaml_path = project / "workflows" / "demo.yaml"
    _write_yaml(yaml_path)

    handler, captured = _make_handler(project)
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))
    time.sleep(_DEBOUNCE_SECONDS + 0.05)
    handler.on_any_event(FileModifiedEvent(str(yaml_path)))

    assert len(captured) == 2


# ---------------------------------------------------------------------------
# Non-YAML filter
# ---------------------------------------------------------------------------


def test_non_yaml_files_ignored(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    workflows = project / "workflows"
    workflows.mkdir(parents=True)
    txt = workflows / "notes.txt"
    txt.write_text("hi", encoding="utf-8")

    handler, captured = _make_handler(project)
    handler.on_any_event(FileModifiedEvent(str(txt)))

    assert captured == []


def test_directory_events_ignored(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    workflows = project / "workflows"
    workflows.mkdir(parents=True)

    handler, captured = _make_handler(project)
    event = FileModifiedEvent(str(workflows))
    # watchdog's FileModifiedEvent stores is_directory as an instance attr;
    # set it manually so we exercise the directory-event filter branch.
    event.is_directory = True
    handler.on_any_event(event)

    assert captured == []


# ---------------------------------------------------------------------------
# Created / deleted / moved
# ---------------------------------------------------------------------------


def test_created_yaml_emits_event(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    yaml_path = project / "workflows" / "new.yaml"
    _write_yaml(yaml_path)

    handler, captured = _make_handler(project)
    handler.on_any_event(FileCreatedEvent(str(yaml_path)))

    assert len(captured) == 1
    assert captured[0]["kind"] == "created"
    assert captured[0]["workflow_id"] == "new"


def test_deleted_yaml_emits_event(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    # The file does not need to still exist on disk — we synthesise the
    # delete event for a virtual path.
    yaml_path = project / "workflows" / "gone.yaml"

    handler, captured = _make_handler(project)
    handler.on_any_event(FileDeletedEvent(str(yaml_path)))

    assert len(captured) == 1
    assert captured[0]["kind"] == "deleted"
    assert captured[0]["workflow_id"] == "gone"


def test_moved_yaml_emits_event(tmp_path: Path) -> None:
    """A FileMovedEvent should surface as ``created`` keyed on the destination.

    Rationale: atomic writes on Windows + POSIX both materialise as
    ``tmp.XYZ -> rename -> final.yaml``, so watchdog reports a
    ``FileMovedEvent`` whose ``src_path`` is the tmp file (not yaml) and
    ``dest_path`` is the final yaml. The canvas cares about "a workflow
    YAML appeared at this path", so we promote moves into the watched
    tree to ``created`` keyed on ``dest_path``.
    """
    project = tmp_path / "proj"
    src = project / "workflows" / "old.tmp.123"
    dst = project / "workflows" / "new.yaml"

    handler, captured = _make_handler(project)
    handler.on_any_event(FileMovedEvent(str(src), str(dst)))

    assert len(captured) == 1
    assert captured[0]["kind"] == "created"
    assert captured[0]["workflow_id"] == "new"  # keyed on the destination side


# ---------------------------------------------------------------------------
# WorkflowWatcher lifecycle
# ---------------------------------------------------------------------------


def test_watcher_emits_on_real_filesystem_write(tmp_path: Path) -> None:
    """Smoke test the full path: start observer + write a YAML + wait for event.

    Uses a real :class:`watchdog.observers.Observer` so this also covers the
    Windows/macOS/Linux native backend wiring. Skipped if the event does
    not arrive within a generous timeout (some CI runners have very slow
    inotify / FSEvents).
    """
    project = tmp_path / "proj"
    (project / "workflows").mkdir(parents=True)

    captured: list[dict[str, Any]] = []
    event = threading.Event()

    class _StubBus:
        async def emit(self, engine_event: Any) -> None:
            captured.append(
                {
                    "type": engine_event.event_type,
                    "data": engine_event.data,
                }
            )
            event.set()

    watcher = WorkflowWatcher(event_bus=_StubBus())  # type: ignore[arg-type]
    # Use a fake "loop" via asyncio.new_event_loop so the threadsafe
    # dispatcher has somewhere to run the coroutine.
    import asyncio

    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    try:
        watcher.start_for_project(project, loop)
        yaml_path = project / "workflows" / "live.yaml"
        yaml_path.write_text("id: w\nnodes: []\nedges: []\n", encoding="utf-8")
        # Wait up to 5 s — generous because watchdog inotify / FSEvents
        # delivery latency is implementation-defined.
        event.wait(timeout=5.0)
    finally:
        watcher.stop()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2.0)
        loop.close()

    assert any(c["type"] == "workflow.changed" for c in captured), captured


def test_watcher_start_is_idempotent_for_same_project(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / "workflows").mkdir(parents=True)

    import asyncio

    loop = asyncio.new_event_loop()
    watcher = WorkflowWatcher(event_bus=MagicMock())
    try:
        watcher.start_for_project(project, loop)
        first_obs = watcher._observer  # type: ignore[attr-defined]
        watcher.start_for_project(project, loop)
        # Same project => same observer instance is kept.
        assert watcher._observer is first_obs  # type: ignore[attr-defined]
    finally:
        watcher.stop()
        loop.close()


def test_watcher_stop_clears_state(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / "workflows").mkdir(parents=True)

    import asyncio

    loop = asyncio.new_event_loop()
    watcher = WorkflowWatcher(event_bus=MagicMock())
    try:
        watcher.start_for_project(project, loop)
        assert watcher.watched_dir is not None
        watcher.stop()
        assert watcher.watched_dir is None
        assert watcher.handler is None
    finally:
        loop.close()


def test_mark_self_write_module_helper_is_no_op_without_watcher() -> None:
    """``mark_self_write`` must not raise when no watcher is installed."""
    # Ensure the singleton is unset.
    watcher_module.set_active_watcher(None)
    # Should not raise even for a non-existent path.
    watcher_module.mark_self_write(Path("/does/not/exist.yaml"))


@pytest.fixture(autouse=True)
def _isolate_module_singleton() -> Any:
    """Reset the module-level active watcher between tests."""
    watcher_module.set_active_watcher(None)
    yield
    watcher_module.set_active_watcher(None)
