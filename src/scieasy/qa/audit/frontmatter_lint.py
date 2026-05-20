"""ADR/spec frontmatter and first-section validation per ADR-042."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from pydantic import ValidationError

from scieasy.qa.audit._util import (
    _apply_governance_amendments,
    load_adr_frontmatter,
    load_spec_frontmatter,
    normalise_path,
    parse_yaml_frontmatter,
)
from scieasy.qa.schemas.frontmatter import ADRAddendumFrontmatter, ADRFrontmatter
from scieasy.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_DETAIL_SECTION_RE = re.compile(r"\bSection\s+(\d+(?:\.\d+)*)\b", re.IGNORECASE)
_ADR_ADDENDUM_RE = re.compile(r"^ADR-\d{3}-addendum")


def _is_adr(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    return "docs" in parts and "adr" in parts and path.name.startswith("ADR-")


def _is_adr_addendum(path: Path) -> bool:
    return _ADR_ADDENDUM_RE.match(path.name) is not None


def _is_spec(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    return "docs" in parts and "specs" in parts


def _finding(path: Path, rule_id: str, message: str, *, line: int | None = None) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.ERROR,
        file=normalise_path(path),
        line=line,
        message=message,
    )


def _headings(body: str) -> list[tuple[int, str, int]]:
    headings: list[tuple[int, str, int]] = []
    in_fence = False
    for index, line in enumerate(body.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if match:
            headings.append((len(match.group(1)), match.group(2).strip(), index))
    return headings


def _section_numbers(headings: list[tuple[int, str, int]]) -> set[str]:
    numbers: set[str] = set()
    for _level, text, _line in headings:
        match = re.match(r"(\d+(?:\.\d+)*)\b", text)
        if match:
            numbers.add(match.group(1))
    return numbers


def _load_adr_addendum_frontmatter(path: Path) -> tuple[ADRAddendumFrontmatter | None, str, list[Finding]]:
    data, body, findings = parse_yaml_frontmatter(path)
    if data is None:
        return None, body, findings
    data, amendment_findings = _apply_governance_amendments(data, body, path=path)
    if amendment_findings:
        return None, body, amendment_findings
    try:
        return ADRAddendumFrontmatter.model_validate(data), body, []
    except ValidationError as exc:
        return (
            None,
            body,
            [
                Finding(
                    rule_id="frontmatter.validation",
                    severity=Severity.ERROR,
                    file=normalise_path(path),
                    line=1,
                    message=f"ADR addendum frontmatter validation failed: {exc}",
                )
            ],
        )


def _check_adr_filename(path: Path, fm: ADRFrontmatter | ADRAddendumFrontmatter) -> list[Finding]:
    if isinstance(fm, ADRAddendumFrontmatter):
        expected = f"ADR-{fm.adr:03d}-addendum{fm.addendum}.md"
        if path.name != expected:
            return [
                _finding(
                    path,
                    "frontmatter.adr-addendum-filename",
                    f"ADR addendum filename must be {expected} for adr={fm.adr} addendum={fm.addendum}",
                    line=1,
                )
            ]
        return []

    expected = f"ADR-{fm.adr:03d}.md"
    if path.name != expected:
        return [
            _finding(
                path,
                "frontmatter.adr-filename",
                f"ADR filename must be {expected} for adr={fm.adr}",
                line=1,
            )
        ]
    return []


def _check_adr_body(path: Path, fm: ADRFrontmatter | ADRAddendumFrontmatter, body: str) -> list[Finding]:
    headings = _headings(body)
    findings: list[Finding] = []

    if isinstance(fm, ADRAddendumFrontmatter):
        expected_h1 = f"ADR-{fm.adr:03d} Addendum {fm.addendum}: {fm.title}"
    else:
        expected_h1 = f"ADR-{fm.adr:03d}: {fm.title}"
    if not headings or headings[0][0] != 1:
        findings.append(_finding(path, "frontmatter.adr-h1", "ADR body must start with an H1 title"))
    elif headings[0][1] != expected_h1:
        findings.append(
            _finding(
                path,
                "frontmatter.adr-h1",
                f"ADR H1 must be '# {expected_h1}'",
                line=headings[0][2],
            )
        )

    h2s = [heading for heading in headings if heading[0] == 2]
    if not h2s or h2s[0][1] != "1. Decision Summary":
        findings.append(
            _finding(
                path,
                "frontmatter.adr-first-h2",
                "first ADR H2 must be '## 1. Decision Summary'",
                line=h2s[0][2] if h2s else None,
            )
        )

    h3_texts = {text for level, text, _line in headings if level == 3}
    if "1.1 Problems Addressed" not in h3_texts:
        findings.append(
            _finding(
                path,
                "frontmatter.adr-problems-addressed",
                "ADR must include '### 1.1 Problems Addressed'",
            )
        )

    section_numbers = _section_numbers(headings)
    for line_no, line in enumerate(body.splitlines(), start=1):
        if "| Problem |" not in line or "Detailed section" not in line:
            continue
        for row_no, row in enumerate(body.splitlines()[line_no + 1 :], start=line_no + 2):
            stripped = row.strip()
            if not stripped.startswith("|"):
                break
            if set(stripped.replace("|", "").strip()) <= {"-", ":"}:
                continue
            match = _DETAIL_SECTION_RE.search(stripped)
            if match and match.group(1) not in section_numbers:
                findings.append(
                    _finding(
                        path,
                        "frontmatter.adr-detail-section",
                        f"Detailed section reference does not resolve: Section {match.group(1)}",
                        line=row_no,
                    )
                )
            elif not match:
                findings.append(
                    _finding(
                        path,
                        "frontmatter.adr-detail-section",
                        "Problems Addressed rows must include a 'Section N' detailed-section reference",
                        line=row_no,
                    )
                )
        break

    return findings


def _check_spec_body(path: Path, body: str) -> list[Finding]:
    headings = _headings(body)
    h2s = [heading for heading in headings if heading[0] == 2]
    if h2s and h2s[0][1] == "1. Change Summary":
        return []
    return [
        _finding(
            path,
            "frontmatter.spec-first-h2",
            "first spec H2 must be '## 1. Change Summary'",
            line=h2s[0][2] if h2s else None,
        )
    ]


def lint_file(path: Path) -> list[Finding]:
    """Validate one ADR/spec file's frontmatter and required first section."""

    if not path.exists():
        return [_finding(path, "frontmatter.file-missing", "file does not exist", line=1)]

    if _is_adr(path):
        adr_fm: ADRFrontmatter | ADRAddendumFrontmatter | None
        if _is_adr_addendum(path):
            adr_fm, body, findings = _load_adr_addendum_frontmatter(path)
        else:
            adr_fm, body, findings = load_adr_frontmatter(path)
        if adr_fm is None:
            return findings
        return findings + _check_adr_filename(path, adr_fm) + _check_adr_body(path, adr_fm, body)

    if _is_spec(path):
        spec_fm, body, findings = load_spec_frontmatter(path)
        if spec_fm is None:
            return findings
        return findings + _check_spec_body(path, body)

    return [
        Finding(
            rule_id="frontmatter.unknown-kind",
            severity=Severity.WARNING,
            file=normalise_path(path),
            line=1,
            message="not an ADR/spec target for frontmatter lint",
        )
    ]


def check(repo_root: Path | None = None) -> list[Finding]:
    """Validate all ADR and spec Markdown files under ``repo_root``."""

    root = Path(repo_root or Path.cwd())
    findings: list[Finding] = []
    for path in sorted((root / "docs" / "adr").glob("ADR-*.md")):
        findings.extend(lint_file(path))
    for path in sorted((root / "docs" / "specs").glob("*.md")):
        findings.extend(lint_file(path))
    return findings


def lint_paths(paths: list[Path], *, repo_root: Path | None = None) -> AuditReport:
    """Validate selected ADR/spec files and return a shared audit report."""

    root = Path(repo_root or Path.cwd())
    findings: list[Finding] = []
    for path in paths:
        target = path if path.is_absolute() else root / path
        findings.extend(lint_file(target))
    return AuditReport(
        tool="frontmatter_lint",
        status=AuditStatus.FAIL if any(f.severity == Severity.ERROR for f in findings) else AuditStatus.PASS,
        source_sha="",
        findings=findings,
        summary={"paths_checked": len(paths)},
    )


def check_report(repo_root: Path | None = None) -> AuditReport:
    """Validate all ADR and spec Markdown files under ``repo_root`` as an audit report."""

    root = Path(repo_root or Path.cwd())
    findings = check(root)
    return AuditReport(
        tool="frontmatter_lint",
        status=AuditStatus.FAIL if any(f.severity == Severity.ERROR for f in findings) else AuditStatus.PASS,
        source_sha="",
        findings=findings,
        summary={"repo_root": normalise_path(root), "findings": len(findings)},
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ADR/spec frontmatter validation."""

    parser = argparse.ArgumentParser(description="Validate ADR-042 frontmatter and document structure")
    parser.add_argument("paths", nargs="*", type=Path, help="ADR/spec files to validate")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    report = lint_paths(args.paths, repo_root=args.repo_root) if args.paths else check_report(args.repo_root)
    if args.format == "json":
        print(report.model_dump_json(indent=2))
    else:
        for finding in report.findings:
            location = f"{finding.file}:{finding.line}" if finding.line is not None else finding.file
            print(f"{finding.severity}: {location}: {finding.message}")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    raise SystemExit(main())
