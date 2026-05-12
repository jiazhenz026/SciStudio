"""LocalRunner -- subprocess execution on the local machine.

ADR-017: All block execution in isolated subprocesses. No in-process execution.
Uses async subprocess to avoid os.fork() deadlock on macOS (#483).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scieasy.engine.runners.process_handle import ProcessRegistry

logger = logging.getLogger(__name__)


def _win_junction(target: str) -> str:
    """Create an NTFS junction from a short path to *target* (Windows only).

    Data physically lives at *target* (inside the project directory) so
    it survives restarts, syncs with cloud storage, and preserves lineage.
    The junction is just a short alias that keeps the total path under
    Windows MAX_PATH (260) for zarr's internal pathlib operations.

    Junction root: ``%LOCALAPPDATA%/scieasy-stores/`` (override via
    ``SCIEASY_STORE`` env var).  No admin privileges required.
    """
    import hashlib
    import os
    import subprocess as sp

    store_root_env = os.environ.get("SCIEASY_STORE", "")
    if store_root_env:
        store_root = Path(store_root_env)
    else:
        local_app = os.environ.get("LOCALAPPDATA", "")
        store_root = Path(local_app) / "scieasy-stores" if local_app else Path("C:/scieasy-stores")

    hash_id = hashlib.sha256(target.encode()).hexdigest()[:8]
    junction = store_root / hash_id

    if junction.exists():
        return str(junction)

    Path(target).mkdir(parents=True, exist_ok=True)
    junction.parent.mkdir(parents=True, exist_ok=True)

    try:
        sp.run(
            ["cmd", "/c", "mklink", "/J", str(junction), target],
            check=True,
            capture_output=True,
        )
    except (sp.CalledProcessError, FileNotFoundError) as exc:
        logger.warning("Failed to create junction %s -> %s: %s", junction, target, exc)
        # Fallback: use the short path as a real directory instead of a
        # junction.  This avoids MAX_PATH failures when the target lives
        # on a virtual filesystem (e.g. Box) that rejects junctions.
        # Data will be written to the short path; it will NOT sync with
        # cloud storage, but zarr operations will succeed.
        junction.mkdir(parents=True, exist_ok=True)
        logger.info("Fallback: using short path %s as real directory", junction)
        return str(junction)

    logger.info("Created junction %s -> %s", junction, target)
    return str(junction)


def _derive_output_dir(block: Any, config: dict[str, Any]) -> str:
    """Return a persistence directory for worker auto-flush outputs."""
    explicit_output_dir = config.get("output_dir")
    if isinstance(explicit_output_dir, str) and explicit_output_dir:
        path = Path(explicit_output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    project_dir = config.get("project_dir")
    block_id = str(config.get("block_id") or getattr(block, "id", "block"))
    workflow_id = str(config.get("workflow_id") or "adhoc")
    if isinstance(project_dir, str) and project_dir:
        short_block_id = block_id[:40] if len(block_id) > 40 else block_id
        candidate = str(Path(project_dir) / "data" / "zarr" / workflow_id / short_block_id)
        # zarr creates internal subfiles adding ~60 chars. If total would
        # exceed Windows MAX_PATH (260), create an NTFS junction from a
        # short path to the real project directory.
        if sys.platform == "win32" and len(candidate) > 180:
            return _win_junction(candidate)
        Path(candidate).mkdir(parents=True, exist_ok=True)
        return candidate

    return tempfile.mkdtemp(prefix="scieasy-worker-")


class LocalRunner:
    """Execute blocks as local subprocesses.

    Implements the BlockRunner protocol (engine/runners/base.py).

    Methods:
        async run(block, inputs, config) -> dict[str, Any]
            - Calls spawn_block_process() to create isolated subprocess.
            - Waits for subprocess to complete.
            - Returns parsed JSON output from subprocess stdout.

        async check_status(run_id) -> str
            - Queries ProcessHandle.is_alive() for the given run_id.
            - Returns "running" if alive, "completed" otherwise.

        async cancel(run_id) -> None
            - Calls ProcessHandle.terminate() for the given run_id.
    """

    def __init__(self, event_bus: Any | None = None, registry: ProcessRegistry | None = None) -> None:
        self._event_bus = event_bus
        self._registry = registry

    async def run(
        self,
        block: Any,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute *block* in an isolated subprocess.

        Uses ``asyncio.create_subprocess_exec`` to avoid ``os.fork()``
        deadlock on macOS when native extensions have been imported (#483).

        Parameters
        ----------
        block:
            The block instance to run. Its class path is resolved for
            serialization to the worker subprocess.
        inputs:
            Mapping of port names to input data references.
        config:
            Execution-time configuration for this invocation.

        Returns
        -------
        dict[str, Any]
            Parsed JSON result from the subprocess worker.
        """
        from scieasy.engine.runners.process_handle import (
            ProcessRegistry,
            build_worker_payload,
            register_async_process,
        )

        block_class_path = f"{block.__class__.__module__}.{block.__class__.__qualname__}"
        registry = self._registry if self._registry is not None else ProcessRegistry()
        block_id = getattr(block, "id", block_class_path)
        output_dir = _derive_output_dir(block, config)

        # Build the serialized payload for the worker subprocess.
        payload_bytes = build_worker_payload(
            block_class=block_class_path,
            inputs_refs=inputs,
            config=config,
            output_dir=output_dir,
        )

        # Launch via asyncio.create_subprocess_exec to avoid os.fork()
        # deadlock on macOS after importing native extensions (#483).
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "scieasy.engine.runners.worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        # Register the process in the ProcessRegistry for lifecycle tracking.
        register_async_process(
            pid=proc.pid,
            block_id=block_id,
            registry=registry,
            event_bus=self._event_bus,
        )

        stdout, stderr = await proc.communicate(input=payload_bytes)

        # Forward worker stderr so block-level diagnostics are visible.
        if stderr:
            for line in stderr.decode(errors="replace").splitlines():
                if line.strip():
                    logger.info("worker[%s] %s", block_id, line)

        if proc.returncode != 0:
            error_msg = stderr.decode(errors="replace") if stderr else "unknown error"
            logger.error(
                "Block subprocess %s exited with code %d: %s",
                block_class_path,
                proc.returncode,
                error_msg,
            )
            # Try to parse stdout for structured error from worker
            if stdout:
                try:
                    payload = dict(json.loads(stdout.decode()))
                    if "error" in payload:
                        raise RuntimeError(str(payload["error"]))
                    outputs = payload.get("outputs", payload)
                    if not isinstance(outputs, dict):
                        raise RuntimeError("Worker returned a non-dict output payload.")
                    return outputs
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            raise RuntimeError(error_msg)

        if stdout:
            try:
                parsed = json.loads(stdout.decode())
                # Worker wraps outputs as {"outputs": {...}, "environment": {...},
                # "final_state": "<state>"?}. Unwrap the envelope so callers see
                # port names at the top level.
                if isinstance(parsed, dict) and "outputs" in parsed:
                    outputs_dict = dict(parsed["outputs"])
                    # #681: when the worker reports a non-DONE terminal state
                    # (block called ``self.transition()`` from inside ``run()``),
                    # raise the typed exception so the scheduler's existing
                    # exception path can finalise the block to that state.
                    final_state_raw = parsed.get("final_state")
                    if isinstance(final_state_raw, str):
                        from scieasy.blocks.base.state import BlockState
                        from scieasy.engine.runners.terminal_state import (
                            BlockTerminalStateReportedError,
                        )

                        try:
                            reported = BlockState(final_state_raw)
                        except ValueError:
                            logger.warning(
                                "Worker reported unknown final_state %r for block %s",
                                final_state_raw,
                                block_id,
                            )
                        else:
                            if reported in (
                                BlockState.CANCELLED,
                                BlockState.ERROR,
                                BlockState.SKIPPED,
                            ):
                                raise BlockTerminalStateReportedError(
                                    state=reported,
                                    outputs=outputs_dict,
                                )
                    return outputs_dict
                return dict(parsed)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RuntimeError(f"Failed to parse worker output: {exc}") from exc

        return {}

    async def check_status(self, run_id: str) -> str:
        """Query the current status of a previously started run.

        Parameters
        ----------
        run_id:
            Block ID / opaque identifier returned when the run was initiated.

        Returns
        -------
        str
            "running", "completed", or "unknown".
        """
        if self._registry is None:
            return "unknown"
        handle = self._registry.get_handle(run_id)
        if handle is None:
            return "unknown"
        alive = handle.is_alive()
        return "running" if alive else "completed"

    async def cancel(self, run_id: str) -> None:
        """Request cancellation of a running execution.

        Parameters
        ----------
        run_id:
            Block ID / opaque identifier of the run to cancel.
        """
        if self._registry is None:
            return
        handle = self._registry.get_handle(run_id)
        if handle is not None:
            handle.terminate()
