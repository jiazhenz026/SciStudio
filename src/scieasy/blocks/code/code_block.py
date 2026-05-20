"""CodeBlock v2 runtime integration and Python backend.

ADR-041 narrows CodeBlock to an AppBlock-shaped script boundary: the
runtime owns exchange folders, materialises declared inputs, launches a
project-local script through a resolved interpreter backend, and reconstructs
declared outputs.  This module wires the shared v2 runtime layer and the
Python backend; notebook, R/Quarto, shell, and MATLAB-family backends remain
separate ADR-041 implementation tracks.  Inline code and SciEasy
entry-function script modes are intentionally rejected with migration
diagnostics instead of being interpreted as v2 configs.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol, cast

from pydantic import ValidationError

from scieasy.blocks.base.block import Block
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.code.config import CodeBlockConfig, MigrationDiagnostic, legacy_migration_diagnostics
from scieasy.blocks.code.exchange import (
    CodeBlockExchangeError,
    CodeBlockExchangeManifest,
    CodeBlockExchangePort,
    collect_codeblock_outputs,
    prepare_codeblock_exchange,
)
from scieasy.blocks.code.interpreters import ResolvedInterpreter
from scieasy.blocks.code.lazy_list import LazyList
from scieasy.blocks.code.provenance import (
    build_codeblock_provenance_payload,
    capture_environment_snapshot,
    capture_script_provenance,
    utc_now_iso,
)
from scieasy.blocks.code.validation import (
    selected_codeblock_capabilities,
    validate_codeblock_config,
)
from scieasy.core.types.array import Array
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy.core.types.composite import CompositeData
from scieasy.core.types.dataframe import DataFrame
from scieasy.core.types.series import Series
from scieasy.core.types.text import Text


class CodeBlockMigrationError(ValueError):
    """Raised when a legacy CodeBlock config needs explicit migration."""

    def __init__(self, diagnostics: list[MigrationDiagnostic]) -> None:
        self.diagnostics = diagnostics
        messages = "; ".join(diagnostic.message for diagnostic in diagnostics)
        super().__init__(f"CodeBlock v2 migration required: {messages}")


class CodeBlockExecutionError(RuntimeError):
    """Raised when the interpreter process exits unsuccessfully."""

    def __init__(self, message: str, *, returncode: int, stdout: str, stderr: str) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CodeBlockTimeoutError(TimeoutError):
    """Raised when a CodeBlock v2 script exceeds its configured timeout."""

    def __init__(self, message: str, *, timeout_seconds: float, stdout: str | None, stderr: str | None) -> None:
        super().__init__(message)
        self.timeout_seconds = timeout_seconds
        self.stdout = stdout
        self.stderr = stderr


_CORE_DATA_TYPES: dict[str, type[DataObject]] = {
    cls.__name__: cls for cls in (DataObject, Array, DataFrame, Series, Text, Artifact, CompositeData)
}


@dataclass(frozen=True)
class CodeBlockRuntimeContext:
    """Shared CodeBlock v2 execution context passed to interpreter backends."""

    config: CodeBlockConfig
    script_path: Path
    project_dir: Path
    exchange_dir: Path
    environment_config: Mapping[str, Any]


class CodeBlockBackend(Protocol):
    """Registration surface for CodeBlock v2 interpreter backends."""

    name: str
    extensions: frozenset[str]

    def supports(self, script_path: Path, config: CodeBlockConfig) -> bool:
        """Return whether this backend can run *script_path*."""

    def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
        """Resolve interpreter metadata for a CodeBlock run."""

    def run(
        self,
        context: CodeBlockRuntimeContext,
        interpreter: ResolvedInterpreter,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a prepared CodeBlock run."""


_CODEBLOCK_BACKENDS: list[CodeBlockBackend] = []
_BACKEND_MODULES_LOADED = False


def register_codeblock_backend(backend: CodeBlockBackend, *, replace: bool = False) -> None:
    """Register a CodeBlock v2 interpreter backend.

    Sibling ADR-041 tracks should register notebook, R/Quarto, shell, and
    MATLAB-family backends through this surface instead of editing
    ``CodeBlock`` dispatch logic.
    """

    normalized_extensions = frozenset(extension.lower() for extension in backend.extensions)
    if not backend.name:
        raise ValueError("CodeBlock backend name must not be empty")
    if not normalized_extensions:
        raise ValueError("CodeBlock backend must declare at least one extension")
    if any(not extension.startswith(".") for extension in normalized_extensions):
        raise ValueError("CodeBlock backend extensions must include a leading dot")

    conflicts = [
        existing
        for existing in _CODEBLOCK_BACKENDS
        if existing.name == backend.name or existing.extensions.intersection(normalized_extensions)
    ]
    if conflicts and not replace:
        names = ", ".join(sorted(existing.name for existing in conflicts))
        raise ValueError(f"CodeBlock backend conflicts with existing backend(s): {names}")

    _CODEBLOCK_BACKENDS[:] = [
        existing
        for existing in _CODEBLOCK_BACKENDS
        if existing.name != backend.name and not existing.extensions.intersection(normalized_extensions)
    ]
    _CODEBLOCK_BACKENDS.append(backend)


def unregister_codeblock_backend(name: str) -> None:
    """Remove a registered CodeBlock backend by name."""

    _CODEBLOCK_BACKENDS[:] = [backend for backend in _CODEBLOCK_BACKENDS if backend.name != name]


def list_codeblock_backends() -> tuple[CodeBlockBackend, ...]:
    """Return registered CodeBlock v2 interpreter backends."""

    ensure_codeblock_backends_loaded()
    return tuple(_CODEBLOCK_BACKENDS)


def resolve_codeblock_backend(script_path: Path, config: CodeBlockConfig) -> CodeBlockBackend:
    """Select the registered backend for a CodeBlock v2 script."""

    ensure_codeblock_backends_loaded()
    for backend in _CODEBLOCK_BACKENDS:
        if backend.supports(script_path, config):
            return backend
    supported = sorted({extension for backend in _CODEBLOCK_BACKENDS for extension in backend.extensions})
    raise ValueError(
        f"Unsupported CodeBlock script extension {script_path.suffix or '<none>'!r}; "
        f"registered extensions: {supported}."
    )


def ensure_codeblock_backends_loaded() -> None:
    """Load built-in CodeBlock backend modules exactly once."""

    global _BACKEND_MODULES_LOADED
    if _BACKEND_MODULES_LOADED:
        return
    from scieasy.blocks.code.backends import load_codeblock_backend_modules

    load_codeblock_backend_modules()
    _BACKEND_MODULES_LOADED = True


def run_codeblock_process(
    *,
    argv: Sequence[str],
    cwd: Path,
    env_delta: Mapping[str, str],
    timeout_seconds: float | None,
) -> subprocess.CompletedProcess[str]:
    """Run an interpreter process with CodeBlock v2 environment handling."""

    env = os.environ.copy()
    env.update({str(key): str(value) for key, value in env_delta.items()})
    try:
        return subprocess.run(
            [str(arg) for arg in argv],
            cwd=cwd,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodeBlockTimeoutError(
            f"CodeBlock script timed out after {timeout_seconds} seconds.",
            timeout_seconds=float(timeout_seconds or 0),
            stdout=exc.stdout if isinstance(exc.stdout, str) else None,
            stderr=exc.stderr if isinstance(exc.stderr, str) else None,
        ) from exc


class CodeBlock(Block):
    """Run project-local scripts through ADR-041 file exchange."""

    name: ClassVar[str] = "Code Block"
    description: ClassVar[str] = "Run project-local scripts through typed file exchange"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataObject], required=False, description="Declared v2 inputs"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[DataObject], description="Declared v2 outputs"),
    ]
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
            "working_directory": {"type": "string", "default": ".", "title": "Working Directory", "ui_priority": 4},
            "exchange_root": {"type": "string", "default": "exchange", "title": "Exchange Root", "ui_priority": 5},
            "timeout_seconds": {"type": "number", "title": "Timeout Seconds", "ui_priority": 6},
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

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config=config)
        self.last_provenance_payload: dict[str, Any] | None = None
        self.last_exchange_manifest: CodeBlockExchangeManifest | None = None
        self.last_process: subprocess.CompletedProcess[str] | None = None

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Execute a CodeBlock v2 script and return declared outputs."""

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
                    unpacked[name] = value[0].view().to_memory()
                else:
                    unpacked[name] = LazyList(value)
            else:
                unpacked[name] = value
        return unpacked

    def _repack_outputs(self, outputs: Mapping[str, Any]) -> dict[str, Any]:
        """Legacy helper retained while inline execution migrates to v2 exchange."""

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
    runtime_only = {
        "project_dir",
        "block_id",
        "run_id",
        "registry",
        "materialise_adapter",
        "reconstruct_adapter",
    }
    return {key: value for key, value in raw_config.items() if key not in runtime_only}


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
    raise ValueError(f"Unknown CodeBlock data_type {data_type!r}; expected one of {sorted(_CORE_DATA_TYPES)}.")


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
        from scieasy.blocks.code.introspect import introspect_script

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
                        "Script defines a SciEasy-style run() entry function but declares no "
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
        materialisation = importlib.import_module("scieasy.engine.materialisation")
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
        materialisation = importlib.import_module("scieasy.engine.materialisation")
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
