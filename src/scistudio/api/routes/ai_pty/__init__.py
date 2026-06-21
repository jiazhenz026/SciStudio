"""WebSocket route hosting the PTY-tab embedded agent (ADR-034 Phase 1.2).

This package exposes a single endpoint:

    ``ws://host/api/ai/pty/{tab_id}?project_dir=<urlencoded>&provider=<claude-code|codex|user-terminal>&dangerous=<true|false>[&cols=<n>&rows=<n>]``

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
    "pty_endpoint",
    "register_ai_pty_subscriber",
    "router",
    "unregister_ai_pty_subscriber",
]
