"""LocalRunner -- subprocess execution on the local machine.

ADR-017: All block execution in isolated subprocesses. No in-process execution.
Uses async subprocess to avoid os.fork() deadlock on macOS (#483).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.engine.runners.process_handle import ProcessRegistry

logger = logging.getLogger(__name__)


class BlockStorageReferenceError(RuntimeError):
    """Raised when a worker reports a structured storage-reference failure."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.error_kind = str(payload.get("error_kind") or "storage_reference_invalid")
        self.ref = payload.get("ref") if isinstance(payload.get("ref"), dict) else {}
        super().__init__(_format_storage_error_message(payload))


def _format_storage_error_message(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, str) and message:
        return message
    raw_ref = payload.get("ref")
    ref: dict[Any, Any] = raw_ref if isinstance(raw_ref, dict) else {}
    backend = ref.get("backend") or "unknown-backend"
    path = ref.get("path") or "unknown-path"
    return f"Storage reference points to unavailable data: {backend}:{path}."


def _raise_for_worker_error_payload(payload: dict[str, Any]) -> None:
    error_kind = payload.get("error_kind")
    if error_kind in {"storage_missing", "storage_reference_invalid"}:
        raise BlockStorageReferenceError(payload)
    if "error" in payload:
        raise RuntimeError(str(payload["error"]))


def _win_junction(target: str) -> str:
    """Create an NTFS junction from a short path to *target* (Windows only).

    Data physically lives at *target* (inside the project directory) so
    it survives restarts, syncs with cloud storage, and preserves lineage.
    The junction is just a short alias that keeps the total path under
    Windows MAX_PATH (260) for zarr's internal pathlib operations.

    Junction root: ``%LOCALAPPDATA%/scistudio-stores/`` (override via
    ``SCISTUDIO_STORE`` env var).  No admin privileges required.
    """
    import hashlib
    import os
    import subprocess as sp

    store_root_env = os.environ.get("SCISTUDIO_STORE", "")
    if store_root_env:
        store_root = Path(store_root_env)
    else:
        local_app = os.environ.get("LOCALAPPDATA", "")
        store_root = Path(local_app) / "scistudio-stores" if local_app else Path("C:/scistudio-stores")

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

    return tempfile.mkdtemp(prefix="scistudio-worker-")


def _runtime_import_roots_for_block(block: Any) -> tuple[str, ...]:
    raw = getattr(block.__class__, "_scistudio_runtime_import_roots", ())
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return ()
    roots: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, (str, os.PathLike)):
            continue
        root = str(entry)
        if not root or root in seen:
            continue
        seen.add(root)
        roots.append(root)
    return tuple(roots)


def _desktop_plugin_import_root_keys() -> set[str]:
    try:
        from scistudio.desktop.paths import desktop_plugin_import_roots
    except Exception:
        logger.debug("Failed to resolve desktop plugin import roots", exc_info=True)
        return set()
    return {str(path.resolve()) for path in desktop_plugin_import_roots()}


def _pythonpath_entry_key(entry: str, *, parent_cwd: Path) -> str:
    path = Path(entry)
    if not path.is_absolute():
        path = parent_cwd / path
    return str(path.resolve())


def _worker_env(
    *,
    worker_cwd: str | None,
    project_dir: str | None,
) -> dict[str, str] | None:
    parent_cwd = Path(os.getcwd())
    env = dict(os.environ)
    plugin_root_keys = _desktop_plugin_import_root_keys()
    existing_pythonpath = env.get("PYTHONPATH", "")
    sanitized_existing: list[str] = []
    removed_plugin_path = False

    for part in existing_pythonpath.split(os.pathsep):
        if not part:
            continue
        if _pythonpath_entry_key(part, parent_cwd=parent_cwd) in plugin_root_keys:
            removed_plugin_path = True
            continue
        if worker_cwd is not None:
            path = Path(part)
            part = str(path if path.is_absolute() else parent_cwd / path)
        sanitized_existing.append(part)

    pythonpath_parts: list[str] = []
    if worker_cwd is not None:
        pythonpath_parts.extend([str(parent_cwd), str(parent_cwd / "src")])
    pythonpath_parts.extend(sanitized_existing)

    if project_dir:
        env["SCISTUDIO_PROJECT_DIR"] = str(Path(project_dir).resolve())

    if pythonpath_parts or removed_plugin_path:
        if pythonpath_parts:
            env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(pythonpath_parts))
        else:
            env.pop("PYTHONPATH", None)

    if worker_cwd is None and not project_dir and not removed_plugin_path:
        return None
    return env


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
        from scistudio.engine.runners.process_handle import (
            ProcessRegistry,
            build_worker_payload,
            register_async_process,
        )

        block_class_path = f"{block.__class__.__module__}.{block.__class__.__qualname__}"
        registry = self._registry if self._registry is not None else ProcessRegistry()
        block_id = getattr(block, "id", block_class_path)
        output_dir = _derive_output_dir(block, config)

        # #706: For Tier-1 drop-in blocks, the registry stamps the source
        # ``.py`` file path on the class so the worker can reload the module
        # (the synthetic ``_scistudio_dropin_*`` module name only exists in the
        # parent process's ``sys.modules``). Tier-2 / builtin block classes
        # do not have this attribute and use the normal import path.
        block_file_path = getattr(block.__class__, "_scistudio_file_path", None)
        runtime_import_roots = _runtime_import_roots_for_block(block)

        # Build the serialized payload for the worker subprocess.
        payload_bytes = build_worker_payload(
            block_class=block_class_path,
            inputs_refs=inputs,
            config=config,
            output_dir=output_dir,
            block_file_path=block_file_path,
            runtime_import_roots=runtime_import_roots,
        )

        # Launch via asyncio.create_subprocess_exec to avoid os.fork()
        # deadlock on macOS after importing native extensions (#483).
        # Fix #1305: worker cwd is the active project root so relative
        # paths in block configs (e.g. ``data/raw/foo.tif`` in LoadImage,
        # ``data/parquet/out.parquet`` in SaveData) resolve against the
        # project, not against wherever ``scistudio gui`` was launched.
        # When no project is active (CLI standalone runs), inherit the
        # parent process cwd unchanged.
        # TODO(#1305): per-block explicit ``_resolve_project_relative``
        #   helper would be more architecturally pure (AGENTS.md §3.5
        #   "Prefer explicit contracts over clever shortcuts"). This
        #   subprocess-cwd approach is the minimal Phase D unblocker;
        #   a follow-up may migrate IO blocks to explicit per-block
        #   resolution and revert this implicit cwd contract.
        #   Followup: https://github.com/zjzcpj/SciStudio/issues/1305
        project_dir = config.get("project_dir")
        worker_cwd = str(project_dir) if isinstance(project_dir, str) and project_dir else None
        # When we change the worker cwd away from the parent process cwd,
        # the parent's implicit ``sys.path[0]=''`` no longer resolves to
        # the same directory in the worker. Tests + dev workflows that
        # imported modules relative to the launcher cwd (e.g. tests'
        # ``tests.fixtures.noop_io_block``) would then fail with
        # ``ModuleNotFoundError``. Preserve that import surface by adding
        # the parent's cwd and source tree to the worker's ``PYTHONPATH``.
        project_dir_str = project_dir if isinstance(project_dir, str) and project_dir else None
        # #1365: propagate ``SCISTUDIO_PROJECT_DIR`` to the worker so the
        # worker-side :func:`scistudio.core.types.serialization._get_type_registry`
        # registers ``<project>/types`` as a TypeRegistry scan dir before the
        # first :func:`reconstruct_inputs` call. Without this the API-side
        # registry sees project drop-in :class:`DataObject` types but the
        # worker singleton falls back to base ``DataObject``. We always
        # rebuild ``worker_env`` when ``project_dir`` is known so the env
        # var lands on the subprocess even when ``worker_cwd`` itself was
        # already configured above.
        #
        # Codex P2 on PR #1386: absolutify before exporting. The worker
        # subprocess starts with ``cwd=worker_cwd=project_dir`` (the few
        # lines above), so a relative ``project_dir`` would have
        # :func:`_get_type_registry` resolve ``Path(project_dir_env) /
        # "types"`` against the new cwd, producing
        # ``<project>/<project>/types`` and missing every drop-in.
        # ``Path(...).resolve()`` makes the env var an absolute path the
        # worker can interpret without depending on its own cwd.
        worker_env = _worker_env(worker_cwd=worker_cwd, project_dir=project_dir_str)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "scistudio.engine.runners.worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            cwd=worker_cwd,
            env=worker_env,
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
                    _raise_for_worker_error_payload(payload)
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
                #
                # ADR-038 §5.2: lift ``environment`` from the worker envelope into
                # the returned dict under the sentinel key ``__scistudio_env__`` so
                # the scheduler can extract it for the BLOCK_DONE event data and
                # the LineageRecorder can attribute it to the run. The scheduler
                # pops the key before storing outputs in ``_block_outputs``, so
                # downstream blocks never observe it on their input ports.
                if isinstance(parsed, dict) and "outputs" in parsed:
                    outputs_dict = dict(parsed["outputs"])
                    env_payload = parsed.get("environment")
                    # Only stamp the sidecar when the worker reported a
                    # populated env — empty dicts are noise that breaks
                    # backward-compat tests asserting exact output shapes.
                    if isinstance(env_payload, dict) and env_payload:
                        outputs_dict["__scistudio_env__"] = env_payload
                    # #681: when the worker reports a non-DONE terminal state
                    # (block called ``self.transition()`` from inside ``run()``),
                    # raise the typed exception so the scheduler's existing
                    # exception path can finalise the block to that state.
                    final_state_raw = parsed.get("final_state")
                    if isinstance(final_state_raw, str):
                        from scistudio.blocks.base.state import BlockState
                        from scistudio.engine.runners.terminal_state import (
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
