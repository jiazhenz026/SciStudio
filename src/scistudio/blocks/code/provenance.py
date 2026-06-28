"""Capturing what ran: provenance records for a Code Block run.

These helpers record enough to reproduce and trust a run: the exact script
(its content hash and git state), the interpreter and environment used, and
timing. The Code Block stores the resulting payload alongside the run's outputs.
"""

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
from scistudio.stability import provisional

GitStatus = Literal["tracked-clean", "tracked-modified", "untracked"]


@provisional(since="0.3.1")
class ScriptProvenance(BaseModel):
    """Identity of the exact script that ran, for reproducibility.

    Records where the script is, a content hash so you can tell if it changed,
    its git state, and basic file metadata.
    """

    model_config = ConfigDict(extra="forbid")

    relative_path: str
    """Script path relative to the project root."""
    resolved_path: str
    """Absolute path to the script."""
    content_sha256: str
    """SHA-256 hash of the script's contents, to detect changes."""
    git_commit: str | None = None
    """Commit hash of the project, or ``None`` if it is not a git repository."""
    git_status: GitStatus
    """Whether the script is tracked and clean, tracked and modified, or untracked."""
    size_bytes: int
    """Script size in bytes."""
    mtime_ns: int
    """Script last-modified time, in nanoseconds since the epoch."""


@provisional(since="0.3.1")
class EnvironmentSnapshot(BaseModel):
    """Best-effort record of the interpreter and environment a script ran in.

    Captures which interpreter was used and how it was chosen, so a run can be
    understood and re-created afterwards.
    """

    model_config = ConfigDict(extra="forbid")

    mode: InterpreterMode
    """How the interpreter was chosen: ``"auto"`` or ``"existing"``."""
    interpreter_path: str
    """Path to the interpreter executable that ran the script."""
    version: str | None = None
    """The interpreter's reported version, or ``None`` if it could not be read."""
    environment_delta: dict[str, str] = Field(default_factory=dict)
    """Environment variable overrides applied for the run, sorted by name."""
    warnings: list[str] = Field(default_factory=list)
    """Non-fatal notes gathered while resolving the interpreter."""


@provisional(since="0.3.1")
class CodeBlockProvenancePayload(BaseModel):
    """The complete provenance record stored for one Code Block run.

    Bundles the script identity, interpreter and environment snapshot, timing,
    the file-format handlers used per port, and the exchange manifest into one
    record kept with the run's lineage.
    """

    model_config = ConfigDict(extra="forbid")

    script: ScriptProvenance
    """Identity of the script that ran."""
    interpreter: ResolvedInterpreter
    """The resolved interpreter command used for the run."""
    environment: EnvironmentSnapshot
    """Snapshot of the interpreter and environment."""
    started_at: str
    """Run start time as a UTC timestamp string."""
    completed_at: str | None = None
    """Run completion time as a UTC timestamp string, or ``None`` if unfinished."""
    selected_capabilities: dict[str, str] = Field(default_factory=dict)
    """The save/load handler chosen per port, keyed by ``direction:port``."""
    exchange_manifest: dict[str, Any] = Field(default_factory=dict)
    """The run's exchange manifest as a plain dictionary."""


@provisional(since="0.3.1")
def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with second precision.

    Returns:
        A timestamp such as ``"2026-06-28T12:00:00Z"``.
    """

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@provisional(since="0.3.1")
def capture_script_provenance(script_path: Path, *, project_dir: Path) -> ScriptProvenance:
    """Record a script's identity: its content hash, git state, and metadata.

    Args:
        script_path: Path to the script that ran.
        project_dir: Absolute path to the project root.

    Returns:
        A :class:`ScriptProvenance` describing the script.
    """

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


@provisional(since="0.3.1")
def capture_environment_snapshot(
    resolved_interpreter: ResolvedInterpreter,
    *,
    mode: InterpreterMode,
    environment_delta: Mapping[str, str] | None = None,
) -> EnvironmentSnapshot:
    """Build an environment snapshot from a resolved interpreter.

    Args:
        resolved_interpreter: The interpreter command chosen for the run.
        mode: How the interpreter was chosen (``"auto"`` or ``"existing"``).
        environment_delta: Environment overrides to record; falls back to the
            interpreter's own environment when omitted.

    Returns:
        An :class:`EnvironmentSnapshot` for the run.
    """

    delta = dict(environment_delta or resolved_interpreter.environment)
    return EnvironmentSnapshot(
        mode=mode,
        interpreter_path=resolved_interpreter.executable,
        version=resolved_interpreter.version,
        environment_delta={str(key): str(value) for key, value in sorted(delta.items())},
        warnings=list(resolved_interpreter.warnings),
    )


@provisional(since="0.3.1")
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
    """Assemble the full provenance record for a run as a JSON-ready dictionary.

    Args:
        script: Identity of the script that ran.
        interpreter: The resolved interpreter command used.
        environment: Snapshot of the interpreter and environment.
        started_at: Run start time as a UTC timestamp string.
        completed_at: Run completion time, or ``None`` if it did not finish.
        selected_capabilities: The save/load handler chosen per port.
        exchange_manifest: The run's exchange manifest as a dictionary.

    Returns:
        The provenance payload as a JSON-serialisable dictionary.
    """

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
