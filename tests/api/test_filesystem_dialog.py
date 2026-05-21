"""Regression tests for the native PowerShell file dialog (#617).

Workflow names are user-provided and can contain apostrophes (e.g.
``Bob's run``). When embedded directly into single-quoted PowerShell
strings in :func:`_native_dialog_windows`, an unescaped apostrophe
breaks the script syntax and prevents the native dialog from opening.

These tests mock :func:`subprocess.run` so they exercise the script
composition logic on every platform, independent of whether PowerShell
is actually available.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from scistudio.api.routes.filesystem import (
    _native_dialog_windows,
    _ps_single_quote_escape,
)


class _StubCompleted:
    """Minimal stand-in for :class:`subprocess.CompletedProcess`."""

    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _captured_ps_script(captured: list[list[str]]) -> str:
    """Extract the PowerShell ``-Command`` payload from the captured argv."""
    assert captured, "expected exactly one subprocess.run invocation"
    argv = captured[0]
    assert argv[0] == "powershell"
    # ``["powershell", "-NoProfile", "-NonInteractive", "-Command", <script>]``
    return argv[-1]


def test_ps_single_quote_escape_doubles_apostrophes() -> None:
    """PowerShell escapes ``'`` inside ``'...'`` by doubling it (``''``)."""
    assert _ps_single_quote_escape("") == ""
    assert _ps_single_quote_escape("plain") == "plain"
    assert _ps_single_quote_escape("Bob's run") == "Bob''s run"
    assert _ps_single_quote_escape("a'b'c") == "a''b''c"


def test_save_file_dialog_escapes_apostrophes_in_initial_dir() -> None:
    """``initial_dir = "Bob's run"`` must reach PowerShell as ``'Bob''s run'``."""
    captured: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: Any) -> _StubCompleted:
        captured.append(argv)
        return _StubCompleted(stdout="")

    with patch("scistudio.api.routes.filesystem.subprocess.run", side_effect=_fake_run):
        result = _native_dialog_windows(
            "save_file",
            initial_dir=r"C:\Users\Bob's runs",
            default_filename="workflow.yaml",
        )

    assert result == []
    script = _captured_ps_script(captured)
    # Apostrophes are doubled when interpolated into the PS single-quoted
    # strings; the raw user-supplied apostrophe never reaches PS as a
    # closing delimiter.
    assert r"$d.InitialDirectory = 'C:\Users\Bob''s runs';" in script
    assert "$d.FileName = 'workflow.yaml';" in script
    # Sanity: the raw single apostrophe with no doubling does NOT appear.
    assert "Bob's runs" not in script


def test_save_file_dialog_escapes_apostrophes_in_default_filename() -> None:
    """User-provided file names may also contain apostrophes (e.g. workflow titles)."""
    captured: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: Any) -> _StubCompleted:
        captured.append(argv)
        return _StubCompleted(stdout="")

    with patch("scistudio.api.routes.filesystem.subprocess.run", side_effect=_fake_run):
        _native_dialog_windows(
            "save_file",
            initial_dir=None,
            default_filename="Bob's run.yaml",
        )

    script = _captured_ps_script(captured)
    assert "$d.FileName = 'Bob''s run.yaml';" in script


def test_save_file_dialog_escapes_apostrophes_in_file_filter() -> None:
    """The ``file_filter`` parameter is also interpolated as a PS string."""
    captured: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: Any) -> _StubCompleted:
        captured.append(argv)
        return _StubCompleted(stdout="")

    with patch("scistudio.api.routes.filesystem.subprocess.run", side_effect=_fake_run):
        _native_dialog_windows(
            "save_file",
            initial_dir=None,
            default_filename="x.yaml",
            file_filter="Bob's filter (*.yaml)|*.yaml",
        )

    script = _captured_ps_script(captured)
    assert "$d.Filter = 'Bob''s filter (*.yaml)|*.yaml';" in script


def test_open_file_dialog_escapes_apostrophes_in_initial_dir() -> None:
    """File-open (Multiselect) mode also escapes ``initial_dir`` (#617)."""
    captured: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: Any) -> _StubCompleted:
        captured.append(argv)
        return _StubCompleted(stdout="")

    with patch("scistudio.api.routes.filesystem.subprocess.run", side_effect=_fake_run):
        _native_dialog_windows("file", initial_dir=r"D:\Bob's data")

    script = _captured_ps_script(captured)
    assert r"$d.InitialDirectory = 'D:\Bob''s data';" in script


def test_dialog_with_none_initial_dir_does_not_crash() -> None:
    """``initial_dir=None`` must render as ``''`` without triggering the escape."""
    captured: list[list[str]] = []

    def _fake_run(argv: list[str], **kwargs: Any) -> _StubCompleted:
        captured.append(argv)
        return _StubCompleted(stdout="")

    with patch("scistudio.api.routes.filesystem.subprocess.run", side_effect=_fake_run):
        _native_dialog_windows("file", initial_dir=None)

    script = _captured_ps_script(captured)
    assert "$d.InitialDirectory = '';" in script
