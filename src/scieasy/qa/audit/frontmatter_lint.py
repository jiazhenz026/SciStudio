"""Validate ADR/spec markdown frontmatter and required first-section structure."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import ValidationError

from scieasy.qa._report_helpers import build_finding, build_report
from scieasy.qa._shared import AuditFinding, AuditReport
from scieasy.qa.schemas.frontmatter import ADRFrontmatter, SpecFrontmatter

DocumentKind = Literal[
    "adr",
    "spec",
    "architecture",
    "contributor",
    "user",
    "prod-agent",
    "doc-guide",
    "audit",
    "generated",
    "unknown",
]


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line: int

    @property
    def slug(self) -> str:
        slug = self.text.strip().lower()
        slug = re.sub(r"[^\w\s-]", "", slug, flags=re.UNICODE)
        slug = slug.replace("_", "-")
        slug = re.sub(r"\s+", "-", slug).strip("-")
        return slug


@dataclass(frozen=True)
class MarkdownDocument:
    path: str
    kind: DocumentKind
    frontmatter: dict[str, Any]
    headings: list[Heading]
    body_line_count: int
    prose_word_count: int
    content_lines: list[str]


def _kind_from_path(path: Path) -> DocumentKind:
    posix_name = path.name.lower()
    if posix_name.startswith("adr") and " " not in posix_name:
        return "adr"
    if posix_name.startswith("spec") and " " not in posix_name:
        return "spec"

    posix = path.as_posix()
    if posix.startswith("docs/adr/"):
        return "adr"
    if posix.startswith("docs/specs/"):
        return "spec"
    if posix.startswith("docs/architecture/"):
        return "architecture"
    if posix.startswith("docs/contributing/"):
        return "contributor"
    if posix.startswith("docs/user/"):
        return "user"
    if posix.startswith("docs/prod-agent/"):
        return "prod-agent"
    if posix.startswith("docs/doc-guide/"):
        return "doc-guide"
    if posix.startswith("docs/audit/"):
        return "audit"
    return "unknown"


def _parse_frontmatter(lines: list[str]) -> tuple[dict[str, Any], list[str]]:
    if not lines or lines[0].strip() != "---":
        return {}, lines
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            raw = "\n".join(lines[1:end])
            if not raw.strip():
                return {}, lines[end + 1 :]
            try:
                loaded = yaml.safe_load(raw) or {}
            except Exception:
                return {"__frontmatter_error__": "invalid-yaml"}, lines[end + 1 :]
            if not isinstance(loaded, dict):
                return {}, lines[end + 1 :]
            return dict(loaded), lines[end + 1 :]
    # unclosed frontmatter fence
    return {}, lines


def _infer_kind_from_frontmatter(frontmatter: dict[str, Any]) -> DocumentKind | None:
    if "adr" in frontmatter:
        return "adr"
    if "spec_id" in frontmatter:
        return "spec"
    return None


def parse_markdown_text(text: str, *, path: str, kind: DocumentKind = "unknown") -> MarkdownDocument:
    raw_lines = text.splitlines()
    frontmatter, content_lines = _parse_frontmatter(raw_lines)
    prose_line_count = 0
    headings: list[Heading] = []
    prose_words = 0

    in_code_block = False
    in_frontmatter_fence = False
    for idx, line in enumerate(content_lines, start=1):
        stripped = line.strip()
        if idx == 1 and stripped == "---":
            # defensive fallback for weird duplicate frontmatter starts
            in_frontmatter_fence = True
            continue
        if in_frontmatter_fence:
            if stripped == "---":
                in_frontmatter_fence = False
            continue

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            headings.append(Heading(level=len(heading_match.group(1)), text=heading_match.group(2).strip(), line=idx))
            continue

        if not stripped:
            continue
        prose_line_count += 1
        prose_words += len(re.findall(r"\b[\w-]+\b", stripped))

    return MarkdownDocument(
        path=path,
        kind=kind,
        frontmatter=frontmatter,
        headings=headings,
        body_line_count=prose_line_count,
        prose_word_count=prose_words,
        content_lines=content_lines,
    )


def parse_markdown_document(path: Path, *, repo_root: Path) -> MarkdownDocument:
    content = path.read_text(encoding="utf-8")
    relative = path.relative_to(repo_root).as_posix() if path.is_absolute() else path.as_posix()
    doc = parse_markdown_text(content, path=relative, kind="unknown")
    kind = _infer_kind_from_frontmatter(doc.frontmatter) or _kind_from_path(Path(relative))
    return MarkdownDocument(**{**doc.__dict__, "kind": kind})


def _add_finding(
    findings: list[Any],
    *,
    path: Path,
    line: int | None,
    finding_id: str,
    finding_class: str,
    message: str,
    severity: Literal["info", "warning", "error"] = "error",
    expected: object | None = None,
    actual: object | None = None,
    remediation: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> None:
    findings.append(
        build_finding(
            finding_id=finding_id,
            tool="frontmatter_lint",
            finding_class=finding_class,
            severity=severity,
            message=message,
            path=path,
            line=line,
            expected=expected,
            actual=actual,
            remediation=remediation,
            evidence=evidence,
        )
    )


def _validate_required_fields(path: Path, fm: dict[str, Any], required: dict[str, Any], findings: list[Any]) -> None:
    for field, expected in required.items():
        if field not in fm:
            _add_finding(
                findings,
                path=path,
                line=None,
                finding_id="frontmatter-schema-missing",
                finding_class="schema",
                message=f"Missing required field: {field}",
            )
            continue
        value = fm.get(field)
        if isinstance(expected, tuple):
            if not any(_field_is_valid(value, item) for item in expected):
                _add_finding(
                    findings,
                    path=path,
                    line=None,
                    finding_id="frontmatter-schema-invalid",
                    finding_class="schema",
                    message=f"ADR frontmatter field '{field}' has invalid type",
                )
            continue
        if not _field_is_valid(value, expected):
            _add_finding(
                findings,
                path=path,
                line=None,
                finding_id="frontmatter-schema-invalid",
                finding_class="schema",
                message=f"ADR frontmatter field '{field}' has invalid type",
            )


def _serializable_validation_errors(exc: ValidationError) -> list[dict[str, object]]:
    return [
        {
            "loc": [str(part) for part in error.get("loc", ())],
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        for error in exc.errors()
    ]


def _validate_adr_frontmatter(path: Path, fm: dict[str, Any], findings: list[Any]) -> None:
    if fm.get("__frontmatter_error__") == "invalid-yaml":
        _add_finding(
            findings,
            path=path,
            line=1,
            finding_id="frontmatter-yaml-invalid",
            finding_class="schema",
            message="Invalid YAML in frontmatter",
        )

    required = {
        "adr": int,
        "title": str,
        "status": str,
        "date_created": (str, date),
        "date_accepted": (str, date, type(None)),
        "date_superseded": (str, date, type(None)),
        "supersedes": list,
        "superseded_by": (int, type(None)),
        "related": list,
        "closes_issues": list,
        "tracking_issue": (int, type(None)),
        "is_code_implementation": bool,
        "governs": dict,
        "tests": list,
        "agent_editable": (bool, str),
        "assisted_by": list,
        "phase": str,
        "tags": list,
        "owner": str,
        "co_authors": list,
        "language_source": str,
        "translations": list,
    }
    _validate_required_fields(path, fm, required, findings)

    if "status" in fm and fm.get("status") not in {"Proposed", "Accepted", "Deprecated", "Superseded"}:
        _add_finding(
            findings,
            path=path,
            line=None,
            finding_id="frontmatter-status-invalid",
            finding_class="schema",
            message="ADR status must be one of Proposed/Accepted/Deprecated/Superseded",
        )
    status = fm.get("status")
    if status == "Accepted" and not fm.get("date_accepted"):
        _add_finding(
            findings,
            path=path,
            line=None,
            finding_id="frontmatter-status-mismatch",
            finding_class="schema",
            message="Accepted ADRs must set date_accepted",
        )
    if status != "Accepted" and fm.get("date_accepted"):
        _add_finding(
            findings,
            path=path,
            line=None,
            finding_id="frontmatter-status-mismatch",
            finding_class="schema",
            severity="warning",
            message="Only Accepted ADRs should set date_accepted",
        )

    if status == "Superseded" and not fm.get("superseded_by"):
        _add_finding(
            findings,
            path=path,
            line=None,
            finding_id="frontmatter-status-mismatch",
            finding_class="schema",
            message="Superseded ADRs must set superseded_by",
        )

    governs = fm.get("governs")
    if isinstance(governs, dict):
        for key in ("modules", "contracts", "files", "excludes"):
            if key not in governs:
                _add_finding(
                    findings,
                    path=path,
                    line=None,
                    finding_id="frontmatter-governs-missing",
                    finding_class="schema",
                    message=f"ADR frontmatter missing governs.{key}",
                )
    else:
        _add_finding(
            findings,
            path=path,
            line=None,
            finding_id="frontmatter-governs-type",
            finding_class="schema",
            message="ADR frontmatter governs must be a mapping",
        )

    try:
        parsed = ADRFrontmatter.model_validate(fm)
    except ValidationError as exc:
        _add_finding(
            findings,
            path=path,
            line=None,
            finding_id="frontmatter-schema-pydantic",
            finding_class="schema",
            message="ADR frontmatter does not validate against ADR-042 schema",
            evidence={"errors": _serializable_validation_errors(exc)},
        )
        return

    normalized = path.as_posix()
    if "/docs/adr/" in normalized or path.name.startswith("ADR-"):
        expected_name = f"ADR-{parsed.adr:03d}.md"
        if path.name != expected_name:
            _add_finding(
                findings,
                path=path,
                line=None,
                finding_id="frontmatter-adr-filename",
                finding_class="schema",
                message=f"ADR filename must be {expected_name}",
                expected=expected_name,
                actual=path.name,
            )


def _validate_spec_frontmatter(path: Path, fm: dict[str, Any], findings: list[Any]) -> None:
    if fm.get("__frontmatter_error__") == "invalid-yaml":
        _add_finding(
            findings,
            path=path,
            line=1,
            finding_id="frontmatter-yaml-invalid",
            finding_class="schema",
            message="Invalid YAML in frontmatter",
        )

    required = {
        "spec_id": str,
        "title": str,
        "status": str,
        "feature_branch": str,
        "created": (str, date),
        "input": str,
        "owners": list,
        "related_adrs": list,
        "related_specs": list,
        "scope": dict,
        "governs": dict,
        "tests": list,
        "acceptance_source": str,
        "language_source": str,
    }
    _validate_required_fields(path, fm, required, findings)

    status = fm.get("status")
    if status not in {"Draft", "Clarifying", "Planned", "Implemented", "Deprecated"}:
        _add_finding(
            findings,
            path=path,
            line=None,
            finding_id="frontmatter-status-invalid",
            finding_class="schema",
            message="Spec status must be Draft/Clarifying/Planned/Implemented/Deprecated",
        )

    scope = fm.get("scope")
    if isinstance(scope, dict) and ("in" not in scope or "out" not in scope):
        _add_finding(
            findings,
            path=path,
            line=None,
            finding_id="frontmatter-spec-scope",
            finding_class="schema",
            message="Spec scope must include in/out",
        )

    try:
        SpecFrontmatter.model_validate(fm)
    except ValidationError as exc:
        _add_finding(
            findings,
            path=path,
            line=None,
            finding_id="frontmatter-schema-pydantic",
            finding_class="schema",
            message="Spec frontmatter does not validate against ADR-042 schema",
            evidence={"errors": _serializable_validation_errors(exc)},
        )


def _field_is_valid(value: Any, expected: Any) -> bool:
    if expected is int:
        return isinstance(value, int)
    if expected is str:
        return isinstance(value, str)
    if expected is bool:
        return isinstance(value, bool)
    if expected is list:
        return isinstance(value, list)
    if expected is dict:
        return isinstance(value, dict)
    if expected is date:
        if isinstance(value, date):
            return True
        if not isinstance(value, str):
            return False
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False
    return True


def _extract_anchor_refs(row_text: str) -> set[str]:
    refs: set[str] = set()
    for value in re.findall(r"\([#]([^)]+)\)", row_text):
        refs.add(value.strip())
    for value in re.findall(r"\s#([\w\-.]+)", row_text):
        refs.add(value.strip())
    for value in re.findall(r"`#([\w\-.]+)`", row_text):
        refs.add(value.strip())
    for value in re.findall(r"\bSection\s+([0-9]+(?:\.[0-9]+)*)\b", row_text, flags=re.IGNORECASE):
        refs.add(value.strip())
    return refs


def _check_detailed_sections(path: Path, doc: MarkdownDocument, findings: list[Any]) -> None:
    h2 = [h for h in doc.headings if h.level == 2]
    if not h2:
        _add_finding(
            findings,
            path=path,
            line=1,
            finding_id="frontmatter-structure-missing-h2",
            finding_class="structure",
            message="No H2 heading found",
        )
        return

    heading_index = {h.slug: h.line for h in doc.headings}

    if doc.kind == "adr":
        first = h2[0]
        if first.text != "1. Decision Summary":
            _add_finding(
                findings,
                path=path,
                line=first.line,
                finding_id="frontmatter-structure-no-summary",
                finding_class="structure",
                message="ADR first H2 must be '1. Decision Summary'",
            )

        problems = [h for h in doc.headings if h.level == 3 and h.text.startswith("1.1 Problems Addressed")]
        if not problems:
            _add_finding(
                findings,
                path=path,
                line=first.line,
                finding_id="frontmatter-structure-missing-problems",
                finding_class="structure",
                message="ADR must include '### 1.1 Problems Addressed'",
            )
            return

        problem_section = problems[0]
        table_started = False
        saw_row = False

        for line_text in doc.content_lines:
            if line_text.startswith("### 1.1 Problems Addressed"):
                table_started = True
                continue
            if not table_started:
                continue
            if line_text.startswith("### "):
                break
            if line_text.startswith("## "):
                break
            if not line_text.strip().startswith("|"):
                continue
            if re.fullmatch(r"\s*\|[\s:\-|]+\|\s*", line_text):
                continue

            cols = [cell.strip() for cell in line_text.strip().split("|")[1:-1]]
            if len(cols) < 4:
                continue
            saw_row = True
            details = cols[-1]
            refs = _extract_anchor_refs(details)
            if not refs:
                lower_cols = [value.lower() for value in cols]
                if lower_cols and lower_cols[0] == "problem" and lower_cols[-1] == "detailed section":
                    continue
                _add_finding(
                    findings,
                    path=path,
                    line=problem_section.line,
                    finding_id="frontmatter-detailed-missing",
                    finding_class="structure",
                    message="Problems row missing Detailed section reference",
                )
                continue

            for anchor in refs:
                slug = anchor.lower().replace(" ", "-")
                target_line = heading_index.get(slug)
                if target_line is None and anchor.isdigit():
                    for h in doc.headings:
                        if h.text.startswith(f"{anchor}."):
                            target_line = h.line
                            break
                if target_line is None:
                    _add_finding(
                        findings,
                        path=path,
                        line=problem_section.line,
                        finding_id="frontmatter-detailed-bad-link",
                        finding_class="structure",
                        message=f"Detailed section reference '#{anchor}' does not resolve in this ADR",
                    )
                    continue
                if target_line <= problem_section.line:
                    _add_finding(
                        findings,
                        path=path,
                        line=problem_section.line,
                        finding_id="frontmatter-detailed-order",
                        finding_class="structure",
                        message=f"Detailed section '#{anchor}' must appear after the problems table",
                    )

        if not saw_row:
            _add_finding(
                findings,
                path=path,
                line=problem_section.line,
                finding_id="frontmatter-detailed-missing",
                finding_class="structure",
                message="Problems section table has no data rows",
            )

    elif doc.kind == "spec":
        first = h2[0]
        if first.text != "1. Change Summary":
            _add_finding(
                findings,
                path=path,
                line=first.line,
                finding_id="frontmatter-structure-no-summary",
                finding_class="structure",
                message="Spec first H2 must be '1. Change Summary'",
            )


def lint_file(path: Path, *, repo_root: Path, expected_kind: DocumentKind | None = None) -> AuditReport:
    target = path if path.is_absolute() else repo_root / path
    doc = parse_markdown_document(target, repo_root=repo_root)
    kind = expected_kind or doc.kind
    findings: list[AuditFinding] = []

    if kind == "adr":
        _validate_adr_frontmatter(target, doc.frontmatter, findings)
    elif kind == "spec":
        _validate_spec_frontmatter(target, doc.frontmatter, findings)

    _check_detailed_sections(target, MarkdownDocument(**{**doc.__dict__, "kind": kind}), findings)
    return build_report(tool="frontmatter_lint", repo_root=repo_root, findings=findings)


def lint_paths(paths: Iterable[Path], *, repo_root: Path) -> AuditReport:
    findings: list[AuditFinding] = []
    for candidate in paths:
        target = candidate if candidate.is_absolute() else repo_root / candidate
        if target.is_dir():
            for child in sorted(target.rglob("*.md")):
                if child.is_file():
                    findings.extend(lint_file(child, repo_root=repo_root).findings)
            continue
        findings.extend(lint_file(target, repo_root=repo_root).findings)
    return build_report(tool="frontmatter_lint", repo_root=repo_root, findings=findings)


def _collect_paths(paths: list[str], repo_root: Path, recursive: bool) -> list[Path]:
    collected: list[Path] = []
    for raw in paths:
        resolved = Path(raw) if Path(raw).is_absolute() else repo_root / raw
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        if resolved.is_dir():
            walker = resolved.rglob if recursive else resolved.glob
            for child in walker("*.md"):
                if child.is_file():
                    collected.append(child)
            continue
        if resolved.suffix.lower() == ".md":
            collected.append(resolved)
    return collected


def _serialize_report(report: Any, as_json: bool) -> None:
    if as_json:
        print(report.model_dump_json())
        return
    for finding in report.findings:
        line = finding.line or 0
        print(f"[{finding.severity}] {finding.path}:{line} {finding.id} {finding.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate ADR/spec frontmatter and structure.")
    parser.add_argument("paths", nargs="+", help="Paths or directories to lint")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)

    try:
        candidates = _collect_paths(args.paths, repo_root=Path.cwd(), recursive=args.recursive)
        report = lint_paths(candidates, repo_root=Path.cwd())
    except (OSError, FileNotFoundError) as exc:
        print(f"frontmatter_lint: file error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"frontmatter_lint: {exc}", file=sys.stderr)
        return 2

    _serialize_report(report, args.format == "json")
    return 1 if report.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
