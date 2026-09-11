"""Panel static assets authenticate independently under default/replacement guards."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scistudio.api.app import create_app
from tests.api.fake_guard import RecordingFakeGuardFactory, authenticate_fake_session
from tests.panels.conftest import make_runtime


@pytest.fixture(params=["", "/user/alice/scistudio"])
def panel_client(request, tmp_path, monkeypatch):
    runtime, store = make_runtime(tmp_path)
    prefix = request.param
    guard = RecordingFakeGuardFactory()
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", prefix)
    app = create_app(guard=guard)
    app.state.runtime = runtime
    client = TestClient(app, base_url="http://testserver")
    authenticate_fake_session(client)
    yield client, prefix, runtime, store, guard
    client.close()


def create(client, prefix):
    response = client.post(
        prefix + "/api/panels/contexts", json={"kind": "preview", "target": {"kind": "data_ref", "ref": "data-a"}}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_assets_prefix_guard_cors_and_token_isolation(panel_client):
    client, prefix, _runtime, _store, _guard = panel_client
    context = create(client, prefix)
    assert context["entry_url"].startswith(prefix + "/api/panels/t/")
    client.cookies.clear()
    response = client.get(context["entry_url"], headers={"Origin": "null"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers
    assert "connect-src 'none'" in response.headers["content-security-policy"]
    assert "http://testserver" + prefix + "/api/panels/t/" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert (
        client.options(
            context["entry_url"], headers={"Origin": "null", "Access-Control-Request-Method": "GET"}
        ).status_code
        == 204
    )
    for url in (prefix + "/api/panels/catalog", prefix + "/api/panels/t-lookalike/x", prefix + "/api/panels/token/x"):
        assert client.get(url).status_code == 401
    for method, path, payload in (
        ("post", "/contexts", {"kind": "preview", "target": {"ref": "data-a"}}),
        ("post", f"/contexts/{context['context_id']}/read", {"ref": "data-a", "op": "metadata"}),
        ("delete", f"/contexts/{context['context_id']}", None),
    ):
        assert (
            client.request(
                method,
                prefix + "/api/panels" + path,
                json=payload,
                headers={"Authorization": "Bearer " + context["token"]},
            ).status_code
            == 401
        )
    assert client.get(context["entry_url"].replace("/assets/lab.text/", "/assets/other.panel/")).status_code == 403
    assert client.get(context["entry_url"].replace("index.html", "panel.py")).status_code == 404
    assert client.get(context["entry_url"].replace(context["token"], "invalid")).status_code == 403
    authenticate_fake_session(client)
    assert client.delete(prefix + "/api/panels/contexts/" + context["context_id"]).status_code == 204
    client.cookies.clear()
    assert client.get(context["entry_url"]).status_code == 403


def test_renew_and_guarded_read_metadata(panel_client):
    client, prefix, _, _, _ = panel_client
    context = create(client, prefix)
    renewed = client.post(prefix + "/api/panels/contexts/" + context["context_id"] + "/renew").json()
    assert renewed["token"] == context["token"]
    assert renewed["bootstrap_proof"] == context["bootstrap_proof"]
    assert renewed["expires_at"] >= context["expires_at"]
    result = client.post(
        prefix + "/api/panels/contexts/" + context["context_id"] + "/read", json={"ref": "data-a", "op": "metadata"}
    )
    assert result.status_code == 200, result.text
    assert result.json()["type_chain"] == ["DataObject", "Text"]
    assert {k: result.json()[k] for k in ("sampled", "truncated", "complete")} == {
        "sampled": False,
        "truncated": False,
        "complete": True,
    }
    rejected = client.post(
        prefix + "/api/panels/contexts/" + context["context_id"] + "/read",
        json={"ref": "another-data", "op": "metadata"},
    )
    assert rejected.status_code == 403


def test_text_and_artifact_grant_separated_from_static_token(panel_client):
    client, prefix, _, _, _ = panel_client
    context = create(client, prefix)
    url = prefix + "/api/panels/contexts/" + context["context_id"] + "/read"
    text = client.post(url, json={"ref": "data-a", "op": "text.chunk", "params": {"offset": 6, "length": 5}})
    assert text.status_code == 200, text.text
    assert text.json()["text"] == "panel"
    artifact = client.post(url, json={"ref": "data-a", "op": "artifact.file"})
    assert artifact.status_code == 200, artifact.text
    grant = artifact.json()["url"]
    assert grant.startswith(prefix + "/api/panels/t/")
    client.cookies.clear()
    assert client.get(grant).content == b"hello panel"
    grant_token = grant.split("/t/")[1].split("/")[0]
    assert grant_token != context["token"]
    assert client.get(grant.replace(grant_token, context["token"])).status_code == 403
    assert client.get(context["entry_url"].replace(context["token"], grant_token)).status_code == 403
    authenticate_fake_session(client)
    client.delete(prefix + "/api/panels/contexts/" + context["context_id"])
    client.cookies.clear()
    assert client.get(grant).status_code == 403


def test_openapi_declares_context_and_binary_read(panel_client):
    client, _prefix, *_ = panel_client
    schema = client.app.openapi()
    assert "context_id" in schema["components"]["schemas"]["ContextResponse"]["required"]
    assert "bootstrap_proof" in schema["components"]["schemas"]["ContextResponse"]["required"]
    response = schema["paths"]["/api/panels/contexts/{context_id}/read"]["post"]["responses"]["200"]
    assert "application/octet-stream" in response["content"]
    assert "X-Panel-Dtype" in response["headers"]


def test_entry_bootstrap_precedes_author_markup_and_is_document_specific(panel_client):
    client, prefix, runtime, store, _ = panel_client
    panel = runtime.get_preview_service().registry.panels.get("lab.text")
    original = (
        b'<!doctype html><meta http-equiv="refresh" content="0;url=next.html"><script>window.author=true</script>'
    )
    (panel.root / panel.entry).write_bytes(original)
    (panel.root / "next.html").write_bytes(b"<p>secondary document</p>")
    (panel.root / "module.js").write_bytes(b"export const value=1;")
    context = create(client, prefix)
    other = create(client, prefix)
    assert len(context["bootstrap_proof"]) >= 40
    assert other["bootstrap_proof"] != context["bootstrap_proof"]
    response = client.get(context["entry_url"])
    assert response.content.startswith(b"<!doctype html><script>")
    assert response.content.endswith(original)
    trusted = response.content[: -len(original)].decode()
    assert context["bootstrap_proof"] in trusted
    assert "new MessageChannel()" in trusted
    assert "ports:event.ports" in trusted and "port.close()" in trusted
    assert trusted.index("host.postMessage") < len(trusted)
    assert other["bootstrap_proof"] not in trusted
    assert client.options(context["entry_url"]).content == b""
    secondary = client.get(context["entry_url"].replace("index.html", "next.html"))
    assert secondary.content == b"<p>secondary document</p>"
    module = client.get(context["entry_url"].replace("index.html", "module.js"))
    assert module.content == b"export const value=1;"
    assert module.headers["content-type"].startswith("text/javascript")
    # Even a future proof generator with markup characters cannot end the script.
    store.contexts[context["context_id"]].bootstrap_proof = "</script><script>alert(1)</script>\u2028"
    escaped = client.get(context["entry_url"]).content[: -len(original)]
    assert escaped.count(b"</script>") == 1
    assert b"\\u003c/script\\u003e" in escaped
    assert b"\\u2028" in escaped


@pytest.mark.parametrize("entry", ["./index.html", "./views/./index.html"])
def test_canonical_entry_bootstraps_at_nested_and_prefixed_urls(panel_client, entry):
    import json
    from pathlib import PurePosixPath

    from scistudio.panels.descriptor import parse_descriptor
    from scistudio.panels.registry import PanelRegistry
    from scistudio.previewers.models import OwnerKind

    client, prefix, runtime, _, _ = panel_client
    root = runtime.get_preview_service().registry.panels.get("lab.text").root
    entry_path = root / entry
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_text("<p>entry</p>")
    manifest = json.loads((root / "panel.json").read_text())
    manifest["entry"] = entry
    (root / "panel.json").write_text(json.dumps(manifest))
    panels = PanelRegistry()
    panel, _ = parse_descriptor(root, owner_kind=OwnerKind.PROJECT, owner_name="project", registered_types={"Text"})
    panels.register(panel)
    runtime.get_preview_service().registry.install_panels(panels)
    context = create(client, prefix)
    assert context["entry_url"].endswith("/assets/lab.text/" + PurePosixPath(entry).as_posix())
    assert "/./" not in context["entry_url"]
    response = client.get(context["entry_url"])
    assert response.status_code == 200
    assert context["bootstrap_proof"] in response.text
    assert response.text.endswith("<p>entry</p>")
    assert "http://testserver" + prefix + "/api/panels/t/" in response.headers["content-security-policy"]


def test_entry_modified_after_discovery_has_bounded_source_read(panel_client, monkeypatch):
    from contextlib import contextmanager
    from pathlib import Path

    from scistudio.panels.files import MAX_SOURCE_BYTES

    client, prefix, runtime, _, _ = panel_client
    panel = runtime.get_preview_service().registry.panels.get("lab.text")
    path = panel.root / panel.entry
    context = create(client, prefix)
    with path.open("wb") as source:
        source.truncate(MAX_SOURCE_BYTES + 1)
    original_open = Path.open
    read_sizes = []

    class ObservedSource:
        def __init__(self, source):
            self.source = source

        def fileno(self):
            return self.source.fileno()

        def read(self, size=-1):
            assert 0 <= size <= MAX_SOURCE_BYTES + 1
            read_sizes.append(size)
            return self.source.read(size)

    @contextmanager
    def observed_open(self, *args, **kwargs):
        with original_open(self, *args, **kwargs) as source:
            yield ObservedSource(source) if self == path else source

    monkeypatch.setattr(Path, "open", observed_open)
    response = client.get(context["entry_url"])
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "read_budget"
    assert read_sizes == []  # Reject oversized files without materializing their bytes.
    with original_open(path, "wb") as source:
        source.write(b"<p>small again</p>")
    assert client.get(context["entry_url"]).status_code == 200
    assert read_sizes == [MAX_SOURCE_BYTES + 1]  # Concurrent growth is still capped.


def test_open_collection_child_uses_real_legacy_session_and_rejects_query_tampering(panel_client):
    from dataclasses import replace

    from scistudio.panels.registry import PanelRegistry
    from scistudio.panels.targets import register_collection

    client, prefix, runtime, store, _ = panel_client
    service = runtime.get_preview_service()
    panels = PanelRegistry()
    panels.register(replace(service.registry.panels.get("lab.text"), types=("Collection[Text]",)))
    service.registry.install_panels(panels)
    group = register_collection(runtime, {"count": 1, "item_type": "Text", "items": [{"data_ref": "data-a"}]})
    parent = store.create({"kind": "preview", "target": {"ref": group["collection_ref"]}})
    url = prefix + "/api/panels/contexts/" + parent.context_id + "/open"
    assert client.post(url, json={"ref": "unrelated"}).status_code == 403
    assert client.post(url, json={"ref": "data-a", "_storage": {"path": "/etc/passwd"}}).status_code == 422
    opened = client.post(url, json={"ref": "data-a"})
    assert opened.status_code == 200, opened.text
    envelope = opened.json()
    assert envelope["previewer_id"] == "core.text.basic"
    assert "hello panel" in opened.text
    assert "_storage" not in opened.text and str(runtime.active_project.path) not in opened.text
    session_url = prefix + "/api/previews/sessions/" + envelope["session_id"]
    client.delete(prefix + "/api/panels/contexts/" + parent.context_id)
    assert client.get(session_url).status_code == 200
    tampered = client.patch(session_url, json={"query": {"_storage": {"path": "/etc/passwd"}}})
    assert tampered.status_code == 422
    assert "hello panel" in client.get(session_url).text
    runtime.data_catalog["data-a"].metadata["changed"] = True
    assert client.get(session_url).status_code == 404
    assert envelope["session_id"] not in service.sessions._session_guards


def test_composite_child_panel_maximizes_independently_after_parent_close(panel_client, tmp_path):
    from dataclasses import replace

    import pyarrow as pa

    from scistudio.api.runtime.models import DataRecord
    from scistudio.core.storage.composite_store import CompositeStore
    from scistudio.core.storage.ref import StorageReference
    from scistudio.panels.registry import PanelRegistry

    client, prefix, runtime, store, _ = panel_client
    storage = CompositeStore().write(
        {"index": ("arrow", pa.table({"a": [1, 2]}))},
        StorageReference(backend="composite", path=str(tmp_path / "composite")),
    )
    runtime.data_catalog["comp"] = DataRecord(
        "comp", storage, "Composite", {"slots": {"index": "DataFrame"}}, ["DataObject", "Composite"]
    )
    panels = PanelRegistry()
    panels.register(
        replace(runtime.get_preview_service().registry.panels.get("lab.text"), types=("Composite", "DataFrame"))
    )
    runtime.get_preview_service().registry.install_panels(panels)
    parent = store.create({"kind": "preview", "target": {"ref": "comp"}})
    opened = client.post(prefix + "/api/panels/contexts/" + parent.context_id + "/open", json={"ref": "comp#index"})
    assert opened.status_code == 200, opened.text
    envelope = opened.json()
    assert envelope["kind"] == "panel"
    client.delete(prefix + "/api/panels/contexts/" + parent.context_id)
    independent = client.post(
        prefix + "/api/panels/contexts",
        json={"kind": "preview", "target": {"ref": "comp#index"}, "preview_session_id": envelope["session_id"]},
    )
    assert independent.status_code == 200, independent.text
    child_id = independent.json()["context_id"]
    read = client.post(
        prefix + "/api/panels/contexts/" + child_id + "/read", json={"ref": "comp#index", "op": "table.page"}
    )
    assert read.status_code == 200 and read.json()["total_rows"] == 2
    # The independent mount still tracks its catalog ancestor, not just slot bytes.
    runtime.data_catalog["comp"].metadata["changed"] = True
    assert (
        client.post(
            prefix + "/api/panels/contexts/" + child_id + "/read", json={"ref": "comp#index", "op": "metadata"}
        ).status_code
        == 409
    )


def test_numeric_binary_metadata_and_byte_order(panel_client, tmp_path):
    import json
    from dataclasses import replace

    import numpy as np

    from scistudio.api.runtime.models import DataRecord
    from scistudio.core.storage.ref import StorageReference
    from scistudio.panels.registry import PanelRegistry

    client, prefix, runtime, _store, _guard = panel_client
    data = np.arange(3 * 4, dtype=">i4").reshape(3, 4)
    import zarr

    path = tmp_path / "array.zarr"
    zarr.save_array(str(path), data)
    runtime.data_catalog["array"] = DataRecord(
        "array",
        StorageReference(backend="zarr", path=str(path)),
        "Array",
        {"shape": [3, 4], "dtype": ">i4"},
        ["DataObject", "Array"],
    )
    panels = PanelRegistry()
    panels.register(replace(runtime.get_preview_service().registry.panels.get("lab.text"), types=("Array",)))
    runtime.get_preview_service().registry.install_panels(panels)
    created = client.post(prefix + "/api/panels/contexts", json={"kind": "preview", "target": {"ref": "array"}})
    assert created.status_code == 200, created.text
    url = prefix + "/api/panels/contexts/" + created.json()["context_id"] + "/read"
    response = client.post(url, json={"ref": "array", "op": "array.plane", "params": {"format": "binary"}})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["x-panel-dtype"] == "<i4"
    shape = json.loads(response.headers["x-panel-shape"])
    assert np.array_equal(np.frombuffer(response.content, dtype="<i4").reshape(shape), data)
    flags = json.loads(response.headers["x-panel-metadata"])
    assert flags["complete"] and not flags["sampled"]
    invalid = client.post(
        url, json={"ref": "array", "op": "array.plane", "params": {"_storage": {"path": "/etc/passwd"}}}
    )
    assert invalid.status_code == 422


def test_reads_execute_off_event_loop(panel_client, monkeypatch):
    import threading

    from scistudio.panels import reads

    client, prefix, *_ = panel_client
    context = create(client, prefix)
    original = reads.read_access
    called = []

    def checked_access():
        called.append(threading.current_thread().name)
        import asyncio

        with pytest.raises(RuntimeError):
            asyncio.get_running_loop()
        return original()

    monkeypatch.setattr(reads, "read_access", checked_access)
    response = client.post(
        prefix + "/api/panels/contexts/" + context["context_id"] + "/read", json={"ref": "data-a", "op": "metadata"}
    )
    assert response.status_code == 200 and called


def test_lifespan_unsubscribes_original_bus_after_runtime_replacement(tmp_path):
    import asyncio
    from types import SimpleNamespace

    from scistudio.api.routes.panels import panels_lifespan
    from scistudio.panels.contexts import PANEL_EVENTS

    runtime, store = make_runtime(tmp_path)
    original_bus = runtime.event_bus
    app = SimpleNamespace(state=SimpleNamespace(runtime=runtime))
    async def replace_bus():
        async with panels_lifespan(app):
            assert all(store.on_event in original_bus._subscribers[event] for event in PANEL_EVENTS)
            runtime.event_bus = SimpleNamespace()  # A runtime recorder need not implement unsubscribe.

    asyncio.run(replace_bus())
    assert all(store.on_event not in original_bus._subscribers[event] for event in PANEL_EVENTS)
