"""T-003 (ADR-054 MiniApp FR-004/FR-005/FR-013): the miniapp context.

Opening a context on a block output starts one process bound to the target,
provides read/call/save (never open/writeBack), refuses a mismatched or missing
output, and ends its process when the context closes, the project switches, or
its realtime client is gone. Preview and interactive contexts never start a
process and never expose call (US3).
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.panels.conftest import install_panel_service

from scistudio.api.runtime.models import DataRecord
from scistudio.core.storage.ref import StorageReference
from scistudio.engine.events import EventBus
from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.panels import process as process_mod
from scistudio.panels.contexts import PanelContexts
from scistudio.panels.descriptor import parse_descriptor
from scistudio.panels.registry import PanelRegistry
from scistudio.panels.service import get_panel_contexts
from scistudio.panels.targets import PanelError
from scistudio.previewers.models import OwnerKind, PreviewTarget

pytestmark = pytest.mark.serial

_PANEL_PY = (
    "seen = {}\n"
    "def setup(data):\n    seen['type'] = type(data).__name__\n"
    "def kind():\n    return seen.get('type')\n"
    "def double(x):\n    return x * 2\n"
)


def _make(
    tmp_path: Path,
    *,
    contexts='["miniapp"]',
    types='["Text"]',
    with_python=True,
    panel_py=_PANEL_PY,
    owner_kind=OwnerKind.PROJECT,
    storage_metadata=None,
    record_metadata=None,
):
    panel_dir = tmp_path / "lab.explorer"
    panel_dir.mkdir()
    (panel_dir / "panel.json").write_text(
        f'{{"id":"lab.explorer","api_version":"1.0","contexts":{contexts},"types":{types}}}', encoding="utf-8"
    )
    (panel_dir / "index.html").write_text("<p>app</p>", encoding="utf-8")
    if with_python:
        (panel_dir / "panel.py").write_text(panel_py, encoding="utf-8")

    data = tmp_path / "data.txt"
    data.write_text("hello", encoding="utf-8")
    panels = PanelRegistry()
    panels.register(
        parse_descriptor(
            panel_dir, owner_kind=owner_kind, owner_name=owner_kind.value, registered_types={"Text", "DataFrame"}
        )[0]
    )
    record = DataRecord(
        "data-a",
        StorageReference(
            backend="filesystem",
            path=str(data),
            metadata={"type_chain": ["DataObject", "Text"]} if storage_metadata is None else storage_metadata,
        ),
        "Text",
        {"type_chain": ["DataObject", "Text"]} if record_metadata is None else record_metadata,
        ["DataObject", "Text"],
    )
    scheduler = SimpleNamespace(
        _project_dir=str(tmp_path),
        _block_outputs={"seg": {"out": {"data_ref": "data-a"}}},
        _block_states={"seg": SimpleNamespace(value="done")},
    )
    runtime = SimpleNamespace(
        active_project=SimpleNamespace(id="p", path=str(tmp_path)),
        data_catalog={"data-a": record},
        workflow_runs={"wf": SimpleNamespace(scheduler=scheduler)},
        event_bus=EventBus(),
    )
    runtime.event_bus.runtime = runtime
    runtime.get_data_record = lambda ref: runtime.data_catalog[ref]
    runtime.resolve_session_target = lambda target: PreviewTarget(
        kind=target.kind,
        ref=target.ref,
        recorded_type=runtime.data_catalog[target.ref].type_name,
        type_chain=tuple(runtime.data_catalog[target.ref].type_chain),
    )
    runtime.type_registry = SimpleNamespace(
        resolve=lambda name: SimpleNamespace(base_type={"Text": "DataObject"}.get(name, ""))
    )
    proc_registry = ProcessRegistry()
    # A test swaps ``runtime.test_panels[0]`` and rescans to change the catalog.
    runtime.test_panels = [panels]
    install_panel_service(runtime, lambda: runtime.test_panels[0])
    return runtime, get_panel_contexts(runtime), proc_registry, panel_dir


_SOURCE = {
    "kind": "miniapp",
    "panel_id": "lab.explorer",
    "source": {"workflow_id": "wf", "block_id": "seg", "port": "out"},
}


def _await_running(process, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline and process.state != process_mod.RUNNING:
        time.sleep(0.02)
    return process.state


def test_open_starts_one_registered_process_on_the_target(tmp_path: Path) -> None:
    _runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE, ws_client_id="ws-1"), process_registry=registry)
    try:
        assert context.kind == "miniapp"
        assert context.provides() == (["read", "call", "submitAnswers"], ["save"])
        assert context.input["ref"] == "data-a"
        assert context.input["panel_id"] == "lab.explorer"
        assert _await_running(context.process) == process_mod.RUNNING
        handle = registry.get_handle(process_mod.REGISTRY_NAMESPACE, f"context-{context.context_id}")
        assert handle is not None
        assert context.process.call("double", {"x": 21}).header["result"] == 42
        # setup received the reconstructed target object.
        assert context.process.call("kind", {}).header["result"]
    finally:
        store.close(context.context_id)


def test_close_stops_and_deregisters_the_process(tmp_path: Path) -> None:
    _runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE), process_registry=registry)
    assert _await_running(context.process) == process_mod.RUNNING
    pid = context.process._popen.pid
    store.close(context.context_id)
    import psutil

    deadline = time.time() + 10
    while time.time() < deadline and psutil.pid_exists(pid):
        time.sleep(0.05)
    assert not psutil.pid_exists(pid)
    while time.time() < deadline and registry.get_handle(
        process_mod.REGISTRY_NAMESPACE, f"context-{context.context_id}"
    ):
        time.sleep(0.02)
    assert registry.get_handle(process_mod.REGISTRY_NAMESPACE, f"context-{context.context_id}") is None


def test_project_switch_closes_and_stops(tmp_path: Path) -> None:
    runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE), process_registry=registry)
    assert _await_running(context.process) == process_mod.RUNNING
    pid = context.process._popen.pid
    # A project switch triggers close_all through _synchronize.
    runtime.active_project = SimpleNamespace(id="other", path=str(tmp_path / "other"))
    store._synchronize()
    import psutil

    deadline = time.time() + 10
    while time.time() < deadline and psutil.pid_exists(pid):
        time.sleep(0.05)
    assert not psutil.pid_exists(pid)


def test_close_for_disconnected_client_stops_the_process(tmp_path: Path) -> None:
    _runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE, ws_client_id="ws-9"), process_registry=registry)
    assert _await_running(context.process) == process_mod.RUNNING
    pid = context.process._popen.pid
    store.close_for_client("ws-9")
    assert context.context_id not in store.contexts
    import psutil

    deadline = time.time() + 10
    while time.time() < deadline and psutil.pid_exists(pid):
        time.sleep(0.02)
    assert not psutil.pid_exists(pid)


def test_restart_starts_a_fresh_process_for_the_same_target(tmp_path: Path) -> None:
    _runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE), process_registry=registry)
    assert _await_running(context.process) == process_mod.RUNNING
    first_pid = context.process._popen.pid
    store.restart(context.context_id, registry)
    try:
        assert _await_running(context.process) == process_mod.RUNNING
        assert context.process._popen.pid != first_pid
        assert context.input["ref"] == "data-a"
    finally:
        store.close(context.context_id)


def test_missing_output_is_refused(tmp_path: Path) -> None:
    _runtime, store, registry, _ = _make(tmp_path)
    bad = dict(_SOURCE, source={"workflow_id": "wf", "block_id": "seg", "port": "nope"})
    with pytest.raises(PanelError) as exc:
        store.create(bad, process_registry=registry)
    assert exc.value.code == "no_output"


def test_type_mismatch_is_refused(tmp_path: Path) -> None:
    # The declared type is DataFrame but the block output is Text.
    runtime, store, registry, _ = _make(tmp_path, types='["DataFrame"]')
    # DataFrame must be registered for the descriptor to parse; re-register.
    from scistudio.panels.descriptor import parse_descriptor

    panels = PanelRegistry()
    panel_dir = tmp_path / "lab.explorer"
    panels.register(
        parse_descriptor(panel_dir, owner_kind=OwnerKind.PROJECT, owner_name="p", registered_types={"DataFrame"})[0]
    )
    runtime.test_panels[0] = panels
    runtime.get_panel_service().rescan(force=True)
    with pytest.raises(PanelError) as exc:
        store.create(dict(_SOURCE), process_registry=registry)
    assert exc.value.code == "type_mismatch"


def test_data_reclaimed_closes_context_and_stops(tmp_path: Path) -> None:
    _runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE), process_registry=registry)
    assert _await_running(context.process) == process_mod.RUNNING
    pid = context.process._popen.pid
    # The run that produced the target is reclaimed: the file disappears.
    Path(tmp_path / "data.txt").unlink()
    with pytest.raises(PanelError):
        store.get(context.context_id)
    assert context.context_id not in store.contexts
    import psutil

    deadline = time.time() + 10
    while time.time() < deadline and psutil.pid_exists(pid):
        time.sleep(0.05)
    assert not psutil.pid_exists(pid)


def test_preview_context_of_a_python_panel_starts_nothing_and_has_no_call(tmp_path: Path) -> None:
    # US3: a panel that declares preview and miniapp and carries panel.py must
    # start no process and expose no call when opened as a preview.
    _runtime, store, registry, _ = _make(tmp_path, contexts='["preview","miniapp"]', types='["Text"]')
    context = store.create(
        {"kind": "preview", "panel_id": "lab.explorer", "target": {"ref": "data-a"}}, process_registry=registry
    )
    try:
        assert context.process is None
        assert context.provides() == (["read"], ["open", "save"])
        assert "call" not in context.provides()[0]
        assert registry.active_handles() == []
    finally:
        store.close(context.context_id)


def test_interactive_context_provides_no_call() -> None:
    # A unit check of the operation contract: interactive never provides call.
    from scistudio.panels.contexts import PanelContext

    context = PanelContext(
        context_id="pc-x",
        panel=None,  # type: ignore[arg-type]
        kind="interactive",
        project=(),
        token="t",
        expires_at=0.0,
        input={},
    )
    assert context.provides() == (["writeBack"], ["save"])


def test_store_is_a_singleton_per_runtime(tmp_path: Path) -> None:
    runtime, store, _, _ = _make(tmp_path)
    assert get_panel_contexts(runtime) is store
    assert isinstance(store, PanelContexts)


# -- FR-006: the import roots a block worker receives -----------------------


def test_panel_py_imports_the_roots_a_block_worker_imports(tmp_path: Path) -> None:
    # FR-006: a MiniApp's panel.py must reach the project's drop-in tier the
    # same way a block worker does. ``types/`` is the project import root the
    # runtime puts on a worker's path; a module there must import in panel.py.
    (tmp_path / "types").mkdir()
    (tmp_path / "types" / "panel_import_probe.py").write_text("VALUE = 7\n", encoding="utf-8")
    body = (
        "def setup(data):\n    pass\ndef probe():\n    import panel_import_probe\n    return panel_import_probe.VALUE\n"
    )
    _runtime, store, registry, _ = _make(tmp_path, panel_py=body)
    context = store.create(dict(_SOURCE), process_registry=registry)
    try:
        assert _await_running(context.process) == process_mod.RUNNING
        assert context.process.call("probe", {}).header["result"] == 7
    finally:
        store.close(context.context_id)


def test_the_context_carries_the_runtime_import_roots(tmp_path: Path) -> None:
    from scistudio.core.dropins import dropin_import_roots

    _runtime, store, registry, _ = _make(tmp_path, with_python=False)
    context = store.create(dict(_SOURCE), process_registry=registry)
    try:
        expected = [str(path) for path in dropin_import_roots(str(tmp_path))]
        assert [root for root in context.import_roots if root in expected] == expected
    finally:
        store.close(context.context_id)


# -- FR-007: the target reconstructed as the catalog records it -------------


def test_setup_receives_the_target_as_its_recorded_type(tmp_path: Path) -> None:
    # FR-007: ``data`` is the target reconstructed by the engine's own
    # reconstruction. The storage reference's own sidecar is less specific than
    # the catalog record here; setup must still receive a Text, not the bare
    # DataObject the reference alone would rebuild, and the record's user slot
    # must survive the trip.
    body = (
        "seen = {}\n"
        "def setup(data):\n    seen['type'] = type(data).__name__\n    seen['user'] = dict(getattr(data, 'user', {}))\n"
        "def kind():\n    return seen['type']\n"
        "def user_slot():\n    return seen['user']\n"
    )
    _runtime, store, registry, _ = _make(
        tmp_path,
        panel_py=body,
        storage_metadata={"type_chain": ["DataObject"]},
        record_metadata={"type_chain": ["DataObject", "Text"], "user": {"note": "from-catalog"}},
    )
    context = store.create(dict(_SOURCE), process_registry=registry)
    try:
        assert _await_running(context.process) == process_mod.RUNNING
        assert context.process.call("kind", {}).header["result"] == "Text"
        assert context.process.call("user_slot", {}).header["result"] == {"note": "from-catalog"}
    finally:
        store.close(context.context_id)


# -- FR-013: the context is bound to one realtime client --------------------


def test_close_for_client_leaves_another_clients_context_open(tmp_path: Path) -> None:
    _runtime, store, registry, _ = _make(tmp_path, with_python=False)
    mine = store.create(dict(_SOURCE, ws_client_id="ws-1"), process_registry=registry)
    theirs = store.create(dict(_SOURCE, ws_client_id="ws-2"), process_registry=registry)
    try:
        store.close_for_client("ws-2")
        assert theirs.context_id not in store.contexts
        assert mine.context_id in store.contexts
        store.close_for_client("ws-nobody")
        assert mine.context_id in store.contexts
    finally:
        store.close(mine.context_id)


# -- FR-014: Restart ---------------------------------------------------------


def test_restart_renews_the_lease_so_synchronize_cannot_close_it(tmp_path: Path) -> None:
    # A restart late in the 600 s lease used to leave expires_at untouched, so
    # the next _synchronize closed the context the user had just restarted.
    _runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE), process_registry=registry)
    try:
        assert _await_running(context.process) == process_mod.RUNNING
        context.expires_at = store.clock() + 0.5
        store.restart(context.context_id, registry)
        assert context.expires_at > store.clock() + 500
        time.sleep(0.6)
        store._synchronize()
        assert context.context_id in store.contexts
        assert _await_running(context.process) == process_mod.RUNNING
    finally:
        store.close(context.context_id)


def test_restart_after_the_data_is_gone_closes_the_context(tmp_path: Path) -> None:
    # US7 edge case: artifact retention reclaimed the run that produced the
    # target. Restart must not start a process on data that is not there; the
    # context closes and the tab is told, so it can offer the picker.
    _runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE), process_registry=registry)
    assert _await_running(context.process) == process_mod.RUNNING
    (tmp_path / "data.txt").unlink()
    with pytest.raises(PanelError) as exc:
        store.restart(context.context_id, registry)
    assert exc.value.code == "stale_context"
    assert context.context_id not in store.contexts


def test_restart_rebuilds_the_setup_payload_from_the_revalidated_target(tmp_path: Path) -> None:
    _runtime, store, registry, _ = _make(tmp_path, with_python=False)
    context = store.create(dict(_SOURCE), process_registry=registry)
    try:
        context.setup_payload = {"stale": True}
        store.restart(context.context_id, registry)
        assert context.setup_payload["path"] == str(tmp_path / "data.txt")
        assert context.setup_payload["metadata"]["type_chain"] == ["DataObject", "Text"]
    finally:
        store.close(context.context_id)


# -- FR-022: the panel directory watch --------------------------------------


def test_an_open_project_miniapp_watches_its_directory(tmp_path: Path) -> None:
    _runtime, store, registry, panel_dir = _make(tmp_path, with_python=False)
    context = store.create(dict(_SOURCE), process_registry=registry)
    watches = _runtime.get_panel_service().file_watches
    try:
        assert context.watched is True
        assert watches.watched() == {"lab.explorer": 1}
        assert watches._watches["lab.explorer"][0].directory == panel_dir.resolve()
    finally:
        store.close(context.context_id)
    assert context.watched is False
    assert watches.watched() == {}


def test_a_package_miniapp_is_not_watched(tmp_path: Path) -> None:
    # FR-022 watches the project and user tiers only.
    _runtime, store, registry, _ = _make(tmp_path, with_python=False, owner_kind=OwnerKind.PACKAGE)
    context = store.create(dict(_SOURCE), process_registry=registry)
    try:
        assert context.watched is False
    finally:
        store.close(context.context_id)


# -- SC-005: a hanging panel.py does not hold the store ----------------------


def test_closing_a_hanging_panel_answers_at_once(tmp_path: Path, monkeypatch) -> None:
    # SC-005/US7: teardown never returns, so PanelProcess.stop must wait out the
    # grace period and kill the tree. That wait must not happen on the caller's
    # thread and must not hold the store lock, or one hung MiniApp blocks every
    # panel request — and, through the realtime handler, the event loop.
    monkeypatch.setenv("SCISTUDIO_PANEL_TEARDOWN_GRACE", "0.5")
    body = (
        "import time\ndef setup(data):\n    pass\ndef ping():\n    return 'pong'\ndef teardown():\n    time.sleep(60)\n"
    )
    _runtime, store, registry, _ = _make(tmp_path, panel_py=body)
    other = store.create(dict(_SOURCE, ws_client_id="ws-other"), process_registry=registry)
    hanging = store.create(dict(_SOURCE), process_registry=registry)
    assert _await_running(hanging.process) == process_mod.RUNNING
    pid = hanging.process._popen.pid
    started = time.monotonic()
    store.close(hanging.context_id)
    closed = time.monotonic() - started
    # The store answers another request while the hung process is being killed.
    assert store.get(other.context_id) is other
    answered = time.monotonic() - started
    store.close(other.context_id)
    assert closed < 1.0
    assert answered < 1.0

    import psutil

    deadline = time.time() + 20
    while time.time() < deadline and psutil.pid_exists(pid):
        time.sleep(0.05)
    assert not psutil.pid_exists(pid)


def test_an_interactive_panel_with_panel_py_starts_nothing(tmp_path: Path) -> None:
    # US3 scenario 2: a panel that declares interactive and miniapp and carries
    # panel.py starts no process when its block pauses, and its context provides
    # writeBack rather than call.
    runtime, store, registry, _ = _make(tmp_path, contexts='["interactive","miniapp"]')
    scheduler = runtime.workflow_runs["wf"].scheduler
    scheduler._block_states["ask"] = SimpleNamespace(value="paused")
    scheduler._interactive_futures = {"ask": SimpleNamespace(done=lambda: False)}
    store.prompts[("wf", "ask")] = {"panel_manifest": {"panel_id": "lab.explorer"}, "panel_payload": {"q": 1}}
    context = store.create(
        {"kind": "interactive", "panel_id": "lab.explorer", "workflow_id": "wf", "block_id": "ask"},
        process_registry=registry,
    )
    try:
        assert context.process is None
        assert context.provides() == (["writeBack"], ["save"])
        assert registry.active_handles() == []
    finally:
        store.close(context.context_id)


def test_stop_does_not_hold_context_lock(tmp_path: Path) -> None:
    import threading

    _runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE), process_registry=registry)
    original = context.process
    entered, release = threading.Event(), threading.Event()

    def blocked_stop():
        entered.set()
        release.wait(3)

    context.process = SimpleNamespace(stop=blocked_stop)
    worker = threading.Thread(target=store.stop_process, args=(context.context_id,))
    worker.start()
    try:
        assert entered.wait(1)
        assert store.lock.acquire(timeout=0.2)
        store.lock.release()
    finally:
        release.set()
        worker.join(3)
        original.stop()
        store.close_all()


def test_project_switch_does_not_join_teardown_on_event_loop(tmp_path: Path) -> None:
    import threading

    runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE), process_registry=registry)
    original = context.process
    release = threading.Event()
    context.process = SimpleNamespace(stop=lambda: release.wait(3))
    try:
        runtime.active_project = SimpleNamespace(id="other", path=str(tmp_path / "other"))
        start = time.monotonic()
        with store.lock:
            store._synchronize()
        assert time.monotonic() - start < 0.5
        assert not store.contexts
    finally:
        release.set()
        original.stop()


def test_html_only_miniapp_does_not_advertise_call(tmp_path: Path) -> None:
    _runtime, store, registry, _ = _make(tmp_path, with_python=False)
    context = store.create(dict(_SOURCE), process_registry=registry)
    try:
        assert context.provides() == (["read", "submitAnswers"], ["save"])
        with pytest.raises(PanelError, match="no panel process"):
            store.stop_process(context.context_id)
    finally:
        store.close_all()


# -- #2455 / #2465: catalog changes leave unrelated contexts open ------------


def _write_miniapp(root: Path, panel_id: str, **fields: object) -> Path:
    import json

    folder = root / panel_id
    folder.mkdir(parents=True)
    (folder / "index.html").write_text("<p>other</p>", encoding="utf-8")
    descriptor = {"id": panel_id, "api_version": "1.0", "contexts": ["miniapp"], "types": ["Text"], **fields}
    (folder / "panel.json").write_text(json.dumps(descriptor), encoding="utf-8")
    return folder


def _with(runtime, *folders: Path) -> PanelRegistry:
    panels = PanelRegistry()
    for folder in folders:
        panels.register(
            parse_descriptor(folder, owner_kind=OwnerKind.PROJECT, owner_name="project", registered_types={"Text"})[0]
        )
    runtime.test_panels[0] = panels
    return panels


def test_writing_a_new_miniapp_leaves_every_open_miniapp_running(tmp_path: Path) -> None:
    # #2455: an agent wrote a MiniApp and opened it; the catalog refresh used to
    # rebuild the preview service and close every MiniApp already open.
    runtime, store, registry, panel_dir = _make(tmp_path)
    service = runtime.get_panel_service()
    first = store.create(dict(_SOURCE, ws_client_id="ws-1"), process_registry=registry)
    second = store.create(dict(_SOURCE, ws_client_id="ws-1"), process_registry=registry)
    try:
        assert _await_running(first.process) == process_mod.RUNNING
        assert _await_running(second.process) == process_mod.RUNNING
        _with(runtime, panel_dir, _write_miniapp(tmp_path / "more", "lab.second"))
        diff = service.rescan(force=True)
        assert diff.added == {"lab.second"} and not diff.invalidated
        opened = store.create(dict(_SOURCE, panel_id="lab.second"), process_registry=registry)
        store.close(opened.context_id)

        for context in (first, second):
            assert store.get(context.context_id) is context
            assert store.by_token(context.token) is context
            assert context.process.state == process_mod.RUNNING
            assert context.process.call("double", {"x": 4}).header["result"] == 8
        assert set(store.contexts) == {first.context_id, second.context_id}
    finally:
        store.close_all()


def test_a_legacy_reload_leaves_miniapp_contexts_open(tmp_path: Path) -> None:
    runtime, store, registry, _ = _make(tmp_path, with_python=False)
    context = store.create(dict(_SOURCE), process_registry=registry)
    runtime.get_panel_service().refresh()
    assert store.get(context.context_id) is context
    store.close_all()


def test_changing_the_open_miniapp_descriptor_revokes_only_its_contexts(tmp_path: Path) -> None:
    import json

    runtime, store, registry, panel_dir = _make(tmp_path, with_python=False)
    other = _write_miniapp(tmp_path / "more", "lab.other")
    _with(runtime, panel_dir, other)
    service = runtime.get_panel_service()
    service.rescan(force=True)
    seen: list = []
    runtime.event_bus.subscribe("panel.contexts_revoked", seen.append)
    changed = store.create(dict(_SOURCE), process_registry=registry)
    kept = store.create(dict(_SOURCE, panel_id="lab.other"), process_registry=registry)
    descriptor = json.loads((panel_dir / "panel.json").read_text())
    (panel_dir / "panel.json").write_text(json.dumps(descriptor | {"name": "Renamed"}), encoding="utf-8")
    _with(runtime, panel_dir, other)
    diff = service.rescan(force=True)
    assert diff.changed == {"lab.explorer"} and diff.miniapps_changed
    assert changed.context_id not in store.contexts
    assert store.get(kept.context_id) is kept
    assert [event.data for event in seen] == [
        {"context_ids": [changed.context_id], "panel_ids": ["lab.explorer"], "reason": "panel_changed"}
    ]
    store.close_all()


def test_the_first_answers_file_changes_nothing(tmp_path: Path) -> None:
    # MiniApp FR-051: the host writes answers.json into the MiniApp folder; the
    # catalog does not look at it, so nothing is rediscovered or revoked.
    from scistudio.panels.registry import panel_sources_fingerprint

    runtime, store, registry, panel_dir = _make(tmp_path, with_python=False)
    service = runtime.get_panel_service()
    context = store.create(dict(_SOURCE), process_registry=registry)
    before = panel_sources_fingerprint(tmp_path)
    (panel_dir / "answers.json").write_text("{}", encoding="utf-8")
    (panel_dir / ".answers-123.tmp").write_text("{}", encoding="utf-8")
    assert panel_sources_fingerprint(tmp_path) == before
    assert service.rescan().empty
    assert store.get(context.context_id) is context
    store.close_all()


def test_closing_the_project_ends_miniapps_at_once(tmp_path: Path) -> None:
    # MiniApp FR-013 / #2465: leaving a project closes its contexts immediately,
    # not on the next panel request.
    import psutil

    runtime, store, registry, _ = _make(tmp_path)
    context = store.create(dict(_SOURCE), process_registry=registry)
    assert _await_running(context.process) == process_mod.RUNNING
    pid = context.process._popen.pid
    closed = runtime.get_panel_service().close_project()
    assert closed == [context.context_id]
    assert not store.contexts
    deadline = time.time() + 10
    while time.time() < deadline and psutil.pid_exists(pid):
        time.sleep(0.05)
    assert not psutil.pid_exists(pid)


def test_reopening_the_open_project_keeps_its_miniapps(tmp_path: Path) -> None:
    runtime, store, registry, _ = _make(tmp_path, with_python=False)
    context = store.create(dict(_SOURCE), process_registry=registry)
    runtime.active_project = SimpleNamespace(id="p", path=str(tmp_path))
    runtime.get_panel_service().refresh()
    assert store.get(context.context_id) is context
    store.close_all()
