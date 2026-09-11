"""Identity seam — the surface an edition composes on the open-source backend."""
# Maintainer context (kept outside generated API documentation):
# ADR-055 identity seam — the surface an edition composes on the open-source backend.
#
# The open-source edition is single-user and asks for no login. Multi-user Lab
# deployment is provided by a separate enterprise edition that builds the
# standard backend through :func:`scistudio.api.app.create_app` and then adds its
# own guard, routes, MCP tools, and background tasks (issue #2304, option B).
# Nothing is loaded automatically: the enterprise edition has its own launch
# command and passes its additions to the factory explicitly.
#
# This module holds everything that composition relies on besides the factory
# itself (``docs/specs/adr-055-identity-seam.md``):
#
# * :class:`GuardFactory` / :class:`GuardContext` — the replacement guard
#   ``create_app(guard=...)`` installs in place of the loopback token middleware.
#   The guard decides which paths it protects; a Hub guard protects everything,
#   ``/ws`` included.
# * :class:`LifespanHook` — startup checks and long-lived background tasks run
#   inside the application lifespan, torn down in reverse order before the core
#   runtime (``create_app(lifespan_hooks=...)``).
# * The **self-authenticating path registry** — route-path prefixes whose owning
#   routes authenticate every request themselves (ADR-054 per-mount panel tokens
#   under ``/api/panels/t/``). The factory enforces the exception structurally:
#   requests under a registered prefix bypass whichever guard is installed, the
#   default one included, and reach their route unauthenticated by the guard.
# * :class:`Capabilities` / :class:`IdentityCapability` — what the backend tells
#   the frontend at boot about enterprise features (``create_app(capabilities=...)``);
#   all off by default.
# * :func:`workflow_runs_active` — the read accessor a Hub activity reporter polls.
# * :data:`mcp` and :data:`AUDIENCE_EXTERNAL_TAG` — the shared FastMCP registry and
#   the tag that keeps an external-only tool out of the local socket transport.
#
# Every public symbol here is ``provisional`` under ADR-052: the enterprise
# edition depends on it, so a change carries a changelog entry instead of
# breaking that edition silently.
# Development references: #2304, ADR-052, ADR-054, ADR-055, docs/specs/adr-055-identity-seam.md.

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from scistudio.ai.agent.mcp.server import AUDIENCE_EXTERNAL_TAG
from scistudio.ai.agent.mcp.server import mcp as _shared_mcp
from scistudio.stability import provisional

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = [
    "AUDIENCE_EXTERNAL_TAG",
    "Capabilities",
    "GuardContext",
    "GuardFactory",
    "IdentityCapability",
    "LifespanHook",
    "is_self_authenticating_path",
    "mcp",
    "register_self_authenticating_prefix",
    "self_authenticating_prefixes",
    "unregister_self_authenticating_prefix",
    "workflow_runs_active",
]


#: The shared module-level FastMCP registry (ADR-040 §3.1). An edition registers
#: its own tools here with ``@mcp.tool(...)``; tag a tool with
#: :data:`AUDIENCE_EXTERNAL_TAG` to publish it through the WebMCP bridge only.
#: This is the same object as :data:`scistudio.ai.agent.mcp.server.mcp`; the
#: stability marker is stamped on that object, so it reads the same through
#: either import path.
mcp = provisional(since="0.3.5")(_shared_mcp)


# ---------------------------------------------------------------------------
# Route path: the path the router matches, after root-path prefix handling.
# ---------------------------------------------------------------------------


def route_path(scope: Scope, root_path: str) -> str:
    """Return the path the router matches for ``scope``.

    Mirrors Starlette's own route-path derivation so a guard and the router can
    never disagree about which route a request reaches: under a configured
    mount prefix the scope path still
    carries the prefix, which is removed here. ``/user/alice/scistudio/api/x``
    becomes ``/api/x``; ``/user/alice/scistudioX/api/x`` is left unchanged.
    """
    # Development references: ADR-055, Spec 0.
    path = str(scope.get("path", ""))
    if not root_path or not path.startswith(root_path):
        return path
    if path == root_path:
        return ""
    if path[len(root_path)] == "/":
        return path[len(root_path) :]
    return path


# ---------------------------------------------------------------------------
# Replacement guard (decision 2a).
# ---------------------------------------------------------------------------


@provisional(since="0.3.5")
@dataclass(frozen=True)
class GuardContext:
    """What ``create_app`` tells a guard about the application it wraps.

    ``root_path`` is the normalized mount prefix (``""`` at the root, else
    ``"/prefix"``), read from the same single normalization point as the rest
    of the backend. New fields are added here rather than to the factory call,
    so a guard written today keeps working.
    """

    root_path: str = ""

    def route_path(self, scope: Scope) -> str:
        """Return the router's path for ``scope`` (the prefix removed)."""
        return route_path(scope, self.root_path)


@provisional(since="0.3.5")
class GuardFactory(Protocol):
    """Build the guard ``create_app(guard=...)`` installs.

    Called once with the inner ASGI application and a :class:`GuardContext`;
    returns the guard, itself an ASGI application wrapping ``app``. A guard
    class whose constructor takes ``(app, context)`` satisfies this protocol
    directly; a guard that needs settings is passed as a closure or
    :func:`functools.partial`.

    The guard sees only ``http`` and ``websocket`` scopes that are not under a
    self-authenticating prefix; the factory routes everything else (the
    lifespan scope, registered prefixes) past it. It sits inside the CORS
    layer, so preflight handling and CORS headers on rejections are unchanged,
    and inside request logging, so a rejection is logged with its request id.
    """

    def __call__(self, app: ASGIApp, context: GuardContext, /) -> ASGIApp:
        """Return the guard wrapping ``app``."""
        ...


class GuardDispatchMiddleware:
    """Install one guard and enforce the self-authenticating bypass around it.

    ``create_app`` adds this middleware for the default loopback guard and for
    any replacement alike. Requests under a registered self-authenticating
    prefix, and every non-HTTP/WebSocket scope, go straight to the inner
    application; everything else goes through the guard. The exception is
    therefore enforced by the factory rather than trusted to each guard.

    Internal: not part of the seam's public surface.
    """

    def __init__(self, app: ASGIApp, *, guard: GuardFactory, root_path: str = "") -> None:
        self._inner = app
        self._context = GuardContext(root_path=root_path)
        self._guarded = guard(app, self._context)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._inner(scope, receive, send)
            return
        if is_self_authenticating_path(self._context.route_path(scope)):
            await self._inner(scope, receive, send)
            return
        await self._guarded(scope, receive, send)


# ---------------------------------------------------------------------------
# Startup/background hook (decision 2b).
# ---------------------------------------------------------------------------


@provisional(since="0.3.5")
class LifespanHook(Protocol):
    """A startup check or background task run inside the application lifespan.

    Called with the application at startup, after the core runtime exists
    (``app.state.runtime`` is set); returns an async context manager. Its entry
    is the startup work: raising aborts startup, so a misconfiguration fails at
    spawn rather than at first login. Its exit is the teardown, run in reverse
    hook order before the core runtime stops, whether the application is
    shutting down normally or startup failed after this hook was entered. A
    ``@contextlib.asynccontextmanager`` function taking ``app`` satisfies this
    protocol.
    """

    def __call__(self, app: FastAPI, /) -> AbstractAsyncContextManager[object]:
        """Return the context manager that brackets this hook's lifetime."""
        ...


# ---------------------------------------------------------------------------
# Self-authenticating path registry (decision 2c).
# ---------------------------------------------------------------------------

_SEGMENT = re.compile(r"^[A-Za-z0-9._~-]+$")
_registry_lock = threading.Lock()
_self_authenticating: tuple[str, ...] = ()


def _normalize_self_authenticating_prefix(prefix: str) -> str:
    """Normalize and validate a self-authenticating route-path prefix.

    A prefix must lie under ``/api/`` and name at least one segment below it.
    Unknown paths under ``/api/`` are 404s (the SPA fallback never serves the
    shell there), so a registered prefix can only ever reach a real route or a
    404 — never the application shell without login. Segments are literal: no
    wildcards, no ``.`` or ``..``.
    """
    if not isinstance(prefix, str):
        raise TypeError(f"self-authenticating prefix must be a str, got {type(prefix).__name__}")
    segments = [segment for segment in prefix.strip().split("/") if segment]
    if len(segments) < 2 or segments[0] != "api":
        raise ValueError(
            f"Invalid self-authenticating prefix {prefix!r}: it must lie under /api/ and name at least "
            "one segment below it (for example /api/panels/t/), so a request under it can only reach "
            "a real route or a 404."
        )
    for segment in segments:
        if segment in (".", "..") or not _SEGMENT.match(segment):
            raise ValueError(f"Invalid self-authenticating prefix {prefix!r}: segment {segment!r} is not literal.")
    return "/" + "/".join(segments)


@provisional(since="0.3.5")
def register_self_authenticating_prefix(prefix: str) -> str:
    """Register a route-path prefix whose routes authenticate requests themselves.

    Every guard, the default loopback guard and any replacement, skips its own
    check for requests under the prefix and leaves authentication to the
    owning route; ``create_app`` enforces this for whichever guard it installs.
    Matching runs on the route path after root-path prefix handling, so
    registering ``/api/panels/t/`` also covers
    ``/user/<name>/scistudio/api/panels/t/...``.

    The owning route MUST authenticate every request it serves. Register the
    narrowest prefix that covers those routes. Returns the normalized prefix
    (``/api/panels/t``); registering the same prefix again is a no-op.

    Raises :class:`ValueError` for a prefix outside ``/api/`` or with a
    non-literal segment.
    """
    normalized = _normalize_self_authenticating_prefix(prefix)
    global _self_authenticating
    with _registry_lock:
        if normalized not in _self_authenticating:
            _self_authenticating = (*_self_authenticating, normalized)
    return normalized


@provisional(since="0.3.5")
def unregister_self_authenticating_prefix(prefix: str) -> None:
    """Remove a registered prefix; requests under it are guarded again.

    Unregistering a prefix that is not registered is a no-op.
    """
    normalized = _normalize_self_authenticating_prefix(prefix)
    global _self_authenticating
    with _registry_lock:
        _self_authenticating = tuple(p for p in _self_authenticating if p != normalized)


@provisional(since="0.3.5")
def self_authenticating_prefixes() -> tuple[str, ...]:
    """Return the registered prefixes, normalized, in registration order."""
    return _self_authenticating


@provisional(since="0.3.5")
def is_self_authenticating_path(path: str) -> bool:
    """Return whether a route path lies under a registered prefix.

    ``path`` is the router's path, the mount prefix already removed (see
    :meth:`GuardContext.route_path`). A prefix matches itself and anything below
    it on a segment boundary: ``/api/panels/t`` matches ``/api/panels/t/abc/x``
    but not ``/api/panels/tx``.
    """
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in _self_authenticating)


# ---------------------------------------------------------------------------
# Capability declaration (decision 2d).
# ---------------------------------------------------------------------------


def _validate_logout_url(url: str) -> None:
    """Accept an absolute same-origin path, nothing else.

    ``logout_url`` names the backend's own logout endpoint, and the frontend
    sends it a same-origin ``POST`` under the service prefix. Another origin, a
    protocol-relative ``//host`` form, and a ``javascript:`` or other scheme
    must never get through.
    """
    if not isinstance(url, str) or not url or url != url.strip() or any(ord(ch) < 0x20 for ch in url):
        raise ValueError(
            "IdentityCapability.logout_url must be a non-empty path without whitespace or control characters"
        )
    if not url.startswith("/") or url.startswith("//"):
        raise ValueError(
            f"IdentityCapability.logout_url {url!r}: name the backend's own logout endpoint as an absolute path"
        )


@provisional(since="0.3.5")
@dataclass(frozen=True)
class IdentityCapability:
    """The ``identity`` capability: who is signed in, and where to sign out.

    ``user`` is the signed-in user's display name. In the enterprise edition's
    one-user-one-backend deployment it is fixed for the backend's lifetime.
    ``logout_url`` names the backend's own logout endpoint as an absolute path
    (for example ``/api/session/logout``). That endpoint ends the SciStudio
    session before any identity-provider logout. The frontend sends it a
    same-origin ``POST``, resolved under the service prefix, and then follows
    the location the response returns; a plain GET navigation would let other
    sites force a logout.
    """

    user: str
    logout_url: str

    def __post_init__(self) -> None:
        if not isinstance(self.user, str) or not self.user.strip():
            raise ValueError("IdentityCapability.user must be a non-empty string")
        _validate_logout_url(self.logout_url)


@provisional(since="0.3.5")
@dataclass(frozen=True)
class Capabilities:
    """The enterprise capabilities the backend declares to the frontend at boot.

    Everything is off by default, which is the open-source edition: no
    declaration reaches the page and the UI is unchanged. ``identity`` carries
    the signed-in user and logout URL; ``transfer`` turns on laptop-to-server
    file transfer. The frontend reads the declaration through its typed
    accessor (``frontend/src/lib/capabilities.ts``).
    """

    identity: IdentityCapability | None = None
    transfer: bool = False

    def __post_init__(self) -> None:
        if self.identity is not None and not isinstance(self.identity, IdentityCapability):
            raise TypeError("Capabilities.identity must be an IdentityCapability or None")
        if not isinstance(self.transfer, bool):
            raise TypeError("Capabilities.transfer must be a bool")

    @property
    def any_enabled(self) -> bool:
        """Whether at least one capability is on."""
        return self.identity is not None or self.transfer

    def to_bootstrap(self) -> dict[str, Any]:
        """Return the JSON-ready declaration injected into the served page."""
        identity: Mapping[str, str] | None = None
        if self.identity is not None:
            identity = {"user": self.identity.user, "logoutUrl": self.identity.logout_url}
        return {"identity": identity, "transfer": self.transfer}


# ---------------------------------------------------------------------------
# Runs-active accessor (decision 3).
# ---------------------------------------------------------------------------


@provisional(since="0.3.5")
def workflow_runs_active(app: FastAPI) -> bool:
    """Return whether any workflow run in this backend is still executing.

    A Hub activity reporter polls this so idle culling never stops a backend
    mid-analysis. Returns ``False`` before the lifespan has created the
    runtime and after every run's task has finished.
    """
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        return False
    return any(not run.task.done() for run in list(runtime.workflow_runs.values()))
