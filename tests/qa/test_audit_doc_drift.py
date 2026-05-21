from __future__ import annotations

from pathlib import Path

from scistudio.qa.audit.doc_drift import classify_repo
from scistudio.qa.schemas.facts import Fact, FactsRegistry
from scistudio.qa.schemas.report import AuditStatus


def _write_adr(path: Path, *, module: str, phase: str = "implementation", adr: int = 42) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
adr: {adr}
title: "Example ADR"
status: Proposed
date_created: 2026-05-19
date_accepted: null
date_superseded: null
supersedes: []
superseded_by: null
related: []
closes_issues: []
tracking_issue: 1
is_code_implementation: true
governs:
  modules: ["{module}"]
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests: ["tests/qa/test_audit_doc_drift.py"]
agent_editable: false
assisted_by: ["Codex:gpt-5"]
phase: {phase}
tags: ["qa"]
owner: "@owner"
co_authors: []
language_source: en
translations: []
---

# ADR-{adr:03d}: Example ADR

## 1. Decision Summary

### 1.1 Problems Addressed
""",
        encoding="utf-8",
    )


def _write_spec(path: Path, *, contract: str, governed_file: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
spec_id: example
title: "Example Spec"
status: Implemented
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
  contracts: ["{contract}"]
  entry_points: []
  files: ["{governed_file}"]
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


def _write_alignment_spec(
    path: Path,
    *,
    module: str,
    related_adrs: list[int],
    status: str = "Implemented",
) -> None:
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
related_adrs: {related_adrs}
related_specs: []
scope:
  in: ["x"]
  out: []
governs:
  modules: ["{module}"]
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


def test_doc_drift_reports_phantom_governed_contract_and_file(tmp_path: Path) -> None:
    _write_spec(tmp_path / "docs" / "specs" / "example.md", contract="sample.missing", governed_file="missing.py")
    facts = FactsRegistry(source_sha="abc123")

    report = classify_repo(tmp_path, facts)

    assert report.status == AuditStatus.FAIL
    assert {finding.rule_id for finding in report.findings} == {
        "doc-drift.phantom-contract",
        "doc-drift.phantom-file",
    }


def test_doc_drift_accepts_resolved_governed_contract_and_file(tmp_path: Path) -> None:
    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir()
    source.write_text("def func():\n    return None\n", encoding="utf-8")
    _write_spec(tmp_path / "docs" / "specs" / "example.md", contract="sample.func", governed_file="src/sample.py")
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

    report = classify_repo(tmp_path, facts)

    assert report.status == AuditStatus.PASS


def test_doc_drift_skips_draft_future_governance(tmp_path: Path) -> None:
    spec = tmp_path / "docs" / "specs" / "example.md"
    _write_spec(spec, contract="sample.future", governed_file="missing.py")
    text = spec.read_text(encoding="utf-8").replace("status: Implemented", "status: Draft")
    spec.write_text(text, encoding="utf-8")

    report = classify_repo(tmp_path, FactsRegistry(source_sha="abc123"))

    assert report.status == AuditStatus.PASS


def test_doc_drift_reports_adr_module_missing_from_active_spec(tmp_path: Path) -> None:
    _write_adr(tmp_path / "docs" / "adr" / "ADR-042.md", module="sample.expected")
    _write_alignment_spec(
        tmp_path / "docs" / "specs" / "example.md",
        module="sample.other",
        related_adrs=[42],
    )
    facts = FactsRegistry(
        source_sha="abc123",
        facts=[
            Fact(
                id="symbol:sample.expected",
                kind="symbol",
                source="griffe",
                subject="sample.expected",
                value={},
                source_sha="abc123",
                confidence="generated",
            ),
            Fact(
                id="symbol:sample.other",
                kind="symbol",
                source="griffe",
                subject="sample.other",
                value={},
                source_sha="abc123",
                confidence="generated",
            ),
        ],
    )

    report = classify_repo(tmp_path, facts)

    assert "doc-drift.missing-spec-governance" in {finding.rule_id for finding in report.findings}


def test_doc_drift_reports_active_spec_module_missing_from_related_adr(tmp_path: Path) -> None:
    _write_adr(tmp_path / "docs" / "adr" / "ADR-042.md", module="sample.expected")
    _write_alignment_spec(
        tmp_path / "docs" / "specs" / "example.md",
        module="sample.other",
        related_adrs=[42],
    )
    facts = FactsRegistry(
        source_sha="abc123",
        facts=[
            Fact(
                id="symbol:sample.expected",
                kind="symbol",
                source="griffe",
                subject="sample.expected",
                value={},
                source_sha="abc123",
                confidence="generated",
            ),
            Fact(
                id="symbol:sample.other",
                kind="symbol",
                source="griffe",
                subject="sample.other",
                value={},
                source_sha="abc123",
                confidence="generated",
            ),
        ],
    )

    report = classify_repo(tmp_path, facts)

    assert "doc-drift.missing-adr-governance" in {finding.rule_id for finding in report.findings}


def test_doc_drift_skips_adr_to_spec_alignment_for_planning_adr(tmp_path: Path) -> None:
    _write_adr(tmp_path / "docs" / "adr" / "ADR-042.md", module="sample.expected", phase="planning")
    _write_alignment_spec(
        tmp_path / "docs" / "specs" / "example.md",
        module="sample.expected",
        related_adrs=[42],
        status="Draft",
    )
    facts = FactsRegistry(
        source_sha="abc123",
        facts=[
            Fact(
                id="symbol:sample.expected",
                kind="symbol",
                source="griffe",
                subject="sample.expected",
                value={},
                source_sha="abc123",
                confidence="generated",
            )
        ],
    )

    report = classify_repo(tmp_path, facts)

    assert "doc-drift.missing-spec-governance" not in {finding.rule_id for finding in report.findings}


def test_doc_drift_skips_adr_to_spec_alignment_for_legacy_adr(tmp_path: Path) -> None:
    _write_adr(tmp_path / "docs" / "adr" / "ADR-042.md", module="sample.expected", phase="legacy")
    facts = FactsRegistry(
        source_sha="abc123",
        facts=[
            Fact(
                id="symbol:sample.expected",
                kind="symbol",
                source="griffe",
                subject="sample.expected",
                value={},
                source_sha="abc123",
                confidence="generated",
            )
        ],
    )

    report = classify_repo(tmp_path, facts)
    rule_ids = {finding.rule_id for finding in report.findings}

    assert "doc-drift.adr-without-implementation-spec" not in rule_ids
    assert "doc-drift.missing-spec-governance" not in rule_ids


def test_doc_drift_reports_active_spec_link_to_missing_adr(tmp_path: Path) -> None:
    _write_alignment_spec(
        tmp_path / "docs" / "specs" / "example.md",
        module="sample.expected",
        related_adrs=[999],
    )
    facts = FactsRegistry(
        source_sha="abc123",
        facts=[
            Fact(
                id="symbol:sample.expected",
                kind="symbol",
                source="griffe",
                subject="sample.expected",
                value={},
                source_sha="abc123",
                confidence="generated",
            )
        ],
    )

    report = classify_repo(tmp_path, facts)

    assert "doc-drift.unlinked-spec" in {finding.rule_id for finding in report.findings}
