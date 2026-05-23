"""Reusable validation for ADR-041 CodeBlock v2 declarations."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from scistudio.blocks.code.config import CodeBlockConfig, legacy_migration_diagnostics
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

_CAPABILITY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_CORE_DATA_TYPES: dict[str, type[DataObject]] = {
    cls.__name__: cls for cls in (DataObject, Array, DataFrame, Series, Text, Artifact, CompositeData)
}
# Fix #1308: mirror the strip-set in ``code_block._persisted_codeblock_config``.
# DAGScheduler injects ``workflow_id`` alongside ``project_dir`` / ``block_id``;
# any key missing from BOTH sets fails CodeBlockConfig(extra="forbid").
_RUNTIME_ONLY_CONFIG_KEYS = {
    "project_dir",
    "block_id",
    "workflow_id",
    "run_id",
    "registry",
    "materialise_adapter",
    "reconstruct_adapter",
}


@dataclass(frozen=True)
class CodeBlockValidationDiagnostic:
    """Human-readable validation diagnostic for one CodeBlock config field."""

    field: str
    message: str
    severity: str = "error"
    port_name: str | None = None

    def render(self, *, node_id: str | None = None) -> str:
        """Render this diagnostic in workflow-validator style."""

        prefix = f"Node '{node_id}': " if node_id else ""
        port = f" port '{self.port_name}'" if self.port_name else ""
        return f"{prefix}CodeBlock{port} {self.field}: {self.message}"


def codeblock_config_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return persisted CodeBlock config values from root or ``params`` shape."""

    params = config.get("params")
    if isinstance(params, Mapping):
        raw = dict(params)
        for key, value in config.items():
            if key != "params" and key not in raw:
                raw[key] = value
    else:
        raw = dict(config)
    return {key: value for key, value in raw.items() if key not in _RUNTIME_ONLY_CONFIG_KEYS}


def resolve_codeblock_data_type(data_type: str) -> type[DataObject]:
    """Resolve a persisted CodeBlock ``data_type`` name to a DataObject class."""

    try:
        return _CORE_DATA_TYPES[data_type]
    except KeyError as exc:
        raise ValueError(f"unknown data_type {data_type!r}; expected one of {sorted(_CORE_DATA_TYPES)}") from exc


def selected_codeblock_capabilities(config: CodeBlockConfig) -> dict[str, str]:
    """Return declared capability ids keyed by ``direction:port``."""

    selected: dict[str, str] = {}
    for port in [*config.inputs, *config.outputs]:
        if port.capability_id:
            selected[f"{port.direction}:{port.name}"] = port.capability_id
    return selected


def validate_codeblock_config(
    config: Mapping[str, Any],
    *,
    project_dir: Path,
    registry: BlockRegistry | None = None,
) -> list[CodeBlockValidationDiagnostic]:
    """Validate persisted ADR-041 CodeBlock v2 config without resolving interpreters."""

    payload = codeblock_config_payload(config)
    diagnostics: list[CodeBlockValidationDiagnostic] = []

    diagnostics.extend(_legacy_diagnostics(payload))
    if diagnostics:
        return diagnostics

    try:
        parsed = CodeBlockConfig(**payload)
    except ValidationError as exc:
        return [
            CodeBlockValidationDiagnostic(
                field="config",
                message=f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}",
            )
            for error in exc.errors()
        ]
    except ValueError as exc:
        return [CodeBlockValidationDiagnostic(field="config", message=str(exc))]

    diagnostics.extend(_path_diagnostics(parsed, project_dir=project_dir))
    if not any(diagnostic.field == "script_path" for diagnostic in diagnostics):
        diagnostics.extend(_script_extension_diagnostics(parsed, project_dir=project_dir))

    diagnostics.extend(_port_diagnostics(parsed, registry=registry))
    return diagnostics


def _legacy_diagnostics(payload: Mapping[str, Any]) -> list[CodeBlockValidationDiagnostic]:
    diagnostics: list[CodeBlockValidationDiagnostic] = []
    for diagnostic in legacy_migration_diagnostics(payload):
        diagnostics.append(
            CodeBlockValidationDiagnostic(
                field="migration",
                message=f"{diagnostic.message} Suggested target: {diagnostic.suggested_target}",
                severity=diagnostic.severity,
            )
        )
    for legacy_field in ("mode", "language"):
        if legacy_field in payload:
            diagnostics.append(
                CodeBlockValidationDiagnostic(
                    field=legacy_field,
                    message="legacy CodeBlock runner fields are not valid in CodeBlock v2; use file exchange ports.",
                )
            )
    return diagnostics


def _path_diagnostics(config: CodeBlockConfig, *, project_dir: Path) -> list[CodeBlockValidationDiagnostic]:
    checks = (
        ("script_path", config.resolve_script_path),
        ("working_directory", config.resolve_working_directory),
        ("exchange_root", config.resolve_exchange_root),
    )
    diagnostics: list[CodeBlockValidationDiagnostic] = []
    for field_name, resolver in checks:
        try:
            resolver(project_dir)
        except Exception as exc:
            diagnostics.append(CodeBlockValidationDiagnostic(field=field_name, message=str(exc)))
    return diagnostics


def _script_extension_diagnostics(
    config: CodeBlockConfig,
    *,
    project_dir: Path,
) -> list[CodeBlockValidationDiagnostic]:
    try:
        script_path = config.resolve_script_path(project_dir)
    except Exception:
        return []

    from scistudio.blocks.code.code_block import list_codeblock_backends

    extension = script_path.suffix.lower()
    supported = sorted({ext.lower() for backend in list_codeblock_backends() for ext in backend.extensions})
    if extension in supported:
        return []
    return [
        CodeBlockValidationDiagnostic(
            field="script_path",
            message=f"unsupported script extension {extension or '<none>'!r}; registered extensions: {supported}",
        )
    ]


def _port_diagnostics(
    config: CodeBlockConfig,
    *,
    registry: BlockRegistry | None,
) -> list[CodeBlockValidationDiagnostic]:
    diagnostics: list[CodeBlockValidationDiagnostic] = []
    seen: set[tuple[str, str]] = set()
    for expected_direction, ports in (("input", config.inputs), ("output", config.outputs)):
        for port in ports:
            if port.direction != expected_direction:
                diagnostics.append(
                    CodeBlockValidationDiagnostic(
                        field="direction",
                        port_name=port.name,
                        message=f"declared under {expected_direction}s but direction is {port.direction!r}",
                    )
                )
            key = (port.direction, port.name)
            if key in seen:
                diagnostics.append(
                    CodeBlockValidationDiagnostic(
                        field="name",
                        port_name=port.name,
                        message=f"duplicate {port.direction} port name",
                    )
                )
            seen.add(key)

            folder = (port.exchange_folder or "").replace("\\", "/")
            expected_prefix = "inputs/" if port.direction == "input" else "outputs/"
            if folder and not folder.startswith(expected_prefix):
                diagnostics.append(
                    CodeBlockValidationDiagnostic(
                        field="exchange_folder",
                        port_name=port.name,
                        message=f"must start with {expected_prefix!r} for {port.direction} ports",
                    )
                )

            data_type: type[DataObject] | None = None
            try:
                data_type = resolve_codeblock_data_type(port.data_type)
            except ValueError as exc:
                diagnostics.append(
                    CodeBlockValidationDiagnostic(field="data_type", port_name=port.name, message=str(exc))
                )

            diagnostics.extend(_capability_id_diagnostics(port_name=port.name, capability_id=port.capability_id))
            if registry is not None and data_type is not None:
                diagnostics.extend(_capability_lookup_diagnostics(port, data_type=data_type, registry=registry))
    return diagnostics


def _capability_id_diagnostics(
    *,
    port_name: str,
    capability_id: str | None,
) -> list[CodeBlockValidationDiagnostic]:
    if capability_id is None:
        return []
    if not capability_id.strip():
        return [
            CodeBlockValidationDiagnostic(
                field="capability_id",
                port_name=port_name,
                message="capability_id must not be empty when declared",
            )
        ]
    if not _CAPABILITY_ID_RE.match(capability_id):
        return [
            CodeBlockValidationDiagnostic(
                field="capability_id",
                port_name=port_name,
                message=f"invalid capability_id syntax {capability_id!r}",
            )
        ]
    return []


def _capability_lookup_diagnostics(
    port: Any,
    *,
    data_type: type[DataObject],
    registry: BlockRegistry,
) -> list[CodeBlockValidationDiagnostic]:
    # ADR-047: the ADR-043 capability methods are the only supported lookup
    # surface. Production ``BlockRegistry`` always defines them; tests that
    # mock the registry must supply them too.
    method_name = "find_saver_capability" if port.direction == "input" else "find_loader_capability"
    capability_method = getattr(registry, method_name, None)
    if not callable(capability_method):
        return []
    try:
        capability_method(
            data_type=data_type,
            extension=port.extension,
            capability_id=port.capability_id,
        )
    except Exception as exc:
        return [
            CodeBlockValidationDiagnostic(
                field="capability",
                port_name=port.name,
                message=(f"{port.direction} {port.data_type} {port.extension} capability lookup failed: {exc}"),
            )
        ]
    return []
