"""WebSocket route hosting the PTY-tab embedded agent (ADR-034 Phase 1.2).

This package exposes a single endpoint:

    ``ws://host/api/ai/pty/{tab_id}?project_dir=<urlencoded>&provider=<provider-key>&dangerous=<true|false>[&cols=<n>&rows=<n>]``

``provider`` accepts **every** key in the ADR-034 provider registry
(:data:`scistudio.api.routes.ai_pty._state._VALID_PROVIDERS`, derived from
:data:`scistudio.ai.agent.providers_registry.REGISTRY` per FR-006). At the
2026-08-06 verification date that set is::

    claude-code | codex | kimi-code | qoder | qoder-cn | user-terminal

That list is documentation of the registry's current contents, not a second
source of truth: a provider added to the registry is accepted here with no edit
to this package. An unrecognised ``provider`` is rejected with an ``error``
frame whose message enumerates the accepted set (FR-023).

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

ADR-035 (§3.10) extends this package with a **pre-spawned** tab-open
path, where the PTY exists before any WebSocket does. See
:func:`open_engine_initiated_tab` (AI Block) and the
``/api/ai/pty/internal/*`` routes wired below, plus
:func:`open_work_import_tab` (ADR-053 Bring In My Work, FR-022), which
shares the same spawn body. The user-launched handler above is
otherwise unchanged: it gained only a join predicate that recognises a
pre-spawned PTY by a provider-neutral marker instead of an
AI-Block-specific one, so both features join their own PTY rather than
starting a second agent over the top of it.

Module layout (issue #1432 refactor of the original 757-LOC single
module):

* :mod:`._state` owns the :class:`fastapi.APIRouter` instance,
  module-level shared state (``MAX_ACTIVE_PTYS``, ``_active_ptys``,
  ``_active_lock``, ``_engine_tab_to_run``, ``_engine_run_to_run_dir``,
  ``_ai_pty_subscribers``, ``_ai_pty_subscribers_lock``), and the
  ``_spawn`` provider dispatch. This ``__init__`` re-exports them so the
  public surface is unchanged.
* :mod:`.websocket` — the user-launched WS handler (``pty_endpoint``)
  and its pump tasks.
* :mod:`.validation` — ``_validate_project_dir`` query-param hardening.
* :mod:`.subscribers` — the cross-WS broadcast registry that
  ``scistudio.api.ws`` subscribes to.
* :mod:`.engine` — engine-initiated tab open + tab/run lookup helpers.
* :mod:`.internal_routes` — IPC-token-guarded HTTP endpoints used by
  AI Block workers.

Round-4 no-cycles: the shared seams moved out of this ``__init__`` into
the :mod:`._state` leaf so sub-modules resolve them via ``_state`` instead
of importing this package back (which closed an at-import cycle). The
mutable test seams (``_spawn``, ``MAX_ACTIVE_PTYS``, ``_active_ptys``,
``_engine_tab_to_run``, ``_engine_run_to_run_dir``) are monkeypatched on
:mod:`._state` (``monkeypatch.setattr(ai_pty._state, "<name>", ...)``);
``open_engine_initiated_tab`` is monkeypatched on :mod:`.engine`.
"""

from __future__ import annotations

# Importing ``internal_routes`` and ``websocket`` registers their route
# handlers on ``_state.router`` as a side-effect of the decorators — the
# bare-module imports are kept (with an ``F401`` waiver) so that side-effect
# is preserved.
from . import internal_routes, websocket  # noqa: F401

# Round-4 no-cycles: the shared state, router, constants, and the
# provider-dispatch seam live in the ``_state`` leaf module. Re-export every
# symbol here so the historical ``scistudio.api.routes.ai_pty.<name>`` public
# surface (and the package-level ``hasattr`` contract in
# ``tests/api/routes/ai_pty/test_public_surface.py``) is unchanged. The
# private seams are not in ``__all__``, hence the F401 waiver.
from ._state import (  # noqa: F401
    _PROVIDER_SPAWNERS,
    _VALID_PROVIDERS,
    MAX_ACTIVE_PTYS,
    _active_lock,
    _active_ptys,
    _ai_pty_subscribers,
    _ai_pty_subscribers_lock,
    _AiPtySubscriber,
    _engine_run_to_run_dir,
    _engine_tab_to_run,
    _spawn,
    router,
)
from .engine import (
    get_block_run_id_for_tab,
    get_run_dir_for_block_run,
    open_engine_initiated_tab,
    open_work_import_tab,
)
from .internal_routes import _ensure_ipc_token as _ensure_ipc_token
from .subscribers import (
    broadcast_ai_pty_message,
    register_ai_pty_subscriber,
    unregister_ai_pty_subscriber,
)
from .websocket import pty_endpoint

__all__ = [
    "MAX_ACTIVE_PTYS",
    "broadcast_ai_pty_message",
    "get_block_run_id_for_tab",
    "get_run_dir_for_block_run",
    "open_engine_initiated_tab",
    "open_work_import_tab",
    "pty_endpoint",
    "register_ai_pty_subscriber",
    "router",
    "unregister_ai_pty_subscriber",
]
