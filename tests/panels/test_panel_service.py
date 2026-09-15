"""#2465: the runtime panel service applies catalog changes incrementally.

The panel service is built once per runtime and never rebuilt. A change to the
panel folders is rediscovered and diffed by descriptor fingerprint: only the
contexts on a panel that was removed, changed or shadowed are revoked, open
previews re-route only when their type's candidates changed, and a MiniApp
written next to open ones leaves them running (#2455). The catalog also follows
the folders on the read side (#2421).
"""

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
from scistudio.api.runtime.models import DataRecord
from scistudio.core.storage.ref import StorageReference
from scistudio.engine.events import EventBus
from scistudio.panels.registry import panel_sources_fingerprint
from scistudio.panels.service import PanelService
from scistudio.panels.watcher import PanelSourceWatcher, _SourceHandler, is_panel_source_change
from scistudio.previewers import PreviewService
from scistudio.previewers.models import PreviewTarget, TargetKind
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.session import PreviewSessionManager

PAGE = "<!doctype html><html><body><div id='app'></div></body></html>"
TYPES = ("DataFrame", "Text")


def _write_panel(project: Path, panel_id: str, *, page: bool = True, **fields: Any) -> Path:
    directory = project / "panels" / panel_id
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = {"id": panel_id, "api_version": "1.0", "contexts": ["miniapp"], "types": ["DataFrame"]} | fields
    (directory / "panel.json").write_text(json.dumps(descriptor), encoding="utf-8")
    if page:
        (directory / "index.html").write_text(PAGE, encoding="utf-8")
    return directory


class _RecordingBus(EventBus):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []
        self.arrived = threading.Event()

    async def emit(self, event: Any) -> None:
        self.events.append(event)
        self.arrived.set()
        await super().emit(event)

    def of(self, event_type: str) -> list[dict[str, Any]]:
        return [dict(event.data) for event in self.events if event.event_type == event_type]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with an empty, isolated user tier."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    fake_home = tmp_path / "home"
    (fake_home / ".scistudio").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return project_dir


def _core_legacy(_project: Any, _resolver: Any) -> PreviewService:
    registry = PreviewerRegistry()
    registry.load_core()
    return PreviewService(registry=registry, sessions=PreviewSessionManager(registry))


def _runtime(project: Path, bus: EventBus | None = None, **extra: Any) -> Any:
    runtime = SimpleNamespace(
        active_project=SimpleNamespace(id="p", path=str(project)),
        event_bus=bus or _RecordingBus(),
        workflow_runs={},
        data_catalog={},
        type_registry=SimpleNamespace(
            all_types=lambda: dict.fromkeys(TYPES),
            resolve=lambda name: SimpleNamespace(base_type="DataObject" if name != "DataObject" else ""),
        ),
        **extra,
    )
    runtime.event_bus.runtime = runtime
    runtime.get_data_record = lambda ref: runtime.data_catalog[ref]
    runtime.resolve_session_target = lambda target: PreviewTarget(
        kind=target.kind,
        ref=target.ref,
        recorded_type=runtime.data_catalog[target.ref].type_name,
        type_chain=tuple(runtime.data_catalog[target.ref].type_chain),
    )
    runtime.is_recent_first_party_entity_write = lambda *args, **kwargs: True
    runtime.is_recent_workflow_first_party_write = lambda *args, **kwargs: True
    service = PanelService(runtime, legacy_factory=_core_legacy, choices_loader=lambda _project: {})
    runtime._panel_service = service
    runtime.get_panel_service = lambda: service
    runtime.get_preview_service = service.legacy_service
    return runtime


def _text_record(runtime: Any, tmp_path: Path, ref: str = "data-text") -> None:
    data = tmp_path / f"{ref}.txt"
    data.write_text("hello", encoding="utf-8")
    runtime.data_catalog[ref] = DataRecord(
        ref, StorageReference(backend="filesystem", path=str(data)), "Text", {}, ["DataObject", "Text"]
    )


# ---------------------------------------------------------------------------
# The sources fingerprint follows what decides the catalog, and nothing else.
# ---------------------------------------------------------------------------


def test_fingerprint_changes_for_catalog_relevant_writes(project: Path) -> None:
    empty = panel_sources_fingerprint(project)
    (project / "panels").mkdir()
    created_root = panel_sources_fingerprint(project)
    assert created_root != empty
    directory = _write_panel(project, "table_explorer", page=False)
    with_descriptor = panel_sources_fingerprint(project)
    assert with_descriptor != created_root
    (directory / "index.html").write_text(PAGE, encoding="utf-8")
    with_page = panel_sources_fingerprint(project)
    assert with_page != with_descriptor, "the entry page appearing can make the directory a panel"
    (directory / "panel.json").write_text('{"id": "table_explorer", "changed": true}', encoding="utf-8")
    assert panel_sources_fingerprint(project) != with_page


def test_fingerprint_ignores_page_content_bytecode_and_answers(project: Path) -> None:
    directory = _write_panel(project, "table_explorer")
    before = panel_sources_fingerprint(project)
    (directory / "index.html").write_text(PAGE + "<!-- edited -->", encoding="utf-8")
    (directory / "__pycache__").mkdir()
    (directory / "__pycache__" / "panel.cpython-312.pyc").write_bytes(b"\0")
    (directory / ".__scistudio_write_x.tmp").write_text("partial", encoding="utf-8")
    (directory / "answers.json").write_text("{}", encoding="utf-8")
    (directory / ".answers-1.tmp").write_text("{}", encoding="utf-8")
    assert panel_sources_fingerprint(project) == before


# ---------------------------------------------------------------------------
# Incremental diffs.
# ---------------------------------------------------------------------------


def test_rescan_reports_added_changed_removed_and_skips_unchanged_folders(project: Path) -> None:
    runtime = _runtime(project)
    service = runtime.get_panel_service()
    service.ensure_loaded()
    generation = service.generation
    assert service.rescan().empty and service.generation == generation

    directory = _write_panel(project, "table_explorer")
    diff = service.rescan()
    assert diff.added == {"table_explorer"} and diff.miniapps_changed and not diff.preview_types
    assert service.panel("table_explorer") is not None
    assert runtime.event_bus.of("blocks.reloaded")[-1]["panels"] == {
        "added": ["table_explorer"],
        "removed": [],
        "changed": [],
    }

    (directory / "app.js").write_text("export {}", encoding="utf-8")
    assert service.rescan().empty, "a new page file changes no descriptor"

    _write_panel(project, "table_explorer", name="Renamed")
    assert service.rescan().changed == {"table_explorer"}

    for child in directory.iterdir():
        child.unlink()
    directory.rmdir()
    assert service.rescan().removed == {"table_explorer"}


def test_a_new_preview_panel_names_the_types_to_reroute(project: Path, tmp_path: Path) -> None:
    runtime = _runtime(project)
    service = runtime.get_panel_service()
    _text_record(runtime, tmp_path)
    target = runtime.resolve_session_target(PreviewTarget(kind=TargetKind.DATA_REF, ref="data-text"))
    assert service.route(target).previewer_id == "core.text.basic"

    _write_panel(project, "lab.text", contexts=["preview"], types=["Text", "Collection[Text]"], priority=5)
    diff = service.rescan()
    assert diff.preview_types == {"Text", "Collection[Text]"}
    assert runtime.event_bus.of("blocks.reloaded")[-1]["preview_candidates_changed"] is True
    # The next opened preview is routed to the new panel.
    envelope = service.create_preview_session(target, fresh=True)
    assert envelope.kind.value == "panel" and envelope.previewer_id == "lab.text"


def test_changing_one_preview_panel_revokes_only_its_contexts(project: Path, tmp_path: Path) -> None:
    runtime = _runtime(project)
    service = runtime.get_panel_service()
    _text_record(runtime, tmp_path)
    _text_record(runtime, tmp_path, "data-other")
    _write_panel(project, "lab.text", contexts=["preview"], types=["Text"])
    _write_panel(project, "lab.miniapp", contexts=["miniapp"], types=["Text"])
    service.rescan()
    store = service.contexts
    changed = store.create({"kind": "preview", "target": {"ref": "data-text"}})
    other = store.create({"kind": "preview", "target": {"ref": "data-other"}})
    assert changed.panel.id == other.panel.id == "lab.text"
    runtime.event_bus.events.clear()

    _write_panel(project, "lab.miniapp", contexts=["miniapp"], types=["Text"], name="Unrelated edit")
    diff = service.rescan()
    assert diff.changed == {"lab.miniapp"} and not diff.preview_types
    assert store.get(changed.context_id) is changed and store.get(other.context_id) is other

    _write_panel(project, "lab.text", contexts=["preview"], types=["Text"], priority=3)
    diff = service.rescan()
    assert diff.changed == {"lab.text"} and diff.preview_types == {"Text"}
    assert set(store.contexts) == set()
    revoked = [
        data | {"context_ids": sorted(data["context_ids"])} for data in runtime.event_bus.of("panel.contexts_revoked")
    ]
    assert revoked == [
        {
            "context_ids": sorted([changed.context_id, other.context_id]),
            "panel_ids": ["lab.text"],
            "reason": "panel_changed",
        }
    ]


def test_choices_change_rebuilds_nothing_and_announces_the_type(project: Path, tmp_path: Path) -> None:
    runtime = _runtime(project)
    service = runtime.get_panel_service()
    service._choices_loader = lambda _project: json.loads((tmp_path / "choices.json").read_text())
    (tmp_path / "choices.json").write_text("{}", encoding="utf-8")
    _text_record(runtime, tmp_path)
    _write_panel(project, "lab.text", contexts=["preview"], types=["Text"], priority=5)
    service.rescan()
    context = service.contexts.create({"kind": "preview", "target": {"ref": "data-text"}})
    legacy = service.legacy_service()
    target = runtime.resolve_session_target(PreviewTarget(kind=TargetKind.DATA_REF, ref="data-text"))
    assert service.route(target).previewer_id == "lab.text"

    from scistudio.previewers import choices as choices_module

    original = choices_module.write_choice
    choices_module.write_choice = lambda path, type_name, previewer_id: path.write_text(
        json.dumps({type_name: previewer_id}), encoding="utf-8"
    )
    try:
        service.set_choice(tmp_path / "choices.json", "Text", "core.text.basic")
    finally:
        choices_module.write_choice = original
    assert service.route(target).previewer_id == "core.text.basic"
    assert service.legacy_service() is legacy
    assert service.contexts.get(context.context_id) is context
    assert runtime.event_bus.of("panel.choices_changed") == [{"type": "Text"}]


def test_a_legacy_reload_ends_only_legacy_sessions(project: Path, tmp_path: Path) -> None:
    from scistudio.previewers.fallbacks import text_previewer
    from scistudio.previewers.models import OwnerKind, PreviewerSpec

    runtime = _runtime(project)
    service = runtime.get_panel_service()

    def legacy_with_a_package_text_viewer(_project: Any, _resolver: Any) -> PreviewService:
        built = _core_legacy(_project, _resolver)
        built.registry.register(
            PreviewerSpec("pkg.text", OwnerKind.PACKAGE, "pkg", "Text", backend_provider=text_previewer)
        )
        return built

    service.legacy._factory = legacy_with_a_package_text_viewer
    _text_record(runtime, tmp_path)
    _write_panel(project, "lab.table", contexts=["preview"], types=["DataFrame"])
    service.rescan()
    text = runtime.resolve_session_target(PreviewTarget(kind=TargetKind.DATA_REF, ref="data-text"))
    legacy_session = service.create_preview_session(text)
    assert service.legacy.owns(legacy_session.session_id)
    table = PreviewTarget(kind=TargetKind.DATA_REF, ref="t", recorded_type="DataFrame", type_chain=("DataFrame",))
    panel_session = service.create_preview_session(table)
    assert panel_session.kind.value == "panel"
    runtime.event_bus.events.clear()

    diff = service.refresh()
    assert diff.legacy_reloaded and not diff.invalidated
    assert runtime.event_bus.of("blocks.reloaded")[-1]["legacy_reloaded"] is True
    assert service.read_session(panel_session.session_id).session_id == panel_session.session_id
    from scistudio.previewers.models import UnknownPreviewerError

    with pytest.raises(UnknownPreviewerError):
        service.read_session(legacy_session.session_id)


def test_a_project_switch_closes_every_context_and_rearms(project: Path, tmp_path: Path) -> None:
    runtime = _runtime(project)
    service = runtime.get_panel_service()
    _text_record(runtime, tmp_path)
    _write_panel(project, "lab.text", contexts=["preview"], types=["Text"])
    service.rescan()
    context = service.contexts.create({"kind": "preview", "target": {"ref": "data-text"}})
    other = tmp_path / "other"
    other.mkdir()
    runtime.active_project = SimpleNamespace(id="q", path=str(other))
    service.refresh()
    assert context.context_id not in service.contexts.contexts
    assert service.panel("lab.text") is None
    assert runtime.event_bus.of("panel.contexts_revoked")[0]["reason"] == "project_switch"


def test_page_watches_are_shared_by_every_context_kind(project: Path, tmp_path: Path) -> None:
    runtime = _runtime(project)
    service = runtime.get_panel_service()
    _text_record(runtime, tmp_path)
    _write_panel(project, "lab.text", contexts=["preview"], types=["Text"])
    service.rescan()
    first = service.contexts.create({"kind": "preview", "target": {"ref": "data-text"}})
    second = service.contexts.create({"kind": "preview", "target": {"ref": "data-text"}})
    assert first.watched and second.watched
    assert service.file_watches.watched() == {"lab.text": 2}
    service.contexts.close(first.context_id)
    assert service.file_watches.watched() == {"lab.text": 1}
    service.contexts.close(second.context_id)
    assert service.file_watches.watched() == {}


# ---------------------------------------------------------------------------
# Read side: the catalog routes answer from the folders as they are now.
# ---------------------------------------------------------------------------


@pytest.fixture
def client(project: Path, monkeypatch: pytest.MonkeyPatch):
    runtime = _runtime(project, EventBus())
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", "")
    app = create_app(guard=RecordingFakeGuardFactory())
    app.state.runtime = runtime
    test_client = TestClient(app, base_url="http://testserver")
    authenticate_fake_session(test_client)
    yield test_client
    test_client.close()


def test_a_miniapp_written_after_startup_is_listed_without_a_reload(client: TestClient, project: Path) -> None:
    assert client.get("/api/panels/miniapps").json() == {"miniapps": []}
    _write_panel(project, "table_explorer", name="Table explorer")
    listed = client.get("/api/panels/miniapps").json()["miniapps"]
    assert [item["panel_id"] for item in listed] == ["table_explorer"]
    catalog = client.get("/api/panels/catalog").json()["panels"]
    assert "table_explorer" in {panel["id"] for panel in catalog}


def test_a_removed_miniapp_leaves_the_list(client: TestClient, project: Path) -> None:
    directory = _write_panel(project, "table_explorer")
    assert [item["panel_id"] for item in client.get("/api/panels/miniapps").json()["miniapps"]] == ["table_explorer"]
    (directory / "index.html").unlink()
    (directory / "panel.json").unlink()
    directory.rmdir()
    assert client.get("/api/panels/miniapps").json() == {"miniapps": []}


# ---------------------------------------------------------------------------
# Push side: the tier watch debounces a burst into one rescan.
# ---------------------------------------------------------------------------


def test_source_watcher_debounces_a_burst_and_stop_cancels(project: Path) -> None:
    calls: list[int] = []
    arrived = threading.Event()

    def on_change() -> None:
        calls.append(1)
        arrived.set()

    (project / "panels").mkdir()
    watcher = PanelSourceWatcher(on_change, debounce=0.05)
    assert watcher.start((project / "panels",))
    try:
        watcher.changed()
        watcher.changed()
        watcher.changed()
        assert arrived.wait(timeout=5.0)
        time.sleep(0.2)
        assert len(calls) == 1
    finally:
        watcher.stop()
    watcher.changed()
    time.sleep(0.2)
    assert len(calls) == 1


def test_source_handler_forwards_only_panel_source_changes(project: Path) -> None:
    (project / "panels").mkdir()
    watcher = PanelSourceWatcher(lambda: None)
    assert watcher.start((project / "panels",))
    seen: list[int] = []
    watcher.changed = lambda: seen.append(1)  # type: ignore[method-assign]
    root = (project / "panels").resolve()
    handler = _SourceHandler(watcher)
    try:
        handler.on_any_event(FileClosedEvent(str(root / "a" / "panel.json")))
        handler.on_any_event(FileCreatedEvent(str(root / "a" / "__pycache__" / "panel.pyc")))
        handler.on_any_event(FileCreatedEvent(str(root / "a" / "answers.json")))
        handler.on_any_event(FileCreatedEvent(str(project.resolve() / "blocks" / "x.py")))
        assert seen == []
        handler.on_any_event(FileModifiedEvent(str(root / "a" / "panel.json")))
        handler.on_any_event(FileCreatedEvent(str(root / "a" / "index.html")))
        handler.on_any_event(DirCreatedEvent(str(root / "b")))
        assert len(seen) == 3
    finally:
        watcher.stop()


def test_is_panel_source_change_rules(project: Path) -> None:
    roots = ((project / "panels").resolve(),)
    root = roots[0]
    assert is_panel_source_change(roots, root, is_directory=True)
    assert is_panel_source_change(roots, root / "a" / "panel.py", is_directory=False)
    assert is_panel_source_change(roots, root / "a" / "lib" / "app.js", is_directory=False)
    assert not is_panel_source_change(roots, root / "a" / "results.parquet", is_directory=False)
    assert not is_panel_source_change(roots, root / "a" / ".__scistudio_write_1.tmp", is_directory=False)
    assert not is_panel_source_change(roots, root / "a" / "answers.json", is_directory=False)
    assert not is_panel_source_change(roots, project / "other" / "panel.json", is_directory=False)


def test_the_service_watch_announces_a_new_miniapp(project: Path) -> None:
    """End to end on a real observer: the panels folder does not exist yet."""
    bus = _RecordingBus()
    runtime = _runtime(project, bus)
    service = runtime.get_panel_service()
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    try:
        service.start(loop)
        time.sleep(0.2)
        _write_panel(project, "table_explorer")
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if any(data.get("panels", {}).get("added") == ["table_explorer"] for data in bus.of("blocks.reloaded")):
                break
            time.sleep(0.05)
    finally:
        service.stop()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2.0)
        loop.close()
    assert any(data.get("panels", {}).get("added") == ["table_explorer"] for data in bus.of("blocks.reloaded")), (
        bus.events
    )
    assert service.panel("table_explorer") is not None


def test_a_descriptor_edit_keeps_the_session_a_revoked_preview_reopens_on(project: Path, tmp_path: Path) -> None:
    # Codex review on #2466: a metadata-only edit revokes the preview context
    # but must not delete the session the host reopens the context with.
    runtime = _runtime(project)
    service = runtime.get_panel_service()
    _text_record(runtime, tmp_path)
    _write_panel(project, "lab.text", contexts=["preview"], types=["Text"])
    service.rescan()
    target = runtime.resolve_session_target(PreviewTarget(kind=TargetKind.DATA_REF, ref="data-text"))
    envelope = service.create_preview_session(target)
    request = {
        "kind": "preview",
        "panel_id": "lab.text",
        "target": {"ref": "data-text"},
        "preview_session_id": envelope.session_id,
    }
    context = service.contexts.create(request)

    _write_panel(project, "lab.text", contexts=["preview"], types=["Text"], name="Renamed")
    diff = service.rescan()
    assert diff.changed == {"lab.text"} and not diff.preview_types
    assert context.context_id not in service.contexts.contexts
    reopened = service.open_context(request)
    assert reopened.panel.name == "Renamed"

    import shutil

    shutil.rmtree(project / "panels" / "lab.text")
    assert service.rescan().removed == {"lab.text"}
    from scistudio.previewers.models import UnknownPreviewerError

    with pytest.raises(UnknownPreviewerError):
        service.read_session(envelope.session_id)


def test_the_panel_browser_backend_builds_its_fixture_runtime(tmp_path: Path) -> None:
    # Codex review on #2466: the Playwright panel server builds its runtime
    # through the panel service, not the removed legacy install_panels.
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "frontend" / "e2e" / "helpers" / "panel-backend.py"
    spec = importlib.util.spec_from_file_location("panel_browser_backend", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runtime = module.build_runtime(tmp_path)
    service = runtime.get_panel_service()
    for name in ("reader", "early", "later", "navigator", "table"):
        assert service.panel(f"browser.{name}") is not None
    context = service.open_context({"kind": "preview", "panel_id": "browser.reader", "target": {"ref": "data-a"}})
    assert context.panel.id == "browser.reader"
    # The composite's text slot has no panel, so it renders through the legacy core viewer.
    from scistudio.previewers.models import PreviewTarget as Target

    slot = Target(kind=TargetKind.DATA_REF, ref="comp#notes", recorded_type="Text", type_chain=("Text",))
    assert service.route(slot).previewer_id == "core.text.basic"
    assert service.route(slot).panel is None
