"""Tests for ProcessHandle, ProcessRegistry, spawn_block_process — ADR-019."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scistudio.engine.resources import ResourceRequest
from scistudio.engine.runners.platform import (
    PlatformOps,
    PosixOps,
    WindowsOps,
    get_platform_ops,
)
from scistudio.engine.runners.process_handle import (
    ProcessExitInfo,
    ProcessHandle,
    ProcessRegistry,
    spawn_block_process,
)

# ---------------------------------------------------------------------------
# ProcessExitInfo
# ---------------------------------------------------------------------------


class TestProcessExitInfo:
    def test_defaults(self) -> None:
        info = ProcessExitInfo()
        assert info.exit_code is None
        assert info.signal_number is None
        assert info.was_killed_by_framework is False
        assert info.platform_detail == ""

    def test_custom_fields(self) -> None:
        info = ProcessExitInfo(
            exit_code=1,
            signal_number=9,
            was_killed_by_framework=True,
            platform_detail="killed by SIGKILL",
        )
        assert info.exit_code == 1
        assert info.signal_number == 9
        assert info.was_killed_by_framework is True
        assert info.platform_detail == "killed by SIGKILL"


# ---------------------------------------------------------------------------
# PlatformOps protocol conformance
# ---------------------------------------------------------------------------


class TestPlatformOps:
    def test_posix_ops_conforms_to_protocol(self) -> None:
        assert isinstance(PosixOps(), PlatformOps)

    def test_windows_ops_conforms_to_protocol(self) -> None:
        assert isinstance(WindowsOps(), PlatformOps)

    def test_get_platform_ops_returns_correct_type(self) -> None:
        ops = get_platform_ops()
        if sys.platform == "win32":
            assert isinstance(ops, WindowsOps)
        else:
            assert isinstance(ops, PosixOps)


# ---------------------------------------------------------------------------
# PlatformOps.create_process_group
# ---------------------------------------------------------------------------


class TestCreateProcessGroup:
    def test_posix_sets_start_new_session(self) -> None:
        ops = PosixOps()
        result = ops.create_process_group({})
        assert result["start_new_session"] is True

    def test_posix_preserves_existing_kwargs(self) -> None:
        ops = PosixOps()
        result = ops.create_process_group({"stdin": subprocess.PIPE})
        assert result["stdin"] == subprocess.PIPE
        assert result["start_new_session"] is True

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_windows_sets_creation_flags(self) -> None:
        ops = WindowsOps()
        result = ops.create_process_group({})
        assert result["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_windows_preserves_existing_creationflags(self) -> None:
        ops = WindowsOps()
        result = ops.create_process_group({"creationflags": 0x00000010})
        # Should have both the original flag and CREATE_NEW_PROCESS_GROUP
        assert result["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
        assert result["creationflags"] & 0x00000010


# ---------------------------------------------------------------------------
# PlatformOps.is_alive
# ---------------------------------------------------------------------------


class TestIsAlive:
    def test_current_process_is_alive(self) -> None:
        """Current process pid should always be alive."""
        ops = get_platform_ops()
        import os

        assert ops.is_alive(os.getpid()) is True

    def test_nonexistent_pid_is_not_alive(self) -> None:
        """A very large PID should not exist."""
        ops = get_platform_ops()
        # Use a PID that almost certainly doesn't exist
        assert ops.is_alive(2**30) is False


# ---------------------------------------------------------------------------
# ProcessHandle
# ---------------------------------------------------------------------------


class TestProcessHandle:
    def test_construction(self) -> None:
        rr = ResourceRequest()
        now = datetime.now()
        handle = ProcessHandle(
            block_id="block-1",
            pid=12345,
            start_time=now,
            resource_request=rr,
        )
        assert handle.block_id == "block-1"
        assert handle.pid == 12345
        assert handle.start_time == now
        assert handle.resource_request is rr
        assert handle.was_killed_by_framework is False
        assert handle._popen is None

    def test_is_alive_delegates_to_platform_ops(self) -> None:
        mock_ops = MagicMock(spec=PlatformOps)
        mock_ops.is_alive.return_value = True

        handle = ProcessHandle(
            block_id="block-1",
            pid=99999,
            start_time=datetime.now(),
            resource_request=ResourceRequest(),
        )
        handle._platform_ops = mock_ops

        assert handle.is_alive() is True
        mock_ops.is_alive.assert_called_once_with(99999)

    def test_exit_info_delegates_to_platform_ops(self) -> None:
        expected = ProcessExitInfo(exit_code=0, platform_detail="exited normally")
        mock_ops = MagicMock(spec=PlatformOps)
        mock_ops.get_exit_info.return_value = expected

        handle = ProcessHandle(
            block_id="block-1",
            pid=99999,
            start_time=datetime.now(),
            resource_request=ResourceRequest(),
        )
        handle._platform_ops = mock_ops

        info = handle.exit_info()
        assert info is expected
        mock_ops.get_exit_info.assert_called_once_with(99999)

    def test_terminate_delegates_and_sets_flag(self) -> None:
        exit_info = ProcessExitInfo(platform_detail="terminated")
        mock_ops = MagicMock(spec=PlatformOps)
        mock_ops.terminate_tree.return_value = exit_info

        handle = ProcessHandle(
            block_id="block-1",
            pid=99999,
            start_time=datetime.now(),
            resource_request=ResourceRequest(),
        )
        handle._platform_ops = mock_ops

        result = handle.terminate(grace_period_sec=3.0)
        assert result.was_killed_by_framework is True
        assert handle.was_killed_by_framework is True
        mock_ops.terminate_tree.assert_called_once_with(99999, 3.0)

    def test_kill_delegates_and_sets_flag(self) -> None:
        exit_info = ProcessExitInfo(platform_detail="killed")
        mock_ops = MagicMock(spec=PlatformOps)
        mock_ops.kill_tree.return_value = exit_info

        handle = ProcessHandle(
            block_id="block-1",
            pid=99999,
            start_time=datetime.now(),
            resource_request=ResourceRequest(),
        )
        handle._platform_ops = mock_ops

        result = handle.kill()
        assert result.was_killed_by_framework is True
        assert handle.was_killed_by_framework is True
        mock_ops.kill_tree.assert_called_once_with(99999)


# ---------------------------------------------------------------------------
# ProcessRegistry
# ---------------------------------------------------------------------------


class TestProcessRegistry:
    def _make_handle(self, block_id: str, pid: int = 1234) -> ProcessHandle:
        return ProcessHandle(
            block_id=block_id,
            pid=pid,
            start_time=datetime.now(),
            resource_request=ResourceRequest(),
        )

    def test_register_and_get_handle(self) -> None:
        registry = ProcessRegistry()
        handle = self._make_handle("block-A")
        registry.register(handle)
        assert registry.get_handle("block-A") is handle

    def test_get_handle_missing_returns_none(self) -> None:
        registry = ProcessRegistry()
        assert registry.get_handle("nonexistent") is None

    def test_deregister(self) -> None:
        registry = ProcessRegistry()
        handle = self._make_handle("block-A")
        registry.register(handle)
        registry.deregister("block-A")
        assert registry.get_handle("block-A") is None

    def test_deregister_nonexistent_is_safe(self) -> None:
        registry = ProcessRegistry()
        registry.deregister("nonexistent")  # Should not raise

    def test_active_handles(self) -> None:
        registry = ProcessRegistry()
        h1 = self._make_handle("block-1", pid=100)
        h2 = self._make_handle("block-2", pid=200)
        registry.register(h1)
        registry.register(h2)
        handles = registry.active_handles()
        assert len(handles) == 2
        assert h1 in handles
        assert h2 in handles

    def test_active_handles_empty(self) -> None:
        registry = ProcessRegistry()
        assert registry.active_handles() == []

    def test_register_replaces_existing(self) -> None:
        registry = ProcessRegistry()
        h1 = self._make_handle("block-A", pid=100)
        h2 = self._make_handle("block-A", pid=200)
        registry.register(h1)
        registry.register(h2)
        assert registry.get_handle("block-A") is h2
        assert len(registry.active_handles()) == 1

    def test_terminate_all(self) -> None:
        registry = ProcessRegistry()
        mock_ops = MagicMock(spec=PlatformOps)
        mock_ops.terminate_tree.return_value = ProcessExitInfo(was_killed_by_framework=True)

        h1 = self._make_handle("block-1", pid=100)
        h1._platform_ops = mock_ops
        h2 = self._make_handle("block-2", pid=200)
        h2._platform_ops = mock_ops

        registry.register(h1)
        registry.register(h2)
        registry.terminate_all(grace_period_sec=2.0)

        assert mock_ops.terminate_tree.call_count == 2

    def test_terminate_all_continues_on_error(self) -> None:
        """One handle failing to terminate should not prevent others."""
        registry = ProcessRegistry()

        mock_ops_ok = MagicMock(spec=PlatformOps)
        mock_ops_ok.terminate_tree.return_value = ProcessExitInfo(was_killed_by_framework=True)

        mock_ops_fail = MagicMock(spec=PlatformOps)
        mock_ops_fail.terminate_tree.side_effect = OSError("permission denied")

        h1 = self._make_handle("block-1", pid=100)
        h1._platform_ops = mock_ops_fail
        h2 = self._make_handle("block-2", pid=200)
        h2._platform_ops = mock_ops_ok

        registry.register(h1)
        registry.register(h2)

        # Should not raise despite h1 failing
        registry.terminate_all(grace_period_sec=2.0)
        mock_ops_ok.terminate_tree.assert_called_once()


# ---------------------------------------------------------------------------
# spawn_block_process
# ---------------------------------------------------------------------------


class TestSpawnBlockProcess:
    @patch("scistudio.engine.runners.process_handle.subprocess.Popen")
    def test_spawns_subprocess_and_registers(self, mock_popen_cls: MagicMock) -> None:
        """spawn_block_process should create a subprocess, register it, and emit event."""
        # Setup mock Popen
        mock_proc = MagicMock()
        mock_proc.pid = 42
        mock_popen_cls.return_value = mock_proc

        # Setup mock EventBus with AsyncMock emit (emit() is async)
        mock_bus = MagicMock()
        mock_bus.emit = AsyncMock()

        registry = ProcessRegistry()

        # Run inside async context so emit() can be scheduled via create_task
        async def _run() -> ProcessHandle:
            h = spawn_block_process(
                block_class="mymodule.MyBlock",
                inputs_refs={"in1": "ref1"},
                config={"param": 1},
                event_bus=mock_bus,
                registry=registry,
                resource_request=ResourceRequest(cpu_cores=2),
            )
            await asyncio.sleep(0)  # Let create_task run
            return h

        handle = asyncio.run(_run())

        # Verify subprocess was created
        mock_popen_cls.assert_called_once()
        call_args = mock_popen_cls.call_args
        assert call_args[0][0] == [
            sys.executable,
            "-m",
            "scistudio.engine.runners.worker",
        ]

        # Verify handle is correct
        assert handle.block_id == "mymodule.MyBlock"
        assert handle.pid == 42
        assert handle.resource_request.cpu_cores == 2
        assert handle._popen is mock_proc
        assert handle._stdin_payload is not None

        # Verify payload is cached for LocalRunner.communicate(input=...)
        payload = handle._stdin_payload.decode("utf-8")
        assert '"block_class": "mymodule.MyBlock"' in payload

        # Verify registration
        assert registry.get_handle("mymodule.MyBlock") is handle

        # Verify event was emitted
        mock_bus.emit.assert_called_once()
        event = mock_bus.emit.call_args[0][0]
        assert event.event_type == "process_spawned"
        assert event.block_id == "mymodule.MyBlock"
        assert event.data == {"pid": 42}

    @patch("scistudio.engine.runners.process_handle.subprocess.Popen")
    def test_spawn_uses_class_object(self, mock_popen_cls: MagicMock) -> None:
        """When block_class is a class, it should resolve the dotted path."""
        mock_proc = MagicMock()
        mock_proc.pid = 99
        mock_popen_cls.return_value = mock_proc

        mock_bus = MagicMock()
        registry = ProcessRegistry()

        class FakeBlock:
            pass

        handle = spawn_block_process(
            block_class=FakeBlock,
            inputs_refs={},
            config={},
            event_bus=mock_bus,
            registry=registry,
        )

        # block_id should be the fully qualified class path
        assert "FakeBlock" in handle.block_id

    @patch("scistudio.engine.runners.process_handle.subprocess.Popen")
    def test_spawn_default_resource_request(self, mock_popen_cls: MagicMock) -> None:
        """When no resource_request given, should default to ResourceRequest()."""
        mock_proc = MagicMock()
        mock_proc.pid = 55
        mock_proc.stdin = MagicMock()
        mock_popen_cls.return_value = mock_proc

        mock_bus = MagicMock()
        registry = ProcessRegistry()

        handle = spawn_block_process(
            block_class="mod.Block",
            inputs_refs={},
            config={},
            event_bus=mock_bus,
            registry=registry,
        )

        assert handle.resource_request.cpu_cores == 1
        assert handle.resource_request.requires_gpu is False

    @patch("scistudio.engine.runners.process_handle.subprocess.Popen")
    def test_spawn_sets_platform_process_group(self, mock_popen_cls: MagicMock) -> None:
        """Popen should be called with platform-specific process group kwargs."""
        mock_proc = MagicMock()
        mock_proc.pid = 77
        mock_proc.stdin = MagicMock()
        mock_popen_cls.return_value = mock_proc

        mock_bus = MagicMock()
        registry = ProcessRegistry()

        spawn_block_process(
            block_class="mod.Block",
            inputs_refs={},
            config={},
            event_bus=mock_bus,
            registry=registry,
        )

        call_kwargs = mock_popen_cls.call_args[1]
        if sys.platform == "win32":
            assert call_kwargs.get("creationflags", 0) & subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            assert call_kwargs.get("start_new_session") is True

    @patch("scistudio.engine.runners.process_handle.subprocess.Popen")
    def test_spawn_with_job_handle_calls_assign(self, mock_popen_cls: MagicMock) -> None:
        """When job_handle is provided, assign_to_job should be called."""
        mock_proc = MagicMock()
        mock_proc.pid = 88
        mock_proc.stdin = MagicMock()
        mock_popen_cls.return_value = mock_proc

        mock_bus = MagicMock()
        registry = ProcessRegistry()

        sentinel_job = object()  # Fake job handle

        with patch("scistudio.engine.runners.process_handle.get_platform_ops") as mock_get_ops:
            mock_ops = MagicMock()
            mock_ops.create_process_group.side_effect = lambda kw: kw
            mock_get_ops.return_value = mock_ops

            spawn_block_process(
                block_class="mod.Block",
                inputs_refs={},
                config={},
                event_bus=mock_bus,
                registry=registry,
                job_handle=sentinel_job,
            )

            mock_ops.assign_to_job.assert_called_once_with(sentinel_job, 88)


# ---------------------------------------------------------------------------
# Job Object (PlatformOps.create_job_object / assign_to_job)
# ---------------------------------------------------------------------------


class TestJobObject:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_create_job_object_returns_handle(self) -> None:
        ops = WindowsOps()
        job = ops.create_job_object()
        assert job is not None

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
    def test_assign_to_job_with_none_handle_returns_false(self) -> None:
        ops = WindowsOps()
        assert ops.assign_to_job(None, 0) is False

    def test_posix_create_job_object_is_noop(self) -> None:
        ops = PosixOps()
        assert ops.create_job_object() is None

    def test_posix_assign_to_job_is_noop(self) -> None:
        ops = PosixOps()
        assert ops.assign_to_job(None, 0) is False
