from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.frontmatter_lint import lint_file, lint_paths
from scieasy.qa.schemas.report import AuditStatus, Severity

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _valid_adr(number: int = 123) -> str:
    return f"""---
adr: {number}
title: "Example Governance Decision"
status: Proposed
date_created: 2026-05-19
date_accepted: null
date_superseded: null
supersedes: []
superseded_by: null
related: []
closes_issues: []
tracking_issue: 1113
is_code_implementation: true
governs:
  modules:
    - scieasy.qa
  contracts:
    - scieasy.qa.audit.frontmatter_lint.lint_file
  entry_points: []
  files:
    - src/scieasy/qa/**
  excludes: []
tests:
  - tests/qa/test_audit_frontmatter_lint.py
agent_editable: false
assisted_by:
  - "Codex:gpt-5"
phase: planning
tags: [qa]
owner: "@owner"
co_authors: []
language_source: en
translations: []
---

# ADR-{number:03d}: Example Governance Decision

## 1. Decision Summary

### 1.1 Problems Addressed

| Problem | Risk | ADR-042 response | Detailed section |
|---|---|---|---|
| Docs drift | False contracts | Add machine checks | Section 2 |

## 2. Details
"""


def test_valid_adr_frontmatter_and_structure_pass(tmp_path: Path) -> None:
    path = _write(tmp_path / "docs" / "adr" / "ADR-123.md", _valid_adr())

    assert lint_file(path) == []


def test_frontmatter_lint_paths_returns_audit_report(tmp_path: Path) -> None:
    path = _write(tmp_path / "docs" / "adr" / "ADR-123.md", _valid_adr())

    report = lint_paths([path], repo_root=tmp_path)

    assert report.tool == "frontmatter_lint"
    assert report.status == AuditStatus.PASS
    assert not report.blocks_merge


def test_adr_filename_must_match_number(tmp_path: Path) -> None:
    path = _write(tmp_path / "docs" / "adr" / "ADR-124.md", _valid_adr())

    findings = lint_file(path)

    assert any(f.rule_id == "frontmatter.adr-filename" for f in findings)


def test_accepted_adr_requires_date_accepted(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "docs" / "adr" / "ADR-123.md",
        _valid_adr().replace("status: Proposed", "status: Accepted"),
    )

    findings = lint_file(path)

    assert findings[0].severity is Severity.ERROR
    assert findings[0].rule_id == "frontmatter.validation"


def test_adr_detail_section_references_must_resolve(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "docs" / "adr" / "ADR-123.md",
        _valid_adr().replace("Section 2", "Section 9"),
    )

    findings = lint_file(path)

    assert any(f.rule_id == "frontmatter.adr-detail-section" for f in findings)


def test_spec_first_h2_must_be_change_summary(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "docs" / "specs" / "example.md",
        """---
spec_id: example
title: "Example Spec"
status: Draft
feature_branch: feat/example
created: 2026-05-19
input: "manual"
owners: ["@owner"]
related_adrs: [42]
related_specs: []
scope:
  in: ["x"]
  out: []
governs:
  modules: []
  contracts: []
  entry_points: []
  files: ["docs/specs/example.md"]
  excludes: []
tests: []
acceptance_source: manual
language_source: en
---

# Example Spec

## 1. Wrong Heading
""",
    )

    findings = lint_file(path)

    assert any(f.rule_id == "frontmatter.spec-first-h2" for f in findings)


def test_spec_frontmatter_requires_at_least_one_owner(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "docs" / "specs" / "example.md",
        """---
spec_id: example
title: "Example Spec"
status: Draft
feature_branch: feat/example
created: 2026-05-19
input: "manual"
owners: []
related_adrs: [42]
related_specs: []
scope:
  in: ["x"]
  out: []
governs:
  modules: []
  contracts: []
  entry_points: []
  files: ["docs/specs/example.md"]
  excludes: []
tests: []
acceptance_source: manual
language_source: en
---

# Example Spec

## 1. Change Summary
""",
    )

    findings = lint_file(path)

    assert findings[0].severity is Severity.ERROR
    assert findings[0].rule_id == "frontmatter.validation"
    assert "owners" in findings[0].message


def test_adr042_governance_documents_pass_frontmatter_lint() -> None:
    paths = [
        REPO_ROOT / "docs" / "adr" / "ADR-042.md",
        REPO_ROOT / "docs" / "specs" / "adr-042-consistency-tools.md",
    ]

    for path in paths:
        assert lint_file(path) == []
