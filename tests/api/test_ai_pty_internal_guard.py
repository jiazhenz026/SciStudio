"""AI Block worker callbacks under a replacement guard (ADR-055 identity seam, #2322).

An AI Block worker subprocess calls back into the backend at
``/api/ai/pty/internal/*`` (``request-tab``, ``notify``) with the engine IPC
token and no browser session. A replacement guard, such as the enterprise Hub
guard, would refuse those calls, so ai_pty registers the prefix as
self-authenticating (seam FR-007 to FR-011) and every route under it checks the
IPC token itself.

Covered at the root mount and under ``/user/alice/scistudio``, under the
default guard and under the test-only fake replacement guard:

* every route under the prefix refuses a request without a valid IPC token,
  with its own 401, never the guard's;
* a callback carrying the token reaches its route;
* the prefix is matched on segment boundaries, and the rest of ``/api/ai``
  stays behind the replacement guard.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from scistudio.api import app as app_module
from scistudio.api.app import create_app
from scistudio.api.routes.ai_pty.internal_routes import INTERNAL_ROUTE_PREFIX
from scistudio.api.seam import is_self_authenticating_path, self_authenticating_prefixes
from tests.api.fake_guard import FAKE_REJECTION, FakeCookieGuard
from tests.api.seam_contract import PREFIXED_MOUNT

MOUNTS = pytest.mark.parametrize("mount_prefix", ["", PREFIXED_MOUNT], ids=["root-mount", "prefixed-mount"])
GUARDS = pytest.mark.parametrize("replacement", [False, True], ids=["default-guard", "replacement-guard"])
IPC_HEADER = "X-SciStudio-IPC-Token"
IPC_REJECTION = {"detail": "invalid SciStudio IPC token"}


@pytest.fixture()
def backend_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated home; returns a directory a request-tab spec may name."""
    from scistudio.api import runtime as runtime_module

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("SCISTUDIO_ROOT_PATH", raising=False)
    monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: None)
    project = tmp_path / "project"
    project.mkdir()
    return project


def _app(*, replacement: bool) -> FastAPI:
    return create_app(guard=FakeCookieGuard) if replacement else create_app()


def _internal_route_paths(app: FastAPI) -> list[str]:
    return sorted(
        path
        for path in (getattr(route, "path", "") for route in app.routes)
        if path.startswith(INTERNAL_ROUTE_PREFIX.rstrip("/") + "/")
    )


def _notify_body() -> dict[str, Any]:
    return {"type": "notify_block_pty_event", "block_run_id": "block-run-1", "event": "completed"}


def test_internal_prefix_is_registered_on_segment_boundaries() -> None:
    assert INTERNAL_ROUTE_PREFIX == "/api/ai/pty/internal"
    assert INTERNAL_ROUTE_PREFIX in self_authenticating_prefixes()
    assert is_self_authenticating_path("/api/ai/pty/internal/request-tab")
    assert is_self_authenticating_path("/api/ai/pty/internal/notify")
    assert not is_self_authenticating_path("/api/ai/pty/internalx/notify")
    assert not is_self_authenticating_path("/api/ai/pty/tab-1")
    assert not is_self_authenticating_path("/api/ai/status")


@MOUNTS
@GUARDS
def test_every_internal_route_refuses_a_request_without_the_ipc_token(
    backend_env: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str, replacement: bool
) -> None:
    """The registry grants no access: each route under the prefix checks the token itself."""
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    app = _app(replacement=replacement)
    with TestClient(app, root_path=mount_prefix) as client:
        paths = _internal_route_paths(app)
        assert paths == ["/api/ai/pty/internal/notify", "/api/ai/pty/internal/request-tab"]
        for path in paths:
            for headers in ({}, {IPC_HEADER: "not-the-token"}):
                response = client.post(f"{mount_prefix}{path}", json={}, headers=headers)
                assert response.status_code == 401, (path, headers)
                # The route's own refusal, never the guard's.
                assert response.json() == IPC_REJECTION, (path, headers)


@MOUNTS
@GUARDS
def test_a_worker_callback_with_the_ipc_token_reaches_its_route(
    backend_env: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str, replacement: bool
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    with TestClient(_app(replacement=replacement), root_path=mount_prefix) as client:
        headers = {IPC_HEADER: os.environ["SCISTUDIO_ENGINE_IPC_TOKEN"]}
        notify = client.post(f"{mount_prefix}/api/ai/pty/internal/notify", json=_notify_body(), headers=headers)
        assert notify.status_code == 204
        # An unknown provider is refused by the route itself, so nothing spawns.
        request_tab = client.post(
            f"{mount_prefix}/api/ai/pty/internal/request-tab",
            json={"type": "request_pty_tab", "spec": {"provider": "no-such-provider", "cwd": str(backend_env)}},
            headers=headers,
        )
    assert request_tab.status_code == 200
    body = request_tab.json()
    assert body["tab_id"] is None
    assert "unknown provider" in body["error"]


@MOUNTS
def test_the_rest_of_ai_pty_stays_behind_the_replacement_guard(
    backend_env: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    with TestClient(_app(replacement=True), root_path=mount_prefix) as client:
        headers = {IPC_HEADER: os.environ["SCISTUDIO_ENGINE_IPC_TOKEN"]}
        for method, path in (("GET", "/api/ai/status"), ("POST", "/api/ai/pty/internalx/notify")):
            response = client.request(method, f"{mount_prefix}{path}", headers=headers)
            assert response.status_code == 401, path
            assert response.json() == {"detail": FAKE_REJECTION}, path
        # The user-launched PTY WebSocket is refused at the handshake.
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(f"{mount_prefix}/api/ai/pty/tab-1?provider=user-terminal") as websocket,
        ):
            websocket.receive_json()
