from __future__ import annotations

from pathlib import Path

from scieasy.qa.audit.facts import write_facts
from scieasy.qa.audit.full_audit import render_markdown, run
from scieasy.qa.schemas.facts import FactsRegistry
from scieasy.qa.schemas.report import AuditStatus

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_full_audit_renders_human_readable_facts_summary() -> None:
    report = run(REPO_ROOT, check_stale=False)

    markdown = render_markdown(report)

    assert report.status == AuditStatus.PASS
    assert "# ADR-042 Facts Audit Summary" in markdown
    assert "## 3. Fact Inventory" in markdown
    assert "## 5. Largest Symbol Areas" in markdown
    assert "No error-severity findings." in markdown


def test_full_audit_reports_stale_generated_facts(tmp_path: Path) -> None:
    facts_path = tmp_path / "generated.yaml"
    write_facts(FactsRegistry(source_sha="stale-sha"), facts_path)

    report = run(REPO_ROOT, facts_path=facts_path)

    assert report.status == AuditStatus.FAIL
    assert report.blocks_merge
    assert [finding.rule_id for finding in report.error_findings()] == ["facts.generated-stale"]
