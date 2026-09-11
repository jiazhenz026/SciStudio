"""The WebMCP HTTP bridge over the shared FastMCP registry."""
# Maintainer context (kept outside generated API documentation):
# ADR-055 Spec 1 — the WebMCP HTTP bridge over the shared FastMCP registry.
#
# An external AI host's page discovers tools over HTTP, registers browser
# callbacks with the host's WebMCP API (``document.modelContext`` /
# ``navigator.modelContext``), and forwards invocations here. Both routes
# dispatch through the same module-level FastMCP registry
# (:data:`scistudio.ai.agent.mcp.server.mcp`) that serves the local socket
# transport — one tool definition, two front doors (ADR-055 §4). This module
# adds no business logic beyond dispatch, adaptation, binding checks, and
# logging (FR-011); router-internal tool synthesis is forbidden (spec decision
# 1), so the demo's synthesized ``about_scistudio``/``import_data``/
# ``write_file``/``read_file``/``run_bash`` tools are deliberately absent.
#
# Transplanted from the hackathon demo (``scistudio-web-demo`` commit
# ``952f697b``, read-only reference) and hardened per ADR-055 §9.2:
#
# * results adapt through the shared, documented adapter
#   :func:`scistudio.ai.agent.mcp.server.adapt_tool_result` (FR-002/FR-003)
#   instead of a lossy text-only serialization;
# * tool visibility is tag-driven (:data:`AUDIENCE_EXTERNAL_TAG`, FR-004) —
#   this catalogue includes external-tagged tools, the socket transport
#   excludes them;
# * calls bind the caller's believed-active project, and mutation-tagged
#   calls with a stale selection are rejected (FR-005);
# * both endpoints sit behind one session middleware with a pluggable
#   identity-backend seam (FR-006); this spec ships the loopback token
#   backend, which ``create_app`` installs as its default guard. A replacement
#   guard passed to ``create_app`` (``adr-055-identity-seam``) takes its place
#   without router changes;
# * call logging records tool name, outcome, and bounded identifiers only —
#   never full arguments, file contents, or command bodies (FR-007).
#
# Read-call policy (FR-005, declared explicitly): read-tagged calls are
# dispatched WITHOUT the staleness check — a read cannot silently redirect a
# write, and a read issued against a changed project simply observes current
# state. Read tools that require a project while none is open fail with the
# existing no-active-project error mapped through the adapter.
#
# The default guard also publishes its loopback token in an owner-only file
# while a launcher arms it (ADR-055 Spec 4 FR-010, #2308), so the stdio MCP
# adapter ``scistudio webmcp-adapter`` can reach this bridge without the page;
# see the "Loopback token file" section below.
# Development references: ADR-055, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-010, FR-011, Spec 1,
# Spec 4, adr-055-identity-seam, #2308.

from __future__ import annotations

import contextlib
import json
import logging
import os
import secrets
import stat
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from scistudio.api.seam import GuardContext, GuardFactory, is_self_authenticating_path, route_path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webmcp"])

# The bridge is mounted at this prefix in ``api.app.create_app`` via the
# standard ``app.include_router(router, prefix=...)`` sequence (FR-011).
ROUTE_PREFIX = "/api/webmcp"

# Header carrying the loopback session token on every bridge call (FR-006).
# The matching value is injected into the served page bootstrap as
# ``window.__SCISTUDIO_WEBMCP_TOKEN__`` by ``api.spa.SPAStaticFiles``.
SESSION_TOKEN_HEADER = "x-scistudio-webmcp-token"

# Machine-readable code in the 409 detail body for a stale project binding
# (FR-005); the frontend maps it to "re-fetch the catalogue and retry".
STALE_PROJECT_CODE = "stale_project_context"


# ---------------------------------------------------------------------------
# Session substrate (FR-006): one middleware, pluggable identity backends.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BridgeIdentity:
    """The authenticated identity attached to a bridge call.

    ``subject`` is a bounded identifier safe for logs (``"loopback"`` for
    this spec's backend; a Hub username for the lab backend).
    """

    subject: str
    backend: str


@runtime_checkable
class BridgeIdentityBackend(Protocol):
    """Identity-backend seam for the bridge session middleware.

    A backend answers a header check. A deployment that needs more — login
    redirects, cookies, WebSocket and UI coverage — replaces the whole guard
    through ``create_app(guard=...)`` instead; the
    router does not change either way.
    """

    # Development references: adr-055-identity-seam.

    def authenticate(self, headers: dict[str, str]) -> BridgeIdentity | None:
        """Return the request's identity, or ``None`` to reject the call."""


class LoopbackTokenBackend:
    """Loopback identity backend: a per-launch random token.

    The token is generated once per backend launch and delivered through the
    served page bootstrap (the ```` SPA injection),
    so only the page this instance served can call the bridge. The threat
    model is single-user loopback; rotation happens on restart.
    """

    # Development references: adr-055-prefix-independence.

    def __init__(self, token: str) -> None:
        self._token = token

    def authenticate(self, headers: dict[str, str]) -> BridgeIdentity | None:
        presented = headers.get(SESSION_TOKEN_HEADER, "")
        if presented and secrets.compare_digest(presented, self._token):
            return BridgeIdentity(subject="loopback", backend="loopback-token")
        return None


class WebMCPSessionMiddleware:
    """Authenticate bridge requests through the configured identity backend.

    Scoped to ``/api/webmcp/*`` only; every other request passes through
    untouched. A deployment that protects more replaces this guard through
    ``create_app(guard=...)`` rather than widening this class. Requests under
    a self-authenticating prefix pass through even
    when this middleware is composed on its own; ``create_app`` also enforces
    that for whichever guard it installs. Pure ASGI — no response-body
    buffering — and added inside the CORS layer so preflight handling and
    CORS headers are unaffected.
    """

    # Development references: adr-055-identity-seam.

    def __init__(
        self,
        app: ASGIApp,
        *,
        backend: BridgeIdentityBackend,
        root_path: str = "",
        route_prefix: str = ROUTE_PREFIX,
    ) -> None:
        self.app = app
        self._backend = backend
        self._root_path = root_path
        self._route_prefix = route_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Under a configured mount prefix (ADR-055 Spec 0 verbatim proxying)
        # the scope path still carries the prefix; match on the route path.
        inner = route_path(scope, self._root_path)
        if is_self_authenticating_path(inner) or (
            inner != self._route_prefix and not inner.startswith(f"{self._route_prefix}/")
        ):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        identity = self._backend.authenticate(headers)
        if identity is None:
            response = JSONResponse(
                {"detail": "webmcp bridge calls require a valid session token"},
                status_code=401,
            )
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})["webmcp_identity"] = identity
        await self.app(scope, receive, send)


def loopback_token_guard(token: str) -> GuardFactory:
    """Return the guard ``create_app`` installs when no replacement is passed.

    The WebMCP bridge's loopback token middleware on ``/api/webmcp/*``,
    authenticated against ``token`` (the per-launch value the served page
    carries) — the open-source edition's behavior before the identity seam,
    unchanged.
    """

    def build(app: ASGIApp, context: GuardContext, /) -> ASGIApp:
        # ADR-055 Spec 4 FR-010: when a launcher armed it (see
        # ``loopback_token_file``), publish the token for the stdio adapter.
        # Only this default guard gets here; a replacement guard never does,
        # so an edition's backend never writes the file.
        _publish_loopback_token(token)
        return WebMCPSessionMiddleware(app, backend=LoopbackTokenBackend(token), root_path=context.root_path)

    return build


# ---------------------------------------------------------------------------
# Loopback token file (ADR-055 Spec 4 FR-010, issue #2308).
#
# The stdio MCP adapter (``scistudio webmcp-adapter``) runs as a separate
# process that the AI app launches, so it cannot read the token from the page.
# With the default guard, the backend therefore publishes its per-launch token
# in a file only the current OS user can read. Rules:
#
# * one file per port, ``~/.scistudio/webmcp/loopback-<port>.json``, holding
#   the token, the backend PID, the port, the loopback base URL (with any root
#   path) and the start time. Several backends on one computer each keep their
#   own file; an adapter given no base URL picks the most recently started
#   backend that is still running;
# * owner-only: the directory is 0700 and the file 0600 on POSIX. On Windows
#   the file lives in the user's profile, whose ACL grants the user, SYSTEM and
#   Administrators only; POSIX mode bits do not apply there;
# * written atomically (a ``mkstemp`` file, then ``os.replace``) and removed when
#   the server stops, but only by the process that wrote it and only while it
#   still holds that process's token. A backend that is killed cannot remove
#   its file, so a reader treats a file as stale unless its PID is running with
#   the process create time the file records (a reused PID does not count), and
#   the next writer prunes stale files;
# * never replaced while another running process owns it: uvicorn starts the
#   application before it binds, so a second backend started on a busy port
#   writes before it fails, and must not take the running backend's file away;
# * written only while a launcher arms it: ``scistudio serve`` and
#   ``scistudio gui`` (the desktop app runs ``gui --bundled``) know the port and
#   wrap their server run in :func:`loopback_token_file`. A replacement guard
#   never mints a token, so it never writes one.
# ---------------------------------------------------------------------------

LOOPBACK_TOKEN_FILE_VERSION = 1
_TOKEN_FILE_PREFIX = "loopback-"
_TOKEN_FILE_SUFFIX = ".json"
_TOKEN_FILE_MAX_BYTES = 64 * 1024


class LoopbackTokenFileError(Exception):
    """A loopback token file is missing, unsafe, malformed, or stale.

    ``retryable`` is true when waiting can fix it (the file is missing or its
    backend is gone, and a backend may be starting); false when the file is
    unsafe or malformed, which waiting cannot fix. ``kind`` is one of
    ``"missing"``, ``"stale"``, ``"unsafe"``, ``"malformed"`` or ``"busy"`` (a
    running backend owns the file). The message never contains the token.
    """

    def __init__(self, path: Path, reason: str, *, retryable: bool, kind: str = "unsafe") -> None:
        super().__init__(f"loopback token file {path} {reason}")
        self.path = path
        self.reason = reason
        self.retryable = retryable
        self.kind = kind


@dataclass(frozen=True)
class LoopbackTokenFile:
    """The contents of one loopback token file. ``token`` is kept out of ``repr``."""

    path: Path
    token: str = field(repr=False)
    pid: int
    port: int
    base_url: str
    started_at: float
    create_time: float | None = None


def loopback_token_dir() -> Path:
    """Return the per-user directory that holds loopback token files."""
    return Path.home() / ".scistudio" / "webmcp"


def loopback_token_path(port: int, directory: Path | None = None) -> Path:
    """Return the token file path for the backend on ``port``."""
    return (directory or loopback_token_dir()) / f"{_TOKEN_FILE_PREFIX}{port}{_TOKEN_FILE_SUFFIX}"


def _pid_alive(pid: int) -> bool:
    # psutil, not ``os.kill(pid, 0)``: on Windows ``os.kill`` with any signal
    # other than CTRL_C/CTRL_BREAK terminates the process.
    import psutil

    return bool(psutil.pid_exists(pid))


# The run-owner markers use the same identity rule (``engine.runners.process_handle``).
_PID_IDENTITY_TOLERANCE_SEC = 1.0


def _process_create_time(pid: int) -> float | None:
    import psutil

    try:
        return float(psutil.Process(pid).create_time())
    except (psutil.Error, OSError):
        return None


def _record_alive(pid: int, create_time: float | None) -> bool:
    """Return whether the process a token file names is still running as that process.

    The PID must be running and, when the file records a create time, the
    running process must have been created at that time: a reused PID does not
    make a leftover file look live.
    """
    if not _pid_alive(pid):
        return False
    if create_time is None:
        return True
    actual = _process_create_time(pid)
    return actual is not None and abs(actual - create_time) <= _PID_IDENTITY_TOLERANCE_SEC


def _recorded_owner(path: Path) -> tuple[int, float | None, str | None] | None:
    """Return ``(pid, create_time, token)`` recorded in ``path``, or ``None`` when unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("pid"), int):
        return None
    create_time = data.get("createTime")
    token = data.get("token")
    return (
        int(data["pid"]),
        float(create_time) if isinstance(create_time, (int, float)) else None,
        token if isinstance(token, str) else None,
    )


def token_file_permission_problem(st: os.stat_result, *, uid: int | None = None) -> str | None:
    """Return why a token file's owner or mode is unsafe, or ``None`` when it is owner-only.

    POSIX: the file must belong to the current user (``uid``) and grant no
    group or other permission bits. Windows has no POSIX owner or mode bits;
    there the per-user profile ACL is the protection and this returns ``None``
    unless ``uid`` is given explicitly (tests exercise the POSIX rule that way).
    """
    if uid is None:
        if sys.platform == "win32":
            return None
        uid = os.getuid()
    if st.st_uid != uid:
        return f"is owned by uid {st.st_uid}, not by the current user (uid {uid})"
    mode = stat.S_IMODE(st.st_mode)
    if mode & 0o077:
        return f"can be read or written by other users (mode {mode:04o}); it must be owner-only (0600)"
    return None


def _ensure_private_dir(directory: Path) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if sys.platform != "win32":
        st = directory.stat()
        if st.st_uid != os.getuid():
            raise PermissionError(f"loopback token directory {directory} belongs to uid {st.st_uid}, not this user")
        if stat.S_IMODE(st.st_mode) & 0o077:
            directory.chmod(0o700)


def _replace_with_retry(source: str, target: Path) -> None:
    # On Windows ``os.replace`` fails while a reader holds the target open; a
    # reader holds it for a moment only, so a short retry is enough.
    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05)


def _prune_stale_token_files(directory: Path) -> None:
    for path in directory.glob(f"{_TOKEN_FILE_PREFIX}*{_TOKEN_FILE_SUFFIX}"):
        owner = _recorded_owner(path)
        if owner is not None and not _record_alive(owner[0], owner[1]):
            with contextlib.suppress(OSError):
                path.unlink()


def write_loopback_token_file(*, token: str, port: int, base_url: str, directory: Path | None = None) -> Path:
    """Write this backend's loopback token file atomically and return its path.

    The file is created owner-only (``mkstemp`` creates it 0600 on POSIX) in a
    0700 directory, then moved into place, so a reader never sees a partial
    file. Files left by backends that are no longer running are pruned first.
    A file that another running process wrote for ``port`` is never replaced:
    :class:`LoopbackTokenFileError` (``kind="busy"``) is raised instead.
    """
    directory = directory or loopback_token_dir()
    _ensure_private_dir(directory)
    _prune_stale_token_files(directory)
    target = loopback_token_path(port, directory)
    owner = _recorded_owner(target)
    if owner is not None and owner[0] != os.getpid() and _record_alive(owner[0], owner[1]):
        raise LoopbackTokenFileError(
            target,
            f"belongs to the running SciStudio backend with pid {owner[0]}; not replacing it",
            retryable=False,
            kind="busy",
        )
    payload = {
        "version": LOOPBACK_TOKEN_FILE_VERSION,
        "token": token,
        "pid": os.getpid(),
        "createTime": _process_create_time(os.getpid()),
        "port": port,
        "baseUrl": base_url,
        "startedAt": time.time(),
    }
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".loopback-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        if sys.platform != "win32":
            os.chmod(tmp, 0o600)
        _replace_with_retry(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    return target


def remove_loopback_token_file(path: Path, *, token: str | None = None, pid: int | None = None) -> None:
    """Remove ``path`` only if it is still the file this process wrote.

    The recorded PID must be ``pid`` (this process by default); for this
    process the recorded create time must match as well, and when ``token`` is
    given the recorded token must equal it. A file another backend has written
    for the same port is left alone.
    """
    owner = _recorded_owner(path)
    if owner is None:
        return
    recorded_pid, recorded_create_time, recorded_token = owner
    if recorded_pid != (os.getpid() if pid is None else pid):
        return
    if pid is None and recorded_create_time is not None:
        own = _process_create_time(os.getpid())
        if own is None or abs(own - recorded_create_time) > _PID_IDENTITY_TOLERANCE_SEC:
            return
    if token is not None and (recorded_token is None or not secrets.compare_digest(recorded_token, token)):
        return
    for attempt in range(5):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05)


def _parse_token_file(path: Path, raw: bytes) -> LoopbackTokenFile:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise LoopbackTokenFileError(path, "is not valid JSON", retryable=False, kind="malformed") from None
    if not isinstance(data, dict) or data.get("version") != LOOPBACK_TOKEN_FILE_VERSION:
        raise LoopbackTokenFileError(path, "has an unknown format", retryable=False, kind="malformed")
    token, pid, port = data.get("token"), data.get("pid"), data.get("port")
    base_url, started_at = data.get("baseUrl"), data.get("startedAt")
    create_time = data.get("createTime")
    if not (
        isinstance(token, str)
        and token
        and isinstance(pid, int)
        and isinstance(port, int)
        and 0 < port < 65536
        and isinstance(base_url, str)
        and isinstance(started_at, (int, float))
        and (create_time is None or isinstance(create_time, (int, float)))
    ):
        raise LoopbackTokenFileError(path, "is missing a required field", retryable=False, kind="malformed")
    return LoopbackTokenFile(
        path=path,
        token=token,
        pid=pid,
        port=port,
        base_url=base_url,
        started_at=float(started_at),
        create_time=float(create_time) if create_time is not None else None,
    )


def read_loopback_token_file(path: Path) -> LoopbackTokenFile:
    """Read and validate one loopback token file.

    Refuses, with :class:`LoopbackTokenFileError`, a file that is missing, a
    symbolic link, not a regular file, not owner-only (POSIX), malformed, or
    stale (its backend PID is no longer running).
    """
    missing = "does not exist; is SciStudio running?"
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise LoopbackTokenFileError(path, missing, retryable=True, kind="missing") from None
    except OSError as exc:
        raise LoopbackTokenFileError(path, f"cannot be inspected ({exc.strerror})", retryable=False) from None
    if stat.S_ISLNK(st.st_mode):
        raise LoopbackTokenFileError(path, "is a symbolic link; refusing to follow it", retryable=False)
    if not stat.S_ISREG(st.st_mode):
        raise LoopbackTokenFileError(path, "is not a regular file", retryable=False)
    problem = token_file_permission_problem(st)
    if problem is not None:
        raise LoopbackTokenFileError(path, problem, retryable=False)
    # O_NONBLOCK: a FIFO swapped in after the lstat must not block the open.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        raise LoopbackTokenFileError(path, missing, retryable=True, kind="missing") from None
    except OSError as exc:
        raise LoopbackTokenFileError(path, f"cannot be opened ({exc.strerror})", retryable=False) from None
    with os.fdopen(fd, "rb") as handle:
        # Re-check the opened file itself: the path could have been swapped
        # between the lstat above and the open.
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise LoopbackTokenFileError(path, "is not a regular file", retryable=False)
        problem = token_file_permission_problem(opened)
        if problem is not None:
            raise LoopbackTokenFileError(path, problem, retryable=False)
        raw = handle.read(_TOKEN_FILE_MAX_BYTES)
    record = _parse_token_file(path, raw)
    if not _record_alive(record.pid, record.create_time):
        raise LoopbackTokenFileError(
            path,
            f"is stale: the SciStudio backend that wrote it (pid {record.pid}) is no longer running",
            retryable=True,
            kind="stale",
        )
    return record


def find_loopback_token_file(port: int | None = None, *, directory: Path | None = None) -> LoopbackTokenFile:
    """Return the token file for ``port``, or the newest live one when ``port`` is ``None``.

    With several backends running, "newest" is the one started most recently.
    Stale files are skipped. A malformed file, or one from a newer SciStudio,
    is skipped with a warning so it cannot hide the other backends. An unsafe
    file (a symbolic link, not owner-only) is refused outright: waiting cannot
    fix it, and it may have been planted.
    """
    directory = directory or loopback_token_dir()
    if port is not None:
        return read_loopback_token_file(loopback_token_path(port, directory))
    live: list[LoopbackTokenFile] = []
    if directory.is_dir():
        for path in sorted(directory.glob(f"{_TOKEN_FILE_PREFIX}*{_TOKEN_FILE_SUFFIX}")):
            try:
                live.append(read_loopback_token_file(path))
            except LoopbackTokenFileError as exc:
                if exc.kind == "unsafe":
                    raise
                if exc.kind == "malformed":
                    logger.warning("webmcp loopback token file skipped: %s %s", path.name, exc.reason)
    if not live:
        raise LoopbackTokenFileError(
            directory,
            "holds no token file of a running SciStudio backend; start SciStudio, or pass --base-url and --token",
            retryable=True,
            kind="missing",
        )
    return max(live, key=lambda record: record.started_at)


@dataclass
class _TokenFileRequest:
    port: int
    base_url: str
    directory: Path | None
    written: list[tuple[Path, str]] = field(default_factory=list)


_token_file_lock = threading.Lock()
_token_file_request: _TokenFileRequest | None = None


@contextlib.contextmanager
def loopback_token_file(*, port: int, base_url: str, directory: Path | None = None) -> Iterator[None]:
    """Publish the default guard's loopback token for the length of one server run.

    A launcher that knows the port wraps its server run in this context
    manager (``scistudio serve`` and ``scistudio gui`` do). While it is open,
    the default guard writes its token file as the application starts; when
    it closes, after the server has stopped, the file is removed. A backend
    built with a replacement guard writes nothing, and a backend built with
    no launcher around it (tests, ``uvicorn`` run directly) writes nothing.
    """
    global _token_file_request
    request = _TokenFileRequest(port=port, base_url=base_url, directory=directory)
    with _token_file_lock:
        _token_file_request = request
    try:
        yield
    finally:
        with _token_file_lock:
            if _token_file_request is request:
                _token_file_request = None
        for path, token in request.written:
            try:
                remove_loopback_token_file(path, token=token)
            except OSError:
                logger.warning("webmcp loopback token file could not be removed: port=%s", request.port)


def _publish_loopback_token(token: str) -> None:
    with _token_file_lock:
        request = _token_file_request
    if request is None or not token:
        return
    try:
        path = write_loopback_token_file(
            token=token, port=request.port, base_url=request.base_url, directory=request.directory
        )
    except LoopbackTokenFileError as exc:
        # Another running backend owns this port's file: leave it alone.
        logger.warning("webmcp loopback token file not written: port=%s reason=%s", request.port, exc.reason)
        return
    except OSError as exc:
        # The backend still starts; the adapter then reports the missing file.
        logger.warning(
            "webmcp loopback token file could not be written: port=%s error_type=%s", request.port, type(exc).__name__
        )
        return
    request.written.append((path, token))
    logger.info("webmcp loopback token file written: port=%s", request.port)


# ---------------------------------------------------------------------------
# Bridge call contract.
# ---------------------------------------------------------------------------


class ToolCallRequest(BaseModel):
    """One WebMCP tool invocation forwarded from the browser.

    ``project_id`` is the caller's believed-active project identifier,
    acquired from the catalogue's context snapshot.
    """

    # Development references: FR-005.

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Tool name as listed by GET /api/webmcp/tools")
    arguments: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = Field(default=None, alias="projectId")


async def build_catalogue(active_project_id: str | None) -> dict[str, Any]:
    """Build the tool catalogue the SPA registers with the host's WebMCP API.

    Entries come straight from the shared FastMCP registry
    (``mcp.list_tools()``) with ``category``/``mutation`` derived from the
    tool's tags through the same helper the socket transport uses, so the
    two surfaces cannot drift. External-audience-tagged tools are INCLUDED
    here. The ``context`` snapshot identifies the active project
    at catalogue-fetch time; the caller presents it back on each call so a
    project switch is detectable.
    """
    # Development references: FR-004, FR-005.
    from scistudio.ai.agent.mcp.server import mcp, tool_category_and_mutation

    tools: list[dict[str, Any]] = []
    for entry in await mcp.list_tools():
        category, mutation = tool_category_and_mutation(entry.tags)
        tools.append(
            {
                "name": entry.name,
                "description": entry.description or "",
                "inputSchema": entry.parameters,
                "category": category,
                "mutation": mutation,
            }
        )
    return {"tools": tools, "context": {"projectId": active_project_id}}


def _active_project_id(request: Request) -> str | None:
    active = request.app.state.runtime.active_project
    return active.id if active is not None else None


@router.get("/tools")
async def list_webmcp_tools(request: Request) -> dict[str, Any]:
    """Return the tool catalogue the SPA registers with ``registerTool()``."""
    return await build_catalogue(_active_project_id(request))


@router.post("/call")
async def call_webmcp_tool(request: Request, body: ToolCallRequest) -> dict[str, Any]:
    """Execute one tool and return the adapted MCP-shaped result payload."""
    from scistudio.ai.agent.mcp._context import bridge_call_scope
    from scistudio.ai.agent.mcp.server import adapt_tool_result, mcp, tool_category_and_mutation

    known = {t.name: t for t in await mcp.list_tools()}
    entry = known.get(body.name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown tool '{body.name}'")

    _, mutation = tool_category_and_mutation(entry.tags)
    active_project_id = _active_project_id(request)

    # FR-005 project binding: opening another page must not silently redirect
    # an in-flight write to another project. Mutation-tagged calls whose
    # presented project no longer matches the backend's active project are
    # rejected; the caller re-fetches the catalogue and retries.
    if mutation == "write" and body.project_id != active_project_id:
        logger.info(
            "webmcp call rejected: tool=%s outcome=%s presented_project=%s active_project=%s",
            body.name,
            STALE_PROJECT_CODE,
            body.project_id,
            active_project_id,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": STALE_PROJECT_CODE,
                "message": (
                    "the active project changed since the catalogue was fetched; "
                    "re-fetch GET /api/webmcp/tools and retry"
                ),
                "presentedProjectId": body.project_id,
                "activeProjectId": active_project_id,
            },
        )

    try:
        # ADR-055 Spec 2 (#2279): mark the dispatch as a bridge call so tools
        # can apply bridge-only hook-parity rules (scaffold_block's
        # list_blocks-first check) without changing local-transport behavior.
        with bridge_call_scope():
            result = await mcp.call_tool(body.name, body.arguments)
    except Exception as exc:
        # Surfaced to the agent as isError content rather than as a 500
        # (FR-003): a failed tool call is information it can act on, and an
        # HTTP error would reach it as a dead end. The detail is BOUNDED to
        # the exception type name (CodeQL py/stack-trace-exposure / PR #2275
        # review): the message can embed argument values, absolute paths, or
        # internals, which must not cross the wire to an external caller —
        # and must not be logged either (FR-007: type only).
        logger.warning(
            "webmcp call failed: tool=%s outcome=isError error_type=%s",
            body.name,
            type(exc).__name__,
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"{type(exc).__name__}: tool call failed; "
                        "detail withheld by the webmcp bridge (check arguments "
                        "and retry, or inspect the local server logs)"
                    ),
                }
            ],
            "isError": True,
        }

    # FR-007 bounded logging: tool name, outcome, and bounded identifiers
    # only. Arguments, file contents, and command bodies are never logged.
    logger.info(
        "webmcp call: tool=%s mutation=%s outcome=ok project=%s",
        body.name,
        mutation,
        active_project_id,
    )
    return adapt_tool_result(result)


__all__ = [
    "LOOPBACK_TOKEN_FILE_VERSION",
    "ROUTE_PREFIX",
    "SESSION_TOKEN_HEADER",
    "STALE_PROJECT_CODE",
    "BridgeIdentity",
    "BridgeIdentityBackend",
    "LoopbackTokenBackend",
    "LoopbackTokenFile",
    "LoopbackTokenFileError",
    "ToolCallRequest",
    "WebMCPSessionMiddleware",
    "build_catalogue",
    "find_loopback_token_file",
    "loopback_token_dir",
    "loopback_token_file",
    "loopback_token_guard",
    "loopback_token_path",
    "read_loopback_token_file",
    "remove_loopback_token_file",
    "router",
    "token_file_permission_problem",
    "write_loopback_token_file",
]
