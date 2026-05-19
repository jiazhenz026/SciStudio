from pathlib import Path

import pytest

from scieasy.qa.audit import frontmatter_lint


def _write_md(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _valid_adr(path: Path) -> None:
    _write_md(
        path,
        """---
adr: 999
title: Documentation lint contract test
status: Accepted
date_created: 2026-05-01
date_accepted: 2026-05-01
date_superseded:
supersedes: []
superseded_by:
related: []
closes_issues: []
tracking_issue:
is_code_implementation: false
governs:
  modules: []
  contracts: []
  files: []
  excludes: []
  entry_points: []
tests: []
agent_editable: false
assisted_by: []
phase: implementation
tags: []
owner: "@owner"
co_authors: []
language_source: en
translations: []
---
# ADR-999: Docs

## 1. Decision Summary

### 1.1 Problems Addressed

| Problem | Impact | Category | Detailed section |
| --- | --- | --- | --- |
| Tooling | ADR validation | docs | [Section](#2-structure) |

## 2. Structure

Lorem ipsum.
"""
    )


def _invalid_spec(path: Path) -> None:
    _write_md(
        path,
        """---
spec_id: adr-000
title: Bad Spec
status: Draft
feature_branch: docs/adr-042-repository-governance-v2
created: 2026-05-01
input: manual
owners: ["@owner"]
related_adrs: []
related_specs: []
scope: {}
governs:
  modules: []
  contracts: []
  files: []
  excludes: []
  entry_points: []
tests: []
acceptance_source: adr
language_source: en
---
# Some Spec

## 2. Wrong start

"""
    )


@pytest.mark.parametrize("kind, writer, expected", [("adr", _valid_adr, "passed"), ("spec", _invalid_spec, "failed")])
def test_frontmatter_signatures(tmp_path: Path, kind: str, writer, expected: str) -> None:
    file_path = tmp_path / f"{kind}.md"
    writer(file_path)
    report = frontmatter_lint.lint_file(file_path, repo_root=tmp_path)
    assert report.status == expected
    if expected == "failed":
        assert report.findings
    else:
        assert report.findings == []


def test_frontmatter_detects_yaml_parse_error(tmp_path: Path) -> None:
    path = tmp_path / "adr-bad.md"
    path.write_text(
        """---
adr: [1, 2
---
# ADR-001: broken

## 1. Decision Summary
""",
        encoding="utf-8",
    )
    report = frontmatter_lint.lint_file(path, repo_root=tmp_path)
    assert report.status == "failed"
    assert any(finding.id == "frontmatter-yaml-invalid" for finding in report.findings)


def test_frontmatter_lint_path_filter(tmp_path: Path) -> None:
    source = tmp_path / "docs" / "adr" / "ADR-100.md"
    _valid_adr(source)
    report = frontmatter_lint.lint_paths([source], repo_root=tmp_path)
    assert report.status == "passed"
