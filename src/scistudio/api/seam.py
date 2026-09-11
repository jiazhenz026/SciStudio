"""ADR-055 identity seam — the surface an edition composes on the open-source backend.

The open-source edition is single-user and asks for no login. Multi-user Lab
deployment is provided by a separate enterprise edition that builds the
standard backend through :func:`scistudio.api.app.create_app` and then adds its
own guard, routes, MCP tools, and background tasks (issue #2304, option B).
Nothing is loaded automatically: the enterprise edition has its own launch
command and passes its additions to the factory explicitly.

This module holds everything that composition relies on besides the factory
itself (``docs/specs/adr-055-identity-seam.md``):

* :class:`GuardFactory` / :class:`GuardContext` — the replacement guard
  ``create_app(guard=...)`` installs in place of the loopback token middleware.
  The guard decides which paths it protects; a Hub guard protects everything,
  ``/ws`` included.
* :class:`LifespanHook` — startup checks and long-lived background tasks run
  inside the application lifespan, torn down in reverse order before the core
  runtime (``create_app(lifespan_hooks=...)``).
* The **self-authenticating path registry** — route-path prefixes whose owning
  routes authenticate every request themselves (ADR-054 per-mount panel tokens
  under ``/api/panels/t/``). The factory enforces the exception structurally:
  requests under a registered prefix bypass whichever guard is installed, the
  default one included, and reach their route unauthenticated by the guard.
* :class:`Capabilities` with :class:`IdentityCapability`,
  :class:`TransferCapability` and :class:`UpdateCapability` — what the backend
  tells the frontend at boot about enterprise features
  (``create_app(capabilities=...)``): the signed-in user, file transfer, the
  AI chat switch, and the update notice (ADR-055 Spec 4,
  ``docs/specs/adr-055-enterprise-support.md``). All off by default; every URL
  in them is a route path the frontend resolves under the service prefix.
* :func:`workflow_runs_active` — the read accessor a Hub activity reporter polls.
* Project access for an edition's routes and tools (issue #2328):
  :func:`active_project_root`; :class:`ToolRefusal`, raised inside a tool to
  return a Spec 1 ``isError`` result with its message; :func:`check_author_path`
  (project confinement plus the Spec 2 author blacklist);
  :func:`write_project_file` (the editor's shared write path); and
  :func:`add_upload_listener` for staged uploads that start, complete, or are
  discarded.
  Each wraps the internal it names in its docstring rather than repeating it.
* :data:`mcp` and :data:`AUDIENCE_EXTERNAL_TAG` — the shared FastMCP registry and
  the tag that keeps an external-only tool out of the local socket transport.

Every public symbol here is ``provisional`` under ADR-052: the enterprise
edition depends on it, so a change carries a changelog entry instead of
breaking that edition silently.
"""

from __future__ import annotations

import contextlib
import inspect
import logging
import os
import re
import threading
import unicodedata
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext
from fastmcp.tools.base import ToolResult
from mcp.types import CallToolRequestParams, TextContent

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
    "ToolRefusal",
    "TransferCapability",
    "UpdateCapability",
    "active_project_root",
    "add_upload_listener",
    "check_author_path",
    "is_self_authenticating_path",
    "mcp",
    "register_self_authenticating_prefix",
    "self_authenticating_prefixes",
    "unregister_self_authenticating_prefix",
    "workflow_runs_active",
    "write_project_file",
]

logger = logging.getLogger(__name__)


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
    mount prefix (ADR-055 Spec 0 verbatim proxying) the scope path still
    carries the prefix, which is removed here. ``/user/alice/scistudio/api/x``
    becomes ``/api/x``; ``/user/alice/scistudioX/api/x`` is left unchanged.
    """
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
    check for requests strictly below the prefix and leaves authentication to
    the owning route; ``create_app`` enforces this for whichever guard it
    installs. Matching runs on the route path after root-path prefix handling,
    so registering ``/api/panels/t/`` also covers
    ``/user/<name>/scistudio/api/panels/t/...``. The bare prefix path
    (``/api/panels/t``) is never exempt: it can be a full match for a
    parameterized sibling route, so it stays behind the guard.

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
    """Return whether a route path lies strictly below a registered prefix.

    ``path`` is the router's path, the mount prefix already removed (see
    :meth:`GuardContext.route_path`). A prefix exempts only the paths below
    it, on a segment boundary: ``/api/panels/t`` exempts
    ``/api/panels/t/abc/x`` but neither ``/api/panels/tx`` nor the bare
    ``/api/panels/t``. The bare prefix path can be a full match for a
    parameterized sibling route (``/api/ai/pty/{tab_id}`` with
    ``tab_id="internal"``, for example), so it always stays behind the guard.
    """
    return any(path.startswith(f"{prefix}/") for prefix in _self_authenticating)


# ---------------------------------------------------------------------------
# Capability declaration (decision 2d).
# ---------------------------------------------------------------------------


#: Version of the declaration's injected shape (``to_bootstrap``). It is carried
#: in the declaration so the frontend can tell which shape it reads; bump it when
#: that shape changes incompatibly. Version 1 is the first versioned shape.
_BOOTSTRAP_VERSION = 1

#: The {path} substitution marker a download URL template carries exactly once.
_PATH_MARKER = "{path}"


#: Character categories a route path never contains: control (``Cc``), format
#: (``Cf``: a BOM, a zero-width space, a soft hyphen) and separators (``Z*``).
_INVISIBLE_CATEGORIES = frozenset({"Cc", "Cf", "Zs", "Zl", "Zp"})
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")


def _has_dot_segment(url: str) -> bool:
    """Whether the path part of ``url`` has a ``.`` or ``..`` segment, encoded or not.

    Percent escapes are decoded byte by byte, as a browser reads ``%2e%2e`` as
    ``..``, and decoded again while that changes anything (three rounds at
    most; a path still changing after that is refused). The frontend's
    ``isRoutePath`` applies the same rule, so both sides agree.
    """
    route = url.split("?", 1)[0].split("#", 1)[0]
    for _round in range(3):
        if any(segment in (".", "..") for segment in re.split(r"[/\\]", route)):
            return True
        decoded = _PERCENT_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), route)
        if decoded == route:
            return False
        route = decoded
    return True


def _validate_route_path(url: object, *, field: str) -> str:
    """Accept a backend route path without the service prefix, nothing else.

    Every URL a capability carries names a route on this backend, such as
    ``/api/enterprise/session/logout``. The frontend resolves it under the
    service prefix exactly as it resolves its API calls, so the value is the
    route path alone:

    - a leading ``/``, never ``//``, and no scheme or host;
    - no whitespace, control, format or separator characters (a BOM or a
      zero-width space included), and no backslashes;
    - no ``.`` or ``..`` segment, percent-encoded or not.

    That keeps out another origin, a protocol-relative ``//host`` form, a
    ``\\``-for-``/`` variant that browsers also treat as a host, a
    ``javascript:`` or other scheme, and a path that climbs out of the service
    prefix once the browser normalizes it.
    """
    if not isinstance(url, str) or not url:
        raise ValueError(f"{field} must be a non-empty backend route path such as /api/...")
    if any(ch.isspace() or ch == "\\" or unicodedata.category(ch) in _INVISIBLE_CATEGORIES for ch in url):
        raise ValueError(
            f"{field} {url!r}: a route path has no whitespace, invisible or control characters, or backslashes"
        )
    if not url.startswith("/") or url.startswith("//"):
        raise ValueError(
            f"{field} {url!r}: name a route on this backend as an absolute path such as /api/..., "
            "without a scheme or host"
        )
    if _has_dot_segment(url):
        raise ValueError(f"{field} {url!r}: a route path has no '.' or '..' segments, encoded or not")
    return url


@provisional(since="0.3.5")
@dataclass(frozen=True)
class IdentityCapability:
    """The ``identity`` capability: who is signed in, and where to sign out.

    ``user`` is the signed-in user's display name. In the enterprise edition's
    one-user-one-backend deployment it is fixed for the backend's lifetime.

    ``logout_url`` is optional. When given, it names the backend's own logout
    endpoint as a route path without the service prefix (for example
    ``/api/enterprise/session/logout``). That endpoint ends the SciStudio
    session before any identity-provider logout and answers
    ``{"location": "<where the browser goes next>"}``. The frontend sends it a
    same-origin ``POST``, resolved under the service prefix, and then navigates
    to that location; a plain GET navigation would let other sites force a
    logout. Without it the user name renders with no Logout action.
    """

    user: str
    logout_url: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.user, str) or not self.user.strip():
            raise ValueError("IdentityCapability.user must be a non-empty string")
        if self.logout_url is not None:
            _validate_route_path(self.logout_url, field="IdentityCapability.logout_url")


@provisional(since="0.3.5")
@dataclass(frozen=True)
class TransferCapability:
    """The ``transfer`` capability: moving files between the laptop and the server.

    Uploads reuse the existing staged ``POST /api/data/upload`` route, so they
    need no URL here. ``download_url_template`` names the edition's download
    route as a route path without the service prefix, with exactly one
    ``{path}`` marker, for example
    ``/api/enterprise/transfer/download?path={path}``. The frontend replaces the
    marker with the URL-encoded project-relative path of the chosen file,
    resolves the result under the service prefix, and sends the browser there
    with a ``GET``.

    ``inline_max_bytes`` is the largest file, in bytes, the edition moves
    inline (for example through an MCP tool) rather than through a staged
    transfer. The UI's own upload always uses the staged route.
    """

    inline_max_bytes: int
    download_url_template: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.inline_max_bytes, int)
            or isinstance(self.inline_max_bytes, bool)
            or self.inline_max_bytes < 0
        ):
            raise ValueError("TransferCapability.inline_max_bytes must be a non-negative integer number of bytes")
        template = _validate_route_path(self.download_url_template, field="TransferCapability.download_url_template")
        if template.count(_PATH_MARKER) != 1:
            raise ValueError(
                f"TransferCapability.download_url_template {template!r} must contain exactly one {_PATH_MARKER} marker"
            )


@provisional(since="0.3.5")
@dataclass(frozen=True)
class UpdateCapability:
    """The ``update`` capability: a user-chosen restart into a newly installed version.

    Update availability and active runs change while the backend runs, so the
    capability carries two route paths, without the service prefix, rather
    than a snapshot. The frontend polls ``GET status_url`` every 60 seconds and
    whenever the window regains focus; it answers
    ``{"running_version", "installed_version", "update_available", "runs_active"}``.
    When an update is available the frontend shows a notice that never takes
    focus. Restart asks for confirmation and warns while runs are active. It
    then sends ``POST restart_url`` with ``{"confirm_active_runs": <bool>}``,
    which is ``true`` only after the user has accepted the runs-active
    warning, so the edition can enforce that warning itself. The route
    answers ``{"location": ...}``, and the frontend navigates there. A ``409``
    answer means work became active after the status read. Its ``active``
    field lists the kinds of work (``workflow_runs``, ``transfers``), and the
    frontend shows the warning for them, asks again, and retries with
    ``true``. The frontend never restarts or reloads on its own.
    """

    status_url: str
    restart_url: str

    def __post_init__(self) -> None:
        _validate_route_path(self.status_url, field="UpdateCapability.status_url")
        _validate_route_path(self.restart_url, field="UpdateCapability.restart_url")


@provisional(since="0.3.5")
@dataclass(frozen=True)
class Capabilities:
    """The enterprise capabilities the backend declares to the frontend at boot.

    Everything is off by default, which is the open-source edition: no
    declaration reaches the page and the UI is unchanged. An absent capability
    is off.

    ``identity``
        The signed-in user and, optionally, the backend's logout route.
    ``transfer``
        Laptop-to-server upload and download. ``None`` and ``False`` both mean
        off; ``True`` is no longer accepted, pass a :class:`TransferCapability`.
    ``ai_chat_disabled``
        ``True`` hides the in-app AI Chat and makes the ``/api/ai`` PTY routes
        refuse agent-kind providers. The Terminal (``user-terminal``) is never
        gated. This is a default and an administrator policy, not a security
        boundary: from the Terminal a user can run any CLI they install.
    ``update``
        Where the frontend polls for a newly installed version and asks for a
        restart into it.

    The frontend reads the declaration through its typed accessor
    (``frontend/src/lib/capabilities.ts``).
    """

    identity: IdentityCapability | None = None
    transfer: TransferCapability | Literal[False] | None = None
    ai_chat_disabled: bool = False
    update: UpdateCapability | None = None

    def __post_init__(self) -> None:
        if self.identity is not None and not isinstance(self.identity, IdentityCapability):
            raise TypeError("Capabilities.identity must be an IdentityCapability or None")
        if self.transfer is True:
            raise TypeError(
                "Capabilities.transfer=True is no longer accepted (changed in 0.3.5): pass "
                "TransferCapability(inline_max_bytes=..., download_url_template=...) to turn transfer on"
            )
        if self.transfer is False:
            # False keeps meaning "off", normalized so it equals the default.
            object.__setattr__(self, "transfer", None)
        elif self.transfer is not None and not isinstance(self.transfer, TransferCapability):
            raise TypeError("Capabilities.transfer must be a TransferCapability or None")
        if not isinstance(self.ai_chat_disabled, bool):
            raise TypeError("Capabilities.ai_chat_disabled must be a bool")
        if self.update is not None and not isinstance(self.update, UpdateCapability):
            raise TypeError("Capabilities.update must be an UpdateCapability or None")

    @property
    def any_enabled(self) -> bool:
        """Whether at least one capability is on."""
        return (
            self.identity is not None or self.transfer is not None or self.ai_chat_disabled or self.update is not None
        )

    def to_bootstrap(self) -> dict[str, Any]:
        """Return the JSON-ready declaration injected into the served page.

        A ``version`` field plus one key per capability that is on; an absent
        key means off. Keys are camelCase for the frontend, and every URL is
        the route path as declared, which the frontend resolves under the
        service prefix.
        """
        declaration: dict[str, Any] = {"version": _BOOTSTRAP_VERSION}
        if self.identity is not None:
            identity: dict[str, str] = {"user": self.identity.user}
            if self.identity.logout_url is not None:
                identity["logoutUrl"] = self.identity.logout_url
            declaration["identity"] = identity
        if isinstance(self.transfer, TransferCapability):
            declaration["transfer"] = {
                "inlineMaxBytes": self.transfer.inline_max_bytes,
                "downloadUrlTemplate": self.transfer.download_url_template,
            }
        if self.ai_chat_disabled:
            declaration["aiChatDisabled"] = True
        if self.update is not None:
            declaration["update"] = {"statusUrl": self.update.status_url, "restartUrl": self.update.restart_url}
        return declaration


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


# ---------------------------------------------------------------------------
# Project access, tool refusals, the shared write path, and upload listeners
# (issue #2328). Thin wrappers over today's internals, so an edition's routes
# and MCP tools reach the project without importing them.
# ---------------------------------------------------------------------------

_NO_PROJECT_MESSAGE = "No project is open in SciStudio. Open a project first."


@provisional(since="0.3.5")
def active_project_root(app: FastAPI) -> Path | None:
    """Return the open project's root directory, or ``None`` when none is open.

    The path is fully resolved (symlinks and, on Windows, short names), the
    same form the confinement checks compare against. ``None`` also before
    the lifespan has created the runtime.
    """
    runtime = getattr(app.state, "runtime", None)
    project = getattr(runtime, "active_project", None) if runtime is not None else None
    if project is None:
        return None
    return Path(os.path.realpath(project.path))


@provisional(since="0.3.5")
class ToolRefusal(ToolError):  # noqa: N818 - the name is the #2328 contract an edition codes against
    """Raise inside an MCP tool to refuse the call with a message the agent can act on.

    It carries the fields of the Spec 2 refusal the workspace tools return:
    ``code`` is a machine-readable reason, ``message`` the explanation, and
    ``alternatives`` the tools that own the refused operation. The call then
    returns a Spec 1 error result instead of failing. The result carries
    ``isError: true``, the message as its text content, and the workspace
    tools' structured content
    ``{"status": "refused", "refusal": {"code", "message", "use_instead"}}``,
    where ``alternatives`` travels as ``use_instead``. It reaches every
    caller that way, including the WebMCP bridge, which withholds the text of
    any other exception.

    Outside a tool, :func:`check_author_path` and :func:`write_project_file`
    raise it too, so an edition's HTTP route can turn the same refusal into
    its own response.

    This exception is not ``scistudio.ai.agent.mcp.tools_workspace.ToolRefusal``,
    the Pydantic model of the structured refusal the result carries.
    """

    def __init__(self, *, code: str, message: str, alternatives: list[str] | None = None) -> None:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("ToolRefusal needs a machine-readable code")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("ToolRefusal needs a message the agent can act on")
        super().__init__(message)
        self.code = code
        self.message = message
        self.alternatives: list[str] = list(alternatives or [])


def _refusal_result(refusal: ToolRefusal) -> ToolResult:
    """The Spec 1 error result for a refusal, built from the workspace tools' own types."""
    from scistudio.ai.agent.mcp.tools_workspace import FlaggedToolResult
    from scistudio.ai.agent.mcp.tools_workspace import ToolRefusal as RefusalDetail

    detail = RefusalDetail(code=refusal.code, message=refusal.message, use_instead=list(refusal.alternatives))
    result = FlaggedToolResult(
        content=[TextContent(type="text", text=refusal.message)],
        structured_content={"status": "refused", "refusal": detail.model_dump()},
    )
    result.is_error = True
    return result


class _ToolRefusalMiddleware(Middleware):
    """Turns a :class:`ToolRefusal` raised by any tool into its error result. Internal."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        try:
            return await call_next(context)
        except ToolRefusal as refusal:
            # Tool name and code only: the message can name paths (FR-007 logging).
            logger.info("tool refused: tool=%s code=%s", context.message.name, refusal.code)
            return _refusal_result(refusal)


_shared_mcp.add_middleware(_ToolRefusalMiddleware())


_INVALID_PATH_MESSAGE = (
    "That path cannot name a project file: it contains a control character or, on Windows, "
    "a stream suffix such as ::$DATA or a drive-relative form such as C:name."
)


def _resolve_in_project(project_root: Path, rel_path: str) -> Path:
    """The one resolver behind :func:`check_author_path` and :func:`write_project_file`.

    Both run exactly this, so a check followed by a write can never name
    different files (#2322 no-context audit P2-3). ``rel_path`` is taken
    literally: it is joined onto the root before the author tools' resolver
    sees it, so a leading ``~`` is a directory name, never the home
    directory. Control characters (NUL included) never name a file, and on
    Windows a ``:`` after the drive is an NTFS stream suffix or a
    drive-relative path, which would slip past the blacklist
    (``workflows/new.yaml::$DATA`` creates ``workflows/new.yaml``). Internal.
    """
    from scistudio.ai.agent.mcp.tools_workspace import _RefusedError, _resolve_author_path

    if not isinstance(rel_path, str) or not rel_path.strip():
        raise ToolRefusal(code="empty_path", message="Name a file inside the project.")
    raw = rel_path.strip()
    if any(unicodedata.category(ch) == "Cc" for ch in raw):
        raise ToolRefusal(code="invalid_path", message=_INVALID_PATH_MESSAGE)
    if os.name == "nt":
        drive, tail = os.path.splitdrive(raw)
        if ":" in tail or (drive and not tail.startswith(("/", "\\"))):
            raise ToolRefusal(code="invalid_path", message=_INVALID_PATH_MESSAGE)
    root = Path(os.path.realpath(project_root))
    candidate = raw if os.path.isabs(raw) else str(root / raw)
    try:
        resolved, _root, relative = _resolve_author_path(candidate, project_root=root)
    except _RefusedError as refused:
        raise ToolRefusal(
            code=refused.refusal.code, message=refused.refusal.message, alternatives=refused.refusal.use_instead
        ) from None
    if relative == ".":
        raise ToolRefusal(code="project_root", message="That path is the project root itself. Name a file inside it.")
    return resolved


@provisional(since="0.3.5")
def check_author_path(project_root: Path | str, rel_path: str) -> Path:
    """Resolve a path an agent wants to change, under the author tools' rules.

    ``rel_path`` is taken literally (``~`` is not expanded) and resolved
    against ``project_root``; an absolute path must lie inside it. It must
    stay inside the project after links are followed, and it is checked
    against the Spec 2 author blacklist: ``data/`` and ``workflows/*.yaml``
    belong to the tools that own them. Returns the resolved path. Otherwise it
    raises :class:`ToolRefusal` with the author tools' own refusal code, or
    ``invalid_path`` for control characters and, on Windows, a stream suffix
    such as ``::$DATA`` or a drive-relative path.
    """
    return _resolve_in_project(Path(project_root), rel_path)


@provisional(since="0.3.5")
async def write_project_file(app: FastAPI, rel_path: str, data: bytes, *, changed_by: str = "edition") -> Path:
    """Write ``data`` to a project file through the shared write path, and return its path.

    The editor's own write path (ADR-055 Spec 2 FR-005): an atomic write, the
    file's state version advanced, ``file.changed`` sent so the open UI
    updates, and a registry reload when the file is a lint-clean drop-in
    module. ``changed_by`` names the writer in that ``file.changed`` event.

    ``rel_path`` goes through the same resolver as :func:`check_author_path`,
    run here again: confinement to the open project and the author
    blacklist. A check followed by a write therefore always names the same
    file. Missing parent directories are created.

    This is a coroutine: ``await`` it from a route or tool. It raises
    :class:`ToolRefusal` when no project is open, the path is refused, or the
    write is refused (the target is a directory, for example). It raises
    :class:`TypeError` for data that is not bytes. A disk failure raises as it
    does for the editor.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("write_project_file writes bytes; encode text before writing it")
    root = active_project_root(app)
    if root is None:
        raise ToolRefusal(code="no_active_project", message=_NO_PROJECT_MESSAGE)
    target = _resolve_in_project(root, rel_path)
    files = app.state.runtime.project_files
    try:
        outcome: dict[str, Any] = await files.write_text(
            target, bytes(data), create_parents=True, changed_by=changed_by
        )
    except PermissionError:
        raise ToolRefusal(
            code="outside_project", message="Only files inside the open project can be written."
        ) from None
    if outcome.get("status") != "ok":
        raise ToolRefusal(
            code=str(outcome.get("condition") or "conflict"),
            message=str(outcome.get("message") or "The write was refused."),
        )
    return Path(os.path.realpath(root.joinpath(*str(outcome["entity_id"]).split("/"))))


#: What a listener hears: the staged upload began, or ended one of two ways.
_UploadStatus = Literal["started", "completed", "discarded"]


@provisional(since="0.3.5")
def add_upload_listener(app: FastAPI, callback: Callable[[str, int, str], Any]) -> Callable[[], None]:
    """Call ``callback(path, size, status)`` for each staged ``POST /api/data/upload``.

    ``path`` is the destination's POSIX path relative to the project the
    upload was staged into (for example ``data/raw/scan.tif``), even if
    another project opens before the upload ends. ``status`` is one of:

    - ``"started"``, when the upload is staged. FastAPI has already received
      the whole request body by then, so this marks the staging copy, not the
      network transfer; ``size`` is the size known then, or 0;
    - ``"completed"``, when the file was placed and registered;
    - ``"discarded"``, when the staged file was thrown away (too large, or the
      request failed).

    For ``"completed"`` and ``"discarded"``, ``size`` is the bytes received. An
    upload the client cancels mid-transfer never reaches the route, so it
    produces no event.

    ``callback`` may be a plain function or a coroutine function. Listeners
    run in the order they were added, before the upload's response is sent,
    so keep them quick. A listener that raises is logged and skipped. It never
    changes the upload's outcome or stops the other listeners. Returns a
    function that removes the listener; calling that function again is
    harmless.
    """
    if not callable(callback):
        raise TypeError("add_upload_listener(callback=...) must be callable as callback(path, size, status)")
    listeners: list[Callable[[str, int, str], Any]] | None = getattr(app.state, "upload_listeners", None)
    if listeners is None:
        listeners = []
        app.state.upload_listeners = listeners
    listeners.append(callback)

    def remove() -> None:
        with contextlib.suppress(ValueError):
            listeners.remove(callback)

    return remove


def upload_relative_path(app: FastAPI, destination: Path) -> str:
    """The staged upload's POSIX path relative to the open project. Internal.

    The upload route calls this once, when the upload is staged, so every
    notification for that upload names the same path even if another project
    opens meanwhile (#2322 audit P3-3).
    """
    root = active_project_root(app)
    if root is None:
        return destination.name
    try:
        return Path(os.path.realpath(destination)).relative_to(root).as_posix()
    except ValueError:
        return destination.name


async def notify_upload_listeners(app: FastAPI, path: str, *, size: int, status: _UploadStatus) -> None:
    """Tell ``app``'s upload listeners about one staged upload. Internal; never raises."""
    listeners = tuple(getattr(app.state, "upload_listeners", None) or ())
    if not listeners:
        return
    for listener in listeners:
        try:
            outcome = listener(path, size, status)
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:
            logger.exception("upload listener failed; the upload itself is unaffected")
