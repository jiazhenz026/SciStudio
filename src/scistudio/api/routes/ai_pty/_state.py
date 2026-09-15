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
import functools
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from scistudio.ai.agent.providers_registry import REGISTRY, ProviderKind
from scistudio.ai.agent.terminal import PtyProcess, spawn_agent, spawn_user_terminal

# Public router shared by every sub-module's route decorators.
router = APIRouter(prefix="/api/ai", tags=["ai"])

# Resource cap — ADR-034 §3 spec. Module-level so a 17th connection
# attempt sees the live count regardless of which worker handles it.
MAX_ACTIVE_PTYS = 16

_active_ptys: dict[str, PtyProcess] = {}
_active_lock = asyncio.Lock()

_ProviderSpawner = Callable[..., PtyProcess]
"""Uniform spawner signature: keyword-only ``project_dir``, ``dangerous``, ``auto``, ``cols``,
``rows``, ``extra_env``, ``prompt``, and the ``_spawn_argv`` test seam."""

# ADR-034 FR-006: both of these are *derived* from the provider registry rather
# than hand-maintained. They used to be two literals that had to be edited in
# lockstep with ``terminal.py``, ``routes/ai.py``, and the AI Block enum every
# time a provider was added — the duplication ADR-034's registry exists to
# remove. Adding a sixth provider is now a registry row and nothing here.
#
# ``_VALID_PROVIDERS`` is the WebSocket query whitelist (FR-023), so it spans the
# *whole* registry including the ``user-terminal`` pseudo-provider; the agent-only
# view (``agent_keys()``) is what ``GET /api/ai/status`` uses. The AI Block enum
# is narrower still: it filters the agent keys down to the providers that can
# carry an AI Block task (#2014).
_VALID_PROVIDERS: tuple[str, ...] = REGISTRY.keys()

# ``functools.partial`` binds the descriptor, leaving the uniform keyword-only
# spawner signature ``_spawn`` calls. There is deliberately no
# ``terminal.spawn_provider(key, …)`` helper to build this map: such a wrapper
# would re-forward every keyword argument and duplicate ``_spawn`` verbatim.
_PROVIDER_SPAWNERS: dict[str, _ProviderSpawner] = {
    descriptor.key: (
        spawn_user_terminal if descriptor.kind is ProviderKind.TERMINAL else functools.partial(spawn_agent, descriptor)
    )
    for descriptor in REGISTRY
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


# ---------------------------------------------------------------------------
# ``ai_chat_disabled`` agent-session policy (ADR-055 Spec 4 FR-006)
#
# An edition that declares the ``ai_chat_disabled`` capability hides the AI
# Chat surface, and the backend must match: every PTY session whose provider is
# agent-kind in the registry is refused before anything is spawned. The
# Terminal (``user-terminal``, TERMINAL-kind) is never gated, and neither is a
# tutorial replay, which spawns nothing and is joined under ``user-terminal``.
#
# The policy is process-wide like the rest of this module's state, because the
# pre-spawned paths (AI Block, Bring In My Work) run without a request or app
# in hand. The application lifespan sets it from ``app.state.capabilities`` at
# startup and clears it at teardown. It is a default and an administrator
# policy, not a security boundary: from the Terminal a user can run any CLI
# they install in their own account.
# ---------------------------------------------------------------------------

#: Tab ids the user-launched PTY WebSocket refuses. Each is a literal segment
#: another route family owns under ``/api/ai/pty/``: ``internal`` is the
#: self-authenticating worker callback prefix (``internal_routes``), and a tab
#: with that id would put the terminal route on the prefix's own path (#2322
#: audit P1-1). Compared case-insensitively.
RESERVED_TAB_IDS: frozenset[str] = frozenset({"internal"})

_agent_sessions_disabled = False


class AgentSessionsDisabledError(RuntimeError):
    """An agent-kind PTY session was requested while ``ai_chat_disabled`` is set."""


def _set_agent_sessions_disabled(disabled: bool) -> None:
    """Turn the ``ai_chat_disabled`` refusal of agent-kind providers on or off."""
    global _agent_sessions_disabled
    _agent_sessions_disabled = bool(disabled)


def agent_session_refusal(provider: str) -> str | None:
    """Return why a session for *provider* is refused, or ``None`` when it may start.

    Refuses only while ``ai_chat_disabled`` is set, and only agent-kind
    providers. An unknown key returns ``None``: the callers reject it
    themselves against the registry, with their own message.
    """
    if not _agent_sessions_disabled or provider not in REGISTRY:
        return None
    descriptor = REGISTRY.get(provider)
    if descriptor.kind is not ProviderKind.AGENT:
        return None
    return (
        f"AI agent sessions are turned off on this server (ai_chat_disabled), so {descriptor.label} "
        "was not started. The Terminal still opens a shell."
    )


def _spawn(
    *,
    provider: str,
    project_dir: Path,
    dangerous: bool,
    auto: bool = False,
    cols: int = 120,
    rows: int = 30,
    extra_env: dict[str, str] | None = None,
    prompt: str = "",
) -> PtyProcess:
    spawner = _PROVIDER_SPAWNERS.get(provider)
    if spawner is None:
        raise ValueError(f"Unknown provider {provider!r}")
    # Backstop for the ``ai_chat_disabled`` policy: every spawn path checks it
    # before reaching here, and the provider dispatch refuses as well, so a
    # future caller that forgets the check still spawns nothing.
    refusal = agent_session_refusal(provider)
    if refusal is not None:
        raise AgentSessionsDisabledError(refusal)
    return spawner(
        project_dir=project_dir,
        dangerous=dangerous,
        auto=auto,
        cols=cols,
        rows=rows,
        extra_env=extra_env,
        prompt=prompt,
    )
