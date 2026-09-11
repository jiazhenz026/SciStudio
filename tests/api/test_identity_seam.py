"""ADR-055 identity seam tests (``docs/specs/adr-055-identity-seam.md`` §4.4).

Covers:

* the guard contract (``tests/api/seam_contract.py``) for the test-only fake
  guard, at the root mount and under a mount prefix;
* default behavior unchanged: ``create_app()`` with no arguments is the
  open-source backend as before — the loopback token on ``/api/webmcp/*``,
  every other route open, no hooks, every capability off, no declaration in
  the served page;
* the self-authenticating bypass, enforced for the default guard as well and
  never reaching a replacement guard, plus the registry's validation and
  segment-boundary matching;
* lifespan hooks: order, access to the runtime, background-task teardown,
  and a startup check that fails;
* capabilities: validation, the served declaration, script safety;
* edition routers, argument validation, ``workflow_runs_active``, and the
  republished MCP registry.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from scistudio.api import app as app_module
from scistudio.api import seam
from scistudio.api.app import create_app
from scistudio.api.routes.webmcp import LoopbackTokenBackend, WebMCPSessionMiddleware
from scistudio.api.seam import (
    Capabilities,
    GuardContext,
    GuardDispatchMiddleware,
    IdentityCapability,
    TransferCapability,
    is_self_authenticating_path,
    register_self_authenticating_prefix,
    self_authenticating_prefixes,
    unregister_self_authenticating_prefix,
    workflow_runs_active,
)
from scistudio.stability import get_stability
from tests.api.fake_guard import FakeCookieGuard, RecordingFakeGuardFactory, authenticate_fake_session
from tests.api.seam_contract import PREFIXED_MOUNT, GuardCase, GuardContractSuite

TOKEN_HEADER = "X-SciStudio-WebMCP-Token"
SELF_AUTH_UNDER_BRIDGE = "/api/webmcp/seam-fixture"
FIXTURE_REJECTION = "fixture route rejected the token"
MOUNTS = pytest.mark.parametrize("mount_prefix", ["", PREFIXED_MOUNT], ids=["root-mount", "prefixed-mount"])


# ---------------------------------------------------------------------------
# Fixtures and helpers.
# ---------------------------------------------------------------------------


@pytest.fixture()
def seam_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated home and a built application shell for apps a test creates."""
    from scistudio.api import runtime as runtime_module

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("SCISTUDIO_ROOT_PATH", raising=False)
    spa_dir = tmp_path / "static"
    spa_dir.mkdir()
    (spa_dir / "index.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: spa_dir)
    return spa_dir


@pytest.fixture()
def registry_snapshot() -> Iterator[None]:
    """Unregister any prefix a test registers, so the global registry is restored."""
    before = self_authenticating_prefixes()
    yield
    for prefix in self_authenticating_prefixes():
        if prefix not in before:
            unregister_self_authenticating_prefix(prefix)


def _bridge_fixture_router() -> APIRouter:
    """A self-authenticating fixture route under the loopback guard's own scope."""
    router = APIRouter()

    @router.get(SELF_AUTH_UNDER_BRIDGE + "/{token}")
    async def fixture(token: str) -> dict[str, bool]:
        if token != "good":
            raise HTTPException(status_code=403, detail=FIXTURE_REJECTION)
        return {"ok": True}

    return router


def _declared_capabilities(shell: str) -> Any:
    match = re.search(r"window\.__SCISTUDIO_CAPABILITIES__ = (.*?);</script>", shell)
    assert match is not None, "the served page carries no capability declaration"
    return json.loads(match.group(1))


async def _noop_app(scope: Scope, receive: Receive, send: Send) -> None:
    return None


# ---------------------------------------------------------------------------
# Decision 2e: the guard contract, for the test-only fake guard.
# ---------------------------------------------------------------------------


class TestFakeGuardContract(GuardContractSuite):
    @pytest.fixture()
    def guard_case(self) -> GuardCase:
        return GuardCase(name="fake-cookie", guard=FakeCookieGuard, authenticate=authenticate_fake_session)


# ---------------------------------------------------------------------------
# Default behavior unchanged.
# ---------------------------------------------------------------------------


@MOUNTS
def test_default_app_is_the_open_source_backend_unchanged(
    seam_env: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    app = create_app()
    token = app.state.webmcp_session_token
    assert token
    assert app.state.capabilities == Capabilities()
    assert app.state.lifespan_hooks == ()
    with TestClient(app, root_path=mount_prefix) as client:
        # Every route outside the bridge stays open, WebSocket included.
        assert client.get(f"{mount_prefix}/api/version").status_code == 200
        assert client.get(f"{mount_prefix}/version").status_code == 200
        with client.websocket_connect(f"{mount_prefix}/ws") as websocket:
            websocket.send_text('{"type": "ping"}')
        # The bridge still requires the per-launch loopback token.
        assert client.get(f"{mount_prefix}/api/webmcp/tools").status_code == 401
        assert client.get(f"{mount_prefix}/api/webmcp/tools", headers={TOKEN_HEADER: token}).status_code == 200
        shell = client.get(f"{mount_prefix}/")
        assert shell.status_code == 200
        assert f"window.__SCISTUDIO_WEBMCP_TOKEN__ = {json.dumps(token)};" in shell.text
        assert "__SCISTUDIO_CAPABILITIES__" not in shell.text


def test_default_guard_is_the_loopback_middleware(seam_env: Path) -> None:
    app = create_app()
    guards = [m for m in app.user_middleware if m.cls is GuardDispatchMiddleware]
    assert len(guards) == 1, "exactly one guard slot"
    assert not [m for m in app.user_middleware if m.cls is WebMCPSessionMiddleware]
    built = guards[0].kwargs["guard"](_noop_app, GuardContext(root_path=""))
    assert isinstance(built, WebMCPSessionMiddleware)


# ---------------------------------------------------------------------------
# Decision 2c: self-authenticating prefixes.
# ---------------------------------------------------------------------------


@MOUNTS
def test_default_guard_honors_self_authenticating_prefixes(
    seam_env: Path, monkeypatch: pytest.MonkeyPatch, registry_snapshot: None, mount_prefix: str
) -> None:
    """A registered prefix inside /api/webmcp/* reaches its route without the loopback token."""
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    register_self_authenticating_prefix(SELF_AUTH_UNDER_BRIDGE)
    app = create_app(routers=[_bridge_fixture_router()])
    with TestClient(app, root_path=mount_prefix) as client:
        assert client.get(f"{mount_prefix}{SELF_AUTH_UNDER_BRIDGE}/good").json() == {"ok": True}
        own = client.get(f"{mount_prefix}{SELF_AUTH_UNDER_BRIDGE}/bad")
        assert own.status_code == 403
        assert own.json() == {"detail": FIXTURE_REJECTION}
        assert client.get(f"{mount_prefix}/api/webmcp/tools").status_code == 401


def test_webmcp_middleware_honors_prefixes_when_composed_alone(registry_snapshot: None) -> None:
    async def endpoint(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    inner = Starlette(
        routes=[Route(SELF_AUTH_UNDER_BRIDGE + "/x", endpoint), Route("/api/webmcp/other", endpoint)],
    )
    register_self_authenticating_prefix(SELF_AUTH_UNDER_BRIDGE)
    client = TestClient(WebMCPSessionMiddleware(inner, backend=LoopbackTokenBackend("secret")))
    assert client.get(SELF_AUTH_UNDER_BRIDGE + "/x").status_code == 200
    assert client.get("/api/webmcp/other").status_code == 401


@MOUNTS
def test_replacement_guard_is_never_consulted_for_self_authenticating_paths(
    seam_env: Path, monkeypatch: pytest.MonkeyPatch, registry_snapshot: None, mount_prefix: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    factory = RecordingFakeGuardFactory()
    register_self_authenticating_prefix(SELF_AUTH_UNDER_BRIDGE)
    app = create_app(guard=factory, routers=[_bridge_fixture_router()])
    with TestClient(app, root_path=mount_prefix) as client:
        assert client.get(f"{mount_prefix}{SELF_AUTH_UNDER_BRIDGE}/good").status_code == 200
        assert client.get(f"{mount_prefix}/api/version").status_code == 401
    assert len(factory.guards) == 1
    # The guard sees route paths (mount prefix removed), never the bypassed ones.
    assert factory.seen_route_paths == ["/api/version"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/api/panels/t/", "/api/panels/t"),
        ("api/panels/t", "/api/panels/t"),
        ("//api//panels/t//", "/api/panels/t"),
        ("/api/x", "/api/x"),
    ],
)
def test_register_normalizes_the_prefix(registry_snapshot: None, raw: str, expected: str) -> None:
    assert register_self_authenticating_prefix(raw) == expected
    assert expected in self_authenticating_prefixes()


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "/",
        "/api",
        "/api/",
        "/panels/t",
        "/ws/terminal",
        "/apix/t",
        "/api/../workflows",
        "/api/./t",
        "/api/pan*els",
        "/api/panels/{token}",
    ],
)
def test_register_rejects_prefixes_outside_api_or_not_literal(raw: str) -> None:
    with pytest.raises(ValueError):
        register_self_authenticating_prefix(raw)


def test_register_rejects_a_non_string() -> None:
    with pytest.raises(TypeError):
        register_self_authenticating_prefix(None)  # type: ignore[arg-type]


def test_registration_is_idempotent_ordered_and_reversible(registry_snapshot: None) -> None:
    register_self_authenticating_prefix("/api/seam-a/")
    register_self_authenticating_prefix("/api/seam-b")
    register_self_authenticating_prefix("/api/seam-a")
    assert [p for p in self_authenticating_prefixes() if p.startswith("/api/seam-")] == ["/api/seam-a", "/api/seam-b"]
    unregister_self_authenticating_prefix("/api/seam-a/")
    assert "/api/seam-a" not in self_authenticating_prefixes()
    unregister_self_authenticating_prefix("/api/seam-a")  # not registered: a no-op
    assert "/api/seam-b" in self_authenticating_prefixes()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/panels/t", True),
        ("/api/panels/t/abc123/assets/core/index.html", True),
        ("/api/panels/tx", False),
        ("/api/panels", False),
        ("/api/panels/t2/abc", False),
        # Matching is on the route path; the guard context removes the prefix.
        ("/user/alice/scistudio/api/panels/t/abc", False),
    ],
)
def test_matching_is_on_segment_boundaries_of_the_route_path(
    registry_snapshot: None, path: str, expected: bool
) -> None:
    register_self_authenticating_prefix("/api/panels/t/")
    assert is_self_authenticating_path(path) is expected


@pytest.mark.parametrize(
    ("root_path", "path", "expected"),
    [
        ("", "/api/panels/t/abc", "/api/panels/t/abc"),
        (PREFIXED_MOUNT, f"{PREFIXED_MOUNT}/api/panels/t/abc", "/api/panels/t/abc"),
        ("/p", "/p", ""),
        ("/p", "/px/api/x", "/px/api/x"),
    ],
)
def test_guard_context_route_path_removes_the_mount_prefix(root_path: str, path: str, expected: str) -> None:
    assert GuardContext(root_path=root_path).route_path({"type": "http", "path": path}) == expected


# ---------------------------------------------------------------------------
# Decision 2b: lifespan hooks.
# ---------------------------------------------------------------------------


def _recording_hook(name: str, events: list[str]) -> Callable[[FastAPI], contextlib.AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def hook(app: FastAPI) -> AsyncIterator[None]:
        events.append(f"enter {name} runtime={hasattr(app.state, 'runtime')}")
        try:
            yield
        finally:
            events.append(f"exit {name}")

    return hook


def test_lifespan_hooks_enter_in_order_after_the_runtime_and_exit_in_reverse(seam_env: Path) -> None:
    events: list[str] = []
    app = create_app(lifespan_hooks=[_recording_hook("a", events), _recording_hook("b", events)])
    assert len(app.state.lifespan_hooks) == 2
    with TestClient(app) as client:
        assert events == ["enter a runtime=True", "enter b runtime=True"]
        assert client.get("/api/version").status_code == 200
    assert events[2:] == ["exit b", "exit a"]


def test_lifespan_hook_background_task_is_cancelled_on_teardown(seam_env: Path) -> None:
    state: dict[str, Any] = {"ticks": 0}

    @asynccontextmanager
    async def activity_reporter(app: FastAPI) -> AsyncIterator[None]:
        async def report() -> None:
            while True:
                state["ticks"] += 1
                state["runs_active"] = workflow_runs_active(app)
                await asyncio.sleep(0.01)

        task = asyncio.create_task(report())
        state["task"] = task
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = create_app(lifespan_hooks=[activity_reporter])
    with TestClient(app) as client:
        assert client.get("/api/version").status_code == 200
        assert not state["task"].done()
    assert state["task"].cancelled()
    assert state.get("runs_active") in (None, False)


def test_failing_startup_hook_aborts_startup_and_unwinds(seam_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    core_teardown: list[str] = []

    async def record_core_teardown(app: object, runtime: object) -> None:
        core_teardown.append("stopped")

    monkeypatch.setattr(app_module, "stop_project_mcp_server", record_core_teardown)

    @asynccontextmanager
    async def callback_check(app: FastAPI) -> AsyncIterator[None]:
        raise RuntimeError("callback URL does not match the service prefix")
        yield  # pragma: no cover - never reached

    app = create_app(
        lifespan_hooks=[_recording_hook("first", events), callback_check, _recording_hook("never", events)],
    )
    with pytest.raises(RuntimeError, match="callback URL"), TestClient(app):
        pass
    assert events == ["enter first runtime=True", "exit first"]
    assert core_teardown == ["stopped"]


# ---------------------------------------------------------------------------
# Decision 2d: capabilities.
# ---------------------------------------------------------------------------


def test_capabilities_are_all_off_by_default() -> None:
    capabilities = Capabilities()
    assert capabilities.any_enabled is False
    # Absent means off: the declaration carries only its version.
    assert capabilities.to_bootstrap() == {"version": 1}


@pytest.mark.parametrize("url", ["/api/session/logout", f"{PREFIXED_MOUNT}/api/session/logout"])
def test_identity_accepts_same_origin_logout_paths(url: str) -> None:
    """``logout_url`` names the backend's own logout endpoint (same-origin POST target)."""
    assert IdentityCapability(user="alice", logout_url=url).logout_url == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "javascript:alert(1)",
        "//evil.example/logout",
        "https://hub.example.org/hub/logout",
        "http://127.0.0.1:8081/api/session/logout",
        "api/session/logout",
        " /api/session/logout",
        "/api/session/\nlogout",
        "ftp://hub.example.org/logout",
    ],
)
def test_identity_rejects_logout_urls_that_are_not_same_origin_paths(url: str) -> None:
    with pytest.raises(ValueError):
        IdentityCapability(user="alice", logout_url=url)


@pytest.mark.parametrize("user", ["", "   "])
def test_identity_requires_a_user(user: str) -> None:
    with pytest.raises(ValueError):
        IdentityCapability(user=user, logout_url="/api/session/logout")


def test_capabilities_reject_wrong_types() -> None:
    with pytest.raises(TypeError):
        Capabilities(transfer="yes")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Capabilities(identity={"user": "alice"})  # type: ignore[arg-type]


@MOUNTS
def test_declared_capabilities_reach_the_served_page(
    seam_env: Path, monkeypatch: pytest.MonkeyPatch, mount_prefix: str
) -> None:
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
    capabilities = Capabilities(
        identity=IdentityCapability(user="alice", logout_url="/api/session/logout"),
        transfer=TransferCapability(inline_max_bytes=1024, download_url_template="/api/x/download?path={path}"),
    )
    app = create_app(capabilities=capabilities)
    assert app.state.capabilities is capabilities
    with TestClient(app, root_path=mount_prefix) as client:
        shell = client.get(f"{mount_prefix}/projects/deep/route").text
    assert (
        'window.__SCISTUDIO_CAPABILITIES__ = {"version":1,'
        '"identity":{"user":"alice","logoutUrl":"/api/session/logout"},'
        '"transfer":{"inlineMaxBytes":1024,"downloadUrlTemplate":"/api/x/download?path={path}"}};' in shell
    )


def test_transfer_alone_declares_no_identity(seam_env: Path) -> None:
    transfer = TransferCapability(inline_max_bytes=0, download_url_template="/api/x/download/{path}")
    app = create_app(capabilities=Capabilities(transfer=transfer))
    with TestClient(app) as client:
        shell = client.get("/").text
    assert _declared_capabilities(shell) == {
        "version": 1,
        "transfer": {"inlineMaxBytes": 0, "downloadUrlTemplate": "/api/x/download/{path}"},
    }


def test_capability_declaration_is_script_safe(seam_env: Path) -> None:
    user = "</script><script>alert(1)</script> & Alice Smith\u2028"
    app = create_app(
        capabilities=Capabilities(identity=IdentityCapability(user=user, logout_url="/api/session/logout"))
    )
    with TestClient(app) as client:
        shell = client.get("/").text
    assert "<script>alert(1)" not in shell
    assert shell.count("</script>") == 1, "only the bootstrap script element closes"
    assert "\u2028" not in shell
    assert _declared_capabilities(shell)["identity"]["user"] == user


# ---------------------------------------------------------------------------
# Edition routers and argument validation.
# ---------------------------------------------------------------------------


def _edition_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/seam-edition/hello")
    async def hello() -> dict[str, str]:
        return {"hello": "edition"}

    return router


def test_edition_routers_are_reached_ahead_of_the_spa_mount(seam_env: Path) -> None:
    app = create_app(routers=[_edition_router()])
    with TestClient(app) as client:
        assert client.get("/api/seam-edition/hello").json() == {"hello": "edition"}


def test_router_included_after_creation_is_shadowed_by_the_spa_mount(seam_env: Path) -> None:
    """Why ``routers=`` exists: the SPA mount at ``/`` is registered last by the factory."""
    app = create_app()
    app.include_router(_edition_router())
    with TestClient(app) as client:
        assert client.get("/api/seam-edition/hello").status_code == 404


@pytest.mark.parametrize(
    "kwargs",
    [
        {"guard": "not a guard"},
        {"lifespan_hooks": ["not a hook"]},
        {"capabilities": {"transfer": True}},
        {"routers": ["not a router"]},
    ],
)
def test_create_app_rejects_malformed_seam_arguments(kwargs: dict[str, Any]) -> None:
    with pytest.raises(TypeError):
        create_app(**kwargs)


# ---------------------------------------------------------------------------
# Decision 3: the runs-active accessor and the declared surface.
# ---------------------------------------------------------------------------


def _run(done: bool) -> SimpleNamespace:
    return SimpleNamespace(task=SimpleNamespace(done=lambda: done))


def test_workflow_runs_active_is_false_before_startup() -> None:
    assert workflow_runs_active(FastAPI()) is False


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ({}, False),
        ({"finished": _run(True)}, False),
        ({"finished": _run(True), "running": _run(False)}, True),
    ],
)
def test_workflow_runs_active_reads_the_run_tasks(runs: dict[str, SimpleNamespace], expected: bool) -> None:
    app = FastAPI()
    app.state.runtime = SimpleNamespace(workflow_runs=runs)
    assert workflow_runs_active(app) is expected


def test_workflow_runs_active_on_a_live_backend(client: TestClient) -> None:
    assert workflow_runs_active(client.app) is False  # type: ignore[arg-type]


def test_seam_republishes_the_shared_mcp_registry() -> None:
    from scistudio.ai.agent.mcp import server

    assert seam.mcp is server.mcp
    assert seam.AUDIENCE_EXTERNAL_TAG == server.AUDIENCE_EXTERNAL_TAG == "audience:external"
    assert get_stability(server.mcp) == get_stability(seam.mcp)


def test_create_app_is_provisional_since_0_3_5() -> None:
    info = get_stability(create_app)
    assert info is not None
    assert (info.tier, info.since) == ("provisional", "0.3.5")
