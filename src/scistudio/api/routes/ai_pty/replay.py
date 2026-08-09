"""The scripted byte source a tutorial replay plays into the AI Chat terminal.

ADR-053 Learning Center spec, FR-061 … FR-061c
(``docs/specs/adr-053-learning-center.md``), checklist §6.1.7.

FR-061a fixes the delivery mechanism, not just the surface set: a replay is
delivered "as a scripted session through that same path, so the tab strip, the
terminal component, and the tab lifecycle stay the product's real ones and only
the byte source changes". So nothing here renders anything, opens a WebSocket,
or speaks the wire protocol. :class:`ScriptedReplaySession` implements the same
small interface ``pty_endpoint`` already depends on — ``read``, ``is_alive``,
``write``, ``resize``, ``kill_tree`` — and is registered in
``_state._active_ptys`` under a fresh tab id carrying the ``_engine_prespawned``
marker, which is the join predicate that route already reads. The frontend then
connects ``WS /api/ai/pty/{tab_id}`` exactly as it does for a Bring In My Work
tab and joins this object instead of spawning an agent.

Three properties are the requirements rather than implementation choices:

* **Input is discarded** (FR-061a, "a replay MUST NOT accept user input back
  into the scripted session"). :meth:`ScriptedReplaySession.write` is where the
  route's WS→PTY pump delivers keystrokes, and it drops them. The pump is left
  running rather than suppressed so the tab behaves like every other tab —
  resize frames still arrive and a disconnect still tears down.

* **Nothing is buffered ahead of the session's sequencing** (FR-061b). Bytes
  become readable when :meth:`deliver` is called, and
  :func:`~scistudio.tutorials.actions.execute_replay` calls it only after that
  segment's own write and copy actions have landed. This module never reads a
  segment asset, so it has nothing it *could* run ahead with.

* **Closing leaves no session object behind** (FR-061c). :meth:`close` pops
  ``_active_ptys`` and terminates, which is the teardown ``pty_endpoint``
  performs for a real PTY, so a session ended mid-replay converges on the same
  state whether the WebSocket was attached or never arrived.

This module imports no sibling under ``ai_pty`` except the ``_state`` leaf and
:mod:`.engine`'s reaper, keeping the package's acyclic-siblings contract.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

from scistudio.api.routes.ai_pty import _state as _pkg
from scistudio.api.routes.ai_pty.engine import reclaim_orphaned_prespawned_tabs
from scistudio.tutorials.actions import REPLAY_SURFACES, ReplaySegment

logger = logging.getLogger(__name__)

__all__ = [
    "PtyReplayHandle",
    "ScriptedReplaySession",
    "UnknownReplaySurfaceError",
    "open_replay_tab",
]


class UnknownReplaySurfaceError(ValueError):
    """A replay named a surface outside :data:`REPLAY_SURFACES` (FR-061a).

    The manifest parser rejects such a surface while the tutorial is being
    listed, so reaching this is a programming error rather than a bad tutorial.
    It is still checked here: this function is the one place that turns a
    surface name into a live byte source, and "a replay must not be able to
    reach any surface other than the one the action names" (FR-061) is worth
    more than one guard.
    """

    def __init__(self, surface: str) -> None:
        self.surface = surface
        super().__init__(f"{surface!r} is not a replay surface; the closed set is {', '.join(sorted(REPLAY_SURFACES))}")


class ScriptedReplaySession:
    """A PTY-shaped byte source that plays scripted bytes and accepts no input.

    Duck-typed against :class:`~scistudio.ai.agent.terminal.PtyProcess` rather
    than derived from it: there is no subprocess, no file descriptor and no
    child to signal, and the five methods below are the entire surface
    ``pty_endpoint`` touches. ``_wait_exit_code`` reads ``_impl`` and ``_popen``
    with :func:`getattr` defaults, so their absence yields the ``-1`` it already
    returns for a reaped process.

    Thread-safe by lock because the two callers are on different threads: the
    route reads through ``loop.run_in_executor``, while :meth:`feed` is called
    from the request handler driving the tutorial step.
    """

    def __init__(self, *, cols: int = 120, rows: int = 30) -> None:
        self._pending = bytearray()
        self._lock = threading.Lock()
        self._arrived = threading.Condition(self._lock)
        self._alive = True
        self._cols = cols
        self._rows = rows

    # -- the scripted side ------------------------------------------------

    def feed(self, payload: bytes) -> None:
        """Make *payload* readable, waking a reader blocked in :meth:`read`."""
        if not payload:
            return
        with self._arrived:
            if not self._alive:
                return
            self._pending.extend(payload)
            self._arrived.notify_all()

    # -- the interface ``pty_endpoint`` depends on ------------------------

    def read(self, timeout: float = 0.1) -> bytes:
        """Return whatever bytes are pending, waiting up to *timeout* for some.

        Blocking-with-a-deadline rather than returning immediately, because the
        route's pump calls this in a loop on an executor thread: a
        non-blocking read would spin that thread at full speed for the whole
        life of the tab.
        """
        with self._arrived:
            if not self._pending and self._alive:
                self._arrived.wait(timeout)
            chunk = bytes(self._pending)
            self._pending.clear()
            return chunk

    def is_alive(self) -> bool:
        """Whether the scripted session is still open.

        Stays true after the last segment has been delivered. The tutorial
        session decides when a replay is over — on leaving, completing,
        failing, or starting another replay — and says so through :meth:`close`.
        Ending at the last byte instead would tear the tab down the moment the
        transcript finished, which is precisely when the user starts reading it.
        """
        return self._alive

    def write(self, data: bytes) -> None:
        """Discard client input (FR-061a).

        A replay is scripted content playback, so a keystroke must not reach
        it. Dropping the bytes here rather than declining to run the route's
        WS→PTY pump keeps resize frames and disconnects working: the tab is a
        real tab that happens to ignore typing.
        """

    def resize(self, *, cols: int, rows: int) -> None:
        """Record the client's viewport. Scripted bytes do not reflow."""
        self._cols = cols
        self._rows = rows

    def kill_tree(self) -> None:
        """Terminate the scripted session. There is no process tree to signal."""
        with self._arrived:
            self._alive = False
            self._pending.clear()
            self._arrived.notify_all()


@dataclass
class PtyReplayHandle:
    """One open replay: the surface it plays into, its tab, and its byte source.

    Satisfies :class:`~scistudio.tutorials.session.ReplayHandle`, which is what
    the tutorial runtime holds and what the session response's ``replay`` field
    is rendered from.
    """

    surface: str
    tab_id: str
    session: ScriptedReplaySession = field(repr=False)

    def deliver(self, segment: ReplaySegment, payload: bytes) -> None:
        """Play one segment's bytes into the terminal.

        Called by :func:`~scistudio.tutorials.actions.execute_replay` after that
        segment's bound write and copy actions have landed (FR-061b).
        """
        self.session.feed(payload)

    def close(self) -> None:
        """Terminate the scripted session, leaving nothing behind (FR-061c).

        The teardown ``pty_endpoint`` performs, in the same order: drop the
        registry entry first, then kill. Popping first is what makes this safe
        to call while a WebSocket is attached — that route pops with a default
        and kills again, and both halves are idempotent.
        """
        _pkg._active_ptys.pop(self.tab_id, None)
        self.session.kill_tree()


def open_replay_tab(surface: str) -> PtyReplayHandle:
    """Register a scripted byte source and return the handle that drives it.

    The tutorial runtime calls this through its ``open_replay`` port when a step
    declares a replay action, then hands the tab id to the frontend in the
    session response so it can attach the terminal.

    Args:
        surface: The surface the replay action named. Must be in
            :data:`~scistudio.tutorials.actions.REPLAY_SURFACES`.

    Returns:
        A handle bound to *surface*, registered under a fresh tab id.

    Raises:
        UnknownReplaySurfaceError: *surface* is outside the closed set.
        RuntimeError: Every terminal slot is in use.
    """
    if surface not in REPLAY_SURFACES:
        raise UnknownReplaySurfaceError(surface)

    # An earlier handoff that never completed holds a slot it will never use;
    # the pre-spawned tab path reclaims for the same reason before counting.
    reclaim_orphaned_prespawned_tabs()
    if len(_pkg._active_ptys) >= _pkg.MAX_ACTIVE_PTYS:
        raise RuntimeError(
            f"tutorial replay: terminal cap ({_pkg.MAX_ACTIVE_PTYS}) reached; close a tab and try the step again"
        )

    session = ScriptedReplaySession()
    # Stamped before registration, for the reason ``_open_prespawned_tab``
    # records: the marker is what the WebSocket route's join branch reads, and a
    # connection arriving between the insert and the stamp would spawn a real
    # agent over the top of the replay.
    session._engine_prespawned = True  # type: ignore[attr-defined]
    session._engine_prespawned_at = time.monotonic()  # type: ignore[attr-defined]

    tab_id = uuid.uuid4().hex[:12]
    _pkg._active_ptys[tab_id] = session  # type: ignore[assignment]
    logger.info("tutorial replay: opened scripted tab_id=%s surface=%s", tab_id, surface)
    return PtyReplayHandle(surface=surface, tab_id=tab_id, session=session)
