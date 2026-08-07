"""ADR-035 §3.10 — server-side (pre-spawned) PTY tab opens.

The existing ``WS /api/ai/pty/{tab_id}`` route in :mod:`._websocket` is
the **user-launched** path: the frontend connects, the route validates
query params, spawns the PTY, pumps bytes both ways. That route is
FROZEN per ADR-034 — do not modify.

This module adds the SECOND path, where the PTY exists *before* any
WebSocket does. Two features use it, through one shared body
(:func:`_open_prespawned_tab`):

* **AI Block** (ADR-035 §3.10) — the worker calls
  :func:`scistudio.engine.pty_control.request_pty_tab` → the engine
  consults the internal HTTP route to allocate a tab from the inside
  and returns the ``tab_id`` to the worker. The frontend then receives
  a ``block_pty_opened`` WS frame on the main workflow WS and connects
  to the tab via the existing user-launched route, just like it would
  for a hand-launched tab. See :func:`open_engine_initiated_tab`.

* **Bring In My Work** (ADR-053 FR-022) — ``POST
  /api/work-import/sessions`` writes the session brief, then opens the
  session's PTY here and returns the ``tab_id`` in its own HTTP
  response, so no broadcast is needed. See
  :func:`open_work_import_tab`.

Sharing one body is what makes ADR-053 FR-022 literally true: work
import runs its agent through the mechanism the AI Block already uses
rather than introducing a second way to run an agent. What it does
**not** share is AI Block control semantics — the ``_engine_tab_to_run``
/ ``_engine_run_to_run_dir`` maps that carry block cancel and mark-done
frames are populated only when a ``block_run_id`` is supplied, which a
work-import tab never does.

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

from scistudio.ai.agent.providers_registry import agent_keys
from scistudio.api.routes.ai_pty import _state as _pkg
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


def _open_prespawned_tab(
    *,
    provider: str,
    cwd: str,
    prompt: str,
    permission_mode: str,
    extra_env: dict[str, str] | None = None,
    block_run_id: str | None = None,
    run_dir_path: str | None = None,
) -> str:
    """Validate, cap-check, spawn, stamp and register one server-side PTY.

    The single body behind every pre-spawned tab. Returns the fresh
    ``tab_id`` the frontend then connects with.

    Steps (ADR-035 §3.10):

      1. Reject a ``cwd`` that is not an existing absolute directory, a
         ``permission_mode`` outside ``safe`` | ``bypass``, and a
         ``provider`` outside the registry's agent keys. A bad provider
         key must fail loudly rather than silently fall back to
         claude-code, which is what the deleted argv-basename sniffing
         did. The accepted set is registry-derived, so a sixth provider
         needs no edit here (ADR-034 FR-001, FR-010, FR-011).
      2. Bail with :class:`RuntimeError` if ``len(_active_ptys) >=
         MAX_ACTIVE_PTYS`` (ADR-034 §8 cap).
      3. Spawn through the same registry-driven ``_spawn`` dispatch the
         user-launched route uses — the agent must not be able to tell
         the tab was opened server-side rather than user-side. The
         spawn helpers derive every argv element, including the
         system-prompt and MCP-config arguments and the provider's own
         bypass-flag spelling, from that provider's registry descriptor.
      4. Stamp ``_engine_prespawned`` **before** registering in
         ``_active_ptys``: that marker is what ``pty_endpoint``'s join
         branch reads, and a WS connecting between the insert and the
         stamp would spawn a second agent over the top of this one.
      5. Register under a fresh ``tab_id`` so the frontend's subsequent
         WS connect joins the existing PTY instead of spawning.

    ``prompt`` is delivered to the agent as a positional CLI argument by
    the spawn helpers rather than typed into the TUI over stdin (#1789):
    a raw-mode agent TUI ignores the trailing carriage return, so a typed
    prompt sat unsubmitted and the agent never ran.

    ``block_run_id`` is the AI-Block-only part. When supplied, the tab is
    additionally registered in the block-run maps that carry the AI
    Block's cancel / mark-done control frames, and the AI-Block metadata
    is stamped on the PTY. A caller that passes ``None`` — Bring In My
    Work — gets an ordinary chat session (ADR-053 FR-025) with none of
    those semantics attached.
    """
    cwd_path = Path(cwd)
    if not cwd_path.is_absolute() or not cwd_path.is_dir():
        raise RuntimeError(f"pre-spawned PTY tab: cwd must be an existing absolute dir, got {cwd!r}")

    if permission_mode not in ("safe", "bypass"):
        raise RuntimeError(f"pre-spawned PTY tab: permission_mode must be 'safe'|'bypass', got {permission_mode!r}")

    accepted = agent_keys()
    if provider not in accepted:
        raise RuntimeError(f"pre-spawned PTY tab: unknown provider {provider!r}; expected one of {sorted(accepted)}")

    # Cap check — same limit as the user-launched route; plain dict access
    # is safe because we are not on the asyncio loop here.
    if len(_pkg._active_ptys) >= _pkg.MAX_ACTIVE_PTYS:
        raise RuntimeError(f"pre-spawned PTY tab: PTY cap ({_pkg.MAX_ACTIVE_PTYS}) reached")

    pty = _pkg._spawn(
        provider=provider,
        project_dir=cwd_path,
        dangerous=permission_mode == "bypass",
        extra_env=extra_env or None,
        prompt=prompt,
    )

    # Provider-neutral marker: this PTY already exists, so a WS arriving
    # for its tab_id must join rather than spawn. Stamped for every
    # pre-spawned tab, AI Block or not.
    pty._engine_prespawned = True  # type: ignore[attr-defined]
    if block_run_id is not None:
        # AI-Block-only metadata. The prompt was delivered as a spawn
        # argument above, so there is nothing left to replay over stdin.
        pty._engine_initial_stdin = ""  # type: ignore[attr-defined]
        pty._engine_block_run_id = block_run_id  # type: ignore[attr-defined]

    tab_id = uuid.uuid4().hex[:12]
    _pkg._active_ptys[tab_id] = pty
    if block_run_id is not None:
        _pkg._engine_tab_to_run[tab_id] = block_run_id
        if run_dir_path:
            _pkg._engine_run_to_run_dir[block_run_id] = Path(run_dir_path)

    return tab_id


def open_work_import_tab(
    *,
    provider: str,
    cwd: str,
    opening_message: str,
    permission_mode: str,
) -> str:
    """Open the Bring In My Work session PTY (ADR-053 FR-022, FR-028, FR-029).

    Called by ``POST /api/work-import/sessions`` *after* the session
    brief has been written and closed (FR-024). Returns the ``tab_id``
    the endpoint hands back to the caller, which connects the existing
    ``WS /api/ai/pty/{tab_id}`` route and joins this PTY. No
    ``block_pty_opened`` broadcast is emitted and no new frame type is
    introduced: unlike an AI Block tab, the frontend initiated this
    request and already holds the ``tab_id``.

    ``opening_message`` is the single line the user sees when the
    session starts (FR-028). It is delivered exactly as the AI Block's
    prompt is — a positional CLI argument on the spawned agent — which
    is what keeps delivery independent of a provider's system-prompt
    capability (FR-029). Only ``claude-code`` is ``FLAG_FILE`` in the
    ADR-034 registry; ``codex``, ``kimi-code`` and both Qoder channels
    are ``AMBIENT`` and have no per-session prompt channel at all, so
    routing the brief through a file plus this pointer is what makes
    that difference invisible.

    It does **not** make every provider equivalent. Being a positional
    argument, the pointer cannot reach a CLI that parses its first
    positional as a subcommand; ``kimi-code`` does, and the registry
    records it as ``prompt_argv_prefix is None``. ``spawn_agent`` raises
    ``ValueError`` for those rather than launching an agent with no
    instructions, so callers must refuse such a provider before they get
    here — ``POST /api/work-import/sessions`` does, via
    :func:`~scistudio.ai.agent.availability.session_unsupported_reason`,
    and the AI Block does the same at config time.

    Args:
        provider: A registry agent key (ADR-034 FR-010).
        cwd: The project directory, absolute and existing.
        opening_message: The one-line pointer at the brief file.
        permission_mode: ``"safe"`` or ``"bypass"`` — the backend
            spelling. The frontend union is ``"safe" | "dangerous"`` and
            is mapped at the request boundary, not here.

    Returns:
        The freshly allocated ``tab_id``.

    Raises:
        RuntimeError: Invalid ``cwd``, ``permission_mode`` or
            ``provider``, or the PTY cap is already reached.
    """
    tab_id = _open_prespawned_tab(
        provider=provider,
        cwd=cwd,
        prompt=opening_message,
        permission_mode=permission_mode,
    )
    logger.info(
        "open_work_import_tab: tab_id=%s provider=%s permission=%s",
        tab_id,
        provider,
        permission_mode,
    )
    return tab_id


def open_engine_initiated_tab(
    *,
    title: str,
    provider: str,
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

    Implementation per ADR-035 §3.10. Validation, the ADR-034 §8 cap
    check, the registry-driven ``_spawn`` dispatch, the PTY stamping and
    the ``_active_ptys`` registration all live in
    :func:`_open_prespawned_tab`, which Bring In My Work shares so that
    ADR-053 FR-022 holds literally. What stays here is what is specific
    to the AI Block: the ``SCISTUDIO_AI_BLOCK_RUN_DIR`` export, the
    block-run maps (populated by the helper from ``block_run_id``), and
    the ``block_pty_opened`` broadcast that tells the frontend to open a
    tab it did not ask for.

    The ``initial_stdin`` arg is delivered to the agent as a positional
    CLI argument at spawn (#1789), not replayed over stdin.
    """
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

    tab_id = _open_prespawned_tab(
        provider=provider,
        cwd=cwd,
        prompt=initial_stdin,
        permission_mode=permission_mode,
        extra_env=extra_env or None,
        block_run_id=block_run_id,
        run_dir_path=run_dir_path,
    )

    # ADR-034 FR-020c / FR-022: carry the provider the engine actually
    # spawned. The frontend previously hardcoded ``claude-code`` on
    # engine-initiated tabs because the payload never told it otherwise.
    message = {
        "type": "block_pty_opened",
        "tab_id": tab_id,
        "title": title,
        "block_run_id": block_run_id,
        "permission_mode": permission_mode,
        "provider": provider,
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
