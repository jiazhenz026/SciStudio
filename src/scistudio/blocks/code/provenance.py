"""Provenance helpers for CodeBlock v2 support modules."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from scistudio.blocks.code.config import InterpreterMode, resolve_project_path
from scistudio.blocks.code.interpreters import ResolvedInterpreter

GitStatus = Literal["tracked-clean", "tracked-modified", "untracked"]


class ScriptProvenance(BaseModel):
    """Source identity for a selected CodeBlock v2 script."""

    model_config = ConfigDict(extra="forbid")

    relative_path: str
    resolved_path: str
    content_sha256: str
    git_commit: str | None = None
    git_status: GitStatus
    size_bytes: int
    mtime_ns: int


class EnvironmentSnapshot(BaseModel):
    """Best-effort interpreter/environment reproducibility evidence."""

    model_config = ConfigDict(extra="forbid")

    mode: InterpreterMode
    interpreter_path: str
    version: str | None = None
    environment_delta: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CodeBlockProvenancePayload(BaseModel):
    """Stable lineage-owned payload for a CodeBlock v2 run."""

    model_config = ConfigDict(extra="forbid")

    script: ScriptProvenance
    interpreter: ResolvedInterpreter
    environment: EnvironmentSnapshot
    started_at: str
    completed_at: str | None = None
    selected_capabilities: dict[str, str] = Field(default_factory=dict)
    exchange_manifest: dict[str, Any] = Field(default_factory=dict)


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp with second precision."""

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def capture_script_provenance(script_path: Path, *, project_dir: Path) -> ScriptProvenance:
    """Capture project-local script hash and git evidence."""

    resolved_script = resolve_project_path(script_path, project_dir=project_dir, field_name="script_path")
    project_root = project_dir.resolve()
    relative_path = resolved_script.relative_to(project_root).as_posix()
    stat = resolved_script.stat()

    return ScriptProvenance(
        relative_path=relative_path,
        resolved_path=resolved_script.as_posix(),
        content_sha256=_sha256_file(resolved_script),
        git_commit=_git_commit(project_root),
        git_status=_git_status(project_root, relative_path),
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )


def capture_environment_snapshot(
    resolved_interpreter: ResolvedInterpreter,
    *,
    mode: InterpreterMode,
    environment_delta: Mapping[str, str] | None = None,
) -> EnvironmentSnapshot:
    """Build a stable environment snapshot from interpreter resolution."""

    delta = dict(environment_delta or resolved_interpreter.environment)
    return EnvironmentSnapshot(
        mode=mode,
        interpreter_path=resolved_interpreter.executable,
        version=resolved_interpreter.version,
        environment_delta={str(key): str(value) for key, value in sorted(delta.items())},
        warnings=list(resolved_interpreter.warnings),
    )


def build_codeblock_provenance_payload(
    *,
    script: ScriptProvenance,
    interpreter: ResolvedInterpreter,
    environment: EnvironmentSnapshot,
    started_at: str,
    completed_at: str | None = None,
    selected_capabilities: Mapping[str, str] | None = None,
    exchange_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a JSON-stable provenance payload for lineage storage."""

    payload = CodeBlockProvenancePayload(
        script=script,
        interpreter=interpreter,
        environment=environment,
        started_at=started_at,
        completed_at=completed_at,
        selected_capabilities=dict(sorted((selected_capabilities or {}).items())),
        exchange_manifest=dict(exchange_manifest or {}),
    )
    return payload.model_dump(mode="json")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(project_dir: Path) -> str | None:
    completed = _run_git(project_dir, "rev-parse", "HEAD")
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _git_status(project_dir: Path, relative_path: str) -> GitStatus:
    tracked = _run_git(project_dir, "ls-files", "--error-unmatch", "--", relative_path)
    if tracked.returncode != 0:
        return "untracked"
    status = _run_git(project_dir, "status", "--porcelain", "--", relative_path)
    if status.returncode != 0:
        return "tracked-modified"
    return "tracked-modified" if status.stdout.strip() else "tracked-clean"


def _run_git(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=project_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["git", *args], returncode=1, stdout="", stderr=str(exc))
