"""Hardcoded-fact detection in prose (ADR-042 §10).

Scans every Markdown / reStructuredText file under ``docs/`` (plus
``README.md`` and ``AGENTS.md``) for literal occurrences of values
declared in the canonical
:class:`~scieasy.qa.schemas.facts.FactsRegistry` (loaded from
``docs/facts/generated.yaml``). Any literal that should be a
``{{ facts.X }}`` substitution is reported as a
``fact-drift.hardcoded`` :class:`~scieasy.qa.schemas.report.Finding`.

Severity is controlled by the ``--severity-floor`` CLI flag (per
Phase 1 investigation default Q1B.3.1): during the transitional period
(§10.6) the floor is ``warning``; from Phase 2 onwards it can be
promoted to ``error`` by the operator.

The Phase 1 implementation strips fenced+indented code blocks and any
existing ``{{ facts.X }}`` substitution; everything else is in scope.
Numeric values less than 3 and 1-character matches are excluded as
likely false positives (configurable via ``pyproject.toml``).

References
----------
ADR-042 §10.1 / §10.2 — problem statement + mechanism.
ADR-042 §10.4 — algorithm overview.
ADR-042 §10.6 — transitional severity.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path

import yaml

from scieasy.qa.schemas.facts import FactsRegistry
from scieasy.qa.schemas.report import Finding, Severity

__all__ = ["check_substitutions", "collect_fact_values", "main"]


# Fenced and indented code blocks.
_FENCED_RE = re.compile(r"```.*?```", re.DOTALL)
_INDENTED_RE = re.compile(r"(?m)^( {4,}|\t).*$")
# Existing {{ facts.X }} substitution patterns we MUST strip before searching.
_SUBSTITUTION_RE = re.compile(r"\{\{\s*facts\.[A-Za-z0-9_.]+\s*\}\}")

# Default exclusions per §10.4 / §10's "false-positive minimization" clause.
_DEFAULT_NUMERIC_FLOOR = 3
_DEFAULT_MIN_LEN = 2


def check_substitutions(
    repo_root: Path,
    *,
    severity_floor: Severity = Severity.WARNING,
    numeric_floor: int = _DEFAULT_NUMERIC_FLOOR,
    min_length: int = _DEFAULT_MIN_LEN,
) -> list[Finding]:
    """Detect hardcoded facts in prose that should use ``{{ facts.X }}``.

    Args:
        repo_root: Repository root.
        severity_floor: Minimum severity for emitted findings. Defaults
            to ``WARNING`` per ADR-042 §10.6 transitional period
            (Phase 1 investigation default Q1B.3.1).
        numeric_floor: Numeric fact values below this threshold are
            excluded as likely false-positive matches.
        min_length: String fact values shorter than this length are
            excluded.

    Returns:
        List of findings; empty when no hardcoded facts are found.
    """
    facts = _load_facts(repo_root)
    if facts is None:
        # No facts registry yet → no findings (transitional period).
        return []

    values = collect_fact_values(facts, numeric_floor=numeric_floor, min_length=min_length)
    if not values:
        return []

    findings: list[Finding] = []
    for prose_path in _iter_prose_files(repo_root):
        findings.extend(_scan_file(prose_path, repo_root, values, severity_floor))
    return findings


# ---------------------------------------------------------------------------
# Fact extraction
# ---------------------------------------------------------------------------


def collect_fact_values(
    facts: FactsRegistry,
    *,
    numeric_floor: int = _DEFAULT_NUMERIC_FLOOR,
    min_length: int = _DEFAULT_MIN_LEN,
) -> dict[str, str]:
    """Flatten a :class:`FactsRegistry` into ``{value: dotted_path}``.

    Single-character matches and numerics below ``numeric_floor`` are
    skipped to limit false positives. The map preserves the dotted
    fact path so findings can render a precise ``suggested_fix``.
    """
    flat: dict[str, str] = {}
    _walk("facts", facts.model_dump(mode="python"), flat, numeric_floor, min_length)
    return flat


def _walk(
    prefix: str,
    obj: object,
    out: dict[str, str],
    numeric_floor: int,
    min_length: int,
) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk(f"{prefix}.{k}", v, out, numeric_floor, min_length)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk(f"{prefix}[{i}]", v, out, numeric_floor, min_length)
    elif isinstance(obj, bool):
        # Booleans render as "True"/"False" — too common in prose to
        # be useful fact-drift signal; skip.
        return
    elif isinstance(obj, int):
        if obj < numeric_floor:
            return
        out[str(obj)] = prefix
    elif isinstance(obj, float):
        if obj < numeric_floor:
            return
        out[repr(obj)] = prefix
    elif isinstance(obj, str):
        if len(obj) < min_length:
            return
        out[obj] = prefix


# ---------------------------------------------------------------------------
# File scanning
# ---------------------------------------------------------------------------


def _scan_file(
    path: Path,
    repo_root: Path,
    values: dict[str, str],
    severity_floor: Severity,
) -> list[Finding]:
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8", errors="replace")

    # Strip code blocks + existing substitutions BEFORE scanning.
    cleaned = _FENCED_RE.sub("", text)
    cleaned = _INDENTED_RE.sub("", cleaned)
    cleaned = _SUBSTITUTION_RE.sub("", cleaned)

    rel_path = str(path.relative_to(repo_root)).replace("\\", "/")

    for line_no, raw_line in enumerate(cleaned.splitlines(), start=1):
        for value, dotted in values.items():
            # Word-boundary match for numerics (Phase 1 default per
            # SUMMARY non-blocking note on TC-1B.3).
            if value.lstrip("-").isdigit():
                pattern = rf"\b{re.escape(value)}\b"
                if not re.search(pattern, raw_line):
                    continue
            elif value not in raw_line:
                continue
            findings.append(
                Finding(
                    rule_id="fact-drift.hardcoded",
                    severity=severity_floor,
                    file=rel_path,
                    line=line_no,
                    message=(f"literal '{value}' found in prose; use '{{{{ {dotted} }}}}' substitution instead"),
                    suggested_fix=(f"replace '{value}' with '{{{{ {dotted} }}}}'"),
                )
            )
    return findings


def _iter_prose_files(repo_root: Path) -> Iterable[Path]:
    """Yield every prose file (.md / .rst) the audit should scan."""
    candidates: list[Path] = []
    docs = repo_root / "docs"
    if docs.is_dir():
        for ext in ("md", "rst"):
            candidates.extend(docs.rglob(f"*.{ext}"))
    for name in ("README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md"):
        p = repo_root / name
        if p.is_file():
            candidates.append(p)
    # Exclude auto-generated paths (consolidated cascade dumps, archive snapshots).
    excluded_prefixes = (
        "docs/adr/_consolidated/",
        "docs/audit/archive/",
        "docs/audit/baselines/",
    )
    for path in candidates:
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
        if any(rel.startswith(p) for p in excluded_prefixes):
            continue
        yield path


# ---------------------------------------------------------------------------
# Facts loader
# ---------------------------------------------------------------------------


def _load_facts(repo_root: Path) -> FactsRegistry | None:
    path = repo_root / "docs" / "facts" / "generated.yaml"
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return FactsRegistry.model_validate(data)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m scieasy.qa.audit.fact_drift``.

    Args:
        argv: Optional argv override (None means use ``sys.argv[1:]``).

    Returns:
        Exit code: 0 on no findings; 1 when any finding at or above the
        severity floor is emitted.
    """
    parser = argparse.ArgumentParser(prog="fact_drift")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="repository root (default: cwd)",
    )
    parser.add_argument(
        "--severity-floor",
        choices=[s.value for s in Severity],
        default=Severity.WARNING.value,
        help=(
            "Minimum severity for findings (default: warning per ADR-042 "
            "§10.6 transitional period). Promote to 'error' from Phase 2."
        ),
    )
    args = parser.parse_args(argv)
    findings = check_substitutions(
        args.repo_root,
        severity_floor=Severity(args.severity_floor),
    )
    for finding in findings:
        print(f"{finding.severity.value}: {finding.file}:{finding.line}: {finding.message}")
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
