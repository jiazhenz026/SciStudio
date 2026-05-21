"""Extended tests for FileExchangeBridge and FileWatcher internals."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scistudio.blocks.app.bridge import FileExchangeBridge, _guess_mime
from scistudio.blocks.app.watcher import FileWatcher


class TestBridgeGuessMime:
    """_guess_mime in bridge.py — MIME type inference."""

    @pytest.mark.parametrize(
        ("suffix", "expected"),
        [
            (".csv", "text/csv"),
            (".tsv", "text/tab-separated-values"),
            (".json", "application/json"),
            (".txt", "text/plain"),
            (".png", "image/png"),
            (".tif", "image/tiff"),
            (".tiff", "image/tiff"),
            (".pdf", "application/pdf"),
        ],
    )
    def test_known_extensions(self, suffix: str, expected: str) -> None:
        assert _guess_mime(Path(f"file{suffix}")) == expected

    def test_unknown_extension(self) -> None:
        assert _guess_mime(Path("file.xyz")) == "application/octet-stream"


class TestBridgeLaunchArgvOverride:
    """FileExchangeBridge.launch — argv_override appends file paths instead of exchange_dir."""

    def test_argv_override_appends_file_paths(self, tmp_path: Path) -> None:
        """When argv_override is given, those paths replace the default exchange_dir trailing arg."""
        bridge = FileExchangeBridge()
        file_paths = ["/data/sample1.mzXML", "/data/sample2.mzML"]

        with patch("scistudio.blocks.app.bridge.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 12345
            bridge.launch(["echo"], tmp_path, argv_override=file_paths)

        cmd = mock_popen.call_args[0][0]
        # The command should end with the file paths, not the exchange dir
        assert cmd[-2:] == file_paths
        assert str(tmp_path) not in cmd

    def test_no_argv_override_uses_exchange_dir(self, tmp_path: Path) -> None:
        """Without argv_override, the exchange_dir is appended as trailing arg."""
        bridge = FileExchangeBridge()

        with patch("scistudio.blocks.app.bridge.subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 12345
            bridge.launch(["echo"], tmp_path)

        cmd = mock_popen.call_args[0][0]
        assert cmd[-1] == str(tmp_path)


class TestBridgePrepareExtended:
    """FileExchangeBridge.prepare — additional input types."""

    def test_prepare_json_serialisable(self, tmp_path: Path) -> None:
        bridge = FileExchangeBridge()
        exchange = tmp_path / "exchange"
        bridge.prepare({"data": [1, 2, 3]}, exchange)
        manifest = (exchange / "manifest.json").read_text(encoding="utf-8")
        assert '"json"' in manifest

    def test_prepare_bytes_input(self, tmp_path: Path) -> None:
        bridge = FileExchangeBridge()
        exchange = tmp_path / "exchange"
        bridge.prepare({"binary": b"\x00\x01\x02"}, exchange)
        manifest = (exchange / "manifest.json").read_text(encoding="utf-8")
        assert '"file"' in manifest

    def test_prepare_scalar_input(self, tmp_path: Path) -> None:
        bridge = FileExchangeBridge()
        exchange = tmp_path / "exchange"
        bridge.prepare({"threshold": 0.5, "name": "test"}, exchange)
        manifest = (exchange / "manifest.json").read_text(encoding="utf-8")
        assert '"scalar"' in manifest


class TestFileWatcherMatches:
    """FileWatcher._matches — pattern matching."""

    def test_matches_glob_pattern(self) -> None:
        watcher = FileWatcher(directory=Path("/tmp"), patterns=["*.csv"])
        assert watcher._matches("result.csv") is True
        assert watcher._matches("result.txt") is False

    def test_matches_multiple_patterns(self) -> None:
        watcher = FileWatcher(directory=Path("/tmp"), patterns=["*.csv", "*.tsv"])
        assert watcher._matches("data.csv") is True
        assert watcher._matches("data.tsv") is True
        assert watcher._matches("data.json") is False


class TestFileWatcherDiff:
    """FileWatcher._diff — detecting new and modified files."""

    def test_diff_detects_new_file(self, tmp_path: Path) -> None:
        watcher = FileWatcher(directory=tmp_path, patterns=["*.csv"])
        watcher._baseline = {}
        new_file = tmp_path / "output.csv"
        new_file.write_text("a,b\n1,2\n")
        current = {new_file: new_file.stat().st_mtime}
        result = watcher._diff(current)
        assert len(result) == 1
        assert result[0] == new_file

    def test_diff_detects_modified_file(self, tmp_path: Path) -> None:
        watcher = FileWatcher(directory=tmp_path, patterns=["*.csv"])
        existing_file = tmp_path / "data.csv"
        existing_file.write_text("old")
        old_mtime = existing_file.stat().st_mtime
        watcher._baseline = {existing_file: old_mtime - 10}  # Pretend it was older
        current = {existing_file: old_mtime}
        result = watcher._diff(current)
        assert len(result) == 1

    def test_diff_no_changes(self, tmp_path: Path) -> None:
        watcher = FileWatcher(directory=tmp_path, patterns=["*.csv"])
        existing = tmp_path / "data.csv"
        existing.write_text("data")
        mtime = existing.stat().st_mtime
        watcher._baseline = {existing: mtime}
        result = watcher._diff({existing: mtime})
        assert result == []


class TestFileWatcherSnapshot:
    """FileWatcher._snapshot — directory scanning."""

    def test_snapshot_empty_directory(self, tmp_path: Path) -> None:
        watcher = FileWatcher(directory=tmp_path, patterns=["*.csv"])
        result = watcher._snapshot()
        assert result == {}

    def test_snapshot_with_matching_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.csv").write_text("data")
        (tmp_path / "b.txt").write_text("data")
        watcher = FileWatcher(directory=tmp_path, patterns=["*.csv"])
        result = watcher._snapshot()
        assert len(result) == 1
        assert tmp_path / "a.csv" in result

    def test_snapshot_nonexistent_directory(self) -> None:
        watcher = FileWatcher(directory=Path("/nonexistent/path"), patterns=["*.csv"])
        result = watcher._snapshot()
        assert result == {}
