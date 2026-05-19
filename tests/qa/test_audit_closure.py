from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.closure import check_bidirectional
from scieasy.qa.schemas.facts import Fact, FactsRegistry
from scieasy.qa.schemas.report import AuditStatus


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
