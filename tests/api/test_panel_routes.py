"""Panel static assets authenticate independently under default/replacement guards."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scistudio.api.app import create_app
from scistudio.api.routes.panels import router
from scistudio.api.seam import register_self_authenticating_prefix
from tests.api.fake_guard import RecordingFakeGuardFactory, authenticate_fake_session
from tests.panels.conftest import make_runtime


@pytest.fixture(params=["", "/user/alice/scistudio"])
def panel_client(request, tmp_path, monkeypatch):
    runtime, store = make_runtime(tmp_path)
    prefix = request.param
    guard = RecordingFakeGuardFactory()
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", prefix)
    register_self_authenticating_prefix("/api/panels/t/")
    app = create_app(guard=guard, routers=[router])
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
    response = schema["paths"]["/api/panels/contexts/{context_id}/read"]["post"]["responses"]["200"]
    assert "application/octet-stream" in response["content"]
    assert "X-Panel-Dtype" in response["headers"]


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
