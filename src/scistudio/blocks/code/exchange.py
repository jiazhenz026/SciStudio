"""CodeBlock v2 file-exchange layout and manifest helpers.

ADR-041 makes CodeBlock an AppBlock-shaped script boundary: the runtime
materialises typed inputs into per-port input folders, scripts write outputs
into per-port output folders, and later integration reconstructs typed outputs.
This module owns only that exchange bookkeeping. Format dispatch remains an
injectable adapter seam so ADR-043 capability lookup can be wired in later
without CodeBlock importing engine-level materialisation helpers.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection

PortDirection = Literal["input", "output"]
ManifestStatus = Literal["planned", "folder_created", "materialised", "collected", "missing", "ignored"]
DiagnosticSeverity = Literal["info", "warning", "error"]

_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


class MaterialiseAdapter(Protocol):
    """Callable seam for writing one :class:`DataObject` into an input folder."""

    def __call__(
        self,
        obj: DataObject,
        dest_dir: Path,
        extension: str,
        *,
        filename_stem: str,
        capability_id: str | None = None,
    ) -> Path: ...


class ReconstructAdapter(Protocol):
    """Callable seam for reconstructing one output file into a DataObject."""

    def __call__(
        self,
        path: Path,
        target_type: type[DataObject] | str,
        extension: str,
        *,
        capability_id: str | None = None,
    ) -> DataObject: ...


@dataclass(frozen=True, kw_only=True)
class CodeBlockExchangePort:
    """Declared file-exchange contract for one CodeBlock port."""

    name: str
    direction: PortDirection
    data_type: type[DataObject] | str = DataObject
    extension: str
    capability_id: str | None = None
    required: bool = True
    folder_name: str | None = None


@dataclass(frozen=True, kw_only=True)
class CodeBlockExchangeLayout:
    """Concrete per-run exchange directory layout."""

    exchange_dir: Path
    inputs_dir: Path
    outputs_dir: Path
    manifest_path: Path
    logs_dir: Path
    temp_dir: Path


@dataclass(frozen=True, kw_only=True)
class ExchangeFileRecord:
    """Manifest record for one materialised or collected file."""

    port_name: str
    direction: PortDirection
    path: Path
    object_type: str
    format_hint: str
    status: ManifestStatus
    capability_id: str | None = None
    warning: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "port_name": self.port_name,
            "direction": self.direction,
            "path": str(self.path),
            "object_type": self.object_type,
            "format_hint": self.format_hint,
            "status": self.status,
            "capability_id": self.capability_id,
            "warning": self.warning,
        }


@dataclass(frozen=True, kw_only=True)
class ExchangeDiagnostic:
    """Structured exchange warning/error surfaced to later runtime integration."""

    severity: DiagnosticSeverity
    code: str
    message: str
    port_name: str | None = None
    path: Path | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "port_name": self.port_name,
            "path": str(self.path) if self.path is not None else None,
        }


@dataclass(kw_only=True)
class PortManifestRecord:
    """Manifest record for one declared input or output port."""

    name: str
    direction: PortDirection
    object_type: str
    folder: Path
    format_hint: str
    capability_id: str | None
    required: bool
    status: ManifestStatus = "planned"
    files: list[ExchangeFileRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "direction": self.direction,
            "object_type": self.object_type,
            "folder": str(self.folder),
            "format_hint": self.format_hint,
            "capability_id": self.capability_id,
            "required": self.required,
            "status": self.status,
            "files": [record.to_dict() for record in self.files],
            "warnings": list(self.warnings),
        }


@dataclass(kw_only=True)
class CodeBlockExchangeManifest:
    """Concrete exchange manifest for one CodeBlock run.

    Manifest records are keyed by ``(direction, name)`` so a CodeBlock
    declaring an input port and an output port with the same name (e.g.
    ``data -> data``) keeps both records (#1281). The
    :attr:`input_folders` / :attr:`output_folders` views remain keyed by
    bare port ``name`` because port names are unique within a single
    direction.
    """

    layout: CodeBlockExchangeLayout
    ports: dict[tuple[PortDirection, str], PortManifestRecord]
    diagnostics: list[ExchangeDiagnostic] = field(default_factory=list)

    @property
    def input_folders(self) -> dict[str, Path]:
        return {record.name: record.folder for record in self.ports.values() if record.direction == "input"}

    @property
    def output_folders(self) -> dict[str, Path]:
        return {record.name: record.folder for record in self.ports.values() if record.direction == "output"}

    def to_dict(self) -> dict[str, object]:
        # Serialise the ``(direction, name)`` tuple keys as
        # ``"<direction>:<name>"`` so the manifest JSON has stable
        # string keys without losing the direction discriminator.
        return {
            "exchange_dir": str(self.layout.exchange_dir),
            "inputs_dir": str(self.layout.inputs_dir),
            "outputs_dir": str(self.layout.outputs_dir),
            "manifest_path": str(self.layout.manifest_path),
            "logs_dir": str(self.layout.logs_dir),
            "temp_dir": str(self.layout.temp_dir),
            "ports": {
                f"{direction}:{name}": record.to_dict()
                for (direction, name), record in sorted(self.ports.items())
            },
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


@dataclass(frozen=True, kw_only=True)
class OutputDiscoveryResult:
    """Declared-output scan result before reconstruction."""

    files_by_port: dict[str, list[Path]]
    diagnostics: list[ExchangeDiagnostic]

    @property
    def has_errors(self) -> bool:
        return any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


class CodeBlockExchangeError(RuntimeError):
    """Raised when exchange diagnostics contain blocking errors."""

    def __init__(self, message: str, diagnostics: Sequence[ExchangeDiagnostic]) -> None:
        super().__init__(message)
        self.diagnostics = list(diagnostics)


def normalise_extension(extension: str) -> str:
    """Return a deterministic lowercase extension with a leading dot."""

    stripped = extension.strip().lower()
    if not stripped:
        raise ValueError("Port extension must not be empty.")
    if not stripped.startswith("."):
        stripped = f".{stripped}"
    if "/" in stripped or "\\" in stripped:
        raise ValueError(f"Port extension must not contain path separators: {extension!r}")
    return stripped


def safe_exchange_name(value: str, *, fallback: str = "port") -> str:
    """Normalise a user-facing name into one safe path component."""

    candidate = _SAFE_NAME_PATTERN.sub("_", value.strip()).strip("._-")
    if not candidate:
        return fallback
    return candidate


def create_codeblock_exchange_layout(
    exchange_root: Path,
    *,
    block_id: str,
    run_id: str,
    block_slug: str = "codeblock",
    create: bool = True,
) -> CodeBlockExchangeLayout:
    """Create or describe the per-run CodeBlock exchange directory layout."""

    block_dir_name = f"{safe_exchange_name(block_slug)}-{safe_exchange_name(block_id, fallback='block')}"
    run_dir_name = safe_exchange_name(run_id, fallback="run")
    exchange_dir = exchange_root / block_dir_name / run_dir_name
    layout = CodeBlockExchangeLayout(
        exchange_dir=exchange_dir,
        inputs_dir=exchange_dir / "inputs",
        outputs_dir=exchange_dir / "outputs",
        manifest_path=exchange_dir / "manifest.json",
        logs_dir=exchange_dir / "logs",
        temp_dir=exchange_dir / "tmp",
    )
    if create:
        for directory in (layout.inputs_dir, layout.outputs_dir, layout.logs_dir, layout.temp_dir):
            directory.mkdir(parents=True, exist_ok=True)
    return layout


def allocate_port_folder(parent: Path, port_name: str, used_names: set[str], *, create: bool = True) -> Path:
    """Allocate a deterministic per-port folder with collision-safe suffixing."""

    base = safe_exchange_name(port_name, fallback="port")
    candidates = [base, f"{base}__scistudio"]
    candidates.extend(f"{base}__scistudio_{index}" for index in range(2, 10_000))
    for candidate in candidates:
        if candidate in used_names:
            continue
        path = parent / candidate
        if path.exists() and candidate == base:
            continue
        if path.exists() and candidate != base:
            continue
        used_names.add(candidate)
        if create:
            path.mkdir(parents=True, exist_ok=False)
        return path
    raise RuntimeError(f"Could not allocate exchange folder for port {port_name!r}.")


def plan_input_filenames(objects: Sequence[DataObject], *, extension: str) -> list[str]:
    """Plan deterministic input filenames for a single port's objects."""

    ext = normalise_extension(extension)
    used: set[str] = set()
    planned: list[str] = []
    for index, obj in enumerate(objects, start=1):
        stem = _source_stem(obj, ext) or f"item_{index:04d}"
        planned.append(_dedupe_filename(stem, ext, used))
    return planned


def initialise_exchange_manifest(
    port_configs: Sequence[CodeBlockExchangePort],
    *,
    layout: CodeBlockExchangeLayout,
) -> CodeBlockExchangeManifest:
    """Create all declared port folders and return an initial manifest."""

    input_names: set[str] = set()
    output_names: set[str] = set()
    records: dict[tuple[PortDirection, str], PortManifestRecord] = {}
    for port in port_configs:
        parent = layout.inputs_dir if port.direction == "input" else layout.outputs_dir
        used_names = input_names if port.direction == "input" else output_names
        folder = (
            allocate_port_folder(parent, port.folder_name, used_names)
            if port.folder_name is not None
            else allocate_port_folder(parent, port.name, used_names)
        )
        # Key by ``(direction, name)`` so an input port and an output port
        # sharing the same name (e.g. ``data -> data``) do not overwrite
        # each other (#1281).
        records[(port.direction, port.name)] = PortManifestRecord(
            name=port.name,
            direction=port.direction,
            object_type=_type_hint_name(port.data_type),
            folder=folder,
            format_hint=normalise_extension(port.extension),
            capability_id=port.capability_id,
            required=port.required,
            status="folder_created",
        )
    return CodeBlockExchangeManifest(layout=layout, ports=records)


def prepare_codeblock_exchange(
    inputs: Mapping[str, DataObject | Collection],
    port_configs: Sequence[CodeBlockExchangePort],
    *,
    exchange_root: Path,
    block_id: str,
    run_id: str,
    materialise_adapter: MaterialiseAdapter,
    block_slug: str = "codeblock",
) -> CodeBlockExchangeManifest:
    """Prepare exchange folders and materialise declared inputs."""

    layout = create_codeblock_exchange_layout(
        exchange_root,
        block_id=block_id,
        run_id=run_id,
        block_slug=block_slug,
    )
    manifest = initialise_exchange_manifest(port_configs, layout=layout)
    for port in (port for port in port_configs if port.direction == "input"):
        record = manifest.ports[(port.direction, port.name)]
        value = inputs.get(port.name)
        if value is None:
            diagnostic = ExchangeDiagnostic(
                severity="error" if port.required else "warning",
                code="missing_input",
                message=f"Input port {port.name!r} has no value to materialise.",
                port_name=port.name,
                path=record.folder,
            )
            manifest.diagnostics.append(diagnostic)
            record.status = "missing"
            record.warnings.append(diagnostic.message)
            continue

        objects = _coerce_input_objects(value)
        filenames = plan_input_filenames(objects, extension=port.extension)
        for obj, filename in zip(objects, filenames, strict=True):
            stem = _strip_declared_extension(filename, normalise_extension(port.extension))
            written = materialise_adapter(
                obj,
                record.folder,
                normalise_extension(port.extension),
                filename_stem=stem,
                capability_id=port.capability_id,
            )
            record.files.append(
                ExchangeFileRecord(
                    port_name=port.name,
                    direction="input",
                    path=written,
                    object_type=type(obj).__name__,
                    format_hint=normalise_extension(port.extension),
                    capability_id=port.capability_id,
                    status="materialised",
                )
            )
        record.status = "materialised"
    return manifest


def discover_declared_outputs(
    port_configs: Sequence[CodeBlockExchangePort],
    *,
    manifest: CodeBlockExchangeManifest,
) -> OutputDiscoveryResult:
    """Discover declared output files and report missing or extra outputs."""

    output_ports = [port for port in port_configs if port.direction == "output"]
    known_folders = {manifest.ports[(port.direction, port.name)].folder.resolve(): port for port in output_ports}
    files_by_port: dict[str, list[Path]] = {port.name: [] for port in output_ports}
    diagnostics: list[ExchangeDiagnostic] = []

    for port in output_ports:
        record = manifest.ports[(port.direction, port.name)]
        extension = normalise_extension(port.extension)
        matching: list[Path] = []
        mismatched: list[Path] = []
        if record.folder.exists():
            for path in sorted(record.folder.iterdir(), key=lambda item: item.name.lower()):
                if not path.is_file():
                    continue
                if _matches_extension(path, extension):
                    matching.append(path)
                else:
                    mismatched.append(path)

        for path in mismatched:
            diagnostics.append(
                ExchangeDiagnostic(
                    severity="warning",
                    code="output_extension_mismatch",
                    message=(
                        f"Output file {path.name!r} in port {port.name!r} does not match declared "
                        f"extension {extension!r}; ignoring it."
                    ),
                    port_name=port.name,
                    path=path,
                )
            )
            record.files.append(
                ExchangeFileRecord(
                    port_name=port.name,
                    direction="output",
                    path=path,
                    object_type=_type_hint_name(port.data_type),
                    format_hint=extension,
                    capability_id=port.capability_id,
                    status="ignored",
                    warning=f"Does not match declared extension {extension!r}.",
                )
            )

        files_by_port[port.name] = matching
        for path in matching:
            record.files.append(
                ExchangeFileRecord(
                    port_name=port.name,
                    direction="output",
                    path=path,
                    object_type=_type_hint_name(port.data_type),
                    format_hint=extension,
                    capability_id=port.capability_id,
                    status="collected",
                )
            )
        record.status = "collected" if matching else "missing"
        if port.required and not matching:
            diagnostics.append(
                ExchangeDiagnostic(
                    severity="error",
                    code="missing_required_output",
                    message=f"Required output port {port.name!r} produced no {extension!r} files.",
                    port_name=port.name,
                    path=record.folder,
                )
            )

    if manifest.layout.outputs_dir.exists():
        for child in sorted(manifest.layout.outputs_dir.iterdir(), key=lambda item: item.name.lower()):
            resolved = child.resolve()
            if resolved in known_folders:
                continue
            if child.is_file():
                diagnostics.append(
                    ExchangeDiagnostic(
                        severity="warning",
                        code="extra_output_file",
                        message=f"Unexpected file {child.name!r} directly under outputs/ is ignored.",
                        path=child,
                    )
                )
            elif child.is_dir():
                diagnostics.append(
                    ExchangeDiagnostic(
                        severity="warning",
                        code="unknown_output_folder",
                        message=f"Unexpected output folder {child.name!r} is ignored.",
                        path=child,
                    )
                )

    manifest.diagnostics.extend(diagnostics)
    return OutputDiscoveryResult(files_by_port=files_by_port, diagnostics=diagnostics)


def collect_codeblock_outputs(
    port_configs: Sequence[CodeBlockExchangePort],
    *,
    manifest: CodeBlockExchangeManifest,
    reconstruct_adapter: ReconstructAdapter,
) -> dict[str, Collection]:
    """Discover and reconstruct declared output files into Collections."""

    discovery = discover_declared_outputs(port_configs, manifest=manifest)
    if discovery.has_errors:
        raise CodeBlockExchangeError("CodeBlock output discovery failed.", discovery.diagnostics)

    outputs: dict[str, Collection] = {}
    for port in (port for port in port_configs if port.direction == "output"):
        extension = normalise_extension(port.extension)
        objects = [
            reconstruct_adapter(
                path,
                port.data_type,
                extension,
                capability_id=port.capability_id,
            )
            for path in discovery.files_by_port[port.name]
        ]
        item_type = type(objects[0]) if objects else _collection_item_type(port.data_type)
        outputs[port.name] = Collection(objects, item_type=item_type)
    return outputs


def _coerce_input_objects(value: DataObject | Collection) -> list[DataObject]:
    if isinstance(value, Collection):
        return list(value)
    if isinstance(value, DataObject):
        return [value]
    raise TypeError(f"CodeBlock exchange inputs must be DataObject or Collection, got {type(value).__name__}.")


def _collection_item_type(data_type: type[DataObject] | str) -> type[DataObject]:
    if isinstance(data_type, type) and issubclass(data_type, DataObject):
        return data_type
    return DataObject


def _type_hint_name(data_type: type[DataObject] | str) -> str:
    return data_type.__name__ if isinstance(data_type, type) else str(data_type)


def _source_stem(obj: DataObject, extension: str) -> str | None:
    storage_ref = getattr(obj, "storage_ref", None)
    raw_path = getattr(storage_ref, "path", None)
    if raw_path is None:
        return None
    filename = Path(str(raw_path)).name
    stem = _strip_declared_extension(filename, extension)
    return safe_exchange_name(stem, fallback="item")


def _dedupe_filename(stem: str, extension: str, used: set[str]) -> str:
    base = safe_exchange_name(stem, fallback="item")
    candidates = [f"{base}{extension}"]
    candidates.extend(f"{base}__{index}{extension}" for index in range(2, 10_000))
    for candidate in candidates:
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise RuntimeError(f"Could not allocate exchange filename for stem {stem!r}.")


def _strip_declared_extension(filename: str, extension: str) -> str:
    if filename.lower().endswith(extension):
        return filename[: -len(extension)]
    return Path(filename).stem


def _matches_extension(path: Path, extension: str) -> bool:
    return path.name.lower().endswith(normalise_extension(extension))
