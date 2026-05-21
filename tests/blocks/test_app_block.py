"""Tests for AppBlock — mock subprocess + file watcher."""

from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Thread
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from scistudio.blocks.app.bridge import FileExchangeBridge
from scistudio.blocks.app.command_validator import validate_app_command
from scistudio.blocks.app.watcher import FileWatcher
from scistudio.core.types.artifact import Artifact


class TestFileWatcher:
    """FileWatcher — polling-based output detection."""

    def test_detects_new_file(self, tmp_path: Path) -> None:
        """Writing an output file after start() triggers detection."""
        output_dir = tmp_path / "outputs"
        output_dir.mkdir()

        watcher = FileWatcher(directory=output_dir, patterns=["*.csv"], timeout=5, poll_interval=0.05)
        watcher.start()

        # Write a file in a background thread.
        def write_file() -> None:
            time.sleep(0.05)
            (output_dir / "result.csv").write_text("a,b\n1,2\n")

        t = Thread(target=write_file)
        t.start()

        files = watcher.wait_for_output()
        t.join()
        watcher.stop()

        assert len(files) == 1
        assert files[0].name == "result.csv"

    def test_timeout(self, tmp_path: Path) -> None:
        """No output within timeout raises TimeoutError."""
        output_dir = tmp_path / "outputs"
        output_dir.mkdir()

        watcher = FileWatcher(directory=output_dir, patterns=["*.csv"], timeout=0.3, poll_interval=0.05)
        watcher.start()

        with pytest.raises(TimeoutError):
            watcher.wait_for_output()
        watcher.stop()

    def test_pattern_filtering(self, tmp_path: Path) -> None:
        """Only files matching the pattern are detected."""
        output_dir = tmp_path / "outputs"
        output_dir.mkdir()

        watcher = FileWatcher(directory=output_dir, patterns=["*.txt"], timeout=5, poll_interval=0.05)
        watcher.start()

        def write_files() -> None:
            time.sleep(0.05)
            (output_dir / "data.csv").write_text("ignored")
            time.sleep(0.05)
            (output_dir / "result.txt").write_text("found")

        t = Thread(target=write_files)
        t.start()

        files = watcher.wait_for_output()
        t.join()
        watcher.stop()

        assert len(files) == 1
        assert files[0].suffix == ".txt"

    def test_not_started_raises(self, tmp_path: Path) -> None:
        watcher = FileWatcher(directory=tmp_path, patterns=["*"])
        with pytest.raises(RuntimeError, match="not been started"):
            watcher.wait_for_output()


class TestFileExchangeBridge:
    """FileExchangeBridge — prepare and collect steps."""

    def test_prepare_creates_manifest(self, tmp_path: Path) -> None:
        bridge = FileExchangeBridge()
        bridge.prepare({"value": 42, "name": "test"}, tmp_path)

        manifest = tmp_path / "manifest.json"
        assert manifest.exists()

        import json

        data = json.loads(manifest.read_text())
        assert data["value"]["type"] == "scalar"
        assert data["value"]["value"] == 42
        assert data["name"]["type"] == "scalar"
        assert data["name"]["value"] == "test"

    def test_prepare_handles_bytes(self, tmp_path: Path) -> None:
        bridge = FileExchangeBridge()
        bridge.prepare({"blob": b"binary data"}, tmp_path)

        import json

        data = json.loads((tmp_path / "manifest.json").read_text())
        assert data["blob"]["type"] == "file"
        blob_path = Path(data["blob"]["path"])
        assert blob_path.exists()
        assert blob_path.read_bytes() == b"binary data"

    def test_collect_creates_artifacts(self, tmp_path: Path) -> None:
        bridge = FileExchangeBridge()

        f1 = tmp_path / "output1.csv"
        f1.write_text("a,b\n1,2\n")
        f2 = tmp_path / "output2.png"
        f2.write_bytes(b"fake png")

        results = bridge.collect([f1, f2])
        assert "output1" in results
        assert "output2" in results
        assert isinstance(results["output1"], Artifact)
        assert results["output1"].mime_type == "text/csv"
        assert results["output2"].mime_type == "image/png"


class TestAppBlockExchangeDir:
    """#68: Exchange directory location — project workspace vs tempfile fallback."""

    def test_exchange_dir_uses_project_workspace(self, tmp_path: Path) -> None:
        """When project_dir and block_id are in config, exchange dir is in project workspace."""
        from unittest.mock import MagicMock, patch

        from scistudio.blocks.app.app_block import AppBlock
        from scistudio.blocks.base.config import BlockConfig

        block = AppBlock()

        project_dir = tmp_path / "my_project"
        project_dir.mkdir()
        config = BlockConfig(
            params={
                "app_command": "echo hello",
                "project_dir": str(project_dir),
                "block_id": "block_123",
            }
        )

        expected_dir = project_dir / "data" / "exchange" / "block_123"

        # Patch bridge and watcher to avoid real subprocess execution.
        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.subprocess") as _mock_sub,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            # Make bridge.launch return a mock process.
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 12345
            mock_bridge.launch.return_value = mock_proc

            # Patch FileWatcher to return fake output files immediately.
            with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
                mock_watcher = MagicMock()
                mock_watcher_cls.return_value = mock_watcher
                fake_output = tmp_path / "result.csv"
                fake_output.write_text("a,b\n1,2\n")
                mock_watcher.wait_for_output.return_value = [fake_output]

                mock_bridge.collect.return_value = {}

                block.run(inputs={}, config=config)

            # Verify bridge.prepare was called with the project workspace path.
            call_args = mock_bridge.prepare.call_args
            actual_exchange_dir = call_args[0][1]  # second positional arg
            assert actual_exchange_dir == expected_dir

    def test_exchange_dir_falls_back_to_tempfile(self, tmp_path: Path) -> None:
        """When project_dir is not set, exchange dir falls back to tempfile."""
        from unittest.mock import MagicMock, patch

        from scistudio.blocks.app.app_block import AppBlock
        from scistudio.blocks.base.config import BlockConfig

        block = AppBlock()

        config = BlockConfig(
            params={
                "app_command": "echo hello",
            }
        )

        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.subprocess") as _mock_sub,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
            patch(
                "scistudio.blocks.app.app_block.tempfile.mkdtemp", return_value=str(tmp_path / "fallback")
            ) as mock_mkdtemp,
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 12345
            mock_bridge.launch.return_value = mock_proc

            with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
                mock_watcher = MagicMock()
                mock_watcher_cls.return_value = mock_watcher
                fake_output = tmp_path / "result.csv"
                fake_output.write_text("a,b\n1,2\n")
                mock_watcher.wait_for_output.return_value = [fake_output]

                mock_bridge.collect.return_value = {}

                block.run(inputs={}, config=config)

            # Verify tempfile.mkdtemp was called as fallback.
            mock_mkdtemp.assert_called_once_with(prefix="scistudio_app_")


class TestFileExchangeBridgeCollection:
    """ADR-020: Collection handling in bridge.prepare()."""

    def test_prepare_handles_collection(self, tmp_path: Path) -> None:
        """Bridge should serialize Collection items into a subdirectory."""
        from scistudio.core.types.array import Array
        from scistudio.core.types.collection import Collection

        # ADR-027 D2: construct plain 2D Arrays instead of the removed
        # core Image class (which now lives in scistudio-blocks-imaging).
        items = [
            Array(axes=["y", "x"], shape=(3, 3), dtype="uint8"),
            Array(axes=["y", "x"], shape=(5, 5), dtype="float32"),
        ]
        items[0]._transient_data = np.zeros((3, 3), dtype=np.uint8)
        items[1]._transient_data = np.zeros((5, 5), dtype=np.float32)
        collection = Collection(items)

        bridge = FileExchangeBridge()
        bridge.prepare({"images": collection}, tmp_path)

        import json

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["images"]["type"] == "collection"
        assert len(manifest["images"]["items"]) == 2


# ---------------------------------------------------------------------------
# Issue #70: Command validation tests
# ---------------------------------------------------------------------------


class TestCommandValidator:
    """validate_app_command — shell injection prevention."""

    def test_validate_command_rejects_metacharacters(self) -> None:
        """Commands with semicolons (injection) are rejected."""
        with pytest.raises(ValueError, match="shell metacharacters"):
            validate_app_command("rm -rf / ; echo pwned")

    def test_validate_command_rejects_pipe(self) -> None:
        """Commands with pipe characters are rejected."""
        with pytest.raises(ValueError, match="shell metacharacters"):
            validate_app_command("cat | nc")

    def test_validate_command_accepts_valid_executable(self) -> None:
        """A command that resolves on PATH is accepted and returned as list."""
        result = validate_app_command("python")
        assert isinstance(result, list)
        assert result == ["python"]

    def test_validate_command_accepts_list_format(self) -> None:
        """Pre-split list commands are accepted as-is."""
        result = validate_app_command(["python", "--version"])
        assert result == ["python", "--version"]

    def test_validate_command_rejects_not_found(self) -> None:
        """An executable that cannot be resolved is rejected."""
        with pytest.raises(ValueError, match="not found"):
            validate_app_command("nonexistent_binary_xyz")

    def test_validate_command_rejects_metachar_in_list(self) -> None:
        """Even list-form commands are checked for metacharacters."""
        with pytest.raises(ValueError, match="shell metacharacters"):
            validate_app_command(["bash", "-c", "echo $HOME"])

    def test_validate_command_rejects_empty(self) -> None:
        """An empty command string is rejected."""
        with pytest.raises(ValueError, match="Empty command"):
            validate_app_command("")

    def test_validate_command_accepts_parentheses_in_path(self, tmp_path: Path) -> None:
        """Parentheses in Windows-style paths like 'Program Files (x86)' are safe (#463)."""
        # Create a fake executable inside a path containing parentheses
        exe_dir = tmp_path / "Program Files (x86)" / "MyApp"
        exe_dir.mkdir(parents=True)
        exe_file = exe_dir / "myapp.exe"
        exe_file.write_text("fake")
        exe_file.chmod(0o755)

        result = validate_app_command([str(exe_file)])
        assert result == [str(exe_file)]

    def test_validate_command_accepts_parentheses_in_string(self, tmp_path: Path) -> None:
        """Parentheses in a string command path are not rejected as metacharacters (#463)."""
        exe_dir = tmp_path / "Program Files (x86)" / "Tool"
        exe_dir.mkdir(parents=True)
        exe_file = exe_dir / "tool.exe"
        exe_file.write_text("fake")
        exe_file.chmod(0o755)

        # shlex.split will handle the quoted path
        result = validate_app_command(f'"{exe_file}"')
        assert result == [str(exe_file)]

    def test_validate_command_accepts_macos_app_bundle(self, tmp_path: Path) -> None:
        """macOS .app bundles (directories) should be accepted on darwin (#483)."""
        from unittest.mock import patch

        app_bundle = tmp_path / "Fiji.app"
        app_bundle.mkdir()

        with patch("scistudio.blocks.app.command_validator.sys") as mock_sys:
            mock_sys.platform = "darwin"
            result = validate_app_command([str(app_bundle)])
            assert result == [str(app_bundle)]

    def test_validate_command_rejects_app_bundle_on_non_darwin(self, tmp_path: Path) -> None:
        """A .app directory should NOT be accepted on non-darwin platforms (#483)."""
        from unittest.mock import patch

        app_bundle = tmp_path / "Fiji.app"
        app_bundle.mkdir()

        with patch("scistudio.blocks.app.command_validator.sys") as mock_sys:
            mock_sys.platform = "linux"
            with pytest.raises(ValueError, match="not found"):
                validate_app_command([str(app_bundle)])


class TestBridgeMacOSAppBundle:
    """#483: .app bundle launch rewriting on macOS."""

    def test_launch_rewrites_app_bundle_on_darwin(self, tmp_path: Path) -> None:
        """On macOS, .app bundles should be launched via ``open -W -n -a`` (#677).

        ``-W`` is required so ``open`` blocks until the launched .app exits —
        without it, ``Popen`` only tracks the short-lived launcher and the
        watcher immediately raises ``ProcessExitedWithoutOutputError`` (#677
        was a regression of #483 once the lifetime mismatch was detected).
        ``-n`` forces a fresh instance so the watcher is keyed to the new
        process.
        """
        from unittest.mock import patch

        bridge = FileExchangeBridge()
        exchange_dir = tmp_path / "exchange"
        exchange_dir.mkdir()

        app_bundle = tmp_path / "Fiji.app"
        app_bundle.mkdir()

        with (
            patch("scistudio.blocks.app.bridge.sys") as mock_sys,
            patch("scistudio.blocks.app.command_validator.sys") as mock_val_sys,
            patch("scistudio.blocks.app.bridge.subprocess.Popen") as mock_popen,
        ):
            mock_sys.platform = "darwin"
            mock_val_sys.platform = "darwin"
            mock_proc = MagicMock()
            mock_proc.pid = 999
            mock_popen.return_value = mock_proc

            bridge.launch([str(app_bundle)], exchange_dir)

            call_args = mock_popen.call_args
            cmd = call_args[0][0]
            assert cmd[0] == "open"
            # -W and -n must both be present before the -a <app> pair so
            # open blocks on a fresh .app instance.
            assert "-W" in cmd, f"expected -W flag in argv: {cmd}"
            assert "-n" in cmd, f"expected -n flag in argv: {cmd}"
            assert "-a" in cmd
            a_index = cmd.index("-a")
            assert cmd[a_index + 1] == str(app_bundle)
            assert "--args" in cmd

    def test_launch_does_not_rewrite_on_non_darwin(self, tmp_path: Path) -> None:
        """On non-macOS, .app paths should NOT be rewritten."""
        from unittest.mock import patch

        bridge = FileExchangeBridge()
        exchange_dir = tmp_path / "exchange"
        exchange_dir.mkdir()

        exe = tmp_path / "myapp.exe"
        exe.write_text("fake")
        exe.chmod(0o755)

        with (
            patch("scistudio.blocks.app.bridge.sys") as mock_sys,
            patch("scistudio.blocks.app.bridge.subprocess.Popen") as mock_popen,
        ):
            mock_sys.platform = "win32"
            mock_proc = MagicMock()
            mock_proc.pid = 999
            mock_popen.return_value = mock_proc

            bridge.launch([str(exe)], exchange_dir)

            call_args = mock_popen.call_args
            cmd = call_args[0][0]
            assert cmd[0] == str(exe)
            assert "open" not in cmd


# ---------------------------------------------------------------------------
# Issue #70: FileWatcher TOCTOU / stability tests
# ---------------------------------------------------------------------------


class TestFileWatcherStability:
    """FileWatcher stability_period and done_marker (TOCTOU mitigation)."""

    def test_watcher_stability_check(self, tmp_path: Path) -> None:
        """File should NOT be returned until its mtime is stable for stability_period."""
        output_dir = tmp_path / "outputs"
        output_dir.mkdir()

        stability = 0.2
        watcher = FileWatcher(
            directory=output_dir,
            patterns=["*.csv"],
            timeout=10,
            poll_interval=0.05,
            stability_period=stability,
        )
        watcher.start()

        # Write file, then wait for it to be returned.
        (output_dir / "result.csv").write_text("a,b\n1,2\n")
        t0 = time.monotonic()

        files = watcher.wait_for_output()
        elapsed = time.monotonic() - t0
        watcher.stop()

        assert len(files) == 1
        assert files[0].name == "result.csv"
        # Must have waited at least stability_period before returning.
        assert elapsed >= stability - 0.15  # small tolerance for scheduling jitter

    def test_watcher_done_marker(self, tmp_path: Path) -> None:
        """A done-marker file causes immediate return of other new files."""
        output_dir = tmp_path / "outputs"
        output_dir.mkdir()

        watcher = FileWatcher(
            directory=output_dir,
            patterns=["*"],
            timeout=10,
            poll_interval=0.05,
            stability_period=60.0,  # Very high — would block without marker.
            done_marker="*.done",
        )
        watcher.start()

        def write_files() -> None:
            time.sleep(0.05)
            (output_dir / "result.csv").write_text("a,b\n1,2\n")
            (output_dir / "output.done").write_text("")

        t = Thread(target=write_files)
        t.start()

        t0 = time.monotonic()
        files = watcher.wait_for_output()
        elapsed = time.monotonic() - t0
        t.join()
        watcher.stop()

        # Should return almost immediately (not wait 60s stability).
        assert elapsed < 5.0
        names = [f.name for f in files]
        assert "result.csv" in names
        # The marker file itself should NOT be in results.
        assert "output.done" not in names

    def test_watcher_changing_file_delays_return(self, tmp_path: Path) -> None:
        """Modifying a file during stability window resets the stability clock."""
        output_dir = tmp_path / "outputs"
        output_dir.mkdir()

        stability = 0.2
        watcher = FileWatcher(
            directory=output_dir,
            patterns=["*.csv"],
            timeout=15,
            poll_interval=0.05,
            stability_period=stability,
        )
        watcher.start()

        fpath = output_dir / "result.csv"
        fpath.write_text("partial")
        t0 = time.monotonic()

        # Modify the file 0.1s later — should reset the stability clock.
        def modify_file() -> None:
            time.sleep(0.1)
            fpath.write_text("complete data\n")
            # Touch to update mtime.
            os.utime(fpath, None)

        t = Thread(target=modify_file)
        t.start()

        files = watcher.wait_for_output()
        elapsed = time.monotonic() - t0
        t.join()
        watcher.stop()

        assert len(files) == 1
        # Total elapsed should be at least 0.1 (delay) + stability_period.
        assert elapsed >= 0.1 + stability - 0.15  # tolerance


# ---------------------------------------------------------------------------
# #338: Subprocess leak — proc.wait() must be called after run()
# #339: Tempfile exchange directory leak — temp dirs must be cleaned up
# ---------------------------------------------------------------------------


class TestAppBlockSubprocessCleanup:
    """#338: Verify subprocess is properly waited on / terminated after run()."""

    def _make_running_block(self):
        """Create an AppBlock instance (state machine removed per #1334)."""
        from scistudio.blocks.app.app_block import AppBlock

        return AppBlock()

    def test_proc_wait_called_on_normal_exit(self, tmp_path: Path) -> None:
        """After successful run(), proc.wait() must be called to reap the process."""
        from unittest.mock import MagicMock, patch

        from scistudio.blocks.base.config import BlockConfig

        block = self._make_running_block()
        config = BlockConfig(params={"app_command": "echo hello"})

        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
            patch(
                "scistudio.blocks.app.app_block.tempfile.mkdtemp",
                return_value=str(tmp_path / "temp_exchange"),
            ),
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 12345
            mock_proc.wait.return_value = 0
            mock_bridge.launch.return_value = mock_proc

            with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
                mock_watcher = MagicMock()
                mock_watcher_cls.return_value = mock_watcher
                fake_output = tmp_path / "result.csv"
                fake_output.write_text("a,b\n1,2\n")
                mock_watcher.wait_for_output.return_value = [fake_output]
                mock_bridge.collect.return_value = {}

                block.run(inputs={}, config=config)

            # proc.wait() must have been called at least once (cleanup).
            assert mock_proc.wait.called, "proc.wait() was never called — subprocess leak (#338)"

    def test_proc_terminated_when_wait_times_out(self, tmp_path: Path) -> None:
        """If proc.wait() times out, proc.terminate() must be called."""
        import subprocess as _subprocess
        from unittest.mock import MagicMock, patch

        from scistudio.blocks.base.config import BlockConfig

        block = self._make_running_block()
        config = BlockConfig(params={"app_command": "echo hello"})

        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
            patch(
                "scistudio.blocks.app.app_block.tempfile.mkdtemp",
                return_value=str(tmp_path / "temp_exchange"),
            ),
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 12345
            # First wait times out, second (after terminate) succeeds.
            mock_proc.wait.side_effect = [
                _subprocess.TimeoutExpired(cmd="echo", timeout=5),
                0,  # after terminate
            ]
            mock_bridge.launch.return_value = mock_proc

            with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
                mock_watcher = MagicMock()
                mock_watcher_cls.return_value = mock_watcher
                fake_output = tmp_path / "result.csv"
                fake_output.write_text("a,b\n1,2\n")
                mock_watcher.wait_for_output.return_value = [fake_output]
                mock_bridge.collect.return_value = {}

                block.run(inputs={}, config=config)

            mock_proc.terminate.assert_called_once()

    def test_proc_waited_on_process_exited_without_output(self, tmp_path: Path) -> None:
        """On ProcessExitedWithoutOutputError, proc must still be waited on.

        Per #1334, AppBlock now signals cancellation by raising
        ``BlockCancelledByAppError`` instead of returning ``{}`` — the engine
        catches it in the worker and emits ``final_state="cancelled"``.
        The proc.wait() reaping at ``finally`` (#338) must still fire.
        """
        from unittest.mock import MagicMock, patch

        import pytest

        from scistudio.blocks.app.watcher import ProcessExitedWithoutOutputError
        from scistudio.blocks.base.config import BlockConfig
        from scistudio.blocks.base.exceptions import BlockCancelledByAppError

        block = self._make_running_block()
        config = BlockConfig(params={"app_command": "echo hello"})

        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
            patch(
                "scistudio.blocks.app.app_block.tempfile.mkdtemp",
                return_value=str(tmp_path / "temp_exchange"),
            ),
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 12345
            mock_proc.wait.return_value = 0
            mock_bridge.launch.return_value = mock_proc

            with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
                mock_watcher = MagicMock()
                mock_watcher_cls.return_value = mock_watcher
                mock_watcher.wait_for_output.side_effect = ProcessExitedWithoutOutputError("Process exited")
                mock_bridge.collect.return_value = {}

                with pytest.raises(BlockCancelledByAppError):
                    block.run(inputs={}, config=config)

            assert mock_proc.wait.called, "proc.wait() not called on cancelled path (#338)"


class TestAppBlockTempDirCleanup:
    """#339: Verify temp exchange directories are cleaned up."""

    def _make_running_block(self):
        from scistudio.blocks.app.app_block import AppBlock

        return AppBlock()

    def test_temp_exchange_dir_cleaned_up(self, tmp_path: Path) -> None:
        """Temp exchange dir (no project_dir) must be removed after run()."""
        from unittest.mock import MagicMock, patch

        from scistudio.blocks.base.config import BlockConfig

        block = self._make_running_block()

        temp_dir = tmp_path / "scistudio_app_temp"
        config = BlockConfig(params={"app_command": "echo hello"})

        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
            patch(
                "scistudio.blocks.app.app_block.tempfile.mkdtemp",
                return_value=str(temp_dir),
            ),
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 12345
            mock_proc.wait.return_value = 0
            mock_bridge.launch.return_value = mock_proc

            with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
                mock_watcher = MagicMock()
                mock_watcher_cls.return_value = mock_watcher
                fake_output = tmp_path / "result.csv"
                fake_output.write_text("a,b\n1,2\n")
                mock_watcher.wait_for_output.return_value = [fake_output]
                mock_bridge.collect.return_value = {}

                block.run(inputs={}, config=config)

        # The temp dir should have been cleaned up.
        assert not temp_dir.exists(), "Temp exchange dir was not cleaned up (#339)"

    def test_project_exchange_dir_not_cleaned_up(self, tmp_path: Path) -> None:
        """Project exchange dir (project_dir + block_id) must NOT be removed."""
        from unittest.mock import MagicMock, patch

        from scistudio.blocks.base.config import BlockConfig

        block = self._make_running_block()

        project_dir = tmp_path / "my_project"
        project_dir.mkdir()
        config = BlockConfig(
            params={
                "app_command": "echo hello",
                "project_dir": str(project_dir),
                "block_id": "block_123",
            }
        )

        exchange_dir = project_dir / "data" / "exchange" / "block_123"

        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 12345
            mock_proc.wait.return_value = 0
            mock_bridge.launch.return_value = mock_proc

            with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
                mock_watcher = MagicMock()
                mock_watcher_cls.return_value = mock_watcher
                fake_output = tmp_path / "result.csv"
                fake_output.write_text("a,b\n1,2\n")
                mock_watcher.wait_for_output.return_value = [fake_output]
                mock_bridge.collect.return_value = {}

                block.run(inputs={}, config=config)

        # Project exchange dir must still exist.
        assert exchange_dir.exists(), "Project exchange dir was incorrectly cleaned up (#339)"

    def test_temp_dir_cleaned_up_on_error(self, tmp_path: Path) -> None:
        """Temp exchange dir must be cleaned up even if run() raises."""
        from unittest.mock import MagicMock, patch

        from scistudio.blocks.base.config import BlockConfig

        block = self._make_running_block()

        temp_dir = tmp_path / "scistudio_app_error"
        config = BlockConfig(params={"app_command": "echo hello"})

        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
            patch(
                "scistudio.blocks.app.app_block.tempfile.mkdtemp",
                return_value=str(temp_dir),
            ),
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            # bridge.launch raises an error.
            mock_bridge.launch.side_effect = RuntimeError("launch failed")

            with pytest.raises(RuntimeError, match="launch failed"):
                block.run(inputs={}, config=config)

        # Even on error, temp dir should be cleaned up.
        assert not temp_dir.exists(), "Temp dir not cleaned up after error (#339)"


# ---------------------------------------------------------------------------
# Issue #680: AppBlock variadic ports + extension-based output binning
# ---------------------------------------------------------------------------


class TestAppBlockVariadicPorts:
    """Issue #680: ``config.{input,output}_ports`` overrides ClassVar ports."""

    def test_effective_input_ports_use_config_when_set(self) -> None:
        from scistudio.blocks.app.app_block import AppBlock

        block = AppBlock(
            config={
                "params": {
                    "input_ports": [
                        {"name": "alpha", "types": ["DataObject"]},
                        {"name": "beta", "types": ["DataObject"]},
                    ]
                }
            }
        )

        ports = block.get_effective_input_ports()
        assert [p.name for p in ports] == ["alpha", "beta"]

    def test_effective_output_ports_use_config_when_set(self) -> None:
        from scistudio.blocks.app.app_block import AppBlock

        block = AppBlock(
            config={
                "params": {
                    "output_ports": [
                        {"name": "tables", "types": ["DataObject"], "extension": "csv"},
                    ]
                }
            }
        )

        ports = block.get_effective_output_ports()
        assert [p.name for p in ports] == ["tables"]

    def test_falls_back_to_classvar_when_config_unset(self) -> None:
        from scistudio.blocks.app.app_block import AppBlock

        block = AppBlock()
        # ClassVar ports remain visible when no config override is given.
        assert [p.name for p in block.get_effective_input_ports()] == ["data"]
        assert [p.name for p in block.get_effective_output_ports()] == ["result"]


class TestAppBlockExtensionBinner:
    """Issue #680: ``_bin_outputs_by_extension`` routing rules."""

    def _make_block_with_ports(self, port_dicts: list[dict[str, Any]]) -> Any:
        from scistudio.blocks.app.app_block import AppBlock

        return AppBlock(config={"params": {"output_ports": port_dicts}})

    def test_routes_files_by_extension_case_insensitive(self, tmp_path: Path) -> None:
        from scistudio.blocks.base.config import BlockConfig

        f1 = tmp_path / "image.TIF"
        f2 = tmp_path / "image2.tif"
        f3 = tmp_path / "summary.csv"
        for f in (f1, f2, f3):
            f.write_text("x", encoding="utf-8")

        block = self._make_block_with_ports(
            [
                {"name": "images", "types": ["DataObject"], "extension": "TIF"},
                {"name": "tables", "types": ["DataObject"], "extension": "csv"},
            ]
        )
        config = BlockConfig(
            params={
                "output_ports": [
                    {"name": "images", "types": ["DataObject"], "extension": "TIF"},
                    {"name": "tables", "types": ["DataObject"], "extension": "csv"},
                ]
            }
        )

        result = block._bin_outputs_by_extension([f1, f2, f3], config)

        assert set(result.keys()) == {"images", "tables"}
        assert result["images"].length == 2
        assert result["tables"].length == 1

    def test_required_port_with_no_files_raises(self, tmp_path: Path) -> None:
        from scistudio.blocks.base.config import BlockConfig

        f1 = tmp_path / "image.tif"
        f1.write_text("x", encoding="utf-8")

        block = self._make_block_with_ports(
            [
                {"name": "images", "types": ["DataObject"], "extension": "tif"},
                {"name": "labels", "types": ["DataObject"], "extension": "png"},
            ]
        )
        config = BlockConfig(
            params={
                "output_ports": [
                    {"name": "images", "types": ["DataObject"], "extension": "tif"},
                    {"name": "labels", "types": ["DataObject"], "extension": "png"},
                ]
            }
        )

        with pytest.raises(ValueError, match=r"Port 'labels' required, no '\.png' files"):
            block._bin_outputs_by_extension([f1], config)

    def test_unmatched_files_emit_warning_log(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from scistudio.blocks.base.config import BlockConfig

        f1 = tmp_path / "image.tif"
        f2 = tmp_path / "stray.txt"
        f1.write_text("x", encoding="utf-8")
        f2.write_text("y", encoding="utf-8")

        block = self._make_block_with_ports([{"name": "images", "types": ["DataObject"], "extension": "tif"}])
        config = BlockConfig(
            params={
                "output_ports": [
                    {"name": "images", "types": ["DataObject"], "extension": "tif"},
                ]
            }
        )

        with caplog.at_level(logging.WARNING, logger="scistudio.blocks.app.app_block"):
            result = block._bin_outputs_by_extension([f1, f2], config)

        assert result["images"].length == 1
        assert any("Unmatched output file" in record.message for record in caplog.records)

    def test_binner_constructs_typed_artifact_items(self, tmp_path: Path) -> None:
        """#690 audit fix: when an output port declares an ``Artifact`` (or
        subclass) type, the binner must construct items of that class so the
        resulting ``Collection.item_type`` homogeneity check passes.

        Previously the binner unconditionally instantiated ``Artifact``,
        which would be rejected by a Collection whose declared ``item_type``
        was a strict ``Artifact`` subclass.
        """
        from scistudio.blocks.base.config import BlockConfig
        from scistudio.core.types.artifact import Artifact

        f1 = tmp_path / "report.pdf"
        f1.write_text("x", encoding="utf-8")

        block = self._make_block_with_ports([{"name": "reports", "types": ["Artifact"], "extension": "pdf"}])
        config = BlockConfig(
            params={
                "output_ports": [
                    {"name": "reports", "types": ["Artifact"], "extension": "pdf"},
                ]
            }
        )

        result = block._bin_outputs_by_extension([f1], config)
        coll = result["reports"]
        assert coll.length == 1
        assert coll.item_type is Artifact
        assert isinstance(next(iter(coll)), Artifact)

    def test_binner_raises_lookup_error_for_non_constructible_type(self, tmp_path: Path) -> None:
        """#1079: when the declared port type is a non-Artifact concrete type
        and no loader is registered for ``(declared_type, extension)``,
        ``reconstruct_from_file`` raises ``LookupError`` and the binner
        propagates it.

        This replaces the pre-#1079 silent downgrade-to-Artifact behavior.
        The old "declared type ... not constructible from a file path"
        warning is gone — the new contract is: if you declare a concrete
        non-Artifact type, the runtime requires a matching loader.
        """
        from scistudio.blocks.base.config import BlockConfig

        f1 = tmp_path / "image.no_loader_for_array_here_xyz"
        f1.write_text("x", encoding="utf-8")

        # "Array" is registered but not a subclass of Artifact. No loader
        # exists for (Array, .no_loader_for_array_here_xyz), so the binner
        # must raise LookupError rather than silently downgrade.
        block = self._make_block_with_ports(
            [{"name": "imgs", "types": ["Array"], "extension": "no_loader_for_array_here_xyz"}]
        )
        config = BlockConfig(
            params={
                "output_ports": [
                    {"name": "imgs", "types": ["Array"], "extension": "no_loader_for_array_here_xyz"},
                ]
            }
        )

        with pytest.raises(LookupError):
            block._bin_outputs_by_extension([f1], config)

    def test_classvar_optional_port_with_no_files_returns_empty_collection(self) -> None:
        """ClassVar-declared optional ports stay empty without raising.

        Per issue #680, every port declared via the editor is required.
        Optional ports only exist as ClassVar scaffolds on subclasses;
        the binner honours their ``required=False`` flag.
        """
        from typing import ClassVar

        from scistudio.blocks.app.app_block import AppBlock
        from scistudio.blocks.base.config import BlockConfig
        from scistudio.blocks.base.ports import OutputPort

        class _OptionalPortBlock(AppBlock):
            variadic_outputs: ClassVar[bool] = False
            output_ports: ClassVar[list[OutputPort]] = [
                OutputPort(name="optional_csv", accepted_types=[], required=False),
            ]

        block = _OptionalPortBlock()
        # No runtime config['output_ports'] -> falls back to ClassVar.
        result = block._bin_outputs_by_extension([], BlockConfig(params={}))
        # ClassVar port has no extension declared, so it stays empty (not raised).
        assert "optional_csv" in result
        assert result["optional_csv"].length == 0

    def test_run_uses_binner_when_output_ports_in_config(self, tmp_path: Path) -> None:
        """End-to-end run() goes through the binner when ports are declared."""
        from unittest.mock import MagicMock, patch

        from scistudio.blocks.app.app_block import AppBlock
        from scistudio.blocks.base.config import BlockConfig

        block = AppBlock()

        config = BlockConfig(
            params={
                "app_command": "echo hello",
                "output_ports": [
                    {"name": "tables", "types": ["DataObject"], "extension": "csv"},
                ],
            }
        )

        f1 = tmp_path / "result.csv"
        f1.write_text("a,b\n1,2\n", encoding="utf-8")

        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
            patch(
                "scistudio.blocks.app.app_block.tempfile.mkdtemp",
                return_value=str(tmp_path / "ex"),
            ),
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 1
            mock_proc.wait.return_value = 0
            mock_bridge.launch.return_value = mock_proc

            with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
                mock_watcher = MagicMock()
                mock_watcher_cls.return_value = mock_watcher
                mock_watcher.wait_for_output.return_value = [f1]

                result = block.run(inputs={}, config=config)

            # bridge.collect should NOT be called because the binner ran.
            mock_bridge.collect.assert_not_called()

        assert "tables" in result
        assert result["tables"].length == 1


class TestAppBlockVestigialStateRemoval:
    """Regression tests for #1334 / #560 — removal of worker-side Block.state."""

    def test_appblock_run_does_not_crash_on_state_precondition(self, tmp_path: Path) -> None:
        """AppBlock.run() must NOT raise `Invalid state transition: ready -> paused`.

        Before #1334, AppBlock.run() called ``self.transition(BlockState.PAUSED)``
        which required the worker to first move the block READY → RUNNING. The
        worker never did, so AppBlock always crashed on the first call. Fixed
        by removing the vestigial state machine entirely (engine-owned state
        per ADR-018 §8.1 is authoritative).
        """
        from unittest.mock import MagicMock, patch

        from scistudio.blocks.app.app_block import AppBlock
        from scistudio.blocks.base.config import BlockConfig

        block = AppBlock()
        config = BlockConfig(
            params={"app_command": "echo hello", "output_patterns": ["*.csv"]},
        )
        out_file = tmp_path / "out" / "result.csv"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text("x\n1\n", encoding="utf-8")

        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
            patch(
                "scistudio.blocks.app.app_block.tempfile.mkdtemp",
                return_value=str(tmp_path / "exchange"),
            ),
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 1
            mock_proc.wait.return_value = 0
            mock_bridge.launch.return_value = mock_proc
            mock_bridge.collect.return_value = {"result": Artifact(file_path=out_file)}

            with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
                mock_watcher = MagicMock()
                mock_watcher_cls.return_value = mock_watcher
                mock_watcher.wait_for_output.return_value = [out_file]

                # The pre-#1334 bug raised at this call:
                # RuntimeError: Invalid state transition: ready -> paused
                result = block.run(inputs={}, config=config)

        assert "result" in result

    def test_block_base_class_has_no_vestigial_state_machine(self) -> None:
        """Block ABC must not expose ``state`` or ``transition`` (#1334)."""
        from scistudio.blocks.base.block import Block

        assert not hasattr(Block, "state")
        assert not hasattr(Block, "transition")

    def test_appblock_signals_cancellation_via_typed_exception(self, tmp_path: Path) -> None:
        """ProcessExitedWithoutOutputError surfaces as BlockCancelledByAppError."""
        from unittest.mock import MagicMock, patch

        from scistudio.blocks.app.app_block import AppBlock
        from scistudio.blocks.app.watcher import ProcessExitedWithoutOutputError
        from scistudio.blocks.base.config import BlockConfig
        from scistudio.blocks.base.exceptions import BlockCancelledByAppError

        block = AppBlock()
        config = BlockConfig(params={"app_command": "echo hello"})

        with (
            patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
            patch("scistudio.blocks.app.app_block.validate_app_command", return_value=["echo", "hello"]),
            patch(
                "scistudio.blocks.app.app_block.tempfile.mkdtemp",
                return_value=str(tmp_path / "exchange"),
            ),
        ):
            mock_bridge = MagicMock()
            mock_bridge_cls.return_value = mock_bridge
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 1
            mock_proc.wait.return_value = 0
            mock_bridge.launch.return_value = mock_proc

            with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
                mock_watcher = MagicMock()
                mock_watcher_cls.return_value = mock_watcher
                mock_watcher.wait_for_output.side_effect = ProcessExitedWithoutOutputError("gone")

                with pytest.raises(BlockCancelledByAppError, match="gone"):
                    block.run(inputs={}, config=config)
