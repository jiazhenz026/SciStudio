"""Panel static assets authenticate independently under default/replacement guards."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scistudio.api.app import create_app
from tests.api.fake_guard import RecordingFakeGuardFactory, authenticate_fake_session
from tests.panels.conftest import make_runtime, use_panels


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
    assert {k: result.json()[k] for k in ("truncated", "complete")} == {"truncated": False, "complete": True}
    assert "sampled" not in result.json()
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
    panel = runtime.get_panel_service().panel("lab.text")
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
    root = runtime.get_panel_service().panel("lab.text").root
    entry_path = root / entry
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_text("<p>entry</p>")
    manifest = json.loads((root / "panel.json").read_text())
    manifest["entry"] = entry
    (root / "panel.json").write_text(json.dumps(manifest))
    panels = PanelRegistry()
    panel, _ = parse_descriptor(root, owner_kind=OwnerKind.PROJECT, owner_name="project", registered_types={"Text"})
    panels.register(panel)
    use_panels(runtime, panels)
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
    panel = runtime.get_panel_service().panel("lab.text")
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
    service = runtime.get_panel_service()
    panels = PanelRegistry()
    panels.register(replace(service.panel("lab.text"), types=("Collection[Text]",)))
    use_panels(runtime, panels)
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
    assert envelope["session_id"] not in service.legacy.sessions._session_guards


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
    panels.register(replace(runtime.get_panel_service().panel("lab.text"), types=("Composite", "DataFrame")))
    use_panels(runtime, panels)
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
    panels.register(replace(runtime.get_panel_service().panel("lab.text"), types=("Array",)))
    use_panels(runtime, panels)
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
    assert flags["complete"] and "sampled" not in flags
    invalid = client.post(
        url, json={"ref": "array", "op": "array.plane", "params": {"_storage": {"path": "/etc/passwd"}}}
    )
    assert invalid.status_code == 422


def test_series_points_route_pages_exact_rows(panel_client, tmp_path):
    """#2460: series.points pages every exact row; nothing is decimated or dropped."""
    from dataclasses import replace

    import pyarrow as pa
    import pyarrow.parquet as pq

    from scistudio.api.runtime.models import DataRecord
    from scistudio.core.storage.ref import StorageReference
    from scistudio.panels.registry import PanelRegistry

    client, prefix, runtime, _store, _guard = panel_client
    values = [float(i) for i in range(5)]
    values[2] = float("nan")
    path = tmp_path / "series.parquet"
    pq.write_table(pa.table({"t": [0.5 * i for i in range(5)], "v": values}), path)
    runtime.data_catalog["series"] = DataRecord(
        "series",
        StorageReference(backend="arrow", path=str(path)),
        "Series",
        {"index_name": "t", "value_name": "v"},
        ["DataObject", "Series"],
    )
    panels = PanelRegistry()
    panels.register(replace(runtime.get_panel_service().panel("lab.text"), types=("Series",)))
    use_panels(runtime, panels)
    created = client.post(prefix + "/api/panels/contexts", json={"kind": "preview", "target": {"ref": "series"}})
    assert created.status_code == 200, created.text
    url = prefix + "/api/panels/contexts/" + created.json()["context_id"] + "/read"
    index, ys, offset = [], [], 0
    while offset is not None:
        page = client.post(url, json={"ref": "series", "op": "series.points", "params": {"offset": offset, "limit": 2}})
        assert page.status_code == 200, page.text
        body = page.json()
        assert body["offset"] == offset and body["total"] == 5
        assert body["truncated"] is (body["next_offset"] is not None)
        index += body["index"]
        ys += body["values"]
        offset = body["next_offset"]
    assert index == [0.0, 0.5, 1.0, 1.5, 2.0]
    assert ys == [0.0, 1.0, "NaN", 3.0, 4.0]
    refused = client.post(url, json={"ref": "series", "op": "series.points", "params": {"max_points": 10}})
    assert refused.status_code == 422


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


@pytest.mark.parametrize("user_contexts,user_types", [(["preview", "interactive"], ["Text"]), (["interactive"], [])])
def test_preview_catalog_includes_shadowed_panel_metadata(panel_client, tmp_path, user_contexts, user_types):
    from scistudio.panels.registry import PanelRegistry
    from scistudio.previewers.models import OwnerKind
    from tests.panels.test_panel_registry import folder

    client, prefix, runtime, _, _ = panel_client
    project = folder(tmp_path / "project", "lab.shaded", priority=5, types=["Text", "Collection[Text]"])
    user = folder(tmp_path / "user", "lab.shaded", priority=99, contexts=user_contexts, types=user_types)
    panels = PanelRegistry()
    panels.load(project, OwnerKind.PROJECT, {"Text"}, "active project")
    panels.load(user, OwnerKind.USER, {"Text"}, "user library")
    use_panels(runtime, panels)
    response = client.get(prefix + "/api/previews/previewers")
    assert response.status_code == 200, response.text
    cards = [card for card in response.json()["previewers"] if card["previewer_id"] == "lab.shaded"]
    assert [(card["owner_kind"], card["shadowed"]) for card in cards] == [("project", False), ("user", True)]
    assert all(card["renderer"] == "panel" for card in cards)
    assert cards[0]["panel"]["types"] == ["Text", "Collection[Text]"]
    assert cards[1]["panel"]["types"] == user_types
    assert cards[1]["panel"]["contexts"] == user_contexts
    assert cards[1]["priority"] == cards[1]["panel"]["priority"] == 99
    assert cards[1]["owner_name"] == "user library"
    assert cards[1]["target_type"] == ("Text" if "preview" in user_contexts else "")
    context = create(client, prefix)
    assert context["panel"]["id"] == "lab.shaded"
    assert runtime.get_panel_service().previewer("lab.shaded").owner_kind is OwnerKind.PROJECT


def test_shared_renderer_assets_are_served_under_context_authority(panel_client):
    client, prefix, _runtime, _store, _guard = panel_client
    context = create(client, prefix)
    sdk = context["sdk_url"].rsplit("/", 1)[0]
    client.cookies.clear()
    for name in (
        "renderers.js",
        "renderers.css",
        "renderer-array.js",
        "renderer-dataframe.js",
        "renderer-series.js",
        "renderer-text.js",
        "renderer-artifact.js",
        "renderer-plot.js",
        "renderer-collection.js",
        "renderer-composite.js",
        "renderer-base.js",
    ):
        response = client.get(f"{sdk}/{name}", headers={"Origin": "null"})
        assert response.status_code == 200, name
        assert response.headers["access-control-allow-origin"] == "*"
        assert client.get(f"{sdk}/{name}".replace(context["token"], "invalid")).status_code == 403
    assert client.get(f"{sdk}/renderer-unreviewed.js").status_code == 404
    authenticate_fake_session(client)
    client.delete(prefix + "/api/panels/contexts/" + context["context_id"])
    client.cookies.clear()
    assert client.get(f"{sdk}/renderers.js").status_code == 403


def test_composite_slots_page_past_the_item_budget(panel_client, tmp_path, monkeypatch):
    """#2460: a composite with more slots than one read carries is paged, not refused."""
    from dataclasses import replace

    import pyarrow as pa

    from scistudio.api.runtime.models import DataRecord
    from scistudio.core.storage.composite_store import CompositeStore
    from scistudio.core.storage.ref import StorageReference
    from scistudio.panels import contexts
    from scistudio.panels.registry import PanelRegistry

    monkeypatch.setattr(contexts, "READ_ITEMS", 2)
    client, prefix, runtime, store, _ = panel_client
    names = [f"s{i}" for i in range(5)]
    storage = CompositeStore().write(
        {name: ("arrow", pa.table({"a": [i]})) for i, name in enumerate(names)},
        StorageReference(backend="composite", path=str(tmp_path / "composite")),
    )
    runtime.data_catalog["comp"] = DataRecord(
        "comp", storage, "Composite", {"slots": dict.fromkeys(names, "DataFrame")}, ["DataObject", "Composite"]
    )
    panels = PanelRegistry()
    panels.register(replace(runtime.get_panel_service().panel("lab.text"), types=("Composite", "DataFrame")))
    use_panels(runtime, panels)
    context = store.create({"kind": "preview", "target": {"ref": "comp"}})
    url = prefix + "/api/panels/contexts/" + context.context_id + "/read"
    seen, cursor = [], None
    while True:
        params = {"cursor": cursor} if cursor else {}
        page = client.post(url, json={"ref": "comp", "op": "composite.slots", "params": params})
        assert page.status_code == 200, page.text
        body = page.json()
        assert len(body["slots"]) <= 2 and body["count"] == 5
        assert body["truncated"] is (body["next_cursor"] is not None)
        seen += [slot["name"] for slot in body["slots"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == names
    # A slot on the last page is authorized before any page listed it.
    fresh = store.create({"kind": "preview", "target": {"ref": "comp"}})
    last = client.post(
        prefix + "/api/panels/contexts/" + fresh.context_id + "/read", json={"ref": "comp#s4", "op": "table.page"}
    )
    assert last.status_code == 200, last.text
    assert last.json()["rows"] == [{"a": 4}]


def test_save_writes_bytes_to_the_dialog_chosen_path(panel_client, tmp_path):
    client, prefix, _, _, _ = panel_client
    context = create(client, prefix)
    destination = tmp_path / "figure.png"
    url = f"{prefix}/api/panels/contexts/{context['context_id']}/save"

    response = client.post(url, params={"path": str(destination)}, content=b"\x89PNG-bytes")

    assert response.status_code == 200, response.text
    assert response.json() == {"saved": True, "destination": "file", "path": str(destination.resolve())}
    assert destination.read_bytes() == b"\x89PNG-bytes"
    assert not list(tmp_path.glob(".*.partial"))


def test_save_refuses_relative_paths_and_missing_parents(panel_client, tmp_path):
    client, prefix, _, _, _ = panel_client
    context = create(client, prefix)
    url = f"{prefix}/api/panels/contexts/{context['context_id']}/save"

    assert client.post(url, params={"path": "figure.png"}, content=b"x").status_code == 400
    missing = tmp_path / "nowhere" / "figure.png"
    assert client.post(url, params={"path": str(missing)}, content=b"x").status_code == 400
    assert client.post(url, params={"path": str(tmp_path)}, content=b"x").status_code == 400
    assert (
        client.post(
            f"{prefix}/api/panels/contexts/pc-unknown/save", params={"path": str(tmp_path / "a")}, content=b"x"
        ).status_code
        == 404
    )
