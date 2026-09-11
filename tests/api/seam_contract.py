"""Reusable guard contract suite for the ADR-055 identity seam (decision 2e).

Every replacement guard installed through ``create_app(guard=...)`` must pass
this suite: the test-only fake guard in this repository
(``tests/api/test_identity_seam.py``) and the enterprise edition's Hub guard.
The suite is written against the seam, not against a particular guard, and
every test runs twice: at the root mount and under a mount prefix
(``/user/alice/scistudio``, ADR-055 Spec 0).

What it pins (``docs/specs/adr-055-identity-seam.md`` §2, US2 and US3):

* without a session, the guard refuses the API, the served application shell,
  the WebMCP bridge, and the ``/ws`` WebSocket handshake;
* the loopback token is not minted and is not a session when a replacement
  guard is installed;
* with a session, all of those work;
* a route under a registered self-authenticating prefix is reached without a
  session and answers for itself, including its own rejection;
* a path that only resembles the prefix, or sits beside it, stays guarded.

"Refused" means any non-2xx answer with redirects not followed, so a guard may
answer 401, 403, or redirect to its login page.

Running it from another package
-------------------------------
This file imports only pytest, FastAPI's test client, Starlette, and SciStudio.
It is not shipped in the SciStudio wheel. An external package:

1. puts this file in its own test tree at the SciStudio version it builds on —
   for example by fetching ``tests/api/seam_contract.py`` from the matching
   SciStudio tag — importable as a plain module;
2. subclasses :class:`GuardContractSuite` in a ``test_*.py`` module and
   provides a ``guard_case`` fixture returning a :class:`GuardCase`;
3. runs pytest. The subclass is collected; the base class is not.

::

    from seam_contract import GuardCase, GuardContractSuite

    class TestHubGuardContract(GuardContractSuite):
        @pytest.fixture()
        def guard_case(self) -> GuardCase:
            return GuardCase(
                name="hub",
                guard=hub_guard_factory(test_settings()),
                authenticate=sign_in_through_hub_double,
            )

Besides the public seam (``scistudio.api.app.create_app`` and
``scistudio.api.seam``), the suite patches two internal test hooks:
``scistudio.api.app._resolve_spa_static_dir``, so a built application shell is
always served, and ``Path.home`` as seen by ``scistudio.api.runtime``, so the
runtime writes into a home directory under ``tmp_path``. Both may change together with this file,
which is why it is taken from the matching SciStudio version.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from scistudio.api.app import create_app
from scistudio.api.seam import (
    GuardFactory,
    register_self_authenticating_prefix,
    unregister_self_authenticating_prefix,
)

PREFIXED_MOUNT = "/user/alice/scistudio"
SELF_AUTH_PREFIX = "/api/seam-contract/t"
SELF_AUTH_TOKEN = "contract-token-ok"
ROUTE_REJECTION = "seam contract fixture: token rejected by its own route"
LOOPBACK_TOKEN_HEADER = "X-SciStudio-WebMCP-Token"


@dataclass(frozen=True)
class GuardCase:
    """One guard under contract test.

    ``guard`` is passed to ``create_app(guard=...)`` unchanged.
    ``authenticate`` turns the given test client into a signed-in session, for
    example by setting the guard's session cookie.
    """

    name: str
    guard: GuardFactory
    authenticate: Callable[[TestClient], None]


def contract_router() -> APIRouter:
    """Fixture routes: one self-authenticating route and two guarded neighbours."""
    router = APIRouter()

    @router.get(SELF_AUTH_PREFIX + "/{token}/ping")
    async def self_authenticating_ping(token: str) -> dict[str, bool]:
        # The route owns authentication for its prefix, as ADR-054 panel
        # token routes do: a wrong token is refused here, not by the guard.
        if not secrets.compare_digest(token, SELF_AUTH_TOKEN):
            raise HTTPException(status_code=403, detail=ROUTE_REJECTION)
        return {"ok": True}

    @router.get("/api/seam-contract/tx/ping")
    async def lookalike_ping() -> dict[str, bool]:
        # Shares the prefix's text but not its segment boundary.
        return {"ok": True}

    @router.get("/api/seam-contract/guarded")
    async def guarded_sibling() -> dict[str, bool]:
        return {"ok": True}

    return router


def _make_spa_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"></head><body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    return root


def assert_refused(response: httpx.Response) -> None:
    """A guard refusal: any non-2xx answer (401, 403, or a login redirect)."""
    assert not 200 <= response.status_code < 300, (
        f"expected the guard to refuse {response.request.url.path}, got {response.status_code}"
    )


class GuardContractSuite:
    """The contract every replacement guard passes. Subclass it as ``Test*``."""

    @pytest.fixture()
    def guard_case(self) -> GuardCase:
        raise NotImplementedError("subclass GuardContractSuite and provide a guard_case fixture")

    @pytest.fixture(params=["", PREFIXED_MOUNT], ids=["root-mount", "prefixed-mount"])
    def mount_prefix(self, request: pytest.FixtureRequest) -> str:
        return str(request.param)

    @pytest.fixture()
    def seam_client(
        self,
        guard_case: GuardCase,
        mount_prefix: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> Iterator[TestClient]:
        from scistudio.api import app as app_module
        from scistudio.api import runtime as runtime_module

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: home))
        monkeypatch.setenv("SCISTUDIO_ROOT_PATH", mount_prefix)
        spa_dir = _make_spa_dir(tmp_path / "static")
        monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: spa_dir)

        registered = register_self_authenticating_prefix(SELF_AUTH_PREFIX + "/")
        try:
            app = create_app(guard=guard_case.guard, routers=[contract_router()])
            with TestClient(app, root_path=mount_prefix, follow_redirects=False) as client:
                yield client
        finally:
            unregister_self_authenticating_prefix(registered)

    # -- without a session -------------------------------------------------

    def test_api_is_refused_without_session(self, seam_client: TestClient, mount_prefix: str) -> None:
        assert_refused(seam_client.get(f"{mount_prefix}/api/version"))

    def test_application_shell_is_refused_without_session(self, seam_client: TestClient, mount_prefix: str) -> None:
        assert_refused(seam_client.get(f"{mount_prefix}/"))
        assert_refused(seam_client.get(f"{mount_prefix}/projects/some/deep/route"))

    def test_webmcp_bridge_is_refused_without_session(self, seam_client: TestClient, mount_prefix: str) -> None:
        assert_refused(seam_client.get(f"{mount_prefix}/api/webmcp/tools"))

    def test_websocket_is_refused_without_session(self, seam_client: TestClient, mount_prefix: str) -> None:
        with (
            pytest.raises((WebSocketDisconnect, WebSocketDenialResponse)),
            seam_client.websocket_connect(f"{mount_prefix}/ws"),
        ):
            pass

    def test_loopback_token_is_not_a_session(self, seam_client: TestClient, mount_prefix: str) -> None:
        assert seam_client.app.state.webmcp_session_token == ""  # type: ignore[attr-defined]
        response = seam_client.get(f"{mount_prefix}/api/webmcp/tools", headers={LOOPBACK_TOKEN_HEADER: "anything"})
        assert_refused(response)

    # -- with a session ----------------------------------------------------

    def test_session_reaches_api_shell_and_bridge(
        self, seam_client: TestClient, guard_case: GuardCase, mount_prefix: str
    ) -> None:
        guard_case.authenticate(seam_client)
        assert seam_client.get(f"{mount_prefix}/api/version").status_code == 200
        assert seam_client.get(f"{mount_prefix}/api/seam-contract/guarded").status_code == 200
        shell = seam_client.get(f"{mount_prefix}/")
        assert shell.status_code == 200
        assert "__SCISTUDIO_WEBMCP_TOKEN__" not in shell.text
        assert seam_client.get(f"{mount_prefix}/api/webmcp/tools").status_code == 200

    def test_session_completes_websocket_handshake(
        self, seam_client: TestClient, guard_case: GuardCase, mount_prefix: str
    ) -> None:
        guard_case.authenticate(seam_client)
        with seam_client.websocket_connect(f"{mount_prefix}/ws") as websocket:
            websocket.send_text('{"type": "ping"}')

    # -- self-authenticating prefixes ---------------------------------------

    def test_self_authenticating_route_needs_no_session(self, seam_client: TestClient, mount_prefix: str) -> None:
        response = seam_client.get(f"{mount_prefix}{SELF_AUTH_PREFIX}/{SELF_AUTH_TOKEN}/ping")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_self_authenticating_route_owns_its_rejection(self, seam_client: TestClient, mount_prefix: str) -> None:
        response = seam_client.get(f"{mount_prefix}{SELF_AUTH_PREFIX}/wrong-token/ping")
        assert response.status_code == 403
        assert response.json() == {"detail": ROUTE_REJECTION}

    def test_paths_beside_the_prefix_stay_guarded(self, seam_client: TestClient, mount_prefix: str) -> None:
        assert_refused(seam_client.get(f"{mount_prefix}/api/seam-contract/tx/ping"))
        assert_refused(seam_client.get(f"{mount_prefix}/api/seam-contract/guarded"))
