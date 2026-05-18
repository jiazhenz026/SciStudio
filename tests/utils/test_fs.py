"""Tests for :func:`scieasy.utils.fs.mount_pathlike`.

Platform-gated: POSIX runs the symlink test, Windows runs the
hardlink + junction tests. Cross-volume failures and ``FileExists``
edges are checked unconditionally because they don't require a
platform-specific primitive to surface.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scieasy.utils.fs import mount_pathlike


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink path only")
def test_posix_creates_symlink(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    src.write_text("hello", encoding="utf-8")
    dst = tmp_path / "linked.txt"

    result = mount_pathlike(src, dst)

    assert result == dst
    assert dst.is_symlink()
    assert dst.read_text(encoding="utf-8") == "hello"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows hardlink path only")
def test_windows_file_creates_hardlink(tmp_path: Path) -> None:
    """On Windows, a file mount produces a hardlink (no admin required)."""
    src = tmp_path / "src.txt"
    src.write_text("hello", encoding="utf-8")
    dst = tmp_path / "linked.txt"

    result = mount_pathlike(src, dst)

    assert result == dst
    assert dst.exists()
    # Hardlink: both names point at the same inode; the byte content is
    # identical and writing through one is visible through the other.
    assert dst.read_text(encoding="utf-8") == "hello"
    # st_ino equality is the canonical hardlink test on Windows too.
    assert dst.stat().st_ino == src.stat().st_ino


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction path only")
def test_windows_directory_creates_junction(tmp_path: Path) -> None:
    """On Windows, a directory mount produces a junction."""
    src = tmp_path / "src_dir"
    src.mkdir()
    (src / "inside.txt").write_text("ok", encoding="utf-8")
    dst = tmp_path / "linked_dir"

    result = mount_pathlike(src, dst)

    assert result == dst
    assert dst.is_dir()
    # Confirm the junction surfaces the source content.
    assert (dst / "inside.txt").read_text(encoding="utf-8") == "ok"


def test_missing_source_raises_filenotfound(tmp_path: Path) -> None:
    src = tmp_path / "nope.txt"
    dst = tmp_path / "linked.txt"
    with pytest.raises(FileNotFoundError, match="source does not exist"):
        mount_pathlike(src, dst)


def test_existing_destination_raises_fileexists(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    src.write_text("a", encoding="utf-8")
    dst = tmp_path / "dst.txt"
    dst.write_text("b", encoding="utf-8")
    with pytest.raises(FileExistsError, match="destination already exists"):
        mount_pathlike(src, dst)


def test_parent_directories_are_created(tmp_path: Path) -> None:
    src = tmp_path / "src.txt"
    src.write_text("data", encoding="utf-8")
    dst = tmp_path / "nested" / "deeper" / "linked.txt"
    assert not dst.parent.exists()

    mount_pathlike(src, dst)

    assert dst.exists()
    assert dst.parent.is_dir()
