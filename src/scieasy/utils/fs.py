"""Filesystem helpers (cross-platform).

``mount_pathlike`` exposes a single helper that materialises a "link"
from one path to another using whichever native primitive is cheapest
on the host platform:

- POSIX: ``os.symlink`` (a true symbolic link).
- Windows directories: ``_winapi.CreateJunction`` (a directory junction
  — no Developer Mode / admin required).
- Windows files: ``os.link`` (a hardlink — works on NTFS without admin).

Callers should treat the helper as opportunistic: it raises ``OSError``
when no native primitive succeeds (for example on Windows file shares
that block both junctions and hardlinks). The recommended pattern is
to call :func:`mount_pathlike` and fall back to a byte-copy
(``shutil.copyfile`` / ``shutil.copytree``) on ``OSError``.

ADR-028 §D8 / issue #1078: introduced for the
``scieasy.core.materialisation`` pass-through optimisation. The
materialisation helper invokes :func:`mount_pathlike` when a source
file already lives on disk in the target format, avoiding a redundant
byte round-trip through the saver.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = ["mount_pathlike"]


def mount_pathlike(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> Path:
    """Make *dst* refer to the same on-disk bytes as *src* via a native link.

    On POSIX this creates a symbolic link. On Windows it tries a
    directory junction (for directories) or a hardlink (for files); a
    true symlink is intentionally NOT attempted because that requires
    Developer Mode or admin privileges on most Windows installs.

    Args:
        src: Existing source path. Must exist.
        dst: Destination path. Must not exist; parents are created.

    Returns:
        ``Path(dst)`` for caller convenience.

    Raises:
        FileNotFoundError: if *src* does not exist.
        FileExistsError: if *dst* already exists.
        OSError: if no native primitive succeeded (caller should fall
            back to a byte copy).
    """
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        raise FileNotFoundError(f"mount_pathlike: source does not exist: {src_path}")
    if dst_path.exists():
        raise FileExistsError(f"mount_pathlike: destination already exists: {dst_path}")

    dst_path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        # POSIX (and macOS): plain symlink.
        os.symlink(str(src_path), str(dst_path))
        return dst_path

    # Windows. Prefer junction for directories (no admin needed),
    # hardlink for files. Both run on plain NTFS without elevation.
    if src_path.is_dir():
        try:
            import _winapi  # type: ignore[import-not-found]

            _winapi.CreateJunction(str(src_path), str(dst_path))
            return dst_path
        except (AttributeError, OSError) as exc:
            # AttributeError: older Python without _winapi.CreateJunction.
            # OSError: e.g. cross-volume junction, or the filesystem
            # doesn't support reparse points. Re-raise as OSError so the
            # caller can fall back to a byte copy.
            raise OSError(
                f"mount_pathlike: failed to create directory junction {dst_path} -> {src_path}: {exc}"
            ) from exc

    # File on Windows: hardlink. Hardlinks must live on the same NTFS
    # volume as the source; cross-volume calls raise OSError, which is
    # the contract callers expect.
    try:
        os.link(str(src_path), str(dst_path))
    except OSError as exc:
        raise OSError(f"mount_pathlike: failed to create hardlink {dst_path} -> {src_path}: {exc}") from exc
    return dst_path
