"""Disk I/O, git helpers, and record-discovery for ADR-042 gate records.

Read/write helpers, slug/path resolution, the git-diff shell-out, and the
sub-PR vs umbrella-PR record discovery heuristic live here. Kept separate
from validation so that a CLI subcommand that only needs to *update* a
record (``plan``, ``check``, ``docs``, ``sentrux``, ``finalize``) can do so
without importing the AuditReport-based validation path.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scistudio.qa.governance.gate_record.models import (
    CheckEvidence,
    GateRecord,
    GateStage,
)
from scistudio.qa.governance.gate_record.paths import (
    SLUG_RE,
    _match_path,
    _normalize_path,
)


def _load_record(record: GateRecord | Mapping[str, Any] | str | Path) -> GateRecord:
    if isinstance(record, GateRecord):
        return record
    if isinstance(record, Mapping):
        return GateRecord.model_validate(record)
    path = Path(record)
    return GateRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _slugify(value: str) -> str:
    slug = SLUG_RE.sub("-", value.lower()).strip("-")
    return slug or "task"


def _record_path(repo_root: Path, issue_number: int, slug: str, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit if explicit.is_absolute() else repo_root / explicit
    return repo_root / ".workflow" / "records" / f"{issue_number}-{_slugify(slug)}.json"


def _write_record(path: Path, record: GateRecord) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = record.model_dump(mode="json", exclude_none=False)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _mark_stage(record: GateRecord, stage: GateStage) -> None:
    for stage_evidence in record.stages:
        if stage_evidence.stage == stage:
            stage_evidence.status = "done"
            return


def _upsert_check(record: GateRecord, evidence: CheckEvidence) -> None:
    record.check_results = [check for check in record.check_results if check.name != evidence.name]
    record.check_results.append(evidence)


def _git_lines(repo_root: Path, args: list[str]) -> list[str]:
    output = subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL)
    return [_normalize_path(line) for line in output.splitlines() if line.strip()]


def _record_task_kind(path: Path) -> str | None:
    """Return the ``task_kind`` field of a gate record on disk, or ``None``.

    Tolerates malformed or missing files: callers fall back to the
    single-record path when this returns ``None``.
    """

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        value = data.get("task_kind")
        return value if isinstance(value, str) else None
    return None


def _discover_gate_record(repo_root: Path, changed_files: Sequence[str]) -> Path | None:
    """Resolve the gate record to validate against.

    The default case is a single PR with a single record under
    ``.workflow/records/``. Umbrella PRs (created by the manager persona)
    accumulate sub-PR records in their diff because each sub-PR merged into
    the umbrella brought its own record along; in that case the umbrella's
    own record carries ``task_kind: manager`` and the sub-PR records carry
    implementation task kinds. When exactly one manager record is present in
    the diff, treat that as the primary record and let the sub-PR records
    pass through as historical evidence (#1340).
    """

    record_paths = [path for path in changed_files if _match_path(path, ".workflow/records/*.json")]
    if len(record_paths) == 1:
        return repo_root / record_paths[0]
    if len(record_paths) > 1:
        manager_paths = [repo_root / path for path in record_paths if _record_task_kind(repo_root / path) == "manager"]
        if len(manager_paths) == 1:
            return manager_paths[0]
    records_dir = repo_root / ".workflow" / "records"
    records = sorted(records_dir.glob("*.json")) if records_dir.exists() else []
    return records[0] if len(records) == 1 else None


def _parse_key_values(values: Sequence[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in values:
        if "=" in item:
            key, value = item.split("=", 1)
        elif ":" in item:
            key, value = item.split(":", 1)
        else:
            raise ValueError(f"expected KEY=VALUE item: {item}")
        pairs.append((key.strip(), value.strip()))
    return pairs


def _parse_issue_numbers(values: Sequence[str]) -> list[int]:
    numbers: list[int] = []
    for value in values:
        match = re.fullmatch(r"#?(\d+)", value.strip())
        if match is None:
            raise ValueError(f"expected issue number or #N item: {value}")
        numbers.append(int(match.group(1)))
    return numbers
