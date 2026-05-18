"""Check ADR-043 section 2.4 tool self-test artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scieasy.qa.schemas.report import Finding, Severity
from scieasy.qa.tracker.adr_implementation_check import make_finding, resolve_repo_root

TOOL_SELF_TEST_ARTIFACTS: dict[str, Path] = {
    "doc_drift": Path("docs/audit/tool-self-test/doc_drift-on-adr-042.json"),
    "frontmatter_lint": Path("docs/audit/tool-self-test/frontmatter_lint-on-adr-042.json"),
    "fact_drift": Path("docs/audit/tool-self-test/fact_drift-on-adr-042.json"),
    "closure": Path("docs/audit/tool-self-test/closure-on-adr-042.json"),
    "pytest_examples": Path("docs/audit/tool-self-test/pytest_examples-on-adr-042.json"),
    "griffe": Path("docs/audit/tool-self-test/griffe-on-adr-042.json"),
    "interrogate": Path("docs/audit/tool-self-test/interrogate-on-adr-042.json"),
    "pydoclint": Path("docs/audit/tool-self-test/pydoclint-on-adr-042.json"),
    "monotonic": Path("docs/audit/tool-self-test/monotonic-on-adr-042.json"),
    "test_quality": Path("docs/audit/tool-self-test/test_quality-on-adr-042.json"),
}


def run_self_test(tool_name: str, repo_root: Path | None = None) -> list[Finding]:
    """Verify a QA tool has a committed self-test artifact for ADR-042."""
    root = resolve_repo_root(repo_root)
    normalized = tool_name.removesuffix(".py").replace("-", "_")
    tools = TOOL_SELF_TEST_ARTIFACTS if normalized == "all" else {normalized: TOOL_SELF_TEST_ARTIFACTS.get(normalized)}

    findings: list[Finding] = []
    for name, relative_path in tools.items():
        if relative_path is None:
            findings.append(
                make_finding(
                    "tool-self-test.unknown-tool",
                    f"Unknown ADR-043 tool self-test target: {tool_name}",
                    file="docs/audit/tool-self-test",
                )
            )
            continue

        path = root / relative_path
        if not path.is_file():
            findings.append(
                make_finding(
                    "tool-self-test.missing-artifact",
                    f"{name} is missing mandatory ADR-042 self-test artifact: {relative_path}",
                    file=relative_path,
                    suggested_fix="Commit the tool self-test JSON artifact required by ADR-043 section 2.4.",
                )
            )
            continue

        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(
                make_finding(
                    "tool-self-test.invalid-json",
                    f"{name} self-test artifact is not valid JSON: {exc}",
                    file=relative_path,
                )
            )

        # TODO(#1113): Execute the tool and diff fresh output against the expected artifact.
        #   Out of scope per ADR-043 §2 skeleton; implementation agent owns command execution.
        #   Followup: #1113.
        # TODO(#1113): Detect stale artifacts via input/config hashes.
        #   Out of scope per ADR-043 §2 skeleton; implementation agent owns stale-artifact checks.
        #   Followup: #1113.

    return findings


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ADR-043 tool self-test checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool_name", help="Tool name to check, or 'all'.")
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)

    findings = run_self_test(args.tool_name, args.repo_root)
    if findings:
        print("Tool self-test check found issues:")
        for finding in findings:
            print(f"  [{finding.severity}] {finding.rule_id}: {finding.message}")
    else:
        print(f"Tool self-test artifact check passed for {args.tool_name}.")
    return 1 if any(finding.severity == Severity.ERROR for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
