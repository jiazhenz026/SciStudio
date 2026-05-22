"""Behavior tests for ``ai_pty._validation`` (issue #1432).

Exercises ``_validate_project_dir`` directly so the validation module
has at least one focused unit test post-split.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.api.routes.ai_pty.validation import _validate_project_dir


def test_resolves_existing_absolute_dir(tmp_path: Path) -> None:
    """Resolving an existing absolute dir returns the canonical Path."""
    resolved = _validate_project_dir(str(tmp_path))
    assert resolved.is_absolute()
    assert resolved.is_dir()
    # ``resolve(strict=True)`` canonicalises so the returned value
    # equals ``tmp_path.resolve()`` (macOS ``/tmp`` → ``/private/tmp``).
    assert resolved == tmp_path.resolve()


def test_rejects_relative_path() -> None:
    """A relative path is refused before any filesystem touch."""
    with pytest.raises(RuntimeError, match="must be absolute"):
        _validate_project_dir("relative/path")


def test_rejects_nonexistent_path(tmp_path: Path) -> None:
    """A non-existent absolute path raises FileNotFoundError."""
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        _validate_project_dir(str(missing))


def test_rejects_file_not_dir(tmp_path: Path) -> None:
    """An existing absolute path that is a file (not dir) is refused."""
    file_path = tmp_path / "regular.txt"
    file_path.write_text("not a dir", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="not a directory"):
        _validate_project_dir(str(file_path))
