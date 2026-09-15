"""#2421: a MiniApp written into the project reaches the catalog without a reload."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.api.fake_guard import RecordingFakeGuardFactory, authenticate_fake_session
from watchdog.events import DirCreatedEvent, FileClosedEvent, FileCreatedEvent, FileModifiedEvent

from scistudio.api.app import create_app
from scistudio.api.routes.workflow_watcher import WorkflowWatcher
from scistudio.engine.events import EventBus
from scistudio.panels.catalog_refresh import (
    REGISTRIES_CHANGED_EVENT_TYPE,
    PanelCatalogHandler,
    PanelCatalogRefresher,
    current_preview_service,
    is_panel_source_change,
)
from scistudio.panels.contexts import get_panel_contexts
from scistudio.panels.registry import panel_sources_fingerprint
from scistudio.previewers import build_preview_service

PAGE = "<!doctype html><html><body><div id='table'></div></body></html>"


def _write_descriptor(project: Path, panel_id: str = "table_explorer") -> Path:
    directory = project / "panels" / panel_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "panel.json").write_text(
        json.dumps(
            {
                "id": panel_id,
                "api_version": "1.0",
                "contexts": ["miniapp"],
                "types": ["DataFrame"],
                "name": "Table explorer",
                "entry": "index.html",
            }
        ),
        encoding="utf-8",
    )
    return directory


def _write_miniapp(project: Path, panel_id: str = "table_explorer") -> Path:
    directory = _write_descriptor(project, panel_id)
    (directory / "index.html").write_text(PAGE, encoding="utf-8")
    return directory


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[Any] = []
        self.arrived = threading.Event()

    async def emit(self, event: Any) -> None:
        self.events.append(event)
        self.arrived.set()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with an empty, isolated user tier."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    fake_home = tmp_path / "home"
    (fake_home / ".scistudio").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return project_dir


def _runtime(project: Path, bus: Any = None) -> Any:
    """A runtime double whose preview service is built and rebuilt for real."""
    runtime = SimpleNamespace(
        active_project=SimpleNamespace(id="p", path=str(project)),
        event_bus=bus or _RecordingBus(),
        workflow_runs={},
        data_catalog={},
        builds=0,
        _service=None,
    )

    def refresh() -> Any:
        runtime.builds += 1
        runtime._service = build_preview_service(project_dir=project, registered_types=["DataFrame"])
        return runtime._service

    runtime.refresh_preview_service = refresh
    runtime.get_preview_service = lambda: runtime._service if runtime._service is not None else refresh()
    # The project observer's file handler asks this; the double answers "first
    # party" so only the panel catalog watch speaks in these tests.
    runtime.is_recent_first_party_entity_write = lambda *args, **kwargs: True
    runtime.is_recent_workflow_first_party_write = lambda *args, **kwargs: True
    runtime.event_bus.runtime = runtime
    return runtime


def _miniapp_ids(service: Any) -> set[str]:
    return {panel_id for panel_id, panel in service.registry.panels.panels.items() if "miniapp" in panel.contexts}


# ---------------------------------------------------------------------------
# The fingerprint follows what decides the catalog, and nothing else.
# ---------------------------------------------------------------------------


def test_fingerprint_changes_for_catalog_relevant_writes(project: Path) -> None:
    empty = panel_sources_fingerprint(project)
    (project / "panels").mkdir()
    created_root = panel_sources_fingerprint(project)
    assert created_root != empty

    directory = _write_descriptor(project)
    with_descriptor = panel_sources_fingerprint(project)
    assert with_descriptor != created_root

    (directory / "index.html").write_text(PAGE, encoding="utf-8")
    with_page = panel_sources_fingerprint(project)
    assert with_page != with_descriptor, "the entry page appearing can make the directory a panel"

    (directory / "panel.json").write_text('{"id": "table_explorer", "changed": true}', encoding="utf-8")
    assert panel_sources_fingerprint(project) != with_page


def test_fingerprint_ignores_page_content_and_bytecode(project: Path) -> None:
    directory = _write_miniapp(project)
    before = panel_sources_fingerprint(project)
    (directory / "index.html").write_text(PAGE + "<!-- edited -->", encoding="utf-8")
    (directory / "__pycache__").mkdir()
    (directory / "__pycache__" / "panel.cpython-312.pyc").write_bytes(b"\0")
    (directory / ".__scistudio_write_x.tmp").write_text("partial", encoding="utf-8")
    assert panel_sources_fingerprint(project) == before


# ---------------------------------------------------------------------------
# Read side: the catalog routes answer from the directories as they are now.
# ---------------------------------------------------------------------------


def test_current_preview_service_rebuilds_only_when_panels_changed(project: Path) -> None:
    runtime = _runtime(project)
    service = current_preview_service(runtime)
    assert _miniapp_ids(service) == set()
    assert current_preview_service(runtime) is service
    builds = runtime.builds

    _write_miniapp(project)
    refreshed = current_preview_service(runtime)
    assert refreshed is not service
    assert "table_explorer" in _miniapp_ids(refreshed)
    assert runtime.builds == builds + 1
    assert current_preview_service(runtime) is refreshed


def test_runtime_without_refresh_keeps_its_service(project: Path) -> None:
    service = object()
    runtime = SimpleNamespace(active_project=None, get_preview_service=lambda: service)
    assert current_preview_service(runtime) is service


@pytest.fixture
def client(project: Path, monkeypatch: pytest.MonkeyPatch):
    runtime = _runtime(project, EventBus())
    get_panel_contexts(runtime)
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", "")
    app = create_app(guard=RecordingFakeGuardFactory())
    app.state.runtime = runtime
    test_client = TestClient(app, base_url="http://testserver")
    authenticate_fake_session(test_client)
    yield test_client
    test_client.close()


def test_a_miniapp_written_after_startup_is_listed_without_a_reload(client: TestClient, project: Path) -> None:
    assert client.get("/api/panels/miniapps").json() == {"miniapps": []}

    _write_miniapp(project)

    listed = client.get("/api/panels/miniapps").json()["miniapps"]
    assert [item["panel_id"] for item in listed] == ["table_explorer"]
    catalog = client.get("/api/panels/catalog").json()["panels"]
    assert "table_explorer" in {panel["id"] for panel in catalog}


def test_a_removed_miniapp_leaves_the_list(client: TestClient, project: Path) -> None:
    directory = _write_miniapp(project)
    assert [item["panel_id"] for item in client.get("/api/panels/miniapps").json()["miniapps"]] == ["table_explorer"]

    (directory / "index.html").unlink()
    (directory / "panel.json").unlink()
    directory.rmdir()

    assert client.get("/api/panels/miniapps").json() == {"miniapps": []}


# ---------------------------------------------------------------------------
# Push side: a burst of writes becomes one refresh and one broadcast.
# ---------------------------------------------------------------------------


def test_refresher_broadcasts_once_per_catalog_change(project: Path) -> None:
    bus = _RecordingBus()
    runtime = _runtime(project, bus)
    refresher = PanelCatalogRefresher(runtime=runtime, event_bus=bus, loop=None)

    _write_miniapp(project)
    assert refresher.flush() is True
    assert [event.event_type for event in bus.events] == [REGISTRIES_CHANGED_EVENT_TYPE]
    assert "table_explorer" in _miniapp_ids(runtime.get_preview_service())

    # Nothing changed since: no second broadcast.
    assert refresher.flush() is False
    assert len(bus.events) == 1


def test_refresher_broadcasts_even_when_a_request_already_rebuilt(project: Path) -> None:
    bus = _RecordingBus()
    runtime = _runtime(project, bus)
    refresher = PanelCatalogRefresher(runtime=runtime, event_bus=bus, loop=None)
    refresher.flush()
    bus.events.clear()

    _write_miniapp(project)
    current_preview_service(runtime)  # a GET got there first
    assert refresher.flush() is True
    assert len(bus.events) == 1


def test_refresher_debounces_a_burst_and_stop_cancels(project: Path) -> None:
    bus = _RecordingBus()
    runtime = _runtime(project, bus)
    refresher = PanelCatalogRefresher(runtime=runtime, event_bus=bus, loop=None, debounce=0.05)

    _write_descriptor(project)
    refresher.changed()
    _write_miniapp(project)
    refresher.changed()
    refresher.changed()
    assert bus.arrived.wait(timeout=5.0)
    time.sleep(0.2)
    assert len(bus.events) == 1

    refresher.stop()
    (project / "panels" / "table_explorer" / "panel.json").write_text("{}", encoding="utf-8")
    refresher.changed()
    time.sleep(0.2)
    assert len(bus.events) == 1


def test_handler_forwards_only_panel_source_changes(project: Path) -> None:
    calls: list[int] = []
    refresher = SimpleNamespace(changed=lambda: calls.append(1))
    root = (project / "panels").resolve()
    handler = PanelCatalogHandler((project / "panels",), refresher)  # type: ignore[arg-type]

    handler.on_any_event(FileClosedEvent(str(root / "a" / "panel.json")))
    handler.on_any_event(FileCreatedEvent(str(root / "a" / "__pycache__" / "panel.pyc")))
    handler.on_any_event(FileCreatedEvent(str(project.resolve() / "blocks" / "x.py")))
    assert calls == []

    handler.on_any_event(FileModifiedEvent(str(root / "a" / "panel.json")))
    handler.on_any_event(FileCreatedEvent(str(root / "a" / "index.html")))
    handler.on_any_event(DirCreatedEvent(str(root / "b")))
    assert len(calls) == 3


def test_is_panel_source_change_rules(project: Path) -> None:
    roots = ((project / "panels").resolve(),)
    root = roots[0]
    assert is_panel_source_change(roots, root, is_directory=True)
    assert is_panel_source_change(roots, root / "a" / "panel.py", is_directory=False)
    assert is_panel_source_change(roots, root / "a" / "lib" / "app.js", is_directory=False)
    assert not is_panel_source_change(roots, root / "a" / "results.parquet", is_directory=False)
    assert not is_panel_source_change(roots, root / "a" / ".__scistudio_write_1.tmp", is_directory=False)
    assert not is_panel_source_change(roots, project / "other" / "panel.json", is_directory=False)


def test_project_watcher_announces_a_new_miniapp(project: Path) -> None:
    """End to end on a real observer: write a MiniApp, get ``blocks.reloaded``."""
    bus = _RecordingBus()
    runtime = _runtime(project, bus)
    runtime.get_preview_service()
    watcher = WorkflowWatcher(event_bus=bus)  # type: ignore[arg-type]
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    try:
        watcher.start_for_project(project, loop)
        _write_miniapp(project)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if any(event.event_type == REGISTRIES_CHANGED_EVENT_TYPE for event in bus.events):
                break
            time.sleep(0.05)
    finally:
        watcher.stop()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2.0)
        loop.close()

    assert any(event.event_type == REGISTRIES_CHANGED_EVENT_TYPE for event in bus.events), bus.events
    assert "table_explorer" in _miniapp_ids(runtime.get_preview_service())
