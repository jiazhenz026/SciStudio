"""``scistudio webmcp-adapter`` — a stdio MCP server over SciStudio's WebMCP HTTP bridge.

ADR-055 Spec 4 (``docs/specs/adr-055-enterprise-support.md``, FR-008 to
FR-011), issue #2308, owner option B of 2026-09-11.

Several AI apps (Claude Desktop, Claude Code, Codex, Cursor) can launch a local
MCP server over stdio but do not expose WebMCP in a browser. This adapter is
that local server. The AI app launches it; it speaks MCP to the app on
stdin/stdout and forwards to the WebMCP HTTP bridge
(:mod:`scistudio.api.routes.webmcp`):

* ``tools/list`` goes to ``GET <base>/api/webmcp/tools``;
* ``tools/call`` goes to ``POST <base>/api/webmcp/call``.

That is the catalogue and the result contract the browser registration uses,
so the ``audience:external`` tools are included, and the adapter adds neither a
second tool registry nor a new server transport (ADR-055 §4). It keeps no tool
list of its own: every ``tools/list`` is fetched from the bridge, and a
``tools/call`` result is passed through unchanged (``isError``,
``structuredContent`` and the bridge's marked substitutions for non-text
content survive as they are).

**Project binding (Spec 1 FR-005).** Each call carries the project snapshot
that was current when the adapter read the request, so calls queued behind
others keep the project they were issued for. Only a ``tools/list`` adopts a
new snapshot. When the bridge answers ``409 stale_project_context``, the
adapter sends ``notifications/tools/list_changed`` and reports the call as an
``isError`` result; calls still bound to the old snapshot fail the same way.
It never retries or redirects a call.

**Target and credentials (FR-009).** ``--base-url`` (or
``SCISTUDIO_MCP_BASE_URL``) names the service and honors a service prefix, for
example ``https://lab.example.org/user/alice/scistudio``. With ``--token`` (or
``SCISTUDIO_MCP_TOKEN``) every bridge request carries
``Authorization: Bearer <token>``; an edition's guard validates it (the lab
uses a JupyterHub API token). With no token, the adapter uses the per-user
loopback token file the local backend writes (FR-010), sent as the bridge's
``x-scistudio-webmcp-token`` header: the file for the port of a loopback
``--base-url``, or, with no base URL, the most recently started backend that
is still running. The token file is never used for a non-loopback URL, and a
missing, stale, or non-owner-only file is refused with a clear message.

**Logging (FR-011, Spec 1 FR-007).** Operation identifiers and outcomes only,
on stderr; never arguments and never a credential. ``--print-config`` prints a
ready-to-paste configuration for Claude Desktop, Claude Code, or Codex.
"""

from __future__ import annotations

import contextlib
import enum
import functools
import ipaddress
import json
import logging
import os
import queue
import shlex
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO, TYPE_CHECKING, Annotated, Any
from urllib.parse import urlsplit

import httpx
import typer

if TYPE_CHECKING:
    from scistudio.api.routes.webmcp import LoopbackTokenFile

logger = logging.getLogger(__name__)

TOKEN_ENV = "SCISTUDIO_MCP_TOKEN"
BASE_URL_ENV = "SCISTUDIO_MCP_BASE_URL"
LOG_LEVEL_ENV = "SCISTUDIO_MCP_LOG_LEVEL"

# Same values as ``scistudio.api.routes.webmcp.SESSION_TOKEN_HEADER`` and
# ``STALE_PROJECT_CODE`` (a test pins the equality). Duplicated so that loading
# this module, which every ``scistudio`` invocation does, stays light.
LOOPBACK_TOKEN_HEADER = "x-scistudio-webmcp-token"
STALE_PROJECT_CODE = "stale_project_context"

#: MCP protocol revisions this adapter speaks, newest first.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_STARTUP_TIMEOUT = 20.0
SERVER_NAME = "scistudio"
TOKEN_PLACEHOLDER = "PASTE_YOUR_TOKEN_HERE"

_TOOLS_PATH = "api/webmcp/tools"
_CALL_PATH = "api/webmcp/call"
_CATALOGUE_SECONDS = 30.0
# The shortest attempt the startup wait makes, even with little time left.
_MIN_ATTEMPT_SECONDS = 0.5
# A tool decides how long it runs; the AI app cancels or times out on its side.
_CALL_TIMEOUT = httpx.Timeout(30.0, read=None)
# After stdin closes: time for in-flight calls to finish, then time for the
# workers to notice the aborted bridge before the adapter exits regardless.
_DRAIN_SECONDS = 2.0
_ABORT_GRACE_SECONDS = 1.0
_RETRYABLE_STATUSES = frozenset({502, 503, 504})
_CANCELLED_MEMORY = 256

_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_AUTH_ERROR = -32001
_UNREACHABLE = -32002

_INSTRUCTIONS = (
    "SciStudio's tools, served through its WebMCP bridge for the project open in SciStudio. "
    "When a call reports that the active project changed, the tool list has been refreshed and "
    "the call was not executed; re-issue it only if it is still intended."
)


class AdapterConfigError(Exception):
    """A configuration or authentication problem the adapter cannot serve past (exit code 2)."""


class TokenFileUnavailableError(Exception):
    """The loopback token file cannot be used; ``retryable`` when waiting can fix it."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ConfigClient(enum.StrEnum):
    """AI apps ``--print-config`` writes a configuration snippet for."""

    CLAUDE_DESKTOP = "claude-desktop"
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"


# ---------------------------------------------------------------------------
# Target: base URL and credential.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BridgeTarget:
    """Where the bridge is and how to authenticate to it. ``credential`` stays out of ``repr``."""

    base_url: str
    credential: str = field(repr=False)
    source: str  # "bearer" (a configured token) or "token-file" (the loopback token file)

    def headers(self) -> dict[str, str]:
        if self.source == "bearer":
            return {"Authorization": f"Bearer {self.credential}"}
        return {LOOPBACK_TOKEN_HEADER: self.credential}


def normalize_base_url(raw: str) -> str:
    """Validate a base URL and return it without a trailing slash.

    The path is kept, so a service prefix such as ``/user/alice/scistudio``
    is honored. Credentials, a query string, or a fragment in the URL are
    refused without echoing the URL, because they may carry a secret.
    """
    text = raw.strip()
    try:
        parts = urlsplit(text)
        _port = parts.port  # raises ValueError for a malformed port
    except ValueError:
        raise AdapterConfigError("the base URL is not a valid URL") from None
    if parts.username is not None or parts.password is not None:
        raise AdapterConfigError(
            "the base URL must not carry credentials; pass the token with --token or SCISTUDIO_MCP_TOKEN"
        )
    if parts.query or parts.fragment:
        raise AdapterConfigError(
            "the base URL must not carry a query string or fragment; pass a token with --token or SCISTUDIO_MCP_TOKEN"
        )
    if parts.scheme not in ("http", "https") or not parts.hostname:
        # Never echoed: a token pasted into the wrong option would land in the
        # AI app's MCP log.
        raise AdapterConfigError(
            "the base URL must be an http(s) URL such as http://127.0.0.1:8000 or "
            "https://lab.example.org/user/<name>/scistudio"
        )
    segments = [segment for segment in parts.path.split("/") if segment]
    path = "/" + "/".join(segments) if segments else ""
    return f"{parts.scheme}://{parts.netloc}{path}"


def is_loopback_url(base_url: str) -> bool:
    """Return whether ``base_url`` names this computer (``localhost`` or a loopback address)."""
    host = urlsplit(base_url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _url_port(base_url: str) -> int:
    parts = urlsplit(base_url)
    return parts.port or (443 if parts.scheme == "https" else 80)


def _read_token_file(port: int | None) -> LoopbackTokenFile:
    # Imported here: the bridge module pulls in the backend, which a lab user
    # with a bearer token never needs.
    from scistudio.api.routes.webmcp import LoopbackTokenFileError, find_loopback_token_file

    try:
        return find_loopback_token_file(port)
    except LoopbackTokenFileError as exc:
        raise TokenFileUnavailableError(str(exc), retryable=exc.retryable) from None


def resolve_target(base_url: str | None, token: str | None) -> BridgeTarget:
    """Resolve the bridge target from the configured base URL and token (FR-009).

    * a token: sent as a bearer credential to ``base_url``, which is required;
    * no token and no base URL: the newest running local backend's token file;
    * no token and a loopback base URL: the token file for that port;
    * no token and any other base URL: refused, the token file stays local.
    """
    if token:
        if base_url is None:
            raise AdapterConfigError(
                "a token needs --base-url (or SCISTUDIO_MCP_BASE_URL) naming the SciStudio service it belongs to"
            )
        return BridgeTarget(normalize_base_url(base_url), token, "bearer")
    if base_url is None:
        record = _read_token_file(None)
        try:
            recorded = normalize_base_url(record.base_url)
        except AdapterConfigError:
            raise AdapterConfigError(
                f"the loopback token file {record.path} names a base URL this adapter cannot use; pass --base-url"
            ) from None
        if not is_loopback_url(recorded):
            # The loopback token never leaves the computer, whatever the file says.
            raise AdapterConfigError(
                f"the loopback token file {record.path} names {recorded}, which is not this computer's loopback "
                "address. The loopback token is only sent to 127.0.0.1, ::1 or localhost: run SciStudio on "
                "loopback, or pass --base-url with --token."
            )
        return BridgeTarget(recorded, record.token, "token-file")
    url = normalize_base_url(base_url)
    if not is_loopback_url(url):
        raise AdapterConfigError(
            f"no credential for {url}: pass --token or set SCISTUDIO_MCP_TOKEN. The loopback token file "
            "is used only for a SciStudio backend on this computer (127.0.0.1 or localhost)."
        )
    record = _read_token_file(_url_port(url))
    return BridgeTarget(url, record.token, "token-file")


def _is_auth_status(status: int) -> bool:
    # A guard that wants a browser login answers with a redirect; the adapter
    # never follows one, and treats it as an authentication failure.
    return status in (401, 403) or 300 <= status < 400


def _auth_message(target: BridgeTarget, status: int) -> str:
    if 300 <= status < 400:
        reason = (
            f"SciStudio at {target.base_url} redirected the request (HTTP {status}), "
            "which usually means it wants a browser login"
        )
    else:
        reason = f"SciStudio at {target.base_url} rejected the credential (HTTP {status})"
    if target.source == "bearer":
        hint = "check the token passed with --token or SCISTUDIO_MCP_TOKEN"
    else:
        hint = (
            "the loopback token file does not match that backend; restart SciStudio, "
            "or pass --base-url for the backend you mean"
        )
    return f"{reason}; {hint}"


class _Bridge:
    """HTTP client for one target. The base URL keeps its prefix; paths are relative."""

    def __init__(self, target: BridgeTarget, transport: httpx.BaseTransport | None) -> None:
        self.target = target
        self._client = httpx.Client(
            base_url=f"{target.base_url}/",
            headers=target.headers(),
            transport=transport,
            timeout=_CALL_TIMEOUT,
            follow_redirects=False,
            # A proxy configured in the environment must never see the
            # loopback token, or any loopback traffic; a lab URL may need it.
            trust_env=target.source == "bearer" and not is_loopback_url(target.base_url),
        )

    def get_catalogue(self, timeout: float | None = None) -> httpx.Response:
        return self._client.get(_TOOLS_PATH, timeout=httpx.Timeout(timeout or _CATALOGUE_SECONDS))

    def post_call(self, body: dict[str, Any]) -> httpx.Response:
        return self._client.post(_CALL_PATH, json=body)

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# MCP message handling.
# ---------------------------------------------------------------------------


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _discard(message: dict[str, Any]) -> None:
    """Default notification sink until :func:`serve_stdio` installs the real one."""


def _mcp_tool(entry: dict[str, Any]) -> dict[str, Any]:
    schema = entry.get("inputSchema")
    return {
        "name": entry["name"],
        "description": entry.get("description") or "",
        "inputSchema": schema if isinstance(schema, dict) else {"type": "object"},
        "_meta": {"category": entry.get("category"), "mutation": entry.get("mutation")},
    }


def _call_result(response: httpx.Response) -> dict[str, Any]:
    try:
        result = response.json()
    except ValueError:
        result = None
    if not isinstance(result, dict) or not isinstance(result.get("content"), list):
        raise _RpcError(_INTERNAL_ERROR, "the SciStudio bridge returned a tool result this adapter does not understand")
    return result


def _stale_detail(response: httpx.Response) -> dict[str, Any] | None:
    try:
        body = response.json()
    except ValueError:
        return None
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict) and detail.get("error") == STALE_PROJECT_CODE:
        return detail
    return None


def _short_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    detail = body.get("detail") if isinstance(body, dict) else None
    return f": {detail}" if isinstance(detail, str) and len(detail) <= 200 else ""


def _stale_result(name: str, detail: dict[str, Any]) -> dict[str, Any]:
    presented = detail.get("presentedProjectId")
    active = detail.get("activeProjectId")
    text = (
        "SciStudio's active project changed since the tool list was fetched (the call was bound to "
        f"project {presented!r}; the open project is now {active!r}). The call to '{name}' was NOT executed. "
        "The tool list has been refreshed; re-issue the call only if it is still intended for the open project."
    )
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": {
            "error": STALE_PROJECT_CODE,
            "presentedProjectId": presented,
            "activeProjectId": active,
        },
        "isError": True,
    }


def _restarted_result(name: str, *, outcome_unknown: bool) -> dict[str, Any]:
    if outcome_unknown:
        text = (
            f"SciStudio restarted while the call to '{name}' was in flight, so whether it ran is unknown. "
            "The adapter reconnected and refreshed the tool list; check the project before re-issuing the call."
        )
    else:
        text = (
            f"SciStudio restarted since the tool list was fetched, so the call to '{name}' was NOT executed. "
            "The adapter reconnected and refreshed the tool list; re-issue the call only if it is still intended."
        )
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _adapter_version() -> str:
    try:
        from scistudio.version import get_version

        return get_version().pep440
    except Exception:
        return "0"


@dataclass(frozen=True)
class _Bound:
    """The project snapshot a request was bound to when the adapter read it (Spec 1 FR-005)."""

    project_id: str | None


class WebMCPAdapter:
    """Translate MCP requests into WebMCP bridge calls.

    ``resolve`` returns the current :class:`BridgeTarget`; it is called again
    when a token-file target stops answering, so the adapter follows a local
    backend that restarted on another port or with a new token. ``emit``
    sends a server notification to the client. ``handle`` is thread-safe.
    """

    def __init__(
        self,
        resolve: Callable[[], BridgeTarget],
        *,
        transport: httpx.BaseTransport | None = None,
        emit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._resolve = resolve
        self._transport = transport
        self.emit: Callable[[dict[str, Any]], None] = emit or _discard
        self._lock = threading.Lock()
        self._bridge: _Bridge | None = None
        self._project_id: str | None = None
        self._cancelled: set[str | int] = set()

    @property
    def base_url(self) -> str | None:
        with self._lock:
            return self._bridge.target.base_url if self._bridge is not None else None

    @property
    def project_id(self) -> str | None:
        """The current project snapshot: from ``connect`` or the last ``tools/list`` (FR-005)."""
        with self._lock:
            return self._project_id

    def bind(self) -> _Bound:
        """Bind a request to the current snapshot; :func:`serve_stdio` does this on receipt."""
        with self._lock:
            return _Bound(self._project_id)

    def close(self) -> None:
        with self._lock:
            bridge, self._bridge = self._bridge, None
        if bridge is not None:
            bridge.close()

    # -- connection ---------------------------------------------------------

    def _use(self, target: BridgeTarget) -> _Bridge:
        with self._lock:
            previous = self._bridge
            if previous is not None and previous.target == target:
                return previous
            bridge = _Bridge(target, self._transport)
            self._bridge = bridge
        if previous is not None:
            previous.close()
        return bridge

    def _current(self) -> _Bridge:
        with self._lock:
            bridge = self._bridge
        return bridge if bridge is not None else self._use(self._resolve())

    def connect(
        self,
        *,
        timeout: float,
        interval: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Wait up to ``timeout`` seconds for the backend, then fetch the catalogue once.

        A missing or stale token file, a refused connection, or a gateway
        error is waited out; an unsafe token file, a rejected credential, or
        any other HTTP error is not, because waiting cannot fix it. Raises
        :class:`AdapterConfigError` with the reason. Each attempt is capped at
        the time left, so a backend that accepts and never answers cannot hold
        the adapter past the bound.
        """
        deadline = clock() + timeout
        while True:
            try:
                target = self._resolve()
            except TokenFileUnavailableError as exc:
                if not exc.retryable:
                    raise AdapterConfigError(str(exc)) from None
                last = str(exc)
            else:
                attempt = min(_CATALOGUE_SECONDS, max(deadline - clock(), _MIN_ATTEMPT_SECONDS))
                reason = self._try_catalogue(self._use(target), timeout=attempt)
                if reason is None:
                    return
                last = reason
            remaining = deadline - clock()
            if remaining <= 0:
                raise AdapterConfigError(
                    f"gave up waiting for SciStudio after {timeout:g} s: {last}. Start SciStudio (the desktop "
                    "app, `scistudio gui` or `scistudio serve`), or check --base-url."
                )
            sleep(min(interval, remaining))

    def _try_catalogue(self, bridge: _Bridge, *, timeout: float | None = None) -> str | None:
        """Fetch the catalogue once; return why it should be retried, or ``None`` on success."""
        base_url = bridge.target.base_url
        try:
            response = bridge.get_catalogue(timeout)
        except httpx.TransportError as exc:
            return f"SciStudio at {base_url} is not reachable ({type(exc).__name__})"
        status = response.status_code
        if status in _RETRYABLE_STATUSES:
            return f"SciStudio at {base_url} answered HTTP {status}"
        if _is_auth_status(status):
            raise AdapterConfigError(_auth_message(bridge.target, status))
        if status != 200:
            raise AdapterConfigError(
                f"GET {base_url}/{_TOOLS_PATH} answered HTTP {status}; check --base-url and its service prefix"
            )
        try:
            tools = self._record_catalogue(response)
        except _RpcError as exc:
            raise AdapterConfigError(f"{exc.message} ({base_url})") from None
        logger.info(
            "connected: base_url=%s credential=%s tools=%d project=%s",
            base_url,
            bridge.target.source,
            len(tools),
            self.project_id,
        )
        return None

    def _refresh_target(self) -> _Bridge | None:
        """Re-resolve a token-file target after a failure; return the new bridge if it moved."""
        current = self._current()
        if current.target.source != "token-file":
            return None
        try:
            target = self._resolve()
        except (TokenFileUnavailableError, AdapterConfigError):
            return None
        if target == current.target:
            return None
        logger.info("reconnected: SciStudio restarted; base_url=%s", target.base_url)
        return self._use(target)

    def _record_catalogue(self, response: httpx.Response) -> list[dict[str, Any]]:
        try:
            body = response.json()
        except ValueError:
            body = None
        tools = body.get("tools") if isinstance(body, dict) else None
        context = body.get("context") if isinstance(body, dict) else None
        if not isinstance(tools, list) or not isinstance(context, dict):
            raise _RpcError(
                _INTERNAL_ERROR, "the SciStudio bridge returned a catalogue this adapter does not understand"
            )
        project_id = context.get("projectId")
        with self._lock:
            self._project_id = project_id if isinstance(project_id, str) else None
        return [entry for entry in tools if isinstance(entry, dict) and isinstance(entry.get("name"), str)]

    def _notify_list_changed(self) -> None:
        """Tell the client its tool list is out of date.

        No new snapshot is adopted here. Calls already read keep the snapshot
        they were bound to, so a mutation issued for the old project fails as
        stale instead of running against the new one; the client's next
        ``tools/list`` adopts the new snapshot.
        """
        self.emit({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})

    # -- requests -----------------------------------------------------------

    def handle(self, message: Any, *, bound: _Bound | None = None) -> dict[str, Any] | None:
        """Handle one decoded JSON-RPC message; return the response, or ``None`` for none.

        ``bound`` is the project snapshot the request was bound to when it was
        read; without it, the request binds the current snapshot now.
        """
        if isinstance(message, list):
            return _error(None, _INVALID_REQUEST, "batch requests are not supported")
        if not isinstance(message, dict):
            return _error(None, _INVALID_REQUEST, "a JSON-RPC message must be an object")
        method = message.get("method")
        has_id = "id" in message
        req_id = message.get("id")
        if not isinstance(method, str):
            # A response from the client (this server sends no requests) needs no answer.
            if not has_id or "result" in message or "error" in message:
                return None
            return _error(req_id, _INVALID_REQUEST, "missing 'method'")
        if not has_id:
            self._notification(method, message.get("params"))
            return None
        params = message.get("params")
        if params is None:
            params = {}
        response: dict[str, Any]
        if not isinstance(params, dict):
            response = _error(req_id, _INVALID_PARAMS, "params must be an object")
        else:
            try:
                result = self._dispatch(method, params, bound or self.bind())
                response = {"jsonrpc": "2.0", "id": req_id, "result": result}
            except _RpcError as exc:
                response = _error(req_id, exc.code, exc.message)
            except Exception as exc:
                logger.error("%s: outcome=internal_error error_type=%s", method, type(exc).__name__)
                response = _error(req_id, _INTERNAL_ERROR, f"internal adapter error ({type(exc).__name__})")
        # MCP: a request the client cancelled gets no response.
        return None if self._take_cancelled(req_id) else response

    def _dispatch(self, method: str, params: dict[str, Any], bound: _Bound) -> dict[str, Any]:
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return self._tools_list()
        if method == "tools/call":
            return self._tools_call(params, bound.project_id)
        raise _RpcError(_METHOD_NOT_FOUND, f"unknown method '{method}'")

    def _notification(self, method: str, params: Any) -> None:
        if method != "notifications/cancelled" or not isinstance(params, dict):
            return
        request_id = params.get("requestId")
        if isinstance(request_id, (str, int)):
            with self._lock:
                if len(self._cancelled) >= _CANCELLED_MEMORY:
                    self._cancelled.clear()
                self._cancelled.add(request_id)

    def _take_cancelled(self, req_id: Any) -> bool:
        if not isinstance(req_id, (str, int)):
            return False
        with self._lock:
            if req_id in self._cancelled:
                self._cancelled.discard(req_id)
                return True
        return False

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": SERVER_NAME, "version": _adapter_version()},
            "instructions": _INSTRUCTIONS,
        }

    def _fetch_catalogue(self) -> httpx.Response:
        """GET the catalogue; once, follow a restarted local backend. A read, so retrying is safe."""
        bridge = self._current()
        retried = False
        while True:
            try:
                response = bridge.get_catalogue()
            except httpx.TransportError as exc:
                refreshed = None if retried else self._refresh_target()
                if refreshed is None:
                    logger.warning("tools/list: outcome=unreachable error_type=%s", type(exc).__name__)
                    raise _RpcError(
                        _UNREACHABLE, f"SciStudio at {bridge.target.base_url} is not reachable ({type(exc).__name__})"
                    ) from None
                bridge, retried = refreshed, True
                continue
            status = response.status_code
            if status == 200:
                return response
            if _is_auth_status(status):
                refreshed = None if retried else self._refresh_target()
                if refreshed is None:
                    logger.warning("tools/list: outcome=auth_rejected status=%d", status)
                    raise _RpcError(_AUTH_ERROR, _auth_message(bridge.target, status))
                bridge, retried = refreshed, True
                continue
            logger.warning("tools/list: outcome=http_error status=%d", status)
            raise _RpcError(
                _INTERNAL_ERROR, f"SciStudio at {bridge.target.base_url} answered HTTP {status} for the tool list"
            )

    def _tools_list(self) -> dict[str, Any]:
        entries = self._record_catalogue(self._fetch_catalogue())
        tools = [_mcp_tool(entry) for entry in entries]
        logger.info("tools/list: outcome=ok tools=%d project=%s", len(tools), self.project_id)
        return {"tools": tools}

    def _tools_call(self, params: dict[str, Any], project_id: str | None) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(name, str) or not name:
            raise _RpcError(_INVALID_PARAMS, "tools/call needs the tool 'name'")
        if not isinstance(arguments, dict):
            raise _RpcError(_INVALID_PARAMS, "tools/call 'arguments' must be an object")
        bridge = self._current()
        try:
            # The snapshot this call was bound to on receipt, never a newer one
            # another call's stale answer brought in (Spec 1 FR-005).
            response = bridge.post_call({"name": name, "arguments": arguments, "projectId": project_id})
        except httpx.TransportError as exc:
            # A refused connection never reached SciStudio; a failure once
            # connected may have happened after the tool started.
            outcome_unknown = not isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))
            if self._refresh_target() is not None:
                self._notify_list_changed()
                logger.info("tools/call: tool=%s outcome=backend_restarted", name)
                return _restarted_result(name, outcome_unknown=outcome_unknown)
            logger.warning("tools/call: tool=%s outcome=unreachable error_type=%s", name, type(exc).__name__)
            state = "whether it ran is unknown" if outcome_unknown else "the call was not delivered"
            raise _RpcError(
                _UNREACHABLE, f"SciStudio at {bridge.target.base_url} is not reachable ({type(exc).__name__}); {state}"
            ) from None
        return self._call_outcome(name, bridge, response)

    def _call_outcome(self, name: str, bridge: _Bridge, response: httpx.Response) -> dict[str, Any]:
        status = response.status_code
        if status == 200:
            result = _call_result(response)
            logger.info("tools/call: tool=%s outcome=%s", name, "isError" if result.get("isError") else "ok")
            return result
        if status == 409 and (detail := _stale_detail(response)) is not None:
            # FR-005: never retried; the client re-lists and the model decides.
            logger.info("tools/call: tool=%s outcome=%s", name, STALE_PROJECT_CODE)
            self._notify_list_changed()
            return _stale_result(name, detail)
        if status == 404:
            logger.info("tools/call: tool=%s outcome=unknown_tool", name)
            raise _RpcError(_INVALID_PARAMS, f"unknown tool '{name}'")
        if _is_auth_status(status):
            # The guard refused before dispatch, so the tool did not run.
            if self._refresh_target() is not None:
                self._notify_list_changed()
                logger.info("tools/call: tool=%s outcome=backend_restarted", name)
                return _restarted_result(name, outcome_unknown=False)
            logger.warning("tools/call: tool=%s outcome=auth_rejected status=%d", name, status)
            raise _RpcError(_AUTH_ERROR, _auth_message(bridge.target, status))
        logger.warning("tools/call: tool=%s outcome=http_error status=%d", name, status)
        raise _RpcError(
            _INTERNAL_ERROR, f"SciStudio at {bridge.target.base_url} answered HTTP {status}{_short_detail(response)}"
        )


# ---------------------------------------------------------------------------
# Stdio transport: newline-delimited JSON-RPC.
# ---------------------------------------------------------------------------


def serve_stdio(
    adapter: WebMCPAdapter,
    stdin: IO[bytes],
    stdout: IO[bytes],
    *,
    max_workers: int = 8,
    drain_timeout: float = _DRAIN_SECONDS,
) -> int:
    """Serve MCP on ``stdin``/``stdout`` until ``stdin`` closes; return the exit code.

    Each request is bound to the current project snapshot when it is read,
    then runs on a worker thread, so a long tool call does not hold up others
    and a call queued behind others keeps the project it was issued for.
    Responses and notifications are written whole, one per line; nothing else
    is ever written to ``stdout``.

    When ``stdin`` closes, queued and in-flight calls get ``drain_timeout``
    seconds to finish. After that, queued calls are dropped, the bridge client
    is closed to abort the calls in flight, and the function returns within a
    short grace period. The workers are daemon threads, so a call that still
    hangs cannot keep the process alive.
    """
    write_lock = threading.Lock()
    closing = threading.Event()
    work: queue.Queue[tuple[Any, _Bound] | None] = queue.Queue()

    def write(message: dict[str, Any]) -> None:
        data = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        with write_lock:
            stdout.write(data)
            stdout.flush()

    def process(message: Any, bound: _Bound) -> None:
        try:
            response = adapter.handle(message, bound=bound)
            if response is not None:
                write(response)
        except OSError as exc:
            logger.debug("stdout write failed: error_type=%s", type(exc).__name__)
        except Exception as exc:
            logger.error("request handling failed: error_type=%s", type(exc).__name__)

    def worker() -> None:
        while True:
            item = work.get()
            if item is None:
                return
            if not closing.is_set():
                process(*item)

    adapter.emit = write
    workers = [
        threading.Thread(target=worker, name=f"scistudio-webmcp-adapter-{index}", daemon=True)
        for index in range(max(1, max_workers))
    ]
    for thread in workers:
        thread.start()
    for raw in iter(stdin.readline, b""):
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            with contextlib.suppress(OSError):
                write(_error(None, _PARSE_ERROR, "parse error: the line is not valid JSON"))
            continue
        # Bind now, on receipt: a later snapshot must never reach this call.
        work.put((message, adapter.bind()))

    for _ in workers:
        work.put(None)
    if not _join_all(workers, drain_timeout):
        # The client has gone; stop waiting for calls it will never read.
        closing.set()
        adapter.close()
        _join_all(workers, _ABORT_GRACE_SECONDS)
    return 0


def _join_all(threads: list[threading.Thread], timeout: float) -> bool:
    """Join ``threads`` within one shared ``timeout``; return whether they all finished."""
    deadline = time.monotonic() + max(timeout, 0.0)
    for thread in threads:
        thread.join(max(deadline - time.monotonic(), 0.0))
    return not any(thread.is_alive() for thread in threads)


# ---------------------------------------------------------------------------
# Configuration snippets (FR-011).
# ---------------------------------------------------------------------------


def adapter_command(base_url: str | None) -> list[str]:
    """Return the command an AI app runs to launch this adapter.

    It runs the interpreter SciStudio is installed in, so the AI app needs no
    ``PATH`` entry for ``scistudio``.
    """
    command = [sys.executable, "-m", "scistudio", "webmcp-adapter"]
    if base_url:
        command += ["--base-url", base_url]
    return command


def _toml_string(value: str) -> str:
    # A JSON string is a valid TOML basic string for these values.
    return json.dumps(value)


def render_config(client: str, *, base_url: str | None, needs_token: bool) -> str:
    """Return a ready-to-paste MCP server configuration for ``client``.

    A credential is never included: when one is needed, the snippet sets
    ``SCISTUDIO_MCP_TOKEN`` to :data:`TOKEN_PLACEHOLDER` for the user to replace.
    """
    command = adapter_command(base_url)
    env = {TOKEN_ENV: TOKEN_PLACEHOLDER} if needs_token else {}
    if client == ConfigClient.CLAUDE_DESKTOP:
        server: dict[str, Any] = {"command": command[0], "args": command[1:]}
        if env:
            server["env"] = env
        return json.dumps({"mcpServers": {SERVER_NAME: server}}, indent=2)
    if client == ConfigClient.CLAUDE_CODE:
        # No ``--env``: a token on a command line lands in shell history and
        # process listings. The adapter reads SCISTUDIO_MCP_TOKEN from the
        # environment Claude Code runs in.
        argv = ["claude", "mcp", "add", "--transport", "stdio", SERVER_NAME, "--", *command]
        return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)
    if client == ConfigClient.CODEX:
        lines = [
            f"[mcp_servers.{SERVER_NAME}]",
            f"command = {_toml_string(command[0])}",
            "args = [" + ", ".join(_toml_string(arg) for arg in command[1:]) + "]",
        ]
        if env:
            lines.append("env = { " + ", ".join(f"{key} = {_toml_string(value)}" for key, value in env.items()) + " }")
        # Codex waits 10 s for a server by default; the adapter may wait longer
        # for SciStudio to start.
        lines.append(f"startup_timeout_sec = {int(DEFAULT_STARTUP_TIMEOUT) + 10}")
        return "\n".join(lines)
    raise AdapterConfigError(f"unknown client {client!r}; choose one of {', '.join(c.value for c in ConfigClient)}")


# ---------------------------------------------------------------------------
# Command.
# ---------------------------------------------------------------------------


def _stderr(message: str) -> None:
    sys.stderr.write(f"scistudio webmcp-adapter: {message}\n")
    sys.stderr.flush()


def _configure_logging(level: str) -> None:
    """Send this module's log records to stderr only; stdout is the MCP channel."""
    numeric = logging.getLevelName(level.upper())
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s scistudio-webmcp-adapter: %(message)s"))
    logger.handlers[:] = [handler]
    logger.setLevel(numeric if isinstance(numeric, int) else logging.INFO)
    logger.propagate = False
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _print_config(client: str, *, base_url: str | None, token: str | None) -> int:
    try:
        if token is not None and base_url is None:
            # The adapter would refuse this configuration at runtime.
            raise AdapterConfigError("a token needs --base-url naming the SciStudio service it belongs to")
        normalized = normalize_base_url(base_url) if base_url else None
        needs_token = token is not None or (normalized is not None and not is_loopback_url(normalized))
        snippet = render_config(client, base_url=normalized, needs_token=needs_token)
    except AdapterConfigError as exc:
        _stderr(str(exc))
        return 2
    sys.stdout.write(snippet + "\n")
    sys.stdout.flush()
    if needs_token and client == ConfigClient.CLAUDE_CODE:
        _stderr(
            "set SCISTUDIO_MCP_TOKEN in the environment Claude Code runs in; the token never goes on a command line"
        )
    elif needs_token:
        _stderr(f"the token is never printed; replace {TOKEN_PLACEHOLDER} with it")
    return 0


def run(
    *,
    base_url: str | None = None,
    token: str | None = None,
    startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
    log_level: str = "INFO",
    print_config: str | None = None,
    stdin: IO[bytes] | None = None,
    stdout: IO[bytes] | None = None,
    transport: httpx.BaseTransport | None = None,
) -> int:
    """Run the adapter once and return the process exit code.

    ``0`` when the client closes stdin; ``2`` on a configuration or
    authentication error, printed to stderr. ``transport`` replaces the HTTP
    transport in tests.
    """
    token = (token or "").strip() or None
    base_url = (base_url or "").strip() or None
    if print_config is not None:
        return _print_config(print_config, base_url=base_url, token=token)
    _configure_logging(log_level)
    adapter: WebMCPAdapter | None = None
    try:
        normalized = normalize_base_url(base_url) if base_url else None
        if token and normalized and urlsplit(normalized).scheme == "http" and not is_loopback_url(normalized):
            _stderr("warning: the bearer token is sent over plain http to another computer; use an https URL")
        adapter = WebMCPAdapter(functools.partial(resolve_target, normalized, token), transport=transport)
        adapter.connect(timeout=max(startup_timeout, 0.0))
        logger.info("serving MCP over stdio")
        return serve_stdio(adapter, stdin or sys.stdin.buffer, stdout or sys.stdout.buffer)
    except AdapterConfigError as exc:
        _stderr(str(exc))
        return 2
    except KeyboardInterrupt:
        return 0
    finally:
        if adapter is not None:
            adapter.close()


def _typer_command(
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        envvar=BASE_URL_ENV,
        help=(
            "SciStudio service URL, with any service prefix (e.g. http://127.0.0.1:8000 or "
            "https://lab.example.org/user/<name>/scistudio). Default: the newest SciStudio running on this computer."
        ),
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        envvar=TOKEN_ENV,
        help=(
            "Bearer token for a guarded service (a lab's JupyterHub API token). Prefer the "
            "SCISTUDIO_MCP_TOKEN environment variable: a command-line value is visible to other processes."
        ),
    ),
    startup_timeout: float = typer.Option(
        DEFAULT_STARTUP_TIMEOUT,
        "--startup-timeout",
        min=0.0,
        help="Seconds to wait for SciStudio to answer before exiting with a configuration error.",
    ),
    log_level: str = typer.Option("INFO", "--log-level", envvar=LOG_LEVEL_ENV, help="Log level for stderr."),
    print_config: Annotated[
        ConfigClient | None,
        typer.Option(
            "--print-config", help="Print a ready-to-paste MCP server configuration for this AI app and exit."
        ),
    ] = None,
) -> None:
    """Typer entry point around :func:`run`."""
    raise typer.Exit(
        code=run(
            base_url=base_url,
            token=token,
            startup_timeout=startup_timeout,
            log_level=log_level,
            print_config=print_config.value if print_config is not None else None,
        )
    )


def register(app: typer.Typer) -> None:
    """Register the ``webmcp-adapter`` subcommand on the ``scistudio`` Typer app."""
    app.command(
        "webmcp-adapter",
        help=(
            "Serve SciStudio's tools to an AI app that runs local MCP servers (Claude Desktop, Claude Code, "
            "Codex, Cursor) over stdio, through the WebMCP HTTP bridge."
        ),
    )(_typer_command)


__all__ = [
    "BASE_URL_ENV",
    "DEFAULT_STARTUP_TIMEOUT",
    "LOOPBACK_TOKEN_HEADER",
    "STALE_PROJECT_CODE",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "TOKEN_ENV",
    "TOKEN_PLACEHOLDER",
    "AdapterConfigError",
    "BridgeTarget",
    "ConfigClient",
    "TokenFileUnavailableError",
    "WebMCPAdapter",
    "adapter_command",
    "is_loopback_url",
    "normalize_base_url",
    "register",
    "render_config",
    "resolve_target",
    "run",
    "serve_stdio",
]
