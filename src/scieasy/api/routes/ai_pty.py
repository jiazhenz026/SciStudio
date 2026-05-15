"""WebSocket route hosting the PTY-tab embedded agent (ADR-034 Phase 1.2).

This module exposes a single endpoint:

    ``ws://host/api/ai/pty/{tab_id}?project_dir=<urlencoded>&provider=<claude-code|codex>&dangerous=<true|false>``

The route validates query parameters, spawns the appropriate PTY via
:mod:`scieasy.ai.agent.terminal`, runs two concurrent pump tasks
(PTY → WS and WS → PTY), and tears down the subprocess tree on
disconnect.

The wire protocol is locked (frontend agent implements the same spec):

* **Client → Server** (frontend keystrokes / viewport changes):

  ::

      {"type": "stdin",  "data": "<utf-8 string>"}
      {"type": "resize", "cols": 120, "rows": 30}

* **Server → Client** (PTY output, lifecycle events, errors):

  ::

      {"type": "stdout", "data": "<utf-8 string>"}
      {"type": "exit",   "code": 0}
      {"type": "error",  "message": "..."}

The route enforces a hard cap of ``MAX_ACTIVE_PTYS`` concurrent
terminals (default 16) — the 17th connection receives an ``error``
frame and is closed before the PTY is spawned.

ADR-035 (§3.10) extends this module — without modifying the existing
``WS /api/ai/pty/{tab_id}`` handler — with an engine-initiated tab-open
path. See :func:`open_engine_initiated_tab` and the
``/api/ai/pty/internal/*`` routes near the bottom of the file.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import secrets
import threading
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from scieasy.ai.agent.mcp._context import _safe_under, get_optional_context
from scieasy.ai.agent.terminal import PtyProcess, spawn_claude, spawn_codex

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Resource cap — ADR-034 §3 spec.  Module-level so a 17th connection
# attempt sees the live count regardless of which worker handles it.
MAX_ACTIVE_PTYS = 16
_active_ptys: dict[str, PtyProcess] = {}
_active_lock = asyncio.Lock()

_VALID_PROVIDERS = ("claude-code", "codex")


@router.websocket("/pty/{tab_id}")
async def pty_endpoint(websocket: WebSocket, tab_id: str) -> None:
    """Accept the WS, validate params, spawn PTY, pump until close."""
    await websocket.accept()

    # ---- Validate query parameters -----------------------------------------
    params = websocket.query_params
    provider = params.get("provider", "")
    project_dir_raw = params.get("project_dir", "")
    dangerous_raw = params.get("dangerous", "false").lower()

    if provider not in _VALID_PROVIDERS:
        await _send_error(
            websocket,
            f"Invalid provider {provider!r}; expected one of {_VALID_PROVIDERS}.",
        )
        await websocket.close()
        return

    if not project_dir_raw:
        await _send_error(websocket, "Missing required query parameter 'project_dir'.")
        await websocket.close()
        return

    try:
        project_dir = _validate_project_dir(project_dir_raw)
    except (RuntimeError, PermissionError, OSError) as exc:
        await _send_error(websocket, f"Invalid project_dir: {exc}")
        await websocket.close()
        return

    dangerous = dangerous_raw in {"true", "1", "yes"}

    # ---- Engine-initiated tab join (ADR-035 §3.10) -------------------------
    # Audit P1-C (Codex #861-2): if the engine pre-spawned a PTY for this
    # tab_id (engine-initiated AI Block tab), JOIN that PTY instead of
    # spawning a fresh one. Re-spawning would orphan the original agent
    # process, drop the engine's _engine_initial_stdin / _engine_block_run_id
    # metadata, and break the worker's completion-watcher correlation.
    existing_pty: PtyProcess | None = None
    async with _active_lock:
        candidate = _active_ptys.get(tab_id)
        if candidate is not None and getattr(candidate, "_engine_block_run_id", None):
            existing_pty = candidate

    if existing_pty is not None:
        pty = existing_pty
        # Replay the engine-supplied initial prompt to the agent, exactly
        # once, on first WS connect. Stamped sentinel attribute prevents
        # double-replay on a StrictMode dev re-mount or a reconnect.
        initial_stdin = getattr(pty, "_engine_initial_stdin", None)
        already_replayed = getattr(pty, "_engine_initial_stdin_sent", False)
        if initial_stdin and not already_replayed:
            try:
                pty.write(initial_stdin.encode("utf-8", errors="replace"))
            except Exception:  # pragma: no cover - PTY may have died
                logger.warning("engine-initiated PTY: failed to flush initial stdin", exc_info=True)
            pty._engine_initial_stdin_sent = True  # type: ignore[attr-defined]
    else:
        # ---- Resource cap --------------------------------------------------
        async with _active_lock:
            if len(_active_ptys) >= MAX_ACTIVE_PTYS:
                # Note: send + close while still holding the lock would
                # serialise rejections; safe because send_json is fast and
                # holding the lock guarantees the count snapshot we report.
                await _send_error(
                    websocket,
                    f"max {MAX_ACTIVE_PTYS} active terminals — close an existing tab and retry.",
                )
                await websocket.close()
                return

        # ---- Spawn PTY -----------------------------------------------------
        try:
            pty = _spawn(provider=provider, project_dir=project_dir, dangerous=dangerous)
        except FileNotFoundError as exc:
            # claude / codex binary missing on PATH — actionable error.
            await _send_error(websocket, f"Provider binary not found: {exc}")
            await websocket.close()
            return
        except Exception as exc:  # pragma: no cover - hard-to-trigger spawn failure
            logger.error("PTY spawn failed", exc_info=True)
            await _send_error(websocket, f"Failed to spawn PTY: {exc}")
            await websocket.close()
            return

        async with _active_lock:
            _active_ptys[tab_id] = pty

    # ---- Pump tasks --------------------------------------------------------
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    async def pump_pty_to_ws() -> None:
        """Forward PTY stdout to WS as ``{type:stdout,data:...}`` frames."""
        try:
            while not stop.is_set():
                # Use an executor — :meth:`PtyProcess.read` blocks up to
                # ~100 ms which would stall the event loop otherwise.
                data = await loop.run_in_executor(None, pty.read, 0.1)
                if data:
                    if websocket.client_state != WebSocketState.CONNECTED:
                        # Client closed already (StrictMode dev double-mount,
                        # tab close, etc.) — abort cleanly instead of letting
                        # send_json explode with "after websocket.close".
                        break
                    try:
                        await websocket.send_json({"type": "stdout", "data": data.decode("utf-8", errors="replace")})
                    except RuntimeError:
                        # ASGI race: client_state can flip between the check
                        # above and the send when uvicorn flushes a close
                        # frame concurrently. Treat as a graceful end.
                        break
                if not pty.is_alive():
                    break
        except WebSocketDisconnect:
            return
        except Exception:  # pragma: no cover - logged, swallowed to trigger cleanup
            logger.warning("PTY→WS pump failed", exc_info=True)
        finally:
            stop.set()

    async def pump_ws_to_pty() -> None:
        """Dispatch client frames to ``stdin`` / ``resize`` actions."""
        try:
            while not stop.is_set():
                msg = await websocket.receive_json()
                kind = msg.get("type")
                if kind == "stdin":
                    data = msg.get("data", "")
                    if isinstance(data, str):
                        pty.write(data.encode("utf-8", errors="replace"))
                elif kind == "resize":
                    try:
                        cols = int(msg.get("cols", 80))
                        rows = int(msg.get("rows", 24))
                    except (TypeError, ValueError):
                        continue
                    pty.resize(cols=cols, rows=rows)
                else:
                    logger.debug("Ignoring unknown WS frame type %r", kind)
        except WebSocketDisconnect:
            return
        except Exception:  # pragma: no cover - logged
            logger.warning("WS→PTY pump failed", exc_info=True)
        finally:
            stop.set()

    task_out = asyncio.create_task(pump_pty_to_ws())
    task_in = asyncio.create_task(pump_ws_to_pty())

    try:
        await stop.wait()
    finally:
        # Pop from the registry FIRST.  The subsequent awaits in this
        # finally block can themselves be cancelled (e.g. Starlette's
        # WebSocketTestSession cancels the anyio scope on context exit
        # via cs.cancel before awaiting fut.result), so deferring the
        # pop until after them would leak the entry on cancellation.
        # ``_active_ptys`` is a plain dict — direct ``pop`` is safe
        # without the asyncio lock here because no other coroutine can
        # observe a torn-down PTY meaningfully (cap check + insertion
        # happen at accept time only, behind ``_active_lock``).
        _active_ptys.pop(tab_id, None)
        # ADR-035: also drop the engine-side tab→run map entry so a
        # subsequent run does not see a stale block_run_id pointer.
        run_id_for_cleanup = _engine_tab_to_run.pop(tab_id, None)
        if run_id_for_cleanup is not None:
            _engine_run_to_run_dir.pop(run_id_for_cleanup, None)
        task_out.cancel()
        task_in.cancel()

        # Kill the subprocess tree in a background thread so even a
        # subsequent cancellation of this coroutine still terminates
        # the PTY.  Using a daemon thread (not ``loop.run_in_executor``)
        # because the awaiting coroutine itself can be cancelled and
        # would otherwise leave kill_tree's future orphaned in the
        # executor without observable completion.
        threading.Thread(target=pty.kill_tree, daemon=True).start()

        # Try to send a final exit frame before tearing down.
        if websocket.client_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                # Best-effort — pty may already be reaped.
                code = _wait_exit_code(pty)
                await websocket.send_json({"type": "exit", "code": code})
            with contextlib.suppress(Exception):
                await websocket.close()

        # Await cancellation completion to keep tests deterministic.
        # Bound with a timeout so an executor-stuck pump_pty_to_ws
        # (run_in_executor doesn't honour cancellation) can't pin the
        # route indefinitely.
        for task in (task_out, task_in):
            with contextlib.suppress(asyncio.CancelledError, TimeoutError, Exception):
                await asyncio.wait_for(task, timeout=1.0)


def _wait_exit_code(pty: PtyProcess) -> int:
    """Return the subprocess exit code if available, else ``-1``.

    Best-effort: on Windows ``winpty.PtyProcess.exitstatus`` is populated
    after :meth:`isalive` flips false; on POSIX :class:`subprocess.Popen.returncode`
    is set after :meth:`wait`.  Either way, we don't block — the caller is
    in shutdown.
    """
    try:
        impl = getattr(pty, "_impl", None)
        if impl is not None:
            status = getattr(impl, "exitstatus", None)
            if status is not None:
                return int(status)
        popen = getattr(pty, "_popen", None)
        if popen is not None and popen.returncode is not None:
            return int(popen.returncode)
    except Exception:  # pragma: no cover
        pass
    return -1


async def _send_error(websocket: WebSocket, message: str) -> None:
    """Best-effort send of an ``{type:error}`` frame."""
    try:
        await websocket.send_json({"type": "error", "message": message})
    except Exception:  # pragma: no cover
        logger.debug("Failed to send error frame", exc_info=True)


def _validate_project_dir(raw: str) -> Path:
    """Resolve and sanity-check the ``project_dir`` query parameter.

    Strategy:

    1. Resolve to an absolute path (the frontend always sends absolute).
    2. If an MCP context with an active project is installed, refuse
       paths outside that root (path-traversal hardening — same defence
       as the MCP tool path resolution).
    3. Otherwise (no MCP context yet, e.g. headless tests), accept any
       absolute path that exists and is a directory.

    Security note: this is a user-supplied path that ultimately becomes
    ``cwd=`` of a spawned subprocess.  The canonicalisation through
    :meth:`Path.resolve` plus the under-project-root check (via
    :func:`_safe_under`'s ``relative_to`` comparison) blocks
    ``..``-escapes and symlink traversal; on macOS realpath also
    canonicalises ``/tmp → /private/tmp`` so the resolved-prefix check
    survives platform-specific filesystem quirks.  CodeQL's
    ``py/path-injection`` rule will still flag this function because the
    primitive ``Path`` operations are user-tainted; the alert is
    accepted given the explicit allowlist check below.
    """
    target = Path(raw)
    if not target.is_absolute():
        raise RuntimeError(f"project_dir must be absolute, got {raw!r}.")
    # ``strict=True`` raises FileNotFoundError when the path doesn't
    # exist — combined with the ``is_dir`` check this gives CodeQL a
    # narrower attack surface than open-ended ``resolve()``.
    try:
        resolved = target.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise FileNotFoundError(f"project_dir does not exist: {raw}") from exc
    if not resolved.is_dir():
        raise FileNotFoundError(f"project_dir is not a directory: {resolved}")

    ctx = get_optional_context()
    if ctx is not None and ctx.project_dir is not None:
        try:
            _safe_under(ctx.project_dir, resolved)
        except PermissionError as exc:
            raise PermissionError(
                f"project_dir {resolved} is outside the active project root {ctx.project_dir}"
            ) from exc
    return resolved


def _spawn(
    *,
    provider: str,
    project_dir: Path,
    dangerous: bool,
    extra_env: dict[str, str] | None = None,
) -> PtyProcess:
    """Dispatch to the right factory for ``provider``.

    Test hook: callers may monkeypatch this function to inject a fake
    PTY that runs an echo subprocess instead of the real claude / codex
    binary (the WS integration tests rely on this seam).

    ``extra_env`` lets engine-initiated callers thread per-AI-Block env
    (e.g. ``SCIEASY_AI_BLOCK_RUN_DIR`` for ``finish_ai_block``, ADR-035
    §3.5 path a) into the spawned PTY without polluting the engine's
    global env.
    """
    if provider == "claude-code":
        return spawn_claude(project_dir=project_dir, dangerous=dangerous, extra_env=extra_env)
    if provider == "codex":
        return spawn_codex(project_dir=project_dir, dangerous=dangerous, extra_env=extra_env)
    # Defensive — guarded earlier in the route too.
    raise ValueError(f"Unknown provider {provider!r}")


# ---------------------------------------------------------------------------
# ADR-035 §3.10 — engine-initiated PTY tab open (skeleton).
#
# The existing ``WS /api/ai/pty/{tab_id}`` route at line 62 is the
# **user-launched** path: the frontend connects, the route validates
# query params, spawns the PTY, pumps bytes both ways. That route is
# FROZEN per ADR-034 — do not modify.
#
# ADR-035 §3.10 adds a SECOND, engine-initiated path: the AI Block
# worker calls :func:`scieasy.engine.pty_control.request_pty_tab` →
# the engine consults this module to allocate a tab from the inside
# (no incoming WS connection yet) and returns the ``tab_id`` to the
# worker. The frontend then receives a ``block_pty_opened`` WS frame
# on the main workflow WS and connects to the tab via the existing
# user-launched route, just like it would for a hand-launched tab.
#
# Skeleton: signatures + comment-block plan only.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# WS subscriber registry
#
# The existing ``/ws`` workflow WS (in ``scieasy.api.ws``) carries
# EngineEvent traffic. ADR-035 needs to push two additional, NON-engine
# messages — ``block_pty_opened`` and ``block_pty_closed`` — without
# adding new EngineEvent types (per the dispatch's hard scope rule:
# "MAY emit existing events but MAY NOT add new event types").
#
# Resolution: maintain a small subscriber registry HERE in ai_pty.py.
# The workflow WS handler (``scieasy.api.ws``) registers a per-connection
# callback on accept and unregisters on disconnect. Engine-initiated tab
# opens / closes call :func:`broadcast_ai_pty_message` which fans out
# the message dict to every live subscriber.
#
# This keeps engine/events.py untouched while still letting the engine
# push these messages to all connected browsers.
# ---------------------------------------------------------------------------


_AiPtySubscriber = Callable[[dict[str, Any]], Awaitable[None] | None]
"""Callable invoked with the message dict for every connected WS client."""

_ai_pty_subscribers: set[_AiPtySubscriber] = set()
_ai_pty_subscribers_lock = threading.Lock()


def register_ai_pty_subscriber(callback: _AiPtySubscriber) -> None:
    """Register a callback to receive ai_pty broadcast messages.

    The workflow WS handler (``scieasy.api.ws.websocket_handler``)
    registers one subscriber per active connection.

    Idempotent — registering the same callback twice is a no-op.
    """
    with _ai_pty_subscribers_lock:
        _ai_pty_subscribers.add(callback)


def unregister_ai_pty_subscriber(callback: _AiPtySubscriber) -> None:
    """Remove a previously registered subscriber.

    Silently no-ops if the callback was not registered (cleanup paths
    should never crash the WS teardown).
    """
    with _ai_pty_subscribers_lock:
        _ai_pty_subscribers.discard(callback)


async def broadcast_ai_pty_message(message: dict[str, Any]) -> None:
    """Fan-out *message* to every registered WS subscriber.

    Best-effort: subscriber exceptions are caught and logged so a single
    flaky client cannot break the broadcast for everyone else. Coroutine
    return values are awaited so async subscribers (the production WS
    handler queues the message into an asyncio.Queue) work correctly.
    """
    with _ai_pty_subscribers_lock:
        snapshot = list(_ai_pty_subscribers)
    for cb in snapshot:
        try:
            result = cb(message)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.warning("broadcast_ai_pty_message: subscriber raised", exc_info=True)


# ---------------------------------------------------------------------------
# Engine-initiated tab open
# ---------------------------------------------------------------------------


# Map tab_id → block_run_id so completion notifies can resolve back.
_engine_tab_to_run: dict[str, str] = {}

# Map block_run_id → run_dir absolute path. Populated by
# :func:`open_engine_initiated_tab` so user-driven control frames
# (``block_user_marked_done`` per ADR-035 §3.5 path c) can locate the
# right run dir to write the ``signals/mark_done.json`` signal file
# without having to reach back into AIBlock or scan the filesystem.
_engine_run_to_run_dir: dict[str, Path] = {}


def get_run_dir_for_block_run(block_run_id: str) -> Path | None:
    """Return the run_dir path registered for *block_run_id*, or None.

    Used by ``scieasy.api.ws`` to handle the ``block_user_marked_done``
    inbound WS frame (ADR-035 §3.5 path c) without bringing the AI Block
    module into the WS layer's import surface.
    """
    return _engine_run_to_run_dir.get(block_run_id)


def get_block_run_id_for_tab(tab_id: str) -> str | None:
    """Return the block_run_id mapped to *tab_id*, or None.

    Inverse of the implicit map written by :func:`open_engine_initiated_tab`;
    used by ``scieasy.api.ws`` to translate ``block_user_cancel`` frames
    addressed by tab_id into a CANCEL_BLOCK_REQUEST keyed by block_run_id.
    """
    return _engine_tab_to_run.get(tab_id)


def open_engine_initiated_tab(
    *,
    title: str,
    spawn_argv: list[str],
    cwd: str,
    initial_stdin: str,
    block_run_id: str,
    permission_mode: str,
    run_dir_path: str | None = None,
) -> str:
    """Allocate a PTY tab from inside the engine (no incoming WS yet).

    Called by the internal ``POST /api/ai/pty/internal/request-tab``
    route handler (which the AI Block worker reaches via
    :func:`scieasy.engine.pty_control.request_pty_tab`). Returns the
    ``tab_id`` so the worker can correlate completion events.

    Implementation per ADR-035 §3.10:

      1. Generate a fresh ``tab_id`` (uuid hex, 12 chars — matches the
         shape used by the user-launched route's frontend caller).
      2. Bail with :class:`RuntimeError` if ``len(_active_ptys) >=
         MAX_ACTIVE_PTYS`` (ADR-034 §8 cap).
      3. Spawn the PTY via the existing ``spawn_claude/spawn_codex``
         factories — the agent must not be able to tell the tab was
         opened server-side rather than user-side. We honour
         ``spawn_argv`` only as the source-of-truth for the binary
         family (claude-code vs codex) and ``--dangerously-*`` flags;
         the spawn helpers always re-derive the system-prompt /
         mcp-config args internally so the engine-initiated path
         lands an identical agent process.
      4. Register the spawned PTY in ``_active_ptys`` keyed by the
         fresh ``tab_id`` so the frontend's subsequent WS connect
         (driven by the ``block_pty_opened`` event) can join the
         existing PTY (the existing ``pty_endpoint`` already accepts
         ``_spawn`` monkeypatching for this seam in tests; production
         frontend → existing-PTY join is wired by I35c).
      5. Push the ``block_pty_opened`` message via the
         :func:`broadcast_ai_pty_message` registry (best-effort —
         WS broadcast failures must NOT fail the tab spawn).
      6. Return the ``tab_id``.

    The ``initial_stdin`` arg is recorded on a sentinel attribute on
    the spawned :class:`PtyProcess` so the join-WS path can replay it
    once the frontend connects (I35c will wire the consumer side).
    """
    cwd_path = Path(cwd)
    if not cwd_path.is_absolute() or not cwd_path.is_dir():
        raise RuntimeError(f"open_engine_initiated_tab: cwd must be an existing absolute dir, got {cwd!r}")

    if permission_mode not in ("safe", "bypass"):
        raise RuntimeError(
            f"open_engine_initiated_tab: permission_mode must be 'safe'|'bypass', got {permission_mode!r}"
        )

    # Resolve provider from spawn_argv. argv[0] is the binary name.
    provider = _provider_from_argv(spawn_argv)
    dangerous = permission_mode == "bypass"

    # Cap check — same lock as user-launched route, plain dict access
    # is safe because we are not on the asyncio loop here.
    if len(_active_ptys) >= MAX_ACTIVE_PTYS:
        raise RuntimeError(f"open_engine_initiated_tab: PTY cap ({MAX_ACTIVE_PTYS}) reached")

    # ADR-035 §3.5 path (a): export SCIEASY_AI_BLOCK_RUN_DIR into the PTY
    # so the spawned mcp-bridge subprocess (which the agent invokes via
    # --mcp-config <project>/.scieasy/mcp.json) can resolve the active
    # AI Block run dir for ``finish_ai_block``. Without this, the tool
    # always returns ``not_in_ai_block_context`` because no other layer
    # propagates this context — workers' env is set by uvicorn and is
    # not per-AI-Block; only the PTY-spawn site knows which block_run_id
    # we are about to attach to.
    extra_env: dict[str, str] = {}
    if run_dir_path:
        extra_env["SCIEASY_AI_BLOCK_RUN_DIR"] = str(run_dir_path)

    pty = _spawn(
        provider=provider,
        project_dir=cwd_path,
        dangerous=dangerous,
        extra_env=extra_env or None,
    )

    # Stamp with engine-side metadata so the join-WS path (I35c) can
    # tell this tab apart from a user-launched one and replay the
    # initial prompt to the agent.
    pty._engine_initial_stdin = initial_stdin  # type: ignore[attr-defined]
    pty._engine_block_run_id = block_run_id  # type: ignore[attr-defined]

    tab_id = uuid.uuid4().hex[:12]
    _active_ptys[tab_id] = pty
    _engine_tab_to_run[tab_id] = block_run_id
    if run_dir_path:
        _engine_run_to_run_dir[block_run_id] = Path(run_dir_path)

    message = {
        "type": "block_pty_opened",
        "tab_id": tab_id,
        "title": title,
        "block_run_id": block_run_id,
        "permission_mode": permission_mode,
    }

    # Best-effort WS broadcast. We schedule the broadcast onto the
    # running event loop if there is one (production: the FastAPI
    # request handler runs on the loop); otherwise log + skip (tests
    # that drive this synchronously can call broadcast_ai_pty_message
    # themselves).
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_ai_pty_message(message))  # noqa: RUF006
    except RuntimeError:
        logger.debug("open_engine_initiated_tab: no running loop, broadcast skipped")

    logger.info(
        "open_engine_initiated_tab: tab_id=%s block_run_id=%s provider=%s permission=%s",
        tab_id,
        block_run_id,
        provider,
        permission_mode,
    )
    return tab_id


def _provider_from_argv(spawn_argv: list[str]) -> str:
    """Pick the provider key (claude-code | codex) from argv[0]."""
    if not spawn_argv:
        raise RuntimeError("open_engine_initiated_tab: spawn_argv is empty")
    head = Path(spawn_argv[0]).name.lower()
    if "codex" in head:
        return "codex"
    # Default to claude-code — matches the AI Block "Claude Code" provider.
    return "claude-code"


# ---------------------------------------------------------------------------
# Internal HTTP routes — worker → engine IPC.
#
# These two endpoints are private to the engine process. The token comes
# from the env var ``SCIEASY_ENGINE_IPC_TOKEN`` which the engine sets at
# startup; child worker subprocesses inherit it via ``os.environ`` and
# attach it on the ``X-SciEasy-IPC-Token`` request header.
# ---------------------------------------------------------------------------


def _ensure_ipc_token() -> str:
    """Return the live IPC token, generating a per-process one if missing.

    The first call sets ``SCIEASY_ENGINE_IPC_TOKEN`` if unset so a child
    process can inherit the same value. Production engines that fork
    workers BEFORE this is touched should call it eagerly during
    startup; tests can rely on lazy generation.
    """
    tok = os.environ.get("SCIEASY_ENGINE_IPC_TOKEN")
    if tok:
        return tok
    tok = secrets.token_urlsafe(24)
    os.environ["SCIEASY_ENGINE_IPC_TOKEN"] = tok
    return tok


def _check_ipc_token(provided: str | None) -> None:
    """Raise 401 if *provided* doesn't match the live IPC token."""
    expected = os.environ.get("SCIEASY_ENGINE_IPC_TOKEN", "")
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid SciEasy IPC token")


_HeaderToken = Annotated[str | None, Header(alias="X-SciEasy-IPC-Token")]
_BodyDict = Annotated[dict[str, Any], Body()]


@router.post("/pty/internal/request-tab")
async def _internal_request_tab(
    payload: _BodyDict,
    x_scieasy_ipc_token: _HeaderToken = None,
) -> dict[str, Any]:
    """Engine-internal endpoint: AI Block worker requests a new PTY tab.

    Returns ``{"tab_id": str, "error": null}`` on success, or
    ``{"tab_id": null, "error": <message>}`` on a soft failure such as
    cap exceeded. Hard transport failures (auth, malformed body) raise
    :class:`HTTPException` with the appropriate status.
    """
    _check_ipc_token(x_scieasy_ipc_token)

    if payload.get("type") != "request_pty_tab":
        raise HTTPException(status_code=400, detail="payload.type must be 'request_pty_tab'")
    spec = payload.get("spec")
    if not isinstance(spec, dict):
        raise HTTPException(status_code=400, detail="payload.spec must be a dict")

    try:
        tab_id = open_engine_initiated_tab(
            title=str(spec.get("title", "")),
            spawn_argv=list(spec.get("spawn_argv", [])),
            cwd=str(spec.get("cwd", "")),
            initial_stdin=str(spec.get("initial_stdin", "")),
            block_run_id=str(spec.get("block_run_id", "")),
            permission_mode=str(spec.get("permission_mode", "safe")),
            run_dir_path=(str(spec["run_dir_path"]) if spec.get("run_dir_path") else None),
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "cap" in msg.lower():
            # 503 — soft failure surface that the worker can interpret
            # as "queue and retry later" if it cared to.
            raise HTTPException(status_code=503, detail=msg) from exc
        return {"tab_id": None, "error": msg}
    except Exception as exc:
        logger.exception("internal_request_tab: spawn failed")
        return {"tab_id": None, "error": str(exc)}

    return {"tab_id": tab_id, "error": None}


@router.post("/pty/internal/notify", status_code=204)
async def _internal_notify(
    payload: _BodyDict,
    x_scieasy_ipc_token: _HeaderToken = None,
) -> None:
    """Engine-internal endpoint: AI Block worker reports completion.

    Fire-and-forget on the worker side. We update the tab→run map and
    broadcast a ``block_pty_closed`` frame so the frontend can decorate
    the tab title with status ✓/✗ per ADR-035 §3.9. The PTY itself
    stays open (per ADR-035 §3.9: "tab survives DONE/ERROR").
    """
    _check_ipc_token(x_scieasy_ipc_token)

    if payload.get("type") != "notify_block_pty_event":
        raise HTTPException(status_code=400, detail="payload.type must be 'notify_block_pty_event'")
    block_run_id = payload.get("block_run_id")
    event = payload.get("event")
    if not isinstance(block_run_id, str) or not block_run_id:
        raise HTTPException(status_code=400, detail="block_run_id must be a non-empty string")
    if event not in ("completed", "cancelled_by_user_close", "error"):
        raise HTTPException(status_code=400, detail=f"unknown event {event!r}")

    # Resolve tab_id from the run_id — best effort; the broadcast still
    # carries block_run_id so the frontend can match independently.
    tab_id = None
    for tid, rid in _engine_tab_to_run.items():
        if rid == block_run_id:
            tab_id = tid
            break

    detail = payload.get("detail") or {}
    message = {
        "type": "block_pty_closed",
        "block_run_id": block_run_id,
        "tab_id": tab_id,
        "event": event,
        "detail": detail if isinstance(detail, dict) else {},
    }
    await broadcast_ai_pty_message(message)
    logger.info(
        "internal_notify: block_run_id=%s event=%s tab_id=%s",
        block_run_id,
        event,
        tab_id,
    )
