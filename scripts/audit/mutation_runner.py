"""CLI shim — invokes :func:`scieasy.qa.test_quality.mutation_runner.run_targeted`.

Usage::

    python -m scripts.audit.mutation_runner \\
        --modules src/scieasy/qa src/scieasy/core \\
        --baseline docs/audit/baselines/mutation.json

The ``--modules`` flag accepts one or more project-relative module paths
(typically the PR's diff-touched packages); ``--baseline`` is optional
and points to the §4.5 baseline JSON. A missing baseline is non-fatal
(no regression detection performed).

Exit codes mirror the other QA shims:

  0 — no error-severity findings (the §4.5 default since Phase 1 is
      report-only — see ``run_targeted`` docstring).
  1 — error-severity findings present (Phase 3 onwards when
      ``TQMUT-below-threshold`` is promoted).
  2 — configuration error (no ``--modules`` supplied, etc.).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scieasy.qa.schemas.report import Finding, Severity  # noqa: E402
from scieasy.qa.test_quality.mutation_runner import run_targeted  # noqa: E402


def _render(finding: Finding) -> str:
    """Render one Finding as a single review-line (line=0 if absent)."""
    line = finding.line if finding.line is not None else 0
    return f"{finding.file}:{line}: {finding.severity.value}: {finding.rule_id}: {finding.message}"


def main(argv: list[str] | None = None) -> int:
    """Entry point — see module docstring."""
    parser = argparse.ArgumentParser(
        prog="scripts.audit.mutation_runner",
        description="ADR-043 §4.5 mutation-score runner.",
    )
    parser.add_argument(
        "--modules",
        type=str,
        nargs="+",
        required=True,
        help="project-relative module paths to mutate (e.g. src/scieasy/qa)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("docs/audit/baselines/mutation.json"),
        help="path to baseline JSON (optional; absent => no regression check)",
    )
    args = parser.parse_args(argv)

    if not args.modules:
        parser.error("--modules requires at least one entry")
        return 2

    findings = run_targeted(args.modules, args.baseline)
    for finding in findings:
        sys.stdout.write(_render(finding) + "\n")

    errors = [f for f in findings if f.severity is Severity.ERROR]
    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover — CLI dispatch
    raise SystemExit(main())
