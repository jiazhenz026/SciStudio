"""Shared low-level helpers for the runtime sub-package.

Issue #1430 / umbrella #1427: extracted verbatim from the original
``api/runtime.py`` god-file so behavior is unchanged. The public surface
of these helpers (``_rmtree_force``, ``_now_iso``, ``_slugify``,
``_safe_parent_dir``) is preserved via ``runtime/__init__.py`` so that
existing callers (``from scistudio.api.runtime import _rmtree_force``)
keep working.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import stat
import time
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _slugify(name: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in name).strip("-")
    return slug or "project"


def _safe_parent_dir(path: str | Path | None) -> Path:
    if path is None:
        return Path.cwd()
    return Path(path).expanduser().resolve()


def _rmtree_force(target: Path) -> None:
    """Remove a directory tree, retrying on Windows read-only / locked files.

    ADR-039: auto-init creates ``.git/`` with read-only object files on
    Windows. Plain ``shutil.rmtree`` cannot remove read-only files, and
    can also race with file watchers that briefly hold handles. This
    helper:

    1. Pre-walks the tree to ``chmod -R`` every file writable.
    2. Calls ``shutil.rmtree`` with an ``onerror`` that retries with
       chmod for any remaining stragglers.
    3. Does a small bounded retry loop for transient locks (file watcher
       holding a handle while we delete).
    """

    target_p = Path(target)
    if not target_p.exists():
        return

    # 1. Walk + chmod everything writable. Directories need execute (x)
    # for traversal on POSIX; files just need write to be unlinkable.
    dir_perms = stat.S_IRWXU  # 0700 — read/write/execute for owner
    file_perms = stat.S_IWRITE | stat.S_IREAD  # 0600
    for root, dirs, files in os.walk(target_p):
        with contextlib.suppress(OSError):
            os.chmod(root, dir_perms)
        for name in dirs:
            with contextlib.suppress(OSError):
                os.chmod(Path(root) / name, dir_perms)
        for name in files:
            with contextlib.suppress(OSError):
                os.chmod(Path(root) / name, file_perms)
    with contextlib.suppress(OSError):
        os.chmod(target_p, dir_perms)

    def _on_rm_error(func, path, _exc_info):  # type: ignore[no-untyped-def]
        try:
            p = Path(path)
            os.chmod(p, dir_perms if p.is_dir() else file_perms)
            func(path)
        except Exception:
            logger.debug("rmtree retry failed for %s", path, exc_info=True)

    # 2. Bounded retry loop for transient locks (e.g. sqlite WAL).
    for _ in range(5):
        try:
            shutil.rmtree(target_p, onerror=_on_rm_error)
        except Exception:
            logger.debug("rmtree raised", exc_info=True)
        if not target_p.exists():
            return
        time.sleep(0.2)
    # Last resort: best-effort one more pass after a longer wait so any
    # in-process sqlite WAL flush has time to release file handles.
    time.sleep(0.5)
    try:
        shutil.rmtree(target_p, onerror=_on_rm_error)
    except Exception:
        logger.warning("rmtree failed to remove %s", target_p, exc_info=True)
