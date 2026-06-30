"""AppBlock — bridges external GUI software via file-exchange protocol."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, ClassVar, cast

from scistudio.blocks.app.bridge import FileExchangeBridge
from scistudio.blocks.app.command_validator import validate_app_command
from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.exceptions import BlockCancelledByAppError
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.base.state import ExecutionMode
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.stability import provisional

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

    Internal (ADR-052 §7.1, option b): :class:`FileWatcher` now accepts a plain
    ``subprocess.Popen`` directly (alive while ``poll()`` is None), so the public
    path no longer needs this wrapper. Kept internal for back-compat with
    out-of-tree callers mid-migration; not part of the public surface.

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


@provisional(since="0.3.1")
class AppBlock(Block):
    """Hand a workflow step off to an external GUI application.

    Subclass this (or configure one directly) to wrap a desktop program — an
    image viewer, an analysis GUI, a file converter — as a workflow block. You
    point it at an executable; the block writes its inputs into a shared
    "exchange" folder on disk, launches the program, waits for the program to
    write result files into an output folder, and packs those files back into
    the block's output ports.

    While the external program is open, the block reports that it is paused and
    waiting, so the rest of the workflow knows it is blocked on you (or on the
    program) rather than stuck. Once result files appear and stop changing, the
    block finishes on its own.

    Config-driven tools: some command-line tools do not read the exchange
    directory themselves — they expect a generated config/parameter file listing
    each input by path and a non-default command line (for example
    ``tool --config config.xml``). Override :meth:`prepare_launch` to generate
    that file from the staged inputs and return the launch arguments; the
    default implementation is a no-op and keeps the standard behavior.

    Ports and config:
        - Reads an optional input port named ``data`` by default; you can add or
          rename input and output ports in the port editor. Each output port may
          declare a file *extension* so that result files are sorted into ports
          by their type (for example ``.csv`` files to one port, ``.png`` to
          another).
        - Emits one output Collection per output port. With no ports declared it
          falls back to emitting one
          :class:`~scistudio.core.types.artifact.Artifact` per output file.
        - The ``app_command`` config field (the path to the executable) is
          required; the optional ``output_dir`` field chooses where results are
          saved.

    Example:
        >>> class FijiBlock(AppBlock):
        ...     app_command = "/Applications/Fiji.app"
        ...     output_patterns = ["*.tif"]
    """

    app_command: ClassVar[str] = ""
    """Default path to the external executable to launch.

    Usually left empty here and set per workflow via the ``app_command`` config
    field; a subclass may hard-code it (for example a fixed install path).
    """
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.EXTERNAL
    """Marks the block as driven by an external process rather than run in-engine."""
    output_patterns: ClassVar[list[str]] = ["*"]
    """Glob patterns the watcher uses to find result files (default: every file)."""
    terminate_grace_sec: ClassVar[float] = 10.0
    """Seconds to wait after asking the external process to quit before force-killing it."""

    # Issue #680: AppBlock ports are user-configurable via the port editor.
    # The ClassVar values below act as default scaffolds — subclasses may
    # override them, and any user can replace them at config time through
    # the port editor (ADR-029).
    variadic_inputs: ClassVar[bool] = True
    """Allow the input ports to be edited per node in the port editor."""
    variadic_outputs: ClassVar[bool] = True
    """Allow the output ports to be edited per node in the port editor."""

    name: ClassVar[str] = "App Block"
    """Display name shown for this block in the palette and on its node."""
    description: ClassVar[str] = "Delegate work to an external GUI application"
    """One-line description shown in the block palette."""

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataObject], required=False, description="Input data for the app"),
    ]
    """Default input ports: a single optional ``data`` port; users may edit these."""
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[Artifact], description="Output artifacts from the app"),
    ]
    """Default output ports: a single ``result`` port; users may edit these."""
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
            # ``output_patterns`` is no longer a user-facing config field: when
            # output ports are declared they already carry per-port extensions
            # that bin saved files, so the watcher glob falls back to the
            # ClassVar default (["*"]) via ``config.get(...) or
            # self.output_patterns`` in run(). Removed from the UI per the
            # 2026-06 config pass.
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
    """Form schema describing this block's config fields for the editor UI."""

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
        through :func:`scistudio.blocks.io.materialisation.reconstruct_from_file`
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
        from scistudio.blocks.base.ports import ports_from_config_dicts
        from scistudio.blocks.io.materialisation import reconstruct_from_file

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

    @provisional(since="0.3.2")
    def prepare_launch(
        self,
        exchange_dir: Path,
        output_dir: Path,
        config: BlockConfig,
    ) -> list[str] | None:
        """Customise the launch of the external tool after inputs are staged.

        This hook is called once per run, after :meth:`run` has materialised the
        block's inputs into *exchange_dir* (``inputs/<port>/item_XXXX.<ext>`` and
        a ``manifest.json``) and created *output_dir*, but **before** the
        external process is started. The default implementation is a no-op that
        returns ``None``, so the base block and every existing subclass keep the
        original behavior unchanged.

        Override this for tools that do not read the exchange directory
        themselves. A *config-driven* command-line tool typically wants a
        generated config/parameter file that enumerates each staged input by
        absolute path plus the output directory, and is launched with a
        non-default command line (for example ``tool --config config.xml``)
        rather than receiving a directory as a positional argument. A subclass
        can do both here:

        1. read the already-staged inputs under *exchange_dir* (via
           ``manifest.json`` or by walking the ``inputs/`` tree) and write the
           tool's config/parameter file (point its outputs at *output_dir* so
           the watcher sees them);
        2. return the argv to launch the tool with.

        The returned list is passed to the bridge as ``argv_override`` and
        becomes the trailing arguments after the validated executable (the
        executable itself is still resolved and injection-checked by
        :func:`validate_app_command`). Returning ``None`` keeps the default
        behavior of passing *exchange_dir* as the sole trailing argument.

        Security: the returned argv is authored by the block, not by untrusted
        user input, and the process is started with ``shell=False`` (each list
        element is one literal ``argv`` token with no shell interpretation),
        exactly like the default ``[str(exchange_dir)]`` trailing argument. It
        therefore needs no separate shell-metacharacter validation; do not build
        it by concatenating an untrusted string into one element.

        Args:
            exchange_dir: The exchange directory holding the staged inputs and
                ``manifest.json`` for this run.
            output_dir: The directory the watcher will poll for result files;
                point the tool's outputs here.
            config: The node configuration for this run.

        Returns:
            The argv (trailing arguments) to launch the tool with, or ``None``
            to use the default behavior.

        Example:
            A minimal config-driven pseudo-tool launched as
            ``mytool --config <file>``::

                class MyToolBlock(AppBlock):
                    app_command = "mytool"

                    def prepare_launch(self, exchange_dir, output_dir, config):
                        inputs = sorted((exchange_dir / "inputs").rglob("*"))
                        config_path = exchange_dir / "config.txt"
                        lines = [f"out_dir={output_dir}"]
                        lines += [f"input={p}" for p in inputs if p.is_file()]
                        config_path.write_text("\\n".join(lines), encoding="utf-8")
                        return ["--config", str(config_path)]
        """
        return None

    @provisional(since="0.3.1")
    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Serialise inputs, launch the external app, and collect its outputs.

        This is the block's main step. It writes each input into a shared
        exchange folder, validates and launches the configured executable,
        watches the output folder until result files appear and settle, then
        loads those files back into output Collections. The external process is
        always waited on (and terminated or killed if it overruns), and any
        exchange folder created just for this run is removed, even on error.

        Between staging the inputs and launching the process, :meth:`prepare_launch`
        is called so subclasses wrapping config-driven tools can generate a
        config file and supply a custom launch command line; by default it is a
        no-op and the executable is launched with the exchange folder as its
        sole trailing argument.

        If output ports were declared in the port editor, result files are
        sorted into those ports by file extension; otherwise every result file
        becomes one :class:`~scistudio.core.types.artifact.Artifact`.

        Args:
            inputs: Input Collections keyed by input-port name.
            config: The node configuration. ``app_command`` (the executable
                path) is required; ``output_dir``, ``output_patterns``,
                ``output_ports``, ``stability_period``, and ``done_marker`` are
                optional.

        Returns:
            Output Collections keyed by output-port name.

        Raises:
            ValueError: If no ``app_command`` is set, the command fails the
                injection-safety check, or a required output port receives no
                matching files.
            LookupError: If a declared output port type cannot be reconstructed
                from its matching file.
            BlockCancelledByAppError: If the external process exits before
                writing any output, so the step is recorded as cancelled.
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
                exchange_dir = Path(tempfile.mkdtemp(prefix="scistudio_app_"))
        exchange_dir.mkdir(parents=True, exist_ok=True)

        # #339: Determine whether exchange_dir is a temp directory that we own.
        # Project-dir and explicit exchange dirs are intentionally persistent.
        is_temp_dir = not explicit_dir and not (config.get("project_dir") and config.get("block_id"))

        # ADR-020 §5: AppBlocks receive whole collections and decide their own
        # exchange format. The file-exchange bridge materialises one file per
        # collection item and records a ``collection`` manifest entry (see
        # ``FileExchangeBridge.prepare``), so a multi-item batch must reach the
        # bridge *as a Collection*. Only a length-one collection is unpacked to a
        # bare DataObject, so a single input still lands as one file at
        # ``inputs/<port>.<ext>`` (and a single-object manifest entry) rather than
        # ``inputs/<port>/item_0000.<ext>``. A 0- or multi-item collection is
        # passed through unchanged so ``prepare`` routes it to its
        # collection-materialise branch.
        #
        # #1874: previously a multi-item collection was downcast to a bare
        # ``list``, which is neither a Collection nor a DataObject and so fell
        # through to ``prepare``'s JSON fallback — silently serialising the items
        # as ``repr`` strings and staging no files. Single inputs survived only
        # because they were unpacked to a bare DataObject.
        unpacked_inputs: dict[str, Any] = {}
        for key, value in inputs.items():
            if isinstance(value, Collection) and len(value) == 1:
                unpacked_inputs[key] = value[0]
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
            # Resolve the output directory *before* launch so the pre-launch
            # hook and the watcher observe the same directory. ADR-030 D3:
            # use the user-selected output_dir when configured.
            # ADR-052 §7.1 (option b): FileWatcher accepts a plain
            # ``subprocess.Popen`` as its ``process_handle`` (alive while
            # ``poll()`` is None), so no adapter wrapper is needed.
            from scistudio.blocks.app.watcher import FileWatcher, ProcessExitedWithoutOutputError

            custom_output_dir = config.get("output_dir")
            output_dir = Path(custom_output_dir) if custom_output_dir else exchange_dir / "outputs"
            output_dir.mkdir(parents=True, exist_ok=True)

            # ADR-006 Addendum 1 (#1870): pre-launch hook. Inputs are now staged
            # under ``exchange_dir`` and ``output_dir`` exists, but the external
            # process has not started. Subclasses may read the staged inputs to
            # generate the config/parameter file a config-driven tool needs and
            # return the argv used to launch it. ``None`` keeps the default
            # behavior (``exchange_dir`` as the sole trailing argument).
            argv_override = self.prepare_launch(exchange_dir, output_dir, config)

            # Step 2: Launch external app (waits for external interaction).
            # PAUSED visibility for in-flight AppBlocks is tracked in #56
            # (subprocess→engine status channel); the engine-owned scheduler
            # (ADR-018 §8.1) is the authoritative state machine.
            proc = bridge.launch(command, exchange_dir, argv_override=argv_override)

            # Step 3: Watch for outputs with process monitoring.
            stability_period = float(config.get("stability_period", 2.0))
            done_marker = config.get("done_marker")
            watcher = FileWatcher(
                directory=output_dir,
                patterns=patterns,
                timeout=None,
                process_handle=proc,
                stability_period=stability_period,
                done_marker=done_marker,
            )
            watcher.start()
            try:
                output_files = watcher.wait_for_output()
            except ProcessExitedWithoutOutputError as exc:
                # ADR-018: external process exited without producing output —
                # signal CANCELLED to the worker, which forwards it to the
                # engine via the ``final_state`` envelope (#681 / #1334).
                raise BlockCancelledByAppError(str(exc)) from exc
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
