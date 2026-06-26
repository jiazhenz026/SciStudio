"""User-launched PTY WebSocket route (ADR-034 Phase 1.2).

Owns ``WS /api/ai/pty/{tab_id}`` — the route that accepts the frontend
connection, validates query params, JOINs an engine-pre-spawned PTY
(ADR-035 §3.10) or spawns a fresh one, runs two concurrent pump tasks
(PTY → WS and WS → PTY), and tears down the subprocess tree on
disconnect.

Mutable seams (``_spawn``, ``MAX_ACTIVE_PTYS``, ``_active_ptys``,
``_active_lock``, ``_engine_tab_to_run``, ``_engine_run_to_run_dir``,
``_VALID_PROVIDERS``) are looked up on the package namespace at call
time so monkeypatching them on ``scistudio.api.routes.ai_pty`` keeps
working — pre-existing test contract.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import logging
import threading

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from scistudio.ai.agent.terminal import PtyProcess
from scistudio.api.routes.ai_pty import _state as _pkg
from scistudio.api.routes.ai_pty.validation import _validate_project_dir

logger = logging.getLogger(__name__)

# #1789: the engine-supplied prompt must be typed into the agent's TUI only
# after that TUI is up and reading input. We wait for the child's first output
# (it has started drawing), then settle briefly before typing. If the child
# never produces output we still type after the timeout so a quiet provider is
# not stuck forever.
_INITIAL_STDIN_READY_TIMEOUT = 5.0
_INITIAL_STDIN_SETTLE_SECONDS = 0.4


async def _replay_initial_stdin(pty: PtyProcess, first_output: asyncio.Event, text: str) -> None:
    """Type the engine-supplied prompt into the agent TUI, once it is ready.

    #1789: claude-code / codex run a full-screen, raw-mode TUI. Writing the prompt
    the instant the WS connects landed it before the TUI's input loop existed
    (codex printed it above its header) and the prompt ended in an LF, which a
    raw-mode TUI does not treat as Enter — so claude-code left the text sitting
    unsent in its input box. Wait for the child's first output (TUI is drawing)
    with a timeout fallback, settle briefly, then write the body followed by a
    carriage return (``\\r``) — the byte a real Enter key sends — so the agent
    actually submits and starts running.
    """
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(first_output.wait(), timeout=_INITIAL_STDIN_READY_TIMEOUT)
    await asyncio.sleep(_INITIAL_STDIN_SETTLE_SECONDS)
    # Strip any trailing newline from the composed body and submit with a single
    # carriage return so the agent sees exactly one Enter, not an LF (ignored by
    # the TUI) followed by a stray blank line.
    body = text.rstrip("\r\n")
    try:
        pty.write(body.encode("utf-8", errors="replace"))
        pty.write(b"\r")
    except Exception:  # pragma: no cover - PTY may have died before replay
        logger.warning("engine-initiated PTY: failed to replay initial stdin", exc_info=True)


@_pkg.router.websocket("/pty/{tab_id}")  # type: ignore[has-type]
async def pty_endpoint(websocket: WebSocket, tab_id: str) -> None:
    """Accept the WS, validate params, spawn PTY, pump until close."""
    await websocket.accept()

    # ---- Validate query parameters -----------------------------------------
    params = websocket.query_params
    provider = params.get("provider", "")
    project_dir_raw = params.get("project_dir", "")
    dangerous_raw = params.get("dangerous", "false").lower()
    initial_cols = _parse_initial_size(params.get("cols"), default=120, min_value=1, max_value=1000)
    initial_rows = _parse_initial_size(params.get("rows"), default=30, min_value=1, max_value=500)

    if provider not in _pkg._VALID_PROVIDERS:
        await _send_error(
            websocket,
            f"Invalid provider {provider!r}; expected one of {_pkg._VALID_PROVIDERS}.",
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
    async with _pkg._active_lock:
        candidate = _pkg._active_ptys.get(tab_id)
        if candidate is not None and getattr(candidate, "_engine_block_run_id", None):
            existing_pty = candidate

    # #1789: when joining an engine-pre-spawned PTY, the engine-supplied prompt
    # is replayed exactly once — but only after the agent TUI is ready (see the
    # deferred ``replay_initial_stdin`` task below). We claim the sentinel here
    # so a StrictMode dev re-mount or reconnect cannot double-replay, and defer
    # the actual write until the pumps are running and first output is seen.
    pending_initial_stdin: str | None = None
    if existing_pty is not None:
        pty = existing_pty
        # #1789: the engine pre-spawns this PTY before any WS connects, so it was
        # sized at the default 120x30 — not the frontend's real viewport. Without
        # correcting it on join, the agent TUI keeps drawing at 120x30 while xterm
        # renders at the fitted size, so the display is garbled and, when the pane
        # is later enlarged, the TUI content still only fills the stale small grid.
        # Resize the joined PTY to the connecting client's size so the baseline is
        # correct from the first frame; later ResizeObserver-driven resizes flow
        # through the normal ``resize`` frames.
        with contextlib.suppress(Exception):
            pty.resize(cols=initial_cols, rows=initial_rows)
        initial_stdin = getattr(pty, "_engine_initial_stdin", None)
        already_replayed = getattr(pty, "_engine_initial_stdin_sent", False)
        if initial_stdin and not already_replayed:
            pending_initial_stdin = initial_stdin
            pty._engine_initial_stdin_sent = True  # type: ignore[attr-defined]
    else:
        # ---- Resource cap --------------------------------------------------
        async with _pkg._active_lock:
            if len(_pkg._active_ptys) >= _pkg.MAX_ACTIVE_PTYS:
                # Note: send + close while still holding the lock would
                # serialise rejections; safe because send_json is fast and
                # holding the lock guarantees the count snapshot we report.
                await _send_error(
                    websocket,
                    f"max {_pkg.MAX_ACTIVE_PTYS} active terminals — close an existing tab and retry.",
                )
                await websocket.close()
                return

        # ---- Spawn PTY -----------------------------------------------------
        try:
            pty = _pkg._spawn(
                provider=provider,
                project_dir=project_dir,
                dangerous=dangerous,
                cols=initial_cols,
                rows=initial_rows,
            )
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

        async with _pkg._active_lock:
            _pkg._active_ptys[tab_id] = pty

    # ---- Pump tasks --------------------------------------------------------
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    # #1789: set once the child has produced its first output, i.e. its TUI is
    # drawing and ready to receive typed input. Gates the initial-prompt replay.
    first_output = asyncio.Event()

    async def pump_pty_to_ws() -> None:
        """Forward PTY stdout to WS as ``{type:stdout,data:...}`` frames."""
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            while not stop.is_set():
                # Use an executor — :meth:`PtyProcess.read` blocks up to
                # ~100 ms which would stall the event loop otherwise.
                data = await loop.run_in_executor(None, pty.read, 0.1)
                # PTY reads are arbitrary byte chunks. Decode incrementally so
                # multibyte UTF-8 glyphs used by TUIs can span reads without
                # being replaced by U+FFFD.
                if data:
                    first_output.set()
                    if not await _send_stdout_frame(websocket, decoder.decode(data)):
                        break
                if not pty.is_alive():
                    break
            await _send_stdout_frame(websocket, decoder.decode(b"", final=True))
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
    task_replay = (
        asyncio.create_task(_replay_initial_stdin(pty, first_output, pending_initial_stdin))
        if pending_initial_stdin is not None
        else None
    )

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
        _pkg._active_ptys.pop(tab_id, None)
        # ADR-035: also drop the engine-side tab→run map entry so a
        # subsequent run does not see a stale block_run_id pointer.
        run_id_for_cleanup = _pkg._engine_tab_to_run.pop(tab_id, None)
        if run_id_for_cleanup is not None:
            _pkg._engine_run_to_run_dir.pop(run_id_for_cleanup, None)
        task_out.cancel()
        task_in.cancel()
        if task_replay is not None:
            task_replay.cancel()

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


async def _send_stdout_frame(websocket: WebSocket, text: str) -> bool:
    """Best-effort send of a stdout frame, returning false after close races."""
    if not text:
        return True
    if websocket.client_state != WebSocketState.CONNECTED:
        # Client closed already (StrictMode dev double-mount, tab close, etc.)
        # — abort cleanly instead of letting send_json explode.
        return False
    try:
        await websocket.send_json({"type": "stdout", "data": text})
    except RuntimeError:
        # ASGI race: client_state can flip between the check above and the send
        # when uvicorn flushes a close frame concurrently.
        return False
    return True


def _parse_initial_size(value: str | None, *, default: int, min_value: int, max_value: int) -> int:
    """Parse optional initial PTY dimensions from the frontend handshake."""
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(parsed, max_value))
