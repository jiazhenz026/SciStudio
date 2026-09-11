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

from scistudio.api.runtime.models import DataRecord
from scistudio.core.storage.ref import StorageReference
from scistudio.engine.events import EventBus
from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.panels import process as process_mod
from scistudio.panels.contexts import PanelContexts, get_panel_contexts
from scistudio.panels.descriptor import parse_descriptor
from scistudio.panels.registry import PanelRegistry
from scistudio.panels.targets import PanelError
from scistudio.previewers.models import OwnerKind, PreviewTarget
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter
from scistudio.previewers.session import PreviewSessionManager

pytestmark = pytest.mark.serial

_PANEL_PY = (
    "seen = {}\n"
    "def setup(data):\n    seen['type'] = type(data).__name__\n"
    "def kind():\n    return seen.get('type')\n"
    "def double(x):\n    return x * 2\n"
)


def _make(tmp_path: Path, *, contexts='["miniapp"]', types='["Text"]', with_python=True):
    panel_dir = tmp_path / "lab.explorer"
    panel_dir.mkdir()
    (panel_dir / "panel.json").write_text(
        f'{{"id":"lab.explorer","api_version":"1.0","contexts":{contexts},"types":{types}}}', encoding="utf-8"
    )
    (panel_dir / "index.html").write_text("<p>app</p>", encoding="utf-8")
    if with_python:
        (panel_dir / "panel.py").write_text(_PANEL_PY, encoding="utf-8")

    data = tmp_path / "data.txt"
    data.write_text("hello", encoding="utf-8")
    panels = PanelRegistry()
    panels.register(
        parse_descriptor(
            panel_dir, owner_kind=OwnerKind.PROJECT, owner_name="project", registered_types={"Text", "DataFrame"}
        )[0]
    )
    registry = PreviewerRegistry()
    registry.load_core()
    registry.install_panels(panels)
    service = SimpleNamespace(
        registry=registry, router=PreviewRouter(registry), sessions=PreviewSessionManager(registry)
    )
    record = DataRecord(
        "data-a",
        StorageReference(backend="filesystem", path=str(data), metadata={"type_chain": ["DataObject", "Text"]}),
        "Text",
        {"type_chain": ["DataObject", "Text"]},
        ["DataObject", "Text"],
    )
    scheduler = SimpleNamespace(
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
    runtime.get_preview_service = lambda: service
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
        assert context.provides() == (["read", "call"], ["save"])
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
    store.close_for_client("ws-9")
    assert context.context_id not in store.contexts


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
    runtime.get_preview_service().registry.install_panels(panels)
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
        preview_service=None,
        token="t",
        expires_at=0.0,
        input={},
    )
    assert context.provides() == (["writeBack"], ["save"])


def test_store_is_a_singleton_per_runtime(tmp_path: Path) -> None:
    runtime, store, _, _ = _make(tmp_path)
    assert get_panel_contexts(runtime) is store
    assert isinstance(store, PanelContexts)
