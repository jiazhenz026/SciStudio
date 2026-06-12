"""Strong checks for block/package developer documentation."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from scistudio.qa.audit._util import git_tracked_relative_paths, is_tracked_path, normalise_path, parse_yaml_frontmatter
from scistudio.qa.schemas.frontmatter import ArchitectureFrontmatter
from scistudio.qa.schemas.report import AuditReport, AuditStatus, DriftClass, Finding, Severity

_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_EXPLICIT_ANCHOR_RE = re.compile(r"\s*\{#([A-Za-z0-9_-]+)\}\s*$")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")

_STALE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "developer-docs.stale-produced-type",
        re.compile(r"\b(?:OutputPort\.)?produced_type\b"),
        "developer docs must not teach the removed OutputPort.produced_type contract",
    ),
    (
        "developer-docs.stale-scieasy-name",
        re.compile(r"\bscieasy\b", re.IGNORECASE),
        "developer docs must use the current SciStudio package and command names",
    ),
    (
        "developer-docs.stale-format-adapter",
        re.compile(r"\b(?:FormatAdapter|scistudio\.adapters)\b"),
        "developer docs must teach current IO format capabilities, not the removed adapter API",
    ),
    (
        "developer-docs.stale-metadata-db",
        re.compile(r"\bmetadata\.db\b"),
        "developer docs must not tell block authors to rely on the internal metadata database",
    ),
    (
        "developer-docs.stale-editable-install",
        re.compile(r"\bpip\s+install\s+-e\s+\."),
        "developer docs must not recommend editable installs as the default author workflow",
    ),
)


class DeveloperDocFrontmatter(BaseModel):
    """Frontmatter required for active block/package developer guide pages."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    doc_type: Literal["block-development"]
    title: str = Field(min_length=4, max_length=160)
    status: Literal["living"]
    owner: str = Field(min_length=1)
    last_updated: date
    governed_by: list[str] = Field(min_length=1)
    summary: str = Field(min_length=8, max_length=400)

    @field_validator("governed_by")
    @classmethod
    def _governed_by_entries(cls, values: list[str]) -> list[str]:
        return ArchitectureFrontmatter._governed_by_entries(values)


def _target_docs(repo_root: Path, docs: Sequence[Path] | None = None) -> list[Path]:
    if docs is not None:
        return [path if path.is_absolute() else repo_root / path for path in docs]
    root = repo_root / "docs" / "block-development"
    tracked_paths = git_tracked_relative_paths(repo_root)
    return sorted(
        path for path in root.glob("*.md") if path.is_file() and is_tracked_path(path, repo_root, tracked_paths)
    )


def _finding(path: Path, rule_id: str, message: str, *, line: int | None = None) -> Finding:
    payload = {"rule_id": rule_id, "severity": Severity.ERROR, "file": normalise_path(path), "line": line}
    return Finding.model_validate(payload | {"message": message, "drift_class": DriftClass.BEHAVIOR_DRIFT})


def _slug(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text.strip().lower())
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text


def _anchors(body: str) -> set[str]:
    anchors: set[str] = set()
    for line in body.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            heading = match.group(2)
            explicit = _EXPLICIT_ANCHOR_RE.search(heading)
            if explicit:
                anchors.add(explicit.group(1))
                heading = heading[: explicit.start()].rstrip()
            anchors.add(_slug(heading))
    return anchors


def _validate_links(path: Path, body: str, repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    anchors_cache: dict[Path, set[str]] = {path.resolve(): _anchors(body)}
    lines = body.splitlines()
    in_fence = False
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        scan_line = _INLINE_CODE_RE.sub("", line)
        for match in _LINK_RE.finditer(scan_line):
            raw_target = match.group(1).strip()
            parsed = urlparse(raw_target)
            if parsed.scheme in {"http", "https", "mailto"}:
                continue
            if raw_target.startswith("<") and raw_target.endswith(">"):
                raw_target = raw_target[1:-1]
            target_path_text = unquote(parsed.path)
            anchor = unquote(parsed.fragment)
            target_path = path if not target_path_text else (path.parent / target_path_text)
            target_path = target_path.resolve()
            try:
                target_path.relative_to(repo_root.resolve())
            except ValueError:
                findings.append(
                    _finding(
                        path,
                        "developer-docs.link-outside-repo",
                        f"developer doc link escapes repo: {raw_target}",
                        line=line_no,
                    )
                )
                continue
            if target_path_text and not target_path.exists():
                findings.append(
                    _finding(
                        path,
                        "developer-docs.link-missing-target",
                        f"developer doc link target is missing: {raw_target}",
                        line=line_no,
                    )
                )
                continue
            if anchor:
                if target_path not in anchors_cache:
                    try:
                        _fm, target_body, _findings = parse_yaml_frontmatter(target_path)
                    except OSError:
                        target_body = ""
                    anchors_cache[target_path] = _anchors(target_body)
                if anchor not in anchors_cache[target_path]:
                    findings.append(
                        _finding(
                            path,
                            "developer-docs.link-missing-anchor",
                            f"developer doc link anchor is missing: {raw_target}",
                            line=line_no,
                        )
                    )
    return findings


def _validate_doc(path: Path, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    data, body, frontmatter_findings = parse_yaml_frontmatter(path)
    if frontmatter_findings:
        return [
            finding.model_copy(update={"rule_id": "developer-docs.frontmatter", "file": normalise_path(path)})
            for finding in frontmatter_findings
        ]
    try:
        DeveloperDocFrontmatter.model_validate(data)
    except ValidationError as exc:
        findings.append(
            _finding(path, "developer-docs.frontmatter", f"developer doc frontmatter failed: {exc}", line=1)
        )
    findings.extend(_validate_links(path, body, root))
    for line_no, line in enumerate(body.splitlines(), start=1):
        for rule_id, pattern, message in _STALE_PATTERNS:
            if pattern.search(line):
                findings.append(_finding(path, rule_id, message, line=line_no))
    return findings


def check_report(repo_root: Path, *, docs: Sequence[Path] | None = None) -> AuditReport:
    """Validate active block/package developer docs."""

    root = repo_root.resolve()
    target_docs = _target_docs(root, docs)
    findings = [finding for path in target_docs for finding in _validate_doc(path, root)]

    return AuditReport(
        tool="developer_docs",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha="",
        findings=findings,
        summary={"docs_checked": len(target_docs), "findings": len(findings)},
    )
