"""The Code Block: run a project-local script as a workflow step.

The Code Block lets you drop a script you already have (Python, R/Quarto,
shell, MATLAB/Octave, or a Jupyter notebook) into a workflow without rewriting
it as a SciStudio block. The runtime owns a per-run exchange folder: it writes
the block's declared inputs to files, launches your script through the matching
interpreter backend, and reads the files your script writes back into typed
outputs.

Scripts exchange data through files, not function calls. Pasted inline code and
old SciStudio entry-function scripts are rejected with a clear migration message
rather than being run, so a script must read its inputs from, and write its
outputs to, the exchange folders described by the ``SCISTUDIO_*`` environment
variables.
"""

from __future__ import annotations

import importlib
import inspect
import json
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar, cast

from pydantic import ValidationError

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort

# Issue #1482: backend-registry primitives live in the sibling
# ``_backends_registry`` module so ``validation.py`` can depend on them
# without forming a cycle through ``code_block``. The names are
# re-exported below for backward compatibility with the ``backends/``
# subpackage and ``scistudio.blocks.code.__init__`` consumers.
from scistudio.blocks.code._backends_registry import (
    CodeBlockBackend as CodeBlockBackend,
)
from scistudio.blocks.code._backends_registry import (
    CodeBlockRuntimeContext as CodeBlockRuntimeContext,
)
from scistudio.blocks.code._backends_registry import (
    CodeBlockTimeoutError as CodeBlockTimeoutError,
)
from scistudio.blocks.code._backends_registry import (
    codeblock_exchange_env as codeblock_exchange_env,
)
from scistudio.blocks.code._backends_registry import (
    ensure_codeblock_backends_loaded as ensure_codeblock_backends_loaded,
)
from scistudio.blocks.code._backends_registry import (
    list_codeblock_backends as list_codeblock_backends,
)
from scistudio.blocks.code._backends_registry import (
    register_codeblock_backend as register_codeblock_backend,
)
from scistudio.blocks.code._backends_registry import (
    resolve_codeblock_backend as resolve_codeblock_backend,
)
from scistudio.blocks.code._backends_registry import (
    run_codeblock_process as run_codeblock_process,
)
from scistudio.blocks.code._backends_registry import (
    unregister_codeblock_backend as unregister_codeblock_backend,
)
from scistudio.blocks.code.config import CodeBlockConfig, MigrationDiagnostic, legacy_migration_diagnostics
from scistudio.blocks.code.exchange import (
    CodeBlockExchangeError,
    CodeBlockExchangeManifest,
    CodeBlockExchangePort,
    collect_codeblock_outputs,
    prepare_codeblock_exchange,
)
from scistudio.blocks.code.lazy_list import LazyList
from scistudio.blocks.code.provenance import (
    build_codeblock_provenance_payload,
    capture_environment_snapshot,
    capture_script_provenance,
    utc_now_iso,
)
from scistudio.blocks.code.validation import (
    selected_codeblock_capabilities,
    validate_codeblock_config,
)
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text
from scistudio.stability import provisional


@provisional(since="0.3.1")
class CodeBlockMigrationError(ValueError):
    """Raised when an old-style Code Block config cannot be run as-is.

    Earlier Code Blocks could hold pasted inline code or call a named entry
    function. Those forms are no longer run; this error explains what needs to
    change (save the code as a project-local script that exchanges data through
    files) and carries one diagnostic per problem found.
    """

    def __init__(self, diagnostics: list[MigrationDiagnostic]) -> None:
        self.diagnostics = diagnostics
        """The list of migration problems found, each with a suggested fix."""
        messages = "; ".join(diagnostic.message for diagnostic in diagnostics)
        super().__init__(f"CodeBlock v2 migration required: {messages}")


@provisional(since="0.3.1")
class CodeBlockExecutionError(RuntimeError):
    """Raised when the script's interpreter process exits with an error.

    The Code Block treats any non-zero exit code from the launched script as a
    failure and raises this, attaching the script's captured output so you can
    diagnose what went wrong.
    """

    def __init__(self, message: str, *, returncode: int, stdout: str, stderr: str) -> None:
        super().__init__(message)
        self.returncode = returncode
        """The non-zero exit code the script's process returned."""
        self.stdout = stdout
        """Standard output captured from the failed script run."""
        self.stderr = stderr
        """Standard error captured from the failed script run."""


_CORE_DATA_TYPES: dict[str, type[DataObject]] = {
    cls.__name__: cls for cls in (DataObject, Array, DataFrame, Series, Text, Artifact, CompositeData)
}


@provisional(since="0.3.1")
class CodeBlock(Block):
    """Run a project-local script as a workflow step, exchanging data via files.

    Use the Code Block when you have a working script (Python, R/Quarto, shell,
    MATLAB/Octave, or a Jupyter notebook) and want to run it inside a workflow
    without porting it to a SciStudio block. You point the block at a script in
    your project and declare which inputs it reads and which outputs it writes.
    The interpreter is chosen automatically from the script's file extension.

    How data flows:

    - **Inputs**: the runtime writes each declared input to a file in the run's
      ``inputs/`` folder before the script starts. The default ``data`` input
      port accepts any data object; you can add more named input ports.
    - **Outputs**: the script writes files into the run's ``outputs/`` folder,
      which the runtime reads back into typed data objects. The default
      ``result`` output port returns any data object; you can add more named
      output ports.
    - Your script finds these folders through the ``SCISTUDIO_*`` environment
      variables the runtime sets for it.

    Configuration highlights (see :class:`CodeBlockConfig` for the full set):
    ``script_path`` (required) points at the project-local script; ``inputs``
    and ``outputs`` declare the file-exchange ports; ``interpreter_mode`` and
    ``interpreter_path`` choose between an auto-detected interpreter and an
    explicit one.

    Example:
        >>> block = CodeBlock({"script_path": "scripts/analyse.py"})
        >>> block.name
        'Code Block'
    """

    name: ClassVar[str] = "Code Block"
    """Display name shown for this block in the workflow editor."""
    description: ClassVar[str] = "Run project-local scripts through typed file exchange"
    """One-line description shown in the block palette."""

    # Issue #1325: CodeBlock matches AppBlock / AIBlock — user-configurable
    # variadic ports so the canvas "+" button can append script-specific
    # inputs / outputs. The ClassVar entries below are the default scaffolds;
    # the per-instance port lists are stored under
    # ``config.{input,output}_ports`` and merged at canvas render time by
    # ``flowNodeBuilder.resolveVariadicPorts``.
    variadic_inputs: ClassVar[bool] = True
    """Whether users may add extra input ports to a block instance on the canvas."""
    variadic_outputs: ClassVar[bool] = True
    """Whether users may add extra output ports to a block instance on the canvas."""

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataObject], required=False, description="Declared v2 inputs"),
    ]
    """Default input ports: a single optional ``data`` port accepting any data object."""
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[DataObject], description="Declared v2 outputs"),
    ]
    """Default output ports: a single ``result`` port returning any data object."""
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "script_path": {"type": "string", "title": "Project Script", "ui_priority": 1},
            "language": {
                "type": "string",
                "enum": ["python", "r", "julia"],
                "title": "Legacy Language",
                "deprecated": True,
                "ui_priority": 99,
            },
            "interpreter_mode": {
                "type": "string",
                "enum": ["auto", "existing"],
                "default": "auto",
                "title": "Interpreter Mode",
                "ui_priority": 2,
            },
            "interpreter_path": {"type": "string", "title": "Interpreter Path", "ui_priority": 3},
            # ``working_directory`` removed from the UI (2026-06 config pass):
            # CodeBlock scripts always run from the project root. The field is
            # forced to "." in _persisted_codeblock_config.
            "exchange_root": {"type": "string", "default": "exchange", "title": "Exchange Root", "ui_priority": 5},
            # ``timeout_seconds`` removed from the UI (2026-06 config pass):
            # CodeBlock always runs without a wall-clock timeout. See
            # _persisted_codeblock_config, which strips any stale value.
            "inputs": {
                "type": "array",
                "title": "Declared Inputs",
                "ui_priority": 10,
                "items": {"type": "object"},
            },
            "outputs": {
                "type": "array",
                "title": "Declared Outputs",
                "ui_priority": 11,
                "items": {"type": "object"},
            },
            "input_ports": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "types": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "default": [],
                "title": "Input Ports",
                "ui_widget": "port_editor",
                "ui_priority": 12,
            },
            "output_ports": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "types": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "default": [],
                "title": "Output Ports",
                "ui_widget": "port_editor",
                "ui_priority": 13,
            },
        },
        "required": ["script_path"],
    }
    """JSON Schema describing the block's editable configuration fields.

    Drives the configuration form in the workflow editor; ``script_path`` is the
    only required field.
    """

    @provisional(since="0.3.1")
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Create a Code Block, optionally seeding its configuration.

        Args:
            config: Optional configuration mapping (for example
                ``{"script_path": "scripts/run.py"}``). Validated when the block
                runs, not here.
        """
        super().__init__(config=config)
        self.last_provenance_payload: dict[str, Any] | None = None
        """Provenance record from the most recent :meth:`run`, or ``None`` before the first run."""
        self.last_exchange_manifest: CodeBlockExchangeManifest | None = None
        """Exchange manifest from the most recent :meth:`run`, or ``None`` before the first run."""
        self.last_process: subprocess.CompletedProcess[str] | None = None
        """The finished script process from the most recent :meth:`run`, or ``None`` before it ran."""

    @provisional(since="0.3.1")
    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Run the configured script and return its declared outputs.

        Writes the declared inputs to files, picks the interpreter backend from
        the script's extension, launches the script, then reads the files it
        produced back into typed output collections. After the call, the run's
        provenance, exchange manifest, and finished process are available on
        :attr:`last_provenance_payload`, :attr:`last_exchange_manifest`, and
        :attr:`last_process`.

        Args:
            inputs: Declared inputs keyed by input-port name; each value is a
                collection of data objects to write to that port's input folder.
            config: The block's configuration for this run (see
                :class:`CodeBlockConfig` for the accepted fields).

        Returns:
            A mapping from each declared output-port name to the collection of
            data objects reconstructed from the files the script wrote.

        Raises:
            CodeBlockMigrationError: If the configuration is an old inline or
                entry-function form that must be migrated first.
            CodeBlockExecutionError: If the script's process exits with an error.
            CodeBlockExchangeError: If preparing inputs or collecting required
                outputs fails.
            ValueError: If the configuration fails validation.
        """

        raw_config = _config_mapping(config)
        diagnostics = _migration_diagnostics(raw_config)
        if diagnostics:
            raise CodeBlockMigrationError(diagnostics)

        try:
            code_config = CodeBlockConfig(**_persisted_codeblock_config(raw_config))
        except ValidationError:
            raise
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        project_dir = _project_dir(raw_config)
        validation_diagnostics = validate_codeblock_config(
            raw_config, project_dir=project_dir, registry=raw_config.get("registry")
        )
        validation_errors = [
            diagnostic.render() for diagnostic in validation_diagnostics if diagnostic.severity == "error"
        ]
        if validation_errors:
            raise ValueError("; ".join(validation_errors))

        script_path = code_config.resolve_script_path(project_dir)
        _raise_if_legacy_script_shape(script_path, code_config)
        exchange_root = code_config.resolve_exchange_root(project_dir)
        block_id = str(raw_config.get("block_id") or "codeblock")
        run_id = str(raw_config.get("run_id") or uuid.uuid4().hex)
        ports = _exchange_ports(code_config)
        registry = raw_config.get("registry")
        environment_config = _environment_config(code_config)
        backend = resolve_codeblock_backend(script_path, code_config)

        manifest = prepare_codeblock_exchange(
            inputs,
            ports,
            exchange_root=exchange_root,
            block_id=block_id,
            run_id=run_id,
            materialise_adapter=raw_config.get("materialise_adapter") or _materialise_adapter(registry),
        )
        self.last_exchange_manifest = manifest
        _write_manifest(manifest)
        _raise_if_manifest_has_errors(manifest)

        runtime_context = CodeBlockRuntimeContext(
            config=code_config,
            script_path=script_path,
            project_dir=project_dir,
            exchange_dir=manifest.layout.exchange_dir,
            environment_config=environment_config,
        )
        resolved_interpreter = backend.resolve(runtime_context)
        script_provenance = capture_script_provenance(script_path, project_dir=project_dir)
        environment = capture_environment_snapshot(
            resolved_interpreter,
            mode=code_config.interpreter_mode,
            environment_delta=resolved_interpreter.environment,
        )
        started_at = utc_now_iso()
        completed_at: str | None = None

        try:
            completed = backend.run(runtime_context, resolved_interpreter)
            self.last_process = completed
            if completed.returncode != 0:
                raise CodeBlockExecutionError(
                    f"CodeBlock script exited with status {completed.returncode}.",
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )

            outputs = collect_codeblock_outputs(
                ports,
                manifest=manifest,
                reconstruct_adapter=raw_config.get("reconstruct_adapter") or _reconstruct_adapter(registry),
            )
            return outputs
        finally:
            completed_at = utc_now_iso()
            self.last_provenance_payload = build_codeblock_provenance_payload(
                script=script_provenance,
                interpreter=resolved_interpreter,
                environment=environment,
                started_at=started_at,
                completed_at=completed_at,
                selected_capabilities=_selected_capabilities(code_config),
                exchange_manifest=manifest.to_dict(),
            )
            _write_manifest(manifest)

    def _unpack_inputs(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        """Legacy helper retained for explicit migration-era compatibility tests."""

        unpacked: dict[str, Any] = {}
        for name, value in inputs.items():
            if isinstance(value, Collection):
                if len(value) == 1:
                    unpacked[name] = value[0].to_memory()
                else:
                    unpacked[name] = LazyList(value)
            else:
                unpacked[name] = value
        return unpacked

    def _repack_outputs(self, outputs: Mapping[str, Any]) -> dict[str, Any]:
        """Legacy helper retained while inline execution migrates to v2 exchange.

        TODO(#1330): redundant once engine ``_normalize_outputs`` list-unpack
            soaks (the engine-side helper at
            ``scistudio.engine.runners.worker._normalize_outputs`` now
            handles both bare DataObject and bare list[DataObject] at the
            output boundary, per ADR-020 §3). Kept as explicit intent
            during the soak window and to preserve legacy-inline-execution
            shape. Cleanup PR removes this helper together with the six
            similar manual wraps in concrete blocks.
            Followup: #1330 follow-up cleanup PR.
        """

        repacked: dict[str, Any] = {}
        for name, value in outputs.items():
            if isinstance(value, DataObject):
                repacked[name] = Collection([value])
            elif isinstance(value, list) and value and all(isinstance(item, DataObject) for item in value):
                repacked[name] = Collection(value)
            else:
                repacked[name] = value
        return repacked


def _config_mapping(config: BlockConfig) -> dict[str, Any]:
    raw = dict(config.params)
    extras = config.__pydantic_extra__ or {}
    raw.update(extras)
    return raw


def _persisted_codeblock_config(raw_config: Mapping[str, Any]) -> dict[str, Any]:
    # Fix #1308: ``workflow_id`` is injected by ``DAGScheduler`` alongside
    # ``block_id`` / ``project_dir`` and MUST be stripped here, otherwise
    # ``CodeBlockConfig(extra="forbid")`` rejects it and every CodeBlock run
    # inside a workflow fails with ``extra_forbidden``.
    runtime_only = {
        "project_dir",
        "block_id",
        "workflow_id",
        "run_id",
        "registry",
        "materialise_adapter",
        "reconstruct_adapter",
    }
    # ``timeout_seconds`` and ``working_directory`` are no longer
    # user-configurable (2026-06 config pass). Stripping them forces the
    # CodeBlockConfig defaults: no wall-clock timeout (None ->
    # ``subprocess.run(timeout=None)``) and the project root as the script cwd
    # ("."), even if a legacy workflow persisted other values.
    dropped = runtime_only | {"timeout_seconds", "working_directory"}
    return {key: value for key, value in raw_config.items() if key not in dropped}


def _migration_diagnostics(raw_config: Mapping[str, Any]) -> list[MigrationDiagnostic]:
    diagnostics = legacy_migration_diagnostics(raw_config)
    for legacy_field in ("mode", "language"):
        if legacy_field in raw_config:
            diagnostics.append(
                MigrationDiagnostic(
                    legacy_mode=str(raw_config.get(legacy_field) or "legacy"),
                    severity="error",
                    message=(
                        f"Legacy CodeBlock field {legacy_field!r} is not valid in CodeBlock v2; "
                        "configure a project-local script with declared file-exchange ports."
                    ),
                    suggested_target="Remove legacy runner fields and use ADR-041 file exchange.",
                )
            )
    return diagnostics


def _project_dir(raw_config: Mapping[str, Any]) -> Path:
    return Path(str(raw_config.get("project_dir") or Path.cwd())).resolve()


def _environment_config(config: CodeBlockConfig) -> dict[str, Any]:
    merged = dict(config.environment)
    if config.environment_variables:
        merged["environment_variables"] = dict(config.environment_variables)
    if config.working_directory:
        merged["working_directory"] = config.working_directory
    return merged


def _exchange_ports(config: CodeBlockConfig) -> list[CodeBlockExchangePort]:
    ports: list[CodeBlockExchangePort] = []
    for port in [*config.inputs, *config.outputs]:
        ports.append(
            CodeBlockExchangePort(
                name=port.name,
                direction=port.direction,
                data_type=_resolve_data_type(port.data_type),
                extension=port.extension,
                capability_id=port.capability_id,
                required=port.required,
                folder_name=_folder_name(port.exchange_folder, direction=port.direction),
            )
        )
    return ports


def _resolve_data_type(data_type: str) -> type[DataObject]:
    if data_type in _CORE_DATA_TYPES:
        return _CORE_DATA_TYPES[data_type]
    # Beyond the core types, resolve plugin / user-defined DataObject subtypes
    # (e.g. Image, Spectrum) the same way variadic ports do
    # (``ports_from_config_dicts._resolve_type``): load the class from the shared
    # type registry and fall back to DataObject when the worker cannot resolve
    # it. This keeps CodeBlock's declared-port types consistent with AppBlock.
    from scistudio.core.types.serialization import _get_type_registry

    try:
        resolved = _get_type_registry().load_class(data_type)
    except Exception:
        resolved = None
    if isinstance(resolved, type) and issubclass(resolved, DataObject):
        return resolved
    return DataObject


def _folder_name(exchange_folder: str | None, *, direction: str) -> str | None:
    if exchange_folder is None:
        return None
    normalized = exchange_folder.replace("\\", "/").strip("/")
    prefix = f"{direction}s/"
    if normalized.startswith(prefix):
        normalized = normalized[len(prefix) :]
    return normalized or None


def _raise_if_legacy_script_shape(script_path: Path, config: CodeBlockConfig) -> None:
    if config.outputs:
        return
    try:
        from scistudio.blocks.code.introspect import introspect_script

        info = introspect_script(script_path)
    except Exception:
        return
    if info.get("has_run"):
        raise CodeBlockMigrationError(
            [
                MigrationDiagnostic(
                    legacy_mode="script",
                    severity="error",
                    message=(
                        "Script defines a SciStudio-style run() entry function but declares no "
                        "CodeBlock v2 output ports; v2 does not call entry functions."
                    ),
                    suggested_target="Adapt the script to write files under outputs/<port>/ or use ProcessBlock.",
                )
            ]
        )


def _raise_if_manifest_has_errors(manifest: CodeBlockExchangeManifest) -> None:
    errors = [diagnostic for diagnostic in manifest.diagnostics if diagnostic.severity == "error"]
    if errors:
        raise CodeBlockExchangeError("CodeBlock input exchange preparation failed.", errors)


def _materialise_adapter(registry: Any) -> Any:
    def adapter(
        obj: DataObject,
        dest_dir: Path,
        extension: str,
        *,
        filename_stem: str,
        capability_id: str | None = None,
    ) -> Path:
        materialisation = importlib.import_module("scistudio.engine.materialisation")
        materialise_to_file = materialisation.materialise_to_file

        kwargs: dict[str, Any] = {"filename_stem": filename_stem, "registry": registry}
        if _accepts_keyword(materialise_to_file, "capability_id"):
            kwargs["capability_id"] = capability_id
        return cast(Path, materialise_to_file(obj, dest_dir, extension, **kwargs))

    return adapter


def _reconstruct_adapter(registry: Any) -> Any:
    def adapter(
        path: Path,
        target_type: type[DataObject],
        extension: str,
        *,
        capability_id: str | None = None,
    ) -> DataObject:
        materialisation = importlib.import_module("scistudio.engine.materialisation")
        reconstruct_from_file = materialisation.reconstruct_from_file

        kwargs: dict[str, Any] = {"registry": registry}
        if _accepts_keyword(reconstruct_from_file, "capability_id"):
            kwargs["capability_id"] = capability_id
        return cast(DataObject, reconstruct_from_file(path, target_type, extension, **kwargs))

    return adapter


def _accepts_keyword(func: Any, name: str) -> bool:
    try:
        return name in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _selected_capabilities(config: CodeBlockConfig) -> dict[str, str]:
    return selected_codeblock_capabilities(config)


def _write_manifest(manifest: CodeBlockExchangeManifest) -> None:
    manifest.layout.manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
