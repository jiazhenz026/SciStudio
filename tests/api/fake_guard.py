"""Test-only fake replacement guard for the ADR-055 identity seam (decision 2e).

Not product code. It stands in for the enterprise edition's Hub guard: it
protects every HTTP and WebSocket request unless the request carries the test
session cookie, and it is installed through ``create_app(guard=...)`` exactly as
a real replacement guard is.

It deliberately knows nothing about the self-authenticating path registry. A
passing contract suite therefore shows that ``create_app`` enforces that
exception around whichever guard it installs, rather than trusting each guard to
remember it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from scistudio.api.seam import GuardContext

FAKE_SESSION_COOKIE = "scistudio-test-session"
FAKE_SESSION_VALUE = "fake-guard-session-ok"
FAKE_REJECTION = "fake guard: login required"


class FakeCookieGuard:
    """Refuse every HTTP/WebSocket request without the test session cookie."""

    def __init__(self, app: ASGIApp, context: GuardContext) -> None:
        self.app = app
        self.context = context
        self.seen_route_paths: list[str] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        self.seen_route_paths.append(self.context.route_path(scope))
        if HTTPConnection(scope).cookies.get(FAKE_SESSION_COOKIE) == FAKE_SESSION_VALUE:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            # Deny the upgrade before any accept, as a Hub guard would.
            await send({"type": "websocket.close", "code": 1008})
            return
        await JSONResponse({"detail": FAKE_REJECTION}, status_code=401)(scope, receive, send)


class RecordingFakeGuardFactory:
    """A guard factory that keeps the guards it builds, to inspect what they saw."""

    def __init__(self) -> None:
        self.guards: list[FakeCookieGuard] = []

    def __call__(self, app: ASGIApp, context: GuardContext, /) -> ASGIApp:
        guard = FakeCookieGuard(app, context)
        self.guards.append(guard)
        return guard

    @property
    def seen_route_paths(self) -> list[str]:
        return [path for guard in self.guards for path in guard.seen_route_paths]


def authenticate_fake_session(client: TestClient) -> None:
    """Make ``client`` a signed-in session for :class:`FakeCookieGuard`."""
    client.cookies.set(FAKE_SESSION_COOKIE, FAKE_SESSION_VALUE)
