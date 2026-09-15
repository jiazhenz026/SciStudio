"""The MCP transport pointers under ``.scistudio/`` are written safely.

``.scistudio/`` may be group-shared. A plain write to ``mcp.sock.path`` followed
a symlink another user planted there and overwrote the file it pointed to
(no-context audit of #2329). ``_publish_mcp_port`` now writes each pointer
through a fresh ``O_CREAT | O_EXCL`` temporary file that replaces the entry. It
refuses, with a warning, a symlink or a file another user owns.
"""

from __future__ import annotations

import logging
import os
import stat
import sys
from pathlib import Path

import pytest

from scistudio.api.runtime import ApiRuntime

_POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX symlink and file-ownership semantics; Windows publishes a TCP port file, not the socket pointer",
)


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / ".scistudio").mkdir(parents=True)
    return project


def test_the_socket_pointer_is_written_whole_and_leaves_no_staging_file(runtime: ApiRuntime, tmp_path: Path) -> None:
    project = _project(tmp_path)
    socket_path = tmp_path / "private" / "mcp.sock"
    runtime._mcp_port = None
    runtime._mcp_socket_path = socket_path

    runtime._publish_mcp_port(project)

    pointer = project / ".scistudio" / "mcp.sock.path"
    assert pointer.read_text(encoding="utf-8") == str(socket_path)
    assert sorted(p.name for p in pointer.parent.iterdir()) == ["mcp.sock.path"]
    if sys.platform != "win32":
        assert stat.S_IMODE(pointer.stat().st_mode) == 0o600


@_POSIX_ONLY
def test_a_planted_symlink_at_the_pointer_is_refused(
    runtime: ApiRuntime, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    project = _project(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    pointer = project / ".scistudio" / "mcp.sock.path"
    pointer.symlink_to(victim)
    runtime._mcp_port = None
    runtime._mcp_socket_path = tmp_path / "private" / "mcp.sock"

    with caplog.at_level(logging.WARNING):
        runtime._publish_mcp_port(project)

    assert victim.read_text(encoding="utf-8") == "precious"
    assert pointer.is_symlink()
    assert any("symbolic link" in record.getMessage() for record in caplog.records)


@_POSIX_ONLY
def test_a_pointer_owned_by_another_user_is_refused(
    runtime: ApiRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    project = _project(tmp_path)
    pointer = project / ".scistudio" / "mcp.sock.path"
    pointer.write_text("theirs", encoding="utf-8")
    real_getuid = os.getuid
    monkeypatch.setattr(os, "getuid", lambda: real_getuid() + 1)
    runtime._mcp_port = None
    runtime._mcp_socket_path = tmp_path / "private" / "mcp.sock"

    with caplog.at_level(logging.WARNING):
        runtime._publish_mcp_port(project)

    assert pointer.read_text(encoding="utf-8") == "theirs"
    assert any("another user" in record.getMessage() for record in caplog.records)
