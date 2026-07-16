"""Checking a Code Block's configuration before it runs.

These helpers validate a saved Code Block configuration without launching any
interpreter: that the script path and folders stay inside the project, that the
file extension has a backend to run it, and that the declared ports are
well-formed. They return human-readable diagnostics the workflow editor can show
the user.
"""

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
from scistudio.stability import provisional

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
# Fix #1957: ``input_ports`` / ``output_ports`` are the ADR-029 variadic
# canvas-port definitions (CodeBlock is variadic, so its effective ports come
# from these via ``Block.get_effective_input_ports``). The frontend port editor
# persists them into the same node config blob, but they are NOT script-config
# fields, so ``CodeBlockConfig(extra="forbid")`` rejects them and validation
# fails the whole workflow. Strip them alongside the runtime-only keys before
# building ``CodeBlockConfig``. Mirrors ``code_block._persisted_codeblock_config``.
_GRAPH_PORT_CONFIG_KEYS = {"input_ports", "output_ports"}
_NON_SCRIPT_CONFIG_KEYS = _RUNTIME_ONLY_CONFIG_KEYS | _GRAPH_PORT_CONFIG_KEYS


@provisional(since="0.3.1")
@dataclass(frozen=True)
class CodeBlockValidationDiagnostic:
    """One problem found in a Code Block configuration, ready to show a user.

    Names the config field (and port, when relevant), explains what is wrong in
    plain language, and says whether it blocks the run (``"error"``) or is only
    advisory (``"warning"``).
    """

    field: str
    """The configuration field the problem relates to (for example ``"script_path"``)."""
    message: str
    """Human-readable explanation of the problem."""
    severity: str = "error"
    """Whether the problem blocks the run (``"error"``) or is advisory (``"warning"``)."""
    port_name: str | None = None
    """The port the problem relates to, if any."""

    def render(self, *, node_id: str | None = None) -> str:
        """Format this diagnostic as a one-line message for the workflow editor.

        Args:
            node_id: Optional workflow node identifier to prefix the message with.

        Returns:
            A single-line message naming the block, port, field, and problem.
        """

        prefix = f"Node '{node_id}': " if node_id else ""
        port = f" port '{self.port_name}'" if self.port_name else ""
        return f"{prefix}CodeBlock{port} {self.field}: {self.message}"


@provisional(since="0.3.1")
def codeblock_config_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    """Extract just the saved Code Block settings from a raw config mapping.

    A config may arrive with its fields at the top level or nested under a
    ``params`` key, and may carry keys that are not part of the script config:
    runtime-only keys the runtime injects (such as the project directory) and
    the ADR-029 variadic canvas-port keys (``input_ports`` / ``output_ports``)
    the port editor persists. This returns the script settings only, flattened
    and with those non-script keys removed.

    Args:
        config: The raw configuration mapping.

    Returns:
        The persisted Code Block settings as a plain dictionary.
    """

    params = config.get("params")
    if isinstance(params, Mapping):
        raw = dict(params)
        for key, value in config.items():
            if key != "params" and key not in raw:
                raw[key] = value
    else:
        raw = dict(config)
    return {key: value for key, value in raw.items() if key not in _NON_SCRIPT_CONFIG_KEYS}


@provisional(since="0.3.1")
def resolve_codeblock_data_type(data_type: str) -> type[DataObject]:
    """Look up a core data-type name and return its class.

    Args:
        data_type: A core data-type name such as ``"DataFrame"`` or ``"Array"``.

    Returns:
        The matching data-type class.

    Raises:
        ValueError: If the name is not one of the core data types.
    """

    try:
        return _CORE_DATA_TYPES[data_type]
    except KeyError as exc:
        raise ValueError(f"unknown data_type {data_type!r}; expected one of {sorted(_CORE_DATA_TYPES)}") from exc


@provisional(since="0.3.1")
def selected_codeblock_capabilities(config: CodeBlockConfig) -> dict[str, str]:
    """List the save/load handler chosen for each port, where one is pinned.

    Args:
        config: The Code Block configuration to inspect.

    Returns:
        A mapping from ``direction:port`` (for example ``"input:data"``) to the
        pinned handler identifier, for ports that pin one.
    """

    selected: dict[str, str] = {}
    for port in [*config.inputs, *config.outputs]:
        if port.capability_id:
            selected[f"{port.direction}:{port.name}"] = port.capability_id
    return selected


@provisional(since="0.3.1")
def validate_codeblock_config(
    config: Mapping[str, Any],
    *,
    project_dir: Path,
    registry: BlockRegistry | None = None,
) -> list[CodeBlockValidationDiagnostic]:
    """Check a saved Code Block configuration and return any problems found.

    Runs the configuration through the same model the runtime uses, then checks
    the script path and folders stay inside the project, the script's extension
    has a backend to run it, and each declared port is well-formed. No
    interpreter is launched. When a registry is provided, it also checks that a
    save/load handler exists for each port.

    Args:
        config: The raw saved configuration mapping.
        project_dir: Absolute path to the project root.
        registry: Optional block registry used to check that a file-format
            handler exists for each declared port.

    Returns:
        A list of diagnostics; empty when the configuration is valid.
    """

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

    # Issue #1482: import the backend-registry helper from the dedicated
    # sibling module, not via ``code_block`` (which would re-introduce
    # the ``code_block ↔ validation`` cycle that sentrux flags).
    from scistudio.blocks.code._backends_registry import list_codeblock_backends

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
