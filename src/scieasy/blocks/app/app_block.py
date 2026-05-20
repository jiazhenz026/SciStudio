"""AppBlock — bridges external GUI software via file-exchange protocol."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, ClassVar, cast

from scieasy.blocks.app.bridge import FileExchangeBridge
from scieasy.blocks.app.command_validator import validate_app_command
from scieasy.blocks.base.block import Block
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.base.state import BlockState, ExecutionMode
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection

logger = logging.getLogger(__name__)


def _normalize_extension(raw: Any) -> str:
    """Lowercase, strip leading dots, return ``""`` for null/empty inputs.

    Used by both the binner and the duplicate-extension validator so the
    matching rule is identical at config-save time and at runtime.
    """
    if raw is None:
        return ""
    text = str(raw).strip()
    while text.startswith("."):
        text = text[1:]
    return text.lower()


class _PopenProcessAdapter:
    """Adapter wrapping subprocess.Popen with process_handle interface for FileWatcher.

    ADR-019: FileWatcher expects a process_handle with ``is_alive()`` and ``pid``
    attributes. ``subprocess.Popen`` has ``poll()`` and ``pid`` but no ``is_alive()``.
    This adapter bridges the two interfaces.
    """

    def __init__(self, proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
        self._proc = proc

    @property
    def pid(self) -> int:
        return self._proc.pid

    def is_alive(self) -> bool:
        return self._proc.poll() is None


class AppBlock(Block):
    """Block that delegates work to an external GUI application.

    Communication happens via a file-exchange directory: the block serialises
    inputs, launches the application, watches for output files, and collects
    the results.

    State transitions: IDLE -> READY -> RUNNING -> PAUSED -> (RUNNING ->) DONE

    The block enters PAUSED state after launching the external application,
    signalling to the scheduler that it is waiting for external output.
    Once output files are detected, the block transitions back to RUNNING
    and then to DONE.
    """

    app_command: ClassVar[str] = ""
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL
    output_patterns: ClassVar[list[str]] = ["*"]
    terminate_grace_sec: ClassVar[float] = 10.0

    # Issue #680: AppBlock ports are user-configurable via the port editor.
    # The ClassVar values below act as default scaffolds — subclasses may
    # override them, and any user can replace them at config time through
    # the port editor (ADR-029).
    variadic_inputs: ClassVar[bool] = True
    variadic_outputs: ClassVar[bool] = True

    name: ClassVar[str] = "App Block"
    description: ClassVar[str] = "Delegate work to an external GUI application"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataObject], required=False, description="Input data for the app"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[Artifact], description="Output artifacts from the app"),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "app_command": {
                "type": "string",
                "title": "Executable Path",
                "ui_widget": "file_browser",
                "ui_priority": 0,
            },
            "output_dir": {
                "type": ["string", "null"],
                "default": None,
                "title": "Save Outputs At",
                "ui_widget": "directory_browser",
                "ui_priority": 1,
            },
            "output_patterns": {
                "type": "string",
                "title": "Output File Patterns",
                "default": "*",
                "ui_priority": 2,
            },
            # ADR-029 D12: port editor fields injected via MRO merge (ADR-030).
            # Leaf subclasses inherit these automatically; no subclass changes needed.
            # ui_priority >= 10 ensures these appear after block-specific config.
            "input_ports": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "types": {"type": "array", "items": {"type": "string"}},
                        "extension": {"type": "string"},
                        "capability_id": {"type": "string"},
                    },
                },
                "default": [],
                "title": "Input Ports",
                "ui_widget": "port_editor",
                "ui_priority": 10,
            },
            # Issue #680: each output port entry carries an additional
            # ``extension`` field (string, no leading dot, case-insensitive)
            # that the runtime uses to bin saved files into ports.
            "output_ports": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "types": {"type": "array", "items": {"type": "string"}},
                        "extension": {"type": "string"},
                        "capability_id": {"type": "string"},
                    },
                    "required": ["name", "extension"],
                },
                "default": [],
                "title": "Output Ports",
                "ui_widget": "port_editor",
                "ui_priority": 11,
            },
        },
        "required": ["app_command"],
    }

    # ------------------------------------------------------------------
    # Issue #680: extension-based output binning
    # ------------------------------------------------------------------

    def _output_port_extensions(self, config: BlockConfig) -> dict[str, str]:
        """Return ``{port_name: normalized_extension}`` from the configured output ports.

        Reads ``config["output_ports"]`` (the user-edited list of port dicts),
        normalises each ``extension`` value (lowercased, leading dots stripped)
        and returns the resulting mapping.  Falls back to an empty dict when
        the user has not declared any output ports — callers treat that as
        "use legacy bridge.collect() behaviour".
        """
        configured = config.get("output_ports")
        if not configured or not isinstance(configured, list):
            return {}
        mapping: dict[str, str] = {}
        for entry in configured:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            mapping[name] = _normalize_extension(entry.get("extension"))
        return mapping

    def _output_port_capability_ids(self, config: BlockConfig) -> dict[str, str]:
        """Return ``{port_name: capability_id}`` from configured output ports."""

        configured = config.get("output_ports")
        if not configured or not isinstance(configured, list):
            return {}
        mapping: dict[str, str] = {}
        for entry in configured:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            raw_capability_id = entry.get("capability_id")
            if raw_capability_id in (None, ""):
                continue
            capability_id = str(raw_capability_id).strip()
            if name and capability_id:
                mapping[name] = capability_id
        return mapping

    def _bin_outputs_by_extension(
        self,
        output_files: list[Path],
        config: BlockConfig,
    ) -> dict[str, Collection]:
        """Bin *output_files* into the configured output ports by file extension.

        Issue #680 routing rules (case-insensitive):

        - A file whose suffix matches a port's declared ``extension`` is
          appended to that port's Collection.
        - A required port that receives zero files raises ``ValueError``.
        - A file whose extension matches no port emits a warning log and
          is otherwise ignored.

        Issue #1079 (ADR-028 §D8): per-file item construction now goes
        through :func:`scieasy.blocks.io.materialisation.reconstruct_from_file`
        with ``target_type`` set to the port's declared first
        ``accepted_types`` entry. This replaces the previous silent
        downgrade of every non-Artifact declared port type to
        ``Artifact``. ``reconstruct_from_file`` handles three outcomes:

        - A loader is registered for ``(declared_type, extension)`` —
          returns a typed :class:`DataObject` instance.
        - No loader is registered but the declared type IS-A
          :class:`Artifact` — returns an :class:`Artifact` (legacy
          behavior preserved as an *intentional* fallback; no warning).
        - No loader is registered and the declared type is a non-Artifact
          concrete type — raises :class:`LookupError`, which propagates
          out of this method. Upstream callers (``AppBlock.run``) treat
          this as a contract violation: the declared port type cannot be
          honored.

        The Collection ``item_type`` is computed from the actual
        constructed-item class (``Artifact`` when no typed loader
        matched, the declared type otherwise) so the existing
        ``Collection.item_type`` homogeneity guarantee from #690 still
        holds.

        Effective output ports are resolved from *config* first (so that
        run-time ``config["output_ports"]`` always wins) and only fall
        back to ``self.get_effective_output_ports()`` when the runtime
        config does not specify any.  This keeps the binner usable both
        from scheduler-driven runs (where ``self.config`` mirrors the
        node config) and from direct ``block.run(config=...)`` test
        harnesses.
        """
        from scieasy.blocks.base.ports import ports_from_config_dicts
        from scieasy.blocks.io.materialisation import reconstruct_from_file

        config_ports = config.get("output_ports")
        ports: list[OutputPort]
        if config_ports and isinstance(config_ports, list):
            # ports_from_config_dicts returns list[InputPort] | list[OutputPort];
            # we requested direction="output" so the runtime type is list[OutputPort].
            ports = cast(list[OutputPort], list(ports_from_config_dicts(config_ports, "output")))
        else:
            ports = self.get_effective_output_ports()
        if not ports:
            return {}

        port_extensions = self._output_port_extensions(config)
        port_capability_ids = self._output_port_capability_ids(config)
        ext_to_port: dict[str, OutputPort] = {}
        for port in ports:
            ext = port_extensions.get(port.name, "")
            if not ext:
                # Port was declared in the editor but its extension field is
                # empty; treat it as unmatched. Required ports will raise
                # below, optional ports stay empty.
                continue
            ext_to_port[ext] = port

        # Resolve the declared target type per port. ``accepted_types`` is a
        # list of concrete classes (resolved by ``ports_from_config_dicts``);
        # the first entry is the canonical type for the port. Empty
        # accepted_types defaults to Artifact (the safest fallback,
        # consistent with the bridge.collect() path).
        #
        # Note on the ``DataObject`` root: ``DataObject`` declared as a
        # port target type is the "no specific type required" wildcard
        # (it's the root of the type hierarchy, not a real domain type).
        # ``reconstruct_from_file`` cannot perform typed dispatch against
        # the root either — its dynamic-port fallback requires a
        # *specific* core type and its Artifact fallback only applies to
        # Artifact subclasses. We therefore map ``DataObject`` ->
        # ``Artifact`` here so the binner keeps the legacy
        # "wildcard-port-yields-Artifact" behavior that ports_from_config_dicts
        # callers depend on, while still routing concrete declared types
        # through reconstruct_from_file.
        port_target_types: dict[str, type] = {}
        for port in ports:
            declared = port.accepted_types[0] if port.accepted_types else Artifact
            # Empty/malformed declarations may yield a non-class; guard
            # against that by falling back to Artifact.
            if not (isinstance(declared, type) and issubclass(declared, DataObject)):
                port_target_types[port.name] = Artifact
            elif declared is DataObject:
                # Wildcard port — fall back to Artifact, matching the
                # legacy semantics of the pre-#1079 binner.
                port_target_types[port.name] = Artifact
            else:
                port_target_types[port.name] = declared

        grouped: dict[str, list[DataObject]] = {port.name: [] for port in ports}
        unmatched: list[Path] = []
        for path in output_files:
            suffix = path.suffix.lstrip(".").lower()
            target = ext_to_port.get(suffix)
            if target is None:
                unmatched.append(path)
                continue
            target_type = port_target_types[target.name]
            # reconstruct_from_file handles three outcomes:
            #   - typed loader registered -> typed instance
            #   - no loader + Artifact target -> Artifact fallback
            #   - no loader + concrete non-Artifact target -> LookupError
            # We pass the normalised extension (with leading dot) so the
            # candidate list matches what BlockRegistry.find_loader sees.
            item = reconstruct_from_file(
                path,
                target_type=target_type,
                extension=f".{suffix}",
                capability_id=port_capability_ids.get(target.name),
            )
            grouped[target.name].append(item)

        for path in unmatched:
            logger.warning("Unmatched output file %r", path.name)

        for port in ports:
            if port.required and not grouped[port.name]:
                ext = port_extensions.get(port.name, "")
                raise ValueError(f"Port {port.name!r} required, no '.{ext}' files in output dir")

        result: dict[str, Collection] = {}
        for port in ports:
            items = grouped[port.name]
            # Compute the Collection's item_type from the actual
            # constructed items, not the originally-declared port type:
            # reconstruct_from_file may have returned Artifact via the
            # documented fallback even when the port declared an Artifact
            # subclass. For empty ports (optional, no matching files) fall
            # back to the declared target type — Collection homogeneity is
            # vacuous on the empty case.
            item_type = type(items[0]) if items else port_target_types[port.name]
            result[port.name] = Collection(items, item_type=item_type)
        return result

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Prepare inputs, launch the external app, and collect outputs.

        ADR-018: Handles CANCELLED transitions when external process exits unexpectedly.
        ADR-019: Stores ProcessHandle from bridge for cancellation support.
        ADR-020: Accepts and returns Collection-wrapped data.

        Issue #680: when the user has declared output ports via the port
        editor, output files are binned by extension instead of being
        passed through the legacy ``bridge.collect()`` path.

        Resource cleanup (#338, #339):
        - Subprocess is always waited on / terminated / killed in finally block.
        - Temp exchange directories (not project-dir) are cleaned up in finally block.
        """
        bridge = FileExchangeBridge()
        command = config.get("app_command") or self.app_command
        if not command:
            raise ValueError("AppBlock requires 'app_command' in config or as class variable")

        patterns = config.get("output_patterns") or self.output_patterns

        # Create exchange directory.
        # Prefer project workspace for reboot-survivable exchange dirs.
        explicit_dir = config.get("exchange_dir")
        if explicit_dir:
            exchange_dir = Path(explicit_dir)
        else:
            project_dir = config.get("project_dir")
            block_id = config.get("block_id", "")
            if project_dir and block_id:
                exchange_dir = Path(project_dir) / "data" / "exchange" / block_id
            else:
                exchange_dir = Path(tempfile.mkdtemp(prefix="scieasy_app_"))
        exchange_dir.mkdir(parents=True, exist_ok=True)

        # #339: Determine whether exchange_dir is a temp directory that we own.
        # Project-dir and explicit exchange dirs are intentionally persistent.
        is_temp_dir = not explicit_dir and not (config.get("project_dir") and config.get("block_id"))

        # ADR-020: Unpack Collection inputs to raw values for serialization.
        unpacked_inputs: dict[str, Any] = {}
        for key, value in inputs.items():
            if isinstance(value, Collection):
                items = list(value)
                unpacked_inputs[key] = items[0] if len(items) == 1 else items
            else:
                unpacked_inputs[key] = value

        # Step 1: Prepare inputs.
        bridge.prepare(
            unpacked_inputs,
            exchange_dir,
            input_ports=config.get("input_ports"),
        )

        # Issue #70: Validate command to prevent shell injection.
        try:
            validate_app_command(command)
        except ValueError as exc:
            raise ValueError(f"AppBlock command validation failed: {exc}") from exc

        proc: subprocess.Popen[bytes] | None = None
        try:
            # Step 2: Launch and pause (waiting for external interaction).
            self.transition(BlockState.PAUSED)
            proc = bridge.launch(command, exchange_dir)

            # ADR-019: Wrap Popen in adapter for FileWatcher process monitoring.
            process_adapter = _PopenProcessAdapter(proc)

            # Step 3: Watch for outputs with process monitoring.
            # ADR-030 D3: use user-selected output_dir if configured.
            from scieasy.blocks.app.watcher import FileWatcher, ProcessExitedWithoutOutputError

            custom_output_dir = config.get("output_dir")
            output_dir = Path(custom_output_dir) if custom_output_dir else exchange_dir / "outputs"
            output_dir.mkdir(parents=True, exist_ok=True)
            stability_period = float(config.get("stability_period", 2.0))
            done_marker = config.get("done_marker")
            watcher = FileWatcher(
                directory=output_dir,
                patterns=patterns,
                timeout=None,
                process_handle=process_adapter,
                stability_period=stability_period,
                done_marker=done_marker,
            )
            watcher.start()
            try:
                output_files = watcher.wait_for_output()
            except ProcessExitedWithoutOutputError:
                # ADR-018: Process exited without producing output — cancel.
                self.transition(BlockState.CANCELLED)
                return {}
            finally:
                watcher.stop()

            # Step 4: Collect results.
            # Issue #680: when the user has declared output ports via the
            # port editor, route files into those ports by extension; the
            # legacy ``bridge.collect()`` path (one Artifact per file,
            # keyed by file stem) is only used when no ports are declared.
            if config.get("output_ports"):
                return self._bin_outputs_by_extension(output_files, config)

            results = bridge.collect(output_files)

            # ADR-020: Wrap output artifacts in Collection.
            collection_results: dict[str, Any] = {}
            for key, value in results.items():
                if isinstance(value, Artifact):
                    collection_results[key] = Collection([value], item_type=Artifact)
                else:
                    collection_results[key] = value

            return collection_results
        finally:
            # #338: Reap subprocess to prevent zombie processes.
            if proc is not None:
                _cleanup_process(proc, self.terminate_grace_sec)
            # #339: Remove temp exchange directory (not project-dir).
            if is_temp_dir and exchange_dir.exists():
                shutil.rmtree(exchange_dir, ignore_errors=True)


def _cleanup_process(
    proc: subprocess.Popen[bytes],
    terminate_grace_sec: float = 10.0,
) -> None:
    """Wait for *proc* to exit; terminate/kill if it does not exit in time.

    Sequence: wait(5s) -> terminate -> wait(grace) -> kill -> wait.
    """
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=terminate_grace_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
