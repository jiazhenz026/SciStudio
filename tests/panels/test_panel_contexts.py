"""Context reference authority, lifecycle, expiry and waiting-block identity."""

import asyncio
from types import SimpleNamespace

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import EngineEvent
from scistudio.panels.targets import PanelError


def open_preview(store):
    return store.create({"kind": "preview", "target": {"kind": "data_ref", "ref": "data-a"}})


def test_unknown_ref_and_miniapp_refused(panel_runtime):
    _, store = panel_runtime
    with pytest.raises(PanelError, match="catalog reference"):
        store.create(
            {"kind": "preview", "target": {"ref": "/etc/passwd"}, "query": {"_storage": {"path": "/etc/passwd"}}}
        )
    with pytest.raises(PanelError, match="Phase A"):
        store.create({"kind": "miniapp", "panel_id": "lab.text"})


def test_close_revoke_renew_expiry_and_project_change(panel_runtime):
    runtime, store = panel_runtime
    now = [1000]
    store.clock = lambda: now[0]
    ctx = open_preview(store)
    now[0] += 20
    assert store.renew(ctx.context_id).token == ctx.token
    assert ctx.expires_at == 1620
    store.close(ctx.context_id)
    with pytest.raises(PanelError):
        store.by_token(ctx.token)
    ctx = open_preview(store)
    now[0] += 601
    with pytest.raises(PanelError):
        store.by_token(ctx.token)
    ctx = open_preview(store)
    runtime.active_project = SimpleNamespace(id="other", path="/other")
    with pytest.raises(PanelError):
        store.get(ctx.context_id)


def test_record_replacement_and_file_mutation_revoke(panel_runtime, tmp_path):
    runtime, store = panel_runtime
    ctx = open_preview(store)
    (tmp_path / "data.txt").write_text("replacement")
    with pytest.raises(PanelError, match="stored data changed"):
        store.get(ctx.context_id)
    ctx = open_preview(store)
    from copy import deepcopy

    runtime.data_catalog["data-a"] = deepcopy(runtime.data_catalog["data-a"])
    with pytest.raises(PanelError, match="catalog reference changed"):
        store.get(ctx.context_id)


def waiting(runtime, store):
    future = SimpleNamespace(done=lambda: False)
    runtime.workflow_runs["wf"] = SimpleNamespace(
        scheduler=SimpleNamespace(_interactive_futures={"block": future}, _block_states={"block": BlockState.PAUSED})
    )
    event = EngineEvent(
        event_type="interactive_prompt",
        block_id="block",
        data={
            "workflow_id": "wf",
            "panel_manifest": {"panel_id": "lab.text", "module_url": ""},
            "panel_payload": {"answer": 42},
        },
    )
    store.on_event(event)
    return store.create({"kind": "interactive", "panel_id": "lab.text", "workflow_id": "wf", "block_id": "block"})


def test_interactive_input_is_backend_snapshot_and_writeback_once(panel_runtime):
    runtime, store = panel_runtime
    ctx = waiting(runtime, store)
    assert ctx.input == {"answer": 42}
    with pytest.raises(PanelError, match="no data references"):
        store.authorize(ctx, "data-a")
    with pytest.raises(PanelError):
        store.claim_writeback(None, "wf", "block", {})
    with pytest.raises(PanelError):
        store.claim_writeback(ctx.context_id, "other", "block", {})
    with pytest.raises(PanelError):
        store.claim_writeback(ctx.context_id, "wf", "block", {"value": float("nan")})
    store.claim_writeback(ctx.context_id, "wf", "block", {"decision": True})
    with pytest.raises(PanelError):
        store.claim_writeback(ctx.context_id, "wf", "block", {})


def test_cancel_event_revokes_interactive_context(panel_runtime):
    runtime, store = panel_runtime
    ctx = waiting(runtime, store)
    asyncio.run(
        runtime.event_bus.emit(
            EngineEvent(event_type="cancel_block_request", block_id="block", data={"workflow_id": "wf"})
        )
    )
    with pytest.raises(PanelError):
        store.by_token(ctx.token)


@pytest.mark.parametrize("change", ["project", "service", "data"])
@pytest.mark.parametrize("operation", ["read", "patch", "resource"])
def test_independent_child_session_validates_every_followup(panel_runtime, change, operation):
    from dataclasses import replace

    from scistudio.panels.registry import PanelRegistry
    from scistudio.panels.targets import register_collection
    from scistudio.previewers.models import UnknownPreviewerError

    runtime, store = panel_runtime
    service = runtime.get_preview_service()
    panels = PanelRegistry()
    panels.register(replace(service.registry.panels.get("lab.text"), types=("Collection[Text]",)))
    service.registry.install_panels(panels)
    group = register_collection(runtime, {"count": 1, "item_type": "Text", "items": [{"data_ref": "data-a"}]})
    parent = store.create({"kind": "preview", "target": {"ref": group["collection_ref"]}})
    envelope = store.open_child(parent.context_id, "data-a")
    store.close(parent.context_id)
    if change == "project":
        runtime.active_project = SimpleNamespace(id="other", path="other")
    elif change == "service":
        runtime.get_preview_service = lambda: object()
    else:
        runtime.data_catalog["data-a"].metadata["changed"] = True
    with pytest.raises(UnknownPreviewerError):
        if operation == "read":
            service.sessions.read_session(envelope.session_id)
        elif operation == "patch":
            service.sessions.patch_session(envelope.session_id, {"page": 2})
        else:
            service.sessions.read_resource(envelope.session_id, "tile")
    assert envelope.session_id not in service.sessions._session_guards
    assert envelope.session_id not in service.sessions._session_authorities


def test_child_session_eviction_cleans_authority(panel_runtime):
    from scistudio.panels.targets import freeze_target

    runtime, _ = panel_runtime
    sessions = runtime.get_preview_service().sessions
    sessions._max_sessions = 1
    root = freeze_target(runtime, "data-a")
    first = sessions.create_session(root.target, guard=lambda: None, authority=root)
    sessions.create_session(root.target)
    assert first.session_id not in sessions._session_guards
    assert first.session_id not in sessions._session_authorities
