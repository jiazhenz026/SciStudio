"""Worker ↔ engine PTY control IPC for ADR-035 (§3.10).

ADR-035 §3.10 introduces two control events that flow from the AI Block
**worker subprocess** (running ``AIBlock.run()`` under
``scieasy.engine.runners.worker``) **back to the engine process**:

  1. :func:`request_pty_tab` — worker asks the engine to open a new
     PTY tab with a specific spawn argv. Engine allocates the tab,
     emits ``block_pty_opened`` over the workflow WS, returns ``tab_id``.
  2. :func:`notify_block_pty_event` — worker tells the engine that a
     completion / cancellation event happened so the engine can update
     lineage and emit the appropriate frontend WS message.

These are the **only** new wire-surface events introduced by ADR-035
(per §3.10 "These two control events are the only new wire surface").

Transport
---------
The current worker→engine IPC channel is one-shot (stdin payload in,
stdout envelope out — see ``scieasy.engine.runners.worker``). A
bidirectional reply path does not exist. Per the ADR-035 implementation
brief (and to avoid touching ``engine/runners/`` which is frozen), this
module uses **HTTP loopback** to the engine's own FastAPI app:

  * The engine process exposes its own URL via the
    ``SCIEASY_ENGINE_API_URL`` environment variable (e.g.
    ``http://127.0.0.1:8000``). Worker subprocesses inherit this var.
  * The engine generates a per-process token in
    ``SCIEASY_ENGINE_IPC_TOKEN`` so opportunistic local processes
    cannot drive engine-initiated tabs.
  * The worker POSTs to two internal routes registered by
    ``scieasy.api.routes.ai_pty`` and authenticates with the token.

For unit tests that do not boot the FastAPI server, an in-process
override is exposed via :func:`set_in_process_handler` — tests register
a callable that receives the IPC payload directly.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public dataclass — wire shape for engine-initiated tab opens.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PtyTabSpec:
    """Spec for the PTY tab the engine should allocate (ADR-035 §3.10).

    Mirrors the existing ADR-034 spawn-argv shape — see
    ``scieasy.ai.agent.terminal.spawn_claude/spawn_codex``.

    Attributes
    ----------
    title
        Tab title shown in the AIChat panel header (e.g. ``"🤖 extract_metadata"``).
    spawn_argv
        Full argv list. Built by :meth:`AIBlock._build_spawn_argv`.
    cwd
        Project directory; the agent runs with this as its cwd. No
        ``--add-dir`` restriction — full filesystem reach per ADR-035 §3.7.
    initial_stdin
        First user-prompt line piped to the agent. References the
        manifest path under ``.scieasy/ai-block-runs/{run_id}/``.
    block_run_id
        Opaque ID linking this tab back to the AI Block run for lineage
        and for routing completion events back to the right worker.
    permission_mode
        ``"safe"`` or ``"bypass"``. Already encoded in ``spawn_argv``;
        kept here for the engine to label the tab UI badge.
    """

    title: str
    spawn_argv: list[str]
    cwd: str
    initial_stdin: str
    block_run_id: str
    permission_mode: Literal["safe", "bypass"]


# ---------------------------------------------------------------------------
# Test seam — in-process handler override.
#
# When set, :func:`request_pty_tab` and :func:`notify_block_pty_event`
# bypass the HTTP loopback transport and call this handler directly.
# Tests register a stub that records IPC calls and returns canned
# responses. Production never sets this — the env-var-driven HTTP
# transport is the live path.
# ---------------------------------------------------------------------------


_in_process_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def set_in_process_handler(handler: Callable[[dict[str, Any]], dict[str, Any]] | None) -> None:
    """Install a test override that intercepts IPC messages.

    The handler receives the message dict and returns a reply dict shaped
    the same as the engine's HTTP response payload. ``None`` removes the
    override (production default).
    """
    global _in_process_handler
    _in_process_handler = handler


def get_in_process_handler() -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    """Return the currently installed test handler, or ``None``."""
    return _in_process_handler


# ---------------------------------------------------------------------------
# Public API.
# ---------------------------------------------------------------------------


_DEFAULT_REQUEST_TIMEOUT_S = 30.0
"""Spawn timeout — claude/codex startup can take several seconds."""

_DEFAULT_NOTIFY_TIMEOUT_S = 5.0
"""Notify is fire-and-forget but we still cap the connect timeout."""


def request_pty_tab(spec: PtyTabSpec) -> str:
    """Worker → engine: ask the engine to open a PTY tab; return tab_id.

    Blocks until the engine confirms the tab spawned. The spawn happens
    via the existing ADR-034 PTY allocation logic in
    ``scieasy.ai.agent.terminal``; this function only carries the IPC
    that lets the worker subprocess trigger it.

    Implementation
    --------------
    1. If a test in-process handler is installed (see
       :func:`set_in_process_handler`), invoke it with the IPC message
       and return the ``tab_id`` from its reply.
    2. Otherwise, look up ``SCIEASY_ENGINE_API_URL`` (engine's own
       loopback URL — set by the engine at startup so workers inherit
       it). Missing → :class:`RuntimeError` with actionable message.
    3. POST to ``{API_URL}/api/ai/pty/internal/request-tab`` with the
       spec dict and the IPC token from ``SCIEASY_ENGINE_IPC_TOKEN``.
    4. Parse the JSON reply ``{"tab_id": str, "error": str|None}``.
       Non-None ``error`` → :class:`RuntimeError`. HTTP 503 (cap
       exceeded per ADR-034 §8) → :class:`RuntimeError` with cap message.

    Edge cases
    ----------
    * Spawn timeout (engine never replies) → :class:`TimeoutError`.
    * IPC channel closed (engine died) → :class:`BrokenPipeError`.
    * Missing env var → :class:`RuntimeError` with diagnostic.

    Raises
    ------
    RuntimeError
        On engine-reported error or missing IPC configuration.
    TimeoutError
        On HTTP timeout.
    BrokenPipeError
        On underlying connection failure.
    """
    payload = {"type": "request_pty_tab", "spec": asdict(spec)}

    if _in_process_handler is not None:
        reply = _in_process_handler(payload)
        return _consume_request_pty_tab_reply(reply)

    api_url = os.environ.get("SCIEASY_ENGINE_API_URL")
    if not api_url:
        raise RuntimeError(
            "request_pty_tab: SCIEASY_ENGINE_API_URL is not set. "
            "The engine process must export this env var so worker "
            "subprocesses can call back to allocate PTY tabs."
        )

    token = os.environ.get("SCIEASY_ENGINE_IPC_TOKEN", "")
    url = api_url.rstrip("/") + "/api/ai/pty/internal/request-tab"

    # httpx is already a project dependency (see pyproject.toml).
    import httpx

    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"X-SciEasy-IPC-Token": token},
            timeout=_DEFAULT_REQUEST_TIMEOUT_S,
        )
    except httpx.TimeoutException as exc:
        raise TimeoutError(f"request_pty_tab: engine HTTP timeout after {_DEFAULT_REQUEST_TIMEOUT_S}s") from exc
    except httpx.HTTPError as exc:
        raise BrokenPipeError(f"request_pty_tab: engine HTTP transport failed: {exc}") from exc

    if response.status_code == 503:
        # Cap-exceeded path (ADR-034 §8). Surface the engine's body verbatim.
        raise RuntimeError(f"request_pty_tab: engine refused (cap exceeded?): {response.text}")
    if response.status_code != 200:
        raise RuntimeError(f"request_pty_tab: engine returned HTTP {response.status_code}: {response.text}")

    try:
        reply = response.json()
    except ValueError as exc:
        raise RuntimeError(f"request_pty_tab: engine reply was not JSON: {response.text!r}") from exc
    return _consume_request_pty_tab_reply(reply)


def _consume_request_pty_tab_reply(reply: dict[str, Any]) -> str:
    """Validate the engine's reply and return the tab_id string."""
    if not isinstance(reply, dict):
        raise RuntimeError(f"request_pty_tab: engine reply must be a dict, got {type(reply).__name__}")
    error = reply.get("error")
    if error:
        raise RuntimeError(f"request_pty_tab: engine error: {error}")
    tab_id = reply.get("tab_id")
    if not isinstance(tab_id, str) or not tab_id:
        raise RuntimeError(f"request_pty_tab: missing tab_id in reply: {reply!r}")
    return tab_id


_VALID_NOTIFY_EVENTS = frozenset({"completed", "cancelled_by_user_close", "error"})


def notify_block_pty_event(
    block_run_id: str,
    event: Literal["completed", "cancelled_by_user_close", "error"],
    detail: dict[str, Any] | None = None,
) -> None:
    """Worker → engine: notify completion or cancellation of an AI Block PTY.

    Fire-and-forget (no reply expected). The engine uses this to:

      * update lineage records,
      * emit ``block_pty_closed`` (or status-update) WS frame to frontend,
      * decorate the tab title with ✓/✗ per ADR-035 §3.9.

    Implementation
    --------------
    1. Validate the ``event`` literal up-front (defensive — catches
       programmer error before any IPC happens).
    2. If a test in-process handler is installed, invoke it and return.
    3. Otherwise POST to
       ``{SCIEASY_ENGINE_API_URL}/api/ai/pty/internal/notify`` with the
       payload and the IPC token. Swallow + log all transport errors —
       the worker has already produced its outputs and a missed
       lineage notification must not crash the worker.

    Raises
    ------
    ValueError
        If ``event`` is not one of the documented literals.
    """
    if event not in _VALID_NOTIFY_EVENTS:
        raise ValueError(
            f"notify_block_pty_event: unknown event {event!r}; expected one of {sorted(_VALID_NOTIFY_EVENTS)}"
        )

    payload = {
        "type": "notify_block_pty_event",
        "block_run_id": block_run_id,
        "event": event,
        "detail": detail or {},
    }

    if _in_process_handler is not None:
        try:
            _in_process_handler(payload)
        except Exception:
            logger.warning("notify_block_pty_event: in-process handler raised", exc_info=True)
        return

    api_url = os.environ.get("SCIEASY_ENGINE_API_URL")
    if not api_url:
        # Best-effort: log + return. The worker already produced outputs;
        # a missing engine URL is an environment misconfiguration that
        # should not crash the data plane.
        logger.warning(
            "notify_block_pty_event: SCIEASY_ENGINE_API_URL is not set; skipping notify for run %s",
            block_run_id,
        )
        return

    token = os.environ.get("SCIEASY_ENGINE_IPC_TOKEN", "")
    url = api_url.rstrip("/") + "/api/ai/pty/internal/notify"

    import httpx

    try:
        httpx.post(
            url,
            json=payload,
            headers={"X-SciEasy-IPC-Token": token},
            timeout=_DEFAULT_NOTIFY_TIMEOUT_S,
        )
    except Exception:
        logger.warning("notify_block_pty_event: HTTP POST failed for run %s", block_run_id, exc_info=True)
