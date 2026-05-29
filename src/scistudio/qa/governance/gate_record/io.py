"""Disk I/O, git observation, discovery, session state, and sanitization.

APPEND-ONLY semantics (Addendum 6 §7.2): writers never overwrite or delete
prior events; corrections are new events. The legacy overwrite mutators
(``_write_record``/``_mark_stage``/``_upsert_check``) are gone.

Session state lives under ``.git/scistudio/gates/`` (local, never committed).
Raw transcripts live under ``.workflow/local/**`` (gitignored). The committed
ledger is sanitized by :func:`sanitize_ledger` before write (§8).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from scistudio.qa.governance.gate_record.ledger import GateLedger
from scistudio.qa.governance.gate_record.surfaces import SLUG_RE, normalize_path

RECORDS_DIR = ".workflow/records"
LOCAL_LOGS_DIR = ".workflow/local/logs"


class SanitizationError(ValueError):
    """Raised when a would-be-committed ledger event leaks local details."""


# ---------------------------------------------------------------------------
# Ledger read / append-only write.
# ---------------------------------------------------------------------------


def load_ledger(record: GateLedger | Mapping[str, Any] | str | Path) -> GateLedger:
    """Load a ledger from a model, mapping, or JSON file path."""

    if isinstance(record, GateLedger):
        return record
    if isinstance(record, Mapping):
        return cast(GateLedger, GateLedger.model_validate(record))
    path = Path(record)
    return cast(GateLedger, GateLedger.model_validate_json(path.read_text(encoding="utf-8")))


def write_ledger(path: Path, ledger: GateLedger, *, repo_root: Path | None = None) -> Path:
    """Sanitize then write the ledger as deterministic JSON.

    This is the only write path. Callers mutate the in-memory ledger by
    APPENDING events (never replacing prior events) and then call this once.
    """

    sanitize_ledger(ledger, repo_root=repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = ledger.model_dump(mode="json", by_alias=True, exclude_none=False)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _slugify(value: str) -> str:
    slug = SLUG_RE.sub("-", value.lower()).strip("-")
    return slug or "task"


def record_path(
    repo_root: Path,
    *,
    issue_number: int | None,
    branch: str,
    slug: str,
    explicit: Path | None,
) -> Path:
    """Resolve the generated ledger path (§5.2).

    Prefer ``<issue>-<slug>.json`` when an issue is known; otherwise
    ``<branch-slug>-<slug>.json``.
    """

    if explicit is not None:
        return explicit if explicit.is_absolute() else repo_root / explicit
    safe_slug = _slugify(slug)
    name = f"{issue_number}-{safe_slug}.json" if issue_number is not None else f"{_slugify(branch)}-{safe_slug}.json"
    return repo_root / RECORDS_DIR / name


# ---------------------------------------------------------------------------
# Local session state under .git/scistudio/gates/.
# ---------------------------------------------------------------------------


def _git_dir(repo_root: Path) -> Path:
    try:
        out = _git_output(repo_root, ["rev-parse", "--git-dir"]).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return repo_root / ".git"
    git_dir = Path(out)
    return git_dir if git_dir.is_absolute() else repo_root / git_dir


def session_state_dir(repo_root: Path) -> Path:
    """Return the local session-state directory (created on demand)."""

    return _git_dir(repo_root) / "scistudio" / "gates"


def new_session_id() -> str:
    """Generate a local session identifier."""

    return str(uuid.uuid4())


def write_session_state(repo_root: Path, session_id: str, state: Mapping[str, Any]) -> Path:
    """Persist local session state (never committed)."""

    directory = session_state_dir(repo_root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.json"
    path.write_text(json.dumps(dict(state), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Git observation helpers.
# ---------------------------------------------------------------------------


def _git_output(repo_root: Path, args: list[str]) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stderr=subprocess.DEVNULL,
    )


def git_lines(repo_root: Path, args: list[str]) -> list[str]:
    """Run a git command, returning normalized non-empty output lines."""

    output = _git_output(repo_root, args)
    return [normalize_path(line) for line in output.splitlines() if line.strip()]


def resolve_sha(repo_root: Path, ref: str) -> str | None:
    """Resolve ``ref`` to a short SHA, or None when unresolvable."""

    try:
        return _git_output(repo_root, ["rev-parse", "--short", ref]).strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def changed_files(repo_root: Path, base: str, head: str, *, staged: bool = False) -> list[str]:
    """Return the observed changed-file set from git (the evidence, §3.3.1)."""

    if staged:
        try:
            return git_lines(repo_root, ["diff", "--name-only", "--cached"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []
    try:
        return git_lines(repo_root, ["diff", "--name-only", f"{base}...{head}"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fall back to a two-dot diff when the merge-base form fails (e.g. no
        # common ancestor on a shallow clone).
        try:
            return git_lines(repo_root, ["diff", "--name-only", base, head])
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []


def diff_fingerprint(repo_root: Path, base: str, head: str, *, staged: bool = False) -> str | None:
    """Return a deterministic sha256 fingerprint of the diff content."""

    args = ["diff", "--cached"] if staged else ["diff", f"{base}...{head}"]
    try:
        content = _git_output(repo_root, args)
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            content = _git_output(repo_root, ["diff", base, head])
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
    digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
    return f"sha256:{digest}"


def fingerprint_paths(paths: Sequence[str]) -> str:
    """Return a stable fingerprint of a sorted path list (covered surface)."""

    joined = "\n".join(sorted(normalize_path(p) for p in paths))
    return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Deterministic ledger discovery (§5.1).
# ---------------------------------------------------------------------------


class DiscoveryResult:
    """Outcome of branch-based ledger discovery."""

    def __init__(self, path: Path | None, candidates: list[Path]):
        self.path = path
        self.candidates = candidates

    @property
    def found(self) -> bool:
        return self.path is not None

    @property
    def ambiguous(self) -> bool:
        return self.path is None and len(self.candidates) > 1


def _ledger_branch(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        value = data.get("branch")
        return value if isinstance(value, str) else None
    return None


def current_branch(repo_root: Path) -> str | None:
    """Return the current git branch, or None when detached/unavailable."""

    try:
        branch = _git_output(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return branch or None


def discover_ledger(repo_root: Path, *, branch: str | None = None) -> DiscoveryResult:
    """Discover the active ledger for ``branch`` (§5.1).

    Exactly one match -> accepted. Zero -> caller prints "run init". Multiple ->
    caller lists candidates and asks for ``--record``. The single canonical
    discovery used by every command and the worktree write guard.
    """

    records_dir = repo_root / RECORDS_DIR
    records = sorted(records_dir.glob("*.json")) if records_dir.exists() else []
    if not records:
        return DiscoveryResult(None, [])

    target_branch = branch if branch is not None else current_branch(repo_root)
    if target_branch is not None:
        matches = [path for path in records if _ledger_branch(path) == target_branch]
        if len(matches) == 1:
            return DiscoveryResult(matches[0], matches)
        if len(matches) > 1:
            return DiscoveryResult(None, matches)

    # No branch match: accept a lone record, otherwise report ambiguity.
    if len(records) == 1:
        return DiscoveryResult(records[0], records)
    return DiscoveryResult(None, records)


# ---------------------------------------------------------------------------
# CLI value parsing helpers (ported from legacy io.py).
# ---------------------------------------------------------------------------


def parse_issue_numbers(values: Sequence[str]) -> list[int]:
    """Parse ``N`` or ``#N`` issue tokens into integers."""

    numbers: list[int] = []
    for value in values:
        match = re.fullmatch(r"#?(\d+)", value.strip())
        if match is None:
            raise ValueError(f"expected issue number or #N item: {value}")
        numbers.append(int(match.group(1)))
    return numbers


def parse_class_rationale(value: str) -> tuple[str, str]:
    """Parse a ``<class>:<rationale>`` N/A argument."""

    if ":" not in value:
        raise ValueError(f"expected <class>:<rationale>, got: {value}")
    cls, rationale = value.split(":", 1)
    return cls.strip(), rationale.strip()


# ---------------------------------------------------------------------------
# Sanitization (§8). A violation is exit code 5.
# ---------------------------------------------------------------------------

# Patterns that must never appear in a committed ledger event.
_ABS_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/])|(?:^/(?:home|Users|root|tmp|var|mnt)/)|(?:/home/)|(?:/Users/)")
_HOME_RE = re.compile(r"(?:~/)|(?:\$HOME)|(?:%USERPROFILE%)|(?:\bC:\\Users\\)")
_VENV_RE = re.compile(r"(?:site-packages)|(?:\.venv)|(?:virtualenvs)|(?:[\\/]venv[\\/])")


def _scan_value(value: Any, path: str, violations: list[str]) -> None:
    if isinstance(value, str):
        if _ABS_PATH_RE.search(value):
            violations.append(f"{path}: absolute local path")
        if _HOME_RE.search(value):
            violations.append(f"{path}: home/user directory reference")
        if _VENV_RE.search(value):
            violations.append(f"{path}: virtualenv/dependency-cache path")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _scan_value(item, f"{path}.{key}", violations)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_value(item, f"{path}[{index}]", violations)


def sanitize_ledger(ledger: GateLedger, *, repo_root: Path | None = None) -> None:
    """Validate that the ledger carries no forbidden local-machine details (§8).

    Raises :class:`SanitizationError` on any violation. The serialized payload
    is scanned for absolute paths, home/venv references, and the like. Raw
    transcripts are referenced only via ``raw_log_ref`` under
    ``.workflow/local/**``; the ref itself must be repo-relative.
    """

    payload = ledger.model_dump(mode="json", by_alias=True)
    violations: list[str] = []
    _scan_value(payload, "ledger", violations)
    # raw_log_ref must point under .workflow/local/ and be repo-relative.
    for index, event in enumerate(ledger.check_events):
        ref = event.raw_log_ref
        if ref and not normalize_path(ref).startswith(".workflow/local/"):
            violations.append(f"ledger.check_events[{index}].raw_log_ref: must live under .workflow/local/")
    if violations:
        raise SanitizationError("; ".join(sorted(set(violations))))
