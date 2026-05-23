"""Disk I/O, git helpers, and record-discovery for ADR-042 gate records.

Read/write helpers, slug/path resolution, the git-diff shell-out, and the
sub-PR vs umbrella-PR record discovery heuristic live here. Kept separate
from validation so that a CLI subcommand that only needs to *update* a
record (``plan``, ``check``, ``docs``, ``sentrux``, ``finalize``) can do so
without importing the AuditReport-based validation path.

Issue #1498 adds the provenance audit log:
``_record_mutation`` is invoked by every mutator in :mod:`stages` before
``_write_record`` writes the file. The provenance ``head_content_hash`` is
the sha256 of the record JSON minus the ``provenance`` field; validators
recompute this hash to detect direct JSON edits that bypassed the CLI.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from scistudio.qa.governance.gate_record.models import (
    CheckEvidence,
    GateRecord,
    GateStage,
    Mutation,
    Provenance,
)
from scistudio.qa.governance.gate_record.paths import (
    SLUG_RE,
    _match_path,
    _normalize_path,
)


def _tool_version() -> str:
    """Return ``scistudio.qa.governance.gate_record/<pkg-version>``.

    Falls back to ``dev`` when the package is not installed (e.g., running
    from a source checkout without ``pip install``).
    """

    try:
        return f"scistudio.qa.governance.gate_record/{version('scistudio')}"
    except PackageNotFoundError:
        return "scistudio.qa.governance.gate_record/dev"


def _record_content_hash(record: GateRecord) -> str:
    """Return sha256 of canonical record JSON minus the provenance field.

    The provenance field is excluded so that updating ``head_content_hash``
    itself does not invalidate the hash (avoids a self-referential loop).
    """

    payload = record.model_dump(mode="json", exclude_none=False)
    payload.pop("provenance", None)
    canonical = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_mutation(
    record: GateRecord,
    *,
    subcommand: str,
    summary: Mapping[str, Any] | None = None,
) -> None:
    """Append a Mutation entry to ``record.provenance`` and update head hash.

    Mutates ``record`` in place. Callers must invoke this *before*
    ``_write_record`` so the persisted JSON includes the new mutation row.
    """

    previous_hash = record.provenance.head_content_hash if record.provenance else None
    new_hash = _record_content_hash(record)
    mutation = Mutation(
        timestamp=datetime.now(UTC),
        tool_version=_tool_version(),
        subcommand=subcommand,
        summary=dict(summary) if summary else {},
        content_hash_before=previous_hash,
        content_hash_after=new_hash,
    )
    if record.provenance is None:
        record.provenance = Provenance(mutations=[mutation], head_content_hash=new_hash)
    else:
        record.provenance.mutations.append(mutation)
        record.provenance.head_content_hash = new_hash


def verify_provenance_hash(record: GateRecord) -> tuple[bool, str]:
    """Verify ``record.provenance.head_content_hash`` matches current content.

    Returns ``(is_valid, computed_hash)``. ``is_valid`` is:
    - ``True`` when ``record.provenance is None`` (backward-compatible for
      pre-Issue-#1498 records, which loaded without a provenance field).
    - ``True`` when the stored ``head_content_hash`` equals
      ``_record_content_hash(record)``.
    - ``False`` otherwise — the record's content was modified without going
      through a CLI mutator (direct JSON edit detected).
    """

    if record.provenance is None:
        return True, ""
    computed = _record_content_hash(record)
    return computed == record.provenance.head_content_hash, computed


def _load_record(record: GateRecord | Mapping[str, Any] | str | Path) -> GateRecord:
    if isinstance(record, GateRecord):
        return record
    if isinstance(record, Mapping):
        return cast(GateRecord, GateRecord.model_validate(record))
    path = Path(record)
    return cast(GateRecord, GateRecord.model_validate_json(path.read_text(encoding="utf-8")))


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
