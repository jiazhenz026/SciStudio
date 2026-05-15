"""Polling watcher for external git changes (ADR-039 §3.8).

Distinct from the engine-level emitter in ``api/routes/workflow_watcher``
(which watches workflows/*.yaml). This module polls
``<project>/.git/HEAD`` and every loose ref under ``.git/refs/heads/*`` so
the BranchPicker / GitHistoryList / GitGraph views can selectively
invalidate their caches.

Why polling, not inotify
------------------------

- Cross-platform: inotify requires watchdog on Windows.
- ``.git/`` writes are atomic-rename based; 1s poll suffices.
- Zero cost when idle.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GitChangeWatcher:
    """Polls ``.git/`` for ref-tip mtime changes; emits ``git.head_changed``."""

    def __init__(self, emit_callback: Callable[[str, dict[str, Any]], Any]) -> None:
        self._emit = emit_callback
        self._task: asyncio.Task[None] | None = None
        self._project_path: Path | None = None
        self._stop_event: asyncio.Event | None = None
        self._last_head_mtime: float = 0.0
        self._last_refs_mtimes: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _scan_refs(self, project_path: Path) -> dict[str, float]:
        refs_dir = project_path / ".git" / "refs" / "heads"
        out: dict[str, float] = {}
        if not refs_dir.exists():
            return out
        try:
            for ref_file in refs_dir.rglob("*"):
                if ref_file.is_file():
                    try:
                        out[str(ref_file.relative_to(refs_dir))] = ref_file.stat().st_mtime
                    except OSError:
                        continue
        except OSError:
            pass
        return out

    def _read_head_sha(self, project_path: Path) -> str:
        head_file = project_path / ".git" / "HEAD"
        try:
            content = head_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        if content.startswith("ref:"):
            ref_path = content.split(" ", 1)[1].strip()
            try:
                target = project_path / ".git" / ref_path
                return target.read_text(encoding="utf-8").strip()
            except OSError:
                return ""
        return content

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_for_project(self, project_path: Path) -> None:
        """Begin polling. Idempotent: stops any existing task first."""
        project_path = Path(project_path).resolve()
        if not (project_path / ".git").exists():
            raise FileNotFoundError(f".git not found at {project_path}")

        # If already running, stop first.
        if self._task is not None and not self._task.done():
            with contextlib.suppress(Exception):
                self._task.cancel()

        self._project_path = project_path
        try:
            self._last_head_mtime = (project_path / ".git" / "HEAD").stat().st_mtime
        except OSError:
            self._last_head_mtime = 0.0
        self._last_refs_mtimes = self._scan_refs(project_path)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — defer; caller may schedule later.
            self._task = None
            self._stop_event = None
            return

        self._stop_event = asyncio.Event()
        self._task = loop.create_task(self._run_loop())

    def stop(self) -> None:
        """Stop polling. Idempotent."""
        if self._stop_event is not None:
            with contextlib.suppress(Exception):
                self._stop_event.set()
        if self._task is not None and not self._task.done():
            with contextlib.suppress(Exception):
                self._task.cancel()
        self._task = None
        self._stop_event = None
        self._project_path = None

    async def _run_loop(self) -> None:
        assert self._stop_event is not None
        assert self._project_path is not None
        project = self._project_path
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=1.0)
                break
            except TimeoutError:
                pass
            except asyncio.CancelledError:
                break
            try:
                head_changed = False
                try:
                    cur_head_mtime = (project / ".git" / "HEAD").stat().st_mtime
                    if cur_head_mtime != self._last_head_mtime:
                        self._last_head_mtime = cur_head_mtime
                        head_changed = True
                except OSError:
                    pass

                cur_refs = self._scan_refs(project)
                branches_changed: list[str] = []
                for name, mtime in cur_refs.items():
                    if self._last_refs_mtimes.get(name) != mtime:
                        branches_changed.append(name)
                for name in self._last_refs_mtimes:
                    if name not in cur_refs:
                        branches_changed.append(name)
                self._last_refs_mtimes = cur_refs

                if head_changed or branches_changed:
                    sha = self._read_head_sha(project)
                    try:
                        result = self._emit(
                            "git.head_changed",
                            {
                                "project": str(project),
                                "head_sha": sha,
                                "branches_changed": branches_changed,
                            },
                        )
                        if inspect.isawaitable(result):
                            await result
                    except Exception:
                        logger.warning("GitChangeWatcher emit failed", exc_info=True)
            except Exception:  # pragma: no cover — defensive
                logger.error("GitChangeWatcher loop iteration failed", exc_info=True)
