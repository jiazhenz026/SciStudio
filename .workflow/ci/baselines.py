"""Read/write helpers for per-tool baseline files under ``docs/audit/baselines/``.

A baseline file captures the previous run's finding counts for a single tool.
The schema is intentionally minimal so the ratchet wrapper (``ratchet.py``)
can operate without depending on the larger ``scieasy.qa.schemas`` package
which is itself implemented in Phase 1A.

Schema (v1.0)::

    {
      "tool": "ruff",
      "total_findings": 0,
      "per_file": {"src/scieasy/foo.py": 3, ...},
      "phase_1_end_sha": null,
      "schema_version": "1.0"
    }

Per ADR-042 §4.3 line 467, there is **no** ``baseline.json`` of tolerated
violations: every tool's baseline starts at zero, and the cleanup sprint
ratchets downward from whatever Phase-1-end empirical count turns out to
be.  These seed files exist solely as schema-valid placeholders that the
ratchet can read on its first invocation; the empirical population happens
during Phase 1.5 sweep.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASELINE_SCHEMA_VERSION = "1.0"

DEFAULT_BASELINES_DIR = Path("docs/audit/baselines")


class BaselineError(ValueError):
    """Raised when a baseline file is malformed or missing required fields."""


def baseline_path(tool: str, base_dir: Path | None = None) -> Path:
    """Return the canonical baseline path for ``tool`` under ``base_dir``."""
    base = base_dir if base_dir is not None else DEFAULT_BASELINES_DIR
    return base / f"{tool}.json"


def read_baseline(tool: str, base_dir: Path | None = None) -> dict[str, Any]:
    """Read the baseline for ``tool``.

    Returns the parsed dict.  Raises :class:`BaselineError` on schema
    mismatch.  Returns a zero-finding stub if the file does not exist —
    this is the documented seed behaviour per ADR-042 §4.3 line 467.
    """
    path = baseline_path(tool, base_dir)
    if not path.exists():
        return _zero_baseline(tool)
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BaselineError(f"baseline {path} is not valid JSON: {exc}") from exc
    _validate(data, path)
    # Codex review (PR #1147): reject mislabeled / mis-copied baselines so the
    # ratchet does not silently compare against the wrong tool's totals.
    if data["tool"] != tool:
        raise BaselineError(
            f"baseline {path} declares tool={data['tool']!r} but was requested "
            f"under tool={tool!r}; rename the file or fix the 'tool' field",
        )
    return data


def write_baseline(
    tool: str,
    total_findings: int,
    per_file: dict[str, int],
    phase_1_end_sha: str | None = None,
    base_dir: Path | None = None,
) -> Path:
    """Persist a baseline for ``tool``.

    Returns the path written.  Overwrites existing content atomically (via
    rename) to avoid partial writes when invoked concurrently.
    """
    if total_findings < 0:
        raise BaselineError(f"total_findings must be >= 0, got {total_findings}")
    if any(v < 0 for v in per_file.values()):
        raise BaselineError("per_file counts must be >= 0")
    path = baseline_path(tool, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tool": tool,
        "total_findings": total_findings,
        "per_file": dict(sorted(per_file.items())),
        "phase_1_end_sha": phase_1_end_sha,
        "schema_version": BASELINE_SCHEMA_VERSION,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def _zero_baseline(tool: str) -> dict[str, Any]:
    return {
        "tool": tool,
        "total_findings": 0,
        "per_file": {},
        "phase_1_end_sha": None,
        "schema_version": BASELINE_SCHEMA_VERSION,
    }


def _validate(data: dict[str, Any], path: Path) -> None:
    required = {"tool", "total_findings", "per_file", "schema_version"}
    missing = required - data.keys()
    if missing:
        raise BaselineError(f"baseline {path} missing keys: {sorted(missing)}")
    if data["schema_version"] != BASELINE_SCHEMA_VERSION:
        raise BaselineError(
            f"baseline {path} schema_version={data['schema_version']!r}; "
            f"this wrapper supports only {BASELINE_SCHEMA_VERSION!r}",
        )
    if not isinstance(data["total_findings"], int) or data["total_findings"] < 0:
        raise BaselineError(f"baseline {path} total_findings must be non-negative int")
    if not isinstance(data["per_file"], dict):
        raise BaselineError(f"baseline {path} per_file must be an object")
    for k, v in data["per_file"].items():
        if not isinstance(k, str):
            raise BaselineError(f"baseline {path} per_file key {k!r} not a string")
        if not isinstance(v, int) or v < 0:
            raise BaselineError(
                f"baseline {path} per_file[{k!r}]={v!r} must be non-negative int",
            )
