"""Polling watcher for external git changes (ADR-039 §3.8).

This watcher is **distinct from** the engine-level event emitter wired
by D39-2.1 in ``scieasy.api.routes.workflow_watcher`` (which adds the
``git.head_changed`` event on ``.git/HEAD`` mtime change for the
workflow-canvas refresh path).

This module addresses a different concern: a **richer UI-cache
invalidation** signal for the BranchPicker + GitHistoryList + GitGraph
views. It polls both ``.git/HEAD`` (current-branch indicator) and every
``.git/refs/heads/*`` ref tip (branch list + per-branch HEAD SHAs), so
the frontend can know which sub-panels need re-fetching rather than
re-fetching everything on every HEAD change.

Why polling, not inotify
------------------------

- Inotify on Windows requires a separate API; watchdog handles this but
  adds a dependency the engine doesn't otherwise need.
- ``.git/`` writes are atomic-rename-based (`git update-ref` writes a
  temp file then renames), so a 1-second poll is sufficient — git's own
  internal consistency window is on the same order.
- Polling has zero cost when the project is idle and SciEasy doesn't
  have many open projects per process.

Skeleton phase
--------------

``GitChangeWatcher.start_for_project`` and ``.stop`` raise
``NotImplementedError``. The impl agent (D39-2.2b) builds the polling
loop; the API layer (``app.py`` lifespan) calls ``start_for_project`` on
project switch and ``stop`` on app teardown — those call sites are
stubbed in the lifespan now.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


class GitChangeWatcher:
    """Polls a project's ``.git/`` directory for ref-tip mtime changes.

    Emits structured events via the injected ``emit`` callable. The
    event bus is owned by ``ApiRuntime`` (passed in by ``app.py`` at
    construction); this watcher never imports from the engine package
    directly to keep the dependency arrow clean.

    Event types emitted
    -------------------

    - ``git.head_changed`` — already defined in ``engine/events.py`` by
      D39-2.1. We REUSE this event type rather than adding a new one
      (per the common-boilerplate scope rule "may NOT add new event
      types"). The event data shape we publish:

         ``{"project": "<path>", "head_sha": "<sha>",
            "branches_changed": ["foo", "bar"]}``

      The ``branches_changed`` field is the new information this richer
      watcher contributes — D39-2.1's emitter only knew HEAD moved.

    Construction
    ------------

    ``emit_callback`` is an async-or-sync callable
    ``(event_type: str, data: dict) -> None`` that the watcher invokes
    when it detects a change. Decoupling lets tests pass in a list-
    appender for assertion.
    """

    def __init__(self, emit_callback: Callable[[str, dict[str, Any]], None]) -> None:
        # Implementation note for D39-2.2b:
        # ---------------------------------
        # 1. Store ``self._emit = emit_callback``.
        # 2. ``self._task: asyncio.Task | None = None``.
        # 3. ``self._project_path: Path | None = None``.
        # 4. ``self._stop_event: asyncio.Event | None = None``.
        # 5. ``self._last_head_mtime: float = 0.0``.
        # 6. ``self._last_refs_mtimes: dict[str, float] = {}``.
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def start_for_project(self, project_path: Path) -> None:
        """Begin polling the given project.

        Purpose
        -------
        Called by ``app.py`` lifespan on app start (for the active
        project) and by ``ApiRuntime.open_project`` on subsequent
        project switches.

        Signature contract
        ------------------
        - Input: ``project_path`` — root of a SciEasy project. Must
          contain ``.git/`` (caller checks via
          :meth:`GitEngine.is_repository`).
        - Output: None.
        - Errors: ``FileNotFoundError`` if no ``.git/`` directory.

        Implementation steps (for D39-2.2b)
        -----------------------------------
        1. If ``self._task`` is not None, call :meth:`stop` first
           (one watcher per project at a time).
        2. Verify ``(project_path / ".git").exists()``.
        3. Seed ``self._last_head_mtime`` and ``self._last_refs_mtimes``
           with the current mtimes of:
              ``.git/HEAD``
              every file under ``.git/refs/heads/``
           so the first poll iteration does NOT emit a spurious change
           event.
        4. Create ``self._stop_event = asyncio.Event()``.
        5. Schedule ``self._task = asyncio.create_task(self._run_loop())``.

        Edge cases
        ----------
        - Project has no ``.git/`` (degraded mode per ADR §3.2) — caller
          should not call us; if they do, raise FileNotFoundError.
        - Race with file watcher on the same project — both are
          read-only observers; no interference.

        Test plan
        ---------
        - ``test_start_seeds_mtimes`` — verify no event emitted on
          immediate poll if files are unchanged.
        - ``test_start_idempotent`` — calling twice stops the first.

        ADR references
        --------------
        - §3.8 lines 373-378 (HEAD + refs/heads/ mtime polling).
        - §5.2 lines 475-476 (workflow_watcher extension — sibling).
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    def stop(self) -> None:
        """Stop polling and release resources.

        Implementation
        --------------
        1. Set ``self._stop_event``.
        2. ``await self._task`` (or schedule cancellation if no event
           loop is running — depends on whether stop is called from
           sync or async context; ``app.py`` lifespan calls from async).
        3. Reset all instance fields to None.

        Edge cases
        ----------
        - Called when not running — no-op (idempotent).

        Test plan
        ---------
        - ``test_stop_terminates_task`` — start then stop within a
          single asyncio.run; task.done() True afterward.

        ADR references
        --------------
        - §3.8.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")

    async def _run_loop(self) -> None:
        """Internal polling loop.

        Implementation steps (for D39-2.2b)
        -----------------------------------
        1. Loop until ``self._stop_event.is_set()``:
           a. Sleep 1 second (await asyncio.sleep(1.0), interruptible
              by stop_event via ``asyncio.wait``).
           b. Stat ``.git/HEAD``. If mtime changed:
                * Read HEAD to get new ref / SHA.
                * Mark ``head_changed = True``.
                * Update ``self._last_head_mtime``.
           c. Scan ``.git/refs/heads/`` recursively for files;
              compute new mtimes; diff against ``self._last_refs_mtimes``;
              collect ``branches_changed = [...]``.
           d. If ``head_changed or branches_changed``:
                * Resolve current HEAD sha via reading ``.git/HEAD``
                  (handle the ``ref: refs/heads/<name>`` indirection;
                  follow to the actual ref file to read the sha).
                * Emit ``("git.head_changed", {"project": str(path),
                  "head_sha": sha, "branches_changed": branches_changed})``.
        2. On any unexpected exception inside the loop, log at ERROR
           and continue — a single bad poll iteration must not kill the
           watcher.

        Edge cases
        ----------
        - ``.git/refs/heads/`` does not exist yet (fresh init,
          pre-first-commit) — skip step c silently.
        - Packed refs (``.git/packed-refs``) — for v1 we only watch
          loose refs under ``refs/heads/``. Documented limitation; if
          a user invokes ``git gc`` externally the watcher will miss
          packed-ref changes. Mitigation deferred to v2.
        - Concurrent modification by git itself (git writes a temp file
          and renames) — atomic rename means our mtime check sees the
          final state; no torn reads.

        Test plan
        ---------
        - ``test_run_loop_detects_head_change`` — set up watcher, commit
          via subprocess, verify emit was called with new SHA within
          2 seconds.
        - ``test_run_loop_detects_branch_creation`` — create a branch
          externally; emit data has the new branch name in
          ``branches_changed``.
        - ``test_run_loop_no_emit_when_idle`` — wait 3 seconds with no
          changes; no emit.

        ADR references
        --------------
        - §3.8.
        """
        raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")
