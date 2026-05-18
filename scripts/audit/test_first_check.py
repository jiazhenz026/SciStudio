"""CLI shim — invokes :func:`scieasy.qa.test_quality.test_first_check.verify_ordering`.

Usage::

    python -m scripts.audit.test_first_check --pr-number 1144 --repo zjzcpj/SciEasy
    python -m scripts.audit.test_first_check --pr-number 1144 --repo zjzcpj/SciEasy --enforce

The ``--enforce`` flag is set by the GitHub workflow only when the PR
carries the ``tdd-required`` label (per ADR-043 §4.3.2 last sentence:
report-only by default, hard-gate opt-in).

Exit codes mirror ``test_quality.py``: ``0`` clean / no errors,
``1`` error-severity findings present, ``2`` configuration error.
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
from scieasy.qa.test_quality.test_first_check import verify_ordering  # noqa: E402


def _render(f: Finding) -> str:
    """Render one Finding as a single review-line (line=0 if absent)."""
    line = f.line if f.line is not None else 0
    return f"{f.file}:{line}: {f.severity.value}: {f.rule_id}: {f.message}"


def main(argv: list[str] | None = None) -> int:
    """Entry point — see module docstring."""
    parser = argparse.ArgumentParser(
        prog="scripts.audit.test_first_check",
        description="ADR-043 §4.3.2 commit-order test-first verifier.",
    )
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--repo", type=str, required=True, help="owner/repo slug")
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Upgrade findings to error severity (tdd-required label gate).",
    )
    args = parser.parse_args(argv)
    findings = verify_ordering(args.pr_number, args.repo, enforce=args.enforce)
    for f in findings:
        sys.stdout.write(_render(f) + "\n")
    errors = [f for f in findings if f.severity is Severity.ERROR]
    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover — CLI dispatch
    raise SystemExit(main())
