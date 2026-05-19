"""Helpers for ADR/spec governed-surface checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scieasy.qa.audit._util import (
    git_tracked_relative_paths,
    is_tracked_path,
    load_adr_frontmatter,
    load_spec_frontmatter,
    normalise_path,
)
from scieasy.qa.schemas.frontmatter import ADRFrontmatter, SpecFrontmatter
from scieasy.qa.schemas.report import Finding


@dataclass(frozen=True)
class GovernedDocument:
    """One ADR/spec document with valid governed-surface metadata."""

    path: Path
    kind: str
    title: str
    owner: str | None
    frontmatter: ADRFrontmatter | SpecFrontmatter


def load_governed_documents(repo_root: Path) -> tuple[list[GovernedDocument], list[Finding]]:
    """Load ADR/spec frontmatter documents that participate in governance checks."""

    docs: list[GovernedDocument] = []
    findings: list[Finding] = []
    tracked_paths = git_tracked_relative_paths(repo_root)
    for path in sorted((repo_root / "docs" / "adr").glob("ADR-*.md")):
        if not is_tracked_path(path, repo_root, tracked_paths):
            continue
        adr_frontmatter, _body, load_findings = load_adr_frontmatter(path)
        if adr_frontmatter is None:
            findings.extend(load_findings)
            continue
        docs.append(
            GovernedDocument(
                path=path,
                kind="adr",
                title=adr_frontmatter.title,
                owner=adr_frontmatter.owner,
                frontmatter=adr_frontmatter,
            )
        )
    for path in sorted((repo_root / "docs" / "specs").glob("*.md")):
        if not is_tracked_path(path, repo_root, tracked_paths):
            continue
        spec_frontmatter, _body, load_findings = load_spec_frontmatter(path)
        if spec_frontmatter is None:
            findings.extend(load_findings)
            continue
        docs.append(
            GovernedDocument(
                path=path,
                kind="spec",
                title=spec_frontmatter.title,
                owner=spec_frontmatter.owners[0] if spec_frontmatter.owners else None,
                frontmatter=spec_frontmatter,
            )
        )
    return docs, findings


def governed_file_matches(repo_root: Path, pattern: str) -> list[Path]:
    """Resolve one governed file path or glob pattern relative to the repo root."""

    normalized = pattern.replace("\\", "/")
    if any(token in normalized for token in ["*", "?", "["]):
        return sorted(path for path in repo_root.glob(normalized) if path.exists())
    path = repo_root / normalized
    return [path] if path.exists() else []


def display_path(path: Path, repo_root: Path) -> str:
    """Return a repo-relative display path when possible."""

    try:
        return normalise_path(path.relative_to(repo_root))
    except ValueError:
        return normalise_path(path)
