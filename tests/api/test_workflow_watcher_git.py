"""Unit tests for the ``.git/HEAD`` watcher half of ``workflow_watcher`` (ADR-039 §3.8).

The watcher gained a second observer surface in D39-2.1: alongside the
``workflows/`` YAML watch (ADR-034 Phase 2), the same observer now also
watches ``<project>/.git/HEAD`` and ``<project>/.git/refs/heads/*`` and
emits a ``git.head_changed`` engine event when either moves.

These tests instantiate ``_GitHeadHandler`` directly and synthesise
watchdog events so the assertions are deterministic on every CI host —
the real-filesystem timing of inotify / FSEvents / ReadDirectoryChangesW
is too flaky for unit-level coverage.

Coverage:

* HEAD modification with a symbolic ref → emit with the resolved SHA.
* HEAD modification with a detached SHA → emit with that SHA.
* ``refs/heads/<branch>`` modification → emit with that SHA.
* Internal git churn (``packed-refs``, ``index``, ``logs/HEAD``) → no emission.
* Rapid bursts within the debounce window → collapse to one emission.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from watchdog.events import FileCreatedEvent, FileModifiedEvent

from scistudio.api.routes.workflow_watcher import (
    _DEBOUNCE_SECONDS,
    _GitHeadHandler,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_git_dir(tmp_path: Path, *, head_target: str = "ref: refs/heads/main", main_sha: str = "a" * 40) -> Path:
    """Materialise a minimal ``.git`` directory the handler can reason over.

    Layout:
        .git/HEAD                       -- ``head_target`` text
        .git/refs/heads/main            -- ``main_sha`` text
        .git/packed-refs                -- ignored-by-handler control
        .git/index                      -- ignored-by-handler control
        .git/logs/HEAD                  -- ignored-by-handler control
    """
    git_dir = tmp_path / ".git"
    (git_dir / "refs" / "heads").mkdir(parents=True)
    (git_dir / "logs").mkdir()
    (git_dir / "HEAD").write_text(head_target + "\n", encoding="utf-8")
    (git_dir / "refs" / "heads" / "main").write_text(main_sha + "\n", encoding="utf-8")
    (git_dir / "packed-refs").write_text("# pack-refs with: peeled fully-peeled sorted\n", encoding="utf-8")
    (git_dir / "index").write_bytes(b"DIRC")
    (git_dir / "logs" / "HEAD").write_text("entry\n", encoding="utf-8")
    return git_dir


def _make_handler(git_dir: Path) -> tuple[_GitHeadHandler, list[dict[str, Any]]]:
    """Return ``(handler, captured)``; loop=None means synchronous dispatch."""
    captured: list[dict[str, Any]] = []

    def broadcast(payload: dict[str, Any]) -> None:
        captured.append(payload)

    handler = _GitHeadHandler(git_dir=git_dir, broadcast=broadcast, loop=None)
    return handler, captured


# ---------------------------------------------------------------------------
# HEAD with symbolic ref
# ---------------------------------------------------------------------------


def test_head_modify_with_symbolic_ref_resolves_to_branch_sha(tmp_path: Path) -> None:
    """A ``HEAD`` modification carrying ``ref: refs/heads/main`` must resolve to main's SHA."""
    git_dir = _make_git_dir(tmp_path, main_sha="b" * 40)
    handler, captured = _make_handler(git_dir)

    handler.on_any_event(FileModifiedEvent(str(git_dir / "HEAD")))

    assert len(captured) == 1
    payload = captured[0]
    assert payload["ref"] == "HEAD"
    assert payload["kind"] == "head"
    assert payload["commit_sha"] == "b" * 40


# ---------------------------------------------------------------------------
# HEAD detached
# ---------------------------------------------------------------------------


def test_head_modify_detached_returns_raw_sha(tmp_path: Path) -> None:
    """A detached ``HEAD`` (raw SHA in the file) returns that SHA verbatim."""
    sha = "c" * 40
    git_dir = _make_git_dir(tmp_path, head_target=sha)
    handler, captured = _make_handler(git_dir)

    handler.on_any_event(FileModifiedEvent(str(git_dir / "HEAD")))

    assert len(captured) == 1
    assert captured[0]["commit_sha"] == sha
    assert captured[0]["ref"] == "HEAD"
    assert captured[0]["kind"] == "head"


# ---------------------------------------------------------------------------
# refs/heads/<branch>
# ---------------------------------------------------------------------------


def test_branch_ref_modify_emits_with_resolved_sha(tmp_path: Path) -> None:
    """Movement of ``refs/heads/<branch>`` emits ``kind=refs``."""
    git_dir = _make_git_dir(tmp_path, main_sha="d" * 40)
    handler, captured = _make_handler(git_dir)

    handler.on_any_event(FileModifiedEvent(str(git_dir / "refs" / "heads" / "main")))

    assert len(captured) == 1
    payload = captured[0]
    assert payload["ref"] == "refs/heads/main"
    assert payload["kind"] == "refs"
    assert payload["commit_sha"] == "d" * 40


def test_nested_branch_path_emits_with_full_ref_name(tmp_path: Path) -> None:
    """Branches like ``feature/x`` materialise as ``refs/heads/feature/x``."""
    git_dir = _make_git_dir(tmp_path)
    branch_path = git_dir / "refs" / "heads" / "feature" / "x"
    branch_path.parent.mkdir(parents=True)
    branch_path.write_text("e" * 40 + "\n", encoding="utf-8")

    handler, captured = _make_handler(git_dir)
    handler.on_any_event(FileCreatedEvent(str(branch_path)))

    assert len(captured) == 1
    assert captured[0]["ref"] == "refs/heads/feature/x"
    assert captured[0]["commit_sha"] == "e" * 40


# ---------------------------------------------------------------------------
# Codex P2-A: ref lockfiles must not emit
# ---------------------------------------------------------------------------


def test_ref_lockfile_in_refs_heads_is_ignored(tmp_path: Path) -> None:
    """Git creates ``refs/heads/<branch>.lock`` transiently during ref updates.

    Treating it as a real branch ref would emit duplicate events and bogus
    ``ref=refs/heads/main.lock`` values that downstream consumers may
    interpret as real branches.
    """
    git_dir = _make_git_dir(tmp_path)
    lock_path = git_dir / "refs" / "heads" / "main.lock"
    lock_path.write_text("f" * 40 + "\n", encoding="utf-8")
    handler, captured = _make_handler(git_dir)
    handler.on_any_event(FileCreatedEvent(str(lock_path)))
    handler.on_any_event(FileModifiedEvent(str(lock_path)))
    assert captured == []


def test_head_lockfile_is_ignored(tmp_path: Path) -> None:
    """``HEAD.lock`` is also a transient and must not produce an event."""
    git_dir = _make_git_dir(tmp_path)
    lock_path = git_dir / "HEAD.lock"
    lock_path.write_text("ref: refs/heads/main\n", encoding="utf-8")
    handler, captured = _make_handler(git_dir)
    handler.on_any_event(FileCreatedEvent(str(lock_path)))
    assert captured == []


# ---------------------------------------------------------------------------
# Internal git churn must not emit
# ---------------------------------------------------------------------------


def test_packed_refs_modify_is_ignored(tmp_path: Path) -> None:
    git_dir = _make_git_dir(tmp_path)
    handler, captured = _make_handler(git_dir)
    handler.on_any_event(FileModifiedEvent(str(git_dir / "packed-refs")))
    assert captured == []


def test_index_modify_is_ignored(tmp_path: Path) -> None:
    git_dir = _make_git_dir(tmp_path)
    handler, captured = _make_handler(git_dir)
    handler.on_any_event(FileModifiedEvent(str(git_dir / "index")))
    assert captured == []


def test_logs_head_modify_is_ignored(tmp_path: Path) -> None:
    """``.git/logs/HEAD`` is reflog churn — must be filtered out."""
    git_dir = _make_git_dir(tmp_path)
    handler, captured = _make_handler(git_dir)
    handler.on_any_event(FileModifiedEvent(str(git_dir / "logs" / "HEAD")))
    assert captured == []


# ---------------------------------------------------------------------------
# Debounce
# ---------------------------------------------------------------------------


def test_debounce_coalesces_rapid_head_writes(tmp_path: Path) -> None:
    """Bursts of HEAD writes within the debounce window collapse to one emission."""
    git_dir = _make_git_dir(tmp_path)
    handler, captured = _make_handler(git_dir)
    for _ in range(5):
        handler.on_any_event(FileModifiedEvent(str(git_dir / "HEAD")))
    # All five events fired well inside _DEBOUNCE_SECONDS — only the first wins.
    assert len(captured) == 1


def test_debounce_allows_emit_after_window(tmp_path: Path) -> None:
    """After the debounce window elapses, the next event must emit again."""
    git_dir = _make_git_dir(tmp_path)
    handler, captured = _make_handler(git_dir)
    handler.on_any_event(FileModifiedEvent(str(git_dir / "HEAD")))
    time.sleep(_DEBOUNCE_SECONDS + 0.05)
    handler.on_any_event(FileModifiedEvent(str(git_dir / "HEAD")))
    assert len(captured) == 2


# ---------------------------------------------------------------------------
# Resilience: file unreadable mid-event still emits (with commit_sha=None)
# ---------------------------------------------------------------------------


def test_unreadable_head_still_emits(tmp_path: Path) -> None:
    """If HEAD vanished between event and read, we still emit (sha=None) so the cache invalidates."""
    git_dir = _make_git_dir(tmp_path)
    head_path = git_dir / "HEAD"
    head_path.unlink()  # simulate race: event fires for a path that has since vanished
    handler, captured = _make_handler(git_dir)
    handler.on_any_event(FileModifiedEvent(str(head_path)))
    assert len(captured) == 1
    assert captured[0]["commit_sha"] is None
    assert captured[0]["ref"] == "HEAD"
