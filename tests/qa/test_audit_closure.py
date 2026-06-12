from __future__ import annotations

from pathlib import Path

from scistudio.qa.audit.closure import check_bidirectional
from scistudio.qa.schemas.facts import Fact, FactsRegistry
from scistudio.qa.schemas.maintainers import MaintainerRule, Maintainers
from scistudio.qa.schemas.report import AuditStatus, Severity


def _write_planned_file_spec(path: Path, *, status: str, planned_file: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
spec_id: example
title: "Example Spec"
status: {status}
feature_branch: feat/example
created: 2026-05-19
input: "manual"
owners: ["@owner"]
related_adrs: []
related_specs: []
scope:
  in: ["x"]
  out: []
governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: ["{planned_file}"]
  excludes: []
tests: []
acceptance_source: manual
language_source: en
---

# Example Spec

## 1. Change Summary
""",
        encoding="utf-8",
    )


def _write_refactor_adr_for_file(path: Path, *, governed_file: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
adr: 42
title: "Refactor Existing Module"
status: Proposed
date_created: 2026-05-19
date_accepted: null
date_superseded: null
supersedes: []
superseded_by: null
related: []
closes_issues: []
tracking_issue: null
is_code_implementation: false
governs:
  modules: []
  contracts: []
  entry_points: []
  files: ["{governed_file}"]
  excludes: []
tests: []
agent_editable: false
assisted_by: ["Codex:gpt-5"]
phase: planning
tags: ["qa"]
owner: "@owner"
co_authors: []
language_source: en
translations: []
---

# ADR-042: Refactor Existing Module

## 1. Decision Summary
""",
        encoding="utf-8",
    )


def test_closure_reports_public_symbol_without_governance(tmp_path: Path) -> None:
    facts = FactsRegistry(
        source_sha="abc123",
        facts=[
            Fact(
                id="symbol:sample.func",
                kind="symbol",
                source="griffe",
                subject="sample.func",
                value={},
                source_sha="abc123",
                confidence="generated",
            )
        ],
    )

    report = check_bidirectional(tmp_path, facts)

    assert report.status == AuditStatus.FAIL
    assert report.findings[0].rule_id == "closure.missing-symbol-governance"


def test_closure_accepts_maintainer_owned_public_symbol(tmp_path: Path) -> None:
    facts = FactsRegistry(
        source_sha="abc123",
        facts=[
            Fact(
                id="symbol:sample.func",
                kind="symbol",
                source="griffe",
                subject="sample.func",
                value={"filepath": "src/sample.py"},
                source_sha="abc123",
                confidence="generated",
            )
        ],
    )
    maintainers = Maintainers(rules=[MaintainerRule(pattern="src/*.py", owners=["@owner"])])

    report = check_bidirectional(tmp_path, facts, maintainers=maintainers)

    assert report.status == AuditStatus.PASS
    assert report.summary["maintainer_covered_symbols"] == 1


def test_closure_accepts_module_governance(tmp_path: Path) -> None:
    spec = tmp_path / "docs" / "specs" / "example.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(
        """---
spec_id: example
title: "Example Spec"
status: Implemented
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
  modules: ["sample"]
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests: []
acceptance_source: manual
language_source: en
---

# Example Spec

## 1. Change Summary
""",
        encoding="utf-8",
    )
    facts = FactsRegistry(
        source_sha="abc123",
        facts=[
            Fact(
                id="symbol:sample.func",
                kind="symbol",
                source="griffe",
                subject="sample.func",
                value={},
                source_sha="abc123",
                confidence="generated",
            )
        ],
    )

    report = check_bidirectional(tmp_path, facts)

    assert report.status == AuditStatus.PASS


def test_closure_applies_locked_document_governance_addendum(tmp_path: Path) -> None:
    spec = tmp_path / "docs" / "specs" / "example.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(
        """---
spec_id: example
title: "Example Spec"
status: Implemented
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
  modules: ["old.sample"]
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests: []
acceptance_source: manual
language_source: en
---

# Example Spec

## 1. Change Summary

```yaml adr042-governance-amendment
governs:
  modules:
    add:
      - sample
    remove:
      - old.sample
```
""",
        encoding="utf-8",
    )
    facts = FactsRegistry(
        source_sha="abc123",
        facts=[
            Fact(
                id="symbol:sample.func",
                kind="symbol",
                source="griffe",
                subject="sample.func",
                value={},
                source_sha="abc123",
                confidence="generated",
            )
        ],
    )

    report = check_bidirectional(tmp_path, facts)

    assert report.status == AuditStatus.PASS


def test_closure_skips_draft_future_governance(tmp_path: Path) -> None:
    spec = tmp_path / "docs" / "specs" / "example.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(
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
  modules: ["sample"]
  contracts: []
  entry_points: []
  files: ["missing.py"]
  excludes: []
tests: []
acceptance_source: manual
language_source: en
---

# Example Spec

## 1. Change Summary
""",
        encoding="utf-8",
    )
    facts = FactsRegistry(source_sha="abc123")

    report = check_bidirectional(tmp_path, facts)

    assert report.status == AuditStatus.PASS


def test_closure_allows_unresolved_planned_file_for_planning_spec(tmp_path: Path) -> None:
    _write_planned_file_spec(
        tmp_path / "docs" / "specs" / "example.md",
        status="Planned",
        planned_file="src/sample/future.py",
    )

    report = check_bidirectional(tmp_path, FactsRegistry(source_sha="abc123"))

    assert report.status == AuditStatus.PASS
    assert [(finding.rule_id, finding.severity) for finding in report.findings] == [
        ("closure.planned-file", Severity.INFO)
    ]


def test_closure_reports_planned_file_that_now_exists_even_for_draft_spec(tmp_path: Path) -> None:
    planned_file = tmp_path / "src" / "sample" / "future.py"
    planned_file.parent.mkdir(parents=True)
    planned_file.write_text("VALUE = 1\n", encoding="utf-8")
    _write_planned_file_spec(
        tmp_path / "docs" / "specs" / "example.md",
        status="Draft",
        planned_file="src/sample/future.py",
    )

    report = check_bidirectional(tmp_path, FactsRegistry(source_sha="abc123"))

    assert report.status == AuditStatus.FAIL
    assert {finding.rule_id for finding in report.findings} == {"closure.planned-file-is-resolved"}


def test_closure_accepts_proposed_refactor_adr_for_existing_file(tmp_path: Path) -> None:
    existing_file = tmp_path / "src" / "sample" / "legacy.py"
    existing_file.parent.mkdir(parents=True)
    existing_file.write_text("VALUE = 1\n", encoding="utf-8")
    _write_refactor_adr_for_file(
        tmp_path / "docs" / "adr" / "ADR-042.md",
        governed_file="src/sample/legacy.py",
    )

    report = check_bidirectional(tmp_path, FactsRegistry(source_sha="abc123"))

    assert report.status == AuditStatus.PASS
    assert report.findings == []
