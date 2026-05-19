from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.doc_drift import classify_repo
from scieasy.qa.schemas.facts import Fact, FactsRegistry
from scieasy.qa.schemas.report import AuditStatus


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
related_adrs: [42]
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
