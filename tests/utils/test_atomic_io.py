"""Tests for the shared atomic-write helper (``scistudio.utils.atomic_io``).

Covers the durability invariant the module exists to provide: a crash /
exception mid-write must never destroy a pre-existing good file, and a
concurrent reader must never observe a truncated file. See issues #1515
(checkpoint), #1516 (SaveData writers), and #1543 (workflow YAML).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scistudio.utils.atomic_io import (
    atomic_path,
    atomic_replace_dir,
    atomic_write_bytes,
    atomic_write_text,
    atomic_writer,
)


class _BoomError(Exception):
    """Sentinel exception raised inside ``with`` bodies under test."""


# ---------------------------------------------------------------------------
# atomic_writer
# ---------------------------------------------------------------------------


class TestAtomicWriter:
    def test_text_write_creates_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        with atomic_writer(dest, mode="w", encoding="utf-8") as fh:
            fh.write("hello")
        assert dest.read_text(encoding="utf-8") == "hello"

    def test_binary_write_creates_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.bin"
        with atomic_writer(dest, mode="wb") as fh:
            fh.write(b"\x00\x01\x02")
        assert dest.read_bytes() == b"\x00\x01\x02"

    def test_creates_missing_parent_dirs(self, tmp_path: Path) -> None:
        dest = tmp_path / "a" / "b" / "out.txt"
        with atomic_writer(dest, mode="w", encoding="utf-8") as fh:
            fh.write("x")
        assert dest.read_text(encoding="utf-8") == "x"

    def test_exception_mid_write_leaves_original_intact(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        dest.write_text("ORIGINAL", encoding="utf-8")

        with pytest.raises(_BoomError), atomic_writer(dest, mode="w", encoding="utf-8") as fh:
            fh.write("PARTIAL-DOOMED")
            raise _BoomError

        # The prior good content survives untouched.
        assert dest.read_text(encoding="utf-8") == "ORIGINAL"

    def test_exception_leaves_no_temp_files_behind(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        dest.write_text("ORIGINAL", encoding="utf-8")
        with pytest.raises(_BoomError), atomic_writer(dest, mode="w", encoding="utf-8") as fh:
            fh.write("partial")
            raise _BoomError
        # Only the original file should remain; no ``.out.txt.*.tmp`` siblings.
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "out.txt"]
        assert leftovers == []

    def test_no_partial_visible_until_replace(self, tmp_path: Path) -> None:
        """The destination keeps its old bytes while the body is mid-write."""
        dest = tmp_path / "out.txt"
        dest.write_text("OLD", encoding="utf-8")
        with atomic_writer(dest, mode="w", encoding="utf-8") as fh:
            fh.write("NEW")
            # Before the context exits, the destination still holds OLD.
            assert dest.read_text(encoding="utf-8") == "OLD"
        assert dest.read_text(encoding="utf-8") == "NEW"

    def test_rejects_append_mode(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="plain write mode"), atomic_writer(tmp_path / "x", mode="a"):
            pass

    def test_rejects_read_mode(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError), atomic_writer(tmp_path / "x", mode="r"):
            pass

    def test_fsync_dir_succeeds(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        with atomic_writer(dest, mode="w", encoding="utf-8", fsync_dir=True) as fh:
            fh.write("durable")
        assert dest.read_text(encoding="utf-8") == "durable"


# ---------------------------------------------------------------------------
# atomic_write_bytes / atomic_write_text
# ---------------------------------------------------------------------------


class TestAtomicWriteHelpers:
    def test_write_bytes_roundtrip(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.bin"
        returned = atomic_write_bytes(dest, b"payload")
        assert returned == dest
        assert dest.read_bytes() == b"payload"

    def test_write_text_roundtrip(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        returned = atomic_write_text(dest, "payload", encoding="utf-8")
        assert returned == dest
        assert dest.read_text(encoding="utf-8") == "payload"

    def test_write_bytes_overwrites_existing(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.bin"
        dest.write_bytes(b"old")
        atomic_write_bytes(dest, b"new")
        assert dest.read_bytes() == b"new"


# ---------------------------------------------------------------------------
# atomic_path
# ---------------------------------------------------------------------------


class TestAtomicPath:
    def test_external_writer_lands_on_dest(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.dat"
        with atomic_path(dest) as tmp:
            tmp.write_bytes(b"written-by-path")
        assert dest.read_bytes() == b"written-by-path"

    def test_exception_mid_write_leaves_original_intact(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.dat"
        dest.write_bytes(b"ORIGINAL")
        with pytest.raises(_BoomError), atomic_path(dest) as tmp:
            tmp.write_bytes(b"PARTIAL")
            raise _BoomError
        assert dest.read_bytes() == b"ORIGINAL"
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "out.dat"]
        assert leftovers == []

    def test_temp_path_carries_requested_suffix(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.npy"
        seen: dict[str, str] = {}
        with atomic_path(dest, suffix=".npy") as tmp:
            seen["suffix"] = tmp.suffix
            tmp.write_bytes(b"x")
        assert seen["suffix"] == ".npy"
        assert dest.read_bytes() == b"x"

    def test_old_file_visible_until_swap(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.dat"
        dest.write_bytes(b"OLD")
        with atomic_path(dest) as tmp:
            tmp.write_bytes(b"NEW")
            assert dest.read_bytes() == b"OLD"
        assert dest.read_bytes() == b"NEW"


# ---------------------------------------------------------------------------
# atomic_replace_dir
# ---------------------------------------------------------------------------


class TestAtomicReplaceDir:
    def test_builds_new_directory(self, tmp_path: Path) -> None:
        dest = tmp_path / "store"
        with atomic_replace_dir(dest) as tmp_dir:
            (tmp_dir / "a.txt").write_text("a", encoding="utf-8")
            (tmp_dir / "b.txt").write_text("b", encoding="utf-8")
        assert dest.is_dir()
        assert (dest / "a.txt").read_text(encoding="utf-8") == "a"
        assert (dest / "b.txt").read_text(encoding="utf-8") == "b"

    def test_replaces_existing_non_empty_directory(self, tmp_path: Path) -> None:
        dest = tmp_path / "store"
        dest.mkdir()
        (dest / "old.txt").write_text("old", encoding="utf-8")

        with atomic_replace_dir(dest) as tmp_dir:
            (tmp_dir / "new.txt").write_text("new", encoding="utf-8")

        assert dest.is_dir()
        # Old tree fully swapped out — only the new content remains.
        assert not (dest / "old.txt").exists()
        assert (dest / "new.txt").read_text(encoding="utf-8") == "new"

    def test_exception_leaves_original_dir_intact(self, tmp_path: Path) -> None:
        dest = tmp_path / "store"
        dest.mkdir()
        (dest / "keep.txt").write_text("keep", encoding="utf-8")

        with pytest.raises(_BoomError), atomic_replace_dir(dest) as tmp_dir:
            (tmp_dir / "doomed.txt").write_text("doomed", encoding="utf-8")
            raise _BoomError

        assert dest.is_dir()
        assert (dest / "keep.txt").read_text(encoding="utf-8") == "keep"
        assert not (dest / "doomed.txt").exists()
        # The temp build dir was cleaned up.
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "store"]
        assert leftovers == []

    def test_no_temp_dirs_left_after_success(self, tmp_path: Path) -> None:
        dest = tmp_path / "store"
        dest.mkdir()
        (dest / "old.txt").write_text("old", encoding="utf-8")
        with atomic_replace_dir(dest) as tmp_dir:
            (tmp_dir / "new.txt").write_text("new", encoding="utf-8")
        # Only the destination dir remains; no temp/backup siblings.
        siblings = [p.name for p in tmp_path.iterdir() if p.name != "store"]
        assert siblings == []


def test_module_does_not_fsync_dir_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """By default the helpers fsync the file but not the directory."""
    calls: list[str] = []
    real_fsync = os.fsync

    def _tracking_fsync(fd: int) -> None:
        calls.append("fsync")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", _tracking_fsync)
    # The directory fsync path opens the directory with os.open; track it too.
    real_open = os.open
    opened_dirs: list[str] = []

    def _tracking_open(path, flags, *args, **kwargs):  # type: ignore[no-untyped-def]
        if os.path.isdir(path):
            opened_dirs.append(str(path))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", _tracking_open)

    atomic_write_text(tmp_path / "out.txt", "x")
    # File was fsynced, but the directory was not opened for fsync.
    assert "fsync" in calls
    assert opened_dirs == []
