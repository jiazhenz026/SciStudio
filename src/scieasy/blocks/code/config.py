"""CodeBlock v2 configuration models.

ADR-041 narrows CodeBlock v2 to project-local scripts that exchange data
through files.  This module defines the small persisted config surface used by
later runtime integration tracks; it intentionally does not execute scripts.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PortDirection = Literal["input", "output"]
InterpreterMode = Literal["auto", "existing"]
ExchangeDirectoryPolicy = Literal["project", "custom"]


class CodeBlockConfigError(ValueError):
    """Raised when a CodeBlock v2 config violates ADR-041 constraints."""


class PortFileConfig(BaseModel):
    """File-exchange contract for one CodeBlock v2 port."""

    model_config = ConfigDict(extra="forbid")

    name: str
    direction: PortDirection
    data_type: str
    extension: str
    capability_id: str | None = None
    required: bool = True
    exchange_folder: str | None = None

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
    """Explicit diagnostic for legacy inline/function CodeBlock configs."""

    model_config = ConfigDict(extra="forbid")

    legacy_mode: str
    severity: Literal["warning", "error"]
    message: str
    suggested_target: str
    reference: str = "ADR-041 Section 3.3"


class CodeBlockConfig(BaseModel):
    """Persisted CodeBlock v2 script configuration.

    ``code`` and ``inline_code`` are accepted only so legacy/mixed configs can
    fail with an explicit migration error instead of an opaque extra-field
    failure.
    """

    model_config = ConfigDict(extra="forbid")

    script_path: str
    code: str | None = None
    inline_code: str | None = None
    entry_function: str | None = None
    working_directory: str = "."
    interpreter_mode: InterpreterMode = "auto"
    interpreter_path: str | None = None
    environment: Mapping[str, Any] = Field(default_factory=dict)
    environment_variables: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0)
    exchange_directory_policy: ExchangeDirectoryPolicy = "project"
    exchange_root: str = "exchange"
    inputs: list[PortFileConfig] = Field(default_factory=list)
    outputs: list[PortFileConfig] = Field(default_factory=list)

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
                "CodeBlock v2 does not call SciEasy entry functions; scripts must use file exchange."
            )
        if self.interpreter_mode == "existing" and not self.interpreter_path:
            raise CodeBlockConfigError("interpreter_mode='existing' requires interpreter_path")
        return self

    def resolve_script_path(self, project_dir: Path) -> Path:
        """Return the validated project-local script path."""

        return resolve_project_path(self.script_path, project_dir=project_dir, field_name="script_path")

    def resolve_working_directory(self, project_dir: Path) -> Path:
        """Return the project-local working directory for interpreter launch."""

        return resolve_project_path(
            self.working_directory,
            project_dir=project_dir,
            field_name="working_directory",
            must_exist=False,
            allow_file=False,
        )

    def resolve_exchange_root(self, project_dir: Path) -> Path:
        """Return the project-local exchange root."""

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
    """Classify legacy CodeBlock config fields without mutating the config."""

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
