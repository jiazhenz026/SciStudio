"""File-exchange layout and manifest helpers for the Code Block.

A Code Block passes data to and from a script through files. This module owns
that bookkeeping: it lays out a per-run exchange folder, writes each declared
input into its own input folder, discovers the files the script wrote into each
output folder, and records what happened in a manifest. The actual file-format
conversion is handed to pluggable adapter callables, so this module never needs
to know how a given data type is written to or read from disk.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.stability import provisional

PortDirection = Literal["input", "output"]
ManifestStatus = Literal["planned", "folder_created", "materialised", "collected", "missing", "ignored"]
DiagnosticSeverity = Literal["info", "warning", "error"]

_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


@provisional(since="0.3.1")
class MaterialiseAdapter(Protocol):
    """A function that writes one data object into an input folder as a file.

    The Code Block calls a materialise adapter for each input it needs to hand
    to a script, turning an in-memory data object into a file the script can
    read. Supplying your own adapter lets you control how data types are written
    to disk.
    """

    def __call__(
        self,
        obj: DataObject,
        dest_dir: Path,
        extension: str,
        *,
        filename_stem: str,
        capability_id: str | None = None,
    ) -> Path:
        """Write *obj* into *dest_dir* and return the path of the written file.

        Args:
            obj: The data object to write.
            dest_dir: The port's input folder to write into.
            extension: File extension to use (with a leading dot).
            filename_stem: Base filename without extension.
            capability_id: Optional identifier pinning which save handler to use.

        Returns:
            The path of the file that was written.
        """
        ...


@provisional(since="0.3.1")
class ReconstructAdapter(Protocol):
    """A function that reads one output file back into a data object.

    The Code Block calls a reconstruct adapter for each file a script writes to
    a declared output port, turning it back into a typed in-memory object.
    Supplying your own adapter lets you control how files are read for each data
    type.
    """

    def __call__(
        self,
        path: Path,
        target_type: type[DataObject] | str,
        extension: str,
        *,
        capability_id: str | None = None,
    ) -> DataObject:
        """Read the file at *path* and return it as a data object.

        Args:
            path: The output file the script wrote.
            target_type: The data type to reconstruct, as a class or its name.
            extension: The file's extension (with a leading dot).
            capability_id: Optional identifier pinning which load handler to use.

        Returns:
            The reconstructed data object.
        """
        ...


@provisional(since="0.3.1")
@dataclass(frozen=True, kw_only=True)
class CodeBlockExchangePort:
    """A single Code Block port, resolved for use by the exchange runtime.

    This is the runtime view of one declared input or output port: the data
    type is a resolved class (not just a name), and the target folder is
    settled. The Code Block builds these from the saved :class:`PortFileConfig`
    entries before preparing the exchange folders.
    """

    name: str
    """Port name, matching the input/output port the script reads or writes."""
    direction: PortDirection
    """Whether this is an ``"input"`` the script reads or an ``"output"`` it writes."""
    data_type: type[DataObject] | str = DataObject
    """The data type carried, as a resolved class or its name."""
    extension: str
    """File extension for this port's files (with a leading dot)."""
    capability_id: str | None = None
    """Optional identifier pinning which save/load handler converts the files."""
    required: bool = True
    """Whether the run fails if this port has no value (inputs) or file (outputs)."""
    folder_name: str | None = None
    """Folder name under ``inputs/`` or ``outputs/`` for this port; ``None`` uses the name."""


@provisional(since="0.3.1")
@dataclass(frozen=True, kw_only=True)
class CodeBlockExchangeLayout:
    """The set of folders and files that make up one run's exchange directory.

    Every Code Block run gets its own exchange folder with fixed subfolders for
    inputs, outputs, logs, and scratch files, plus a manifest file recording
    what happened. This describes where each of those lives on disk.
    """

    exchange_dir: Path
    """Root folder for this run's exchange directory."""
    inputs_dir: Path
    """Folder under which each input port's files are written."""
    outputs_dir: Path
    """Folder under which each output port's files are expected."""
    manifest_path: Path
    """Path to the JSON manifest describing this run's ports and files."""
    logs_dir: Path
    """Folder for run logs."""
    temp_dir: Path
    """Folder for scratch files created during the run."""


@provisional(since="0.3.1")
@dataclass(frozen=True, kw_only=True)
class ExchangeFileRecord:
    """One file in the manifest: a written input or a discovered output.

    The manifest keeps one of these per file so a run can be traced after the
    fact: which port the file belongs to, where it is, what it holds, and
    whether it was written, collected, or ignored.
    """

    port_name: str
    """The port this file belongs to."""
    direction: PortDirection
    """Whether the file is an ``"input"`` written or an ``"output"`` discovered."""
    path: Path
    """Path to the file on disk."""
    object_type: str
    """Name of the data type the file holds."""
    format_hint: str
    """File extension describing the on-disk format (with a leading dot)."""
    status: ManifestStatus
    """Lifecycle state of the file (for example written, collected, or ignored)."""
    capability_id: str | None = None
    """Optional identifier of the save/load handler used for this file."""
    warning: str | None = None
    """Human-readable note when the file was ignored or needs attention."""

    def to_dict(self) -> dict[str, str | None]:
        """Return this record as a JSON-serialisable dictionary."""
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


@provisional(since="0.3.1")
@dataclass(frozen=True, kw_only=True)
class ExchangeDiagnostic:
    """One warning or error raised while preparing or collecting exchange files.

    Examples: a required input had no value, a required output produced no file,
    or the script left an unexpected file in the outputs folder. The Code Block
    fails the run when any diagnostic has ``"error"`` severity.
    """

    severity: DiagnosticSeverity
    """How serious the issue is: ``"info"``, ``"warning"``, or ``"error"``."""
    code: str
    """Short machine-readable code identifying the kind of issue."""
    message: str
    """Human-readable explanation of the issue."""
    port_name: str | None = None
    """The port the issue relates to, if any."""
    path: Path | None = None
    """The file or folder the issue relates to, if any."""

    def to_dict(self) -> dict[str, str | None]:
        """Return this diagnostic as a JSON-serialisable dictionary."""
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "port_name": self.port_name,
            "path": str(self.path) if self.path is not None else None,
        }


@provisional(since="0.3.1")
@dataclass(kw_only=True)
class PortManifestRecord:
    """The manifest entry for one declared port and the files it gathered.

    Each declared input or output port has one of these in the manifest. It
    records the port's folder and expected data type, its current state, and the
    files written to or discovered in that folder.
    """

    name: str
    """Port name."""
    direction: PortDirection
    """Whether this is an ``"input"`` or ``"output"`` port."""
    object_type: str
    """Name of the data type the port carries."""
    folder: Path
    """Folder on disk holding this port's files."""
    format_hint: str
    """File extension describing the port's on-disk format (with a leading dot)."""
    capability_id: str | None
    """Optional identifier of the save/load handler used for this port."""
    required: bool
    """Whether the run fails if this port has no value (inputs) or file (outputs)."""
    status: ManifestStatus = "planned"
    """Current lifecycle state of the port (for example planned or collected)."""
    files: list[ExchangeFileRecord] = field(default_factory=list)
    """The files written to or discovered in this port's folder."""
    warnings: list[str] = field(default_factory=list)
    """Human-readable warnings accumulated for this port."""

    def to_dict(self) -> dict[str, object]:
        """Return this port record as a JSON-serialisable dictionary."""
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


@provisional(since="0.3.1")
@dataclass(kw_only=True)
class CodeBlockExchangeManifest:
    """The full record of one Code Block run's exchange: folders, ports, issues.

    The manifest ties together the run's folder layout, one record per declared
    port, and any warnings or errors. Ports are keyed by ``(direction, name)``
    so a block declaring an input and an output with the same name (such as
    ``data`` in and ``data`` out) keeps both. The :attr:`input_folders` and
    :attr:`output_folders` views are keyed by plain port name, which is unique
    within a single direction.
    """

    layout: CodeBlockExchangeLayout
    """The folder and file layout for this run."""
    ports: dict[tuple[PortDirection, str], PortManifestRecord]
    """Per-port records keyed by the ``(direction, name)`` pair."""
    diagnostics: list[ExchangeDiagnostic] = field(default_factory=list)
    """Warnings and errors accumulated across the run."""

    @property
    def input_folders(self) -> dict[str, Path]:
        """Map each input port name to its on-disk folder.

        Returns:
            A dictionary of input port name to folder path.
        """
        return {record.name: record.folder for record in self.ports.values() if record.direction == "input"}

    @property
    def output_folders(self) -> dict[str, Path]:
        """Map each output port name to its on-disk folder.

        Returns:
            A dictionary of output port name to folder path.
        """
        return {record.name: record.folder for record in self.ports.values() if record.direction == "output"}

    def to_dict(self) -> dict[str, object]:
        """Return the whole manifest as a JSON-serialisable dictionary."""
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
                f"{direction}:{name}": record.to_dict() for (direction, name), record in sorted(self.ports.items())
            },
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


@provisional(since="0.3.1")
@dataclass(frozen=True, kw_only=True)
class OutputDiscoveryResult:
    """What an output-folder scan found, before files are read back into objects.

    Returned by :func:`discover_declared_outputs`: the files matched for each
    output port and any issues (missing required outputs, extension mismatches,
    stray files) found while scanning.
    """

    files_by_port: dict[str, list[Path]]
    """The matched output files for each output port, keyed by port name."""
    diagnostics: list[ExchangeDiagnostic]
    """Warnings and errors found during the scan."""

    @property
    def has_errors(self) -> bool:
        """Whether any diagnostic is an error.

        Returns:
            ``True`` if at least one diagnostic has ``"error"`` severity.
        """
        return any(diagnostic.severity == "error" for diagnostic in self.diagnostics)


@provisional(since="0.3.1")
class CodeBlockExchangeError(RuntimeError):
    """Raised when preparing inputs or collecting outputs hits a blocking error.

    Carries the diagnostics that caused the failure (for example a required
    input with no value, or a required output the script never wrote).
    """

    def __init__(self, message: str, diagnostics: Sequence[ExchangeDiagnostic]) -> None:
        super().__init__(message)
        self.diagnostics = list(diagnostics)
        """The diagnostics that triggered this error."""


@provisional(since="0.3.1")
def normalise_extension(extension: str) -> str:
    """Clean up a file extension into a consistent ``.lowercase`` form.

    Trims whitespace, lowercases, and adds a leading dot if missing, so that
    ``"CSV"``, ``" .csv "``, and ``"csv"`` all become ``".csv"``.

    Args:
        extension: The raw extension, with or without a leading dot.

    Returns:
        The normalised extension, for example ``".csv"``.

    Raises:
        ValueError: If the extension is empty or contains a path separator.

    Example:
        >>> normalise_extension("CSV")
        '.csv'
    """

    stripped = extension.strip().lower()
    if not stripped:
        raise ValueError("Port extension must not be empty.")
    if not stripped.startswith("."):
        stripped = f".{stripped}"
    if "/" in stripped or "\\" in stripped:
        raise ValueError(f"Port extension must not contain path separators: {extension!r}")
    return stripped


@provisional(since="0.3.1")
def safe_exchange_name(value: str, *, fallback: str = "port") -> str:
    """Turn a free-form name into a single safe folder/file name component.

    Replaces characters that are not letters, digits, ``_``, ``.``, or ``-``
    with underscores and trims stray punctuation, so an arbitrary port name can
    be used as a folder name.

    Args:
        value: The name to sanitise.
        fallback: Name to use when *value* sanitises to nothing.

    Returns:
        A path-safe name, or *fallback* if nothing usable remains.

    Example:
        >>> safe_exchange_name("my port!")
        'my_port'
    """

    candidate = _SAFE_NAME_PATTERN.sub("_", value.strip()).strip("._-")
    if not candidate:
        return fallback
    return candidate


@provisional(since="0.3.1")
def create_codeblock_exchange_layout(
    exchange_root: Path,
    *,
    block_id: str,
    run_id: str,
    block_slug: str = "codeblock",
    create: bool = True,
) -> CodeBlockExchangeLayout:
    """Work out (and optionally create) the folders for one Code Block run.

    Builds a per-run folder under *exchange_root* named from the block and run
    identifiers, with ``inputs/``, ``outputs/``, ``logs/``, and ``tmp/``
    subfolders and a manifest path.

    Args:
        exchange_root: Root folder that holds all runs' exchange directories.
        block_id: Identifier of the block instance, used in the folder name.
        run_id: Identifier of this run, used as the per-run subfolder name.
        block_slug: Short label prefixed to the block folder name.
        create: When ``True`` (the default), create the folders on disk; when
            ``False``, only compute the paths.

    Returns:
        The resolved :class:`CodeBlockExchangeLayout` for the run.
    """

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


@provisional(since="0.3.1")
def allocate_port_folder(parent: Path, port_name: str, used_names: set[str], *, create: bool = True) -> Path:
    """Choose a unique folder for one port under *parent*, avoiding collisions.

    Derives a safe folder name from the port name; if that name is already used
    or already exists on disk, it appends a suffix until it finds a free name,
    so two ports never share a folder.

    Args:
        parent: The ``inputs/`` or ``outputs/`` folder to create the port folder in.
        port_name: The port's name, used as the basis for the folder name.
        used_names: Folder names already taken; updated in place with the choice.
        create: When ``True`` (the default), create the folder on disk.

    Returns:
        The path of the allocated port folder.

    Raises:
        RuntimeError: If no free folder name can be found.
    """

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


@provisional(since="0.3.1")
def plan_input_filenames(objects: Sequence[DataObject], *, extension: str) -> list[str]:
    """Pick a unique filename for each input object on one port.

    Names each file after its source (when known) or a numbered ``item_NNNN``
    stem otherwise, all sharing the given extension, and de-duplicates so no two
    objects collide.

    Args:
        objects: The data objects to be written to one input port, in order.
        extension: File extension for the files (with or without a leading dot).

    Returns:
        One filename per object, in the same order.
    """

    ext = normalise_extension(extension)
    used: set[str] = set()
    planned: list[str] = []
    for index, obj in enumerate(objects, start=1):
        stem = _source_stem(obj, ext) or f"item_{index:04d}"
        planned.append(_dedupe_filename(stem, ext, used))
    return planned


@provisional(since="0.3.1")
def initialise_exchange_manifest(
    port_configs: Sequence[CodeBlockExchangePort],
    *,
    layout: CodeBlockExchangeLayout,
) -> CodeBlockExchangeManifest:
    """Create a folder for every declared port and return a starting manifest.

    Allocates one folder per port under the inputs or outputs directory and
    records each as a planned port in a fresh manifest, ready for inputs to be
    written and outputs to be collected.

    Args:
        port_configs: The declared input and output ports for the run.
        layout: The run's folder layout.

    Returns:
        A manifest with one ``"folder_created"`` record per port and no files yet.
    """

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


@provisional(since="0.3.1")
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
    """Lay out the run's folders and write the declared inputs to files.

    Creates the exchange folders, then, for each declared input port, writes its
    value(s) to files using *materialise_adapter*. A required input with no value
    records an error diagnostic; an optional one records a warning.

    Args:
        inputs: Input values keyed by input-port name.
        port_configs: The declared input and output ports for the run.
        exchange_root: Root folder that holds all runs' exchange directories.
        block_id: Identifier of the block instance.
        run_id: Identifier of this run.
        materialise_adapter: Function that writes one data object to a file.
        block_slug: Short label prefixed to the block folder name.

    Returns:
        The manifest after inputs are written, including any input diagnostics.
    """

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


@provisional(since="0.3.1")
def discover_declared_outputs(
    port_configs: Sequence[CodeBlockExchangePort],
    *,
    manifest: CodeBlockExchangeManifest,
) -> OutputDiscoveryResult:
    """Scan the output folders for the files the script wrote.

    For each output port, lists the files whose extension matches the declared
    one. Files with the wrong extension are ignored with a warning; a required
    port that produced no matching file records an error; stray files or folders
    directly under ``outputs/`` are noted as warnings. The manifest is updated
    in place with the files and diagnostics found.

    Args:
        port_configs: The declared input and output ports for the run.
        manifest: The run manifest, updated in place with discovered files.

    Returns:
        The matched files per output port together with the scan diagnostics.
    """

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


@provisional(since="0.3.1")
def collect_codeblock_outputs(
    port_configs: Sequence[CodeBlockExchangePort],
    *,
    manifest: CodeBlockExchangeManifest,
    reconstruct_adapter: ReconstructAdapter,
) -> dict[str, Collection]:
    """Read the script's output files back into typed collections.

    Scans the output folders, then reads each matched file into a data object
    with *reconstruct_adapter* and groups them into one collection per output
    port. Fails if the scan found any blocking error (such as a missing required
    output).

    Args:
        port_configs: The declared input and output ports for the run.
        manifest: The run manifest, updated in place during discovery.
        reconstruct_adapter: Function that reads one file into a data object.

    Returns:
        A mapping from each output-port name to its collection of data objects.

    Raises:
        CodeBlockExchangeError: If output discovery reports a blocking error.
    """

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
