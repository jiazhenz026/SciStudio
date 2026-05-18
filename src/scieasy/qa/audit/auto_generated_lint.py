"""Auto-generated doc hand-edit detection (ADR-044 §11.5 + §10.3).

Files under ``docs/`` whose frontmatter declares ``generation: auto`` are
authored by build-time generators (``llms_txt.generate``,
``entry_point_catalog.generate``, etc.). Hand-edits to those files
introduce drift between the renderer and the persisted output, defeating
the anti-drift discipline of ADR-044.

This module detects hand-edits by hashing the body content (frontmatter
+ body) of every auto-generated file and comparing against a baseline
hash recorded in ``docs/audit/baselines/auto-gen.json``. A mismatch
indicates the file changed without a corresponding regeneration step.

Baseline strategy (Phase 1 investigation SUMMARY Q1B.10.1)
----------------------------------------------------------
Content-hash via ``docs/audit/baselines/auto-gen.json`` was chosen over
mtime-based detection because mtimes are unreliable across Windows /
cross-checkout / shallow-clone scenarios. The baseline JSON is written
by the generator scripts themselves at regeneration time (in a follow-up
1D PR); until then, missing entries surface as INFO findings (no false
positives during the first audit cycle).

The ``Regenerated-At:`` trailer escape hatch from ADR-044 §11.5 is
deferred per Q1B.10.2 — v1 simply requires the file to round-trip
through the generator before commit.

References
----------
ADR-044 §10.3 — generators.
ADR-044 §11.5 — entry-point signature + algorithm prose.
ADR-044 §13.1 — pre-commit wiring.

Deferred work
-------------
* ``Regenerated-At:`` trailer parsing — TODO(#1154-ext-trailer).
* Baseline auto-population from generators — TODO(#1154-ext-baseline);
  v1 reads the baseline file but does not write it.

# TODO(#1154-ext): wire `Regenerated-At:` trailer escape hatch
#   Out of scope per Phase 1 investigation SUMMARY Q1B.10.2.
#   Followup: open as ADR-042 §13.2 errata after sub-PR 3 ships.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from scieasy.qa.schemas.report import Finding, Severity

__all__ = ["check", "compute_body_hash", "load_baseline"]

#: Repo-relative path to the content-hash baseline JSON.
BASELINE_RELPATH = Path("docs/audit/baselines/auto-gen.json")


def check(repo_root: Path | None = None) -> list[Finding]:
    """Scan ``docs/`` for hand-edits to ``generation: auto`` files.

    Algorithm:
      1. Load baseline JSON (path -> sha256 hex). Missing file → empty mapping.
      2. Walk ``docs/`` recursively for ``*.md`` and ``*.txt``.
      3. Parse frontmatter; skip files without ``generation: auto``.
      4. Compute SHA-256 of the full file body.
      5. If path not in baseline → INFO ``auto-generated-lint.no-baseline``.
      6. If hash differs from baseline → ERROR ``auto-generated-lint.hand-edit``.
      7. If hash matches → no finding.

    Files outside ``docs/`` are not in scope. Symlinks are followed as
    Python's ``Path.read_text`` follows them by default.
    """
    repo_root = repo_root or Path.cwd()
    docs_dir = repo_root / "docs"
    findings: list[Finding] = []
    if not docs_dir.is_dir():
        return findings

    baseline = load_baseline(repo_root)

    for path in _iter_doc_files(docs_dir):
        rel_path = path.relative_to(repo_root).as_posix()
        frontmatter = _read_frontmatter(path)
        if frontmatter is None:
            continue
        if frontmatter.get("generation") != "auto":
            continue

        actual = compute_body_hash(path)
        baseline_hash = baseline.get(rel_path)

        if baseline_hash is None:
            findings.append(
                Finding(
                    rule_id="auto-generated-lint.no-baseline",
                    severity=Severity.INFO,
                    file=rel_path,
                    message=(
                        f"no baseline hash for auto-generated file; add "
                        f"`{rel_path}`: `{actual}` to "
                        f"{BASELINE_RELPATH.as_posix()} (first-run case)."
                    ),
                    git_evidence=actual,
                )
            )
            continue

        if baseline_hash != actual:
            findings.append(
                Finding(
                    rule_id="auto-generated-lint.hand-edit",
                    severity=Severity.ERROR,
                    file=rel_path,
                    message=(
                        "auto-generated file body hash differs from baseline "
                        f"(expected {baseline_hash[:12]}…, got {actual[:12]}…). "
                        "Regenerate via the appropriate "
                        "scieasy.qa.docs.generators script — do not hand-edit."
                    ),
                    git_evidence=actual,
                )
            )

    return findings


def load_baseline(repo_root: Path) -> dict[str, str]:
    """Read the baseline JSON; return ``{}`` when absent or malformed.

    A malformed baseline (non-dict, non-string values, JSON parse error)
    is treated as absent — we don't want a corrupt baseline file to
    silently mask hand-edits. Callers can detect this via the empty
    return value combined with an existing ``BASELINE_RELPATH``.
    """
    baseline_path = repo_root / BASELINE_RELPATH
    if not baseline_path.is_file():
        return {}
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(k): str(v)
        for k, v in data.items()
        if isinstance(k, str) and isinstance(v, str)
    }


def compute_body_hash(path: Path) -> str:
    """Hex SHA-256 of the file's full UTF-8 bytes (frontmatter included).

    Hashing the full body (rather than body-minus-frontmatter) keeps the
    baseline check sensitive to frontmatter drift too — a hand-edit that
    only touches ``last_generated_sha`` still counts as drift.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _iter_doc_files(docs_dir: Path) -> list[Path]:
    """Sorted list of ``.md`` / ``.txt`` files under ``docs_dir``."""
    md_files = list(docs_dir.rglob("*.md"))
    txt_files = list(docs_dir.rglob("*.txt"))
    return sorted(set(md_files + txt_files))


def _read_frontmatter(path: Path) -> dict[str, Any] | None:
    """Parse YAML frontmatter; return ``None`` if file has no frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data
