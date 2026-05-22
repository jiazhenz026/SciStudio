"""ADR-035 §3.10 — engine-initiated PTY tab open.

The existing ``WS /api/ai/pty/{tab_id}`` route in :mod:`._websocket` is
the **user-launched** path: the frontend connects, the route validates
query params, spawns the PTY, pumps bytes both ways. That route is
FROZEN per ADR-034 — do not modify.

This module adds the SECOND, engine-initiated path: the AI Block
worker calls :func:`scistudio.engine.pty_control.request_pty_tab` →
the engine consults the internal HTTP route to allocate a tab from the
inside (no incoming WS connection yet) and returns the ``tab_id`` to
the worker. The frontend then receives a ``block_pty_opened`` WS frame
on the main workflow WS and connects to the tab via the existing
user-launched route, just like it would for a hand-launched tab.

Mutable seams (``_spawn``, ``MAX_ACTIVE_PTYS``, ``_active_ptys``,
``_engine_tab_to_run``, ``_engine_run_to_run_dir``) are looked up on
the package namespace at call time so monkeypatching them on
``scistudio.api.routes.ai_pty`` keeps working — pre-existing test
contract.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from scistudio.api.routes import ai_pty as _pkg
from scistudio.api.routes.ai_pty.subscribers import broadcast_ai_pty_message

logger = logging.getLogger(__name__)


def get_run_dir_for_block_run(block_run_id: str) -> Path | None:
    """Return the run_dir path registered for *block_run_id*, or None.

    Used by ``scistudio.api.ws`` to handle the ``block_user_marked_done``
    inbound WS frame (ADR-035 §3.5 path c) without bringing the AI Block
    module into the WS layer's import surface.
    """
    return _pkg._engine_run_to_run_dir.get(block_run_id)


def get_block_run_id_for_tab(tab_id: str) -> str | None:
    """Return the block_run_id mapped to *tab_id*, or None.

    Inverse of the implicit map written by :func:`open_engine_initiated_tab`;
    used by ``scistudio.api.ws`` to translate ``block_user_cancel`` frames
    addressed by tab_id into a CANCEL_BLOCK_REQUEST keyed by block_run_id.
    """
    return _pkg._engine_tab_to_run.get(tab_id)


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
    :func:`scistudio.engine.pty_control.request_pty_tab`). Returns the
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
    if len(_pkg._active_ptys) >= _pkg.MAX_ACTIVE_PTYS:
        raise RuntimeError(f"open_engine_initiated_tab: PTY cap ({_pkg.MAX_ACTIVE_PTYS}) reached")

    # ADR-035 §3.5 path (a): export SCISTUDIO_AI_BLOCK_RUN_DIR into the PTY
    # so the spawned mcp-bridge subprocess (which the agent invokes via
    # --mcp-config <project>/.scistudio/mcp.json) can resolve the active
    # AI Block run dir for ``finish_ai_block``. Without this, the tool
    # always returns ``not_in_ai_block_context`` because no other layer
    # propagates this context — workers' env is set by uvicorn and is
    # not per-AI-Block; only the PTY-spawn site knows which block_run_id
    # we are about to attach to.
    extra_env: dict[str, str] = {}
    if run_dir_path:
        extra_env["SCISTUDIO_AI_BLOCK_RUN_DIR"] = str(run_dir_path)

    pty = _pkg._spawn(
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
    _pkg._active_ptys[tab_id] = pty
    _pkg._engine_tab_to_run[tab_id] = block_run_id
    if run_dir_path:
        _pkg._engine_run_to_run_dir[block_run_id] = Path(run_dir_path)

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
