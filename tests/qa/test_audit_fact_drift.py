from __future__ import annotations

from pathlib import Path

from scistudio.qa.audit.fact_drift import check_substitutions
from scistudio.qa.schemas.facts import Fact, FactsRegistry
from scistudio.qa.schemas.report import AuditStatus


def test_fact_drift_reports_unknown_fact_substitution(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "example.md"
    doc.parent.mkdir()
    doc.write_text("Value: {{ facts['missing:fact'] }}\n", encoding="utf-8")

    report = check_substitutions(tmp_path, FactsRegistry(source_sha="abc123"))

    assert report.status == AuditStatus.FAIL
    assert report.findings[0].rule_id == "fact-drift.unknown-fact"


def test_fact_drift_accepts_known_fact_substitution(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "example.md"
    doc.parent.mkdir()
    doc.write_text("Value: {{ facts['symbol:sample.func'] }}\n", encoding="utf-8")
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

    report = check_substitutions(tmp_path, facts)

    assert report.status == AuditStatus.PASS
