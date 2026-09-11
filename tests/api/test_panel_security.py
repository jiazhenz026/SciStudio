"""ADR-054 global refusal must survive edition guards and mount prefixes."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import Response

from scistudio.api.app import create_app
from scistudio.api.seam import register_self_authenticating_prefix, unregister_self_authenticating_prefix
from tests.api.fake_guard import RecordingFakeGuardFactory, authenticate_fake_session


@pytest.fixture(autouse=True)
def isolated_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCISTUDIO_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("SCISTUDIO_ROOT_PATH", raising=False)
    monkeypatch.setattr("scistudio.api.app._resolve_spa_static_dir", lambda: None)


@pytest.mark.parametrize("setting", ["*", "null", "https://example.org, *", "null, https://example.org", " NULL "])
def test_unsafe_global_cors_refused(monkeypatch: pytest.MonkeyPatch, setting: str) -> None:
    monkeypatch.setenv("SCISTUDIO_CORS_ORIGINS", setting)
    with pytest.raises(ValueError, match="SCISTUDIO_CORS_ORIGINS"):
        create_app()


@pytest.mark.parametrize("prefix", ["", "/user/alice/scistudio"])
@pytest.mark.parametrize("replacement", [False, True])
def test_opaque_mutations_refused_on_every_route(
    monkeypatch: pytest.MonkeyPatch, prefix: str, replacement: bool
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", prefix)
    factory = RecordingFakeGuardFactory()
    router = APIRouter()
    seen = []

    def mutate() -> dict[str, bool]:
        seen.append(True)
        return {"ok": True}

    paths = ["/edition/action", "/api/security-fixture/t/token/action"]
    for path in paths:
        router.add_api_route(path, mutate, methods=["POST", "PUT", "PATCH", "DELETE"])
    registered = register_self_authenticating_prefix("/api/security-fixture/t/")
    try:
        app = create_app(guard=factory if replacement else None, routers=[router])
        client = TestClient(app)
        # Includes unknown paths, protected builtins and static panel token paths.
        for path in [*paths, "/api/workflows", "/api/webmcp/tools", "/api/panels/t/token/assets/a/index.html"]:
            for method in ["POST", "PUT", "PATCH", "DELETE"]:
                response = client.request(method, prefix + path, headers={"Origin": "null"})
                assert response.status_code == 403
                assert "Opaque Origin null" in response.json()["detail"]
                assert "access-control-allow-origin" not in response.headers
        assert not seen
        assert not factory.seen_route_paths
        if replacement:
            authenticate_fake_session(client)
        for origin in [None, "http://testserver", "http://localhost:5173"]:
            headers = {} if origin is None else {"Origin": origin}
            assert client.post(prefix + paths[0], headers=headers).status_code == 200
        assert len(seen) == 3
        # Opaque writes remain refused even when a legitimate session is present.
        assert client.post(prefix + paths[0], headers={"Origin": "null"}).status_code == 403
        # Duplicate Origin values cannot hide an opaque origin behind a trusted one.
        assert (
            client.post(
                prefix + paths[0], headers=[("Origin", "http://localhost:5173"), ("Origin", "null")]
            ).status_code
            == 403
        )
    finally:
        unregister_self_authenticating_prefix(registered)


@pytest.mark.parametrize("prefix", ["", "/user/alice/scistudio"])
def test_cors_is_explicit_and_get_options_unchanged(monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", prefix)
    monkeypatch.setenv("SCISTUDIO_CORS_ORIGINS", "https://trusted.example")
    router = APIRouter()

    @router.get("/api/security-fixture/t/module.js")
    def module() -> dict[str, bool]:
        return {"ok": True}

    @router.options("/api/security-fixture/t/module.js")
    def preflight() -> dict[str, bool]:
        return {"ok": True}

    registered = register_self_authenticating_prefix("/api/security-fixture/t/")
    try:
        client = TestClient(create_app(guard=RecordingFakeGuardFactory(), routers=[router]))
        url = prefix + "/api/security-fixture/t/module.js"
        for method in ["GET", "OPTIONS"]:
            assert client.request(method, url, headers={"Origin": "null"}).status_code == 200
        response = client.get(prefix + "/api/version", headers={"Origin": "https://trusted.example"})
        assert response.status_code == 401
        assert response.headers["access-control-allow-origin"] == "https://trusted.example"
        response = client.get(prefix + "/api/version", headers={"Origin": "null"})
        assert response.status_code == 401
        assert "access-control-allow-origin" not in response.headers
    finally:
        unregister_self_authenticating_prefix(registered)


@pytest.mark.parametrize("prefix", ["", "/user/alice/scistudio"])
def test_token_preflight_reaches_authentication_not_global_cors(prefix: str) -> None:
    from scistudio.panels.security import PanelCORSMiddleware

    app = FastAPI(root_path=prefix)
    app.add_middleware(PanelCORSMiddleware, allow_origins=["https://trusted.example"])

    @app.api_route("/api/panels/t/{token}/file.js", methods=["GET", "OPTIONS"])
    def token_asset(token: str, request: Request) -> Response:
        if token != "valid-token":
            return Response(status_code=401)
        return Response(
            status_code=204 if request.method == "OPTIONS" else 200,
            headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS"},
        )

    @app.options("/api/panels/tx/{token}/file.js")
    def lookalike(token: str) -> Response:
        return Response(status_code=204)

    client = TestClient(app)
    headers = {"Origin": "null", "Access-Control-Request-Method": "GET"}
    response = client.options(prefix + "/api/panels/t/valid-token/file.js", headers=headers)
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers
    response = client.options(prefix + "/api/panels/t/invalid-token/file.js", headers=headers)
    assert response.status_code == 401
    assert "access-control-allow-origin" not in response.headers
    assert client.options(prefix + "/api/panels/tx/valid-token/file.js", headers=headers).status_code == 400


@pytest.mark.parametrize("prefix", ["", "/user/alice/scistudio"])
@pytest.mark.parametrize("replacement", [False, True])
def test_real_mounted_panel_routes_and_lifecycle(
    tmp_path, monkeypatch: pytest.MonkeyPatch, prefix: str, replacement: bool
) -> None:
    import asyncio
    import json
    from pathlib import Path

    from scistudio.core.dropins import panel_scan_dirs
    from scistudio.engine.events import EngineEvent

    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", prefix)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("scistudio.api.runtime.Path.home", classmethod(lambda cls: home))
    factory = RecordingFakeGuardFactory()
    app = create_app(guard=factory if replacement else None)
    with TestClient(app) as client:
        if replacement:
            authenticate_fake_session(client)
        created = client.post(prefix + "/api/projects/", json={"name": "Panel security", "path": str(tmp_path)})
        assert created.status_code == 200, created.text
        project = Path(created.json()["path"])
        directory = panel_scan_dirs(project)[0] / "lab.security"
        directory.mkdir(parents=True)
        (directory / "panel.json").write_text(
            json.dumps(
                {
                    "id": "lab.security",
                    "api_version": "1.0",
                    "contexts": ["preview"],
                    "types": ["Text"],
                }
            )
        )
        (directory / "index.html").write_text("<!doctype html><p>Scientific text</p>")
        (project / "data" / "security.txt").write_text("real authorized data")
        app.state.runtime.refresh_preview_service()
        registered = client.post(prefix + "/api/data/register-path", json={"path": "data/security.txt"})
        assert registered.status_code == 200, registered.text
        ref = registered.json()["ref"]
        payload = {"kind": "preview", "panel_id": "lab.security", "target": {"kind": "data_ref", "ref": ref}}
        response = client.post(prefix + "/api/panels/contexts", json=payload)
        assert response.status_code == 200, response.text
        context = response.json()
        assert context["entry_url"].startswith(prefix + "/api/panels/t/")
        assert context["entry_url"].count(prefix) == 1 if prefix else True
        read_url = prefix + "/api/panels/contexts/" + context["context_id"] + "/read"
        body = {"ref": ref, "op": "text.chunk", "params": {}}
        assert client.post(read_url, json=body).status_code == 200
        assert client.post(read_url, json=body, headers={"Origin": "null"}).status_code == 403
        client.cookies.clear()
        preflight = client.options(
            context["entry_url"],
            headers={
                "Origin": "null",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code == 204, preflight.text
        assert preflight.headers["access-control-allow-origin"] == "*"
        asset = client.get(context["entry_url"], headers={"Origin": "null"})
        assert asset.status_code == 200
        assert "Scientific text" in asset.text
        assert asset.headers["referrer-policy"] == "no-referrer"
        assert "access-control-allow-credentials" not in asset.headers
        if replacement:
            assert (
                client.post(read_url, json=body, headers={"Authorization": "Bearer " + context["token"]}).status_code
                == 401
            )
            assert client.get(prefix + "/api/panels/catalog").status_code == 401
            assert client.get(prefix + "/api/panels/tx/" + context["token"]).status_code == 401
            authenticate_fake_session(client)
        assert client.delete(prefix + "/api/panels/contexts/" + context["context_id"]).status_code == 204
        assert client.get(context["entry_url"]).status_code in (403, 404)
        # Keep a real context alive until lifespan exits, then prove revocation
        # and that an emitted prompt cannot repopulate an unsubscribed store.
        assert client.post(prefix + "/api/panels/contexts", json=payload).status_code == 200
        store = app.state.runtime._panel_contexts
        bus = app.state.runtime.event_bus
        assert store.contexts
    assert not store.contexts and not store.prompts
    asyncio.run(bus.emit(EngineEvent(event_type="interactive_prompt", block_id="b", data={"workflow_id": "w"})))
    assert not store.prompts
