"""Tests for _native_dialog_windows: modern IFileOpenDialog COM folder picker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.skipif(
    __import__("sys").platform != "win32",
    reason="Windows-only dialog",
)
class TestNativeDialogWindowsDirectory:
    """Verify that the directory branch uses the modern IFileOpenDialog COM dialog."""

    def test_directory_mode_uses_ifileopendialog(self) -> None:
        """The PowerShell script should compile a C# FolderPicker via Add-Type,
        NOT use the legacy FolderBrowserDialog."""
        from scistudio.api.routes.filesystem import _native_dialog_windows

        mock_result = MagicMock()
        mock_result.stdout = r"C:\Users\test\Documents"
        mock_result.returncode = 0

        with patch("scistudio.api.routes.filesystem.subprocess.run", return_value=mock_result) as mock_run:
            result = _native_dialog_windows("directory", None)

        mock_run.assert_called_once()
        ps_command = mock_run.call_args[0][0]
        ps_script = ps_command[-1]  # last arg is the -Command value

        # Must use IFileOpenDialog COM approach, not FolderBrowserDialog
        assert "FolderPicker" in ps_script
        assert "IFileDialog" in ps_script
        assert "Add-Type -TypeDefinition" in ps_script
        assert "$owner.TopMost = $true;" in ps_script
        assert "[FolderPicker]::Pick('Select Folder', $owner.Handle)" in ps_script
        assert "FolderBrowserDialog" not in ps_script

        assert result == [r"C:\Users\test\Documents"]

    def test_directory_mode_cancel_returns_empty(self) -> None:
        """When the user cancels, the function should return an empty list."""
        from scistudio.api.routes.filesystem import _native_dialog_windows

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("scistudio.api.routes.filesystem.subprocess.run", return_value=mock_result):
            result = _native_dialog_windows("directory", None)

        assert result == []

    def test_file_mode_uses_openfiledialog(self) -> None:
        """The file branch should still use OpenFileDialog (not IFileOpenDialog)."""
        from scistudio.api.routes.filesystem import _native_dialog_windows

        mock_result = MagicMock()
        mock_result.stdout = r"C:\file1.txt|C:\file2.txt"
        mock_result.returncode = 0

        with patch("scistudio.api.routes.filesystem.subprocess.run", return_value=mock_result) as mock_run:
            result = _native_dialog_windows("file", None)

        ps_command = mock_run.call_args[0][0]
        ps_script = ps_command[-1]

        assert "OpenFileDialog" in ps_script
        assert "FolderPicker" not in ps_script
        assert "$owner.TopMost = $true;" in ps_script
        assert "$d.ShowDialog($owner)" in ps_script
        assert result == [r"C:\file1.txt", r"C:\file2.txt"]


class TestNativeDialogNoTimeout:
    """Regression for #678: the native dialog must NOT enforce a 120s timeout.

    On a desktop-local server the user may legitimately spend many minutes
    browsing for a file. The previous 120s timeout killed the dialog process
    from under the user. These tests assert each platform helper invokes
    ``subprocess.run`` with ``timeout=None`` (or no ``timeout`` kwarg).
    """

    @staticmethod
    def _assert_no_timeout(mock_run: MagicMock) -> None:
        timeout = mock_run.call_args.kwargs.get("timeout", None)
        assert timeout is None, (
            f"native dialog must not enforce a finite subprocess timeout (got {timeout!r}); see #678"
        )

    def test_windows_dialog_has_no_timeout(self) -> None:
        from scistudio.api.routes.filesystem import _native_dialog_windows

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("scistudio.api.routes.filesystem.subprocess.run", return_value=mock_result) as mock_run:
            _native_dialog_windows("directory", None)

        self._assert_no_timeout(mock_run)

    def test_macos_dialog_has_no_timeout(self) -> None:
        from scistudio.api.routes.filesystem import _native_dialog_macos

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("scistudio.api.routes.filesystem.subprocess.run", return_value=mock_result) as mock_run:
            _native_dialog_macos("file", None)

        self._assert_no_timeout(mock_run)

    def test_macos_save_file_result_converts_file_hfs_path(self) -> None:
        from scistudio.api.routes.filesystem import _native_dialog_macos

        mock_result = MagicMock()
        mock_result.stdout = "file Macintosh HD:Users:jiazhenz:Desktop:spectrum.svg"
        mock_result.returncode = 0

        with patch("scistudio.api.routes.filesystem.subprocess.run", return_value=mock_result):
            result = _native_dialog_macos("save_file", "/Users/jiazhenz/Desktop", "spectrum.svg")

        assert result == ["/Users/jiazhenz/Desktop/spectrum.svg"]

    def test_linux_dialog_has_no_timeout(self) -> None:
        from scistudio.api.routes.filesystem import _native_dialog_linux

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("scistudio.api.routes.filesystem.subprocess.run", return_value=mock_result) as mock_run:
            _native_dialog_linux("file", None)

        self._assert_no_timeout(mock_run)


class TestResolveDialogStartDir:
    """#1915: load/save dialogs default to the active project root, not $HOME.

    Project-scope dialogs (the default) prefer ``project_root``; home-scope
    dialogs (``prefer_home`` — create/open project, diagnostic export) keep
    opening at last-used / home.
    """

    def test_explicit_initial_dir_wins(self, tmp_path) -> None:
        from scistudio.api.routes.filesystem import _resolve_dialog_start_dir

        chosen = tmp_path / "chosen"
        chosen.mkdir()
        project = tmp_path / "project"
        project.mkdir()
        # Explicit, valid initial_dir beats project root regardless of scope.
        assert _resolve_dialog_start_dir(str(chosen), False, str(project), None) == str(chosen)
        assert _resolve_dialog_start_dir(str(chosen), True, str(project), None) == str(chosen)

    def test_project_scope_defaults_to_project_root(self, tmp_path) -> None:
        from scistudio.api.routes.filesystem import _resolve_dialog_start_dir

        project = tmp_path / "project"
        project.mkdir()
        assert _resolve_dialog_start_dir(None, False, str(project), None) == str(project)

    def test_project_root_beats_last_used(self, tmp_path) -> None:
        from scistudio.api.routes.filesystem import _resolve_dialog_start_dir

        project = tmp_path / "project"
        project.mkdir()
        last_used = tmp_path / "elsewhere"
        last_used.mkdir()
        # Project-scope: project root is the reliable default, above last-used.
        assert _resolve_dialog_start_dir(None, False, str(project), str(last_used)) == str(project)

    def test_prefer_home_ignores_project_root(self, tmp_path) -> None:
        from scistudio.api.routes.filesystem import _resolve_dialog_start_dir

        project = tmp_path / "project"
        project.mkdir()
        last_used = tmp_path / "picked-before"
        last_used.mkdir()
        # Home-scope: project root is skipped; last-used is honored.
        assert _resolve_dialog_start_dir(None, True, str(project), str(last_used)) == str(last_used)

    def test_prefer_home_falls_back_to_home(self, tmp_path) -> None:
        from pathlib import Path

        from scistudio.api.routes.filesystem import _resolve_dialog_start_dir

        project = tmp_path / "project"
        project.mkdir()
        # Home-scope with no last-used: home, never the project root.
        assert _resolve_dialog_start_dir(None, True, str(project), None) == str(Path.home())

    def test_no_active_project_falls_back_to_last_used_then_home(self, tmp_path) -> None:
        from pathlib import Path

        from scistudio.api.routes.filesystem import _resolve_dialog_start_dir

        last_used = tmp_path / "last"
        last_used.mkdir()
        assert _resolve_dialog_start_dir(None, False, None, str(last_used)) == str(last_used)
        assert _resolve_dialog_start_dir(None, False, None, None) == str(Path.home())

    def test_nonexistent_candidates_are_skipped(self, tmp_path) -> None:
        from pathlib import Path

        from scistudio.api.routes.filesystem import _resolve_dialog_start_dir

        missing_initial = str(tmp_path / "does-not-exist")
        missing_project = str(tmp_path / "also-missing")
        # An invalid initial_dir and a stale project_root both degrade to home.
        assert _resolve_dialog_start_dir(missing_initial, False, missing_project, None) == str(Path.home())
