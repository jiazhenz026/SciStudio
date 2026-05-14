"""Worker ↔ engine PTY control IPC for ADR-035 (skeleton).

ADR-035 §3.10 introduces two new IPC events that flow from the AI Block
**worker subprocess** (running ``AIBlock.run()`` under
``scieasy.engine.runners.worker``) **back to the engine process**:

  1. :func:`request_pty_tab` — worker asks the engine to open a new
     PTY tab with a specific spawn argv. Engine allocates the tab,
     emits ``block_pty_opened`` to the frontend, returns ``tab_id``.
  2. :func:`notify_block_pty_event` — worker tells the engine that a
     completion / cancellation event happened so the engine can
     update lineage and emit the appropriate frontend WS message.

These are the **only** new wire-surface events introduced by ADR-035
(per §3.10 "These two control events are the only new wire surface").

The transport reuses the existing worker → engine IPC channel
(``scieasy.engine.runners.worker``) — do NOT introduce a new socket.

Skeleton invariants (per skeleton-agent.md):
    * Every function body raises ``NotImplementedError``.
    * Each is preceded by a docstring + structured implementation plan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)


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


def request_pty_tab(spec: PtyTabSpec) -> str:
    """Worker → engine: ask the engine to open a PTY tab; return tab_id.

    Blocks until the engine confirms tab spawned. The spawn happens via
    the existing ADR-034 PTY allocation logic in
    ``scieasy.ai.agent.terminal``; this function only adds the IPC layer
    that lets the worker subprocess trigger it.

    Implementation plan (per ADR-035 §3.10):
        1. From inside the worker subprocess, look up the IPC handle to
           the parent engine (provided by
           ``scieasy.engine.runners.worker`` at worker bootstrap).
        2. Send a structured IPC message:
           ``{"type": "request_pty_tab", "spec": <spec dict>}``.
        3. Block on the IPC reply queue with a sane timeout (e.g. 30s
           for spawn). Reply shape: ``{"tab_id": str, "error": str|None}``.
        4. If ``error`` is non-None → raise ``RuntimeError(error)``.
           Caller (AIBlock.run()) transitions the block to ERROR with
           the spawn exception per ADR-035 §3.8 run-time tier.
        5. Engine side (handler in ``scieasy.api.routes.ai_pty`` —
           sibling stub function): allocate tab via existing
           ``terminal.spawn_claude/codex`` builder, emit
           ``block_pty_opened`` WS event to frontend so AIChat
           auto-switches focus, return ``tab_id``.

    Edge cases:
        * Spawn timeout (engine never replies) → ``TimeoutError``.
        * Engine reports MAX_ACTIVE_PTYS exceeded (ADR-034 §8 cap of 16) →
          ``RuntimeError`` with explanatory message.
        * IPC channel closed (engine died) → ``BrokenPipeError``;
          worker should exit with non-zero so scheduler marks block ERROR.

    Test plan:
        * test_request_pty_tab_happy_path_returns_tab_id (with mock engine)
        * test_request_pty_tab_engine_error_raises (mock returns error reply)
        * test_request_pty_tab_timeout (mock engine never replies)
        * test_request_pty_tab_max_ptys_raises (mock returns cap-exceeded)

    References:
        ADR-035 §3.10 (IPC contract);
        ADR-034 §8 (MAX_ACTIVE_PTYS cap);
        src/scieasy/engine/runners/worker.py (existing IPC bootstrap);
        src/scieasy/api/routes/ai_pty.py (existing PTY route to be extended)
    """
    raise NotImplementedError("see comment block above")


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

    Implementation plan (per ADR-035 §3.10):
        1. Send IPC message ``{"type": "notify_block_pty_event",
           "block_run_id": ..., "event": ..., "detail": ...}``.
        2. Do NOT block on a reply — the worker proceeds with output
           validation while the engine processes the event in parallel.
        3. Best-effort: log + swallow IPC errors (the worker has
           already produced its outputs; lineage notification failure
           must not crash the worker).

    Edge cases:
        * IPC channel closed → log warning, return cleanly (engine will
          observe the worker's exit independently and reconcile).
        * Unknown ``event`` literal → ``ValueError`` (programmer error,
          fail loud).

    Test plan:
        * test_notify_completed_sends_correct_ipc_message
        * test_notify_cancelled_sends_correct_ipc_message
        * test_notify_error_includes_detail
        * test_notify_swallows_ipc_failure
        * test_notify_unknown_event_raises_ValueError

    References:
        ADR-035 §3.10 (IPC contract);
        ADR-035 §3.9 (state-machine — engine consumes these events to
        update tab UI without changing the block state itself).
    """
    raise NotImplementedError("see comment block above")
