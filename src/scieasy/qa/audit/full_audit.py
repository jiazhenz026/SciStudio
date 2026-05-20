"""Aggregate ADR-042 audit reports and render human-readable summaries."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from yaml import YAMLError

from scieasy.qa.audit._util import normalise_path
from scieasy.qa.audit.closure import check_bidirectional
from scieasy.qa.audit.doc_drift import classify_repo
from scieasy.qa.audit.fact_drift import check_substitutions
from scieasy.qa.audit.facts import DEFAULT_FACTS_PATH, DEFAULT_GENERATED_AT, check_generated_facts, load_facts
from scieasy.qa.audit.frontmatter_lint import check_report as check_frontmatter
from scieasy.qa.audit.loaders import load_maintainers
from scieasy.qa.audit.signature_drift import check_expected_signatures
from scieasy.qa.schemas.facts import Fact, FactsRegistry
from scieasy.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

DEFAULT_REPORT_PATH = Path("docs/audit/latest/facts-summary.md")


def _counter(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _symbol_kind(fact: Fact) -> str:
    value = fact.value if isinstance(fact.value, Mapping) else {}
    kind = value.get("kind")
    return kind if isinstance(kind, str) else "unknown"


def _symbol_package(subject: str) -> str:
    parts = subject.split(".")
    if len(parts) < 2:
        return subject
    if parts[0] == "scieasy" and len(parts) >= 2:
        return ".".join(parts[:2])
    return ".".join(parts[:1])


def summarize_facts(registry: FactsRegistry) -> dict[str, Any]:
    """Return a compact, human-oriented summary of a facts registry."""

    facts = registry.facts
    symbol_facts = [fact for fact in facts if fact.kind == "symbol"]
    symbol_packages = Counter(_symbol_package(fact.subject) for fact in symbol_facts)
    top_symbol_packages = dict(sorted(symbol_packages.items(), key=lambda item: (-item[1], item[0]))[:12])
    return {
        "total_facts": len(facts),
        "facts_by_kind": _counter([fact.kind for fact in facts]),
        "facts_by_source": _counter([fact.source for fact in facts]),
        "facts_by_confidence": _counter([fact.confidence for fact in facts]),
        "facts_by_stability": _counter([fact.stability for fact in facts]),
        "symbol_facts": len(symbol_facts),
        "symbols_by_kind": _counter([_symbol_kind(fact) for fact in symbol_facts]),
        "top_symbol_packages": top_symbol_packages,
    }


def _finding(rule_id: str, file: Path, message: str, *, line: int | None = None) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.ERROR,
        file=normalise_path(file),
        line=line,
        message=message,
    )


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return normalise_path(path.relative_to(repo_root))
    except ValueError:
        return normalise_path(path)


def _facts_report(
    repo_root: Path,
    *,
    facts_path: Path,
    check_stale: bool,
) -> AuditReport:
    path = facts_path if facts_path.is_absolute() else repo_root / facts_path
    source_sha = ""
    try:
        registry = load_facts(path)
    except (OSError, ValidationError, YAMLError) as exc:
        finding = _finding("facts.generated-unreadable", path, f"cannot load generated facts registry: {exc}", line=1)
        return AuditReport(
            tool="generate_facts",
            status=AuditStatus.FAIL,
            generated_at=DEFAULT_GENERATED_AT,
            source_sha=source_sha,
            findings=[finding],
            summary={"facts_path": _display_path(path, repo_root)},
        )

    stale_report = check_generated_facts(repo_root, facts_path=facts_path) if check_stale else None
    findings = stale_report.findings if stale_report is not None else []
    status = AuditStatus.FAIL if stale_report is not None and stale_report.blocks_merge else AuditStatus.PASS
    return AuditReport(
        tool="generate_facts",
        status=status,
        generated_at=DEFAULT_GENERATED_AT,
        source_sha=registry.source_sha,
        findings=findings,
        summary={"facts_path": _display_path(path, repo_root), **summarize_facts(registry)},
    )


def run(
    repo_root: Path,
    *,
    facts_path: Path = DEFAULT_FACTS_PATH,
    check_stale: bool = True,
    include_frontmatter_lint: bool = True,
    include_doc_drift: bool = True,
    include_fact_drift: bool = True,
    include_closure: bool = True,
    include_signature_drift: bool = True,
) -> AuditReport:
    """Run the currently implemented ADR-042 aggregate audit checks."""

    root = repo_root.resolve()
    facts_child = _facts_report(root, facts_path=facts_path, check_stale=check_stale)
    child_reports = [facts_child]
    deferred_children: list[str] = []
    if not facts_child.blocks_merge:
        if include_frontmatter_lint:
            child_reports.append(check_frontmatter(root))
        else:
            deferred_children.append("frontmatter_lint")
        registry = load_facts(root / facts_path if not facts_path.is_absolute() else facts_path)
        if include_fact_drift:
            child_reports.append(check_substitutions(root, registry))
        else:
            deferred_children.append("fact_drift")
        if include_doc_drift:
            child_reports.append(classify_repo(root, registry))
        else:
            deferred_children.append("doc_drift")
        if include_closure:
            maintainers_path = root / "MAINTAINERS"
            maintainers = load_maintainers(maintainers_path) if maintainers_path.exists() else None
            child_reports.append(check_bidirectional(root, registry, maintainers=maintainers))
        else:
            deferred_children.append("closure")
        if include_signature_drift:
            child_reports.append(check_expected_signatures(root, registry))
        else:
            deferred_children.append("signature_drift")

    status = AuditStatus.FAIL if any(child.blocks_merge for child in child_reports) else AuditStatus.PASS
    return AuditReport(
        tool="full_audit",
        status=status,
        generated_at=DEFAULT_GENERATED_AT,
        source_sha=facts_child.source_sha,
        findings=[],
        summary={
            "implemented_children": [child.tool for child in child_reports],
            "deferred_children": deferred_children,
        },
        child_reports=child_reports,
    )


def _markdown_table(mapping: Mapping[str, Any], *, key_header: str, value_header: str) -> list[str]:
    lines = [f"| {key_header} | {value_header} |", "|---|---:|"]
    for key, value in mapping.items():
        lines.append(f"| `{key}` | {value} |")
    return lines


def _summary_value(summary: Mapping[str, Any], key: str) -> Any:
    return summary.get(key, {})


def render_markdown(report: AuditReport) -> str:
    """Render an ADR-042 audit report for human readers."""

    facts_report = report.child_reports[0] if report.child_reports else report
    summary = facts_report.summary
    lines = [
        "# ADR-042 Facts Audit Summary",
        "",
        "## 1. Change Summary",
        "",
        "This generated report summarizes the current machine-readable facts registry.",
        "It is intended for human review; drift checks consume the YAML facts directly.",
        "",
        "## 2. Overall Status",
        "",
        f"- Status: `{report.status}`",
        f"- Blocks merge: `{report.blocks_merge}`",
        f"- Source hash: `{report.source_sha}`",
        f"- Facts file: `{summary.get('facts_path', DEFAULT_FACTS_PATH.as_posix())}`",
        f"- Total facts: `{summary.get('total_facts', 0)}`",
        f"- Symbol facts: `{summary.get('symbol_facts', 0)}`",
        "",
        "## 3. Fact Inventory",
        "",
    ]
    lines.extend(
        _markdown_table(_summary_value(summary, "facts_by_kind"), key_header="Fact kind", value_header="Count")
    )
    lines.extend(["", "## 4. Symbol Inventory", ""])
    lines.extend(
        _markdown_table(_summary_value(summary, "symbols_by_kind"), key_header="Symbol kind", value_header="Count")
    )
    lines.extend(["", "## 5. Largest Symbol Areas", ""])
    lines.extend(
        _markdown_table(_summary_value(summary, "top_symbol_packages"), key_header="Package", value_header="Count")
    )
    lines.extend(["", "## 6. Findings", ""])
    findings = report.error_findings()
    if not findings:
        lines.append("No error-severity findings.")
    else:
        lines.extend([f"Total error-severity findings: `{len(findings)}`", ""])
        for finding in findings:
            location = f"{finding.file}:{finding.line}" if finding.line is not None else finding.file
            lines.append(f"- `{finding.rule_id}` at `{location}`: {finding.message}")
    lines.extend(["", "## 7. Child Reports", ""])
    lines.extend(["| Tool | Status | Errors | Summary |", "|---|---|---:|---|"])
    for child in report.child_reports:
        child_summary = ", ".join(
            f"{key}={value}" for key, value in child.summary.items() if not isinstance(value, dict)
        )
        lines.append(f"| `{child.tool}` | `{child.status}` | {len(child.error_findings())} | {child_summary} |")
    deferred = report.summary.get("deferred_children", [])
    if deferred:
        lines.extend(["", "## 8. Deferred Checks", ""])
        for child in deferred:
            lines.append(f"- `{child}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ADR-042 aggregate audit checks")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--facts", type=Path, default=DEFAULT_FACTS_PATH)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-stale-check", action="store_true")
    parser.add_argument("--skip-frontmatter-lint", action="store_true")
    parser.add_argument("--skip-doc-drift", action="store_true")
    parser.add_argument("--skip-fact-drift", action="store_true")
    parser.add_argument("--skip-closure", action="store_true")
    parser.add_argument("--skip-signature-drift", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = run(
            args.repo_root,
            facts_path=args.facts,
            check_stale=not args.no_stale_check,
            include_frontmatter_lint=not args.skip_frontmatter_lint,
            include_doc_drift=not args.skip_doc_drift,
            include_fact_drift=not args.skip_fact_drift,
            include_closure=not args.skip_closure,
            include_signature_drift=not args.skip_signature_drift,
        )
        text = report.model_dump_json(indent=2) + "\n" if args.format == "json" else render_markdown(report)
        if args.output is None:
            print(text, end="" if text.endswith("\n") else "\n")
        else:
            output = args.output if args.output.is_absolute() else args.repo_root / args.output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
    except Exception as exc:
        print(f"full_audit failed: {exc}", file=sys.stderr)
        return 2

    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    raise SystemExit(main())
