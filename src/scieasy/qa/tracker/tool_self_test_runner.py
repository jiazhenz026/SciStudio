"""Check ADR-043 section 2.4 tool self-test artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

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
REQUIRED_KEYS = {"tool", "target", "generated_at"}


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

        artifact_findings, payload = _load_artifact(root, name, relative_path)
        findings.extend(artifact_findings)
        if payload is None:
            continue
        findings.extend(_validate_payload(root, name, relative_path, payload))

    return findings


def _load_artifact(root: Path, name: str, relative_path: Path) -> tuple[list[Finding], dict[str, Any] | None]:
    path = root / relative_path
    if not path.is_file():
        return [
            make_finding(
                "tool-self-test.missing-artifact",
                f"{name} is missing mandatory ADR-042 self-test artifact: {relative_path}",
                file=relative_path,
                suggested_fix="Commit the tool self-test JSON artifact required by ADR-043 section 2.4.",
            )
        ], None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [
            make_finding(
                "tool-self-test.invalid-json",
                f"{name} self-test artifact is not valid JSON: {exc}",
                file=relative_path,
            )
        ], None
    if not isinstance(payload, dict):
        return [
            make_finding(
                "tool-self-test.invalid-shape",
                f"{name} self-test artifact must be a JSON object.",
                file=relative_path,
            )
        ], None
    return [], payload


def _validate_payload(root: Path, name: str, relative_path: Path, payload: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    missing = sorted(REQUIRED_KEYS - payload.keys())
    if missing:
        findings.append(
            make_finding(
                "tool-self-test.missing-required-field",
                f"{name} self-test artifact is missing required field(s): {missing}",
                file=relative_path,
            )
        )

    if payload.get("tool") not in {name, name.replace("_", "-")}:
        findings.append(
            make_finding(
                "tool-self-test.tool-mismatch",
                f"{name} self-test artifact declares tool={payload.get('tool')!r}.",
                file=relative_path,
            )
        )
    if payload.get("target") != "docs/adr/ADR-042.md":
        findings.append(
            make_finding(
                "tool-self-test.target-mismatch",
                f"{name} self-test artifact must target docs/adr/ADR-042.md.",
                file=relative_path,
            )
        )

    adr_path = root / "docs/adr/ADR-042.md"
    artifact_path = root / relative_path
    if adr_path.is_file() and artifact_path.stat().st_mtime < adr_path.stat().st_mtime:
        findings.append(
            make_finding(
                "tool-self-test.stale-artifact",
                f"{name} self-test artifact is older than docs/adr/ADR-042.md.",
                file=relative_path,
            )
        )

    fresh_output = payload.get("fresh_output_path")
    if fresh_output:
        findings.extend(_compare_fresh_output(root, name, relative_path, payload, str(fresh_output)))
    return findings


def _compare_fresh_output(
    root: Path,
    name: str,
    relative_path: Path,
    payload: dict[str, Any],
    fresh_output: str,
) -> list[Finding]:
    fresh_path = root / fresh_output
    if not fresh_path.is_file():
        return [
            make_finding(
                "tool-self-test.fresh-output-missing",
                f"{name} fresh output path does not exist: {fresh_output}",
                file=relative_path,
            )
        ]
    try:
        fresh_payload = json.loads(fresh_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [
            make_finding(
                "tool-self-test.fresh-output-invalid-json",
                f"{name} fresh output is not valid JSON: {exc}",
                file=fresh_output,
            )
        ]

    expected = payload.get("expected_output", payload.get("output"))
    if expected is None:
        return [
            make_finding(
                "tool-self-test.expected-output-missing",
                f"{name} artifact declares fresh_output_path but no expected_output/output field.",
                file=relative_path,
            )
        ]
    if fresh_payload != expected:
        return [
            make_finding(
                "tool-self-test.output-mismatch",
                f"{name} fresh output differs from committed expected output.",
                file=relative_path,
            )
        ]
    return []


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
