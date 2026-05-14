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
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from pathlib import Path

from fastapi import APIRouter, WebSocket
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

    # ---- Resource cap ------------------------------------------------------
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

    # ---- Spawn PTY ---------------------------------------------------------
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
                    await websocket.send_json({"type": "stdout", "data": data.decode("utf-8", errors="replace")})
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
    """
    target = Path(raw)
    if not target.is_absolute():
        raise RuntimeError(f"project_dir must be absolute, got {raw!r}.")
    resolved = target.resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"project_dir does not exist or is not a directory: {resolved}")

    ctx = get_optional_context()
    if ctx is not None and ctx.project_dir is not None:
        try:
            _safe_under(ctx.project_dir, resolved)
        except PermissionError as exc:
            raise PermissionError(
                f"project_dir {resolved} is outside the active project root {ctx.project_dir}"
            ) from exc
    return resolved


def _spawn(*, provider: str, project_dir: Path, dangerous: bool) -> PtyProcess:
    """Dispatch to the right factory for ``provider``.

    Test hook: callers may monkeypatch this function to inject a fake
    PTY that runs an echo subprocess instead of the real claude / codex
    binary (the WS integration tests rely on this seam).
    """
    if provider == "claude-code":
        return spawn_claude(project_dir=project_dir, dangerous=dangerous)
    if provider == "codex":
        return spawn_codex(project_dir=project_dir, dangerous=dangerous)
    # Defensive — guarded earlier in the route too.
    raise ValueError(f"Unknown provider {provider!r}")
