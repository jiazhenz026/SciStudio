"""WebSocket route hosting the PTY-tab embedded agent (ADR-034 Phase 1.2).

This package exposes a single endpoint:

    ``ws://host/api/ai/pty/{tab_id}?project_dir=<urlencoded>&provider=<claude-code|codex>&dangerous=<true|false>``

The route validates query parameters, spawns the appropriate PTY via
:mod:`scistudio.ai.agent.terminal`, runs two concurrent pump tasks
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

ADR-035 (§3.10) extends this package — without modifying the existing
``WS /api/ai/pty/{tab_id}`` handler — with an engine-initiated tab-open
path. See :func:`open_engine_initiated_tab` and the
``/api/ai/pty/internal/*`` routes wired below.

Module layout (issue #1432 refactor of the original 757-LOC single
module):

* This ``__init__`` owns the :class:`fastapi.APIRouter` instance,
  module-level shared state (``MAX_ACTIVE_PTYS``, ``_active_ptys``,
  ``_active_lock``, ``_engine_tab_to_run``, ``_engine_run_to_run_dir``,
  ``_ai_pty_subscribers``, ``_ai_pty_subscribers_lock``), and the
  ``_spawn`` provider dispatch — all of which are monkeypatched by the
  existing test suite via attribute lookup on this package.
* :mod:`.websocket` — the user-launched WS handler (``pty_endpoint``)
  and its pump tasks.
* :mod:`.validation` — ``_validate_project_dir`` query-param hardening.
* :mod:`.subscribers` — the cross-WS broadcast registry that
  ``scistudio.api.ws`` subscribes to.
* :mod:`.engine` — engine-initiated tab open + tab/run lookup helpers.
* :mod:`.internal_routes` — IPC-token-guarded HTTP endpoints used by
  AI Block workers.

Sub-modules deliberately resolve mutable seams (``_spawn``,
``MAX_ACTIVE_PTYS``, ``_active_ptys``, ``_engine_tab_to_run``,
``_engine_run_to_run_dir``) by attribute lookup on this package so
``monkeypatch.setattr(ai_pty, "<name>", ...)`` continues to affect
the route handlers' behaviour — pre-existing test contract.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from scistudio.ai.agent.terminal import PtyProcess, spawn_claude, spawn_codex

# ---------------------------------------------------------------------------
# Public router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/ai", tags=["ai"])

# ---------------------------------------------------------------------------
# Module-level shared state (ADR-034 / ADR-035).
#
# Defined here (not in submodules) so the existing test suite's
# ``monkeypatch.setattr(ai_pty, "<name>", ...)`` calls keep working
# after the sub-package split. Sub-modules look these up at call time
# via the package namespace.
# ---------------------------------------------------------------------------

# Resource cap — ADR-034 §3 spec. Module-level so a 17th connection
# attempt sees the live count regardless of which worker handles it.
MAX_ACTIVE_PTYS = 16

_active_ptys: dict[str, PtyProcess] = {}
_active_lock = asyncio.Lock()

_VALID_PROVIDERS = ("claude-code", "codex")

# ADR-035 §3.10 — engine-initiated tab tracking.
# Map tab_id → block_run_id so completion notifies can resolve back.
_engine_tab_to_run: dict[str, str] = {}
# Map block_run_id → run_dir absolute path. Populated by
# :func:`open_engine_initiated_tab` so user-driven control frames
# (``block_user_marked_done`` per ADR-035 §3.5 path c) can locate the
# right run dir to write the ``signals/mark_done.json`` signal file
# without having to reach back into AIBlock or scan the filesystem.
_engine_run_to_run_dir: dict[str, Path] = {}

# ---------------------------------------------------------------------------
# WS subscriber registry
#
# The existing ``/ws`` workflow WS (in ``scistudio.api.ws``) carries
# EngineEvent traffic. ADR-035 needs to push two additional, NON-engine
# messages — ``block_pty_opened`` and ``block_pty_closed`` — without
# adding new EngineEvent types (per the dispatch's hard scope rule:
# "MAY emit existing events but MAY NOT add new event types").
#
# Resolution: maintain a small subscriber registry HERE. The workflow
# WS handler (``scistudio.api.ws``) registers a per-connection callback
# on accept and unregisters on disconnect. Engine-initiated tab
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


# ---------------------------------------------------------------------------
# Provider dispatch (test seam — monkeypatched by ai_pty test suite).
# ---------------------------------------------------------------------------


def _spawn(
    *,
    provider: str,
    project_dir: Path,
    dangerous: bool,
    extra_env: dict[str, str] | None = None,
) -> PtyProcess:
    """Dispatch to the right factory for ``provider``.

    Test hook: callers may monkeypatch this function (via
    ``monkeypatch.setattr(ai_pty, "_spawn", fake)``) to inject a fake
    PTY that runs an echo subprocess instead of the real claude / codex
    binary (the WS integration tests rely on this seam).

    ``extra_env`` lets engine-initiated callers thread per-AI-Block env
    (e.g. ``SCISTUDIO_AI_BLOCK_RUN_DIR`` for ``finish_ai_block``, ADR-035
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
# Submodule wiring
#
# Submodules are imported AFTER the module-level state above so their
# top-level ``from scistudio.api.routes import ai_pty as _pkg`` lookups
# see a package with the seams already bound. Submodules in turn
# register their HTTP / WS handlers on ``router`` at import time, and
# expose their public functions for re-export below.
# ---------------------------------------------------------------------------

# Importing ``internal_routes`` and ``websocket`` registers their
# route handlers on ``router`` as a side-effect of the decorators —
# the bare-module imports are kept (with ``F401`` waivers) so that
# side-effect is preserved.
from scistudio.api.routes.ai_pty import internal_routes, websocket  # noqa: E402, F401
from scistudio.api.routes.ai_pty.engine import (  # noqa: E402
    get_block_run_id_for_tab,
    get_run_dir_for_block_run,
    open_engine_initiated_tab,
)
from scistudio.api.routes.ai_pty.internal_routes import (  # noqa: E402
    _ensure_ipc_token as _ensure_ipc_token,
)
from scistudio.api.routes.ai_pty.subscribers import (  # noqa: E402
    broadcast_ai_pty_message,
    register_ai_pty_subscriber,
    unregister_ai_pty_subscriber,
)
from scistudio.api.routes.ai_pty.websocket import pty_endpoint  # noqa: E402

__all__ = [
    "MAX_ACTIVE_PTYS",
    "broadcast_ai_pty_message",
    "get_block_run_id_for_tab",
    "get_run_dir_for_block_run",
    "open_engine_initiated_tab",
    "pty_endpoint",
    "register_ai_pty_subscriber",
    "router",
    "unregister_ai_pty_subscriber",
]
