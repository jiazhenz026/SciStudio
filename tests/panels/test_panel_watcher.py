"""T-003 (ADR-054 MiniApp FR-022): the open MiniApp's panel-directory watch.

While a ``miniapp`` context is open on a project- or user-tier MiniApp the
backend watches that MiniApp's directory and emits ``panel.files_changed`` with
its panel id, coalescing a burst of writes into one event. Only the page files
count: what ``panel.py`` writes beside itself, and anything under
``__pycache__/``, must never reload the tab that is running it.

The filter and debounce are driven with synthesised watchdog events so they are
deterministic on every platform, as the workflow watcher's tests are; one test
attaches a real observer to prove the watch is actually scheduled.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileMovedEvent

from scistudio.engine.events import EngineEvent, EventBus
from scistudio.panels.watcher import (
    DEBOUNCE_SECONDS,
    PANEL_FILES_CHANGED,
    PanelDirectoryWatcher,
    _PanelDirectoryHandler,
    counts,
    watches,
)
from scistudio.previewers.models import OwnerKind


def _bus() -> tuple[EventBus, list[EngineEvent]]:
    bus = EventBus()
    seen: list[EngineEvent] = []
    bus.subscribe(PANEL_FILES_CHANGED, seen.append)
    return bus, seen


def _watcher(tmp_path: Path, *, debounce: float = 0.05) -> tuple[PanelDirectoryWatcher, list[EngineEvent]]:
    bus, seen = _bus()
    watcher = PanelDirectoryWatcher(
        panel_id="lab.explorer", directory=tmp_path, event_bus=bus, loop=None, debounce=debounce
    )
    return watcher, seen


def _settle(seen: list[Any], *, expected: int = 1, timeout: float = 5.0) -> list[Any]:
    deadline = time.time() + timeout
    while time.time() < deadline and len(seen) < expected:
        time.sleep(0.01)
    # Give a spurious extra event time to arrive so "exactly one" means it.
    time.sleep(0.15)
    return seen


def test_the_debounce_is_five_hundred_milliseconds() -> None:
    # FR-022 pins the reload debounce; the tests below run it faster on purpose.
    assert DEBOUNCE_SECONDS == 0.5


@pytest.mark.parametrize("name", ["panel.py", "index.html", "app.js", "theme.css", "icon.svg"])
def test_page_files_count(tmp_path: Path, name: str) -> None:
    assert counts(tmp_path, tmp_path / name) is True


@pytest.mark.parametrize(
    "relative",
    [
        "__pycache__/panel.cpython-312.pyc",
        "__pycache__/cached.js",
        "output.csv",
        "notes.txt",
        "results/run.parquet",
        "panel.pyc",
    ],
)
def test_what_panel_py_writes_beside_itself_does_not_count(tmp_path: Path, relative: str) -> None:
    # FR-022: a MiniApp that writes its own output into its directory must not
    # reload the tab that is running it.
    assert counts(tmp_path, tmp_path / relative) is False


def test_a_path_outside_the_panel_directory_does_not_count(tmp_path: Path) -> None:
    assert counts(tmp_path / "panel", tmp_path / "elsewhere" / "index.html") is False


def test_only_the_project_and_user_tiers_are_watched() -> None:
    # FR-022 names the project and user tiers; a package or core MiniApp ships
    # inside an installation and nobody edits it in place.
    for owner in (OwnerKind.PROJECT, OwnerKind.USER):
        assert watches(type("P", (), {"owner_kind": owner})()) is True
    for owner in (OwnerKind.PACKAGE, OwnerKind.CORE):
        assert watches(type("P", (), {"owner_kind": owner})()) is False


def test_a_page_change_emits_panel_files_changed_with_the_panel_id(tmp_path: Path) -> None:
    watcher, seen = _watcher(tmp_path)
    handler = _PanelDirectoryHandler(tmp_path.resolve(), watcher._changed)
    handler.on_any_event(FileModifiedEvent(str(tmp_path / "index.html")))
    _settle(seen)
    assert [event.event_type for event in seen] == [PANEL_FILES_CHANGED]
    assert seen[0].data == {"panel_id": "lab.explorer"}


def test_a_burst_of_writes_emits_once(tmp_path: Path) -> None:
    watcher, seen = _watcher(tmp_path, debounce=0.3)
    handler = _PanelDirectoryHandler(tmp_path.resolve(), watcher._changed)
    for index in range(6):
        handler.on_any_event(FileModifiedEvent(str(tmp_path / f"chunk{index}.js")))
        time.sleep(0.02)
    _settle(seen, timeout=5.0)
    assert len(seen) == 1


def test_ignored_files_emit_nothing(tmp_path: Path) -> None:
    watcher, seen = _watcher(tmp_path)
    handler = _PanelDirectoryHandler(tmp_path.resolve(), watcher._changed)
    handler.on_any_event(FileCreatedEvent(str(tmp_path / "__pycache__" / "panel.cpython-312.pyc")))
    handler.on_any_event(FileModifiedEvent(str(tmp_path / "scratch.npy")))
    time.sleep(0.3)
    assert seen == []


def test_a_rename_into_the_page_counts(tmp_path: Path) -> None:
    watcher, seen = _watcher(tmp_path)
    handler = _PanelDirectoryHandler(tmp_path.resolve(), watcher._changed)
    # Editors write atomically: a temp file renamed onto index.html arrives as a
    # move whose destination is the page file.
    handler.on_any_event(FileMovedEvent(str(tmp_path / ".tmp123"), str(tmp_path / "index.html")))
    _settle(seen)
    assert len(seen) == 1


def test_stop_drops_a_change_that_had_not_been_announced(tmp_path: Path) -> None:
    watcher, seen = _watcher(tmp_path, debounce=0.5)
    handler = _PanelDirectoryHandler(tmp_path.resolve(), watcher._changed)
    handler.on_any_event(FileModifiedEvent(str(tmp_path / "index.html")))
    watcher.stop()
    time.sleep(0.8)
    assert seen == []


@pytest.mark.serial
def test_a_started_watch_observes_the_directory(tmp_path: Path) -> None:
    # The observer runs on its own thread; this is the one test that proves the
    # watch is really scheduled rather than only that the filter is right.
    panel_dir = tmp_path / "lab.explorer"
    panel_dir.mkdir()
    (panel_dir / "index.html").write_text("<p>one</p>", encoding="utf-8")
    watcher, seen = _watcher(panel_dir, debounce=0.1)
    assert watcher.start() is True
    try:
        (panel_dir / "index.html").write_text("<p>two</p>", encoding="utf-8")
        _settle(seen, timeout=20.0)
        assert [event.data for event in seen][:1] == [{"panel_id": "lab.explorer"}]
    finally:
        watcher.stop()


def test_a_missing_directory_is_not_watched(tmp_path: Path) -> None:
    watcher, _seen = _watcher(tmp_path / "gone")
    assert watcher.start() is False
    watcher.stop()


def test_the_event_reaches_a_running_loop_from_the_watch_thread(tmp_path: Path) -> None:
    # The host subscribes on the API event loop; the watchdog thread hands the
    # event to that loop rather than emitting on its own.
    bus, seen = _bus()

    async def drive() -> None:
        loop = asyncio.get_running_loop()
        watcher = PanelDirectoryWatcher(
            panel_id="lab.explorer", directory=tmp_path, event_bus=bus, loop=loop, debounce=0.05
        )
        handler = _PanelDirectoryHandler(tmp_path.resolve(), watcher._changed)
        await asyncio.to_thread(handler.on_any_event, FileModifiedEvent(str(tmp_path / "panel.py")))
        for _ in range(200):
            if seen:
                return
            await asyncio.sleep(0.02)

    asyncio.run(drive())
    assert [event.data for event in seen] == [{"panel_id": "lab.explorer"}]
