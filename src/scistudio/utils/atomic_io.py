"""Atomic, crash-safe file writes (shared durability helper).

Several SciStudio subsystems persist files that the system exists to
protect — pause/resume checkpoints (ADR-018 / ADR-012), SaveData
scientific artifacts (ADR-028 Addendum 1 §C9), and workflow YAML
definitions. The naive ``open(path, "w")`` / ``Path.write_text`` /
``json.dump(..., f)`` pattern writes **directly into the final path**:
a crash (SIGKILL, OOM, power loss) mid-write leaves a truncated file,
and when the destination already held a good copy the prior good bytes
are already gone. See issues #1515 (checkpoint), #1516 (SaveData
writers), and #1543 (workflow YAML).

This module centralises the durable-write recipe:

1. Write the new bytes to a temporary sibling file in the **same
   directory** as the destination (so the final :func:`os.replace` is a
   same-filesystem rename, which POSIX and Windows both make atomic).
2. ``flush`` + :func:`os.fsync` the file so the bytes hit stable storage
   before the rename is published.
3. :func:`os.replace` the temp file onto the final path. ``os.replace``
   atomically swaps the new file in; a concurrent reader either sees the
   complete old file or the complete new file, never a half-written one.
4. On any exception before the rename, the temp file is removed and the
   original destination is left untouched.

The functions here do **not** ``fsync`` the containing directory by
default. A directory fsync is required only when an application must
guarantee that the *rename itself* survives a power loss (as opposed to
the file contents); SciStudio's durability requirement is "never observe
a truncated/half-written artifact", which the same-directory
``os.replace`` already satisfies. Callers that need rename-durability can
pass ``fsync_dir=True``.

Directory-style outputs (zarr stores, ``shutil.copytree`` targets) are
handled by :func:`atomic_replace_dir`, which builds the new tree in a
temp sibling directory and swaps it into place; see its docstring for the
non-empty-destination caveat.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

__all__ = [
    "atomic_path",
    "atomic_replace_dir",
    "atomic_write_bytes",
    "atomic_write_text",
    "atomic_writer",
]


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of *directory* so a rename survives power loss.

    Opening a directory for fsync is not supported on every platform
    (notably Windows raises ``PermissionError``/``OSError``); those
    failures are swallowed because directory fsync is an extra durability
    guarantee, not a correctness requirement for the never-truncated
    invariant this module provides.
    """
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


@contextlib.contextmanager
def atomic_writer(
    path: str | os.PathLike[str],
    *,
    mode: str = "wb",
    encoding: str | None = None,
    fsync: bool = True,
    fsync_dir: bool = False,
) -> Iterator[IO[Any]]:
    """Context manager yielding a temp file that atomically replaces *path*.

    Usage::

        with atomic_writer(path, mode="w", encoding="utf-8") as fh:
            json.dump(data, fh)

    The yielded file handle points at a uniquely-named temporary file in
    the same directory as *path*. On a clean exit the temp file is
    flushed, optionally ``fsync``-ed, closed, and then
    :func:`os.replace`-d onto *path*. If the ``with`` body raises, the
    temp file is closed and removed and *path* is left untouched.

    Args:
        path: Final destination path. Its parent directory is created if
            missing.
        mode: File mode. Must be a write mode (``"wb"`` default, or
            ``"w"`` for text). Append/read modes are rejected because they
            are incompatible with the temp-then-replace recipe.
        encoding: Text encoding (only meaningful for text modes).
        fsync: When ``True`` (default) ``os.fsync`` the temp file before
            the rename so the contents are durable.
        fsync_dir: When ``True`` also fsync the destination directory
            after the rename so the rename itself is durable across a
            power loss. Defaults to ``False``.

    Yields:
        An open writable file handle for the temporary file.
    """
    if "a" in mode or "r" in mode or "x" in mode:
        raise ValueError(f"atomic_writer requires a plain write mode ('w'/'wb'), got {mode!r}")
    if "w" not in mode:
        raise ValueError(f"atomic_writer requires a write mode, got {mode!r}")

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    is_binary = "b" in mode
    # ``delete=False`` so we control the lifetime: we either rename the
    # temp into place or unlink it ourselves. Same directory as the
    # destination so the final os.replace is an atomic same-FS rename.
    # SIM115: the handle's lifetime is intentionally manual — the enclosing
    # contextmanager owns close/replace/unlink, so a plain ``with`` here
    # would defeat the temp-then-replace recipe.
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        mode=mode,
        encoding=None if is_binary else (encoding or "utf-8"),
        dir=str(dest.parent),
        prefix=f".{dest.name}.",
        suffix=".tmp",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    try:
        yield tmp  # type: ignore[misc]
        tmp.flush()
        if fsync:
            os.fsync(tmp.fileno())
        tmp.close()
        os.replace(str(tmp_path), str(dest))
    except BaseException:
        # Leave the original destination intact; clean up the temp file.
        with contextlib.suppress(Exception):
            tmp.close()
        with contextlib.suppress(FileNotFoundError, OSError):
            tmp_path.unlink()
        raise
    else:
        if fsync_dir:
            _fsync_dir(dest.parent)


@contextlib.contextmanager
def atomic_path(
    path: str | os.PathLike[str],
    *,
    suffix: str = "",
    fsync: bool = True,
    fsync_dir: bool = False,
) -> Iterator[Path]:
    """Yield a temp file *path* that atomically replaces *path* on exit.

    Use this for third-party writers that insist on a filesystem path
    rather than a file handle (``numpy.save``, ``pyarrow.parquet`` writers,
    ``shutil.copy2``, the streaming CSV/Parquet exporters). The yielded
    path is a uniquely-named temporary file in the **same directory** as
    *path*; populate it inside the ``with`` body. On a clean exit the temp
    file is ``fsync``-ed and :func:`os.replace`-d onto *path*; if the body
    raises, the temp file is removed and *path* is left untouched.

    The temp file is created and immediately closed so the writer can
    open/create it itself. Some writers (``numpy.save``) append their own
    extension to a path that lacks one; pass ``suffix`` (e.g. ``".npy"``)
    so the temp path already carries the final extension and the writer
    does not rewrite it.

    Args:
        path: Final destination path. Its parent directory is created if
            missing.
        suffix: Extension to give the temp file (defaults to ``""``).
        fsync: When ``True`` (default) ``os.fsync`` the temp file before
            the rename.
        fsync_dir: When ``True`` also fsync the destination directory
            after the rename.

    Yields:
        A :class:`~pathlib.Path` to the temp file to populate.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(dest.parent),
        prefix=f".{dest.name}.",
        suffix=suffix or ".tmp",
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        yield tmp_path
        if fsync:
            # Reopen to fsync the bytes the external writer produced.
            with contextlib.suppress(OSError):
                fd = os.open(str(tmp_path), os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        os.replace(str(tmp_path), str(dest))
    except BaseException:
        with contextlib.suppress(FileNotFoundError, OSError):
            tmp_path.unlink()
        raise
    else:
        if fsync_dir:
            _fsync_dir(dest.parent)


def atomic_write_bytes(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    fsync: bool = True,
    fsync_dir: bool = False,
) -> Path:
    """Atomically write *data* bytes to *path*.

    Equivalent to ``Path(path).write_bytes(data)`` but crash-safe: a
    concurrent reader or a crash mid-write never observes a truncated
    file, and an existing good file at *path* is only ever replaced
    wholesale.

    Returns the destination :class:`~pathlib.Path`.
    """
    dest = Path(path)
    with atomic_writer(dest, mode="wb", fsync=fsync, fsync_dir=fsync_dir) as fh:
        fh.write(data)
    return dest


def atomic_write_text(
    path: str | os.PathLike[str],
    text: str,
    *,
    encoding: str = "utf-8",
    fsync: bool = True,
    fsync_dir: bool = False,
) -> Path:
    """Atomically write *text* to *path* using *encoding*.

    Crash-safe equivalent of ``Path(path).write_text(text,
    encoding=encoding)``. Returns the destination :class:`~pathlib.Path`.
    """
    dest = Path(path)
    with atomic_writer(dest, mode="w", encoding=encoding, fsync=fsync, fsync_dir=fsync_dir) as fh:
        fh.write(text)
    return dest


@contextlib.contextmanager
def atomic_replace_dir(path: str | os.PathLike[str]) -> Iterator[Path]:
    """Context manager that builds a directory tree then atomically swaps it.

    Yields a temporary sibling directory for the caller to populate. On a
    clean exit the destination *path* is replaced by the temp directory.

    Atomicity caveat: :func:`os.replace` can atomically replace a file or
    an *empty* directory, but it cannot atomically replace a *non-empty*
    directory (it raises ``OSError``/``ENOTEMPTY``). To keep a single
    visible swap, when *path* already exists this helper renames the old
    tree aside to a temp name, renames the freshly built tree into place,
    and only then deletes the old tree. The brief window where the
    destination is momentarily absent (between the two renames) is the
    documented limitation of directory swaps; readers that hit that window
    see "missing" rather than "half-written", which is the safe failure
    mode for the zarr/copytree outputs this is used for.

    Args:
        path: Final destination directory.

    Yields:
        A :class:`~pathlib.Path` to the temp directory to populate.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(dir=str(dest.parent), prefix=f".{dest.name}.", suffix=".tmp"))
    try:
        yield tmp_dir
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    backup: Path | None = None
    if dest.exists():
        backup = Path(tempfile.mkdtemp(dir=str(dest.parent), prefix=f".{dest.name}.bak.", suffix=".tmp"))
        # mkdtemp created an empty dir; remove it so os.replace can move
        # the old tree onto that name.
        backup.rmdir()
        os.replace(str(dest), str(backup))
    try:
        os.replace(str(tmp_dir), str(dest))
    except BaseException:
        # Roll back: restore the original tree if we moved it aside.
        if backup is not None and backup.exists() and not dest.exists():
            with contextlib.suppress(OSError):
                os.replace(str(backup), str(dest))
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)
