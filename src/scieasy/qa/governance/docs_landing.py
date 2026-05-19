"""Docs landing checks for ADR-042 gate sessions."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.governance.local_gate import GateSession, load_session, staged_files


def check(
    *,
    repo_root: Path,
    session: GateSession,
    staged: Sequence[Path] | None = None,
):
    staged = staged if staged is not None else staged_files(repo_root)
    findings = []
    landing = session.docs_landing
    if landing is None:
        findings.append(
            build_finding(
                finding_id="docs-landing-missing",
                tool="docs_landing",
                finding_class="docs-landing",
                severity="error",
                message="Missing docs landing record.",
            )
        )
        return build_report(tool="docs_landing", repo_root=repo_root, findings=findings)
    if not (
        landing.not_applicable_rationale
        or landing.docs_updated
        or landing.changelog_updated
        or landing.checklist_updated
    ):
        findings.append(
            build_finding(
                finding_id="docs-landing-empty",
                tool="docs_landing",
                finding_class="docs-landing",
                severity="error",
                message="Docs landing must list docs/changelog/checklist updates or explicit N/A rationale.",
            )
        )
    changed_docs = {Path(path).as_posix() for path in staged if Path(path).as_posix().startswith("docs/")}
    declared_docs = {Path(path).as_posix() for path in landing.docs_updated}
    undeclared = sorted(changed_docs - declared_docs)
    if undeclared and not landing.not_applicable_rationale:
        findings.append(
            build_finding(
                finding_id="docs-landing-undeclared-docs",
                tool="docs_landing",
                finding_class="docs-landing",
                severity="error",
                message="Changed docs are missing from docs landing record.",
                subject=", ".join(undeclared),
                evidence={"undeclared_docs": undeclared},
            )
        )
    return build_report(tool="docs_landing", repo_root=repo_root, findings=findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check ADR-042 docs landing evidence.")
    parser.add_argument("--session")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    session = load_session(Path.cwd(), session_id=args.session)
    if session is None:
        report = build_report(
            tool="docs_landing",
            repo_root=Path.cwd(),
            findings=[
                build_finding(
                    finding_id="docs-landing-missing-session",
                    tool="docs_landing",
                    finding_class="missing-session",
                    severity="error",
                    message="No gate session found.",
                )
            ],
        )
    else:
        report = check(repo_root=Path.cwd(), session=session)
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
