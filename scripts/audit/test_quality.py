"""CLI shim — invokes :func:`scieasy.qa.test_quality.ast_lint.check_test_file`.

Usage::

    python -m scripts.audit.test_quality <path> [<path> ...]
    python -m scripts.audit.test_quality tests/

When given a directory, walks ``**/test_*.py`` under it. Emits one
finding per line in the format::

    <file>:<line>: <severity>: <rule_id>: <message>

Exit codes:

* ``0`` — no error-severity findings.
* ``1`` — one or more error-severity findings.
* ``2`` — configuration / environment error (no paths supplied, etc.).

This is the Phase-1 invocation surface. Phase 3 hardens it into a
pre-commit / CI hook; for now it ships as a standalone CLI so the
maintainer can spot-check ``tests/qa/`` while implementation continues.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the ``src/`` layout is importable when invoked as a script from a
# fresh checkout (CI sometimes runs without an editable install).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scieasy.qa.schemas.report import Finding, Severity  # noqa: E402
from scieasy.qa.test_quality.ast_lint import check_test_file  # noqa: E402


def _iter_test_files(paths: list[Path]) -> list[Path]:
    """Expand directories to ``**/test_*.py`` and pass through files."""
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(p.rglob("test_*.py")))
        elif p.is_file():
            out.append(p)
    return out


def _render(f: Finding) -> str:
    """Render one Finding as a single review-line."""
    line = f.line if f.line is not None else 1
    return f"{f.file}:{line}: {f.severity.value}: {f.rule_id}: {f.message}"


def main(argv: list[str] | None = None) -> int:
    """Entry point — see module docstring for behavior."""
    parser = argparse.ArgumentParser(
        prog="scripts.audit.test_quality",
        description="ADR-043 §4.2 AST anti-pattern detector for test files.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to scan; directories walked for test_*.py",
    )
    args = parser.parse_args(argv)
    if not args.paths:
        parser.error("at least one path required")
        return 2
    files = _iter_test_files(args.paths)
    findings: list[Finding] = []
    for file_path in files:
        findings.extend(check_test_file(file_path))
    for finding in findings:
        sys.stdout.write(_render(finding) + "\n")
    errors = [finding for finding in findings if finding.severity is Severity.ERROR]
    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover — CLI dispatch
    raise SystemExit(main())
