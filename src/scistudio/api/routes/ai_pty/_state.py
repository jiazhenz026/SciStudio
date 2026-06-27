"""Module-level shared state and the provider-dispatch seam for ``ai_pty``.

Round-4 no-cycles: the PTY registry, locks, router, constants, and the
``_spawn`` provider-dispatch seam used to live in the package ``__init__``.
Every sub-module (``engine``, ``internal_routes``, ``subscribers``,
``websocket``) read them back via ``from ... import ai_pty as _pkg`` — a
child -> parent import that closed an at-import cycle around the package
facade. The indirection existed so package-level
``monkeypatch.setattr(ai_pty, "<name>", ...)`` seams resolve at call time.

Hosting the shared state in this leaf module — which imports nothing from
its own package — breaks the cycle: sub-modules import ``_state`` instead
of the package, and the package ``__init__`` re-exports every symbol so the
historical ``scistudio.api.routes.ai_pty.<name>`` public surface is
unchanged. The test monkeypatch seams move from the package to this module
(``monkeypatch.setattr(ai_pty._state, "<name>", ...)``).

This module MUST NOT import from any ``scistudio.api.routes.ai_pty``
sibling — that constraint is what makes it a safe cycle-breaking leaf.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from scistudio.ai.agent.terminal import PtyProcess, spawn_claude, spawn_codex, spawn_user_terminal

# Public router shared by every sub-module's route decorators.
router = APIRouter(prefix="/api/ai", tags=["ai"])

# Resource cap — ADR-034 §3 spec. Module-level so a 17th connection
# attempt sees the live count regardless of which worker handles it.
MAX_ACTIVE_PTYS = 16

_active_ptys: dict[str, PtyProcess] = {}
_active_lock = asyncio.Lock()

_VALID_PROVIDERS = ("claude-code", "codex", "user-terminal")
_PROVIDER_SPAWNERS = {
    "claude-code": spawn_claude,
    "codex": spawn_codex,
    "user-terminal": spawn_user_terminal,
}

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


def _spawn(
    *,
    provider: str,
    project_dir: Path,
    dangerous: bool,
    cols: int = 120,
    rows: int = 30,
    extra_env: dict[str, str] | None = None,
    prompt: str = "",
) -> PtyProcess:
    spawner = _PROVIDER_SPAWNERS.get(provider)
    if spawner is None:
        raise ValueError(f"Unknown provider {provider!r}")
    return spawner(
        project_dir=project_dir,
        dangerous=dangerous,
        cols=cols,
        rows=rows,
        extra_env=extra_env,
        prompt=prompt,
    )
