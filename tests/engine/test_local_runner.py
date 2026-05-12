"""Tests for LocalRunner and subprocess pipeline -- ADR-017."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from scieasy.engine.events import EventBus
from scieasy.engine.runners.local import LocalRunner, _derive_output_dir
from scieasy.engine.runners.process_handle import (
    ProcessExitInfo,
    ProcessHandle,
    ProcessRegistry,
)
from scieasy.engine.runners.worker import reconstruct_inputs, serialise_outputs

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestLocalRunnerConstruction:
    def test_default_construction(self) -> None:
        runner = LocalRunner()
        assert runner._event_bus is None
        assert runner._registry is None

    def test_construction_with_dependencies(self) -> None:
        bus = EventBus()
        registry = ProcessRegistry()
        runner = LocalRunner(event_bus=bus, registry=registry)
        assert runner._event_bus is bus
        assert runner._registry is registry


# ---------------------------------------------------------------------------
# check_status
# ---------------------------------------------------------------------------


class TestLocalRunnerCheckStatus:
    def _make_handle(self, block_id: str, alive: bool = True) -> ProcessHandle:
        mock_ops = MagicMock()
        mock_ops.is_alive.return_value = alive

        handle = ProcessHandle(
            block_id=block_id,
            pid=12345,
            start_time=datetime.now(),
            resource_request=MagicMock(),
        )
        handle._platform_ops = mock_ops
        return handle

    def test_unknown_when_no_registry(self) -> None:
        runner = LocalRunner(event_bus=None, registry=None)
        result = asyncio.run(runner.check_status("any-id"))
        assert result == "unknown"

    def test_unknown_when_handle_not_found(self) -> None:
        registry = ProcessRegistry()
        runner = LocalRunner(event_bus=None, registry=registry)
        result = asyncio.run(runner.check_status("nonexistent"))
        assert result == "unknown"

    def test_running_when_alive(self) -> None:
        registry = ProcessRegistry()
        handle = self._make_handle("block-1", alive=True)
        registry.register(handle)
        runner = LocalRunner(event_bus=None, registry=registry)
        result = asyncio.run(runner.check_status("block-1"))
        assert result == "running"

    def test_completed_when_not_alive(self) -> None:
        registry = ProcessRegistry()
        handle = self._make_handle("block-1", alive=False)
        registry.register(handle)
        runner = LocalRunner(event_bus=None, registry=registry)
        result = asyncio.run(runner.check_status("block-1"))
        assert result == "completed"


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


class TestLocalRunnerCancel:
    def _make_handle(self, block_id: str) -> ProcessHandle:
        mock_ops = MagicMock()
        mock_ops.terminate_tree.return_value = ProcessExitInfo(was_killed_by_framework=True)

        handle = ProcessHandle(
            block_id=block_id,
            pid=12345,
            start_time=datetime.now(),
            resource_request=MagicMock(),
        )
        handle._platform_ops = mock_ops
        return handle

    def test_cancel_without_registry_is_safe(self) -> None:
        runner = LocalRunner(event_bus=None, registry=None)
        asyncio.run(runner.cancel("any-id"))  # Should not raise

    def test_cancel_nonexistent_handle_is_safe(self) -> None:
        registry = ProcessRegistry()
        runner = LocalRunner(event_bus=None, registry=registry)
        asyncio.run(runner.cancel("nonexistent"))  # Should not raise

    def test_cancel_terminates_handle(self) -> None:
        registry = ProcessRegistry()
        handle = self._make_handle("block-1")
        registry.register(handle)
        runner = LocalRunner(event_bus=None, registry=registry)
        asyncio.run(runner.cancel("block-1"))
        assert handle.was_killed_by_framework is True


# ---------------------------------------------------------------------------
# run -- with mocked subprocess
# ---------------------------------------------------------------------------


class TestLocalRunnerRun:
    def _make_async_proc(self, stdout: bytes, stderr: bytes, returncode: int, pid: int = 100) -> AsyncMock:
        """Create a mock async subprocess process."""
        mock_proc = AsyncMock()
        mock_proc.pid = pid
        mock_proc.returncode = returncode
        mock_proc.communicate = AsyncMock(return_value=(stdout, stderr))
        return mock_proc

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_run_returns_parsed_output(self, mock_create_sub: AsyncMock) -> None:
        """run() should return the worker output payload from subprocess stdout."""
        output_data = {"outputs": {"result": "42"}}
        mock_proc = self._make_async_proc(json.dumps(output_data).encode(), b"", 0, pid=100)
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        registry = ProcessRegistry()
        runner = LocalRunner(event_bus=bus, registry=registry)

        class FakeBlock:
            pass

        block = FakeBlock()
        result = asyncio.run(runner.run(block, {"input": "ref1"}, {"param": 1}))

        # After fix #120: envelope is unwrapped -- we get the inner dict.
        assert result == {"result": "42"}
        mock_proc.communicate.assert_called_once()
        # Verify the stdin payload was passed correctly.
        call_kwargs = mock_proc.communicate.call_args
        stdin_payload = call_kwargs.kwargs.get("input") or call_kwargs.args[0] if call_kwargs.args else None
        if stdin_payload is None:
            stdin_payload = call_kwargs[1].get("input", b"")
        payload = json.loads(stdin_payload.decode())
        assert payload["block_class"].endswith("FakeBlock")
        assert payload["inputs"] == {"input": "ref1"}
        assert payload["config"] == {"param": 1}
        assert payload["output_dir"]
        assert Path(payload["output_dir"]).exists()

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_run_raises_on_nonzero_exit(self, mock_create_sub: AsyncMock) -> None:
        """run() should raise when the subprocess exits with a non-zero code."""
        mock_proc = self._make_async_proc(b"", b"traceback here", 1, pid=101)
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        registry = ProcessRegistry()
        runner = LocalRunner(event_bus=bus, registry=registry)

        class FakeBlock:
            pass

        try:
            asyncio.run(runner.run(FakeBlock(), {}, {}))
        except RuntimeError as exc:
            assert "traceback here" in str(exc)
        else:
            raise AssertionError("Expected LocalRunner.run() to raise RuntimeError")

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_run_returns_empty_dict_on_no_stdout(self, mock_create_sub: AsyncMock) -> None:
        """run() should return empty dict when subprocess produces no stdout."""
        mock_proc = self._make_async_proc(b"", b"", 0, pid=102)
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        registry = ProcessRegistry()
        runner = LocalRunner(event_bus=bus, registry=registry)

        class FakeBlock:
            pass

        result = asyncio.run(runner.run(FakeBlock(), {}, {}))
        assert result == {}

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_run_unwraps_output_envelope(self, mock_create_sub: AsyncMock) -> None:
        """run() should unwrap the {"outputs": ...} envelope (#120)."""
        inner = {"port_a": "value_a", "port_b": 123}
        envelope = {"outputs": inner}
        mock_proc = self._make_async_proc(json.dumps(envelope).encode(), b"", 0, pid=200)
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        runner = LocalRunner(event_bus=bus, registry=ProcessRegistry())

        class FakeBlock:
            pass

        result = asyncio.run(runner.run(FakeBlock(), {}, {}))
        assert result == inner

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_run_passes_through_non_envelope_json(self, mock_create_sub: AsyncMock) -> None:
        """run() should return raw dict when no 'outputs' key is present."""
        raw = {"error": "something broke"}
        mock_proc = self._make_async_proc(json.dumps(raw).encode(), b"", 0, pid=201)
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        runner = LocalRunner(event_bus=bus, registry=ProcessRegistry())

        class FakeBlock:
            pass

        result = asyncio.run(runner.run(FakeBlock(), {}, {}))
        assert result == raw

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_run_raises_terminal_state_for_cancelled(self, mock_create_sub: AsyncMock) -> None:
        """#681: run() should raise BlockTerminalStateReportedError(CANCELLED)
        when the worker envelope contains ``final_state: "cancelled"``.
        """
        from scieasy.blocks.base.state import BlockState
        from scieasy.engine.runners.terminal_state import BlockTerminalStateReportedError

        envelope = {
            "outputs": {},
            "environment": {},
            "final_state": "cancelled",
        }
        mock_proc = self._make_async_proc(json.dumps(envelope).encode(), b"", 0, pid=300)
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        runner = LocalRunner(event_bus=bus, registry=ProcessRegistry())

        class FakeBlock:
            pass

        try:
            asyncio.run(runner.run(FakeBlock(), {}, {}))
        except BlockTerminalStateReportedError as exc:
            assert exc.state == BlockState.CANCELLED
            assert exc.outputs == {}
        else:
            raise AssertionError("Expected BlockTerminalStateReportedError to be raised")

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_run_raises_terminal_state_for_error(self, mock_create_sub: AsyncMock) -> None:
        """#681: ``final_state: "error"`` raises BlockTerminalStateReportedError(ERROR)."""
        from scieasy.blocks.base.state import BlockState
        from scieasy.engine.runners.terminal_state import BlockTerminalStateReportedError

        envelope = {
            "outputs": {"partial": "value"},
            "environment": {},
            "final_state": "error",
        }
        mock_proc = self._make_async_proc(json.dumps(envelope).encode(), b"", 0, pid=301)
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        runner = LocalRunner(event_bus=bus, registry=ProcessRegistry())

        class FakeBlock:
            pass

        try:
            asyncio.run(runner.run(FakeBlock(), {}, {}))
        except BlockTerminalStateReportedError as exc:
            assert exc.state == BlockState.ERROR
            assert exc.outputs == {"partial": "value"}
        else:
            raise AssertionError("Expected BlockTerminalStateReportedError to be raised")

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_run_ignores_done_final_state(self, mock_create_sub: AsyncMock) -> None:
        """#681: ``final_state: "done"`` (non-terminal-failure) is treated as a
        normal return — the runner does not raise. The worker only emits
        ``final_state`` for non-DONE terminal states, but defensively the
        runner must not raise on values like ``"done"`` or unknown values.
        """
        envelope = {
            "outputs": {"port_a": "value"},
            "environment": {},
            "final_state": "done",
        }
        mock_proc = self._make_async_proc(json.dumps(envelope).encode(), b"", 0, pid=302)
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        runner = LocalRunner(event_bus=bus, registry=ProcessRegistry())

        class FakeBlock:
            pass

        result = asyncio.run(runner.run(FakeBlock(), {}, {}))
        assert result == {"port_a": "value"}

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_run_returns_outputs_when_final_state_absent(self, mock_create_sub: AsyncMock) -> None:
        """#681 backward compat: envelope without ``final_state`` returns outputs."""
        envelope = {
            "outputs": {"port_a": "value"},
            "environment": {},
        }
        mock_proc = self._make_async_proc(json.dumps(envelope).encode(), b"", 0, pid=303)
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        runner = LocalRunner(event_bus=bus, registry=ProcessRegistry())

        class FakeBlock:
            pass

        result = asyncio.run(runner.run(FakeBlock(), {}, {}))
        assert result == {"port_a": "value"}


class TestLocalRunnerOutputDir:
    def test_derive_output_dir_prefers_project_scoped_path(self, tmp_path: Path) -> None:
        class FakeBlock:
            id = "block-123"

        output_dir = _derive_output_dir(
            FakeBlock(),
            {
                "project_dir": str(tmp_path),
                "workflow_id": "wf-1",
            },
        )

        assert output_dir == str(tmp_path / "data" / "zarr" / "wf-1" / "block-123")
        assert Path(output_dir).exists()

    def test_derive_output_dir_falls_back_to_tempdir(self) -> None:
        class FakeBlock:
            id = "block-temp"

        output_dir = _derive_output_dir(FakeBlock(), {})

        assert output_dir.startswith(tempfile.gettempdir())
        assert Path(output_dir).exists()


# ---------------------------------------------------------------------------
# reconstruct_inputs -- TypeSignature recovery (#132, updated T-014)
# ---------------------------------------------------------------------------


class TestReconstructInputsTypeChain:
    def test_uses_type_chain_from_metadata(self) -> None:
        """ADR-027 Addendum 1 §1 (T-014): reconstruct_inputs recovers type_chain
        from metadata and returns a typed DataObject instance.
        """
        from scieasy.core.types.array import Array

        payload = {
            "inputs": {
                "image": {
                    "backend": "zarr",
                    "path": "/data/img.zarr",
                    "format": "zarr",
                    "metadata": {
                        "type_chain": ["DataObject", "Array"],
                        "axes": ["z", "y", "x"],
                        "shape": [8, 16, 16],
                        "dtype": "uint8",
                    },
                }
            }
        }
        result = reconstruct_inputs(payload)
        obj = result["image"]
        assert isinstance(obj, Array)
        assert obj.dtype_info.type_chain == ["DataObject", "Array"]

    def test_falls_back_to_dataobject_without_metadata(self) -> None:
        """Reconstruct_inputs defaults to bare ``DataObject`` when no type_chain."""
        from scieasy.core.types.base import DataObject

        payload = {
            "inputs": {
                "data": {
                    "backend": "zarr",
                    "path": "/data/obj.zarr",
                    "format": "zarr",
                }
            }
        }
        result = reconstruct_inputs(payload)
        obj = result["data"]
        assert isinstance(obj, DataObject)
        assert obj.dtype_info.type_chain == ["DataObject"]

    def test_scalar_passthrough(self) -> None:
        """Scalar values should pass through unchanged."""
        payload = {"inputs": {"threshold": 0.5, "name": "test"}}
        result = reconstruct_inputs(payload)
        assert result == {"threshold": 0.5, "name": "test"}


# ---------------------------------------------------------------------------
# serialise_outputs -- type_chain inclusion (#132, updated T-014)
# ---------------------------------------------------------------------------


class TestSerialiseOutputsTypeChain:
    def test_includes_type_chain_in_metadata(self) -> None:
        """serialise_outputs includes type_chain in the wire-format metadata
        sidecar (ADR-027 Addendum 1 §1, builds on #132).
        """
        from scieasy.core.storage.ref import StorageReference
        from scieasy.core.types.base import DataObject

        obj = DataObject(storage_ref=StorageReference(backend="zarr", path="/out/result.zarr", format="zarr"))

        result = serialise_outputs({"output": obj}, "/tmp/out")
        assert "type_chain" in result["output"]["metadata"]
        assert "DataObject" in result["output"]["metadata"]["type_chain"]


# ---------------------------------------------------------------------------
# spawn_block_process -- async emit scheduling (#122)
# ---------------------------------------------------------------------------


class TestSpawnEmitScheduling:
    @patch("scieasy.engine.runners.process_handle.subprocess.Popen")
    def test_emit_scheduled_on_running_loop(self, mock_popen_cls: MagicMock) -> None:
        """emit() should be scheduled via create_task when event loop exists (#122)."""
        from scieasy.engine.runners.process_handle import spawn_block_process

        mock_proc = MagicMock()
        mock_proc.pid = 300
        mock_proc.stdin = MagicMock()
        mock_popen_cls.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        registry = ProcessRegistry()

        async def _run() -> None:
            spawn_block_process(
                block_class="some.module.Block",
                inputs_refs={},
                config={},
                event_bus=bus,
                registry=registry,
            )
            # Let the scheduled task run
            await asyncio.sleep(0)

        asyncio.run(_run())
        bus.emit.assert_called_once()

    @patch("scieasy.engine.runners.process_handle.subprocess.Popen")
    def test_emit_skipped_without_event_loop(self, mock_popen_cls: MagicMock) -> None:
        """spawn_block_process should not raise when no event loop exists (#122)."""
        from scieasy.engine.runners.process_handle import spawn_block_process

        mock_proc = MagicMock()
        mock_proc.pid = 301
        mock_proc.stdin = MagicMock()
        mock_popen_cls.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        registry = ProcessRegistry()

        # Call outside any async context -- should not raise.
        spawn_block_process(
            block_class="some.module.Block",
            inputs_refs={},
            config={},
            event_bus=bus,
            registry=registry,
        )
        # emit should NOT have been called (no loop to schedule on).
        bus.emit.assert_not_called()


# ---------------------------------------------------------------------------
# run — async non-blocking behaviour (#162)
# ---------------------------------------------------------------------------


class TestLocalRunnerAsyncBehavior:
    """Verify LocalRunner.run() does not block the event loop (#162)."""

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_event_loop_responsive_during_run(self, mock_create_sub: AsyncMock) -> None:
        """A concurrent coroutine should complete while run() is in progress."""
        output_data = {"outputs": {"result": "ok"}}
        mock_proc = AsyncMock()
        mock_proc.pid = 400
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(json.dumps(output_data).encode(), b""))
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        runner = LocalRunner(event_bus=bus, registry=ProcessRegistry())

        class FakeBlock:
            pass

        concurrent_ran = False

        async def _test() -> None:
            nonlocal concurrent_ran

            async def concurrent_task() -> None:
                nonlocal concurrent_ran
                await asyncio.sleep(0)
                concurrent_ran = True

            task = asyncio.create_task(concurrent_task())
            result = await runner.run(FakeBlock(), {}, {})
            await task
            assert result == {"result": "ok"}

        asyncio.run(_test())
        assert concurrent_ran, "Concurrent coroutine should have completed during run()"

    @patch("scieasy.engine.runners.local.asyncio.create_subprocess_exec")
    def test_run_uses_block_id_attribute(self, mock_create_sub: AsyncMock) -> None:
        """run() should read block.id and use it as the ProcessHandle identifier (#163).

        PR #160 approach: DAGScheduler._instantiate_block() sets block.id = node_id,
        and LocalRunner.run() reads it via getattr(block, "id", ...).
        """
        mock_proc = AsyncMock()
        mock_proc.pid = 401
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b'{"outputs": {}}', b""))
        mock_create_sub.return_value = mock_proc

        bus = MagicMock()
        bus.emit = AsyncMock()
        registry = ProcessRegistry()
        runner = LocalRunner(event_bus=bus, registry=registry)

        class FakeBlock:
            pass

        block = FakeBlock()
        block.id = "node_A"  # type: ignore[attr-defined]
        asyncio.run(runner.run(block, {}, {}))

        # The ProcessHandle should be registered with the block.id value,
        # not the class path.
        handle = registry.get_handle("node_A")
        assert handle is not None
        assert handle.block_id == "node_A"
