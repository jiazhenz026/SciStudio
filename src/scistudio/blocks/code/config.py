"""Configuration models for the Code Block.

The Code Block runs a project-local script that exchanges data through files.
This module defines the settings that are saved with a Code Block: which script
to run, how to choose an interpreter, where the exchange folder lives, and the
input and output ports the script reads and writes. These are plain data models;
they validate configuration but do not run any script.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scistudio.stability import provisional

PortDirection = Literal["input", "output"]
InterpreterMode = Literal["auto", "existing"]
ExchangeDirectoryPolicy = Literal["project", "custom"]


@provisional(since="0.3.1")
class CodeBlockConfigError(ValueError):
    """Raised when a Code Block configuration is invalid.

    Examples: pasted inline code where a script path is required, an entry
    function that the Code Block does not call, a script or folder path that
    escapes the project directory, or ``interpreter_mode="existing"`` without an
    ``interpreter_path``.
    """


@provisional(since="0.3.1")
class PortFileConfig(BaseModel):
    """How one Code Block port maps a named input or output to files on disk.

    A Code Block script does not pass data by argument; it reads and writes
    files. Each declared port says what kind of data it carries, what file
    extension to use, and which folder under the exchange directory to read from
    or write to. One ``PortFileConfig`` describes a single input or output port.

    Example:
        >>> PortFileConfig(
        ...     name="spectra",
        ...     direction="input",
        ...     data_type="DataFrame",
        ...     extension="csv",
        ... ).exchange_folder
        'inputs/spectra/'
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    """Port name, matching the input/output port the script reads or writes."""
    direction: PortDirection
    """Whether this port is an ``"input"`` the script reads or an ``"output"`` it writes."""
    data_type: str
    """Name of the data type carried, for example ``"DataFrame"`` or ``"Array"``."""
    extension: str
    """File extension for this port's files; a leading dot is added if omitted."""
    capability_id: str | None = None
    """Optional identifier pinning which save/load handler converts the files."""
    required: bool = True
    """Whether the run fails if this port has no value (inputs) or file (outputs)."""
    exchange_folder: str | None = None
    """Folder under the exchange directory for this port; defaults from name and direction."""

    @field_validator("name", "data_type")
    @classmethod
    def _non_empty_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("extension")
    @classmethod
    def _normalize_extension(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("extension must not be empty")
        if not value.startswith("."):
            value = f".{value}"
        return value

    @field_validator("exchange_folder")
    @classmethod
    def _normalize_exchange_folder(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\\", "/").strip()
        if not normalized:
            raise ValueError("exchange_folder must not be empty")
        return normalized.rstrip("/") + "/"

    @model_validator(mode="after")
    def _default_exchange_folder(self) -> PortFileConfig:
        if self.exchange_folder is None:
            self.exchange_folder = f"{'inputs' if self.direction == 'input' else 'outputs'}/{self.name}/"
        return self


class MigrationDiagnostic(BaseModel):
    """Explicit diagnostic for legacy inline/function CodeBlock configs.

    Internal (ADR-052 §7A): legacy-config migration diagnostic model; not part
    of the public ``scistudio.blocks.code`` surface.
    """

    model_config = ConfigDict(extra="forbid")

    legacy_mode: str
    severity: Literal["warning", "error"]
    message: str
    suggested_target: str
    reference: str = "ADR-041 Section 3.3"


@provisional(since="0.3.1")
class CodeBlockConfig(BaseModel):
    """The saved settings for one Code Block: script, interpreter, and ports.

    This is the full set of fields a Code Block stores. The only required field
    is ``script_path``; the rest have sensible defaults. The ``inputs`` and
    ``outputs`` lists declare the file-exchange ports the script reads and
    writes (see :class:`PortFileConfig`).

    The ``code`` and ``inline_code`` fields are accepted only so an old
    inline-code configuration fails with a clear migration message instead of an
    opaque "unexpected field" error.

    Example:
        >>> config = CodeBlockConfig(
        ...     script_path="scripts/analyse.py",
        ...     outputs=[
        ...         PortFileConfig(
        ...             name="result", direction="output",
        ...             data_type="DataFrame", extension="csv",
        ...         )
        ...     ],
        ... )
        >>> config.interpreter_mode
        'auto'
    """

    model_config = ConfigDict(extra="forbid")

    script_path: str
    """Project-local path to the script to run, relative to the project root."""
    code: str | None = None
    """Old inline-code field; accepted only to raise a clear migration error."""
    inline_code: str | None = None
    """Old inline-code field; accepted only to raise a clear migration error."""
    entry_function: str | None = None
    """Old entry-function name; accepted only to raise a clear migration error."""
    working_directory: str = "."
    """Directory the script launches from, relative to the project root (default: root)."""
    interpreter_mode: InterpreterMode = "auto"
    """``"auto"`` to detect an interpreter, or ``"existing"`` to require ``interpreter_path``."""
    interpreter_path: str | None = None
    """Explicit path to the interpreter executable; required when mode is ``"existing"``."""
    environment: Mapping[str, Any] = Field(default_factory=dict)
    """Extra interpreter hints (for example a language-specific executable path)."""
    environment_variables: dict[str, str] = Field(default_factory=dict)
    """Environment variables to set for the script process; keys and values are coerced to strings."""
    timeout_seconds: float | None = Field(default=None, gt=0)
    """Wall-clock time limit in seconds, or ``None`` for no limit (must be positive)."""
    exchange_directory_policy: ExchangeDirectoryPolicy = "project"
    """Whether exchange folders live under the project (``"project"``) or a custom root."""
    exchange_root: str = "exchange"
    """Folder under the project root that holds per-run exchange directories."""
    inputs: list[PortFileConfig] = Field(default_factory=list)
    """Declared input ports the script reads from files."""
    outputs: list[PortFileConfig] = Field(default_factory=list)
    """Declared output ports the script writes as files."""

    @field_validator("script_path", "working_directory", "exchange_root")
    @classmethod
    def _non_empty_pathlike(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("path-like value must not be empty")
        return value

    @field_validator("environment_variables")
    @classmethod
    def _stringify_environment(cls, value: dict[str, str]) -> dict[str, str]:
        return {str(key): str(env_value) for key, env_value in value.items()}

    @model_validator(mode="after")
    def _reject_legacy_inline_or_function_mode(self) -> CodeBlockConfig:
        if self.code or self.inline_code:
            raise CodeBlockConfigError(
                "CodeBlock v2 does not support inline code; save code as a project-local script "
                "or migrate framework-shaped logic to a ProcessBlock/custom block."
            )
        if self.entry_function:
            raise CodeBlockConfigError(
                "CodeBlock v2 does not call SciStudio entry functions; scripts must use file exchange."
            )
        if self.interpreter_mode == "existing" and not self.interpreter_path:
            raise CodeBlockConfigError("interpreter_mode='existing' requires interpreter_path")
        return self

    def resolve_script_path(self, project_dir: Path) -> Path:
        """Resolve ``script_path`` to an absolute path inside the project.

        Args:
            project_dir: Absolute path to the project root.

        Returns:
            The absolute path to the script file.

        Raises:
            CodeBlockConfigError: If the path resolves outside the project, or
                is not a file.
            FileNotFoundError: If the script does not exist.
        """

        return resolve_project_path(self.script_path, project_dir=project_dir, field_name="script_path")

    def resolve_working_directory(self, project_dir: Path) -> Path:
        """Resolve ``working_directory`` to an absolute path inside the project.

        The directory need not exist yet (the script launcher checks that).

        Args:
            project_dir: Absolute path to the project root.

        Returns:
            The absolute working directory the script will launch from.

        Raises:
            CodeBlockConfigError: If the path resolves outside the project, or
                points at an existing file rather than a directory.
        """

        return resolve_project_path(
            self.working_directory,
            project_dir=project_dir,
            field_name="working_directory",
            must_exist=False,
            allow_file=False,
        )

    def resolve_exchange_root(self, project_dir: Path) -> Path:
        """Resolve ``exchange_root`` to an absolute path inside the project.

        The directory need not exist yet; it is created per run.

        Args:
            project_dir: Absolute path to the project root.

        Returns:
            The absolute exchange root that holds per-run exchange folders.

        Raises:
            CodeBlockConfigError: If the path resolves outside the project, or
                points at an existing file rather than a directory.
        """

        return resolve_project_path(
            self.exchange_root,
            project_dir=project_dir,
            field_name="exchange_root",
            must_exist=False,
            allow_file=False,
        )


def resolve_project_path(
    raw_path: str | Path,
    *,
    project_dir: Path,
    field_name: str,
    must_exist: bool = True,
    allow_file: bool = True,
) -> Path:
    """Resolve *raw_path* and require it to stay inside *project_dir*.

    Internal (ADR-052 §7A): path-resolution helper, not part of the public
    ``scistudio.blocks.code`` surface.


    The check resolves symlinks before comparing paths, matching ADR-041's
    project-local source requirement without scanning the project tree.
    """

    project_root = project_dir.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve(strict=must_exist)
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise CodeBlockConfigError(f"{field_name} must resolve inside the project directory") from exc
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"{field_name} does not exist: {raw_path}")
    if not allow_file and resolved.exists() and not resolved.is_dir():
        raise CodeBlockConfigError(f"{field_name} must be a directory")
    if allow_file and must_exist and not resolved.is_file():
        raise CodeBlockConfigError(f"{field_name} must be a file")
    return resolved


def legacy_migration_diagnostics(config: Mapping[str, Any]) -> list[MigrationDiagnostic]:
    """Classify legacy CodeBlock config fields without mutating the config.

    Internal (ADR-052 §7A): legacy-config migration tooling, not public surface.
    """

    diagnostics: list[MigrationDiagnostic] = []
    mode = str(config.get("mode", "")).strip().lower()
    has_inline = bool(config.get("code") or config.get("inline_code") or config.get("script"))
    has_entry = bool(config.get("entry_function"))
    if mode == "inline" or has_inline:
        diagnostics.append(
            MigrationDiagnostic(
                legacy_mode=mode or "inline",
                severity="error",
                message="Inline CodeBlock configs are not valid CodeBlock v2 configs.",
                suggested_target="Save the code as a project-local script, or use ProcessBlock/custom block authoring.",
            )
        )
    if has_entry:
        diagnostics.append(
            MigrationDiagnostic(
                legacy_mode=mode or "script",
                severity="error",
                message="Entry-function script configs are framework-shaped legacy CodeBlock configs.",
                suggested_target="Adapt the script to ADR-041 file exchange or keep the logic in a ProcessBlock.",
            )
        )
    return diagnostics
